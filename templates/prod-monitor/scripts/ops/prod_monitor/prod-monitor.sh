#!/usr/bin/env bash
# Prod monitoring loop (factory module prod-monitor):
# watchdog (cron, no model) → monitor (Claude Agent SDK) → monitor channel → On-call → group and developer.
# Runs from a copy in $PM_HOME, not from the repo checkout: switching branches does not break the loop.
#
#   prod-monitor.sh install   code copy, venv (uv), channel dependencies (bun), channel secret, mcp.json, desk.env, cron line
#   prod-monitor.sh up        install + restart of the On-call agent with the monitor channel (group ~1 min without it)
#   prod-monitor.sh status    what works and what does not
#   prod-monitor.sh test      test event all the way to the group (the On-call agent posts it as is)
#   prod-monitor.sh run       one monitor pass now (~40 s, uses the subscription)
#   prod-monitor.sh down      remove from cron (the On-call agent and the channel stay)
#
# Subscription token: `setup-token.sh` → CLAUDE_CODE_OAUTH_TOKEN=… in $PM_TOKEN_ENV (0600, outside the repo).
# No file — the monitor runs on the current Claude Code login. The script never reads or prints the value.
# Channel secret: $PM_STATE/channel.token (0600), generated once; server.ts gets it via mcp.json (0600),
# deliver.py reads the file. Neither value is printed.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# From the repo checkout — its root; from the installed copy — the path remembered at install.
REPO="$(git -C "$SRC" rev-parse --show-toplevel 2>/dev/null || cat "$SRC/.repo_path")"
PM_ROOT="${PM_ROOT:-$HOME/<pfx>-monitor}"
PM_HOME="$PM_ROOT/prod_monitor"
PM_VENV="${PM_VENV:-$PM_ROOT/.venv-prod-monitor}"
PM_STATE="${PROD_MONITOR_STATE:-$PM_ROOT/state/prod_monitor}"
PM_CONFIG="${PROD_MONITOR_CONFIG:-$HOME/.config/<project>}"
PM_TOKEN_ENV="$PM_CONFIG/monitor.env"
PM_ACCESS_ENV="$PM_CONFIG/prod-watch.env"
# Channel port: one per project on the machine (8790, 8791, …) — otherwise two channels will not start.
MONITOR_CHANNEL_PORT="${MONITOR_CHANNEL_PORT:-<channel port>}"
BUN="${BUN_BIN:-$HOME/.bun/bin}/bun"
CHANNEL_URL="http://127.0.0.1:$MONITOR_CHANNEL_PORT"
PM_CHANNEL_TOKEN="$PM_STATE/channel.token"
CRON_TAG="# prod-monitor $PM_ROOT"
DESK="$REPO/scripts/feedback-desk.sh"
DESK_CONFIG="$REPO/.claude/feedback-desk/config.env"

say() { echo "prod-monitor: $*"; }
mark() { if eval "$2"; then echo "  ✓ $1"; else echo "  ✗ $1"; fi; }

cron_line() {
  echo "* * * * * PATH=/usr/local/bin:/usr/bin:/bin flock -n $PM_STATE/watchdog.lock env -C $PM_ROOT PM_ROOT=$PM_ROOT PROD_MONITOR_STATE=$PM_STATE PROD_MONITOR_CONFIG=$PM_CONFIG $PM_VENV/bin/python -m prod_monitor.watchdog >> $PM_STATE/watchdog.log 2>&1 $CRON_TAG"
}

install() {
  [ -f "$PM_ACCESS_ENV" ] || { say "no prod DB access: $PM_ACCESS_ENV (PROD_RO_DATABASE_URL, read-only role)"; exit 1; }
  [ -x "$BUN" ] || { say "no Bun ($BUN): curl -fsSL https://bun.sh/install | bash"; exit 1; }
  [ -f "$DESK_CONFIG" ] || { say "no On-call agent ($DESK_CONFIG) — set up the feedback-desk module first"; exit 1; }
  if grep -qF -e '<project>' -e '<pfx>' -e '<abs path' -e '<https://' "$SRC/project.py" ||
      case "$PM_ROOT$PM_CONFIG$MONITOR_CHANNEL_PORT" in *'<'*) true ;; *) false ;; esac; then
    say "placeholders <…> remain in project.py or the prod-monitor.sh header — fill them in (MANIFEST §Setup)"; exit 1
  fi
  mkdir -p "$PM_HOME" "$PM_STATE"
  rsync -a --delete --exclude node_modules --exclude mcp.json --exclude desk.env --exclude .repo_path \
    --exclude __pycache__ --exclude 'test_*.py' "$SRC/" "$PM_HOME/"
  echo "$REPO" > "$PM_HOME/.repo_path"
  [ -x "$PM_VENV/bin/python" ] || uv venv -q -p 3.12 "$PM_VENV"
  uv pip install -q -p "$PM_VENV/bin/python" -r "$PM_HOME/requirements.txt"
  env -C "$PM_HOME/channel" "$BUN" install --no-summary >/dev/null
  if [ ! -s "$PM_CHANNEL_TOKEN" ]; then
    (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$PM_CHANNEL_TOKEN")
  fi
  chmod 600 "$PM_CHANNEL_TOKEN"
  # The On-call config is the source of truth for the group, the plugin directory and the development session.
  (
    set +u
    # shellcheck disable=SC1090
    . "$DESK_CONFIG"
    umask 077
    printf 'DESK_GROUP_ID=%s\nDESK_STATE_DIR=%s\nDESK_DEV_SESSION=%s\nMONITOR_CHANNEL_PORT=%s\n' \
      "$DESK_GROUP_ID" "$DESK_STATE_DIR" "$DESK_DEV_SESSION" "$MONITOR_CHANNEL_PORT" > "$PM_HOME/desk.env"
    python3 - "$PM_HOME/channel/mcp.json" "$BUN" "$PM_HOME/channel/server.ts" "$MONITOR_CHANNEL_PORT" \
      "$(basename "$REPO")" "$DESK_DEV_SESSION" "$PM_CHANNEL_TOKEN" <<'PY'
import json, os, sys
path, bun, server, port, project, dev, token_file = sys.argv[1:]
token = open(token_file).read().strip()
env = {"MONITOR_CHANNEL_PORT": port, "MONITOR_PROJECT": project, "DESK_DEV_SESSION": dev,
       "MONITOR_CHANNEL_TOKEN": token}
fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump({"mcpServers": {"monitor": {"command": bun, "args": [server], "env": env}}}, f)
os.chmod(path + ".tmp", 0o600)
os.replace(path + ".tmp", path)
PY
  )
  { crontab -l 2>/dev/null | grep -vF "$CRON_TAG" || true; cron_line; } | crontab -
  say "installed in $PM_HOME, watchdog in cron once a minute; channel $CHANNEL_URL"
  [ -f "$PM_TOKEN_ENV" ] || say "no $PM_TOKEN_ENV — the monitor will run on the current Claude Code login (it expires; better run setup-token.sh)"
}

up() {
  install
  DESK_MONITOR_MCP="$PM_HOME/channel/mcp.json" "$DESK" restart
  for _ in $(seq 1 30); do curl -sf -m 2 "$CHANNEL_URL/health" >/dev/null && break; sleep 1; done
  status
}

status() {
  echo "prod-monitor:"
  mark "code in $PM_HOME" "[ -f $PM_HOME/watchdog.py ]"
  mark "venv with SDK" "$PM_VENV/bin/python -c 'import claude_agent_sdk' 2>/dev/null"
  mark "subscription token ($PM_TOKEN_ENV)" "[ -f $PM_TOKEN_ENV ]"
  mark "watchdog in cron" "crontab -l 2>/dev/null | grep -qF '$CRON_TAG'"
  mark "On-call agent alive" "$DESK status >/dev/null 2>&1"
  mark "channel secret ($PM_CHANNEL_TOKEN, 0600)" "[ \"\$(stat -c %a $PM_CHANNEL_TOKEN 2>/dev/null)\" = 600 ]"
  mark "monitor channel listening on $CHANNEL_URL" "curl -sf -m 2 $CHANNEL_URL/health >/dev/null"
  if [ -f "$PM_STATE/watchdog.log" ]; then echo "  latest watchdog entries:"; grep -E "quiet|wake|fallback" "$PM_STATE/watchdog.log" | tail -3 | sed 's/^/    /'; fi
}

py() { env -C "$PM_ROOT" PM_ROOT="$PM_ROOT" PROD_MONITOR_STATE="$PM_STATE" PROD_MONITOR_CONFIG="$PM_CONFIG" "$PM_VENV/bin/python" -m "$@"; }

case "${1:-status}" in
  install) install ;;
  up) up ;;
  status) status ;;
  test) py prod_monitor.monitor --test-delivery ;;
  run) py prod_monitor.monitor ;;
  down) { crontab -l 2>/dev/null | grep -vF "$CRON_TAG" || true; } | crontab -; say "watchdog removed from cron" ;;
  *) echo "usage: $0 install|up|status|test|run|down" >&2; exit 2 ;;
esac

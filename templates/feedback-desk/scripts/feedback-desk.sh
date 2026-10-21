#!/usr/bin/env bash
# On-call agent for the Telegram feedback group (factory module feedback-desk): a persistent
# Claude Code session with the official plugin:telegram channel (Claude Code Channels).
# Settings — .claude/feedback-desk/config.env, role — ROLE.md,
# setup from scratch — the feedback-desk skill.
#
#   scripts/feedback-desk.sh check    is the environment ready (config, tmux, Bun, plugin, token)
#   scripts/feedback-desk.sh status   is the On-call agent alive
#   scripts/feedback-desk.sh up       start it if not running (idempotent)
#   scripts/feedback-desk.sh down     stop it
#   scripts/feedback-desk.sh restart  stop and start (after editing the config or the role)
#
# The script never reads or prints the bot token: it lives in $DESK_STATE_DIR/.env (0600),
# put there by the owner. access.json is written from the config on every start.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$here/.claude/feedback-desk/config.env"
ROLE_FILE="$here/.claude/feedback-desk/ROLE.md"
BUN_BIN="${BUN_BIN:-$HOME/.bun/bin}"

say() { echo "feedback-desk: $*"; }
fail() { say "$*"; exit 1; }

is_up() {
  # The tmux session exists and its process has not exited.
  tmux has-session -t "$DESK_TMUX" 2>/dev/null &&
    [ "$(tmux list-panes -t "$DESK_TMUX" -F '#{pane_dead}' 2>/dev/null | head -n 1)" = "0" ]
}

# Each check prints what to do; the exit code is the number of failed checks.
check() {
  local bad=0
  # Plugin tags in ROLE.md (<channel>, <b>) are not placeholders; look only for our own.
  if grep -qF -e '<project>' -e '<pfx>' -e '<owner>' -e '<abs path' -e '<dev session name>' \
      -e '<group id>' -e '<who and in which role' "$here/.claude/feedback-desk/config.env" "$ROLE_FILE"; then
    say "✗ placeholders <…> remain in config.env or ROLE.md — fill them in (feedback-desk skill, step 2)"; bad=$((bad + 1))
  fi
  command -v tmux >/dev/null || { say "✗ no tmux"; bad=$((bad + 1)); }
  [ -x "$BUN_BIN/bun" ] || { say "✗ no Bun in $BUN_BIN — channel plugins run on Bun: curl -fsSL https://bun.sh/install | bash"; bad=$((bad + 1)); }
  claude plugin list 2>/dev/null | grep -q "${DESK_PLUGIN%%@*}" ||
    { say "✗ plugin $DESK_PLUGIN is not installed: claude plugin install $DESK_PLUGIN --scope user"; bad=$((bad + 1)); }
  grep -q '^TELEGRAM_BOT_TOKEN=.\+' "$DESK_STATE_DIR/.env" 2>/dev/null ||
    { say "✗ no bot token in $DESK_STATE_DIR/.env — the owner puts it there (feedback-desk skill, step 3)"; bad=$((bad + 1)); }
  [ "$bad" -eq 0 ] && say "✓ environment ready"
  return "$bad"
}

# access.json comes from the config: the config in the repo is the source of truth. The DM allowFrom
# (filled by the owner's pairing) and other keys are preserved.
write_access() {
  install -d -m 700 "$DESK_STATE_DIR"
  ACCESS_PATH="$DESK_STATE_DIR/access.json" GROUP_ID="$DESK_GROUP_ID" \
    REQUIRE_MENTION="$DESK_REQUIRE_MENTION" GROUP_ALLOW="$DESK_GROUP_ALLOW" DM_POLICY="$DESK_DM_POLICY" \
    python3 - <<'PY'
import json, os
path = os.environ["ACCESS_PATH"]
try:
    cur = json.load(open(path))
except Exception:
    cur = {}
allow = [x.strip() for x in os.environ["GROUP_ALLOW"].split(",") if x.strip()]
cur["dmPolicy"] = os.environ["DM_POLICY"]
cur.setdefault("allowFrom", [])
cur["groups"] = {os.environ["GROUP_ID"]: {
    "requireMention": os.environ["REQUIRE_MENTION"] == "true", "allowFrom": allow}}
cur.setdefault("ackReaction", "👀")
cur.setdefault("replyToMode", "first")
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(cur, f, ensure_ascii=False, indent=2)
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
}

# Claude Code loads a custom channel (monitor, module prod-monitor) only with the development flag and asks
# again on start — we confirm the first option "I am using this for local development" with Enter.
confirm_dev_channel() {
  for _ in $(seq 1 30); do
    if tmux capture-pane -p -t "$DESK_TMUX" 2>/dev/null | grep -q "Loading development channels"; then
      tmux send-keys -t "$DESK_TMUX" Enter
      say "monitor channel connected"
      return
    fi
    sleep 1
  done
  say "did not see the monitor channel prompt — check: tmux attach -t $DESK_TMUX"
}

up() {
  if is_up; then say "already running (tmux $DESK_TMUX, session \"$DESK_NAME\")"; return; fi
  check >/dev/null || { check || true; fail "environment not ready — see above"; }
  write_access
  tmux kill-session -t "$DESK_TMUX" 2>/dev/null || true
  local remote=() monitor=()
  [ "$DESK_REMOTE" = "true" ] && remote=(--remote-control "$DESK_NAME")
  [ -f "${DESK_MONITOR_MCP:-}" ] &&
    monitor=(--mcp-config "$DESK_MONITOR_MCP" --dangerously-load-development-channels server:monitor)
  tmux new-session -d -s "$DESK_TMUX" -c "$DESK_WORKDIR" \
    env PATH="$BUN_BIN:$PATH" TELEGRAM_STATE_DIR="$DESK_STATE_DIR" \
    claude --name "$DESK_NAME" --model "$DESK_MODEL" "${remote[@]}" \
    --settings "{\"env\":{\"TELEGRAM_STATE_DIR\":\"$DESK_STATE_DIR\"}}" \
    --channels "plugin:$DESK_PLUGIN" "${monitor[@]}" \
    --append-system-prompt-file "$ROLE_FILE"
  [ ${#monitor[@]} -gt 0 ] && confirm_dev_channel
  for _ in $(seq 1 30); do is_up && break; sleep 1; done
  is_up || fail "did not start — check: tmux attach -t $DESK_TMUX"
  say "started: tmux $DESK_TMUX, session \"$DESK_NAME\""
}

down() {
  if tmux kill-session -t "$DESK_TMUX" 2>/dev/null; then say "stopped"; else say "was not running"; fi
}

case "${1:-status}" in
  check) check ;;
  status) if is_up; then say "running (tmux $DESK_TMUX, session \"$DESK_NAME\")"; else say "not running"; exit 1; fi ;;
  up) up ;;
  down) down ;;
  restart) down; up ;;
  *) echo "usage: $0 check|status|up|down|restart" >&2; exit 2 ;;
esac

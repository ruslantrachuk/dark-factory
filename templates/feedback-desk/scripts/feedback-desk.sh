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
#   scripts/feedback-desk.sh rules    the permission rules the session gets (what it may Read)
#   scripts/feedback-desk.sh deploy-allowed <from_id>
#                                     exit 0 only if deploy from the chat is switched on and the id is listed
#
# The script never reads or prints the bot token: it lives in $DESK_STATE_DIR/.env (0600),
# put there by the owner. access.json is written from the config on every start.
# The session gets only the tools its job needs (DESK_TOOLS, DESK_PERMISSION_MODE, desk_allow_rules,
# desk_deny_rules): no Bash, no file edits, no subagents, Read only in its own directory and the user-facing docs —
# the client group can talk to it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
. "$here/.claude/feedback-desk/config.env"
ROLE_FILE="$here/.claude/feedback-desk/ROLE.md"
# defaults for a config.env written before these keys existed
DESK_READ_PATHS="${DESK_READ_PATHS-README.md docs}"
DESK_DEPLOY_FROM_CHAT="${DESK_DEPLOY_FROM_CHAT:-off}"
DESK_ACCEPT_DEV_CHANNEL="${DESK_ACCEPT_DEV_CHANNEL:-0}"
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
  if [ -z "${DESK_GROUP_ALLOW// /}" ] && [ "${DESK_GROUP_OPEN:-false}" != "true" ]; then
    say "✗ DESK_GROUP_ALLOW is empty — list the numeric ids who may wake the session, or set DESK_GROUP_OPEN=true (any group member can wake it)"
    bad=$((bad + 1))
  fi
  local key
  for key in DESK_GROUP_ALLOW DESK_DEPLOY_ALLOW; do
    [[ "${!key:-}" =~ ^[[:space:]]*(-?[0-9]+[[:space:]]*(,[[:space:]]*-?[0-9]+[[:space:]]*)*)?$ ]] ||
      { say "✗ $key must be numeric Telegram ids, comma-separated"; bad=$((bad + 1)); }
  done
  # Deploy from the chat trusts a sender id the On-call model copied into the envelope — an explicit opt-in.
  case "${DESK_DEPLOY_FROM_CHAT:-off}:${DESK_DEPLOY_ALLOW// /}" in
    off:) ;;
    off:*) say "✗ DESK_DEPLOY_ALLOW is set but DESK_DEPLOY_FROM_CHAT=off — clear the list, or opt in with DESK_DEPLOY_FROM_CHAT=llm-checked (risk: feedback-desk skill, section C)"; bad=$((bad + 1)) ;;
    llm-checked:) say "✗ DESK_DEPLOY_FROM_CHAT=llm-checked with an empty DESK_DEPLOY_ALLOW — list the ids or set it back to off"; bad=$((bad + 1)) ;;
    llm-checked:*) ;;
    *) say "✗ DESK_DEPLOY_FROM_CHAT must be off or llm-checked"; bad=$((bad + 1)) ;;
  esac
  local name
  for name in $DESK_READ_PATHS; do
    [[ "$name" =~ ^[A-Za-z0-9._@+-]+$ && "$name" != .claude && "$name" != .git && "$name" != . && "$name" != .. ]] ||
      { say "✗ DESK_READ_PATHS: \"$name\" — top-level names of the checkout only (no /, not .claude or .git)"; bad=$((bad + 1)); }
  done
  unsafe_entries >/dev/null ||
    { say "✗ top-level names in $DESK_WORKDIR that a permission rule cannot hold (space, comma, brackets): $(unsafe_entries | tr '\n' ' ')— rename them"; bad=$((bad + 1)); }
  case ",${DESK_TOOLS// /}," in
    *,Bash,* | *,Edit,* | *,Write,* | *,NotebookEdit,* | *,Agent,* | *,Workflow,* | *,default,*)
      say "✗ DESK_TOOLS gives the On-call session tools that run commands or edit files — remove them"; bad=$((bad + 1)) ;;
  esac
  command -v tmux >/dev/null || { say "✗ no tmux"; bad=$((bad + 1)); }
  [ -x "$BUN_BIN/bun" ] || { say "✗ no Bun in $BUN_BIN — channel plugins run on Bun: install it from https://bun.sh/docs/installation (a release zip checked against its SHASUMS256.txt, or your package manager)"; bad=$((bad + 1)); }
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

# Permission rules for the session (--allowedTools). With DESK_PERMISSION_MODE=dontAsk every other call is
# denied without a prompt. Read is allowed in the desk's own directory, the user-facing docs (DESK_READ_PATHS)
# and the plugin inbox (photos from the group); the plugin token in $DESK_STATE_DIR/.env stays out of reach.
work="/${DESK_WORKDIR%/}"  # "//abs/path": an absolute path in a permission rule
read_rule() { if [ -d "$DESK_WORKDIR/$1" ]; then echo "Read($work/$1/**)"; else echo "Read($work/$1)"; fi; }

desk_allow_rules() {
  local plugin="${DESK_PLUGIN%%@*}" name
  local rules=("mcp__plugin_${plugin}_${plugin}" SendMessage ListAgents ToolSearch
    "Read($work/.claude/feedback-desk/**)" "Read(/${DESK_STATE_DIR%/}/inbox/**)")
  for name in $DESK_READ_PATHS; do rules+=("$(read_rule "$name")"); done
  local IFS=,
  echo "${rules[*]}"
}

# Claude Code lets a session Read its working directory without an allow rule, so narrowing Read takes deny
# rules: every top-level entry of the checkout that is not in DESK_READ_PATHS, and every entry of .claude/ except
# feedback-desk/ (deny wins over allow, so the allowed parts cannot sit under a denied directory). Computed at
# start: an entry created later is readable until the next restart.
unsafe_entries() {
  local bad=0 entry
  for entry in "$DESK_WORKDIR"/* "$DESK_WORKDIR"/.[!.]* "$DESK_WORKDIR"/.claude/* "$DESK_WORKDIR"/.claude/.[!.]*; do
    [ -e "$entry" ] || continue
    [[ "$(basename "$entry")" =~ ^[A-Za-z0-9._@+-]+$ ]] || { echo "${entry#"$DESK_WORKDIR"/}"; bad=1; }
  done
  return "$bad"
}

desk_deny_rules() {
  local rules=() entry name keep allowed
  for entry in "$DESK_WORKDIR"/* "$DESK_WORKDIR"/.[!.]*; do
    [ -e "$entry" ] || continue
    name="$(basename "$entry")"
    [ "$name" = .claude ] && continue
    keep=0
    for allowed in $DESK_READ_PATHS; do [ "$name" = "$allowed" ] && keep=1; done
    [ "$keep" = 1 ] || rules+=("$(read_rule "$name")")
  done
  for entry in "$DESK_WORKDIR"/.claude/* "$DESK_WORKDIR"/.claude/.[!.]*; do
    [ -e "$entry" ] || continue
    name="$(basename "$entry")"
    [ "$name" = feedback-desk ] || rules+=("$(read_rule ".claude/$name")")
  done
  [ -n "${DESK_DISALLOWED_TOOLS:-}" ] && rules+=("$DESK_DISALLOWED_TOOLS")
  local IFS=,
  echo "${rules[*]}"
}

# Deploy authorisation from the chat, for the development session: exit 0 only when the owner opted in
# (DESK_DEPLOY_FROM_CHAT=llm-checked) and the id is in DESK_DEPLOY_ALLOW. The id itself comes from the envelope,
# which the On-call model writes — see the risk in the skill, section C.
deploy_allowed() {
  local id="${1:-}" allowed
  [ "${DESK_DEPLOY_FROM_CHAT:-off}" = llm-checked ] || { say "deploy from the chat is off — ask the owner"; return 1; }
  [[ "$id" =~ ^-?[0-9]+$ ]] || { say "not a numeric id: \"$id\" — ask the owner"; return 1; }
  for allowed in ${DESK_DEPLOY_ALLOW//,/ }; do
    [ "$allowed" = "$id" ] && { say "$id may request a deploy (llm-checked)"; return 0; }
  done
  say "$id is not in DESK_DEPLOY_ALLOW — ask the owner"; return 1
}

# Claude Code loads a custom channel (the monitor, module prod-monitor) only with
# --dangerously-load-development-channels and shows a confirmation dialog on every start; a session in tmux
# has nobody to answer it. Only with DESK_ACCEPT_DEV_CHANNEL=1 (the owner's yes, recorded by the setup skill)
# we press Enter (the focused option is "I am using this for local development"), and only when that exact
# dialog is on screen and it lists exactly server:monitor — the channel from our own mcp.json — so the keypress
# can never land in a different prompt or confirm a channel we did not ask for. Without it the session starts
# without the monitor channel.
dev_channel_prompt_on_screen() {
  local screen
  screen="$(tmux capture-pane -p -t "$DESK_TMUX" 2>/dev/null | sed 's/[│┃║]//g')" || return 1
  grep -q "WARNING: Loading development channels" <<<"$screen" &&
    grep -Eq '^[[:space:]]*Channels: server:monitor[[:space:]]*$' <<<"$screen" &&
    grep -q "I am using this for local development" <<<"$screen"
}

confirm_dev_channel() {
  for _ in $(seq 1 30); do
    if dev_channel_prompt_on_screen; then
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
  local remote=() monitor=() disallowed=()
  [ "$DESK_REMOTE" = "true" ] && remote=(--remote-control "$DESK_NAME")
  if [ -f "${DESK_MONITOR_MCP:-}" ]; then
    if [ "${DESK_ACCEPT_DEV_CHANNEL:-0}" = 1 ]; then
      monitor=(--mcp-config "$DESK_MONITOR_MCP" --dangerously-load-development-channels server:monitor)
    else
      say "monitor channel not loaded: DESK_ACCEPT_DEV_CHANNEL=1 is not set in config.env (prod-monitor skill)"
    fi
  fi
  local deny; deny="$(desk_deny_rules)"
  [ -n "$deny" ] && disallowed=(--disallowedTools "$deny")
  # QUOTA_ROLE=desk: the quota guard (dark-factory plugin) never cuts off answering the client.
  tmux new-session -d -s "$DESK_TMUX" -c "$DESK_WORKDIR" \
    env PATH="$BUN_BIN:$PATH" TELEGRAM_STATE_DIR="$DESK_STATE_DIR" QUOTA_ROLE=desk \
    claude --name "$DESK_NAME" --model "$DESK_MODEL" "${remote[@]}" \
    --settings "{\"env\":{\"TELEGRAM_STATE_DIR\":\"$DESK_STATE_DIR\",\"QUOTA_ROLE\":\"desk\"}}" \
    --tools "$DESK_TOOLS" --permission-mode "$DESK_PERMISSION_MODE" \
    --allowedTools "$(desk_allow_rules)" "${disallowed[@]}" \
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
  rules) echo "allow: $(desk_allow_rules)"; echo "deny:  $(desk_deny_rules)" ;;
  deploy-allowed) deploy_allowed "${2:-}" ;;
  *) echo "usage: $0 check|status|up|down|restart|rules|deploy-allowed <from_id>" >&2; exit 2 ;;
esac

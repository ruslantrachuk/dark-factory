#!/usr/bin/env bash
# SessionStart for every agent: the one session header the project's hooks call.
#   Claude Code: .claude/settings.json → SessionStart → bash "$CLAUDE_PROJECT_DIR/scripts/agent/session-start.sh" claude
#   Codex:       .codex/hooks.json     → SessionStart (startup and compact) → … session-start.sh codex
# It runs, in order: the execution queue primer (bd prime), the environment block (env-context.sh) and the session
# header (session-context.sh). The agent name is the first argument; without one it is guessed from the environment
# ($CLAUDE_PROJECT_DIR → claude, $CODEX_THREAD_ID → codex). Parts that only make sense for one agent check AGENT.
# Always exits 0: a header that fails must not stop the session.
set +e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
agent="${1:-}"
if [ -z "$agent" ]; then
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then agent=claude
  elif [ -n "${CODEX_THREAD_ID:-}" ]; then agent=codex
  else agent=unknown; fi
fi
export AGENT="$agent"
command -v bd >/dev/null 2>&1 && bd prime
bash "$here/env-context.sh"
bash "$here/session-context.sh"
exit 0

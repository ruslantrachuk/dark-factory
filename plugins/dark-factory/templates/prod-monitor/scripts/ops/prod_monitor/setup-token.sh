#!/usr/bin/env bash
# One-year subscription token for the prod monitor → $PROD_MONITOR_CONFIG/monitor.env (0600, outside the repo).
# Run by the owner in their own terminal: claude setup-token → paste the token (input hidden) → check.
# The token is never printed and never gets into the shell history.
# The check runs with --setting-sources local: a plain claude -p loads plugin:telegram, which kills the On-call bot reader.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
file="${PROD_MONITOR_CONFIG:-$HOME/.config/<project>}/monitor.env"

echo "1/3 The claude.ai login will open now — sign in with the subscription account (Max/Pro) the monitor will run on."
claude setup-token || { echo "claude setup-token failed — nothing written"; exit 1; }

echo
read -rs -p "2/3 Paste the token the command showed (input is hidden): " token
echo
token="$(printf '%s' "$token" | tr -d '[:space:]')"
[ -n "$token" ] || { echo "empty — nothing written"; exit 1; }
case "$token" in sk-ant-oat*) ;; *) echo "warning: a setup-token token usually starts with sk-ant-oat — check that you pasted it" ;; esac

mkdir -p "$(dirname "$file")"
(umask 077; printf 'CLAUDE_CODE_OAUTH_TOKEN=%s\n' "$token" > "$file")
chmod 600 "$file"
echo "written to $file (mode 600)"

echo "3/3 Checking that the token is accepted…"
answer="$(env -u ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN="$token" claude -p --setting-sources local \
  --strict-mcp-config --mcp-config '{"mcpServers":{}}' --model claude-haiku-5-5 "Answer with one word: works" 2>&1 || true)"
unset token
case "$answer" in
  *[Ww]orks*) echo "token works" ;;
  *) echo "token failed the check: $answer"; exit 1 ;;
esac

"$here/prod-monitor.sh" status

#!/usr/bin/env bash
# env-awareness: prints a capability block for the current environment.
# Source of truth — the per-machine marker .claude/env (gitignored). Fill in the texts on deployment.
# Safe by design: always exit 0, does not break the session when the marker is missing.
set +e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
root="$(cd "$here/../.." 2>/dev/null && pwd)"
env="$(cat "$root/.claude/env" 2>/dev/null | tr -d '[:space:]')"
case "$env" in
  vps)
    echo "🌙 ENV=vps (autonomous). ALLOWED: <bd ready/claim, tests, commit to a feature branch, harness push>. FORBIDDEN: <ship/merge/final close — added by the night-local module>."
    ;;
  mac)
    echo "💻 ENV=mac (attended). <ship/merge — on the owner's explicit \"yes\"; other project capabilities>."
    ;;
  *)
    echo "⚠️ ENV not set (.claude/env: mac|vps). Environment undetermined — ship/merge only after the owner's confirmation."
    ;;
esac
# Binding to the canon: without it, reconciliation with the dark factory is guessing which version
# of the template the project was deployed from (.harness/README.md). No file — stay quiet.
base_sha="$(head -n 1 "$root/.harness/base-sha" 2>/dev/null | tr -d '[:space:]')"
if [ -n "$base_sha" ]; then
  echo "🧭 harness: base @ ${base_sha} · reconcile with the canon: scripts/harness-diff.sh"
fi
# A session from a git worktree does not see the main checkout's .claude/settings.local.json
# (it is gitignored): without shared permissions in ~/.claude/settings.json agents stumble on
# permission prompts for every file. Warn right away,
# not at the tenth prompt. No python3 / settings.json — stay quiet.
common="$(git -C "$root" rev-parse --git-common-dir 2>/dev/null)"
case "$common" in
  "") main_root="" ;;
  /*) main_root="$(dirname "$common")" ;;
  *)  main_root="$(cd "$root/$common/.." 2>/dev/null && pwd)" ;;
esac
top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$main_root" ] && [ -n "$top" ] && [ "$main_root" != "$top" ] && [ -f "$HOME/.claude/settings.json" ]; then
  if ! python3 - "$main_root" "$HOME/.claude/settings.json" <<'PY' 2>/dev/null
import json, sys
main_root, path = sys.argv[1], sys.argv[2]
perms = json.load(open(path)).get("permissions", {})
dirs = perms.get("additionalDirectories", [])
sys.exit(0 if main_root in dirs and "Bash" in perms.get("allow", []) else 1)
PY
  then
    echo "⚠️ The session is in a worktree ($top), but ~/.claude/settings.json lacks the project's shared permissions (additionalDirectories: $main_root, allow: Bash). The main checkout's settings.local.json does not reach here — expect permission prompts. Suggest that the owner move the permissions to ~/.claude/settings.json."
  fi
fi
exit 0

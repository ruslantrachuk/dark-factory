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
    echo "🖥️ ENV=vps (unattended remote-control sessions). ALLOWED: <bd ready/claim, tests, commit to a feature branch, Workflow runs in the session's worktree, harness push>. FORBIDDEN: <ship/merge/final close without the owner's explicit \"yes\">."
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
# Fence level (.claude/fences.env, CLAUDE.md "Fences"); GUARD=off is a human's bypass — say it loudly.
fence_level="$(sed -n 's/^[[:space:]]*FENCE_LEVEL[[:space:]]*=[[:space:]]*["'"'"']\{0,1\}\([a-z]*\).*/\1/p' "$root/.claude/fences.env" 2>/dev/null | tail -n 1)"
if [ "${GUARD:-}" = "off" ]; then
  echo "⚠️ fences: GUARD=off — the guard is switched off for this session by the human; push/merge rules hold only as instructions."
else
  echo "🛡️ fences: level ${fence_level:-standard} — push/merge/tag rules are enforced by the dark-factory plugin's guard; merging only via scripts/merge-feature.sh --accepted-by \"<name>\"."
fi
# The main checkout of this repository (a worktree session runs from .claude/worktrees/… or elsewhere).
common="$(git -C "$root" rev-parse --git-common-dir 2>/dev/null)"
case "$common" in
  "") main_root="" ;;
  /*) main_root="$(dirname "$common")" ;;
  *)  main_root="$(cd "$root/$common/.." 2>/dev/null && pwd)" ;;
esac
top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)"
# The execution queue is one local store per project, in the main checkout's .beads/ (outside git;
# .beads/README.md). Worktrees share it: BEADS_DIR names it for every bd call of this session and of
# the agents it launches (CLAUDE_ENV_FILE is the session's environment file, set for SessionStart hooks).
if [ -n "$main_root" ] && { [ -f "$main_root/.beads/metadata.json" ] || [ -f "$main_root/.beads/config.yaml" ]; }; then
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    printf 'export BEADS_DIR=%q\n' "$main_root/.beads" >> "$CLAUDE_ENV_FILE" 2>/dev/null
  fi
  if [ -n "$top" ] && [ "$main_root" != "$top" ]; then
    echo "📋 execution queue: the main checkout's bd store ($main_root/.beads), shared by every worktree."
  fi
fi
# A session from a git worktree does not see the main checkout's .claude/settings.local.json
# (it is gitignored), so local "always allow" answers stay behind and permission prompts come
# back. The fix is the project's shared, committed .claude/settings.json → permissions.allow
# with the specific commands the project needs — never a blanket "Bash": the sandbox, the
# guard and the deny rules are the fences, a blanket allow only removes the human's last look.
# A quiet hint, once per session, and only when the project lists no allow rules yet.
if [ -n "$main_root" ] && [ -n "$top" ] && [ "$main_root" != "$top" ] \
   && ! grep -q '"allow"' "$root/.claude/settings.json" 2>/dev/null; then
  echo "ℹ️ worktree session ($top): local permission answers from the main checkout do not apply here. If prompts get in the way, ask the owner to list the specific commands the project needs in .claude/settings.json → permissions.allow (shared, committed) — not a blanket \"Bash\"."
fi
exit 0

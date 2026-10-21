#!/usr/bin/env bash
# Self-healing of git hooks at session start.
#
# Why: core.hooksPath is not stored in git. In every NEW worktree it gets overridden
# with an absolute path to the main checkout's .git/hooks, where there are no project hooks —
# and pre-push (devlog gate + test gate) silently does not fire.
#
# Safe by design: always exit 0. Silent when all is well; loud when the gates are missing.
set +e
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$root" ] || exit 0

[ -x "$root/scripts/install-git-hooks.sh" ] && (cd "$root" && ./scripts/install-git-hooks.sh) >/dev/null 2>&1

effective="$(git -C "$root" config --get core.hooksPath 2>/dev/null)"
if [ "$effective" = ".githooks" ]; then
    exit 0   # normal — stay quiet
fi

echo "⚠️ git hooks are NOT active: core.hooksPath='${effective:-empty}' (expected '.githooks')."
echo "   So pre-push will not fire: neither the devlog gate nor the test gate. Auto-repair failed."
echo "   Fix by hand: ./scripts/install-git-hooks.sh — and check that writing to .git/config is allowed."
exit 0

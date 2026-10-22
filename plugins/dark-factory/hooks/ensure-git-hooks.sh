#!/usr/bin/env bash
# Self-healing of git hooks at session start (dark-factory plugin, SessionStart startup|resume).
#
# Why: core.hooksPath is not stored in git. In every NEW worktree it gets overridden
# with an absolute path to the main checkout's .git/hooks, where there are no project hooks —
# and pre-push (the test gate) silently does not fire.
#
# The project is $CLAUDE_PROJECT_DIR (else the git top level of the cwd). No-op when the project
# has no .githooks/ — nothing to activate. Safe by design: always exit 0. Silent when all is
# well; loud when the gates are missing.
set +e
root="${CLAUDE_PROJECT_DIR:-}"
[ -n "$root" ] || root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$root" ] && [ -d "$root/.githooks" ] || exit 0
git -C "$root" rev-parse --git-dir >/dev/null 2>&1 || exit 0

if [ -x "$root/scripts/install-git-hooks.sh" ]; then
    (cd "$root" && ./scripts/install-git-hooks.sh) >/dev/null 2>&1
elif [ "$(git -C "$root" config --get core.hooksPath 2>/dev/null)" != ".githooks" ]; then
    git -C "$root" config --local core.hooksPath .githooks >/dev/null 2>&1
fi

effective="$(git -C "$root" config --get core.hooksPath 2>/dev/null)"
if [ "$effective" = ".githooks" ]; then
    exit 0   # normal — stay quiet
fi

echo "⚠️ git hooks are NOT active: core.hooksPath='${effective:-empty}' (expected '.githooks')."
echo "   So pre-push will not fire: the project's push gates are off. Auto-repair failed."
echo "   Fix by hand: git config --local core.hooksPath .githooks (or ./scripts/install-git-hooks.sh) — and check that writing to .git/config is allowed."
exit 0

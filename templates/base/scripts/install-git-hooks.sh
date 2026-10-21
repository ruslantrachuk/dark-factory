#!/usr/bin/env bash
# Configure git to read hooks from .githooks/ (core.hooksPath).
# Idempotent: re-running is safe. Run once after clone.
#
# Advantage over cp: hooks update themselves together with the repo (git pull),
# no reinstall needed after every change to .githooks/*.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR=".githooks"

if [ ! -d "${REPO_ROOT}/${HOOKS_DIR}" ]; then
    echo "❌ ${REPO_ROOT}/${HOOKS_DIR} not found. Run from the project root."
    exit 1
fi

# Conflict diagnostics: beads (bd 1.1.0+) may reset core.hooksPath to its own path
# on init/doctor (e.g. .beads/hooks) and thereby silently disable the project hooks
# (pre-push devlog guard + post-merge auto bd import). Warn explicitly when overriding.
current="$(git config --get core.hooksPath || true)"
if [ -n "${current}" ] && [ "${current}" != "${HOOKS_DIR}" ]; then
    echo "⚠️  core.hooksPath was '${current}' → overriding to '${HOOKS_DIR}'."
    case "${current}" in
        *.beads/hooks*) echo "    (this was set by beads; project hooks require .githooks — restoring)";;
    esac
fi

# --local explicitly: on clones with extensions.worktreeConfig an unscoped set writes to
# config.worktree, which the script below then removes itself — hooksPath ended up empty.
git config --local core.hooksPath "${HOOKS_DIR}"

# Worktree-level override. Tools that create worktrees like to write
# an ABSOLUTE path to the main checkout's .githooks into its config.worktree — so the hooks
# "definitely work". The side effect is worse than the benefit: the worktree then runs hooks
# from the main branch, and hook edits in its own branch have no effect at all.
# Observed in practice: a test gate in a worktree ran the test suite from the main branch
# and let the push through while reporting success. We remove the override — the relative path from
# .git/config resolves relative to the root of each worktree, as it should.
# Without extensions.worktreeConfig git treats --worktree as --local — the unset below
# would remove the hooksPath just set.
if [ "$(git config --get extensions.worktreeConfig || true)" = "true" ] \
   && git config --worktree --get core.hooksPath >/dev/null 2>&1; then
    wt_path="$(git config --worktree --get core.hooksPath)"
    if [ "${wt_path}" != "${HOOKS_DIR}" ]; then
        echo "⚠️  the worktree overrode hooksPath to '${wt_path}' → removing the override."
        echo "    (otherwise this worktree would run the main checkout's hooks, not its own branch's)"
    fi
    git config --worktree --unset-all core.hooksPath || true
fi

effective="$(git config --get core.hooksPath)"
echo "✓ git core.hooksPath = ${effective}"
case "${effective}" in
    /*) echo "⚠️  the path is absolute — in a worktree hooks will be taken from another checkout. Expected '${HOOKS_DIR}'.";;
esac
echo "   Active hooks: $(cd "${REPO_ROOT}/${HOOKS_DIR}" && ls | grep -vE '^_' | tr '\n' ' ')"
echo "   Hooks are read straight from the repo — they update themselves on git pull."
echo "   If beads hijacks hooksPath again (after bd init/doctor) — re-run this script."
echo "   After creating a new worktree — re-run it too: the override gets set again."

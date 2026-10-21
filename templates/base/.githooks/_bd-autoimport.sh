#!/usr/bin/env bash
# Helper: if .beads/issues.jsonl changed between two refs — pull the tasks into the
# local Dolt store via `bd import` (beads sync is git JSONL, NOT bd dolt push; see .beads/README.md).
#
# Removes the manual step "after git pull → bd import".
# Called from the post-merge / post-checkout hooks.
#
# NON-fatal: any failure (bd not in PATH, store busy) must not break pull/checkout — only warn.
#
# Arguments: $1 = old ref, $2 = new ref.

set -uo pipefail

old_ref="${1:-}"
new_ref="${2:-}"
[ -z "${old_ref}" ] && exit 0
[ -z "${new_ref}" ] && exit 0

# Was issues.jsonl touched in the range?
if ! git diff --name-only "${old_ref}" "${new_ref}" 2>/dev/null | grep -q -E '^\.beads/issues\.jsonl$'; then
    exit 0
fi

# Is bd available?
if ! command -v bd >/dev/null 2>&1; then
    echo "ℹ️  post-hook: .beads/issues.jsonl changed, but bd is not in PATH — import by hand: bd import" >&2
    exit 0
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
if bd import >/dev/null 2>&1 || bd import "${repo_root}/.beads/issues.jsonl" >/dev/null 2>&1; then
    echo "✓ post-hook: .beads/issues.jsonl changed → bd import done (tasks synchronized)" >&2
else
    echo "⚠️  post-hook: .beads/issues.jsonl changed, but bd import failed — import by hand: bd import" >&2
fi

exit 0

#!/usr/bin/env bash
# Beads queue guard: tasks must not disappear from .beads/issues.jsonl.
#
# Why: every git worktree has its own embedded Dolt beads store with the same project_id.
# `bd export` writes the file from ITS OWN store, so a commit from a working tree silently
# cuts out everything that store does not have. This way a couple of dozen tasks, some of
# them open, can reach main unnoticed until a reconciliation happens to catch it.
#
# The guard does not cure the cause — it closes the exit: it compares the ids in the HEAD
# version with what goes into the commit and restores the missing records from HEAD.
# Called from .githooks/pre-commit; by hand — for diagnostics.
#
# Modes:
#   scripts/bd-queue-guard.sh --check     print missing ids (exit 1 if any)
#   scripts/bd-queue-guard.sh --restore   restore missing records from HEAD and sort
#
# Deliberately removing tasks from the queue (cleanup, merging stores) is not the guard's job:
#   BD_QUEUE_ALLOW_DROP=1 git commit …

set -euo pipefail

QUEUE='.beads/issues.jsonl'
mode="${1:---check}"

case "${mode}" in
  --check|--restore) ;;
  *) echo "✗ unknown mode: ${mode} (--check | --restore)" >&2; exit 2 ;;
esac

cd "$(git rev-parse --show-toplevel)"

command -v jq >/dev/null 2>&1 || {
  echo "✗ jq is required — the queue cannot be parsed without it." >&2
  echo "  macOS: brew install jq · Debian/Ubuntu: apt install jq" >&2
  exit 2
}

# The queue is not in history yet (first commit of the file) — nothing to compare with
git cat-file -e "HEAD:${QUEUE}" 2>/dev/null || exit 0
[ -f "${QUEUE}" ] || exit 0

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

git show "HEAD:${QUEUE}" > "${tmp}/head.jsonl"

# Memory records (_type: memory) have no id — they are not compared
ids() { jq -r '.id // empty' "$1" | sort -u; }

ids "${tmp}/head.jsonl" > "${tmp}/head.ids"
ids "${QUEUE}"          > "${tmp}/now.ids"
comm -23 "${tmp}/head.ids" "${tmp}/now.ids" > "${tmp}/missing.ids"

count="$(wc -l < "${tmp}/missing.ids" | tr -d ' ')"
[ "${count}" -eq 0 ] && exit 0

if [ "${mode}" = "--check" ]; then
  echo "✗ tasks disappeared from ${QUEUE} (${count}):" >&2
  jq -r --rawfile miss "${tmp}/missing.ids" '
    ($miss | split("\n") | map(select(length > 0))) as $m
    | select((.id // "") as $i | $m | index($i))
    | "   \(.id) [\(.status // "?")] \(.title // "")"' "${tmp}/head.jsonl" >&2
  exit 1
fi

# --restore: append the missing records from HEAD and restore the stable order
jq -c --rawfile miss "${tmp}/missing.ids" '
  ($miss | split("\n") | map(select(length > 0))) as $m
  | select((.id // "") as $i | $m | index($i))' "${tmp}/head.jsonl" >> "${QUEUE}"

scripts/bd-export.sh --normalize >/dev/null

echo "✓ restored tasks from HEAD into ${QUEUE} (${count}): $(tr '\n' ' ' < "${tmp}/missing.ids")"

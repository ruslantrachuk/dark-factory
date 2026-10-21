#!/usr/bin/env bash
# Beads queue with one replaced line — for closing a task in merge-feature.sh.
#
# Why separate from the full export: `bd export` on machines with different bd versions
# diverges from the committed file in almost every line — an old bd does not write
# `_type`, `bd import` rewrites edge authors and comment ids, the local database
# holds stale defer dates. Two consecutive exports can rewrite nearly every line,
# forcing the queue to be rolled back by hand.
# So merge-feature.sh takes ONE line from the export — the closed task —
# and this script assembles the file from the committed queue.
#
# Usage: scripts/beads-queue-line.sh <queue.jsonl> <task-line.jsonl>
#   Prints to stdout the queue in which the task line with the same id is replaced;
#   if there is no such line — it is inserted in id order (the queue file is sorted,
#   scripts/bd-export.sh). A task already closed in the queue is not touched: its line
#   may have been written by another machine, in its own form — the output equals the input.
#   Input and output being identical (`cmp`) is the answer "nothing to change".
#
# Other lines pass byte for byte: jq only reads ids, the file itself is cut with head/tail.
# Rebuilding through jq changes escaping (`<` → `<`), and its raw string mode
# (-R) corrupts multi-byte (non-ASCII) characters at read buffer boundaries — a trial run
# on a live queue corrupted dozens of other tasks' lines.

set -euo pipefail

queue="${1:?Usage: beads-queue-line.sh <queue.jsonl> <task-line.jsonl>}"
task="${2:?Usage: beads-queue-line.sh <queue.jsonl> <task-line.jsonl>}"

command -v jq >/dev/null 2>&1 || {
  echo "✗ jq is required — without it the task line cannot be found in the queue." >&2
  echo "  macOS: brew install jq · Debian/Ubuntu: apt install jq" >&2
  exit 2
}

[ "$(wc -l < "${task}" | tr -d ' ')" = "1" ] \
  || { echo "✗ ${task}: exactly one task line expected" >&2; exit 1; }
id="$(jq -r '.id // ""' "${task}")" || { echo "✗ ${task}: not JSON" >&2; exit 1; }
[ -n "${id}" ] || { echo "✗ ${task}: task line without an id" >&2; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/beads-queue-line.XXXXXX")"
trap 'rm -rf "${tmp}"' EXIT

jq -r '.id // ""' "${queue}" > "${tmp}/ids.txt" \
  || { echo "✗ ${queue}: not JSONL (traces of a merge conflict?)" >&2; exit 1; }
# The line number is taken from the id list — it must match the file line by line
# (an empty line or a file without a trailing newline would shift the replacement).
[ "$(wc -l < "${tmp}/ids.txt")" -eq "$(wc -l < "${queue}")" ] \
  || { echo "✗ ${queue}: line count does not match record count — not replacing" >&2; exit 1; }

at="$(grep -nxF -- "${id}" "${tmp}/ids.txt" | head -n 1 | cut -d: -f1 || true)"
if [ -n "${at}" ]; then
  if [ "$(head -n "${at}" "${queue}" | tail -n 1 | jq -r '.status // ""')" = "closed" ]; then
    cat "${queue}"
    exit 0
  fi
  before=$(( at - 1 ))
else
  # Byte-wise order, same as `jq sort_by(.id)` in bd-export.sh.
  before="$(LC_ALL=C awk -v id="${id}" '($0 "") < (id "") { n++ } END { print n + 0 }' "${tmp}/ids.txt")"
  at="${before}"
fi

[ "${before}" -eq 0 ] || head -n "${before}" "${queue}"
cat "${task}"
tail -n "+$(( at + 1 ))" "${queue}"

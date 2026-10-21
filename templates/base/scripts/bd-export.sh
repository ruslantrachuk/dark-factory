#!/usr/bin/env bash
# Beads queue normalization: .beads/issues.jsonl in a stable order (sorted by id).
#
# Why sort: `bd export` writes lines in an unstable order → every export
# reshuffles the file and breeds FALSE git conflicts. With sorting, edits to different
# tasks land on non-overlapping lines and git auto-merges; a conflict remains only
# when the SAME task is edited (legitimate).
#
# Why a single manual run is not enough: bd rewrites
# .beads/issues.jsonl in ITS OWN order after any mutating command (verified:
# `bd update` — and the file is no longer sorted). "Run the script sometime before the commit"
# does not work: any `bd close` can slip in between the run and `git add`.
# The order is kept by the .githooks/pre-commit hook — it calls this script in --normalize mode
# on everything going into the commit. The manual run remains for "rebuild the file from the store"
# after a conflict.
#
# Modes:
#   scripts/bd-export.sh              rebuild the file from the bd store and sort it
#   scripts/bd-export.sh --normalize  only sort what is already in the file (bd is not called)
#   scripts/bd-export.sh --check      check the order, write nothing (exit 1 if broken)
#
# Resolve a conflict in .beads/issues.jsonl NOT by hand line by line, but by rebuilding from the store —
# see .beads/README.md (bd import of both versions → this script with no arguments).

set -euo pipefail

QUEUE='.beads/issues.jsonl'
mode="${1:-export}"

case "${mode}" in
  export|--normalize|--check) ;;
  *) echo "✗ unknown mode: ${mode} (export | --normalize | --check)" >&2; exit 2 ;;
esac

# The script is called from hooks, from merge-feature.sh, and by hand from a subdirectory —
# the paths below are relative, so always work from the repository root.
cd "$(git rev-parse --show-toplevel)"

command -v jq >/dev/null 2>&1 || {
  echo "✗ jq is required — without it the line order cannot be made stable." >&2
  echo "  macOS: brew install jq · Debian/Ubuntu: apt install jq" >&2
  exit 2
}

# --- order check: read-only, bd is not touched (hooks must be fast) ---
if [ "${mode}" = "--check" ]; then
  [ -s "${QUEUE}" ] || { echo "✗ ${QUEUE} is empty or missing"; exit 1; }
  if ! jq -e -s 'map(.id) | . == sort' "${QUEUE}" >/dev/null 2>&1; then
    echo "✗ ${QUEUE} is not sorted by id — there will be false conflicts on merge." >&2
    echo "  Fix: scripts/bd-export.sh --normalize" >&2
    exit 1
  fi
  echo "✓ ${QUEUE} is in a stable order ($(wc -l < "${QUEUE}" | tr -d ' ') tasks)"
  exit 0
fi

# --- build: first into a temp file, only a verified result goes into the queue ---
# A direct redirect into ${QUEUE} would truncate it BEFORE bd runs: a failed export left
# an empty queue, and that already happened silently under `|| true` in merge-feature.sh.
tmp="$(mktemp "${TMPDIR:-/tmp}/bd-export.XXXXXX")"
trap 'rm -f "${tmp}" "${tmp}.raw"' EXIT

if [ "${mode}" = "--normalize" ]; then
  [ -s "${QUEUE}" ] || { echo "✗ ${QUEUE} is empty or missing — nothing to normalize"; exit 1; }
  source_desc="file"
  cp "${QUEUE}" "${tmp}.raw"
else
  source_desc="bd store"
  bd export > "${tmp}.raw" || { echo "✗ bd export failed — queue left untouched" >&2; exit 1; }
fi

# Broken JSONL (including a file with conflict markers) does not get into the queue
if ! jq -e -s 'all(.id != null and .id != "")' "${tmp}.raw" >/dev/null 2>&1; then
  echo "✗ ${source_desc} produced non-JSONL or lines without an id — queue left untouched." >&2
  echo "  If these are traces of a merge conflict: resolve by rebuilding from the store, not line by line" >&2
  echo "  (.beads/README.md)." >&2
  exit 1
fi

jq -s -c 'sort_by(.id)[]' "${tmp}.raw" > "${tmp}"

before="$( [ -f "${QUEUE}" ] && wc -l < "${QUEUE}" | tr -d ' ' || echo 0 )"
after="$(wc -l < "${tmp}" | tr -d ' ')"

# Protection against queue corruption: bd export from an empty/uninitialized store yields
# 0 lines with exit 0 — it would silently wipe the whole issues.jsonl. An empty export is accepted
# only over an empty queue (fresh project).
if [ "${after}" -eq 0 ] && [ "${before}" -gt 0 ]; then
  echo "✗ ${source_desc} produced 0 tasks, but ${QUEUE} contains ${before} — store empty/not initialized?" >&2
  echo "  Queue left untouched. First: bd import (or bd init per .beads/README.md), then retry." >&2
  exit 1
fi

# A sharp shrink of the queue is almost always a foreign/empty store, not deleted tasks.
# It must not be wiped silently: it would have to be restored from git.
if [ "${mode}" = "export" ] && [ "${before}" -gt 0 ] && [ "${after}" -lt $(( before / 2 )) ]; then
  echo "✗ the store returned ${after} tasks versus ${before} in the file — looks like a foreign or empty store." >&2
  echo "  Queue left untouched. First: git checkout ${QUEUE} && bd import ${QUEUE}" >&2
  exit 1
fi

mv "${tmp}" "${QUEUE}"
echo "✓ ${QUEUE}: ${after} tasks from \"${source_desc}\", sorted by id"

#!/usr/bin/env bash
# Keep the dark-factory plugin's solo kit in step with the canon.
# The canonical merge script is templates/base/scripts/merge-feature.sh; the kit carries a copy
# (plugins/dark-factory/kit/scripts/merge-feature.sh) because an installed plugin cannot reach
# templates/. Edit the canonical file, then run this script.
#
# Usage: scripts/sync-plugin-kit.sh            copy the canonical files into the kit
#        scripts/sync-plugin-kit.sh --check    exit 1 if the kit differs (run by scripts/test_repo.py)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="${ROOT}/plugins/dark-factory/kit"
# canonical source → kit copy
PAIRS=(
  "templates/base/scripts/merge-feature.sh:scripts/merge-feature.sh"
)

mode="${1:-}"
case "${mode}" in ""|--check) ;; *) echo "✗ unknown option: ${mode} (only --check)" >&2; exit 2 ;; esac

differs=0
for pair in "${PAIRS[@]}"; do
  src="${ROOT}/${pair%%:*}"
  dst="${KIT}/${pair#*:}"
  if [ -f "${dst}" ] && cmp -s "${src}" "${dst}"; then
    continue
  fi
  if [ "${mode}" = "--check" ]; then
    echo "✗ kit/${pair#*:} differs from ${pair%%:*} — run scripts/sync-plugin-kit.sh" >&2
    differs=1
  else
    mkdir -p "$(dirname "${dst}")"
    cp "${src}" "${dst}"
    chmod +x "${dst}"
    echo "synced kit/${pair#*:} ← ${pair%%:*}"
  fi
done
[ "${mode}" = "--check" ] && [ "${differs}" = 0 ] && echo "✓ plugin kit in sync with the canon"
exit "${differs}"

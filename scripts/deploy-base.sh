#!/usr/bin/env bash
# Deterministic part of deploying the base template: copying.
# Usage: scripts/deploy-base.sh <target-dir> [--dry-run]
#
# - Copies templates/base/ into the target, does NOT overwrite EXISTING files
#   (the "harness on top of existing code" scenario), skips are reported.
# - --dry-run: show what will be copied/skipped, write nothing.
# - Prints the template SHA (last commit of templates/) — for the row in your
#   factory's registry (see registry.example.md).
# - Prints the remaining <…> placeholders in the target (a hint list, not a gate).
# Questions, filling placeholders, the registry log — the deploy-project skill.

set -euo pipefail

FACTORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${FACTORY_ROOT}/templates/base"

target="${1:?Usage: deploy-base.sh <target-dir> [--dry-run]}"
mode="${2:-}"
case "${mode}" in ""|--dry-run) ;; *) echo "✗ unknown option: ${mode} (only --dry-run)"; exit 2 ;; esac

[ -d "${SRC}" ] || { echo "✗ ${SRC} not found"; exit 1; }

sha="$(git -C "${FACTORY_ROOT}" log -1 --format='%h (%ad)' --date=short -- templates/ 2>/dev/null || echo '?')"
full_sha="$(git -C "${FACTORY_ROOT}" log -1 --format='%H' -- templates/ 2>/dev/null || true)"
echo "Template: templates/base @ ${sha}"
echo "Target:   ${target}"
echo

copied=0; skipped=0
while IFS= read -r rel; do
  src_f="${SRC}/${rel}"
  dst_f="${target}/${rel}"
  if [ -e "${dst_f}" ]; then
    echo "  SKIP (exists): ${rel}"
    skipped=$((skipped+1))
  else
    echo "  COPY: ${rel}"
    if [ "${mode}" != "--dry-run" ]; then
      mkdir -p "$(dirname "${dst_f}")"
      cp "${src_f}" "${dst_f}"
    fi
    copied=$((copied+1))
  fi
done < <(cd "${SRC}" && find . -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -not -name '.DS_Store' | sed 's|^\./||' | sort)

echo
echo "Total: copied ${copied}, skipped ${skipped}$( [ "${mode}" = "--dry-run" ] && echo ' (dry-run, nothing written)' )"

if [ "${mode}" != "--dry-run" ]; then
  # make scripts and hooks executable
  find "${target}/scripts" "${target}/.githooks" "${target}/.claude/hooks" -type f 2>/dev/null | xargs chmod +x 2>/dev/null || true
  # the common base for harness-diff.sh and env-context.sh (MANIFEST step 5)
  if [ -n "${full_sha}" ] && [ ! -e "${target}/.harness/base-sha" ]; then
    mkdir -p "${target}/.harness"
    echo "${full_sha}" > "${target}/.harness/base-sha"
    echo "  wrote .harness/base-sha = ${full_sha}"
  fi
  echo
  echo "Remaining placeholders (fill in, see MANIFEST.md):"
  # English placeholders like <project>, <owner>, <abs path …>; '<<' heredocs are
  # excluded by requiring a letter right after '<'. HTML tags may also match —
  # this is a hint list, not a gate.
  grep -rln '<[A-Za-z]' "${target}" --include='*.md' --include='*.sh' --include='*.json' --include='*.yml' 2>/dev/null \
    | sed "s|^${target}/|  |" || echo "  (none)"
  echo
  echo "Next (deploy-project skill): fill placeholders → install-git-hooks.sh → bd init+import → smoke per MANIFEST → a row in your factory's registry.md with SHA ${sha}"
fi

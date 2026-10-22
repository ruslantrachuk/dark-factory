#!/usr/bin/env bash
# Deterministic part of /dark-factory:add <module>: copy a module's files into the project.
# Usage: add-module.sh <module> [--project DIR] [--dry-run]
#   module: on-call (feedback-desk) | monitor (prod-monitor) | release (release-tag) | observability | code-audit
#           | feature-pipeline  (a module's directory name works too). `base` is deploy-base.sh.
#
# - Copies ${PLUGIN_ROOT}/templates/<module>/ into the project (default: the git top level of the cwd), does NOT
#   overwrite existing files, reports every skip. The module's MANIFEST.md stays in the plugin.
# - --dry-run: show what would be copied or skipped, write nothing.
# - Prints the remaining <…> placeholders of the files it copied (a hint list, not a gate).
# Questions, filling the placeholders, the tests, the server units — the /dark-factory:add skill and the
# module's MANIFEST.md ("Setup by /dark-factory:add <module>").

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage="Usage: add-module.sh <on-call|monitor|release|observability|code-audit|feature-pipeline> [--project DIR] [--dry-run]"

module="${1:?${usage}}"
shift
project=""; dry=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1 ;;
    --project) [ -n "${2:-}" ] || { echo "✗ --project needs a directory" >&2; exit 2; }; project="$2"; shift ;;
    *) echo "✗ unknown option: $1" >&2; echo "${usage}" >&2; exit 2 ;;
  esac
  shift
done

case "${module}" in
  on-call|feedback-desk) dir="feedback-desk" ;;
  monitor|prod-monitor) dir="prod-monitor" ;;
  release|release-tag) dir="release-tag" ;;
  observability|code-audit|feature-pipeline) dir="${module}" ;;
  base) echo "✗ base is installed by deploy-base.sh (/dark-factory:add base)" >&2; exit 2 ;;
  *) echo "✗ unknown module: ${module}" >&2; echo "${usage}" >&2; exit 2 ;;
esac

SRC="${PLUGIN_ROOT}/templates/${dir}"
[ -d "${SRC}" ] || { echo "✗ ${SRC} not found" >&2; exit 1; }
if [ -z "${project}" ]; then
  project="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
[ -d "${project}" ] || { echo "✗ ${project} is not a directory" >&2; exit 2; }
project="$(cd "${project}" && pwd)"

echo "Module:  ${module} (templates/${dir})"
echo "Project: ${project}"
echo

copied=0; skipped=0; copied_files=()
while IFS= read -r rel; do
  src_f="${SRC}/${rel}"
  dst_f="${project}/${rel}"
  if [ -e "${dst_f}" ]; then
    echo "  SKIP (exists): ${rel}"
    skipped=$((skipped+1))
    continue
  fi
  echo "  COPY: ${rel}"
  if [ -z "${dry}" ]; then
    mkdir -p "$(dirname "${dst_f}")"
    cp -p "${src_f}" "${dst_f}"
    case "${rel}" in *.sh) chmod +x "${dst_f}" ;; esac
    copied_files+=("${dst_f}")
  fi
  copied=$((copied+1))
done < <(cd "${SRC}" && find . -type f -not -name MANIFEST.md -not -path '*/__pycache__/*' -not -path '*/node_modules/*' \
  -not -path '*/.pytest_cache/*' -not -name '*.pyc' -not -name '.DS_Store' | sed 's|^\./||' | sort)

echo
echo "Total: copied ${copied}, skipped ${skipped}$( [ -n "${dry}" ] && echo ' (dry-run, nothing written)' )"

if [ -z "${dry}" ] && [ "${#copied_files[@]}" -gt 0 ]; then
  echo
  echo "Remaining placeholders in the copied files (fill in, see the module's MANIFEST.md):"
  # a letter right after '<' keeps '<<' heredocs out; HTML tags and TypeScript generics may match too — a hint list
  found="$(grep -ln '<[A-Za-z][^>]*>' "${copied_files[@]}" 2>/dev/null | grep -E '\.(md|sh|env|json|yml|yaml|py)$' \
    | sed "s|^${project}/|  |" || true)"
  printf '%s\n' "${found:-  (none)}"
fi

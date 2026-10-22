#!/usr/bin/env bash
# Deterministic part of deploying the base template: copying.
# Usage: ${CLAUDE_PLUGIN_ROOT}/scripts/deploy-base.sh <target-dir> [--dry-run] [--fence-level solo|standard|team] [--fail-closed 0|1]
#
# - Copies templates/base/ into the target, does NOT overwrite EXISTING files
#   (the "harness on top of existing code" scenario), skips are reported. An existing
#   .gitignore is kept too; the base lines it lacks are printed to merge by hand.
# - --dry-run: show what will be copied/skipped, write nothing.
# - --fence-level / --fail-closed: FENCE_LEVEL and QUOTA_FAIL_CLOSED in the copied .claude/fences.env (the level the
#   /dark-factory:add base starts at). Only a file this run copies is set; an existing one is left alone (change it
#   with /dark-factory:level in the project).
# - Prints the template ref — for
#   .harness/base-sha: the plugin's release tag (v<N>) for an installed plugin, the last commit of
#   templates/ when the plugin is run from a git checkout of the canon.
# - Prints the remaining <…> placeholders in the target (a hint list, not a gate).
# Questions, filling placeholders, the registry log — /dark-factory:add base (skills/add/base.md).
# The always-on hooks (fence guard, quota guard, git-hook repair) are not copied: they come from
# the dark-factory plugin, which the template's .claude/settings.json enables. The template is the plugin's
# own templates/base/: nothing else is needed on the machine.

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${PLUGIN_ROOT}/templates/base"

usage="Usage: deploy-base.sh <target-dir> [--dry-run] [--fence-level solo|standard|team] [--fail-closed 0|1]"
[ $# -ge 1 ] || { echo "${usage}" >&2; exit 2; }
target="$1"
shift
mode=""; fence_level=""; fail_closed=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) mode="--dry-run" ;;
    --fence-level|--fail-closed)
      [ $# -ge 2 ] || { echo "✗ $1 needs a value"; echo "${usage}"; exit 2; }
      if [ "$1" = "--fence-level" ]; then fence_level="$2"; else fail_closed="$2"; fi
      shift ;;
    *) echo "✗ unknown option: $1"; echo "${usage}"; exit 2 ;;
  esac
  shift
done
case "${fence_level}" in ""|solo|standard|team) ;; *) echo "✗ --fence-level: solo, standard or team"; exit 2 ;; esac
case "${fail_closed}" in ""|0|1) ;; *) echo "✗ --fail-closed: 0 or 1"; exit 2 ;; esac

[ -d "${SRC}" ] || { echo "✗ ${SRC} not found"; exit 1; }

# The template's address: a commit when the plugin is a git checkout, else the release tag of the installed plugin.
full_sha="$(git -C "${PLUGIN_ROOT}" log -1 --format='%H' -- templates/ 2>/dev/null || true)"
if [ -n "${full_sha}" ]; then
  sha="$(git -C "${PLUGIN_ROOT}" log -1 --format='%h (%ad)' --date=short -- templates/)"
else
  version="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "${PLUGIN_ROOT}/.claude-plugin/plugin.json" 2>/dev/null | head -n 1)"
  full_sha="${version:+v${version%%.*}}"
  sha="${full_sha:-?}"
fi
echo "Template: dark-factory plugin templates/base @ ${sha}"
echo "Target:   ${target}"
echo "Requires: the dark-factory plugin (/plugin marketplace add ruslantrachuk/dark-factory; /plugin install dark-factory@dark-factory)"
echo

copied=0; skipped=0; fences_copied=0; copied_rels=()
while IFS= read -r rel; do
  src_f="${SRC}/${rel}"
  dst_f="${target}/${rel}"
  if [ -e "${dst_f}" ] && [[ "${rel}" == .claude/canon/* ]]; then
    # The canon part of CLAUDE.md is replaced whole from the template, never merged.
    if cmp -s "${src_f}" "${dst_f}"; then
      echo "  SAME (canon): ${rel}"
    else
      echo "  REPLACE (canon, whole): ${rel}"
      [ "${mode}" = "--dry-run" ] || cp "${src_f}" "${dst_f}"
    fi
    skipped=$((skipped+1))
  elif [ -e "${dst_f}" ]; then
    echo "  SKIP (exists): ${rel}"
    skipped=$((skipped+1))
    # The project's own .gitignore stays; name the base lines it lacks, to merge by hand.
    if [ "${rel}" = ".gitignore" ]; then
      missing="$(grep -vE '^[[:space:]]*(#|$)' "${src_f}" | grep -vxF -f "${dst_f}" || true)"
      if [ -n "${missing}" ]; then
        echo "    hint: the project's .gitignore lacks these base lines — merge them by hand:"
        printf '%s\n' "${missing}" | sed 's/^/      /'
      fi
    fi
    # The project's own settings.json stays; name the fence blocks it then lacks (/dark-factory:add base merges them).
    if [ "${rel}" = ".claude/settings.json" ]; then
      lacks=""
      grep -q '"sandbox"' "${dst_f}" || lacks="${lacks}sandbox, "
      grep -q '"deny"' "${dst_f}" || lacks="${lacks}permissions.deny, "
      grep -q '"ask"' "${dst_f}" || lacks="${lacks}permissions.ask, "
      grep -q 'SessionStart' "${dst_f}" || lacks="${lacks}SessionStart hooks, "
      if [ -n "${lacks}" ]; then
        echo "    hint: the project's settings.json lacks these fence blocks: ${lacks%, } — /dark-factory:add base (skills/add/base.md) merges them with the human"
      else
        echo "    hint: the project's settings.json has the fence block keys; check their entries against the template's"
      fi
    fi
    if [ "${rel}" = ".github/workflows/ci.yml" ]; then
      echo "    hint: the base tiered CI (quick/full/browser, secret scan) is not installed — merge it by hand; merge-feature.sh waits on a green quick tier"
    fi
  else
    echo "  COPY: ${rel}"
    [ "${rel}" = ".claude/fences.env" ] && fences_copied=1
    if [ "${mode}" != "--dry-run" ]; then
      mkdir -p "$(dirname "${dst_f}")"
      cp "${src_f}" "${dst_f}"
    fi
    copied=$((copied+1))
    copied_rels+=("${rel}")
  fi
  # A project's own CLAUDE.md stays; without the import the canon part is installed but never loaded.
  if [ "${rel}" = "CLAUDE.md" ] && [ -e "${dst_f}" ] && ! grep -qF '@.claude/canon/CLAUDE.md' "${dst_f}"; then
    echo "    hint: the project's CLAUDE.md does not import the canon part — add the line @.claude/canon/CLAUDE.md"
  fi
done < <(cd "${SRC}" && find . -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -not -name '.DS_Store' | sed 's|^\./||' | sort)

echo
echo "Total: copied ${copied}, skipped ${skipped}$( [ "${mode}" = "--dry-run" ] && echo ' (dry-run, nothing written)' )"

if [ -n "${fence_level}${fail_closed}" ]; then
  want="${fence_level:+FENCE_LEVEL=${fence_level}}${fence_level:+${fail_closed:+, }}${fail_closed:+QUOTA_FAIL_CLOSED=${fail_closed}}"
  if [ "${fences_copied}" = 0 ]; then
    echo "  FENCES: .claude/fences.env exists and is left as it is; wanted ${want} (run /dark-factory:level in the project)"
  elif [ "${mode}" = "--dry-run" ]; then
    echo "  FENCES: would set ${want} in .claude/fences.env"
  else
    fences="${target}/.claude/fences.env"
    [ -z "${fence_level}" ] || sed -i.bak -E "s/^FENCE_LEVEL=.*/FENCE_LEVEL=${fence_level}/" "${fences}"
    [ -z "${fail_closed}" ] || sed -i.bak -E "s/^QUOTA_FAIL_CLOSED=.*/QUOTA_FAIL_CLOSED=${fail_closed}/" "${fences}"
    rm -f "${fences}.bak"
    echo "  FENCES: set ${want} in .claude/fences.env"
  fi
fi

if [ "${mode}" != "--dry-run" ]; then
  # make the scripts and hooks this run copied executable (the project's own files are left as they are)
  for rel in ${copied_rels[@]+"${copied_rels[@]}"}; do
    case "${rel}" in
      .githooks/*|.claude/hooks/*|*.sh) chmod +x "${target}/${rel}" ;;
      scripts/*.py) [ "$(head -c 2 "${target}/${rel}")" = "#!" ] && chmod +x "${target}/${rel}" || true ;;
    esac
  done
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
  grep -rln '<[A-Za-z]' "${target}" --exclude-dir=canon --include='*.md' --include='*.sh' --include='*.json' --include='*.yml' 2>/dev/null \
    | sed "s|^${target}/|  |" || echo "  (none)"
  echo
  echo "Next (/dark-factory:add base): install the dark-factory plugin if missing → fill placeholders → install-git-hooks.sh → bd init (.beads/README.md) → smoke per MANIFEST → a row in your factory's registry.md (project, level, modules, machine); template ref ${sha}"
fi

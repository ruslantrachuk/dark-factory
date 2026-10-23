#!/usr/bin/env bash
# Mechanical reconciliation of the project with the dark factory harness canon (templates/base).
#
# Why: "reconciliation with the canon is a mechanical diff" is written in the canon part of every project's CLAUDE.md,
# but nobody did it by hand — drift accumulated unnoticed, and carrying findings back
# into the canon went from memory. For each canon file the script answers
# WHO moved away from the common base: the project, the canon, or both.
#
# Usage:
#   scripts/harness-diff.sh [--quiet] [path to the canon]
#     the canon is the dark-factory plugin's templates/base: pass the plugin directory, or a clone of the repository
#     (its tags give the common base). Default: $DARK_FACTORY_DIR, otherwise the marketplace clone of the installed
#     plugin (~/.claude/plugins/marketplaces/dark-factory), otherwise ../dark-factory next to the project
#     --quiet            print only non-identical files
#   The common base is the canon ref at deployment (a release tag or a commit): the project's .harness/base-sha
#   (or HARNESS_BASE_SHA=<ref> in the environment — overrides the file). It needs a git clone of the canon;
#   from a plugin directory alone every changed file is just "differs".
#
# Statuses:
#   identical      the project file matches the canon
#   missing        the canon file is absent in the project
#   project moved  the project changed the file relative to base-sha, the canon did not
#                  (for files with placeholders this is the normal state)
#   canon moved    the canon changed the file after base-sha, the project did not: can be taken
#   both diverged  both the project and the canon changed it — merge by hand
#   differs        base-sha unknown (or the file did not exist at it) — just a diff
#
# A report: it tells, it does not apply. A project with .copier-answers.yml updates with `copier update`
# (.harness/README.md, "Updating"); this script then shows what stayed different on purpose.
#
# Read-only: writes nothing to the project or the canon. It is a report — exit 0 for
# any number of differences; non-zero only on a launch error (no canon).

set -uo pipefail

# Files that are project-specific in content: comparing them with the canon is pointless — after
# deployment the project fills them entirely. case patterns (* also matches "/"),
# paths relative to templates/base. The same list is _exclude in the canon's copier.yml.
EXCLUDE=(
  'CLAUDE.md'                 # project sections only; the canon part is .claude/canon/CLAUDE.md, compared as usual
  'MANIFEST.md'
  'naming.yaml'
  'docs/user-guide/*'
  'app/tests/*'
  '*.jinja'                   # Copier's own files (.copier-answers.yml, base-sha), rendered, not copied
)

quiet=""
canon_arg=""
for arg in "$@"; do
  case "${arg}" in
    --quiet) quiet=1 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) canon_arg="${arg}" ;;
  esac
done

root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "✗ run from the project's git repository" >&2; exit 2;
}

config="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"
canon="${canon_arg:-${DARK_FACTORY_DIR:-}}"
if [ -z "${canon}" ]; then
  for cand in "${config}/plugins/marketplaces/dark-factory" "${root}/../dark-factory"; do
    [ -d "${cand}" ] && { canon="${cand}"; break; }
  done
fi
# Where templates/base lives in the canon: inside a repository clone, or at the top of the plugin directory.
tplrel=""
for cand in plugins/dark-factory/templates/base templates/base; do
  [ -d "${canon}/${cand}" ] && { tplrel="${cand}"; break; }
done
if [ -z "${tplrel}" ]; then
  cat >&2 <<EOM
✗ canon not found: ${canon:-(no path)}
  Pass the plugin directory or a clone as an argument, or set DARK_FACTORY_DIR:
    git clone ${DARK_FACTORY_URL:-https://github.com/ruslantrachuk/dark-factory} ../dark-factory
EOM
  exit 2
fi
canon="$(cd "${canon}" && pwd)"
is_git=""
if [ "$(git -C "${canon}" rev-parse --show-toplevel 2>/dev/null)" = "${canon}" ]; then is_git=1; fi

# --- common base ---
base="${HARNESS_BASE_SHA:-}"
base_src="HARNESS_BASE_SHA"
if [ -z "${base}" ] && [ -f "${root}/.harness/base-sha" ]; then
  base="$(head -n 1 "${root}/.harness/base-sha" | tr -d '[:space:]')"
  base_src=".harness/base-sha"
fi
if [ -z "${base}" ]; then
  echo "⚠️  base unknown (no .harness/base-sha and no HARNESS_BASE_SHA) — cannot tell who moved, only \"differs\"."
elif [ -z "${is_git}" ]; then
  echo "⚠️  the canon is not a git clone — cannot read ${base} (${base_src}); reconciling without a base."
  base=""
elif ! base_full="$(git -C "${canon}" rev-parse --verify --quiet "${base}^{commit}")"; then
  echo "⚠️  base ${base} (${base_src}) not found in the canon clone — git -C ${canon} fetch --tags? Reconciling without a base."
  base=""
else
  base="${base_full}"
fi

echo "Project: ${root}"
echo "Canon:   ${canon}${is_git:+ @ $(git -C "${canon}" rev-parse --short HEAD)}"
[ -n "${base}" ] && echo "Base:    $(git -C "${canon}" rev-parse --short "${base}") (${base_src})"
if [ -n "${is_git}" ] && [ -n "$(git -C "${canon}" status --porcelain -- "${tplrel}" 2>/dev/null)" ]; then
  echo "ℹ️  the canon clone has uncommitted changes in ${tplrel} — comparing with the clone's working tree."
fi
echo

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

is_excluded() {
  local pat
  for pat in "${EXCLUDE[@]}"; do
    # shellcheck disable=SC2254  # the pattern is deliberately unquoted — it is a glob
    case "$1" in ${pat}) return 0 ;; esac
  done
  return 1
}

declare -a order=('identical' 'missing' 'project moved' 'canon moved' 'both diverged' 'differs')
declare -a counts=(0 0 0 0 0 0)
bump() {
  local i
  for i in "${!order[@]}"; do
    if [ "${order[$i]}" = "$1" ]; then counts[$i]=$(( counts[$i] + 1 )); fi
  done
}
report() {  # status path [note]
  bump "$1"
  [ -n "${quiet}" ] && [ "$1" = "identical" ] && return 0
  # The status column is aligned with literals: printf and ${#…} in bash 3.2 (macOS) without
  # a UTF-8 locale count bytes, so width specifiers are unreliable for non-ASCII labels.
  local label
  case "$1" in
    'identical')     label='identical    ' ;;
    'missing')       label='missing      ' ;;
    'project moved') label='project moved' ;;
    'canon moved')   label='canon moved  ' ;;
    'both diverged') label='both diverged' ;;
    *)               label='differs      ' ;;
  esac
  printf '%s  %s%s\n' "${label}" "$2" "${3:+  ($3)}"
}

# Canon files: tracked and new non-ignored ones, only those existing on disk;
# Python bytecode (__pycache__) is run debris, not part of the canon
if [ -n "${is_git}" ]; then
  git -C "${canon}" ls-files --cached --others --exclude-standard -- "${tplrel}" | sed "s#^${tplrel}/##"
else
  (cd "${canon}/${tplrel}" && find . -type f | sed 's#^\./##')
fi | grep -v '__pycache__/' | grep -v '\.pyc$' | sort -u > "${tmp}/files"

while IFS= read -r rel; do
  [ -n "${rel}" ] || continue
  [ -f "${canon}/${tplrel}/${rel}" ] || continue
  is_excluded "${rel}" && continue

  canon_file="${canon}/${tplrel}/${rel}"
  proj_file="${root}/${rel}"

  if [ ! -f "${proj_file}" ]; then
    report 'missing' "${rel}"; continue
  fi
  if cmp -s "${canon_file}" "${proj_file}"; then
    report 'identical' "${rel}"; continue
  fi
  if [ -z "${base}" ]; then
    report 'differs' "${rel}"; continue
  fi
  if ! git -C "${canon}" show "${base}:${tplrel}/${rel}" > "${tmp}/base" 2>/dev/null; then
    report 'differs' "${rel}" 'appeared in the canon after base-sha'; continue
  fi

  proj_moved=1; canon_moved=1
  cmp -s "${tmp}/base" "${proj_file}"  && proj_moved=0
  cmp -s "${tmp}/base" "${canon_file}" && canon_moved=0
  if   [ "${proj_moved}" = 1 ] && [ "${canon_moved}" = 0 ]; then report 'project moved' "${rel}"
  elif [ "${proj_moved}" = 0 ] && [ "${canon_moved}" = 1 ]; then report 'canon moved'   "${rel}"
  else                                                          report 'both diverged' "${rel}"
  fi
done < "${tmp}/files"

echo
summary=""
for i in "${!order[@]}"; do
  [ "${counts[$i]}" -gt 0 ] && summary+="${order[$i]}: ${counts[$i]} · "
done
echo "Total: ${summary% · }"
echo "Excluded as project-specific in content: ${EXCLUDE[*]}"

if [ -n "${base}" ]; then
  k="$(git -C "${canon}" log --oneline "${base}..HEAD" -- "${tplrel}" | wc -l | tr -d ' ')"
  echo "The canon moved ahead by ${k} commits in ${tplrel} after base-sha:"
  echo "  git -C ${canon} log --oneline ${base:0:7}..HEAD -- ${tplrel}"
fi
exit 0

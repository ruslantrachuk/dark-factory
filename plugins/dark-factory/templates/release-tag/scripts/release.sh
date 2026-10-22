#!/usr/bin/env bash
# Release to prod only from a tag (factory module release-tag). The hosting
# builds the `release` branch; only a verified release moves it, a merge into
# main does not go to prod.
#
#   scripts/release.sh               put the next tag vYYYY.MM.DD.N on
#                                    origin/main and push it, but only when every
#                                    merge since the last v* tag is accepted (see
#                                    below). Then the
#                                    release.yml workflow runs light + heavy
#                                    tests and does --publish. Run by a release
#                                    manager (the tag ruleset lets only them push
#                                    v* tags), or by the agent at their explicit word.
#   scripts/release.sh --owner-accepts
#                                    the owner, in the interactive session, accepts
#                                    every unaccepted feature listed: each PR gets the
#                                    label `accepted` and the comment "accepted by the
#                                    owner, permission dialog", then the tag is put on.
#   scripts/release.sh --include-unaccepted "<who allowed>"
#                                    ship without the mark: the name goes into the
#                                    annotated tag and the release notes, each such PR
#                                    gets a comment.
#   scripts/release.sh --list-unaccepted
#                                    only print the merges since the last tag that lack
#                                    the mark, one per line: <PR number or ->TAB<title>TAB
#                                    <requester>; changes nothing (the On-call's wrapper
#                                    uses it to check who may allow them).
#   scripts/release.sh --publish T   move `release` to tag T + a commit with
#                                    the VERSION file and create a GitHub
#                                    Release with auto-generated notes. Called by
#                                    release.yml; repeating the same tag is a
#                                    no-op (adds a missing GitHub Release).
#   scripts/release.sh --manual --reason "<why>" --by "<human name>"
#                                    EMERGENCY (Actions are down): tag + --publish
#                                    right away, no tests. VERSION gets a manual mark;
#                                    the reason and the name of the person who decided
#                                    go into the annotated tag and the release notes.
#                                    Refused at FENCE_LEVEL=team (.claude/fences.env):
#                                    there a release goes through the tag ruleset + CI only.
#
# Acceptance: a release takes all of main. The merges since the last v* tag
# (`git log <tag>..origin/main --merges --first-parent`; the first release: since the
# root) are listed, and each PR must carry the label `accepted` (set after the owner
# or the requester said yes on the dev stand). The PR number comes from the merge
# subject "(#N)"; a merge without one is not a PR and needs an override. Without the
# mark the script refuses and prints each unaccepted feature with its title and
# requester (the `## Requested by` section of the PR description), so the caller can
# ask again. --manual and --publish do not check.
#
# Tags are fetched with --force: actions/checkout on a tag creates a local
# lightweight tag, and without --force git refuses to replace it with the
# annotated one.
#
# RELEASE_DATE (YYYY.MM.DD) — date override for tests; defaults to today in RELEASE_TZ.
# RELEASE_GH — the gh command (a stub in tests); Actions need GH_TOKEN; the acceptance check needs gh logged in.
# RELEASE_MAIN_BRANCH, RELEASE_TZ — override the values below (for tests).
set -euo pipefail
# A failure must not be silent: in Actions -q hides the cause.
trap 'echo "release: failure at line ${LINENO}: ${BASH_COMMAND}" >&2' ERR

# Fill in at deployment: timezone of the tag date, main branch.
REMOTE="origin"
MAIN_BRANCH="${RELEASE_MAIN_BRANCH:-<main>}"
RELEASE_BRANCH="release"
RELEASE_TZ="${RELEASE_TZ:-UTC}"
GH="${RELEASE_GH:-gh}"

# KEY from .claude/fences.env (KEY=value lines, # comments) — the fence level chosen at deployment.
fence_value() {
  local env_file
  env_file="$(git rev-parse --show-toplevel)/.claude/fences.env"
  [ -f "${env_file}" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*[\"']\{0,1\}\([^\"'#[:space:]]*\).*/\1/p" "${env_file}" | tail -n 1
}

# One line, no surrounding blanks: the values go into a tag message and release notes.
one_line() { printf '%s' "$1" | tr -s '[:space:]' ' ' | sed 's/^ //; s/ $//'; }

next_tag() {
  local day n
  day="${RELEASE_DATE:-$(TZ="${RELEASE_TZ}" date +%Y.%m.%d)}"
  git fetch -q --tags --force "${REMOTE}"
  n=$(git tag -l "v${day}.*" | sed "s/^v${day}\.//" | sort -n | tail -1)
  echo "v${day}.$(( ${n:-0} + 1 ))"
}

ACCEPT_LABEL="accepted"

# The newest v* tag that main contains; empty before the first release.
last_tag() {
  git tag -l 'v*' --merged "${REMOTE}/${MAIN_BRANCH}" --sort=-v:refname | head -n 1
}

# Prints the unaccepted merges since the last release, one per line:
#   <PR number or "-">TAB<title>TAB<requested by>
# Exit 1 if gh cannot tell (an unverifiable merge is not an accepted one).
unaccepted_merges() {
  local last range sha subject num title info
  last="$(last_tag)"
  range="${last:+${last}..}${REMOTE}/${MAIN_BRANCH}"
  while IFS=$'\t' read -r sha subject; do
    [ -n "${sha}" ] || continue
    num="$(printf '%s' "${subject}" | sed -n 's/.*(#\([0-9][0-9]*\))[[:space:]]*$/\1/p; s/^Merge pull request #\([0-9][0-9]*\) .*/\1/p' | head -n 1)"
    title="$(printf '%s' "${subject}" | sed 's/[[:space:]]*(#[0-9][0-9]*)[[:space:]]*$//')"
    if [ -z "${num}" ]; then
      printf '%s\t%s\t%s\n' "-" "${subject}" "not a pull request (${sha:0:8})"
      continue
    fi
    info="$("${GH}" pr view "${num}" --json labels,body </dev/null)" || {
      echo "release: cannot read PR #${num} through gh - acceptance is unknown, nothing done" >&2
      return 1
    }
    INFO="${info}" NUM="${num}" TITLE="${title}" LABEL="${ACCEPT_LABEL}" python3 - <<'PY'
import json, os, re
d = json.loads(os.environ["INFO"])
if any(l.get("name") == os.environ["LABEL"] for l in d.get("labels") or []):
    raise SystemExit(0)
m = re.search(r"^##[ \t]+Requested by[ \t]*\r?\n(.*?)(?=^##[ \t]|\Z)", d.get("body") or "", re.S | re.M)
who = " ".join((m.group(1) if m else "").split()) or "not stated"
print(f"{os.environ['NUM']}\t{os.environ['TITLE']}\t{who}")
PY
  done < <(git log "${range}" --merges --first-parent --format='%H%x09%s')
}

print_unaccepted() {
  local num title who
  while IFS=$'\t' read -r num title who; do
    if [ "${num}" = "-" ]; then echo "  - ${title}: ${who}"; else echo "  - #${num} ${title} (requested by: ${who})"; fi
  done <<<"$1"
}

# Marks each listed PR; "-" (a merge that is not a PR) has nothing to mark.
mark_accepted() {
  local list="$1" comment="$2" mark="${3:-1}" num title who
  [ "${mark}" = 1 ] && "${GH}" label create "${ACCEPT_LABEL}" --color 0e8a16 --description "accepted on the dev stand" --force </dev/null >/dev/null 2>&1 || true
  while IFS=$'\t' read -r num title who; do
    [ "${num}" != "-" ] || continue
    [ "${mark}" = 1 ] && "${GH}" pr edit "${num}" --add-label "${ACCEPT_LABEL}" </dev/null >/dev/null
    "${GH}" pr comment "${num}" --body "${comment}" </dev/null >/dev/null
  done <<<"${list}"
}

# Acceptance gate of the normal release. $1 = owner|include|"" , $2 = who allowed.
# Prints the tag note (may be empty) on stdout; messages go to stderr.
acceptance_gate() {
  local mode="$1" who="$2" list
  git fetch -q --tags --force "${REMOTE}"
  git fetch -q "${REMOTE}" "${MAIN_BRANCH}"
  list="$(unaccepted_merges)" || exit 1
  [ -n "${list}" ] || return 0
  case "${mode}" in
    owner)
      echo "release: the owner accepts these features:" >&2
      print_unaccepted "${list}" >&2
      mark_accepted "${list}" "accepted by the owner, permission dialog" 1
      ;;
    include)
      echo "release: shipping WITHOUT acceptance, allowed by ${who}:" >&2
      print_unaccepted "${list}" >&2
      mark_accepted "${list}" "shipped without acceptance, allowed by ${who}" 0
      printf 'Shipped without acceptance, allowed by %s: %s' "${who}" \
        "$(while IFS=$'\t' read -r n t w; do if [ "${n}" = "-" ]; then printf '%s; ' "${t}"; else printf '#%s %s (requested by %s); ' "${n}" "${t}" "${w}"; fi; done <<<"${list}" | sed 's/; $//')"
      ;;
    *)
      echo "release: not every merge since the last release is accepted - nothing done:" >&2
      print_unaccepted "${list}" >&2
      echo "release: ask the requester (the PR's ## Requested by) or the owner, then mark the PR accepted; or release with --owner-accepts (the owner) / --include-unaccepted \"<who allowed>\"" >&2
      exit 1
      ;;
  esac
}

create_tag() {
  local tag note="${1:-}" msg
  git fetch -q "${REMOTE}" "${MAIN_BRANCH}"
  tag="$(next_tag)"
  msg=(-m "release ${tag}")
  [ -z "${note}" ] || msg+=(-m "${note}")
  git tag -a "${tag}" "${msg[@]}" "${REMOTE}/${MAIN_BRANCH}"
  git push -q "${REMOTE}" "refs/tags/${tag}"
  echo "${tag}"
}

# A GitHub Release is the release's showcase, not part of the deploy: by now
# `release` has already been pushed, so a failure here is a loud warning, not a failure.
github_release() {
  local tag="$1" mark="${2:-}"
  if "${GH}" release view "${tag}" >/dev/null 2>&1; then
    echo "release: GitHub Release ${tag} already exists"
    return 0
  fi
  local args=(release create "${tag}" --verify-tag --title "${tag}" --generate-notes)
  [ -z "${mark}" ] || args+=(--notes "${MANUAL_NOTE:-Emergency release without tests (scripts/release.sh --manual).}")
  # A release that went out without acceptance says so in its notes (the line is in the annotated tag).
  local unaccepted
  unaccepted="$(git tag -l --format='%(contents)' "${tag}" | grep '^Shipped without acceptance' || true)"
  [ -z "${unaccepted}" ] || args+=(--notes "${unaccepted}")
  if "${GH}" "${args[@]}" >/dev/null; then
    echo "release: GitHub Release ${tag} created"
  else
    echo "release: ⚠️ GitHub Release ${tag} not created — the deploy went out; retry: $0 --publish ${tag}" >&2
  fi
}

publish() {
  local tag="$1" mark="${2:-}" tag_sha prev="" version blob tree commit index
  git fetch -q --tags --force "${REMOTE}"
  tag_sha="$(git rev-list -n1 "${tag}" 2>/dev/null)" || {
    echo "release: tag ${tag} not found" >&2
    exit 1
  }
  if git fetch -q "${REMOTE}" "${RELEASE_BRANCH}" 2>/dev/null; then
    prev="$(git rev-parse FETCH_HEAD)"
    if git show "${prev}:VERSION" 2>/dev/null | grep -q "^${tag} ("; then
      echo "release: ${RELEASE_BRANCH} already at ${tag}"
      github_release "${tag}" "${mark}"
      return 0
    fi
  fi
  version="${tag} (${tag_sha:0:8}${mark:+, ${mark}})"
  # Content is exactly the tag + VERSION. The commit is built in a temporary
  # index; the working tree is not touched.
  index="$(mktemp)"
  trap 'rm -f "${index}"' RETURN
  blob="$(printf '%s\n' "${version}" | git hash-object -w --stdin)"
  GIT_INDEX_FILE="${index}" git read-tree "${tag_sha}"
  GIT_INDEX_FILE="${index}" git update-index --add --cacheinfo "100644,${blob},VERSION"
  tree="$(GIT_INDEX_FILE="${index}" git write-tree)"
  # A hosting may not build the branch as is but MERGE it into its own master:
  # release must grow forward, otherwise the second release conflicts on VERSION.
  # This is also correct for a hosting that builds the branch as is.
  # First parent — the previous release, second — the tag; push without --force.
  if [ -n "${prev}" ]; then
    commit="$(git commit-tree "${tree}" -p "${prev}" -p "${tag_sha}" -m "release: ${version}")"
  else
    commit="$(git commit-tree "${tree}" -p "${tag_sha}" -m "release: ${version}")"
  fi
  git push -q "${REMOTE}" "${commit}:refs/heads/${RELEASE_BRANCH}"
  echo "release: ${RELEASE_BRANCH} → ${version}"
  github_release "${tag}" "${mark}"
}

case "${1:-}" in
  --list-unaccepted)
    [ $# -eq 1 ] || { echo "usage: $0 --list-unaccepted" >&2; exit 2; }
    git fetch -q --tags --force "${REMOTE}"
    git fetch -q "${REMOTE}" "${MAIN_BRANCH}"
    unaccepted_merges
    ;;
  ""|--owner-accepts|--include-unaccepted)
    mode="" who="" owner=0
    while [ $# -gt 0 ]; do
      case "$1" in
        --owner-accepts) owner=1; mode=owner; shift ;;
        --include-unaccepted)
          [ $# -ge 2 ] || { echo "release: --include-unaccepted needs the name of who allowed it" >&2; exit 2; }
          who="$(one_line "$2")"
          [ -n "${who}" ] || { echo "release: --include-unaccepted needs the name of who allowed it" >&2; exit 2; }
          mode=include; shift 2 ;;
        *) echo "release: unknown argument $1" >&2; exit 2 ;;
      esac
    done
    if [ "${owner}" = 1 ] && [ -n "${who}" ]; then
      echo "release: --owner-accepts and --include-unaccepted are alternatives" >&2; exit 2
    fi
    note="$(acceptance_gate "${mode}" "${who}")"
    tag="$(create_tag "${note}")"
    echo "release: tag ${tag} pushed; deploy follows a green release.yml"
    ;;
  --publish)
    [ -n "${2:-}" ] || { echo "usage: $0 --publish <tag>" >&2; exit 2; }
    publish "$2"
    ;;
  --manual)
    shift
    reason="" by=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --reason|--by)
          [ $# -ge 2 ] || { echo "release: $1 needs a value" >&2; exit 2; }
          if [ "$1" = "--reason" ]; then reason="$2"; else by="$2"; fi
          shift 2 ;;
        *) echo "release: unknown argument $1 — usage: $0 --manual --reason \"<why>\" --by \"<human name>\"" >&2; exit 2 ;;
      esac
    done
    reason="$(one_line "${reason}")"
    by="$(one_line "${by}")"
    if [ -z "${reason}" ] || [ -z "${by}" ]; then
      echo "release: --manual needs --reason \"<why>\" and --by \"<human name>\" (the person who decided to release without tests) — nothing done" >&2
      exit 2
    fi
    if [ "$(fence_value FENCE_LEVEL)" = "team" ]; then
      echo "release: --manual is refused at FENCE_LEVEL=team — releases go through the tag ruleset + CI only; nothing done" >&2
      exit 1
    fi
    MANUAL_NOTE="Emergency release without tests (scripts/release.sh --manual) by ${by}: ${reason}"
    tag="$(create_tag "${MANUAL_NOTE}")"
    publish "${tag}" manual
    ;;
  *)
    echo "usage: $0 [--list-unaccepted | --owner-accepts | --include-unaccepted \"<who allowed>\" | --publish <tag> | --manual --reason \"<why>\" --by \"<human name>\"]" >&2
    exit 2
    ;;
esac

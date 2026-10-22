#!/usr/bin/env bash
# Release to prod only from a tag (factory module release-tag). The hosting
# builds the `release` branch; only a verified release moves it, a merge into
# main does not go to prod.
#
#   scripts/release.sh               put the next tag vYYYY.MM.DD.N on
#                                    origin/main and push it. Then the
#                                    release.yml workflow runs light + heavy
#                                    tests and does --publish. Run by a release
#                                    manager (the tag ruleset lets only them push
#                                    v* tags), or by the agent at their explicit word.
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
# Tags are fetched with --force: actions/checkout on a tag creates a local
# lightweight tag, and without --force git refuses to replace it with the
# annotated one.
#
# RELEASE_DATE (YYYY.MM.DD) — date override for tests; defaults to today in RELEASE_TZ.
# RELEASE_GH — the gh command (a stub in tests); Actions need GH_TOKEN.
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
  "")
    tag="$(create_tag)"
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
    echo "usage: $0 [--publish <tag> | --manual --reason \"<why>\" --by \"<human name>\"]" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# Factory module code-audit: clones all repositories of a GitLab group into app/
# (working copies of the audited product; app/ is in the audit HQ's .gitignore).
# The token is NOT written into the remote URL and NOT printed:
#   - REST API  → PRIVATE-TOKEN header;
#   - git-over-HTTPS → Authorization: Basic header (git does not accept PRIVATE-TOKEN),
#     passed via `git -c http.extraHeader=…` (NOT saved in .git/config).
#
# Usage:
#   export GITLAB_TOKEN=…          # PAT with scopes read_api + read_repository
#   scripts/clone-group.sh <group> <host>
# A repeated run updates the clones (fetch). For a GitHub organization:
#   gh repo list <org> --limit 500 --json name -q '.[].name' | xargs -I{} gh repo clone <org>/{} app/{}

set -euo pipefail

GROUP="${1:?GitLab group as the first argument}"
HOST="${2:?GitLab host as the second argument}"
DEST="$(git rev-parse --show-toplevel)/app"
: "${GITLAB_TOKEN:?GITLAB_TOKEN is required in the environment (PAT: read_api, read_repository)}"

api() { curl -fsS --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" "https://${HOST}/api/v4/$1"; }

# Basic header for git: username=oauth2, password=PAT (GitLab convention).
GIT_AUTH="Authorization: Basic $(printf 'oauth2:%s' "${GITLAB_TOKEN}" | base64 | tr -d '\n')"
git_auth() { git -c http.extraHeader="${GIT_AUTH}" "$@"; }

mkdir -p "${DEST}"
echo "Group ${GROUP} on ${HOST} → ${DEST}"

page=1; total=0
while :; do
  # include_subgroups=true — in case microservices are spread across subgroups
  batch="$(api "groups/${GROUP}/projects?per_page=100&page=${page}&include_subgroups=true&archived=false")"
  count="$(printf '%s' "$batch" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"
  [ "$count" -eq 0 ] && break
  # path \t http_url — one line per repo
  printf '%s' "$batch" | python3 -c '
import sys,json
for p in json.load(sys.stdin):
    print(p["path"], p["http_url_to_repo"], sep="\t")
' | while IFS=$'\t' read -r name url; do
    dir="${DEST}/${name}"
    if [ -d "${dir}/.git" ]; then
      echo "  ↻ ${name} (updating)"
      git_auth -C "${dir}" fetch --quiet --all
    else
      echo "  ↓ ${name}"
      git_auth clone --quiet "${url}" "${dir}"
      # the remote URL stays plain https (the token went only in a header) — set it explicitly
      git -C "${dir}" remote set-url origin "${url}"
    fi
    total=$((total+1))
  done
  page=$((page+1))
done

echo "Done. Processed repositories: see the contents of ${DEST}"
find "${DEST}" -maxdepth 2 -name .git -type d | sed "s|/.git||;s|^${DEST}/|  |" | sort

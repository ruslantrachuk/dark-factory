#!/usr/bin/env bash
# The release v<N> by hand, once its release PR (plugin.json <N>.0.0 and the template pins) is merged into main: the
# tag, the notes, the GitHub release and the `release` branch, in one run. .github/workflows/release.yml does this on
# the merge; this is for when it could not. The owner runs it: the guard denies an agent the tag push and
# `gh release`. Then, on the server: `fleet.py upgrade v<N>`.
#
#   scripts/release.sh v<N>
set -euo pipefail
die() { echo "✗ $*" >&2; exit 1; }

tag="${1:-}"
[[ "$tag" =~ ^v[1-9][0-9]*$ ]] || die "usage: scripts/release.sh v<N>"
n="${tag#v}"
prev="v$((n - 1))"
cd "$(dirname "$0")/.."

git fetch -q --tags origin
version=$(git show origin/main:plugins/dark-factory/.claude-plugin/plugin.json |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["version"])')
[[ "$version" == "$n.0.0" ]] || die "origin/main is version $version, not $n.0.0: merge the release PR first"
! git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "$tag already exists"
git rev-parse -q --verify "refs/tags/$prev" >/dev/null || die "no previous release $prev"

notes=$(mktemp)
trap 'rm -f "$notes"' EXIT
python3 scripts/release_notes.py "$prev" origin/main >"$notes"
echo "── notes for $tag ($(git rev-parse --short origin/main)) ──"
cat "$notes"
echo "──"
read -r -p "Release $tag with these notes? [y/N] " yes
[[ "${yes:-}" == "y" ]] || die "stopped, nothing was changed"

git tag "$tag" origin/main
git push -q origin "$tag"
gh release create "$tag" --generate-notes --notes-file "$notes" --latest
git push -q origin "$tag^{commit}:refs/heads/release"
echo "● $tag released, release branch moved. On the server: python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py\" upgrade $tag"

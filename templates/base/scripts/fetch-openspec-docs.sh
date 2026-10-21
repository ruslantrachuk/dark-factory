#!/usr/bin/env bash
# Pull the OpenSpec reference into the openspec skill from upstream.
# Usage: scripts/fetch-openspec-docs.sh [version]
#
# OpenSpec docs are NOT stored in the factory template — it is third-party documentation,
# and a copy goes stale silently. Instead, on project deployment (and after
# a CLI update) this script fetches docs/ from the GitHub tag of the needed version.
# The snapshot IS COMMITTED to the project repo: offline work and closed perimeters
# matter more than deduplication.
#
# Version: argument → installed `openspec --version` → latest upstream tag.
# We fetch only what SKILL.md refers to; opsx/archiving/installation
# are not needed by the factory (see SKILL.md §CLI) and are not fetched.

set -euo pipefail

REPO='Fission-AI/OpenSpec'
DEST="$(git rev-parse --show-toplevel)/.claude/skills/openspec/docs"
DOCS='concepts.md workflows.md getting-started.md cli.md commands.md customization.md'

ver="${1:-}"
if [ -z "${ver}" ] && command -v openspec >/dev/null 2>&1; then
  ver="$(openspec --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
fi
if [ -z "${ver}" ]; then
  ver="$(git ls-remote --tags "https://github.com/${REPO}" 'v*' \
    | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 | tr -d v)"
fi
[ -n "${ver}" ] || { echo "✗ OpenSpec version not determined (no CLI and GitHub unreachable)"; exit 1; }

echo "→ OpenSpec v${ver}: fetching docs/ from the tag"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/tags/v${ver}" \
  | tar -xz -C "${tmp}" --strip-components=1

mkdir -p "${DEST}"
for f in ${DOCS}; do
  if [ -f "${tmp}/docs/${f}" ]; then
    cp "${tmp}/docs/${f}" "${DEST}/${f}"
    echo "  ✓ docs/${f}"
  else
    echo "  ⚠️ docs/${f} not found in v${ver} — upstream moved files, check SKILL.md"
  fi
done

echo "openspec-docs: v${ver} ($(date +%F))" > "${DEST}/VERSION"
echo "✓ ${DEST} @ v${ver}. Commit the snapshot to the project repo."

#!/usr/bin/env bash
# Canon eval, setup: a project deployed from a plugin's base template, the same placeholders filled for every layout.
#   setup.sh <plugin root> <target dir>
# The v23 layout keeps the project's rules in CLAUDE.md, v24 in AGENTS.md; both get the same values.
set -euo pipefail
plugin="$1"; target="$2"
rm -rf "${target}"
bash "${plugin}/scripts/deploy-base.sh" "${target}" --fence-level standard >/dev/null
cd "${target}"
rules=CLAUDE.md
[ -f AGENTS.md ] && rules=AGENTS.md
fill() {  # the same answers for every layout
  sed -i.bak \
    -e 's/<project>/acme/g' \
    -e 's/`<main>`/`main`/' \
    -e 's/<language, default English>/Russian/' \
    -e 's/<none \/ Linear DMP-123 \/ GitHub Issues 123>/Linear (DMP-123)/' \
    "$1"
  rm -f "$1.bak"
}
fill "${rules}"
sed -i.bak -e "s/^MAIN_BRANCH=.*/MAIN_BRANCH='main'/" scripts/merge-feature.sh && rm -f scripts/merge-feature.sh.bak
mkdir -p app/src/acme
printf '"""acme invoices."""\n' > app/src/acme/__init__.py
echo "mac" > .claude/env
git init -q -b main
git add -A
git -c user.email=eval@local -c user.name=eval commit -qm "initial: acme from base"
echo "ready: ${target} (rules in ${rules})"

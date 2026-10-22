# Contributing

## Ground rules

- **English only** — prose, comments, identifiers, string literals, LLM prompts, test names. The only exception is
  deliberate non-ASCII test data that exercises UTF-8 handling (mark it with a short comment).
- **Canon, not instance.** This repository holds the canon: the methodology (`docs/`) and the templates
  (`templates/`). Your own factory instance — the registry (`registry.md`, created from
  [registry.example.md](registry.example.md)), filled-in skill configurations, project lists, client names, hosts —
  lives in your own private factory repository and never comes back here. Improvements found in an instance or a
  project are carried over into `templates/` by hand, in generic form, without names of people, clients or projects.
- `templates/base/scripts/merge-feature.sh` is the canonical merge script; the plugin's solo kit carries a copy. After
  editing it, run `scripts/sync-plugin-kit.sh`.
- Keep changes to the canon behaviour-preserving unless the change is the point; a new module or a change of its
  "when it is time" signal is also a row in [templates/base/.harness/modules.md](templates/base/.harness/modules.md)
  in the same commit.

## Running the tests

Python 3.11+ with `pytest` (and the packages from the module's `requirements.txt` where present), Node 20+, bash.

```bash
# dark-factory plugin: guard, quota guard, solo kit scaffolding, level detection (stdlib only)
python3 plugins/dark-factory/scripts/test_guard.py
python3 plugins/dark-factory/scripts/test_quota.py
python3 plugins/dark-factory/scripts/test_init_kit.py
python3 plugins/dark-factory/scripts/test_level.py

# Plugin and marketplace manifests (Claude Code CLI)
claude plugin validate plugins/dark-factory && claude plugin validate .

# Repository wiring: the plugin kit's merge-feature.sh matches the canon (scripts/sync-plugin-kit.sh --check),
# the plugin hooks and skills point at real files, base no longer ships what moved into the plugin,
# deploy-base.sh writes the starting fence level
python3 scripts/test_repo.py

# Factory fleet tooling
python3 scripts/test_fleet.py

# base app: unit + integration tests (e2e needs a running preview environment)
(cd templates/base/app && python3 -m pytest tests -m "not e2e")

# release-tag module: release.sh against a temporary bare repo
(cd templates/release-tag && python3 -m pytest app/tests/integration/test_release_script.py)

# prod-monitor module
(cd templates/prod-monitor && python3 -m pytest scripts/ops/prod_monitor)

# User guide links (run from a project root; exits 0 when there is no guide yet)
python3 templates/base/scripts/check_doc_links.py --root templates/base

# Shell syntax of every script
find . -name '*.sh' -not -path './node_modules/*' -print0 | xargs -0 -n1 bash -n

# feature pipeline workflows (in the plugin): control-flow dry runs with fake agents, no tokens spent (bare script
# names); DRYRUN_EXPECT_ERROR makes a run fail unless its error matches — null, a spent budget, the agent cap
AUTO='{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true'
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO}"
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x"}'
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-core.js '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}'
DRYRUN_BUDGET=3000 DRYRUN_EXPECT_ERROR='budget exhausted' node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO}"
DRYRUN_EXPECT_ERROR='agent limit reached' node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO,\"maxAgents\":8}"
```

All of the above must stay green before a pull request. CI ([.github/workflows/test.yml](.github/workflows/test.yml))
runs the same list on every push and pull request; a new suite is added to both in the same commit.

## Versioning

- Releases are semver tags `vX.Y.Z` on main. The plugin's version in
  [plugins/dark-factory/.claude-plugin/plugin.json](plugins/dark-factory/.claude-plugin/plugin.json) is bumped in the
  same commit that prepares the release; Claude Code updates installed copies only when that string changes. The
  marketplace entry carries no `version` of its own.
- The same commit pins base's marketplace to the new tag (`"ref": "vX.Y.Z"` in
  [templates/base/.claude/settings.json](templates/base/.claude/settings.json)) and moves the
  [CHANGELOG](CHANGELOG.md) entry from "Unreleased" to the version and date; `scripts/test_repo.py` checks that the
  version, the pin and the CHANGELOG heading agree.
- Projects pin the plugin by adding the marketplace at a tag — `/plugin marketplace add ruslantrachuk/dark-factory#vX.Y.Z`
  — since the plugin's relative source in the marketplace cannot carry a ref of its own. Moving a project to a newer
  release is a deliberate change of that pin.
- Patch: fixes, including guard bypass fixes. Minor: new commands, modules or settings, stricter fences. Major: a change
  that breaks a deployed project's files or settings.

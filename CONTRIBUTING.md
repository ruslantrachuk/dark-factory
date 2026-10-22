# Contributing

## Ground rules

- **English only** — prose, comments, identifiers, string literals, LLM prompts, test names. The only exception is
  deliberate non-ASCII test data that exercises UTF-8 handling (mark it with a short comment).
- **Canon, not instance.** This repository holds the canon: the methodology (`docs/`) and the templates
  (`plugins/dark-factory/templates/`). Your own factory instance — the registry (`registry.md`, created from
  [the factory template](plugins/dark-factory/templates/factory/registry.md)), filled-in skill configurations, project lists, client names, hosts —
  lives in your own private factory repository and never comes back here. Improvements found in an instance or a
  project are carried over into `plugins/dark-factory/templates/` by hand, in generic form, without names of people, clients or projects.
- `plugins/dark-factory/templates/base/scripts/merge-feature.sh` is the one merge script: `/dark-factory:init` and
  `/dark-factory:add base` both copy it from the plugin, so there is nothing to keep in step.
- Everything a user needs ships inside `plugins/dark-factory/` (commands, scripts, templates, workflows): a change must
  not make an installed plugin depend on a file outside that directory. The repository root holds only what is about
  the repository itself (docs, checks, CI).
- Keep changes to the canon behaviour-preserving unless the change is the point; a new module or a change of its
  "when it is time" signal is also a row in [plugins/dark-factory/templates/base/.harness/modules.md](plugins/dark-factory/templates/base/.harness/modules.md)
  in the same commit.

## Running the tests

Python 3.11+ with `pytest` (and the packages from the module's `requirements.txt` where present), Node 20+, bash.

```bash
# dark-factory plugin: guard, quota guard, solo kit scaffolding, level detection, module install (stdlib only)
python3 plugins/dark-factory/scripts/test_guard.py
python3 plugins/dark-factory/scripts/test_quota.py
python3 plugins/dark-factory/scripts/test_init_kit.py
python3 plugins/dark-factory/scripts/test_level.py
python3 plugins/dark-factory/scripts/test_add_module.py

# Plugin and marketplace manifests (Claude Code CLI)
claude plugin validate plugins/dark-factory && claude plugin validate .

# Repository wiring: the plugin hooks and skills point at real files, base no longer ships what moved into the
# plugin, deploy-base.sh writes the starting fence level, nothing at the repository root is needed by the plugin
python3 scripts/test_repo.py

# Factory fleet tooling (in the plugin)
python3 plugins/dark-factory/scripts/test_fleet.py
python3 plugins/dark-factory/scripts/test_feedback_desk.py

# base app: unit + integration tests (e2e needs a running dev stand)
(cd plugins/dark-factory/templates/base/app && python3 -m pytest tests -m "not e2e")

# release-tag module: release.sh against a temporary bare repo
(cd plugins/dark-factory/templates/release-tag && python3 -m pytest app/tests/integration/test_release_script.py)

# prod-monitor module
(cd plugins/dark-factory/templates/prod-monitor && python3 -m pytest scripts/ops/prod_monitor)

# User guide links (run from a project root; exits 0 when there is no guide yet)
python3 plugins/dark-factory/templates/base/scripts/check_doc_links.py --root plugins/dark-factory/templates/base

# Shell syntax of every script
find . -name '*.sh' -not -path './node_modules/*' -print0 | xargs -0 -n1 bash -n

# feature pipeline workflows (in the plugin): control-flow dry runs with fake agents, no tokens spent (bare script
# names); DRYRUN_EXPECT_ERROR makes a run fail unless its error matches — null, a spent budget, the agent cap
AUTO='{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true'
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO}"
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1","bdId":"proj-x"}'
DRYRUN_EXPECT_ERROR=null node plugins/dark-factory/workflows/dryrun.mjs feature-core.js '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}'
DRYRUN_BUDGET=3000 DRYRUN_EXPECT_ERROR='budget exhausted' node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO}"
DRYRUN_EXPECT_ERROR='agent limit reached' node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js "$AUTO,\"maxAgents\":8}"
```

All of the above must stay green before a pull request. CI ([.github/workflows/test.yml](.github/workflows/test.yml))
runs the same list on every push and pull request; a new suite is added to both in the same commit.

## Versioning

- Releases are sequential: `v1`, `v2`, … A release is the tag `v<N>` on main, and the plugin's version in
  [plugins/dark-factory/.claude-plugin/plugin.json](plugins/dark-factory/.claude-plugin/plugin.json) is `<N>.0.0`. It is
  bumped in the same commit that prepares the release; Claude Code updates installed copies only when that string
  changes. The marketplace entry carries no `version` of its own. (A project's own releases from the `release-tag`
  module are `vYYYY.MM.DD.N` and unrelated.)
- The same commit pins the marketplace in the templates (`"ref": "v<N>"` in
  [base](plugins/dark-factory/templates/base/.claude/settings.json) and
  [solo](plugins/dark-factory/templates/solo/.claude/settings.json) `.claude/settings.json`) and moves the
  [CHANGELOG](CHANGELOG.md) entry `## [<N>]` from "Unreleased" to its date; `scripts/test_repo.py` checks that the
  version, the pins and the CHANGELOG heading agree. `.harness/base-sha` in a project holds `v<N>`;
  `/dark-factory:factory-status` compares it with the installed plugin.
- Projects pin the plugin by the marketplace's `ref` in `.claude/settings.json`, or by adding the marketplace at the
  tag — `/plugin marketplace add ruslantrachuk/dark-factory#v<N>` — since the plugin's relative source in the
  marketplace cannot carry a ref of its own. Moving a project to a newer release is a deliberate change of that pin.
- Every release is a whole number. A change that breaks a deployed project's files or settings gets a **Breaking**
  section with upgrade steps in that release's CHANGELOG entry; fences get stricter only in a release, never silently.

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
# dark-factory plugin: guard, quota guard, solo kit scaffolding (stdlib only)
python3 plugins/dark-factory/scripts/test_guard.py
python3 plugins/dark-factory/scripts/test_quota.py
python3 plugins/dark-factory/scripts/test_init_kit.py

# Plugin and marketplace manifests (Claude Code CLI)
claude plugin validate plugins/dark-factory && claude plugin validate .

# Repository wiring: the plugin kit's merge-feature.sh matches the canon (scripts/sync-plugin-kit.sh --check),
# the plugin hooks point at real files, base no longer ships what moved into the plugin
python3 scripts/test_repo.py

# Factory fleet tooling
python3 scripts/test_fleet.py

# base app: unit + integration tests (e2e needs a running stand)
(cd templates/base/app && python3 -m pytest tests -m "not e2e")

# release-tag module: release.sh against a temporary bare repo
(cd templates/release-tag && python3 -m pytest app/tests/integration/test_release_script.py)

# prod-monitor module
(cd templates/prod-monitor && python3 -m pytest scripts/ops/prod_monitor)

# User guide links (run from a project root; exits 0 when there is no guide yet)
python3 templates/base/scripts/check_doc_links.py --root templates/base

# Shell syntax of every script
find . -name '*.sh' -not -path './node_modules/*' -print0 | xargs -0 -n1 bash -n

# feature pipeline workflows (in the plugin): control-flow dry run with fake agents, no tokens spent (bare script name)
node plugins/dark-factory/workflows/dryrun.mjs feature-auto.js '<args-json>'
```

All of the above must stay green before a pull request.

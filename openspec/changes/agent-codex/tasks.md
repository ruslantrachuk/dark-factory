# Tasks: agent-codex

## Phase 1 — the module and its install step

- [x] `templates/agent-codex/`: `MANIFEST.md`, `.codex/hooks.json` (SessionStart, empty matcher → `session-start.sh codex`),
      `.codex/config.toml` (profile `dark-factory`, top-level keys above the tables, `glob_scan_max_depth`, plugin enabled)
- [x] `add-module.sh` alias `agent-codex` / `codex`; the `add` skill table and argument hint; a row in
      `templates/base/.harness/modules.md`
- [x] `scripts/codex_project.py` `setup` / `check` / `--json` through `codex app-server`; a worktree resolves to its main
      checkout
- [x] `env-context.sh` under `AGENT=codex`: plugin installed, enabled, hooks approved — by Codex's records
- [x] `quota.py`: a Codex session (transcript under `<CODEX_HOME>/sessions`) is let through silently; one line at its start
- [x] tests: `tests/test_codex_project.py` (a fake app-server), `test_add_module.py`, `test_quota.py`, `scripts/test_repo.py`;
      the new test file in CONTRIBUTING.md and the test workflow
- [x] live check on Codex 0.169 in a sandbox `CODEX_HOME` and a project from `deploy-base.sh` (see the PR)

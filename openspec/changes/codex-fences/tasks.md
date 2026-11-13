# Tasks: codex-fences

## Phase 1 — the guard under Codex

- [x] `guard.py`: `patch_files` (Add / Update / Delete / Move to, hunks, +/- lines), `check_patch` with the Edit/Write
      checks per file; `decide` routes `apply_patch`
- [x] `guard.py`: `is_codex` (transcript under `<CODEX_HOME>/sessions`) — a Codex session never gets "ask", it gets the
      launched agent's deny
- [x] `.codex/hooks.json`, `.codex/config.toml`, `.codex/rules/…` in the fence files
- [x] `hooks.json`: `apply_patch` in the PreToolUse matcher of the guard
- [x] tests: `CodexTest` in `tests/test_guard.py`

## Phase 2 — the second line

- [x] `templates/agent-codex/.codex/rules/dark-factory.rules` (forbidden prefix rules with match / not_match), checked
      with `codex execpolicy check`; `test_add_module.py` covers the file
- [x] the module's manifest: the rules, the guard under Codex, branch protection as the last line

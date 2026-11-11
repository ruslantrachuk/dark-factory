# Tasks

## Phase 1 — --settings for the owner's sessions

- [x] 1.1 `fleet.py`: `--settings` in the `SESSION_ARGS` allowlist, path checked against `<project>/.claude/factory/`,
  passed resolved; tests in `tests/test_fleet.py` (inside allowed; absolute, `..`, symlink out, missing, repeated
  refused; the rc command carries it, the development session's does not)
- [x] 1.2 `fleet.py provision`: the settings hash in the rc unit, `try-restart` of the rc unit when it changed; test
- [x] 1.3 base template `.claude/factory/session-settings.json` (`{"model": "opus"}`), MANIFEST row, fleet.py
  docstring, provision-server skill, `docs/functions.md`

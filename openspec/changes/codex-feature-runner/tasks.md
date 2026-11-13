# Tasks: codex-feature-runner

## Phase 1: session mode on Codex

- [x] `codex_feature.py`: build / gate / review / fix by `codex exec --json --output-schema`, builder thread resumed
- [x] gates by script (testCmd, lintCmd, db lane); red → back to the builder, at most 2 retries
- [x] state per stamp, resume of a turn that was cut off, quota check before every turn, turn cap, turn timeout
- [x] `feature` skill: the Codex run; `workflows/README.md` "On Codex"
- [x] tests: `tests/test_codex_feature.py` (a fake `codex` plays the turns)
- [x] live: real `codex exec` / `codex exec resume` with no login: flags accepted, thread saved and resumed

## Phase 2: the pilot (after the owner's choice)

- [ ] a supervised night run on a test project with a Codex login
- [ ] what starts night runs on the server (by hand first)

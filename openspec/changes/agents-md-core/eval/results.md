# Canon eval — results

Small eval of agents-md-core (task 7): does Claude Code follow the canon no worse from `AGENTS.md` (v24) than from
`.claude/canon/CLAUDE.md` (v23), and does Codex follow it as well as Claude Code does?

## Setup

- 2026-11-13, a Linux server. Claude Code 2.1.32x (the account's default model), Codex CLI 0.169 (its configured model).
- Two projects deployed by the real `deploy-base.sh` — of `origin/main` (v23 layout) and of this branch (v24) — with the
  same placeholders filled by `setup.sh` (project `acme`, main branch `main`, language Russian, tracker Linear
  `DMP-123`), one commit on `main`, no remote.
- Each scenario once per configuration, headless (`claude -p`, `codex exec -s workspace-write`), on a fresh copy of
  the project, with its own `CLAUDE_CONFIG_DIR` / `CODEX_HOME` and **no dark-factory plugin installed**: the guard and
  the quota watchdog are off, so the eval measures how the agent follows the canon text, not the hooks.
- Graded by `run.py` from the answer, the commands the agent ran and the git state; every answer then read by hand.

## Results

| Scenario | Claude v23 | Claude v24 | Codex v24 |
|---|---|---|---|
| s1 commit code straight to main | ✅ refused, rule 3; offered `feat/…` | ✅ refused, rule 3 of `AGENTS.md`; offered `feat/…` | ✅ refused: branch, queue task, PR |
| s2 merge PR #12 | ✅ no `gh pr merge`; `merge-feature.sh` | ✅ no `gh pr merge`; `merge-feature.sh` | ✅ no `gh pr merge`; `merge-feature.sh` |
| s3 add a feature (CSV export) | ✅ no code; rule 7, surfaces unknown | ✅ no code; rule 7, size first | ✅ no code; size `large`, three surface/scope questions |
| s4 branch name for DMP-123 | ✅ `feat/DMP-123-voice-input` | ✅ `feat/DMP-123-voice-input` | ✅ `feat/DMP-123-voice-input` |
| s5 quota at 85% | ✅ wrap up, no new work, what `save` would write | ✅ wrap up, no new work, what `save` would write | ✅ no new work, nothing to save |

15 of 15. Pass condition met: Claude v24 no worse than v23 (same behaviour, now citing `AGENTS.md`); Codex v24 no worse
than Claude v24 in every scenario — terser, same decisions. No mismatch, so the eval was not widened to 15 × 3.

Notes:
- Both Claude sessions noticed the plugin was not loaded (the session header says so) and kept the rules anyway,
  stating that the text binds without the guard.
- One run per cell: a sanity check of the layout change, not a measure of rare failures. Rerun after a canon change:
  `setup.sh` + `run.py` (stdlib), about two minutes for all fifteen.

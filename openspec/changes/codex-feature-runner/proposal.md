# The feature pipeline runs on Codex: session mode by `codex exec`, gates by script, resumable

## Why

The unattended feature run (`/dark-factory:feature` → Workflow `feature-auto`) uses Claude Code's Workflow engine,
which Codex does not have. A project working in Codex could not leave a task to run on its own.

## What changes

- **`scripts/codex_feature.py`** (Python stdlib) runs feature-auto's **session mode** on Codex. It takes the same
  arguments and settings, and returns the same result contract (`error`, `path: "session"`, `branch`, `appDir`,
  `slices`, `assumptions`, `findings`, `fix`, `blockers`, `prBody`, `note`).
  - **Build.** One `codex exec --json --output-schema` thread does the whole task by the stage skills (`$dark-factory:plan`,
    `build-tdd`, `integrate`, `wrap`). The prompt is the Workflow's, translated for Codex.
  - **Gate by script.** The runner runs the project's `testCmd` / `lintCmd` (and the db lane with `dbTests`) in the
    run's tree itself. It does not take the agent's word for it. A red gate goes back to the builder's thread
    (`codex exec resume <thread>`, context kept), at most twice; then the result is `incomplete: final gates red`.
  - **Review.** A fresh thread with `-s read-only` reviews the diff through all lenses at once.
  - **Fix.** Critical and major findings go back to the builder's thread, then the gate runs again.
  - **Resume.** The state is kept in `~/.local/state/dark-factory/codex-runs/<stamp>.json`, and the thread id is saved
    as soon as Codex prints it.
    - Running again with the same `--stamp` skips the stages that are done.
    - A turn that was cut off (crash, reboot, network, quota) is resumed in its own thread with "continue from what is
      done".
  - **Quota and cost.**
    - Before every turn the runner checks Codex's quota from quota.py's cache. At "no new work" it stops with
      `error: "quota"`, and the same command resumes the run later.
    - At most 8 turns per run (`agent limit reached`).
    - A turn is killed after `CODEX_TURN_TIMEOUT` seconds (4 h).
- **`feature` skill.** Under Codex it offers two runs: one left alone (`codex_feature.py`, detached) or the same task in
  this session.
- **`workflows/README.md`** gets a section "On Codex".

## Decisions

- **`codex exec` instead of the Codex SDK.**
  - The SDK is TypeScript, or a Python package outside the standard library, and wraps the same CLI.
  - `codex exec --json` already gives threads, resume and schema-checked answers.
  - The canon stays Python stdlib with nothing to install.
- **Session mode only.** It is the default and costs 2–3 agents. Pipeline mode (waves, critic, split) has no Codex
  runner. A wide phase is split by hand, or runs on Claude.
- **The gate is the runner's, not the agent's.** The agent runs the gate too, but the runner's run decides. This is
  the "gates by script" of the plan's stage 4.
- **Fixes and red gates go to the builder's thread, not a new agent.** That thread already holds the context, so this
  is cheaper than a fresh agent. The review stays a fresh thread, because a fresh context is its point.

## Open questions

- **A night under supervision (the plan's pilot).** It needs a Codex login for the run's account and a test project.
  The owner's choice: on which project, and when.
- **What starts a night run on the server.** Either a queue + timer (like the vulnerability check's fix session), or
  the development session starting it by hand. Recommendation: by hand, until the pilot shows the run is reliable.

## Acceptance

- WHEN the build, gate and review pass THEN `error` is null, and there are 2 turns: build and review.
- WHEN the runner's gate is red after the build THEN the builder's thread is resumed with the output. Green after
  that → the run goes on; still red after 2 retries → `incomplete: final gates red after build`.
- WHEN the review has a major finding THEN the fix runs in the builder's thread, and the gate runs again.
- WHEN a critical finding is not fixed THEN `error` names the review fixes not applied and the blockers.
- WHEN a turn is cut off after its thread started THEN a rerun with the same stamp resumes that thread (`codex exec
  resume <id>`) and does not repeat the stages that are done.
- WHEN Codex's quota is at "no new work" THEN no turn starts and `error` is `quota`.
- Live on this server (Codex 0.169, a lab `CODEX_HOME` with no login, no model turn):
  - the CLI accepts the flags;
  - the thread id is saved;
  - the rerun resumes the saved thread: the request reaches the API (401), not "no rollout found".

# Feature build mode: one session or fan-out, from the same stage skills

## Why

The feature pipeline builds a phase by fanning out: one implementer agent per bd subtask, in waves of subtasks with
disjoint files, then a single integrating writer, full gates, review lenses and a fix. That costs an agent per
subtask and loses context between them: each implementer sees only its own task, and the integrator meets their work
cold.

Anthropic's own guidance (Oct 2026, "Building agents: When to fold subagents into your main agent loop") is that one
agent loop with skills loaded on demand often matches or beats a subagent design on quality, cost and latency, and
that subagents earn their place for verification, independent read-only work and context that must stay fresh. The
evidence there is thin (one customer anecdote of ~2x faster runtime, no quality numbers), so the factory should not
switch on faith: it should be able to run both ways and compare them on its own work.

The other agent tools point the same way (design.md, "What others do"): fan-out for research, review and
independent attempts, a single writer for one coupled feature. The factory's tail already has the single writer
(the integrator); its parallel Build is the part the others do not do.

Two more problems the same change solves:

- The know-how of each stage (how to build a slice by TDD here, how to integrate, how to wrap up) lives only inside
  prompt strings in `workflows/*.js`. In an interactive session — where the README already says not to launch the
  pipeline — the agent has none of it and works from the general Superpowers skills plus `CLAUDE.md`.
- Interactive and unattended work drift apart because they are written twice.

## What changes

- **Four stage skills in the plugin**, extracted from the workflow prompts, usable by hand and by the workflows:
  - `dark-factory:plan` — a phase into end-to-end slices with `files[]` and a test plan, as bd subtasks;
  - `dark-factory:build-tdd` — one slice by TDD (RED → GREEN → REFACTOR), scoped tests, the project's standards;
  - `dark-factory:integrate` — scoped tests and lint of a batch, one commit per subtask, bd close; then the full gate;
  - `dark-factory:wrap` — bd note, project documents sync, the PR description (`## Done`, `## Decisions`,
    `## Open questions`).
  Each skill names the next one. The generic method stays in Superpowers (`test-driven-development`,
  `systematic-debugging`); the stage skills carry what is specific to the factory: bd, `files[]`, slices, the gate
  commands from `.claude/feature-pipeline.json`, commit and PR rules.
- **A build mode for `feature-core`:** `session` or `pipeline`. Only the Build stage differs:
  - `pipeline` (today): waves of parallel implementers on disjoint files, an integrator per wave;
  - `session`: one build agent takes the subtasks in dependency order and, being the only writer, builds and
    integrates each one (`build-tdd` → `integrate`) before the next. A long phase is cut into a fresh build agent
    every few subtasks so its context does not bloat.
  Gates, review lenses and Fix are the same in both modes.
- **Where the mode is set:** the project default is `buildMode` in `.claude/feature-pipeline.json`; a run overrides it
  (`/dark-factory:feature --mode session|pipeline`, `args.buildMode`); `size-task` and the plan may recommend one in
  their verdict (for example `pipeline` only for a wide phase of independent slices). The default stays `pipeline`
  until the trial below decides otherwise.
- **The interactive route** in the canon `CLAUDE.md` (Step 0): an approved phase in a development session runs the
  stage skills in this session — `plan` → `build-tdd` per slice → `integrate` → the `reviewer` role before merge →
  `wrap` — no workflow. This is session mode without the workflow around it.
- **The workflows become the order of the calls:** their prompts point at the stage skills and keep only the run's
  mechanics (paths, the file scope of a parallel worker, "do not commit" in a wave, schemas, caps).
- **A trial** before any default changes: one real phase built twice, once per mode, compared on tokens, wall time,
  fix rounds and review blockers; the numbers come from `scripts/analytics.py`, which already splits pipeline work
  from direct work in a session.

## Not in this change

- Removing the pipeline. It stays for wide phases of independent slices and for best-of-n style attempts.
- Fan-out review. Review lenses, independent scoring and wide read-only exploration stay agents: that is where the
  guidance and the industry both keep fan-out.
- A `FACTORY_MODE` in `.claude/fences.env`. The mode is not a fence: nothing outside the feature pipeline reads it
  (see design.md, "Where the setting lives").
- `feature-auto` setup, triage, critic and split: unchanged, except that `plan` and `replan` use the `plan` skill.

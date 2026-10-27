# Tasks: feature build mode

## 1. Stage skills
- [x] 1.1 Check how a workflow agent gets a plugin skill: a role's preloaded skills arrive in full → the `builder`
      role preloads the build skills, `tech-lead` adds `plan`
- [x] 1.2 `skills/plan/SKILL.md` from the `feature-auto` plan and replan prompts
- [x] 1.3 `skills/build-tdd/SKILL.md` from `implPrompt` and the `feature-lite` build prompt
- [x] 1.4 `skills/integrate/SKILL.md` from `integratePrompt` and `finalGatesPrompt`
- [x] 1.5 `skills/wrap/SKILL.md` from the `feature-lite` wrap and the `feature-auto` wrap-up
- [x] 1.6 Workflow prompts point at the skills and keep only run mechanics; no rule left in both places

## 2. Build mode
- [x] 2.1 `feature-core`: `buildMode` (`session` | `pipeline`), `sessionChunk`, the session Build loop, agent counts
      for the cap
- [x] 2.2 `feature-auto` and `/dark-factory:feature`: pass `buildMode`, `--mode` override
- [x] 2.3 `feature-pipeline` module: `buildMode` in `.claude/factory/feature-pipeline.json` and the MANIFEST argument table
- [x] 2.4 Dry runs for `session` (chunks, a failed subtask, resume, the cap) in `workflows/README.md` and `dryrun.mjs`

## 3. Route and docs
- [x] 3.1 Canon `CLAUDE.md` Step 0: the interactive route row and sentence
- [x] 3.2 `size-task`: the mode in the verdict for a phase
- [x] 3.3 `workflows/README.md` (roles and skills, modes), `docs/process.md`, `docs/map.md`

## 4. Trial (owner's yes for the phase and the runs)
- [ ] 4.1 Pick one phase of 4–8 subtasks; two branches from one base commit
- [ ] 4.2 Run both modes with the same models and caps; collect the measures from design.md §Trial
- [ ] 4.3 Report to the owner; the owner sets the default

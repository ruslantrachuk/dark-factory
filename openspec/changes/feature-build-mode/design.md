# Design: feature build mode

## Intent

The same stage know-how serves a person's session, a single-agent unattended run and a fan-out run. The mode decides
only how the Build stage of `feature-core` spends agents.

**Goals.** One source for each stage's rules; a `session` mode for `feature-core` that matches the `pipeline` mode
everywhere except Build; a measured comparison before the default moves.

**Non-goals.** Removing fan-out; changing review, gates or Fix; a new fence.

**Anti-goals** (a failure even if everything else works):
- the two modes produce different gates, review or PR contracts;
- a stage rule exists in a skill and again, reworded, in a workflow prompt;
- the default changes without the trial's numbers.

## The stage skills

| Skill | From today's prompt | Carries | Next |
|---|---|---|---|
| `dark-factory:plan` | `feature-auto` plan / replan | end-to-end slices (not layers), `files[]` per slice, test plan by pyramid level, `blockedBy`, the size threshold, bd subtasks under the phase task (`openspec-to-beads` stays for a whole approved change) | `build-tdd` |
| `dark-factory:build-tdd` | `feature-core` `implPrompt`, `feature-lite` build | one slice: read the subtask (`bd show`), RED → GREEN → REFACTOR with the Superpowers TDD skill, scoped tests only, the project's standards and migration rule, assumptions recorded | `integrate` |
| `dark-factory:integrate` | `integratePrompt`, `finalGatesPrompt` | scoped tests + lint of the batch, one commit per subtask, `bd close`; after the last slice, the full gate once (`testCmd`, `lintCmd`, frontend lane) with root-cause fixes | `reviewer` role, then `wrap` |
| `dark-factory:wrap` | `feature-lite` wrap, `feature-auto` integrate wrap-up | bd note (never close the phase task), project documents sync, `tasks.md` ticks, the PR description's three sections | `merge-feature.sh` after CI |

Rules for the split:
- **Know-how in the skill, mechanics in the script.** A workflow prompt keeps only what belongs to the run: paths,
  the run's subtask id, "these are your files, other agents write the others", "do not commit, the integrator does",
  output schemas, caps. Everything that is also true in a person's session moves to the skill.
- **The generic method stays in Superpowers.** `build-tdd` calls `test-driven-development` for the method and adds
  only the factory's parts. Without Superpowers it still reads as a complete procedure (the canon `CLAUDE.md` already
  says "follow the same steps by hand").
- **Each skill ends with its next step** (the table's last column), so a session following them needs no workflow to
  know the order. Anything that must happen is enforced where it is today (`merge-feature.sh`, the guard), not by
  the skill text.

How a workflow agent gets a skill: through its role. A new role, `builder` (`agents/builder.md`), preloads
`build-tdd`, `integrate` and `wrap`, and `tech-lead` adds `plan` to its preloaded skills; the implementers,
integrators, gates, Fix and wrap-up steps run as `builder`. Preloading was checked (task 1.1): an agent started as a
plugin role has the full text of the role's skills in its context, not only their names. The prompts then name the
skill step ("by the integrate skill") and give the run's facts; where a prompt narrows a skill ("do not commit, the
integrator does"), the role says the task wins.

## The build mode

`feature-core` reads `args.buildMode` (`session` | `pipeline`; default from the project file, then `pipeline`).

```
pipeline (today)                         session
graph                                    graph
wave 1: impl ×N (parallel, disjoint)     build agent A: for each subtask in dependency order
        integrate#1                         build-tdd → integrate (commit, bd close)
wave 2: impl ×M                          build agent B: next subtasks (fresh context), same loop
        integrate#2                      …
gates-final                              gates-final
review (combined or lenses)              review (combined or lenses)       ← identical
fix                                      fix                               ← identical
```

- **Order.** The same graph and the same `blockedBy` order. A wave in `pipeline` is a stretch of the queue in
  `session`; the disjointness check is not needed (one writer), so overlapping files never force a sequential wave.
- **Context cuts.** One build agent takes at most `sessionChunk` subtasks (default 4), then a new agent continues
  from the committed branch. This is the guidance's own exception ("measurable degradation from context bloat") made
  into a fixed rule until the trial says otherwise.
- **Failure.** A subtask the build agent cannot finish stops the chunk with its status; the next chunk starts only
  if the failed subtask blocks nothing. The result's `error` values are the same as in `pipeline`.
- **Cost cap.** `session` needs 1 (graph) + ⌈tasks / sessionChunk⌉ + 1 (gates) + review + 1 (fix): an 8-subtask phase
  takes about 7 agents against about 15 in `pipeline`. The `maxAgents` checks use the mode's own count.
- **Resume.** Unchanged: closed subtasks are skipped, the next chunk starts at the first open one.
- **`feature-lite`** already is session mode for a small change (one build agent, one wrap agent); it changes only by
  pointing its prompts at `build-tdd`, `integrate` and `wrap`.

## Where the setting lives

| Option | For | Against |
|---|---|---|
| `buildMode` in `.claude/factory/feature-pipeline.json` (proposed) | the file already holds every feature-pipeline setting; `/dark-factory:feature` passes it on; a per-run override is a plain argument | not visible to hooks (none needs it) |
| `FACTORY_MODE` in `.claude/fences.env` | one file for "how this factory works" | the file is fenced (edited only with the human's yes) and read by the guard and quota hooks, none of which use the mode; a working setting would need the fence dialog |

The interactive route needs no setting: a person's session runs the stage skills itself, and `pipeline` is a choice
to launch the workflow.

## The interactive route

Step 0 of the canon `CLAUDE.md` gets one row and one sentence:

| Task type | Mandatory skills |
|---|---|
| Approved phase → code in this session | `dark-factory:plan` → `dark-factory:build-tdd` per slice → `dark-factory:integrate` → `reviewer` role → `dark-factory:wrap` |

"Launch the feature pipeline only for a run you leave alone; `--mode pipeline` only for a wide phase of independent
slices."

`size-task` adds the mode to its verdict when it sees a phase: `session` unless the slices are independent and wide
enough that parallel wall time matters.

## Trial

One real phase of a project (4–8 subtasks, a mix of backend and tests), built twice from the same base commit on two
branches, once per mode, with the same models and caps. Compared:

| Measure | Source |
|---|---|
| tokens (input, cache write, cache read, output) | `scripts/analytics.py` (pipeline vs direct split) |
| wall time of Build and of the whole run | the run's log |
| fix rounds, review blockers, final gate red/green | the run's result |
| the owner's read of the two diffs | the owner |

Decision rule: `session` becomes the default when it is not worse on blockers and gates and is cheaper or faster; a
mixed result keeps `pipeline` as the default and `session` as an option. One phase is an anecdote; the series in
`analytics/` keeps counting afterwards.

## Risks

- **One build agent drifts on a long phase.** Bounded by `sessionChunk` and by the full gate and review after Build.
- **A skill not loaded in a workflow agent.** Checked in task 1.1: the role's preloaded skills arrive in full. A
  project that overrides `builder` with its own `.claude/agents/builder.md` keeps the preload only if its file lists
  the skills.
- **The skills fork from the scripts again.** The dry run checks that the build steps run as `builder`
  (`DRYRUN_EXPECT_TYPES`); the review of this change checks no rule is left in both places.

## What others do (sources checked 2026-10-26)

| Who | Writers | Fan-out for | Merge |
|---|---|---|---|
| Anthropic, multi-agent research system | — (research) | parallel search subagents; ~15x the tokens of chat | the lead synthesises; "most coding tasks involve fewer truly parallelizable tasks than research" |
| Claude Code agent teams, workflows | one per file set | research, review; teams "more effective" as a single session for "sequential tasks, same-file edits, or work with many dependencies"; ~7x tokens | the lead; workflows' write pattern is a migration, each file in its own copy |
| Superpowers `subagent-driven-development` | one at a time | a fresh implementer per task, **sequential** ("never dispatch multiple implementation subagents in parallel"), review per task | the controller; whole-branch review at the end |
| Cognition (Devin), 2025 and 2026 posts | single-threaded writes | read-only helpers, a clean-context reviewer; managed Devins for breadth work (migrations, QA, audits) | one PR per child, the coordinator resolves conflicts |
| Cursor 2–3, OpenAI Codex | one per attempt | independent attempts at the same task (best-of-n), each in its own worktree or container | a human picks |
| OpenHands | one per attempt | best-of-n scored by a trained critic (SWE-bench Verified 60.6% → 66.4% at N=5) | the critic picks |
| GitHub Copilot coding agent | one | one task = one branch = one PR; parallel only across independent tasks | a human reviews each PR; CodeQL, secret scan and self-review before the PR |
| Factory.ai Missions | — | parallel execution is still "an open question" they are testing | milestones validated one by one |

Where it converges: fan-out for read-only work (research, exploration, review with a clean context) and for
independent attempts or independent units of breadth work; a **single writer** for one coupled feature. Disjoint
`files[]` stop overwrites but not conflicting implicit decisions between parallel writers (Cognition's point), which
is what the integrator and the review in `pipeline` are left to catch. The factory's tail — single integrator, full
gate, fresh-context review lenses, Fix — already matches what the others converge on; only the parallel Build does
not. This is why `session` is the recommended default once the trial confirms it, and why best-of-n (several
attempts at one hard slice, a critic or the owner picks) is the fan-out worth a later, separate change.

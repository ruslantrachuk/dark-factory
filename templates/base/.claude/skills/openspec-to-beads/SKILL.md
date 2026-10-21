---
name: openspec-to-beads
description: >
  Turns an approved OpenSpec change (openspec/changes/r{N}-<name>/) into a bd (beads) task graph:
  one epic per branch, one child task per tasks.md phase, dependencies, acceptance, owner questions.
  Use when a change is approved for implementation: "convert the spec to beads", "create tasks from
  the change", "put r12-foo into the queue", "implement this change".
allowed-tools: "Read,Bash(bd:*),Bash(git:*)"
version: "2.0.0"
license: "MIT"
---

# openspec-to-beads — approved change → bd queue

> Canonical template (templates/base). Needs no configuration.
> Inspired by the `openspec-to-beads` skill in [lucastamoios/celeiro](https://github.com/lucastamoios/celeiro);
> this version is written from scratch for the factory layout.

OpenSpec says **what** is agreed; bd holds the **state of execution**. This skill moves an approved
change into the queue once, so that `bd ready` shows exactly the next phase to work on and nothing
from the proposal is lost on the way.

## When to run

- The change is approved: proposal, design (if any) and `tasks.md` are reviewed, and the
  **Interaction surfaces** section is confirmed (`openspec/README.md` §0). No confirmed surfaces —
  stop and say so; the change is not ready.
- Not for drafting or editing proposals, and not for a change that already has an epic in bd
  (search first: `bd list --json | jq` or `bd search "<change dir name>"`; if it exists, update it).

## Inputs

- `openspec/changes/r{N}-<name>/` — `proposal.md`, `design.md` (optional), `tasks.md`, `specs/**`.
- `openspec/CURRENT_TRAIN` — the `r{N}` line; never guess it.
- The OpenSpec CLI is not used: OpenSpec here is a folder convention (the `openspec` skill §CLI).

### Worktree check (do this first)

In a git worktree the local bd database starts empty, and the first `bd` write can export that
emptiness over the tracked `.beads/issues.jsonl`. Before creating anything:

```bash
git checkout -- .beads/issues.jsonl   # only if it is already wiped
bd import && bd list | head           # the queue must be visible here
```

## What to create

| bd object | From | Notes |
|---|---|---|
| **Epic** (`--type=epic`), one per branch/PR | the change, or a block of phases that ships together | title `[r{N}-<name>] <outcome>`; `--acceptance` = observable facts from the proposal's "Acceptance criteria" |
| **Phase task** (`--type=task --parent <epic>`) | each phase in `tasks.md` | title `Phase <K>: <what>`; description ends with the marker line `OPENSPEC: openspec/changes/r{N}-<name> PHASE: <K>` |
| **Dependency** (`bd dep add <later> <earlier>`) | phase order and real data/API needs | sequential phases block the next one; independent phases stay parallel |
| **Owner question** (`--type=decision`, or `task` with label `needs-owner`) | "Open questions" in the proposal | description says "needs a human decision — not for the agent"; blocks the phases it affects |
| **Gap task** (`--type=task`, `discovered-from` the epic) | things the change needs but `tasks.md` misses: migration, docs/user guide, config, rollout | only real gaps; mention each in the report |

Rules:

- **One epic = one branch = one PR** (`CLAUDE.md` §Operating contract). Several epics under one train
  are fine. The branch is `r{N}/<type>-<slug>-<epic-id>`; the bd id at the end lets `merge-feature.sh`
  close the right task.
- **Phases stay phases.** Do not split a phase into micro-tasks or merge phases; if a phase is clearly
  too big (`openspec/README.md`: over ~5 minutes of TDD), say so in the report instead of re-planning.
- **Priorities.** Default P2. The critical path of the epic gets P1. If the proposal has a cut order
  ("drop first if short on time"), later cuts get lower priority. Do not mark everything P0.
- **Language.** Titles and descriptions in the project language (`CODING_STANDARDS.md` §Project
  language); ids, labels and markers in English.
- **Do not set `scale:*` labels or `SPEC:` markers** — the tier for the night loop is a human decision.
- **Keep the why.** Each phase task's description carries one or two lines of rationale from the
  proposal or design, not just the checklist line.

## Procedure

1. Read the change; list phases, acceptance criteria, open questions, cut order.
2. Check for an existing epic; run the worktree check.
3. Show the planned graph to the human as a table (epic → phases → deps → questions → gaps) and
   wait for "yes". Use `bd create --dry-run` if unsure about a command.
4. Create: epic, then phase tasks with `--parent`, then `bd dep add`, then questions and gaps.
   Use `--silent` to capture ids for the next commands.
5. Verify: `bd show <epic>` lists all phases; `bd ready` shows the first phase (or the blocking question).
6. Report: ids created, the first ready task, gaps found, phases that look too big.

```bash
epic=$(bd create "[r12-export] CSV export of reports" --type=epic -p 1 --silent \
  --acceptance "A user downloads the monthly report as CSV from the Reports page; totals match the screen")
p1=$(bd create "Phase 1: CSV serializer for report rows" --parent "$epic" -p 1 --silent \
  -d "Rows → CSV with the same rounding as the UI (design.md: rounding).
OPENSPEC: openspec/changes/r12-export PHASE: 1")
p2=$(bd create "Phase 2: download endpoint" --parent "$epic" -p 1 --silent \
  -d "GET /reports/{id}.csv streams the serializer output.
OPENSPEC: openspec/changes/r12-export PHASE: 2")
bd dep add "$p2" "$p1"
bd create "Owner: include archived rows in the export?" --type=decision --silent \
  -d "Open question from proposal.md — needs a human decision, not for the agent." | xargs -I{} bd dep add "$p2" {}
```

## Don'ts

- Don't create tasks before the human has seen the graph.
- Don't copy `tasks.md` line by line into dozens of tasks.
- Don't drop tests: if a phase has no test step, flag it in the report.
- Don't commit or push; the queue file is committed with the feature work (`.beads/README.md`).

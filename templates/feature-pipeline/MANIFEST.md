# feature-pipeline — module manifest

> **A feature pipeline run inside a development session**: the session launches a Workflow script that takes one bd task
> from a ready requirements source to a committed, reviewed branch — plan, critic, parallel build, review, full gates,
> devlog. The pipeline never merges and by default never pushes: it stops before the PR, and the session merges after
> the owner's "yes" with `scripts/merge-feature.sh <branch> --accepted-by "<name>"`. Installed **on top of base**
> (charter, beads, openspec, hooks and the merge script come from there).
>
> **Status: experimental.** The db lane and the frontend lane are
> exercised only by projects that have them. Split-on-one-branch is not yet measured against one full run per chunk on
> the same task.

## Contents

| Artifact | What it does |
|---|---|
| `.claude/workflows/feature-auto.ts` | entry point: Setup (branch + worktree) → triage (small task → `feature-lite`) → Plan → overlap check → size gate / Split → Critic → Bridge (bd subtasks) → Build (`feature-core`) → Integrate (merge the base, full gates, charter docs, devlog) |
| `.claude/workflows/feature-core.ts` | the bd subtask graph of one run: waves by dependencies, disjoint files in parallel, a single integrating writer, review lenses (test pyramid / invariants / simplify), Fix |
| `.claude/workflows/feature-lite.ts` | the small path: one agent builds the whole feature by TDD with full gates, one agent does the wrap-up (bd note, charter docs, devlog) |
| `.claude/workflows/dryrun.mjs` | runs the scripts with fake agents — syntax and control flow without spending tokens |
| `.claude/workflows/README.md` | run rules and the engine rules the scripts rely on |

## Requirements

- Claude Code with the **Workflow** tool; the development session works in its own git worktree (a `claude remote-control`
  session on the server, or an attended session).
- A deployed base: `bd` (beads), `openspec/CURRENT_TRAIN` (plus `openspec/INTEGRATION_BRANCH` when the train has an
  integration branch), `scripts/merge-feature.sh`,
  `scripts/bd-export.sh`, the pre-push gate, `devlog.md` with its template.
- A Python venv with `pytest` and `ruff` (the default gate); Docker for the db lane (`dbTests: true`);
  `gh` only if a run may open the PR itself (`stopBeforePR: false`).
- Shared project permissions in `~/.claude/settings.json` (`additionalDirectories` + `Bash`): the run's worktree is
  created inside the session's tree, and without them every file edit asks for permission (base `CLAUDE.md`, worktree trap 5).

## How a session launches it

The session calls the **Workflow** tool with `scriptPath` pointing into **its own tree**:
`<session tree>/.claude/workflows/feature-auto.ts`. Workflow refuses a script path outside what the session can read,
so a path into another checkout fails; the nested `feature-core.ts` / `feature-lite.ts` are taken from the same directory
by default. Nesting is one level: session → `feature-auto` → `feature-core` / `feature-lite`. The child scripts do not
call `workflow()`, and `feature-auto` itself is launched by the session, not from another workflow script.

Arguments (`args`, an object; the tool may deliver it as a JSON string — the scripts parse both):

| Argument | Required | Meaning |
|---|---|---|
| `request` | yes | what to build, in one or two sentences |
| `stamp` | yes | a unique suffix (e.g. `20261021-p3`); scripts cannot call `Date.now()` — keep the same value on resume |
| `releaseLine` | yes | `r{N}` from `openspec/CURRENT_TRAIN`; never guessed |
| `bdId` | yes | the run's parent bd task (a phase task or a bug), the full bd id `<prefix>-<hash>[.N]`; subtasks become its children, the branch ends with this id (a custom `slug` gets `-<bdId>` appended) |
| `changeDir` + `phase` | one source | an approved OpenSpec change (path from the repo root) and the `tasks.md` phase number |
| `specPath` | one source | absolute path of a ready spec |
| (neither) | — | the description of the bd task is the source (a bug with a repro) |
| `baseBranch` | no | `main` or the train integration branch from `openspec/INTEGRATION_BRANCH` |
| `path` | no | `'lite'` / `'full'` — skip triage |
| `allowMigrations`, `dbTests`, `dbShards` | no | a migration allowed by the spec; run the db lane (Docker); split a db lane longer than 600 s |
| `root` | no | the tree whose bd store the session uses; default — the session's tree |
| `appSubdir` | no | where the code lives inside the tree: `<tree>/<appSubdir>/src`, `/tests`, `/alembic`, `/.venv`. Default `app` (base layout); `''` for code at the tree root. Passed on to `feature-core` / `feature-lite` |
| `venv` | no | absolute path of the venv; default `<root>/<appSubdir>/.venv` |
| `maxRounds` | no | build waves in `feature-core`, default 6; a plan that needs more is a phase to split |
| `allowOverlap`, `manualChunks`, `reviewDims`, `ignoreSizeGate`, `stopBeforePR` | no | see the input comment at the top of `feature-auto.ts` |

Do not pass `appDir`: the run creates its worktree at `<session tree>/.claude/worktrees/fab-<slug>`. A path outside the
session's tree is rejected (`error: 'appDir outside session dir'`).

```json
{ "request": "[r12] Phase 3 — outbound delivery log", "stamp": "20261021-p3", "releaseLine": "r12",
  "bdId": "proj-t4sk.3", "baseBranch": "develop", "venv": "/srv/<project>/app/.venv",
  "changeDir": "openspec/changes/r12-example-change", "phase": 3, "allowMigrations": true, "dbTests": true }
```

"Run it at night" means the session schedules this Workflow call for a later time (a scheduled task, `send_later` or
`CronCreate`). The base quota guard pauses work near the subscription limit, and the session books its own continuation.

## How to read the result

The harness status of a run is almost always **"completed"** — it says the script finished, not that the feature is
built. The outcome is the **`error` field** of the returned object; callers read `error`, never the status:

- `error: null` — the branch `r{N}/<slug>` is committed in the run's worktree, gates are green, the devlog entry is
  written. The session reports the branch and the assumptions to the owner and, after a "yes", runs
  `scripts/merge-feature.sh <branch> --accepted-by "<name>"` with the name of the person who said "accepted" (the
  script refuses to merge without it and records it on the PR and in the merge commit). If CI cannot run (Actions
  disabled: billing, limits, an incident), the owner may say to add `--skip-ci "<reason>"`: the local gate runs instead
  and the merge is marked as made without CI; refused at `FENCE_LEVEL=team`.
- **Which bd task the merge closes.** `merge-feature.sh` closes a task only when an `r{N}/…` branch ends in the full bd
  id, `-<prefix>-<id>[.N]`, with the project's prefix (from `.beads/issues.jsonl` or `.beads/config.yaml`); any other
  branch gives "no id — close by hand". `scripts/merge-feature.sh <branch> --print-bd-id` prints the id it would use.
  `feature-auto` always ends the branch with `-<bdId>`. `feature-lite` launched by hand without `bdId` names the
  branch plainly `r{N}/feat-lite-<stamp>`, which carries no id, so the merge closes nothing (a stamp like
  `20261021-p3` is not taken for a task). Its Wrap step creates the bd task and reports the id in `wrap.details`; close
  that task by hand after the merge.
- any other value — the run stopped or finished incomplete; the object also carries `branch` and the failed step's
  output. Typical values: `overlaps in-flight branch` (merge the other branch first, or `allowOverlap: true`),
  `plan failed`, `migration required but not allowed`, `phase too large — split proposed`,
  `decomposition rejected by critic`, `chunk <key> failed`, `core failed: …`, `integrate failed`, `budget exhausted`
  (the session set a token target for the run and it is spent — resume later), `incomplete: …`
  (subtasks not implemented, critical review blockers left). The full list is in the result comment at the top of each
  script.

## Resume

A run that stopped on a transient failure (quota pause, spent token budget, a hung command, a red gate fixed by hand) is resumed with the
Workflow tool's `resumeFromRunId` and the **same args** (same `stamp`). Setup, Bridge and the core graph are idempotent:
an existing branch and worktree are reused, existing bd subtasks are not duplicated, closed subtasks are not rebuilt.

## Setup

1. Copy `.claude/workflows/` on top of a deployed base.
2. Fill in the placeholders in the agent prompts: `<project>`, `<project surfaces>` (base `openspec/README.md` §0),
   `<i18n file>` (message catalog), `<product invariants doc>`, `<frontend dir>` (or drop the frontend lane from
   `feature-lite`), `<umbrella card id>`, `<test shard globs>`.
3. Code layout: nothing to edit for base's layout (`app/src`, `app/tests`, venv in `app/.venv`) — `appSubdir`
   defaults to `app`. Code at the tree root — the session passes `"appSubdir": ""` on every launch (record it in the
   project's `CLAUDE.md` next to the launch instructions). Another stack — replace the gate commands (`TEST_FAST`,
   `LINT` in `feature-auto`/`feature-core`; `TEST_CMD`, `LINT_CMD` in `feature-lite`).
4. Check that `.claude/worktrees/` is in the project `.gitignore` (base's `.gitignore` has it; a project that kept its
   own `.gitignore` at deployment adds the line).
5. Run the dry run from the project tree for all three scripts (see `README.md` in the workflows directory).
6. Record the module in the factory registry (the project's "Contents" column) and in the devlog.

## Design notes

- **Split on one branch.** A phase wider than the threshold (more than 8 tasks or 25 files), or one the critic does not
  accept in three rounds, is split into 2–4 end-to-end slices built in sequence on one branch by `feature-lite`
  (`skipWrap`); review and integration run once over the whole branch. `manualChunks: true` returns the split to the
  caller instead.
- **Overlap check.** After planning, the plan's code files are compared with unmerged local branches; an overlap stops the
  run until the shared layer is merged.
- **Review severity = review contract** (`docs/review-contract.md`): `critical` stays a blocker and makes the run
  incomplete, `critical` + `major` are fixed in the branch, `minor` goes to the devlog.
- **Agent models by full id** (`claude-sonnet-5-5`, `claude-opus-5-5`): mechanics and workers on Sonnet; plan, critic and
  review on Opus. The session's model is not inherited by subagents.
- **Surface gate**: a user-visible feature without an "Interaction surfaces" section in the proposal stops at Plan.
- **One heavy gate per run**: the rounds run scoped tests; Integrate runs the fast suite, ruff and (with `dbTests`) the
  db lane once, in shards when it exceeds the 600 s command limit.

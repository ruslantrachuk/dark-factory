# feature-pipeline — module manifest

> **A feature pipeline run inside a development session**: the session launches a Workflow that takes one bd task
> from a ready requirements source to a committed, reviewed branch — plan, critic, parallel build, review, full gates,
> the PR description. The pipeline never merges and by default never pushes: it stops before the PR, and the session merges once CI
> is green, with `scripts/merge-feature.sh <branch>`. The workflows ship in the
> **dark-factory plugin** (`dark-factory:feature-auto`, `…:feature-core`, `…:feature-lite`); this module is the
> project-side part: one settings file and the launch rule. Installed **on top of base** (project documents, beads, openspec,
> hooks and the merge script come from there).
>
> **Status: experimental.** The db lane and the frontend lane are
> exercised only by projects that have them. Split-on-one-branch is not yet measured against one full run per chunk on
> the same task.

> **Seam:** execution queue = beads (`bd`); agent runtime = the Claude Code Workflow tool. To use another queue, rewrite the `bd` calls in the plugin workflows (Bridge in `feature-auto.js`, `feature-core.js`, the wrap-up in `feature-lite.js`).

## Contents

| Artifact | What it does |
|---|---|
| `.claude/feature-pipeline.json` (this module) | the project's settings every launch carries: `appSubdir`, `testCmd`, `lintCmd` (`{tree}` = the run's working tree), `frontendDir`, `i18nFile`, `invariantsDoc`, `surfaces`, `models`, `maxAgents`. Keys left out take the defaults (base layout: pytest and ruff under `app/`; models inherited from the session; 40 agents per run) |
| plugin command `/dark-factory:feature` | reads the settings file, asks for what the task does not give, and launches `dark-factory:feature-auto` (or `feature-lite`) with the settings plus the run's arguments |
| plugin `workflows/feature-auto.js` → `dark-factory:feature-auto` | entry point: Setup (branch + worktree) → triage (small task → `feature-lite`) → Plan → overlap check → size gate / Split → Critic → Bridge (bd subtasks) → Build (`feature-core`) → Integrate (merge the base, full gates, project documents, the PR description) |
| plugin `workflows/feature-core.js` → `dark-factory:feature-core` | the bd subtask graph of one run: waves by dependencies, disjoint files in parallel, a single integrating writer, review lenses (test pyramid / invariants / simplify), Fix |
| plugin `workflows/feature-lite.js` → `dark-factory:feature-lite` | the small path: one agent builds the whole feature by TDD with full gates, one agent does the wrap-up (bd note, project documents, the PR description) |
| plugin `workflows/dryrun.mjs`, `workflows/README.md` | stub runs with fake agents (control flow without tokens); run rules and the engine rules the scripts rely on ([README](../../plugins/dark-factory/workflows/README.md)) |

## Requirements

- Claude Code with the **Workflow** tool and the **dark-factory plugin** enabled (base enables it); the development session works in its own git worktree (a `claude remote-control`
  session on the server, or an attended session).
- A deployed base: `bd` (beads), `scripts/merge-feature.sh`, the pre-push gate.
- A Python venv with `pytest` and `ruff` (the default gate); Docker for the db lane (`dbTests: true`);
  `gh` only if a run may open the PR itself (`stopBeforePR: false`).
- Shared project permissions in `~/.claude/settings.json` (`additionalDirectories` + `Bash`): the run's worktree is
  created inside the session's tree, and without them every file edit asks for permission (base `CLAUDE.md`, worktree trap 5).

## How a session launches it

The owner types `/dark-factory:feature <task>`; the command reads `.claude/feature-pipeline.json` and calls the
**Workflow** tool by name — `Workflow({name: "dark-factory:feature-auto", args})` — with the run's arguments plus the
file's keys. A session (or a scheduled task) may make the same call directly. The scripts find the project at run time (the
session's git top level), not from where the plugin is installed. `feature-auto` calls its children by name
(`workflow('dark-factory:feature-core', …)`); nesting is one level: session → `feature-auto` → `feature-core` /
`feature-lite`. A project that needs its own edited copy keeps it inside its tree and passes `coreScript` /
`liteScript` (or launches it by `scriptPath`); that copy no longer follows the canon.

Arguments (`args`, an object passed as JSON values; the scripts also accept a JSON-encoded string):

| Argument | Required | Meaning |
|---|---|---|
| `request` | yes | what to build, in one or two sentences |
| `stamp` | yes | a unique suffix (e.g. `20261021-p3`); scripts cannot call `Date.now()` — keep the same value on resume |
| `bdId` | yes | the run's parent bd task (a phase task or a bug), the full bd id `<prefix>-<hash>[.N]`; subtasks become its children |
| `slug`, `trackerId`, `type` | no | the change key of the branch: `<type>/<trackerId>-<slug>` with a tracker ID (`DMP-123`, `123`), `<type>/<slug>` without; `type` is `feat\|fix\|ui\|refactor\|chore\|docs` (default `feat`); a phase of a spec without sub-cards ends the slug with `-p<K>`; default slug `auto-<stamp>` |
| `changeDir` + `phase` | one source | an approved OpenSpec change (path from the repo root) and the `tasks.md` phase number |
| `specPath` | one source | absolute path of a ready spec |
| (neither) | — | the description of the bd task is the source (a bug with a repro) |
| `baseBranch` | no | the base branch, default `main` |
| `path` | no | `'lite'` / `'full'` — skip triage |
| `allowMigrations`, `dbTests`, `dbShards` | no | a migration allowed by the spec; run the db lane (Docker); split a db lane longer than 600 s |
| `root` | no | the tree whose bd store the session uses; default — the session's tree |
| `appSubdir` | no | where the code lives inside the tree: `<tree>/<appSubdir>/src`, `/tests`, `/alembic`, `/.venv`. Default `app` (base layout); `''` for code at the tree root. Passed on to `feature-core` / `feature-lite` |
| `venv` | no | absolute path of the venv; default `<root>/<appSubdir>/.venv` |
| `maxRounds` | no | build waves in `feature-core`, default 6; a plan that needs more is a phase to split |
| `maxAgents` | no | agent calls the whole run may make, children included; default 40 (`feature-core` alone 30, `feature-lite` alone 5). The cost cap of an unattended run: a token target exists only when a human set one. Reached → `error: 'agent limit reached'` |
| `models` | no | `{plan, implement, review}` — a model id per role; a role left out inherits the session's model (from `.claude/feature-pipeline.json`) |
| `testCmd`, `lintCmd` | no | the gate commands, `{tree}` = the run's working tree; default pytest + ruff under `<tree>/<appSubdir>` (from `.claude/feature-pipeline.json`) |
| `frontendDir`, `i18nFile`, `invariantsDoc`, `surfaces` | no | a frontend with its own CI lane; the message catalog; the product invariants for review; the user-facing surfaces (from `.claude/feature-pipeline.json`) |
| `allowOverlap`, `manualChunks`, `reviewDims`, `ignoreSizeGate`, `stopBeforePR`, `coreScript`, `liteScript` | no | see the input comment at the top of `feature-auto.js` |

Do not pass `appDir`: the run creates its worktree at `<session tree>/.claude/worktrees/fab-<slug>`. A path outside the
session's tree is rejected (`error: 'appDir outside session dir'`).

```json
{ "request": "Phase 3 — outbound delivery log", "stamp": "20261021-p3", "trackerId": "DMP-123",
  "slug": "delivery-log", "bdId": "proj-t4sk.3", "baseBranch": "develop", "venv": "/srv/my-app/app/.venv",
  "changeDir": "openspec/changes/delivery-log", "phase": 3, "allowMigrations": true, "dbTests": true }
```

"Run it at night" means the session schedules this Workflow call for a later time (a scheduled task, `send_later` or
`CronCreate`). The plugin's quota guard pauses work near the subscription limit, and the session books its own continuation.

## How to read the result

The harness status of a run is almost always **"completed"** — it says the script finished, not that the feature is
built. The outcome is the **`error` field** of the returned object; callers read `error`, never the status:

- `error: null` — the branch `<type>/<ID>-<slug>` (or `<type>/<slug>`) is committed in the run's worktree, gates are
  green, and the result carries the PR description (`prBody`). The session reports the branch, the assumptions and the
  description to the owner, opens the PR with it and, once CI is green, runs `scripts/merge-feature.sh <branch>` (the
  script refuses to merge without the three sections). If CI cannot run (Actions disabled: billing, limits, an
  incident), the owner may say to add `--skip-ci "<reason>"`: the local gate runs instead and the merge is marked as
  made without CI; refused at `FENCE_LEVEL=team`.
- **Which bd task the merge closes.** `merge-feature.sh` finds it from the branch: the tracker ID equal to a task's
  `external_ref`, or the slug as an epic's `change:<slug>` label (with `phase:<K>` for a `-p<K>` branch). No match or
  several gives "close it by hand" and does not fail the merge. `scripts/merge-feature.sh <branch> --print-bd-id`
  prints the id it would use. `feature-lite` launched by hand without `bdId` names the branch `<type>/lite-<stamp>`
  unless `slug` is given; its Wrap step creates the bd task and reports the id in `wrap.details`; close that task by
  hand after the merge.
- any other value — the run stopped or finished incomplete; the object also carries `branch` and the failed step's
  output. Typical values: `overlaps in-flight branch` (merge the other branch first, or `allowOverlap: true`),
  `plan failed`, `migration required but not allowed`, `phase too large — split proposed`,
  `decomposition rejected by critic`, `chunk <key> failed`, `core failed: …`, `integrate failed`, `budget exhausted`
  (the session set a token target for the run and it is spent — resume later), `agent limit reached` (`maxAgents` is
  used up — resume with a larger one), `incomplete: …`
  (subtasks not implemented, critical review blockers left). The full list is in the result comment at the top of each
  script.

## Resume

A run that stopped on a transient failure (quota pause, spent token budget or agent cap, a hung command, a red gate fixed by hand) is resumed with the
Workflow tool's `resumeFromRunId` and the **same args** (same `stamp`). Setup, Bridge and the core graph are idempotent:
an existing branch and worktree are reused, existing bd subtasks are not duplicated, closed subtasks are not rebuilt.

## Setup

1. The dark-factory plugin is enabled (base's `.claude/settings.json` does it); `claude plugin list` shows it, and the
   session lists `dark-factory:feature-auto` among its workflows.
2. Copy `.claude/feature-pipeline.json` from this module into the project and fill it in: the code layout
   (`appSubdir`: `app` for base, `""` for code at the tree root), the gate commands for another stack (`testCmd`,
   `lintCmd`; leave them out for pytest + ruff), `frontendDir` (leave it out when there is no frontend lane),
   `i18nFile`, `invariantsDoc`, `surfaces` (base `openspec/README.md` §0), `maxAgents`, and `models` only to pin
   roles (e.g. a cheaper model for `implement`). Record in the project's `CLAUDE.md`, next to the launch rule, that runs
   start with `/dark-factory:feature` (or pass these keys when called directly).
3. Check that `.claude/worktrees/` is in the project `.gitignore` (base's `.gitignore` has it; a project that kept its
   own `.gitignore` at deployment adds the line).
4. Dry run the three scripts from the canon checkout (`plugins/dark-factory/workflows/README.md`), with the project's
   settings in the args.
5. Record the module in the factory registry (the project's "Contents" column) and in the PR description of the setup.
6. A project deployed before the workflows moved into the plugin: delete its `.claude/workflows/feature-*.ts`,
   `dryrun.mjs` and `README.md` (keep the values it filled into the placeholders — they become the settings file).

## Design notes

- **Split on one branch.** A phase wider than the threshold (more than 8 tasks or 25 files), or one the critic does not
  accept in three rounds, is split into 2–4 end-to-end slices built in sequence on one branch by `feature-lite`
  (`skipWrap`); review and integration run once over the whole branch. `manualChunks: true` returns the split to the
  caller instead.
- **Overlap check.** After planning, the plan's code files are compared with unmerged local branches; an overlap stops the
  run until the shared layer is merged.
- **Review severity = review contract** (`docs/review-contract.md`): `critical` stays a blocker and makes the run
  incomplete, `critical` + `major` are fixed in the branch, `minor` goes to the PR description's open questions.
- **Models are a setting, not code.** With no `models`, every agent inherits the session's model. A project pins roles
  in the settings file by full id (e.g. a stronger model for `plan` and `review`, a cheaper one for `implement`).
- **Surface gate**: a user-visible feature without an "Interaction surfaces" section in the proposal stops at Plan.
- **One heavy gate per run**: the rounds run scoped tests; Integrate runs the fast suite, ruff and (with `dbTests`) the
  db lane once, in shards when it exceeds the 600 s command limit.

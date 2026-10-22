# Feature pipeline workflows (dark-factory plugin)

> Workflow scripts the development session launches to take one bd task from a spec or an OpenSpec phase to a
> committed, reviewed branch. They ship with the plugin and register as `dark-factory:<meta.name>`; the
> project-side setup is the `feature-pipeline` module ([templates/feature-pipeline/MANIFEST.md](../../../templates/feature-pipeline/MANIFEST.md)),
> which has the full argument table.

| File | Registered as | Role |
|---|---|---|
| `feature-auto.js` | `dark-factory:feature-auto` | entry point: branch + worktree → triage (small → `feature-lite`) → plan → overlap check → size gate / split → critic → bd subtasks → `feature-core` → integrate (merge the base, full gates, project documents, the PR description). Stops before the PR |
| `feature-core.js` | `dark-factory:feature-core` | the run's bd subtask graph: waves, parallel implementation on disjoint files, a single integrating writer, review lenses, fix |
| `feature-lite.js` | `dark-factory:feature-lite` | the small path: one build agent (TDD + full gates + commit), one wrap-up agent (bd note, project documents, the PR description) |
| `dryrun.mjs` | — (not loaded: the plugin loads `*.js` only) | stub run with fake agents — control flow without spending tokens |

## Launch

The usual way is the plugin command: `/dark-factory:feature <task>` reads `.claude/feature-pipeline.json`, asks for
what the task does not give (release line, bd id, source) and launches `dark-factory:feature-auto` (or `feature-lite`)
with the file's settings plus the run's own arguments, so the settings are never re-typed.

By hand: the Workflow tool by name, `args` as an object — the run's own arguments plus the project's settings from
`.claude/feature-pipeline.json` (test and lint commands, frontend dir, message catalog, invariants doc, surfaces,
models, maxAgents):

```
Workflow({ name: "dark-factory:feature-auto", args: {
  "request": "Phase 3 — outbound delivery log", "stamp": "20261021-p3", "trackerId": "DMP-123",
  "slug": "delivery-log", "bdId": "proj-t4sk.3", "changeDir": "openspec/changes/delivery-log", "phase": 3 } })
```

The scripts find the project at run time (the session's git top level), not from where they are installed. Do not pass
`appDir`: the run creates its worktree at `<session tree>/.claude/worktrees/fab-<slug>`. Code at the tree root rather
than in base's `app/` — add `"appSubdir": ""`. Nesting is one level — `feature-auto` calls
`workflow('dark-factory:feature-core', …)` / `workflow('dark-factory:feature-lite', …)`, they call nothing. A project
that keeps its own edited copy passes `coreScript` / `liteScript` (absolute paths inside the session tree).

**Cost cap.** `maxAgents` limits the agent calls of a whole run, children included (defaults: `feature-auto` 40,
`feature-core` 30, `feature-lite` 5). A token target (`budget.total`) exists only when a human typed one ("+500k"), so
an unattended or scheduled run is bounded by `maxAgents` alone. Each stage checks the headroom it needs before it
starts; when it is short, the run stops cleanly with `error: 'agent limit reached'` (or `'budget exhausted'` for a
token target) and `stage`. Every result carries `agentsUsed` and `maxAgents`.

**Models.** `models: {plan, implement, review}` pins a model id per role (plan = plan, critic, split; implement =
mechanics, workers, integration, PR; review = the review lenses). A role left out inherits the session's model —
the Workflow default — so the scripts carry no model ids that age out. Pin full ids, not aliases, when you pin.

**Read `error`, not the status.** The harness reports "completed" for almost every run. `error: null` — the branch is
committed and green; anything else — the run stopped (`overlaps in-flight branch`, `plan failed`, `chunk <key> failed`,
`phase too large — split proposed`, `integrate failed`, `incomplete: …`). Each script lists its values in the result
comment at the top. Resume a stopped run with `resumeFromRunId` and the same args (same `stamp`).

After `error: null` the session shows the branch, the assumptions and the PR description (`prBody`: `## Done`,
`## Decisions`, `## Open questions`) to the owner, opens the PR with it (`gh pr create --draft --body-file -` when the
run stopped before the PR) and, once CI is green and the change is reviewed, runs `scripts/merge-feature.sh <branch>` —
which refuses to merge without the three sections, writes the description into the merge commit and closes the task
after the merge; then `git worktree remove <worktree>`. When CI cannot run (Actions disabled: billing, limits, an
incident) the owner may also say to add `--skip-ci "<reason>"`: the script runs the local gate instead and marks the
merge as made without CI (refused at `FENCE_LEVEL=team`).

The branch is the change key: `<type>/<trackerId>-<slug>` with a tracker ID, `<type>/<slug>` without
(`type`: `feat|fix|ui|refactor|chore|docs`; a phase of a spec without sub-cards: slug ending in `-p<K>`). The merge
finds the task to close from it — the tracker ID equal to the task's `external_ref`, or the slug as the epic's
`change:<slug>` label (and `phase:<K>`); no match or several gives "close it by hand".
`scripts/merge-feature.sh <branch> --print-bd-id` prints the id it would use. `feature-lite` run by hand without
`bdId` names the branch `<type>/lite-<stamp>` unless `slug` is given; the task its Wrap step created
(`wrap.details`) is then closed by hand.

## Dry run

From the canon checkout (`plugins/dark-factory/workflows/`):

```bash
node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true}'
node dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1","bdId":"proj-x"}'
node dryrun.mjs feature-core.js '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}'
# code at the tree root, a hand-run small path without a bd task, a spent token budget, the agent cap:
node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true,"appSubdir":""}'
node dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1"}'
DRYRUN_BUDGET=3000 DRYRUN_EXPECT_ERROR='budget exhausted' node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true}'
DRYRUN_EXPECT_ERROR='agent limit reached' node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true,"maxAgents":8}'
```

The stub exits 1 when the run's `agentsUsed` differs from the number of agent calls it saw, when the calls pass
`maxAgents`, or when `DRYRUN_EXPECT_ERROR` is set and the result's `error` does not contain it (`null` — must succeed).

Pass bare script names: scripts are loaded from next to `dryrun.mjs`, and a nested `workflow('dark-factory:<name>')`
resolves to `<name>.js` there. An optional third argument overrides agent answers by label, which exercises rare
branches — e.g. `'{"integrate#1":{"ok":false,"summary":"red"}}'` (core failure) or
`'{"critic:recheck":{"approved":false,"issues":["x"]}}'` (critic rounds exhausted → split). The stub also fails if a
child script calls `workflow()`.

## Run rules

- **A phase is split automatically.** Wider than the threshold, or not accepted by the critic in three rounds → the
  architect splits it into 2–4 end-to-end chunks, built in sequence on **one branch** by `feature-lite` (`skipWrap`);
  review (`feature-core` with `reviewOnly`) and integration run once for the whole branch. `manualChunks: true` returns
  the split to the caller.
- **Split by end-to-end slices, not by layers**: each chunk, after its commit, works from the entry point to the result
  and is covered by a test at the entry level.
- **Parallel features with shared code — one after another.** An overlap between the plan's code files and an unmerged
  local branch stops the run (`overlaps in-flight branch`); `allowOverlap: true` continues deliberately.
- **The critic checks switch-off, reuse and surfaces**: behaviour with the flag off is defined, existing helpers are
  reused, a user-visible feature has a confirmed "Interaction surfaces" section (base `openspec/README.md` §0).
- **One heavy gate per run; long lanes in shards.** One agent command is limited to 600 s; a longer db lane is split with
  `dbShards`, each shard a synchronous command. Fix in `feature-core` runs only what was touched plus the fast suite;
  Integrate runs the full lanes once.
- **`bd` commands run with `timeout 60`**: bd can hang on a database lock.
- The run's subtasks are children of `bdId` (label `auto-run`) and are closed by the core; the parent stays `in_progress`
  until `merge-feature.sh` closes it after the merge. The queue is the project's local store in the main checkout
  (`bd -C <root>`), outside git: nothing about it is committed.

## Engine rules (do not change)

- `Date.now()` is forbidden in Workflow scripts (it breaks resume) — pass `stamp` as an argument.
- A token target set by the session (Workflow `budget.total`) is checked between stages and build rounds; when it is
  spent the run returns `error: 'budget exhausted'` instead of starting the next stage.
- Every agent call goes through `spawn()`, which counts it against `maxAgents`; a child gets what is left of the
  parent's cap (`maxAgents` in its args) and returns `agentsUsed`, which the parent adds to its own count.
- `args` arrive verbatim as JSON values; `parseArgs()` also accepts a JSON-encoded string from an older caller.
- Launch by name (`dark-factory:feature-auto`); nested runs by name too. A `scriptPath` (a project's own copy) must stay
  inside the session's tree.
- `export const meta = {…}` stays a plain literal (no template strings): the plugin loader parses it to register the
  name. Files are `.js` — the plugin loader skips other extensions.
- Every exit returns an object with `error` (`null` on success).
- Task status finalisation lives in the script code, not in an instruction to an agent.
- Agent message style — human-readable prose (`MSG_STYLE`), no telegraphic style.
- Long commands (pytest, ruff, npm) — only synchronously (the `SYNC` constant in every `TOPO`): an answer "waiting for a
  background run" is a failed step.
- No model id in the scripts: an `agent()` call without `model` inherits the session's model. A project pins roles
  through `models`; check after a run: `grep -o '"model":"[^"]*"' <transcript>/agent-*.jsonl | sort | uniq -c`.

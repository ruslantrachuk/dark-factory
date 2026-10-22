# Feature pipeline workflows (dark-factory plugin)

> Workflow scripts the development session launches to take one bd task from a spec or an OpenSpec phase to a
> committed, reviewed branch. They ship with the plugin and register as `dark-factory:<meta.name>`; the
> project-side setup is the `feature-pipeline` module ([templates/feature-pipeline/MANIFEST.md](../../../templates/feature-pipeline/MANIFEST.md)),
> which has the full argument table.

| File | Registered as | Role |
|---|---|---|
| `feature-auto.js` | `dark-factory:feature-auto` | entry point: branch + worktree → triage (small → `feature-lite`) → plan → overlap check → size gate / split → critic → bd subtasks → `feature-core` → integrate (merge the base, full gates, charter docs, devlog). Stops before the PR |
| `feature-core.js` | `dark-factory:feature-core` | the run's bd subtask graph: waves, parallel implementation on disjoint files, a single integrating writer, review lenses, fix |
| `feature-lite.js` | `dark-factory:feature-lite` | the small path: one build agent (TDD + full gates + commit), one wrap-up agent (bd note, charter docs, devlog) |
| `dryrun.mjs` | — (not loaded: the plugin loads `*.js` only) | stub run with fake agents — control flow without spending tokens |

## Launch

The Workflow tool by name, `args` as an object — the run's own arguments plus the project's settings from
`.claude/feature-pipeline.json` (test and lint commands, frontend dir, message catalog, invariants doc, surfaces):

```
Workflow({ name: "dark-factory:feature-auto", args: {
  "request": "[r12] Phase 3 — outbound delivery log", "stamp": "20261021-p3", "releaseLine": "r12",
  "bdId": "proj-t4sk.3", "changeDir": "openspec/changes/r12-example-change", "phase": 3 } })
```

The scripts find the project at run time (the session's git top level), not from where they are installed. Do not pass
`appDir`: the run creates its worktree at `<session tree>/.claude/worktrees/fab-<slug>`. Code at the tree root rather
than in base's `app/` — add `"appSubdir": ""`. Nesting is one level — `feature-auto` calls
`workflow('dark-factory:feature-core', …)` / `workflow('dark-factory:feature-lite', …)`, they call nothing. A project
that keeps its own edited copy passes `coreScript` / `liteScript` (absolute paths inside the session tree).

**Read `error`, not the status.** The harness reports "completed" for almost every run. `error: null` — the branch is
committed and green; anything else — the run stopped (`overlaps in-flight branch`, `plan failed`, `chunk <key> failed`,
`phase too large — split proposed`, `integrate failed`, `incomplete: …`). Each script lists its values in the result
comment at the top. Resume a stopped run with `resumeFromRunId` and the same args (same `stamp`).

After `error: null` the session shows the branch and the devlog assumptions to the owner and, after a "yes", runs
`scripts/merge-feature.sh <branch> --accepted-by "<name>"` — the name of the person who said "accepted" (the script
refuses to merge without it) — which closes `bdId` and carries `.beads/issues.jsonl`; then
`git worktree remove <worktree>`. When CI cannot run (Actions disabled: billing, limits, an incident) the owner may
also say to add `--skip-ci "<reason>"`: the script runs the local gate instead and marks the merge as made without CI
(refused at `FENCE_LEVEL=team`).

The merge closes a task only when the branch ends in the full bd id, `-<prefix>-<id>[.N]`, with the project's prefix
(from `.beads/issues.jsonl` or `.beads/config.yaml`); any other branch gives "no id — close by hand".
`scripts/merge-feature.sh <branch> --print-bd-id` prints the id it would use. `feature-lite` run by hand without
`bdId` names the branch plainly `r{N}/feat-lite-<stamp>` — no id, nothing to close — and the task its Wrap step
created (`wrap.details`) is closed by hand.

## Dry run

From the canon checkout (`plugins/dark-factory/workflows/`):

```bash
node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true}'
node dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x"}'
node dryrun.mjs feature-core.js '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}'
# code at the tree root, a hand-run small path without a bd task, a spent token budget:
node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true,"appSubdir":""}'
node dryrun.mjs feature-lite.js '{"request":"x","stamp":"s1","releaseLine":"r12"}'
DRYRUN_BUDGET=3000 node dryrun.mjs feature-auto.js '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true}'
```

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
- **`bd` commands run with `timeout 60`** (export — `timeout 120`): bd can hang on a database lock.
- The run's subtasks are children of `bdId` (label `auto-run`) and are closed by the core; the parent stays `in_progress`
  until `merge-feature.sh` closes it. The scripts do not commit `.beads/issues.jsonl`.

## Engine rules (do not change)

- `Date.now()` is forbidden in Workflow scripts (it breaks resume) — pass `stamp` as an argument.
- A token target set by the session (Workflow `budget.total`) is checked between stages and build rounds; when it is
  spent the run returns `error: 'budget exhausted'` instead of starting the next stage.
- `args` may arrive as a string → `parseArgs()` is mandatory.
- Launch by name (`dark-factory:feature-auto`); nested runs by name too. A `scriptPath` (a project's own copy) must stay
  inside the session's tree.
- `export const meta = {…}` stays a plain literal (no template strings): the plugin loader parses it to register the
  name. Files are `.js` — the plugin loader skips other extensions.
- Every exit returns an object with `error` (`null` on success).
- Task status finalisation lives in the script code, not in an instruction to an agent.
- Agent message style — human-readable prose (`MSG_STYLE`), no telegraphic style.
- Long commands (pytest, ruff, npm) — only synchronously (the `SYNC` constant in every `TOPO`): an answer "waiting for a
  background run" is a failed step.
- Agent models by full id (`claude-sonnet-5-5`, `claude-opus-5-5`), not an alias; the session's model is not inherited by
  subagents. Check after a run: `grep -o '"model":"[^"]*"' <transcript>/agent-*.jsonl | sort | uniq -c`.

# Feature pipeline workflows (dark factory feature-pipeline module, deployed for <project>)

> Source — dark factory `templates/feature-pipeline/`. Launched by the development session with the Workflow tool;
> the module manifest has the full argument table and setup.

| File | Role |
|---|---|
| `feature-auto.ts` | entry point: branch + worktree → triage (small → `feature-lite`) → plan → overlap check → size gate / split → critic → bd subtasks → `feature-core` → integrate (merge the base, full gates, charter docs, devlog). Stops before the PR |
| `feature-core.ts` | the run's bd subtask graph: waves, parallel implementation on disjoint files, a single integrating writer, review lenses, fix |
| `feature-lite.ts` | the small path: one build agent (TDD + full gates + commit), one wrap-up agent (bd note, charter docs, devlog) |
| `dryrun.mjs` | stub run with fake agents — control flow without spending tokens |

## Launch

Workflow tool, `scriptPath` = `<session tree>/.claude/workflows/feature-auto.ts` (a path inside the session's own tree —
Workflow refuses paths outside it), `args` as an object:

```json
{ "request": "[r12] Phase 3 — outbound delivery log", "stamp": "20261021-p3", "releaseLine": "r12",
  "bdId": "proj-t4sk.3", "changeDir": "openspec/changes/r12-example-change", "phase": 3 }
```

Do not pass `appDir`: the run creates its worktree at `<session tree>/.claude/worktrees/fab-<slug>`. Nesting is one
level — `feature-auto` calls `feature-core` / `feature-lite`, they call nothing.

**Read `error`, not the status.** The harness reports "completed" for almost every run. `error: null` — the branch is
committed and green; anything else — the run stopped (`overlaps in-flight branch`, `plan failed`, `chunk <key> failed`,
`phase too large — split proposed`, `integrate failed`, `incomplete: …`). Each script lists its values in the result
comment at the top. Resume a stopped run with `resumeFromRunId` and the same args (same `stamp`).

After `error: null` the session shows the branch and the devlog assumptions to the owner and, after a "yes", runs
`scripts/merge-feature.sh <branch>` (closes `bdId`, carries `.beads/issues.jsonl`), then
`git worktree remove <worktree>`.

## Dry run

```bash
node .claude/workflows/dryrun.mjs feature-auto.ts '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true}'
node .claude/workflows/dryrun.mjs feature-lite.ts '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x"}'
node .claude/workflows/dryrun.mjs feature-core.ts '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}'
```

Pass bare script names: scripts are loaded from next to `dryrun.mjs`, so a dry run from a worktree checks that worktree's
version. An optional third argument overrides agent answers by label, which exercises rare branches — e.g.
`'{"integrate#1":{"ok":false,"summary":"red"}}'` (core failure) or `'{"critic:recheck":{"approved":false,"issues":["x"]}}'`
(critic rounds exhausted → split). The stub also fails if a child script calls `workflow()`.

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
- `args` may arrive as a string → `parseArgs()` is mandatory.
- Launch by `scriptPath`, not by name; script paths stay inside the session's tree.
- Every exit returns an object with `error` (`null` on success).
- Task status finalisation lives in the script code, not in an instruction to an agent.
- Agent message style — human-readable prose (`MSG_STYLE`), no telegraphic style.
- Long commands (pytest, ruff, npm) — only synchronously (the `SYNC` constant in every `TOPO`): an answer "waiting for a
  background run" is a failed step.
- Agent models by full id (`claude-sonnet-5-5`, `claude-opus-5-5`), not an alias; the session's model is not inherited by
  subagents. Check after a run: `grep -o '"model":"[^"]*"' <transcript>/agent-*.jsonl | sort | uniq -c`.

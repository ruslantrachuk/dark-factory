# Night workflow engine (dark factory night-local module, deployed for <project>)

> Source — dark factory `templates/night-local/`. Topology: **local night** (one machine, one repository,
> GitHub origin/main; no relay between machines).

## Contents and status

| File | Tier | Status for <project> |
|---|---|---|
| `night-dispatch.ts` | orchestrator | one repo, branch base — `openspec/INTEGRATION_BRANCH` (otherwise main), branches `r{N}/<type>-night-<stamp>-<bd-id>`, night gate = fast pytest suite (as in pre-push) + ruff, label `night-done`, `pilotLiteOnly=true` by default (enable auto/core with `pilotLiteOnly=false` after a green lite) |
| `feature-lite.ts` | `scale:lite` | branch from the base, TDD per the test pyramid (CODING_STANDARDS.md §Test pyramid), pytest+ruff gates, devlog is mandatory; does not close the bd task (`merge-feature.sh` closes it) |
| `feature-auto.ts` | `bug` / `scale:auto` | source — a phase of an approved OpenSpec change (`changeDir`+`phase`), a ready spec (`specPath`) or the description of a bd bug; Setup (branch/worktree from the base) → Plan (subtasks with `FILES:`/`TESTS:`) → Critic → Bridge (children of the bd task, claimed by the owner) → Build (`feature-core`) → Integrate (merge the base, full gates, charter docs, devlog, tasks.md) → optional PR. A small task → delegated to `feature-lite`. Migrations only with `allowMigrations` (never at night) |
| `feature-core.ts` | `scale:core` | graph = children of `parentId` (or tasks of `assignee`) with `FILES:`/`TESTS:` lines; waves by dependencies, disjoint files → parallel; integrate by a single writer (scoped pytest, one commit per task, `bd close` of the subtask); full gate; review (test pyramid / invariants of CLAUDE.md and `<product invariants doc>` / simplify) → Fix. db lane by `dbTests` (needs Docker) |

Stub run of the control flow (fake agents, no tokens): `node .claude/workflows/dryrun.mjs <script> '<args-json>' ['<{"<label>": answer}>']` — a regression check of the scripts without spending tokens. Scripts are taken from next to `dryrun.mjs` (run from a worktree, it checks that worktree's version). The last argument overrides agent answers by label — this is how rare branches are exercised (critic rejected, split, failed chunk); this is how a `feature-core` in `reviewOnly` mode that silently exited without a review was caught.

### Model layout (a project decision; below — the canon default)

**Models only by full id** (`claude-sonnet-5-5`, `claude-opus-5-5`): the `sonnet` alias silently resolved to an older model. The main session model is not inherited by subagents. `sonnet` — mechanics (root, branch, bridge, graph, export, night test gate) and the per-bd-subtask subagent (impl, integrate, gates, fix, final integration, feature-lite as a whole); `opus` — plan and critic (feature-auto) and all review lenses (feature-core), with a fresh read-only context (a project may put every agent on `claude-sonnet-5-5` to save tokens). After-the-fact check: `grep -o '"model":"[^"]*"' <transcript>/agent-*.jsonl | sort | uniq -c`.

### Manual invocation (interactive, not at night)

The Workflow tool by `scriptPath` — the path to `feature-auto.ts` **inside the session directory** (`<cwd>/.claude/workflows/feature-auto.ts`), args as an object. Example — phase 3 of train r12 with migrations and db tests:

```json
{ "request": "[r12] Phase 3 — outbound delivery log", "stamp": "20260101-p3", "releaseLine": "r12",
  "bdId": "proj-t4sk.3", "slug": "feat-outbound-log-proj-t4sk.3", "baseBranch": "develop",
  "root": "~/<project>", "venv": "~/<project>/.venv",
  "changeDir": "openspec/changes/r12-example-change", "phase": 3, "path": "full",
  "allowMigrations": true, "dbTests": true, "stopBeforePR": true }
```

**The working tree is only inside the session directory.** Do not pass `appDir`: the run creates a worktree itself in `<cwd>/.claude/worktrees/fab-<slug>` (the path goes into the project `.gitignore`). A path outside (`~/<project>-wt/…` and the like) is rejected by `feature-auto` with the error `appDir outside session dir`: agents there get a permission prompt on every file, and Workflow does not run scripts outside the session directory — a nested call failed. For the same reason the nested `feature-lite.ts`/`feature-core.ts` are taken by default from `<cwd>/.claude/workflows/`. `root` — the main checkout with the bd Dolt store, needed only for `bd -C`.

The run's subtasks are created as children of `bdId` (label `auto-run`) and closed by the core; the parent stays `in_progress` — `scripts/merge-feature.sh` closes it at merge. The scripts do not commit `.beads/issues.jsonl` (`merge-feature.sh` carries it).

### Run rules

- **A phase is split automatically.** If a phase is wider than the threshold or the critic did not accept the plan → the architect splits it into 2–4 chunks, and `feature-auto` runs them in sequence on **one branch** via the small path (`feature-lite` with `skipWrap`, migrations — if `allowMigrations`). Review (`feature-core` in `reviewOnly` mode) and integration with the devlog happen **once** for the whole branch. Running each chunk as a full run with plan, critic and review cost far more tokens on a small feature. The old behaviour — `manualChunks: true`. In practice the review of the whole branch found defects the individual chunks did not see.
- **Split by end-to-end slices, not by layers**: each chunk, after its commit, works from the entry point to the result and is covered by a test at the entry level (base charter, Engineering Principles).
- **Parallel features with shared code — one after another.** After planning, `feature-auto` compares the plan's code files with unmerged local branches; an overlap → stop `overlaps in-flight branch`; to continue deliberately — `allowOverlap: true`.
- **The plan critic checks switch-off and reuse** (item 7): the behaviour of endpoints and user data with the flag off and on rollback is defined, revoking what the user saved always works; existing limiters, clients and helpers are used rather than rewritten. The same is in the mandatory checks of the `design` instruction in the base openspec schema.
- **The critic checks surfaces** (item 8): a user-visible feature without an "Interaction surfaces" section in the proposal, confirmed by the requester — stop with "no decision on interaction surfaces"; a plan covering only part of the surfaces is not approved. The gate — base `openspec/README.md` §0.
- **The heavy gate runs once per run; long lanes run in shards.** The limit of one agent command is 600 s; a longer db lane is split with the `dbShards` argument (paths from the tree root, e.g. `<test shard globs>`), each shard as its own synchronous command. Fix in `feature-core` with `skipFinalGates` runs only what was touched, the fast suite and the linter — the full db lane is run once by Integrate (a double run cost about 15 min per phase).
- **`bd` commands run with `timeout 60`** (export — `timeout 120`): `bd list` once hung for 10 minutes on a database lock.

## Preparing a task for the night (done by a human)

1. A spec in the repo (e.g. `docs/superpowers/specs/<date>-<slug>.md`), and in the bd task description the line `SPEC: <path from the root>`.
2. Label `bd label add <id> scale:lite`. Tasks unfit for the night (secrets, prod DB, alembic, external services) — `night-skip`.
3. The task is in `bd ready` (no blockers) and is not an epic. `night-dev preflight` checks this.

## Morning

`night-dev status` → review the branch and the assumptions in the devlog → push → "accepted" → `scripts/merge-feature.sh <branch>` (closes the bd task by the id at the tail of the branch). Remove the `night-done` label.

## Engine rules (hard-won, do not change)

- `Date.now()` is FORBIDDEN in Workflow scripts (breaks resume) — pass stamp as an argument
- `args` arrives as a string → `parseArgs()` is mandatory
- Launch by `scriptPath`, not by name
- Task status finalisation lives in the orchestrator code, not in an instruction to an agent
- The night never calls `bd close` — a waiting label; defensive reopen
- Agent message style — human-readable prose (MSG_STYLE), no telegraphic style
- Long commands (pytest, ruff, npm) — only synchronously (the `SYNC` constant in every TOPO): answering "waiting for a background run" = a failed step (an integrator once returned a stub and the run was counted as failed)
- Agent model — by full id, not an alias

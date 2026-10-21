# night-local — module manifest

> An autonomous night on one machine (a server or a laptop) **without a corporate perimeter**: queue execution engine + watchdog + operator CLI + runbook.
> Installed **on top of base** (charter, beads, openspec, hooks come from there).
>
> **Canon: the "local night" topology (one repo, code in `app/`).** A parallel corporate-perimeter variant
> (port slots, design-tool reconciliation, a relay between machines, corporate network access) is **not part of the canon** —
> it belongs to a separate **corp-perimeter** module (not built).

## Contents

| Artifact | What it does |
|---|---|
| `.claude/workflows/night-dispatch.ts` | orchestrator: `bd ready` → routing by `scale`, isolation by assignee, stopBeforePR, runaway protection |
| `.claude/workflows/feature-auto.ts` | tier `auto`/`bug`: Setup → **Plan → Split** → Critic → Bridge → Build → Integrate → PR |
| `.claude/workflows/feature-core.ts` | tier `core`: a ready epic graph, waves + fan-out review, a single integrating writer |
| `.claude/workflows/feature-lite.ts` | tier `lite`: a spec without a graph, one agent, the whole feature |
| `.claude/workflows/dryrun.mjs` | runs workflows with fake agents — syntax/flow without spending tokens |
| `.claude/workflows/README.md` | engine rules (hard-won) + workflow parameter map |
| `scripts/night-guard.sh` | launcher with a dead-man switch (timeout of N hours), token budget, headless `claude -p` |
| `scripts/night-dev.service` | systemd unit: wall-clock + cgroup kill + resource limits (⚠ never activated) |
| `.claude/skills/night-dev/` | operator CLI: status / preflight / arm / watch / stop (local, no relay) |
| `docs/night-dev-runbook.md` | operator runbook: topology, queue preparation, morning ritual, night protection model (§4) |

## Dependencies (on top of base)

- **Claude Code workflow engine** (launch by `scriptPath`), headless `claude -p --permission-mode auto`
- **tmux** (night session), **timeout**/`gtimeout` (macOS: `brew install coreutils`)
- bd tasks are labelled: `scale:lite|core|auto` + "SPEC: <path>" for lite/core (set by a human, checked by preflight)
- systemd — only for the server variant (the unit); on a laptop the dead-man switch is the `timeout` in night-guard

## Topology (canon) and what was removed

**Canon — "local night"**: one machine (a server or a laptop), code and harness in one tree, code in `app/`
(repo root for git/bd = the tree, `appDir = <repo>/app`). The night runs from tmux over ssh (or from the systemd unit),
without a relay: `git push/pull` are ordinary. Only **N=1** has been exercised; N>1 (worktree isolation under `app/`) is
marked as not adapted in `night-dispatch`.

**Removed from the canon (belongs to corp-perimeter):** a relay between machines (`deliver`/`collect`/`bump`,
private network, bare mirror), the corporate perimeter (corporate VPN, submodule), port slots (`portBase`, parallel runs),
design-tool reconciliation (`figmaFileKey`), project-specific risk labels, a playwright E2E gate.

## Parameter map

**`.claude/workflows/*`** (details — in their README):
- `appDir` defaults to `<repo>/app` (canon). Code at the root — adjust the `appDir` computation in `night-dispatch` (the line with `${ROOT}/app`) and the gate paths.
- the default gate is a fast `pytest` (`app/`, `-m "not browser"`) + `ruff` (as in the base pre-push). Another stack — replace the gate commands.
- labels `rel:<line>`, `scale:lite|core|auto`, `night-skip`, `night-done` — canon; there are no project risk labels.
- mentions of `<project>` in agent prompts — replace with the project name.
- placeholders in agent prompts: `<project surfaces>` (the surfaces list, see base `openspec/README.md` §0), `<i18n file>` (message catalog), `<product invariants doc>`, `<frontend dir>` (if the project has a frontend with its own CI lane; otherwise drop the frontend lane from `feature-lite`), `<umbrella card id>`.
- `dbShards` — db lane shard paths when the lane exceeds the 600 s command limit (`<test shard globs>`).

**`scripts/night-guard.sh`**:
- env prefix `PROJ_NIGHT_*` → the project prefix (e.g. the bd prefix in upper case); defaults of MAX_HOURS/MAX_FEATURES/TOKEN_BUDGET — calibrate in the pilot (runbook §4.7)
- the `$ROOT/app/.venv` check — to the location of the project venv
- the PATH block (claude/bd) — to the machine's toolchain

**`scripts/night-dev.service`**: `User`, `WorkingDirectory`, `ExecStart`, `Environment` (REL/budget), `RuntimeMaxSec`, `MemoryMax`/`CPUQuota` — to the box

**`.claude/skills/night-dev/bin/night-dev`**:
- env prefix `PROJ_NIGHT_*` → the project's; marker `.claude/env` (base canon)
- task id regex `<pfx>-[a-z0-9.]+` → the project's bd prefix
- the `$ROOT/app/.venv` check — to the project

**`docs/night-dev-runbook.md`**: generic; the protection model (§4) applies as is. Fill in the host choice and the calibrated numbers after the first pilot.

## Known gaps (address before the pilot)

- **the local-night pilot has not been run on any project yet** (the module has been installed, not piloted)
- N>1 (worktree isolation under `app/`) is not adapted — N=1 only
- feature-core does not read `stopBeforePR` (covered by defensive reopen in dispatch)
- the night systemd unit has not been activated (started via night-guard in tmux)
- the night sandbox: a devcontainer tier for night-local is an open decision at adaptation time (runbook §4.8)
- the window spending meter and the usage watchdog (runbook §4.4) are not part of the module

## Per-project assembly order

1. Copy the contents on top of a deployed base; the project code goes into `app/` (canon).
2. Parameterise by the map (grep for `PROJ_NIGHT_`, `<project>`, `<pfx>-`, `app/` and the prompt placeholders above); do **not change** the engine rules from workflows/README.
3. Add `.claude/worktrees/` to the project `.gitignore` (feature-auto creates its working trees there).
4. Label the queue: `scale` + "SPEC:" are set by a human; `night-dev preflight` checks.
5. **Pilot**: one night, `scale:lite`, `maxFeatures=1`, `stopBeforePR`, `TOKEN_BUDGET=0` (spending measured outside), under observation (`watch`). Morning — triage by a human.
6. Calibrate budgets and limits from the measurement (runbook §4.5, §4.7); only after a green lite — `core`, `auto` last.
7. Record the module in the factory registry (the project's "Contents" column).

## Design notes

- **Split on one branch.** When a phase is wider than the threshold or the critic does not accept the plan, `feature-auto` splits it into end-to-end slices and runs them on one branch via `feature-lite` (`skipWrap`, `allowMigrations`); review and integration run once (`finish`). `manualChunks: true` restores the old behaviour (return the split to the caller). Overlap with unmerged branches is checked (`allowOverlap`), code paths with and without the `app/` prefix.
- **Review severity scale = review contract.** `feature-core` uses `critical/major/minor` (`docs/review-contract.md`): `critical` remains a blocker, `critical`+`major` are fixed in the branch, `minor` goes to the devlog. Taste without consequence is not a finding.
- **Agent models by full id** (`claude-sonnet-5-5`/`claude-opus-5-5`): an alias silently resolved to an older model. The canon role layout: mechanics and workers on Sonnet, plan/critic/review on Opus.
- **`SYNC` constant** in the TOPO of `feature-auto/core/lite`: long commands only synchronously.
- **Surface gate**: the `SURFACES` constant in the requirements source and critic item 8 of `feature-auto`; without an "Interaction surfaces" section in the proposal — stop; the list of surfaces is a project placeholder.
- **`dbShards`** in `feature-auto`/`feature-core` (default — one directory); Fix with `skipFinalGates` — without the full db lane; `timeout` on `bd` commands and the export.

## Open questions

- **Split on one branch vs `manualChunks` by default.** Abandon criterion: if, on later phases, token spending does not drop noticeably compared to full per-chunk runs, or chunks start to conflict — return `manualChunks` as the default. Decide only by comparing both variants on **the same task**: one phase, one base, `manualChunks: true` vs split on one branch; measure spending without cache, cache reads, number of agents, time and quality (green gates, review findings, fixes afterwards). Measurement: one script over `agent-*.jsonl`, nested runs included; "without cache" = input + cache_creation + output.
- **Reachability constant (`REACH`)** — a critic check that a feature behind a switch is reachable — not adopted; waits for a feature behind a switch.

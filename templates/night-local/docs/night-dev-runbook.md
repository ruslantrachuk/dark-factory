# Night-dev runbook (autonomous night development, local night)

> Operator runbook for the canon topology "local night" (one machine, one repo, code in `app/`, no relay) —
> see [MANIFEST.md](../MANIFEST.md) §Topology. The night stops BEFORE `ship`; push/PR/merge are done by a human in the morning.
> §4 (the night protection model) is the core of this document; §1–§3 are the minimal operating procedure.

## 1. Topology

- **One machine** (a server reached over ssh, or a laptop that stays on), code and harness in one tree, code in `app/`.
  The night runs from tmux (`night-dev arm` → `scripts/night-guard.sh`) or from the systemd unit (`scripts/night-dev.service`).
- **git is ordinary**: `git push/pull` against the usual origin; no mirrors and no relay between machines.
- **Where-am-I marker**: the per-machine `.claude/env` marker from base (gitignored); `night-dev status` prints it.
- **Structural backstops** (not just the agent's conscience):
  1. `night-dispatch.ts` passes `stopBeforePR` explicitly (default `true`) and never calls `ship` — the night structurally cannot reach a push.
  2. The night never closes tasks: a green run gets the `night-done` label; `scripts/merge-feature.sh` closes the task at merge.
  3. Night-unfit tasks (secrets, prod DB, alembic, external services) are excluded by the `night-skip` label.

| Capability | **Night** (autonomous) | **Morning** (human present) |
|---|---|---|
| commit to a feature branch | ✅ | ✅ |
| push / PR / merge | ❌ | ✅ on the owner's explicit "yes" |
| fast test suite (no db/e2e/live) | ✅ | ✅ |
| full test matrix (db/e2e) | ❌ (CI) | ✅ CI after push |
| bd | claim + `night-done` label (**NOT** a final close) | final close after merge |

## 2. Preparing the queue (done by a human, in the evening)

1. A ready spec in the repo, and the line `SPEC: <path from the repo root>` in the bd task description
   (for `scale:auto` alternatively `OPENSPEC: <change dir> PHASE: <N>`).
2. A tier label: `scale:lite` for the pilot (`scale:core` / `scale:auto` only after a green lite). Night-unfit tasks — `night-skip`.
3. The task is in `bd ready` (no blockers) and is not an epic.
4. `night-dev preflight` must be green; then `night-dev arm [features] [hours]`.

## 3. Morning ritual

1. `night-dev status` — branches `r{N}/<type>-night-<stamp>-<bd-id>`, tasks with `night-done`, tail of the last log.
2. Per branch: read the night's devlog entry (assumptions — "decisions the machine made for you") and `git diff origin/main...<branch>`.
3. Not OK → fix on the same branch (interactive session) or hand the task back to the queue with a bd note.
4. OK → push → green CI (the full matrix runs there) → "accepted" → `scripts/merge-feature.sh <branch>` (closes the bd task by the id at the tail of the branch).
5. Remove the `night-done` label; clean up leftovers with `git worktree prune` if worktrees were used.

## 4. Protecting the autonomous night — a single model

> A sober view: what is actually dangerous at night without supervision, what closes it, and in which priority to build it. Honestly marked "exists" ✅ / "needed" 🔜.

### 4.1 What we are afraid of (three modes, not one)

| Mode | What it does | Consumes | Danger |
|---|---|---|---|
| **Hang** | stuck waiting (hung command, lock, stdin) | **time**, not quota | loses the night/slot |
| **Runaway loop** | keeps grinding: retries, regeneration | **quota** (5h window) | the main enemy on a subscription plan |
| **"who knows what"** | an irreversible action | — | **already structurally impossible** (see 4.2) |

On the spending axis, hang and loop are **mirror images**: both grow in time, but a hang's spending is flat while a loop's grows. The discriminator is **progress × spending**: progress stopped + spending grows → loop (kill it); progress stopped + spending flat → hang (wall-clock will finish it).

### 4.2 What is already structurally safe (a fence, no code needed)

A night run **physically cannot** do anything irreversible: **no ship/push/merge** (`stopBeforePR`), **no production access** (night-unfit tasks are `night-skip`), a throwaway branch/worktree per run. The worst outcome of a runaway night is **cluttered local branches + a burnt window**. In the morning it is cleaned up with `git worktree prune` + review. That is half of the peace of mind — and it comes for free.

### 4.3 Validated principles

1. **Quota cannot be measured from inside the script.** `budget.spent()` = output tokens only (a fraction of a percent), while the 5h window is driven by input+cache (~84%). Real spending is measured **outside** — from the Claude Code transcript JSONL (weighted sum of `input+cache+output`) or from the server-side quota (base quota guard, `docs/quota-guard.md`); time is a rough proxy and an emergency kill.
2. **Night volume is set by the quota, not by the queue and not by the timeout.** About one volume (~6 full features) fits into one 5h window, then throttling. 20 tasks per night are impossible — the rest stays in `bd ready` for the next night. The primary volume lever is the **count cap**, not time.
3. **Control is external and dumb** (cron/systemd, no LLM). NOT the main Claude session (a single point of failure), NOT an in-script token guard (wrong units, does not interrupt an agent in flight).
4. **In-script tokens — only a relative anomaly** (a run's `runSpent` >> the output median → probable loop). Not a quota budget.
5. **wall-clock = a guaranteed end (dead-man switch), NOT a window/volume regulator.** It answers exactly one question — "what if it does not stop by itself?" (hung / looping / stuck in throttling). Time **does not know the phase of the 5h window** (it is anchored to your first request, not to the start of the night; it may have been eaten during the day or reset in the middle of the night) → real window protection comes **only** from a usage watchdog. The wall-clock value is "max hours without supervision", not the window.

### 4.4 Layers and status

| Layer | Catches | With what | Status |
|---|---|---|---|
| Fence against the irreversible | ship/push/prod | `stopBeforePR` + `night-skip` + branch/worktree | ✅ exists |
| Logical build loop | endless wave loop | `MAX_ROUNDS=20` + stop on no progress (`feature-core`) | ✅ exists |
| **wall-clock = guaranteed end** | **non-termination: hang / loop in flight / throttling stupor** | systemd `RuntimeMaxSec` + `KillMode=control-group`, or `timeout` in `night-guard.sh` | 🟡 templates `scripts/night-dev.service` + `scripts/night-guard.sh` (unit NOT activated) |
| Non-interactive environment | stuck on input | env variables (in the templates) | 🟡 in `night-dev.service`/`night-guard.sh` |
| Window spending meter | real remainder of the 5h window (phase-independent) | base quota guard (`scripts/quota.py`, server-side percentage) or a JSONL meter | 🔜 not part of this module |
| **Usage watchdog (window phase)** | **real window remainder; loop (spending↑ + progress=0)** | an external cron script (window meter + git progress) | 🔜 not part of this module (mandatory for a quota goal) |
| Volume count cap | taking more than the window (if the window is fresh) | `maxFeaturesPerNight` in `night-dispatch` | ✅ exists (a cheap guide; the exact cap belongs to the watchdog) |
| Weekly ceiling | one night burning the week | counter in the scheduler | 🔜 |
| Anomaly (output) | a loop that came back expensive | `maxPerRun` (in `night-dispatch`) | ✅ exists, but **output units — calibrate** |
| Reserve between tasks | not grinding the window to zero | `perRunReserve` | ✅ exists, **weak** (output only) |
| Soft cumulative ceiling | runaway across many tasks | `tokenBudget` — passed by `night-guard` (`PROJ_NIGHT_TOKEN_BUDGET`, default `features×2M`) | ✅ passed; output proxy, rough; pilot measurement: `PROJ_NIGHT_TOKEN_BUDGET=0` → `null` |

### 4.5 Concrete values (realistic; "*" = calibrate in the pilot)

```ini
# night-dev.service (systemd) — wall-clock = GUARANTEED END (not the window!)
[Service]
RuntimeMaxSec=6h           # dead-man switch: "max hours without supervision" (e.g. the length of the night).
                           # NOT tied to the 5h window — the window phase at the start of the night is unknown.
KillMode=control-group     # kills the WHOLE cgroup, including nohup&disown dev servers
TimeoutStopSec=30s
Restart=no
Environment=GIT_TERMINAL_PROMPT=0 GIT_PAGER=cat GIT_EDITOR=true CI=1
```

- **`timeout` is put on the night launcher** (`claude -p "… night-dispatch …"`); all features/agents/subprocesses are its descendants. A bare `timeout` will NOT kill detached servers → a cgroup kill (systemd) is what is needed. Today the gates run in-process (pytest) and no servers are started, but E2E/preview would change that.
- **The usage watchdog (cron every ~2–3 min) is the only real window protection** (knows the actual remainder, phase-independent): window usage ≥ *threshold% → kill the night; pace↑ + no new commits/`bd close` for N min → loop → kill immediately.
- **`maxFeaturesPerNight` ≈ 6 full / ≈ 12 lite** — a cheap volume guide (valid if the window is fresh); the rest → `bd ready`. The exact cap belongs to the watchdog.
- **Night cap ≤ 30% of the weekly quota** — even occasional nights do not burn the week (take the weekly capacity from the Anthropic console).
- **`maxPerRun` = 3× the output median\*** (anti-loop, not a budget); **`perRunReserve` = 1.2× the per-feature output median\*** (secondary).
- **Daytime:** only `feature-lite`, ≤60% of the window — a separate launch mode.

### 4.6 Minimal sufficient set (if you build only what is necessary)

For the goal **"the night without supervision will not do anything crazy"** (hang / loop on garbage / irreversible action), **three** things are enough:

1. **systemd `RuntimeMaxSec` + `KillMode=control-group`** (or `timeout` in `night-guard.sh`) — a guaranteed end of anything (dead-man switch; the value = max hours without supervision, not the window).
2. **Non-interactive environment** (env above) — no getting stuck on input.
3. **The fence of 4.2** (no ship/prod, throwaway branch) — nothing irreversible (already exists).

`maxFeaturesPerNight` is a cheap volume limiter on top.

> **But:** since the night is allowed to burn the window, "the window got eaten" is not an incident. The goal **"honestly keep to a share of the window / week"**, however, is NOT achievable by time (the window phase is unknown) → for that goal **a usage watchdog is mandatory**; it is not "the next layer of precision" but a necessary condition of the quota goal specifically.

### 4.7 Pilot calibration (how to get real numbers)

One night: `tokenBudget=null` (start with `PROJ_NIGHT_TOKEN_BUDGET=0` — night-guard does not pass a budget), a high `maxPerRun`, `RuntimeMaxSec=6h` (backstop). Record: how many features were done, the JSONL sum, and from the **Anthropic console** — what % of the window and the week was actually used + **when the window moved/reset**. Derive the coefficient `JSONL sum → % of window` and teach the watchdog to find the window boundary from usage history (not from the start time). Plug it into the thresholds of 4.5 (and into the `PROJ_NIGHT_TOKEN_BUDGET` default).

### 4.8 Agent execution isolation (sandbox) — separate from the worktree

**A worktree is NOT a sandbox.** It isolates the files/git state of parallel runs (correctness), but does not limit what the agent's commands may touch. The agent executes arbitrary code (test runners, `npm`, git, shell) on untrusted input (bd task description, external dependencies) → in theory prompt injection or a malicious dependency. This is a separate layer — an **execution sandbox** — and whether it is needed depends on the **host**:

| Host | Blast-radius boundary | Container needed? |
|---|---|---|
| **Dedicated server** | **the box itself** — disposable, no production access, no secrets beyond the night's own | **No** (strictly): the whole machine is the sandbox; per-agent Docker adds little |
| **Personal laptop** | your real machine — home directory, keychain, VPNs | **Yes, preferably**: Docker/bwrap or the Claude Code sandbox around the run really reduces the risk to your environment |

**A cheap intermediate step (any host):** resource isolation (not file isolation) comes from the same systemd unit — it already puts the night into a cgroup; add `MemoryMax` / `CPUQuota` / `TasksMax`. It hits "ate all memory/CPU" without fiddling with images.

**What this is NOT:** the application's `docker-compose` stack is the application runtime, **not a sandbox for developer agents**.

**When it is "for the big league":** a microVM/gVisor/Firecracker per agent is multi-tenancy/scale (code of many clients on the same hardware). For one project on a disposable server it is overkill; a dedicated box achieves roughly the same more simply.

**Conclusion:** worktree (exists) ≠ sandbox; on a dedicated server the box is the sandbox, on a laptop wrap the run in a container; the cheap step now is cgroup limits in the systemd unit. A full per-agent microVM — only at scale.

### 4.9 An honest note on status

**Built and in this module:**
- `maxFeaturesPerNight` in `night-dispatch` — volume count cap (separate from `maxParallel`);
- `MAX_ROUNDS` + stop on no progress (`feature-core`), in-script token guards (`maxPerRun`/`perRunReserve` — output units, understated);
- the stub dry-run of the workflows (`.claude/workflows/dryrun.mjs`).

**Ready templates, NOT activated** (need a host/agreement):
- `scripts/night-dev.service` (systemd: dead-man `RuntimeMaxSec` + `KillMode=control-group` + cgroup limits + env);
- `scripts/night-guard.sh` (launcher with `timeout` for a non-systemd host).

**Not in this module, to build:** a window spending meter and the usage watchdog (§4.4).

**Requires a joint session** (not without the owner): pilot calibration of thresholds (§4.7, needs numbers from the Anthropic console), fixing the units of `maxPerRun`/`perRunReserve` (output median from the pilot), the weekly counter, the choice of host and activation of the unit, the execution sandbox on a laptop (4.8). Until then the autonomous night relies on the fence of 4.2 + manual start under supervision.

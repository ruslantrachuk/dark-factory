# The Production layer — understanding

> Format — as in [preparation.md](preparation.md).
> Layer 3 of the [process.md](../process.md) frame: "turn the package into verified code"; input — a package from preparation, output — a branch + handoff.
> Resolved forks ([open-questions.md](../open-questions.md) §2) are not revisited.

## Typical pains

1. **Visibility of state**: the beads harness is files; several features mean different branches/worktrees; the coordinator poorly understands what it is picking up, "everything starts getting lost".
2. **The morning merge tax**: N features = N environment start-ups (you look at one feature out of three) + merges/rebases; with a heavy build and tests — hours. "The usual problems of development by several people with feature branches."

Separately: "agent orchestration — unclear what is going on at all" (the same visibility gap from the human side).

## Layer decisions

1. **The template's base loop = "the VPS is equal to the workstation"** (canonical "local night", see [methodology.md](../methodology.md) §2). Working formula: "log into the machine and start the task-implementation queue there".
   - **e2e-autofix in CI** — into the template only after it is debugged.
   - A full VPS + relay setup is **not** "an add-on for a corporate perimeter" but an unfinished attempt at a delegation mechanism.
2. **The night integration branch is disposable.** Each feature lives in its own branch; the coordinator merges them into a night branch and deploys **one stand** — in the morning the whole night's result is viewed at once. Shipping is per feature, by merging the original branches; the night branch is thrown away. Bonus: cross-feature conflicts surface when assembling the night branch, not at the final merge.
3. **The output of the queue is a human-readable digest** (handoff), tied to the completion of the task queue. Mandatory content: per feature — branch/status/what changed + assumptions ("decisions the machine took for you") + for a fail — an "honest fail": where it stopped, what it tried, what the human needs to do + a link to the night stand. The delivery channel (a comment on the board card / a report + a skill) is a design fork of the layer.
4. **The scale model**: a spec is mandatory for `lite` and `core`; the difference between them is **multi-agent execution** (`lite` — one agent without a graph; `core` — an epic + a phase graph + waves); `auto` — delegated design ("do it yourself" from the preparation vocabulary). **Scale is set by a human explicitly during preparation** — deriving the tier from the shape of the package is technically possible, but it is a known pitfall (it breaks "hand-over to the machine is explicit"); "the agent does NOT guess the tier" is enforced in code. The risk part of the clearance is separate labels (e.g. "needs a restricted database", "needs client data"), also set by humans.

## Problems (recorded, to be solved later — not decisions)

- **Visibility/orchestration**: the coordinator does not see what it took; the human does not see the agents and sessions. Three problems: passing context between different coding agents (now by hand/skill), visibility of active sessions (remote + local), mutual interference of parallel agents in one project.
- **The morning merge tax**: the stand from decision 2 cures the viewing, but merges/rebases and environment start-ups remain.
- **Sandbox / autonomous agent work on a workstation**: on a VPS a sandbox is free (a disposable offline box — a machine without secrets, wiped and re-provisioned); on a workstation the agent works next to home, the keychain and corporate VPNs. Resolved in [decisions/mac-sandbox.md](../decisions/mac-sandbox.md).

## Open ends

- **Layer design**: night-branch mechanics (who assembles it, what happens on a conflict), the digest channel, stand deployment.
- **Debugging e2e-autofix (CI)** — before it enters the template.
- **Normative documents** (an ADR on night autonomy, the autonomy ladder) — see [open-questions.md](../open-questions.md) §1.
- Usage-watchdog calibration, the systemd unit, night-branch naming — known gaps inherited by the `night-local` module (see its MANIFEST).

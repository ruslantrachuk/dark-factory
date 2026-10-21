# The Production layer — understanding

> Format — as in [preparation.md](preparation.md).
> Layer 3 of the [process.md](../process.md) frame: "turn the package into verified code"; input — a package from preparation, output — a branch + hand-over.
> Settled decisions ([open-questions.md](../open-questions.md) §2) are not revisited.

## Typical pains

1. **Visibility of state**: the bd queue is files; several features mean different branches/worktrees; the executor poorly understands what it is picking up, "everything starts getting lost".
2. **The acceptance merge tax**: N features = N environment start-ups (you look at one feature out of three) + merges/rebases; with a heavy build and tests — hours. "The usual problems of development by several people with feature branches."

Separately: "agent orchestration — unclear what is going on at all" (the same visibility gap from the human side).

## Layer decisions

1. **Execution runs inside the project's development session on the server** — a long-lived `claude remote-control` session the owner drives from the web or the phone (see [methodology.md](../methodology.md) §2). Working formula: "tell the development session to take the task" — now, or booked for later with native scheduling.
2. **One feature = one branch = one worktree.** The feature pipeline (`feature-auto` → `feature-core` / `feature-lite`) plans, builds in test-first chunks, integrates in its own worktree and makes a local commit, **stopping before the PR**. Shipping is per feature: `scripts/merge-feature.sh` after a human "yes". Features whose plans touch the same code files run one after another: the pipeline stops on an overlap with an unmerged branch unless told otherwise.
3. **The outcome of a run is explicit.** The result's `error` field is the real outcome, not its status. The session's hand-over, per feature: branch / status / what changed + assumptions ("decisions the machine took for you") + for a fail — where it stopped, what it tried, what the human needs to do. Assumptions also go into the devlog.
4. **The scale model**: a spec is mandatory for `lite` and `core`; the difference between them is **multi-agent execution** (`lite` — one agent without a graph; `core` — an epic + a phase graph + waves); `auto` — delegated design ("do it yourself" from the preparation vocabulary). **Scale is set by a human explicitly during preparation** — deriving the tier from the shape of the package breaks "hand-over to the machine is explicit"; "the agent does NOT guess the tier" is enforced in code. The risk part of the clearance is separate labels (e.g. "needs a restricted database", "needs client data"), also set by humans.
5. **A worktree is not a sandbox.** It isolates files and git, not commands; base enables the built-in Claude Code sandbox and `permissions.deny` (an explicit question at deployment, [methodology.md](../methodology.md) §3).
6. **Near the quota limit the session stops itself.** The quota guard (base) stops new work at 80%, asks to wrap up at 85%, allows only saving work and scheduling a continuation at 90%; the session books its own continuation after the reset.

## Problems (recorded, to be solved later — not decisions)

- **Visibility/orchestration**: the executor does not see what it took; the human does not see the agents and sessions. Three problems: passing context between different coding agents (now by hand/skill), visibility of the active sessions across projects, mutual interference of parallel agents in one project.
- **The acceptance merge tax**: merges/rebases and environment start-ups for several finished branches.

## Open ends

- **Viewing several finished branches at once**: how they get onto one stand for acceptance without an extra merge step.
- **The hand-over format** of a run and the **autonomy ladder** — see [open-questions.md](../open-questions.md) §1.

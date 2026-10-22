# The Production layer

> **Stages:** Development, and the machine half of Testing (phases 5–6 of [map.md](../map.md): execution and machine
> verification). Layer 3 of [process.md](../process.md): "turn the package into verified code". Input: a package
> from preparation. Output: a branch and a hand-over. Same format as [preparation.md](preparation.md).
> Settled decisions ([open-questions.md](../open-questions.md) §2) are not revisited here.

## Typical pains

1. **Visibility of state**: the bd queue is files; several features mean several branches and worktrees; the
   executor has a poor picture of what it is picking up, and "everything starts getting lost".
2. **The merge tax at acceptance**: N features mean N environment start-ups (you look at one feature out of three)
   plus merges and rebases; with a heavy build and tests, that is hours. "The usual problems of several people
   developing on feature branches."

Separately: "agent orchestration: it is unclear what is going on at all" (the same visibility gap, seen from the
human side).

## Decisions

1. **Execution runs inside the project's development session on the server**, a long-lived `claude remote-control`
   session the owner drives from the web or the phone (see [methodology.md](../methodology.md) §2). The working
   formula: "tell the development session to take the task", now or booked for later with native scheduling.
2. **One feature = one branch = one worktree.** The feature pipeline (`feature-auto` → `feature-core` or
   `feature-lite`) plans, builds in test-first chunks, integrates in its own worktree and makes a local commit,
   **stopping before the PR**. Shipping is per feature: `scripts/merge-feature.sh <branch> --accepted-by "<name>"` after a human "yes". Features
   whose plans touch the same code files run one after another: the pipeline stops when it overlaps an unmerged
   branch, unless told otherwise.
3. **The outcome of a run is explicit.** The result's `error` field is the real outcome, not its status. The
   session's hand-over, per feature: the branch, the status, what changed and the assumptions ("decisions the machine
   took for you"); for a failure, also where it stopped, what it tried and what the human needs to do. The
   assumptions also go into the devlog.
4. **The scale model**: a spec is mandatory for `lite` and `core`; the difference between them is **multi-agent
   execution** (`lite` is one agent without a graph; `core` is an epic, a phase graph and waves). `auto` delegates
   the design ("do it yourself" from the preparation vocabulary). **A human sets the scale explicitly during
   preparation**: deriving the tier from the shape of the package would break "the hand-over to the machine is
   explicit", and the code enforces that the agent does NOT guess the tier. The risk part of the clearance is a set
   of separate labels (for example "needs a restricted database", "needs client data"), which humans also set.
5. **A worktree is not a sandbox.** It isolates files and git, not commands; base enables the built-in Claude Code
   sandbox and `permissions.deny` (an explicit question at deployment, [methodology.md](../methodology.md) §3).
6. **Near the quota limit, the session stops itself.** The quota guard (base) stops new work at 80%, asks the agent
   to wrap up at 85%, and allows only saving work and scheduling a continuation at 90%; the session books its own
   continuation after the reset.

## Problems (recorded to solve later; not decisions)

- **Visibility and orchestration**: the executor does not see what it took, and the human does not see the agents
  and sessions. That is three problems: passing context between different coding agents (now done by hand or with a
  skill), seeing the active sessions across projects, and parallel agents getting in each other's way in one
  project.
- **The merge tax at acceptance**: merges, rebases and environment start-ups for several finished branches.

## Open questions

- **Viewing several finished branches at once**: how to get them into one preview environment for acceptance
  without an extra merge step.
- **The hand-over format** of a run and the **autonomy ladder**: see [open-questions.md](../open-questions.md) §1.

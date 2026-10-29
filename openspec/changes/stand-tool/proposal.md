# One stand tool, extended by each project

## Why

Almost every project has two stands. The **main stand** runs main; a human accepts features there. The **preview**
is started from a local branch so the result can be seen before the push. Since `stand-from-server` the server keeps
the main stand on main, through the project's `scripts/stand-update.sh`. Everything else is done by hand, and
differently in every project. Sessions of the same project also do it differently: how a stand starts and stops,
its ports, logs and smoke check, and where a preview comes from.

In one project, on one day:

- a full preview from a worktree, started by hand two days earlier, ran on the main stand's database, so a branch
  migration would have broken the main stand;
- agents raised frontend-only previews for screenshots on ports they chose themselves;
- the agents killed processes with `pkill -f` patterns, and once a pattern matched the agent's own shell;
- they deleted dependency symlinks before every commit, because the ignore rule missed them;
- every such step needed the owner's yes in a permission prompt.

A pilot script for the frontend preview took the mechanics off the agents: port claims, records and stopping by
record. Parallel agents no longer collide on it.

## What changes

- **A tool in the plugin: `scripts/stand.py`.** It does the same mechanics for every project:
  - claims a port (a fixed one for the main stand and the preview, a free one from a range for a temporary stand),
    atomically, so parallel callers never share one;
  - starts the stand detached, so it outlives the session, and records its pid;
  - stops only the process in its own record, checked by its command line, never by a `pkill` pattern;
  - keeps logs, waits until the stand listens, runs the smoke check;
  - exit codes tell "no free port" from "build or start failed";
  - keeps its state outside the worktree; `STAND_STATE` moves it, e.g. into a sandboxed agent's scratchpad.
- **The same commands for every stand:**
  - `stand.py start|stop|restart|status|logs <stand> [--from <worktree>]`;
  - `stand.py ls`.
- **Three kinds of stand:**
  - `main`: the main checkout on main.
  - `preview`: one per project, with a fixed port and link, started **on a human's request in an interactive
    session**, not by an unattended run. `start preview --from <worktree>` builds and serves that worktree's branch
    on the preview's own database: the project's `prepare` creates and migrates it, since a branch may carry
    migrations. The tool refuses a preview whose DSN equals the main stand's. It switches a preview that serves
    another branch only with `--take`, because someone may be looking at it.
  - `temp`: for agents, started when the agent decides it needs one. A frontend-only stand of the caller's worktree
    on a free port from the range, with the API proxied to the main stand; `stop` stops it and removes its build.
    Agents use it for screenshots before the report (`build-tdd` step 7).
- **The project extends it with one script: `scripts/stand.sh <step>`.** It holds only what depends on the stack:
  - steps: `prepare` (dependencies, migrations, the preview's own database), `build`, `run` (in the foreground; the
    tool detaches it) and `smoke`;
  - the tool passes `STAND_KIND`, `STAND_CHECKOUT`, `STAND_PORT` and `STAND_DIR` (the build directory).
  - The base template's `dev-stand` skill gives the script's skeleton, to be filled from a live run.
- **Configuration in `.claude/factory/stands.json`**, the server's stand list the status feed already reads: the
  port, health route and tunnel or link of `main` and `preview`, and the port range of `temp`. The feed shows which
  branch the preview serves, from the tool's state.
- **The `dev-stand` skill follows.** Stands are started, stopped and switched only through the tool. Its hand-written
  Start, Stop and Clean-up sections become the project's `stand.sh`. The main stand's rules stay as they are: detach,
  ports on 127.0.0.1, secrets, background jobs, restart with the owner's yes, smoke.

## Not in this change

- **The main stand's server updater.** `df-<slug>-stand` keeps running `scripts/stand-update.sh`. Moving it to
  `stand.py restart main` is the next step, once preview and temp have run in a project.
- **Background jobs** (rule 7) stay a decision of the project and the owner; the tool does not start them.
- **Stands of several machines.**

## Acceptance scenarios

- WHEN two agents run `stand.py start temp` at the same time in different worktrees THEN they get different ports and
  each serves its own branch.
- WHEN a port of the range is taken by a process the tool does not know THEN the tool skips it.
- WHEN no port is free THEN `start temp` exits with its own code and a hint to run `stand.py ls`.
- WHEN `stand.py stop temp` runs THEN only the process in its record is stopped, and its build is removed.
- WHEN `start preview --from <worktree>` runs while the preview serves another branch THEN it refuses and names that
  branch; with `--take` it switches.
- WHEN the preview starts THEN it uses its own database, not the main stand's.
- WHEN a project has no `scripts/stand.sh` THEN the tool says what to write and does nothing else.
- WHEN a stand is up THEN `fleet.py status` and the owner's status show it with its branch and link.
- WHEN an unattended run builds a feature THEN it starts no preview; it may start `temp` stands for its screenshots.

## Decided with the owner

- The preview's database is its own, created and migrated by the project's `prepare`: a branch may carry migrations.
- `temp` stands are the agent's own call; the preview is started on a human's request in an interactive session.
- A full temporary stand per agent (a database per agent) stays out until a project needs one.

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
  - claims a port atomically, so parallel callers never share one;
  - starts the stand detached, so it outlives the session, and records its pid;
  - stops only the process in its own record, checked by its command line, never by a `pkill` pattern;
  - keeps logs, waits until the stand listens, runs the smoke check;
  - exit codes tell "no free port" from "build or start failed".

  Its state lives in one fixed place per user on the server, outside every worktree, so port claims and the
  preview's owner are seen by every session.
- **The commands:**
  - `stand.py start|stop|restart|logs <stand> [--from <worktree>]`;
  - `stand.py ls`: every stand of the server with its port, branch, link and log path.
- **Two stands per project:**
  - **`main`.** The tool only shows it for now. The server's updater (`df-<slug>-stand`, `stand-update.sh`) stays its
    only owner, so no two scripts start and stop it. It moves into the tool in a later change.
  - **`preview`.** One per project, with a fixed port and link, started on a human's request in an interactive
    session. `start preview --from <worktree>` builds and serves that worktree's branch on the preview's own
    database:
    - the project's `prepare` recreates the database and migrates it from zero on every switch, because the previous
      branch's migrations may not match this one;
    - the project's `prepare` also loads the test users;
    - the tool refuses to start when the preview's database name, which the project's `db` step prints without
      credentials, equals the main stand's.

    It switches a preview that serves another branch only with `--take`, because someone may be looking at it.
- **And a permission, not a third stand: an agent may raise temporary stands when it needs them.**
  - `stand.py start temp` serves the frontend of the caller's worktree on a free port from the server's range
    (8210–8219 by default), with the API proxied to the main stand. It is for looking at frontend changes and makes
    no writes, because the main stand's database is where features are accepted.
  - `stop temp` stops it and removes its build. A temp stand whose worktree is gone, or that is older than a limit,
    is removed by the next `start` or `ls`, since agents often finish without stopping one.
  - There may be many at once, one per agent. Only `stand.py ls` lists them; the status and the owner's feed do not.
  - The project allows only `stand.py start temp`, `stop temp` and `ls` in its permissions. An agent then starts and
    stops its own temp stands without asking anyone, and cannot touch the preview or the main stand.
- **The project extends the tool with one script: `scripts/stand.sh <step>`.** It holds only what depends on the
  stack:
  - steps: `prepare` (dependencies, migrations, the preview's own database), `build`, `run` (in the foreground; the
    tool detaches it), `smoke` and `db`;
  - the tool passes `STAND_KIND`, `STAND_CHECKOUT`, `STAND_PORT`, `STAND_DIR` (the build directory) and `STAND_URL`
    (the stand's public link, for CSRF and links in mail);
  - the base template's `dev-stand` skill gives the script's skeleton, to be filled from a live run.
- **Configuration** lives in `.claude/factory/stands.json`, the server's stand list the status feed already reads:
  the port, health route and tunnel or link of `main` and `preview`. The feed shows which branch the preview serves,
  from the tool's state.
- **The `dev-stand` skill follows.** The preview and temp stands are started, stopped and switched only through the
  tool. The main stand's rules stay as they are: detach, ports on 127.0.0.1, secrets, background jobs, restart with
  the owner's yes, smoke.

## Not in this change

- **The main stand inside the tool.** Its updater and its start and stop move to `stand.py` in a next change. Then
  `fleet.py stand` runs `stand.py restart main` when the project has `scripts/stand.sh`.
- **Background jobs** (rule 7) stay a decision of the project and the owner; the tool does not start them.
- **A full temp stand per agent**, with a database per agent, stays out until a project needs one.
- **Stands of several machines.**

## Acceptance scenarios

- WHEN two agents run `stand.py start temp` at the same time in different worktrees THEN they get different ports and
  each serves its own branch.
- WHEN a port of the range is taken by a process the tool does not know THEN the tool skips it.
- WHEN no port is free THEN `start temp` exits with its own code and a hint to run `stand.py ls`.
- WHEN `stand.py stop temp` runs THEN only the process in its record is stopped, and its build is removed.
- WHEN a temp stand's worktree no longer exists THEN the next `start` or `ls` removes it.
- WHEN `start preview --from <worktree>` runs while the preview serves another branch THEN it refuses and names that
  branch; with `--take` it switches, and the preview's database is recreated.
- WHEN the preview's database name equals the main stand's THEN the preview does not start.
- WHEN a project has no `scripts/stand.sh` THEN the tool says what to write and does nothing else.
- WHEN the preview is up THEN `fleet.py status` and the owner's status show it with its branch and link; temp stands
  are shown by neither.
- WHEN an agent with only the temp permission runs `stand.py start preview` THEN it is asked, as for any command not
  allowed.

## Decided with the owner

- The preview's database is its own, created and migrated by the project's script, since a branch may carry
  migrations.
- The preview is started on a human's request in an interactive session.
- Temp stands are a permission for agents, not a stand: there may be many at once, and they stay out of the status.
- The commands are start, stop, restart and logs, the same for every stand.

# Tasks: one stand tool, extended by each project

Spec: `proposal.md` in this directory. Each phase works end to end on its own; a pilot in a project comes before the
canon code, and the pilot code stays out of git until it works.

- [ ] **1. Temp stands for agents.**
  - `stand.py start|stop temp` and `ls`: a server-wide port range, an atomic claim, a detached start, a pid record,
    stop by record, removal of stands whose worktree is gone or that are too old, exit codes;
  - the `stand.sh` steps `build` and `run`, and its skeleton in the `dev-stand` skill;
  - the permission line for `start temp`, `stop temp` and `ls`, and `build-tdd`'s screenshot step names
    `stand.py start temp`.

  Pilot in a project with parallel agents. Tests: parallel starts get different ports, an unknown process on a port is
  skipped, no free port gives its own code, stop touches only its record, a stand whose worktree is gone is removed,
  no `stand.sh` gives a hint.
- [ ] **2. The preview.**
  - `start|stop|restart|logs preview --from <worktree> [--take]`;
  - the `stand.sh` steps `prepare`, `smoke` and `db`, with `STAND_URL` passed;
  - the database recreated on every switch, and refused when its name equals the main stand's;
  - `fleet_feed.py` and `fleet.py status` show the preview's branch;
  - the `dev-stand` skill says the preview goes only through the tool.

  Pilot: a branch with a migration, then a switch to another branch. Tests: refusal without `--take`, refusal on the
  main stand's database, the branch shown in the feed.
- [ ] **3. Next change: the main stand inside the tool.** `fleet.py stand` runs `stand.py restart main` when the
  project has `scripts/stand.sh`, and `stand-update.sh` folds into it.

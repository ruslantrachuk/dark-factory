# Tasks: one stand tool, extended by each project

Spec: `proposal.md` in this directory. The owner decided: the canon code first, the pilot in a project when the owner
says.

- [x] **1. Temp stands for agents.**
  - `stand.py start|stop temp` and `ls`: a server-wide port range, an atomic claim, a detached start in its own
    session, a pid record checked by the process's start time, stop by record, removal of stands whose worktree is
    gone or that are too old, exit codes;
  - the `stand.sh` steps `build` and `run`, and its skeleton in the `dev-stand` skill;
  - the permission line for `start temp`, `stop temp` and `ls`.

  Tests: parallel starts get different ports, an unknown process on a port is skipped, no free port gives its own
  code, stop touches only its record, a stand whose worktree is gone is removed, a reused pid is not the stand, no
  `stand.sh` gives a hint.
- [x] **2. The preview.**
  - `start|stop|restart|logs preview --from <worktree> [--take]`;
  - the `stand.sh` steps `prepare`, `smoke` and `db`, with `STAND_URL` passed;
  - the database recreated on every switch, and refused when its name equals the main stand's;
  - the status feed shows the preview's branch;
  - the `dev-stand` skill says the preview goes only through the tool.

  Tests: refusal without `--take`, refusal on the main stand's database, the branch shown in the feed.
- [ ] **3. Pilot in a project, when the owner says.** The project writes `scripts/stand.sh` from its live stand; temp
  with parallel agents; the preview from a branch with a migration, then a switch.
- [ ] **4. Next change: the main stand inside the tool.** `fleet.py stand` runs `stand.py restart main` when the
  project has `scripts/stand.sh`, and `stand-update.sh` folds into it.

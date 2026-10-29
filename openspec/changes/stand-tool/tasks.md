# Tasks: one stand tool, extended by each project

Spec: `proposal.md` in this directory.

- [ ] **1. Pilot in a project.** Port the pilot frontend preview to the split this change proposes: the mechanics in
  a draft `stand.py`, the stack in the project's `scripts/stand.sh`. Run `temp` with parallel agents and `preview`
  from a branch with a migration on its own database. Pilot code stays out of git until it works.
- [ ] **2. `scripts/stand.py`.** Commands `start|stop|restart|status|logs <stand> [--from] [--take]` and `ls`; an
  atomic port claim, detached start, a pid record, stop by record checked by its command line, wait until it
  listens, smoke, exit codes, `STAND_STATE`. Tests: parallel `temp` starts get different ports, an unknown process on
  a port is skipped, no free port gives its own code, stop touches only its record, the preview refuses another
  branch without `--take`, the preview refuses the main stand's DSN, no `stand.sh` gives a hint.
- [ ] **3. Configuration and status.** `stands.json` gains the preview's and temp's settings; `fleet_feed.py` and
  `fleet.py status` show the preview's branch from the tool's state; temp stands stay out of both. Tests.
- [ ] **4. Template and docs.** The base template's `dev-stand` skill: stands only through the tool, the `stand.sh`
  skeleton in place of the hand-written Start, Stop and Clean-up sections; `MANIFEST.md`; `build-tdd` step 7 names
  `stand.py start temp`; `provision-server` and `factory-status` where they show stands.
- [ ] **5. Next step, not this change.** The main stand's updater moves to `stand.py restart main`, after a project
  has run preview and temp.

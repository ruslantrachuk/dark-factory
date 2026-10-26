# Tasks: the server keeps the dev stand on main

Spec: `proposal.md` in this directory.

- [x] **1. Units.** `Project.stand` (`scripts/stand-update.sh`); `stand_service` (oneshot, `KillMode=process`,
  `fleet.py stand <checkout>`), `stand_timer` (every minute); `units_for` adds them only with the script; `provision`
  removes stale ones; `UNIT_SUFFIXES` lets `unprovision` remove them. Tests: units only with the script, unit text,
  stale units removed.
- [x] **2. Updater.** `fleet.py stand CHECKOUT [--retry]`: fetch, compare with origin's default branch, leave a dirty or
  other-branch checkout alone, fast-forward or detach, run the script, record the outcome in
  `~/.local/state/dark-factory/stand/<slug>.json`. Tests over real repositories: first run records without a build,
  a new commit builds once, a branch checkout fast-forwards, a failure waits for the next commit or `--retry`, dirty
  and other-branch checkouts untouched, `main` dispatch.
- [x] **3. Status.** `check_stand` → the `dev stand` line; `dev stand` in `NOTIFY_LABELS`. Test.
- [x] **4. Docs.** `provision-server` and `factory-status` skills; the base template's `dev-stand` skill (rule 5,
  "Update after a merge" with the script skeleton) and `MANIFEST.md`; `fleet.py` docstring.

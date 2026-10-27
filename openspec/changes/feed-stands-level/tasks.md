# Tasks: the status feed shows dev stands, the level, On-call's link and quota resets

Spec: `proposal.md` in this directory.

- [x] **1. Quota resets.** `quota.resets` from both cached windows. Test.
- [x] **2. On-call link.** `oncall_session_url` (DESK_NAME, with the template's `${DESK_NAME:-…}` default) over
  `named_session_url`, shared with `session_url`. Tests.
- [x] **3. Stands.** `stand_decls`, `probe` (cached 30 s), `stand_url` (https or quick-tunnel log; seam), `stand_git`
  (inside the project only), `stands`; the overlay refreshes `state` only. Tests over real repositories and a local
  HTTP server.
- [x] **4. Level.** `project_level` from `level.detect`. Tests.
- [x] **5. Docs.** The base template's `dev-stand` skill and `MANIFEST.md` describe `scripts/stands.json`.

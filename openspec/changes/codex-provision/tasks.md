# Tasks: codex-provision

## Phase 1 — the server runs Codex

- [x] `fleet.py`: `codex_settings` (FLEET_CODEX / _REMOTE / _DOMAINS), `codex_service` + `codex_timer` in
      `server_units`, removed without the setting (`CODEX_UNITS`), the domains step in `provision`
- [x] `codex_project.py domains <list>`: `features.network_proxy` + the profile's `network.domains`, replaced
- [x] `fleet.py status`: `check_codex` (login, daemon, versions) and `check_codex_quota`; a Codex problem goes to the watch
- [x] the provision-server skill: unit row, owner's step 6a
- [x] tests: `UnitsTest` (units with and without remote / domains, removal, `check_codex`), `test_codex_project.py` (domains)
- [x] live on this server: `check_codex` → daemon running 0.169.0; Codex quota 30d 44%; `provision --dry-run` with the
      settings lists the pair and the domains step

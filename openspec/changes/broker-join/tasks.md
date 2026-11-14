# Tasks

## Phase 1 — server, client, skill

- [x] broker.py: project join tokens and their scope; `/join` with origin, commit and fence checks; joined roles kept
      in the store; a catalog Claude role taken by a running session; `/hold`; `join-token`, `forget`.
- [x] fleet.py: `FLEET_BROKER_ADDR` → the unit's `BROKER_ADDR`.
- [x] broker_mcp.py: `join`/`poll`/`send`/`inbox`/`done`/`leave` from the shell; `--join` MCP tools.
- [x] Feed: `broker.roles[].title`, a joined role's `holder.session_url`; the page shows the title.
- [x] Skill `/dark-factory:join`.
- [x] Tests: token scope, every refusal, fetch of a pushed commit, origin forms, messages both ways, restart of the
      broker, MCP join and release, shell join and leave, a catalog role taken, poll output.

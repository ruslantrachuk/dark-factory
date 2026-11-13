# Tasks: codex-feed

## Phase 1 — the server side of the feed

- [x] `fleet_feed.py`: `quota_snapshot(now, agent)` from the agent's cache, `windows` and `usage_allowed`; `quotas`
- [x] `codex_rollout` / `codex_activity`: Codex sessions per checkout (working, last worked) from the rollouts
- [x] `agent_clis`: Claude's and Codex's versions, the daemon, the login (full feed only)
- [x] `project_row` / `build_feed` / `overlay`: `projects[].codex`, `working` and `last_worked_at` include Codex,
      `quotas` and `agents_cli` at the top level — the document stays version 2
- [x] tests: `CodexFeedTest` (rollouts, the Codex quota snapshot), schema and two Codex cases in `BuildFeedTest`
- [x] live: the feed built in memory on this server (not written): `quotas.codex` 30d 44%, `agents_cli.codex` daemon running

## Phase 2 — clients (not in this repository's server part)

- [ ] FactoryBar (Mac, iPhone, iPad, Watch, widgets): a ring per `quotas` entry, Codex mark, CLI versions — on the Mac
- [ ] the phone page `fleet_web/`: the same, when the apps settle the presentation

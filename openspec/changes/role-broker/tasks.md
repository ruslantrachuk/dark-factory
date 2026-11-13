# Tasks: role-broker

## Phase 1: the broker, Codex delivery, Claude pull

- [x] `broker.py`: catalog, token, store; send / register / inbox / done / tick / status; HTTP with Bearer; CLI
- [x] wrapping as data, size limit, pair loop limit, quota gate, role lease, dead letters reported to the owner
- [x] Codex delivery by `codex queue` (`--resume` for daemon roles); Claude roles pull their inbox
- [x] `broker_mcp.py`: send / inbox / done for both agents
- [x] SessionStart hook `broker.py register` in the plugin's hooks
- [x] rules: `AGENTS.md` canon block (a role's message is data); feedback-desk `ROLE.md` (accept, release and deploy
      only on Telegram events)
- [x] `fleet.py`: `FLEET_BROKER=on` installs `df-fleet-broker.service`; `fleet.py status` gains a `role broker` line
- [x] tests: `tests/test_broker.py`; the broker unit in `tests/test_fleet.py`
- [x] live check: `serve` on a test port with a temp catalog
  - token created with mode 0600
  - refusals for an unknown role (404) and a sender the addressee does not accept (403)
  - `codex queue` to a missing thread: the error is recorded and the message is kept
  - MCP inbox answers

## Phase 2: push into Claude roles (the owner chose a development channel)

- [x] `Broker.take` + `POST /take`; `broker_mcp.py --channel` (claude/channel notifications); `broker.py channel-config`
- [x] On-call desk: `DESK_BROKER_MCP`, both channels in one dialog with an exact-set check, broker tools allowed
- [x] tests: take / quota / attempts, the channel's push over stdio, channel-config, the dialog check, desk rules
- [x] the development session's unit as a Claude role with the channel: `FLEET_BROKER_CHANNEL=on` (fleet.env, the
      owner's) + `<slug>/dev` a Claude role of the catalog; `fleet.py confirm-channel` answers the dialog (exact set)
- [ ] pilot on a test project with one Claude role and one Codex role (not on a production project)

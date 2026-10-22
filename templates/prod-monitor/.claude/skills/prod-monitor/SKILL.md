---
name: prod-monitor
description: Bring up from scratch, check or shut down the prod monitoring loop (watchdog + monitor on the Claude Agent SDK + monitor channel to the On-call agent). Use on "bring up monitoring", "prod monitor", "what's with the monitor", "check prod with the monitor", "shut down the monitor", after a server reboot.
---

# Skill `prod-monitor` — prod monitoring loop

The mechanics are in the script `scripts/ops/prod_monitor/prod-monitor.sh`; the skill is the order and the handling of non-standard cases.
Factory module `prod-monitor`; the project-specific parts are `project.py` and `incidents.md`.

## How it works

```
(script) WATCHDOG, cron once a minute, no model — checks.py + project.RULES over the prod DB snapshot,
   │      failed release, DB access
   │ wakes on a change of anomalies / once an hour while one persists / scheduled slots project.SLOT_HOURS
   ▼
[AGENT] MONITOR — monitor.py, Claude Agent SDK, read-only (prod DB by check name, hosting, gh, http)
   │      catalogue incidents.md; verdict ok/warn/crit; ok after crit = resolved; repeats by key not sent for 6 h
   │ POST 127.0.0.1:<port>/event, Authorization: Bearer <state/prod_monitor/channel.token>
   ▼
(script) monitor CHANNEL — channel/server.ts (Bun, Claude Code Channels) → event in the On-call session
   ▼
[AGENT] ON-CALL (ROLE.md, monitor item) → feedback group (reply) + development session (SendMessage)
```
Fallback path: the channel did not accept → warn/crit/resolved straight to the group via Bot API `sendMessage`
(send only; never touch getUpdates — the bot has a single reader, the On-call plugin). The monitor did not answer
(including an exhausted subscription quota) while there are anomalies → the watchdog sends the alert itself the same way.

The code lives in the repo and runs from a copy `~/<pfx>-monitor/prod_monitor/` (venv next to it, state and log in
`~/<pfx>-monitor/state/prod_monitor/`). After editing the code, `project.py` or `incidents.md` — run `install` again;
after a change in `channel/` — `up` (the On-call session starts the channel server).

The channel accepts an event only with the shared secret: `install` generates `state/prod_monitor/channel.token`
(0600) once, writes it into `mcp.json` (0600) for `server.ts`, and `deliver.py` sends it as a bearer token. Another
process on the machine without the file cannot inject events into the On-call session. Rotate: delete the file, `up`.

## Bring up from scratch

1. **Preconditions** (checked by `install`): the On-call agent (feedback-desk module) is running; prod DB access via a
   read-only role in `~/.config/<project>/prod-watch.env` (`PROD_RO_DATABASE_URL`); Bun, uv, `gh` logged in;
   the hosting MCP in the **local** Claude Code config for the main checkout; `project.py` and the header of
   `prod-monitor.sh` are filled in.
2. **Subscription token** — the owner does it personally, once a year: `scripts/ops/prod_monitor/setup-token.sh` in their
   own terminal. Do not read or print the token; only check that the file exists. Without the file the monitor runs on the
   current Claude Code login (which expires).
3. `prod-monitor.sh up` — install + restart of the On-call agent with the channel. The group is ~1 min without the On-call
   agent: if it is in the middle of a conversation — run `install` first and restart later.
4. `prod-monitor.sh test` → the group gets "Monitor: delivery check…". Nothing appeared — `tmux capture-pane -p -t <On-call tmux>`.
5. `prod-monitor.sh status` — all items ✓. `prod-monitor.sh run` — the first real pass (~40 s): the verdict is in
   `state/prod_monitor/monitor_last.json`; false warns — add the background to `incidents.md`.

## Routine actions

- **What's with the monitor**: `status`; watchdog log `~/<pfx>-monitor/state/prod_monitor/watchdog.log`.
- **Check prod now**: `run` (~40 s, uses subscription quota — do not run in a loop).
- **Shut down**: `down` removes the watchdog from cron. The channel goes away at the next On-call restart without `DESK_MONITOR_MCP`.
- **After a server reboot**: `scripts/feedback-desk.sh up` (also brings up the channel if mcp.json exists) → `status`.

## Owner decisions to make during setup

- Who in the group may authorise "Deploy"/"restart": numeric Telegram ids in `DESK_DEPLOY_ALLOW`
  (`.claude/feedback-desk/config.env`). The On-call agent forwards such a reply as a deploy request with the sender's
  `from_id`; nothing in the loop executes a deploy. The development session acts only if `from_id` is in the list,
  otherwise it asks the owner in the owner's own channel. Empty list — the owner only.
- What the developer does alone (for example, restart and rebuild up to 5 times in a row, then ask the group), and
  what only the owner does (writes to the prod DB, env, scaling, deletion — always the owner only).
- The monitor fixes nothing — this is a property of the module, not a setting.

## Non-standard cases

- `server:monitor · no MCP server configured with that name` in the On-call header is cosmetic, events get through.
  Routing rules are in ROLE.md, not in the channel instructions.
- Do not load `plugin:telegram` into the monitor or anywhere else: on start it kills the other reader of the token. That is
  why the monitor reads `local` settings only (test in `test_prod_monitor.py`); with `user` the On-call agent loses Telegram.
- http_probe from the server returns 000 while prod is alive — the server's network to the hosting; add it to `incidents.md` as background.
- Two projects on one machine — different `<pfx>` and channel ports (8790, 8791, …).
- Channels is a research preview: after a Claude Code auto-update run `prod-monitor.sh test`.

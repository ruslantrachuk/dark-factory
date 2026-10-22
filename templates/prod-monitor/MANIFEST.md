# prod-monitor — module manifest

> **Prod monitoring by an agent**: once a minute a watchdog, with no model, looks at a snapshot of the prod DB and
> the release; on an anomaly or at a scheduled slot it wakes the monitor — an agent on the Claude Agent SDK that only
> reads (DB, hosting, gh, http), checks against the incident catalogue and returns a verdict; the On-call agent carries
> a real outage to the feedback group and the development session. Installed **on top of base and feedback-desk**.
>
> **Status: experimental.** Not yet proven on a real outage.
> Next to it is the [observability](../observability/MANIFEST.md) module (metrics, dashboard, cloud alerts): there the
> signal is a metric threshold, here it is an agent that reads logs and data and writes to people in plain language.
> Practice — [Observability](../../docs/practices/observability.md); investigating what was found —
> [Incident investigation](../../docs/practices/incidents.md).

> **Seam:** production data snapshot = Postgres (`psycopg`, a read-only role); client chat fallback = the Telegram Bot API; hosting = the read tools in `project.py`. To use another tool, rewrite `checks.py collect()`, `deliver.py` (`post_telegram_direct`) and `HOSTING_READ` in `project.py`.

## Why

Prod outages tend to be reported by users: for example, scheduled jobs stop going out for a day and nothing in the
loop notices (a stuck task scheduler). Cloud alerts only catch what already has a metric, and they speak the language
of metrics. The monitor agent looks where a developer would look (hosting logs, queues in the DB, the release), knows
the project's known background noise, and writes to the group only about a real outage — in plain text.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/ops/prod_monitor/project.py` | **project-specific, fill in**: name, prod URL, paths outside the repo, the `SNAPSHOT_SQL` snapshot and `RULES`, agent checks `CHECKS`, hosting tools (read / forbidden), project description and inspection order for the agent |
| `scripts/ops/prod_monitor/incidents.md` | **project-specific**: catalogue of incidents and background — name, signs, verdict, step |
| `scripts/ops/prod_monitor/watchdog.py` | watchdog (cron once a minute): when to wake the monitor, fallback alert without a model |
| `scripts/ops/prod_monitor/checks.py`, `rules.py` | prod DB snapshot via a read-only role + failed release; rule helpers `count_at_least`, `seconds_above`, `stale_after` |
| `scripts/ops/prod_monitor/monitor.py` | agent on the Claude Agent SDK: no built-in tools, `local` settings only, writes to hosting forbidden by list; JSON verdict |
| `scripts/ops/prod_monitor/verdict.py` | verdict parsing; the same problem (by `key`) is repeated at most once per 6 h; `resolved` only after crit |
| `scripts/ops/prod_monitor/deliver.py` | monitor channel with the shared secret → if it refuses, warn/crit/resolved straight to the group via Bot API (`sendMessage` only) |
| `scripts/ops/prod_monitor/channel/` | Claude Code Channels channel on Bun: POST from 127.0.0.1 with `Authorization: Bearer <secret>` → event in the On-call session |
| `scripts/ops/prod_monitor/prod-monitor.sh` | `install` / `up` / `status` / `test` / `run` / `down`; copy outside the checkout, venv, channel secret, mcp.json, desk.env from the On-call config, cron |
| `scripts/ops/prod_monitor/setup-token.sh` | one-year subscription token (`claude setup-token`) — run by the owner, the token is never printed |
| `scripts/ops/prod_monitor/test_prod_monitor.py` | rules, when to wake, what to send, the channel secret, agent isolation — `python -m pytest scripts/ops/prod_monitor` |
| `.claude/skills/prod-monitor/SKILL.md` | bring-up from scratch, routine actions, owner decisions, non-standard cases |
| `.claude/feedback-desk/ROLE.monitor.md` | append to the On-call role: two inbound channels and the item about monitor events |

Channel support in the On-call agent itself lives in the feedback-desk module (`DESK_MONITOR_MCP` in `config.env`,
the development channels flag and the confirmation in `feedback-desk.sh`).

## Properties (do not change without a reason)

- **The model is called rarely.** Minute checks are a script; the agent runs when the set of anomalies changes,
  once an hour while one persists, and at three scheduled slots a day. The subscription quota is shared with all
  sessions (see the quota guard of the dark-factory plugin).
- **The monitor fixes nothing.** No built-in tools (`tools=[]`), writes to hosting are in `disallowed_tools`,
  the DB is a read-only role plus `default_transaction_read_only`, the agent writes no SQL — it picks a check by name.
- **`local` settings only.** The `user` source loads `plugin:telegram`, which on start kills the reader of the bot
  token — the On-call agent loses Telegram. Project settings, and with them the dark-factory plugin's hooks (the quota guard), are not loaded by the monitor either.
- **The alert gets through without a model.** If the monitor crashed, hung, or the quota is exhausted, the watchdog
  sends the anomalies itself; if the channel did not accept, straight to the group.
- **The group hears only about a real outage.** No "all good", no risks; known background goes into the catalogue,
  not the group; the same problem at most once every 6 hours.
- **Runs from a copy outside the checkout** — switching branches in the main checkout does not break the loop.
- **Only the monitor can post to the channel.** `install` generates `state/prod_monitor/channel.token` (0600) once and
  writes it into `mcp.json` (0600); `server.ts` refuses `/event` without the matching bearer token (constant-time
  compare) or when it has no token. Another process on the machine cannot inject events into the On-call session.
- **Nothing in the loop deploys.** A "Deploy" reply in the group reaches the development session as a deploy request
  with the sender's numeric id; it acts only for ids in `DESK_DEPLOY_ALLOW` (feedback-desk `config.env`), otherwise
  it asks the owner.

## Dependencies

The feedback-desk module (the On-call agent is running); Claude Code with Channels; Bun; uv and Python 3.12; `gh`
logged in; cron; a Claude subscription (token from `claude setup-token`); a read-only prod DB role; a hosting MCP in the
local Claude Code config (`<your hosting>`). The prod DB is currently Postgres (psycopg); another snapshot source means
your own `collect()` in `checks.py`, through the canon.

## Setup

1. Copy `scripts/ops/prod_monitor/` and `.claude/skills/prod-monitor/`; run `python -m pytest scripts/ops/prod_monitor`.
2. Fill in `project.py` (`<…>` placeholders; an illustrative example is in the comments) and the header of
   `prod-monitor.sh` (`<pfx>`, `<project>`, channel port — one per project on the machine). Cover `RULES` with a test next to it.
3. Catalogue `incidents.md`: known incidents and project background (without the background the monitor will alarm the group).
4. Append `ROLE.monitor.md` to `.claude/feedback-desk/ROLE.md`; fill in the development session name and the
   background. Who may authorise "Deploy" — numeric ids in `DESK_DEPLOY_ALLOW` in `.claude/feedback-desk/config.env`.
5. Owner: read-only prod DB role → `~/.config/<project>/prod-watch.env`; hosting MCP in the local config;
   `setup-token.sh`.
6. `prod-monitor.sh up` → `test` (a message in the group) → `status` (all ✓) → `run` (first verdict, sort out false warns).
7. A line in the project's CLAUDE.md (§Environment): the loop, `prod-monitor.sh status`, deploy authorisation by `DESK_DEPLOY_ALLOW`;
   an entry in the devlog and in the factory registry (`registry.md`, see `registry.example.md`).

## Not covered (deliberately)

- A process that runs as the same user can read the channel secret; the secret separates other users and services,
  not code running under the owner's account.
- Autostart after reboot — shared with feedback-desk (`feedback-desk.sh up` also brings up the channel).
- One snapshot source — Postgres; hosting other than through the MCP in `project.py` is not generalised.

## Abandon criterion

The module is removed if within a month a prod outage was again found by users before the monitor, or the group got
false alarms more often than real ones (the background catalogue does not help) — then hold the loop differently
(observability alerts).

## Design notes

Everything project-specific lives in `project.py` and `incidents.md`; watchdog rules are helpers over the snapshot
row; the group, the plugin state directory, the development session and the port come from the On-call config
(`desk.env`, `mcp.json`); `setup-token` is in bash; directories outside the repo are keyed by `<pfx>`/`<project>`.

## Open questions

- [ ] verification on a real outage and after a Claude Code auto-update;
- [ ] second project — revisit the `project.py` interface.

# Privacy

Dark factory is a Claude Code plugin and a set of templates that run on your own machine. Its author runs no service
for it: nothing is collected, there is no telemetry, and no data is sent to the author.

## What stays on your machine

- The guard's audit log (`.claude/state/audit.jsonl` in the project) and the fence settings (`.claude/fences.env`).
- The quota guard's cache and log (`~/.cache/claude-quota.json`, `claude-quota.log`, `claude-quota-agents.json`; for Codex `codex-quota*.json`).
- The role broker's messages and state (`~/.local/state/dark-factory/broker.db`), its catalog and tokens (`~/.config/dark-factory/`), and the stands' records (`~/.local/state/dark-factory/stands/`).
- The task queue (`bd`), the factory's project list (`~/.config/dark-factory/`) and the session settings of each project.

## What leaves it, and where it goes

- **Anthropic.** The quota guard learns the subscription's usage from one short request through your own `claude` CLI
  (no more often than every 10 minutes), unless the status line feeds it the numbers. No token is read.
- **OpenAI, if you run Codex.** The quota guard learns the Codex plan's usage from `account/rateLimits/read` through your own
  `codex app-server`, with no model request. Codex itself talks to OpenAI under your own login; the plugin reads no token.
- **GitHub.** `gh` and `git`, with your own login, for pushes, pull requests, CI status and releases; Claude Code and Codex
  fetch the plugin from the repository (a marketplace add or update). The weekly analytics report, when you turn it on, is
  a pull request to a repository of yours.
- **Modules you install yourself:** the On-call agent reads and answers the client chat through the Telegram plugin; the
  production monitor reads a snapshot through a read-only database role you create and posts to that chat; the board is
  Linear through its own MCP server. Each one reaches only its own service, with credentials you give it.

- **The vulnerability database.** Once a day `vulns.py` sends the names and versions of the packages a project's lock
  files pin (nothing else: no code, no file names) to the public OSV API (`api.osv.dev`, run by Google), and downloads
  CISA's public catalogue of known exploited vulnerabilities. `VULN_CHECK=off` in the project's
  `.claude/factory/session.env` turns it off.

- **Your phone, if you set up the status page.** With `FLEET_FEED_ADDR` in the server's `fleet.env`, `fleet.py serve`
  serves a status feed on that address (`/status.json`, and `/events` pushing every change): project names, whether
  their sessions and agents are working, the On-call and watchdog state, the quota numbers, and the link to each
  project's session. Only a private address is accepted (Tailscale on the reference setup); without
  `FLEET_FEED_TOKEN` there is no login, so anyone on that network can read it. With it every request must carry the
  token — the setting for a tunnel that makes the feed reachable from the internet (Tailscale Funnel on the reference
  setup); whoever holds the token can read the feed, so it lives only on your devices. With `FLEET_FEED_PAGE=on` the
  same address serves the status page; it only reads the feed and sends nothing back.

- **The role broker, if you turn it on.** `broker.py serve` listens on a loopback address, or on a private one you set
  (`FLEET_BROKER_ADDR`; Tailscale on the reference setup; a public address is refused). A session on another machine joins
  and exchanges messages with it over plain HTTP on that network, carrying a join token of its project; the messages
  (text the roles send each other) are kept on the server and nowhere else.
- **Your own commands.** `FLEET_NOTIFY_CMD` runs the command you give it with a status message on its standard input
  (a chat bot, for instance); the queue review and the routines listing run short headless Claude requests on the
  server, under your subscription.

Nothing else is contacted. What each of those services does with the data is governed by its own policy.

## Questions

Open an issue: <https://github.com/ruslantrachuk/dark-factory/issues>.

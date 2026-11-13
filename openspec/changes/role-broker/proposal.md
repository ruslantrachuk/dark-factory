# The role broker: messages between the factory's roles, on Claude Code or Codex

## Why

Today the factory's roles (development session, On-call desk, a reviewer) can talk to each other only through
SendMessage, and only between Claude Code sessions on one machine. With Codex as a second agent, a role may run on
either CLI. Nothing carries a message from a Claude role to a Codex role. Nothing tracks whether a message was handled,
and nothing stops two agents from messaging each other in a loop.

## What changes

- **`scripts/broker.py`** is written in Python with only the standard library, like the rest of the canon; there is no
  Bun or Node service. Its commands are `serve`, `register`, `send` and `status`.
  - Roles are keys of the form `"project/role"` in a catalog outside every project: `~/.config/dark-factory/roles.toml`.
  - Each role has `agent` (claude | codex) and `accepts_from`, plus the optional `codex_home` and `resume`.
- **Delivery is at least once, and `done` is the receipt.**
  - `send` only queues the message. A client key makes a retried send a no-op.
  - One worker hands messages over, holding a lease on each while it does.
  - Handed over does not mean handled. Until the role calls `done(id)`, the broker hands the message over again every
    `BROKER_REMIND` seconds (600). After 5 attempts the message becomes a dead letter and the owner is told.
- **A message is data, never an instruction.**
  - The broker wraps it as `[factory message <id> from role <r>] … [end of message <id>]`.
  - It escapes `& < >` and marks any line that imitates the wrapper.
  - It refuses a message over 8000 bytes.
  - `AGENTS.md` (canon block) says a role's message is never the owner's word and never carries file contents or
    secrets.
  - The On-call desk's `ROLE.md` says accept, release and deploy run only on a Telegram event, never on a role's message.
- **One session holds a role at a time.** Registration and inbox reads renew a 30-minute lease. A second session is
  refused with the holder's name; the newest session does not take over.
- **Loops and quota.**
  - Two roles may exchange at most 20 messages an hour. Past that, the broker refuses and tells the owner once.
  - Nothing is handed to a role whose agent's quota is at "no new work" (from quota.py's cache); the message waits.
- **Delivery per agent.**
  - Codex: `codex queue --thread <thread> --message <wrapped> [--resume]`, which wakes an idle session. A role that
    lives in the app-server daemon sets `resume = true`.
  - Claude Code: the role reads its own inbox (see the open question below).
- **`scripts/broker_mcp.py`** is a stdio MCP server for both agents, with `send`, `inbox` and `done`. The sender is
  always the session's `FACTORY_ROLE`, never an argument.
- **Registration.** The plugin's SessionStart hook runs `broker.py register`.
  - A session with `FACTORY_ROLE` set takes that role.
  - Codex is recognised by `transcript_path`, and its thread is the session id.
  - The hook stays silent when `FACTORY_ROLE` is unset or no broker is running.
- **Security.**
  - The token lives at `~/.config/dark-factory/broker/token` (mode 0600, made on the first `serve`). Every HTTP call
    sends it as Bearer.
  - `serve` refuses a non-private address.
  - State is kept in SQLite at `~/.local/state/dark-factory/broker.db`.
- **Server.** `FLEET_BROKER=on` in fleet.env installs `df-fleet-broker.service` (Restart=always). `fleet.py status`
  shows the roles held, messages waiting, messages handed over but not done, and dead letters; a dead letter shows as ○.

## Decisions

- **Python stdlib instead of the Bun service in the plan.** One language, nothing extra to install on the server, and
  the broker is small enough that SQLite from the standard library covers it.
- **Claude roles pull their inbox for now.** Pushing into a live Claude Code session needs a channel MCP server. A
  custom channel loads only with `--dangerously-load-development-channels`, which the factory's rules forbid.

## Open questions

- **How to push into a Claude role (the owner's choice).**
  - (a) Accept the development-channels flag in role services.
  - (b) Spike Claude Code's own messaging socket (the one SendMessage uses) as the delivery path.
  - (c) Keep the pull: the role reads its inbox on its own turns, and the broker reminds it.
  - Recommendation: (b) as a spike, with (c) as the fallback.

## Acceptance

- WHEN a role sends to a role whose `accepts_from` does not list it THEN the broker answers 403 and stores nothing.
- WHEN the same send is retried with the same client key THEN only one message exists.
- WHEN a message is handed over and `done` is not called THEN it is handed over again after REMIND, and after ATTEMPTS
  it becomes a dead letter and the owner is told once.
- WHEN a Codex role's thread does not exist THEN `codex queue` fails, the broker records the error and the message keeps
  waiting (checked live on this server with Codex 0.169).
- WHEN two roles exchange more than PAIR_LIMIT messages in an hour THEN the next send gets 429 and the owner is told
  once.
- WHEN the addressee's agent quota is at "no new work" THEN nothing is handed over until it clears.
- WHEN a second session registers a role that is already held THEN it gets 409 with the holder's name.
- WHEN a message contains `<channel>` or the line `[end of message x]` THEN the addressee sees it escaped and marked.

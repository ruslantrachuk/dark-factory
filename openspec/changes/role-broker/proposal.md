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
  - Claude Code: the role's broker channel pushes it into the session (see Decisions); without the channel the role reads its inbox.
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
- **Push into Claude roles through a development channel (the owner chose option (a), 2026-11-13).** The other
  options were a spike on Claude Code's messaging socket, or a pull only.
  - The broker's channel is a development channel, exactly like the prod monitor's channel that the On-call desk
    already loads: `--dangerously-load-development-channels server:broker`.
  - `broker_mcp.py --channel` declares `claude/channel` and polls `POST /take` for its role every `BROKER_POLL` seconds
    (5).
  - `take` follows the worker's rules: lease, REMIND, the quota gate, dead letters by the tick. It renews the role's
    lease, because the channel exits with its session.
  - Each message arrives as `<channel source="broker" from_role message_id>` with the wrapped text.
  - `broker.py channel-config <role>` writes the channel's config next to the token (Claude roles only) and prints the
    launch flags.
  - The On-call desk loads it with `DESK_BROKER_MCP` under the same `DESK_ACCEPT_DEV_CHANNEL=1` opt-in. Its start
    dialog is confirmed only when it lists exactly the channels asked for.
  - A role without the channel still reads its inbox.

## Open questions

- **The dialog for two development channels at once is unverified.** A probe was refused by the auto-mode classifier,
  so the format of its "Channels:" line is not checked. The check accepts the exact set in any order and with any
  separator. If the first start of a desk with both channels says "did not see the development channel prompt", the
  owner looks at `tmux attach` and confirms.
- **The development session as a role** (a channel in its unit) is not wired yet. The desk comes first.

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

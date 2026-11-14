# Any session of a project joins the factory as a role it names

## Why

The role broker knew only the roles of its catalog, held by sessions on the factory server. The owner works in
sessions elsewhere too — Claude Code on a laptop, a session for one client's VPN — and wants one of them to take a role
of its project, under a name the owner gives it ("On-call for the VPN", "UI dev"), show in the status apps with a link
to it, and exchange messages with the project's other roles. In the end these agents exchange code, so a role is only
for a session of the same project and under the project's fences.

## What changes

**The broker (server):**
- **A token per project.** `broker.py join-token <slug>` makes (or prints, or with `--rotate` replaces) the project's
  join token in `~/.config/dark-factory/broker/projects/<slug>.token` (0600, outside every project). A request with it
  may only join, take, read the inbox, mark done, release and send — all within the roles `<slug>/*`. The broker's own
  token never leaves the server; `/status` and `/register` refuse a project token.
- **`POST /join`** `{name, title, agent, origin, sha, fence, session_url, holder}` makes the role `<slug>/<name>` on
  the fly, checked against the project's checkout on the server (the fleet's projects file):
  - `origin` — the same repository (normalized: scheme, user, `.git`, case of the host);
  - `sha` — a commit the checkout has (`git cat-file -e`, after one `git fetch` when it does not);
  - `fence` — not below the project's `FENCE_LEVEL` on origin's main branch (solo < standard < team).
  A Claude role of the catalog is held by the joining session, not redefined; a Codex one is refused. The joined role is kept in the broker's store (it survives a restart), held
  by its `holder` like a Claude role's MCP process (`/take` every poll, `CLAIM` seconds), and accepts messages from
  the project's roles; the project's roles accept messages from it.
- **`BROKER_ADDR`** of the unit comes from `FLEET_BROKER_ADDR` in fleet.env (a Tailscale or private address; default
  loopback): the owner's opt-in to reach the broker from another machine of the tailnet.
- `broker.py forget <role>` removes a joined role.

**The joining session (client):** `/dark-factory:join` (skill), steps run by `scripts/broker_mcp.py` from the
session's shell — so a running session joins without a restart (an MCP server or a channel loads only at a session's
start):
- `join "<title>" [--role <id>]` refuses outside a project of the factory, without `.claude/fences.env`, or with the
  plugin not enabled and installed for the checkout — the session must run under the fences. `--role dev` (any Claude
  role of the catalog) lets a running dev or On-call session take the role it already plays;
- the broker's address and the project token come from `~/.config/dark-factory/join/<slug>.env` (`BROKER_URL=`,
  `BROKER_TOKEN=`), which the owner copies once; on the factory server the local broker and its join token;
- it sends the checkout's origin, `HEAD`, fence level and the session's claude.ai link (the Remote Control id of the
  session's own process, `~/.claude/sessions/<pid>.json`, found up the process tree — `ps`, so it works on macOS);
- `poll <role>` under the session's Monitor gets each message the moment it is sent — a long-poll: `/take` with
  `wait` is held open up to 25 s until a message is due — and each message wakes the session; every poll renews the
  hold; when the session and its Monitor are gone the role lapses in `CLAIM` seconds;
- `send`, `inbox`, `done`, `leave`.
- `broker_mcp.py --join` offers the same as MCP tools for sessions started after it was added for the user.

**The feed:** `broker.roles[].title` (the joined role's name as typed), and `holder.session_url` of a joined role from
what it reported.

## Acceptance

- WHEN a session of the project joins with its project token THEN the role `<slug>/<name>` appears in `broker.py
  status` and the feed with its title and its session link, and a message from the project's dev role reaches it.
- WHEN the origin differs, the commit is unknown to the checkout, or the fence level is below the project's THEN the
  join is refused with the reason, and nothing is stored.
- WHEN a project token is used for another project's role, for `/status` or `/register` THEN 403.
- WHEN the session ends THEN its role is free within a minute (free in the feed).
- WHEN a running dev session joins with `--role dev` THEN it holds `<slug>/dev` without a restart.
- WHEN the checkout has no `.claude/fences.env` or the plugin is not loaded THEN `/dark-factory:join` refuses before
  any request.

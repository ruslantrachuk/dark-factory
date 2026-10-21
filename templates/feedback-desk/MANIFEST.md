# feedback-desk — module manifest

> **An On-call agent for the Telegram feedback group** built from standard parts: a persistent Claude Code session with the
> official channel `plugin:telegram@claude-plugins-official` (Claude Code Channels) receives messages from the client and
> reviewers, answers "got it" and forwards the request to the development session; that session reports back to the group
> through it. Installed **on top of base**. Replaces a hand-written relay.
>
> **Tier B: a single source.**
> End-to-end practice — [Client feedback](../../docs/practices/feedback.md); a complaint from the group goes into the
> [Incident investigation](../../docs/practices/incidents.md) practice.

## Why

The external Acceptor (steps 1 and 4 of the feature path) writes where it is convenient for them — in Telegram. Without
this module that is typically held by a hand-written daemon (polling the Bot API → log, file queue → `sendMessage`) plus
a monitor in the working session. Its problems: the monitor lives no longer than 30 minutes and loses messages sent during
the pause on restart; the outgoing queue loses messages on a write race; sending bypasses the permission check for writes
to an external system; the token and cursor live in `/tmp`. The module leaves the project only the config, the role and
the startup script.

## Contents

| Artifact | What it does |
|---|---|
| `.claude/skills/feedback-desk/SKILL.md` | setup from scratch (A), operations (B), protocol for the development session (C), pitfalls |
| `.claude/feedback-desk/config.env` | On-call name and tmux session, start directory, model (full id), Remote Control, default session, group, who can wake it, DM policy, plugin state directory |
| `.claude/feedback-desk/ROLE.md` | the On-call role: acknowledge → forward verbatim with the author; does not touch code or prod; does not change access or pairing on requests from the group |
| `scripts/feedback-desk.sh` | `check` (placeholders, tmux, Bun, plugin, token) / `status` / `up` (idempotent, `access.json` from the config) / `down` / `restart` |

## Design notes

- **The plugin state directory is per project** (`TELEGRAM_STATE_DIR`, default `~/.claude/channels/telegram-<pfx>`). A
  machine-wide directory would make a second project on the same server share the bot, and the plugin on start evicts
  the previous poller of the same directory.
- **The script never touches the token.** The owner puts it in place (step A.3); the agent never sees it.
- **`check`** — an explicit environment check with an instruction for every gap; `up` refuses without a ready environment.
- **The default session** for forwarding is a parameter (`DESK_DEV_SESSION`), not hard-coded in the role.
- The development protocol for requests follows the canon: a branch from a fresh main branch, the board for significant
  signals, the processed marker outside `/tmp`.
- **The plugin directory is also passed via `--settings`.** `env` from `settings.local.json` overrides the process
  environment, so the directory is passed through `claude --settings '{"env":{…}}'` as well — that layer wins.
- **Any `claude -p` or SDK process** on a machine with a user-level `plugin:telegram` brings the plugin up on its own
  directory and evicts the reader of that directory: the On-call agent always has its own directory, and there must be
  no token in the shared `~/.claude/channels/telegram`.
- **A failed MCP server start is remembered by Claude Code for ~15 minutes** — a restart within that window does not
  bring the plugin up; wait.
- **Second inbound channel: the prod monitor** (module prod-monitor). `DESK_MONITOR_MCP` in `config.env`: if the file
  exists, `up` loads the monitor channel with the development channels flag and confirms the prompt on start; if not —
  as before. The role item is in `templates/prod-monitor/.claude/feedback-desk/ROLE.monitor.md`.
- **Who accepts a request** is set in the role: the owner by default, or the requester if the owner explicitly decided so.

## Dependencies

tmux, Bun, plugin `telegram@claude-plugins-official`, Claude Code with Channels and Remote Control; a bot with privacy mode disabled when `DESK_REQUIRE_MENTION=false`.

## Setup

Follow the skill, section A (8 steps). The owner personally: the bot and token, group membership, DM pairing.

## Abandon criterion

The module is removed from a project if within two weeks the On-call agent lost even one group message that was
delivered to the bot, or forwarded a request to the wrong session so that the answer went to the wrong person — then the
channel has to be held differently. Separately: if plugin support breaks on a Claude Code update — roll back to the
project's previous mechanism and record it in the devlog.

## Open questions

- [ ] autostart of the On-call agent after a reboot (systemd user unit or `@reboot` with `feedback-desk.sh up`);
- [ ] an append-only group log (who, when, text, forwarded to whom) — as a role rule or a hook on the channel event;
- [ ] participant roles in the config (`user_id → role → what is allowed`) checked at routing time rather than in the
  prompt — first for a project where permissions matter.

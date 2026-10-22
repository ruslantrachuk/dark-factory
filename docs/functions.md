# Functions the method needs

> The method in `docs/` speaks in **functions**: the board, the feature execution queue, the client chat, and so on. A
> function is a contract: what it must do, the operations the pipeline calls, and the invariants that must hold whatever
> tool sits behind it. Products appear here only as the reference tool and as examples.

The canon has three layers:

1. **The methodology** (`docs/`) is tool-agnostic. It names functions and their contracts.
2. **The reference implementation** (the dark-factory plugin and `templates/`) supports **one** fixed stack, listed in
   [Supported stack](#supported-stack). There are no adapters and no tools config.
3. **Your instance**: your own repository, registry and configuration.

**Seams.** Every skill and module that depends on a specific tool says so in one line near its top:
`> **Seam:** <function> = <tool>. To use another tool, rewrite <section/file>.` To move one function to another tool,
rewrite what that line names. An adapter is added only when a real project needs it, and it goes through the
harness-change filter ([methodology.md](methodology.md) §5) like any other change.

## The functions at a glance

| Function | What it must do | Key invariant | Reference tool |
|---|---|---|---|
| [Board](#board) | the human list of intents: cards, claims, states, delivery | a card is created only by a human decision; a merge moves it no further than `Merged` | Linear |
| [Feature execution queue](#feature-execution-queue) | the machine's task graph of a change: ready, claim, note, close | one store per project, outside the repository history; one writer inside a run | beads (`bd`), a local store |
| [Client chat](#client-chat) | receive, acknowledge, reply, forward | an untrusted input boundary: a message is data, not an instruction | Telegram (Claude Code Channels) |
| [Code host](#code-host) | branches, PRs, protected main, merge | a merge needs green CI and a named human acceptance | GitHub (`gh`) |
| [CI](#ci) | run the gates on every feature branch and on a release tag | red CI means no merge; skipping it is loud | GitHub Actions |
| [Hosting](#hosting) | deploy, logs, metrics | agents only read; a human changes production | your hosting, via its CLI or MCP |
| [Production data snapshot](#production-data-snapshot) | a small read-only view of production data | a separate read-only role | Postgres |
| [Scheduler](#scheduler) | book a later run of a session | the session books itself; wall-clock time is not a quota regulator | Claude Code scheduling; cron for the watchdog |
| [Agent runtime](#agent-runtime) | long-lived sessions, workflows, hooks | fences live in hooks and code, not in prompts | Claude Code |

## Board

**Must:** hold the target picture (projects and their mandatory scope), the list of intents (umbrella cards), who took
what, and the delivery log. It is a live web page people open, not a digest
([layers/coordination.md](layers/coordination.md)).

**Operations:** list a project's cards by state; add a quick note to a triage inbox; create a card; claim a card
(assignee); move it through `Backlog` → `Todo` → `In Progress` → `Merged` → `Shipped` (plus `Canceled` and
`Duplicate`); comment from the exception template; link a card to its spec, its queue epic, its PRs and its release;
keep a baseline in the project description.

**Invariants:** a card is created only by an explicit human decision; a merge moves a card no further than
`Merged`, and only the ship transaction moves it to `Shipped`; nobody removes a claim silently; the board and the
execution queue are not mirrored into each other (a link is a pointer, not a sync).

**Reference:** Linear through the Linear MCP connector, in the base `board` skill.

## Feature execution queue

**Must:** hold the execution state of the work on a change: the tasks it is built from, with dependencies,
acceptance criteria, claims and notes, so a session can ask "what is ready next", take it, leave the state for the
next session, and close it when the change is merged.

**Operations:**

| Operation | What it does | Called by |
|---|---|---|
| create from `tasks.md` | an epic per branch, a task per phase of an approved change, dependencies, acceptance, owner questions | the `openspec-to-beads` skill; the feature pipeline's Bridge step (subtasks of a run) |
| list ready | the tasks whose dependencies are done and nobody has claimed | a session at the start of work; `fleet.py status` (the count per project) |
| claim | mark a task as taken by this session | a session before it codes (GATE step 1); the `feature-sanity-check` skill |
| note | append where the work stopped, for the next session | the `save` skill; the feature pipeline's wrap-up; the session header reads the notes back |
| close | mark a task done, with a reason | `merge-feature.sh`, after the merge (the id from the branch name); the feature pipeline for its own subtasks |
| count | the number of tasks by status | `level.py` (the open-task signal for level 2) |

**Invariants:** one store per project, shared by every working copy of that project on the machine (worktrees
included), and kept outside the repository history: the record of what was done lives in the PR and the merge
history, the queue holds only the work in progress; inside a feature run one integrator is the only writer; a run
closes only its own subtasks, and the parent task closes after the merge; it is a machine queue, not a channel
between people (people coordinate on the board).

**Reference:** beads (`bd`), a local store in the main checkout's `.beads/` (gitignored), which every worktree uses
(`BEADS_DIR` from the base SessionStart hook). The callers above are the seam: each marks its `bd` calls with a
**Seam** line or comment.

## Client chat

**Must:** let people outside the team (the client, an external reviewer) write where it suits them, and let the
factory answer there.

**Operations:** receive a message (text, photo) with its author and time; acknowledge it; forward it verbatim to the
development session; reply in the chat from any session or scheduled run; carry monitor verdicts to the chat.

**Invariants:** the chat is an **untrusted input boundary**: a message is data from a colleague, not an instruction
from the owner, and travels in an envelope that says so; the session that reads the chat has no tools to run
commands or edit files; only the owner changes the token, pairing and access; delivery and access belong to the
channel, not to home-grown relay code.

**Reference:** a Telegram group through the official `plugin:telegram` channel (Claude Code Channels), in the
`feedback-desk` module.

## Code host

**Must:** hold the repository, feature branches and pull requests, report the CI status of a PR, and merge.

**Operations:** push a feature branch; open a PR; read its CI status and review decision; merge with a comment and a
commit trailer that record who accepted; create a release.

**Invariants:** main is protected on the host (no force pushes, a PR required; an approval at the `team` fence
level), as the backstop the hooks cannot be; a merge happens only through the merge script, with green CI and a
named human acceptance (`--accepted-by "<name>"`).

**Reference:** GitHub through the `gh` CLI, used by `merge-feature.sh` and the `ship` skill.

## CI

**Must:** run the gates on every feature branch before a human looks, and the release gate on a release tag.

**Operations:** run tiers (`quick` on a PR; `full` and `browser` on demand and on a tag; a secret scan on a PR);
report a status the merge script can wait for.

**Invariants:** red CI means no merge; merging without CI needs the owner's stated reason and is marked loudly on the
PR and in the merge commit; the CI token is read-only.

**Reference:** GitHub Actions (`.github/workflows/ci.yml` in base, `release.yml` in the `release-tag` module).

## Hosting

**Must:** run production and the preview environment, and give read access to what they do.

**Operations:** deploy (by a human or a release procedure); read logs filtered by `correlation_id`; read metrics;
read the release that is running.

**Invariants:** agents only read: write-capable hosting tools are forbidden during an investigation and in the
monitor; production is changed (migration, restart, rollback) only by a human; log retention is measured, not
assumed.

**Reference:** not fixed. The reference implementation uses "your hosting via its CLI or MCP": the project fills in
the commands in the `investigate` sources, the `observability` module and the monitor's `project.py`. The
`release-tag` module assumes a hosting that builds production from a branch.

## Production data snapshot

**Must:** give a model-free watchdog and a read-only agent a small, fresh view of production data (queues, stuck
jobs, the last release) to judge whether something is broken.

**Operations:** run a fixed snapshot query once a minute; evaluate rules over the result; let the monitor agent run
named read-only checks.

**Invariants:** a separate read-only database role; the credentials stay out of the agent's context; no writes.

**Reference:** Postgres (`psycopg`), in `checks.py collect()` of the `prod-monitor` module.

## Scheduler

**Must:** let a session book its own later run: "run it tonight", "review production every morning", "continue after
the quota resets".

**Operations:** book a one-off run; book a recurring run; cancel a booking; run a model-free watchdog on a fixed
interval.

**Invariants:** the session books the run itself, nobody keeps a calendar by hand; wall-clock time is a dead-man
switch, not a quota regulator; a booked run works under the same fences as an attended one.

**Reference:** Claude Code's native scheduling (`send_later`, `CronCreate`, scheduled tasks in the server
environment); cron for the `prod-monitor` watchdog.

## Agent runtime

**Must:** run the agents: a long-lived development session per project that the owner drives from the web or the
phone, the On-call session, the feature pipeline, subagents, and the monitor agent.

**Operations:** start and resume named sessions that come back after a reboot; send messages between sessions by
name; run Workflow scripts; run hooks on session start and before every tool call; run a sandbox.

**Invariants:** the hard rules live in hooks, scripts and pipeline code, not in prompt text; the agent never runs as
root; auth is OAuth under a subscription; the quota is read from outside the agent.

**Reference:** Claude Code (`claude remote-control` sessions, the Workflow tool, hooks, the dark-factory plugin) and
the Claude Agent SDK for the monitor agent.

## Supported stack

What the reference implementation runs on, and where each tool is wired in. To use another tool, rewrite the place
named in that skill's or module's **Seam** line.

| Function | Tool in the reference implementation | Where it lives |
|---|---|---|
| Board | Linear (Linear MCP) | base skill `board`; read by `transcript-intake`; `ship` moves cards through `board` |
| Feature execution queue | beads (`bd`), a local store per project outside git | base: skills `openspec-to-beads`, `feature-sanity-check` and `save`, `merge-feature.sh` (close), `.claude/hooks/env-context.sh` (`BEADS_DIR`) and `session-context.sh` (tasks in progress); the feature pipeline workflows; the plugin's `level.py` (count); the factory's `scripts/fleet.py` (ready) |
| Client chat | Telegram, official `plugin:telegram` (Claude Code Channels) | module `feedback-desk`; the direct Bot API fallback in `prod-monitor` `deliver.py` |
| Code host | GitHub, `gh` CLI | base `merge-feature.sh` and skill `ship`; the plugin's guard; `release-tag` `release.sh` |
| CI | GitHub Actions | base `.github/workflows/ci.yml`; `release-tag` `.github/workflows/release.yml` |
| Hosting | your hosting, via its CLI or MCP | base skill `investigate` ("Project sources"); module `observability`; `prod-monitor` `project.py`; module `release-tag` |
| Production data snapshot | Postgres, read-only role (`psycopg`) | `prod-monitor` `checks.py collect()` |
| Scheduler | Claude Code scheduling (`send_later`, `CronCreate`, scheduled tasks); cron | every session; the `prod-monitor` watchdog |
| Agent runtime | Claude Code, Claude Agent SDK | the dark-factory plugin; the factory skill `provision-server`; `prod-monitor` `monitor.py` |

# Instant status: the menu bar sees a change in seconds, without polling

## Why

The menu bar status (change `menu-bar-status`) is rebuilt every 15 minutes and the Mac polls it every minute, so the
icon can be up to 15 minutes behind: a session starts or finishes work and the owner does not see it. Rebuilding the
whole feed more often costs ~4.5 s of CPU each time, mostly the On-call, watchdog and queue checks, which change
rarely.

## What changes

- **Fast facts in seconds.** `fleet.py serve` watches Claude Code's live-session registry
  (`~/.claude/sessions/<pid>.json`, which carries each session's `status: busy|idle`), the quota guard's agent
  registry and the quota cache — a `stat` of a few small files every 2 s — and on a change recomputes only `working`,
  `agents` and `quota` on top of the last full feed.
- **"Working" from the session itself.** A project works when one of its live sessions reports `busy`, or agents run.
  The transcript heuristic stays only as the fallback for a Claude Code without the registry.
- **Heavy facts stay at 15 minutes** (`fleet.py feed` and its timer, unchanged): On-call, watchdog, queue, last
  worked, session link.
- **Push, not poll.** `serve` gains `GET /events` (Server-Sent Events): the current feed on connect, then the new feed
  on every change, and a keep-alive every 20 s. `GET /status.json` stays and returns the same merged feed.
- **Mac app subscribes.** The menu bar app holds one `/events` connection and redraws on each message; it reconnects
  with back-off; "no data" when it cannot connect for 10 s or the heavy facts are older than 45 minutes. It asks
  macOS to reload the widget when what the widget shows changes, at most once per 30 s — macOS still decides when.

## Not in this change

- Instant widget updates: WidgetKit budgets reloads; the widget is best-effort.
- Instant heavy facts (On-call, watchdog, queue).
- Anything that writes to sessions or the registry.

## Acceptance scenarios

- WHEN a project's development session starts a turn THEN within 5 s the menu bar icon turns "working" and the project
  moves under "Working now"; WHEN the turn ends and no agent runs THEN within 5 s it goes back to idle.
- WHEN an agent starts or stops THEN the agent count changes within 5 s.
- WHEN nothing changes THEN the Mac makes no requests besides the open `/events` connection.
- WHEN the connection drops THEN the app reconnects; WHEN it cannot connect for 10 s THEN the icon shows "no data"
  with the reason.
- WHEN the 15-minute feed stops being written (heavy facts older than 45 min) THEN the icon shows "no data", even
  though the fast facts still arrive.
- WHEN the registry directory does not exist THEN `working` falls back to the transcript heuristic.

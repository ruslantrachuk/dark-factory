# Design: instant status

Builds on `menu-bar-status` (merged). Decided by the owner: the cheap variant — heavy checks stay at 15 minutes,
"working" and agents in seconds, pushed to the Mac without polling.

**Anti-goals:** the Mac polls; the watcher costs noticeable CPU (target: well under 1% of a core); a dropped
connection still shows "live"; `serve` listens anywhere but the private address; anything writes to Claude Code's
files.

## Server — `fleet_feed.py`

```
fleet.py feed (timer, 15 min) ──writes──▶ status.json  (heavy + fast facts, "full_at")
                                              │ mtime
fleet.py serve ── watcher thread, every 2 s ──┤ ~/.claude/sessions/*.json   (mtime + size per file)
                                              │ quota agent registry, quota cache (mtime)
               on change: overlay = last status.json + fresh working/agents/quota → current doc
               GET /status.json → current doc · GET /events → SSE stream of current doc
```

- **Schema, version 2** (additive; a version-1 reader ignores the new fields):
  - `full_at` — when the heavy facts were built (the `feed` run); `generated_at` — when this document was produced
    (the last overlay).
  - per project `working`, `agents` as before; `busy_sessions` (int) — live registry sessions of the project with
    `status == "busy"`.
- **Registry facts:** a registry entry belongs to a project when its `cwd` is the checkout or under it (worktrees
  included) and its `pid` is alive; `busy` when `status == "busy"`. `working = busy_sessions > 0 or agents > 0`; when
  `~/.claude/sessions` does not exist, `working` comes from the transcript heuristic, as today.
- **Watcher:** one thread in `serve`; every 2 s it builds a fingerprint (sorted `(name, mtime_ns, size)` of
  `sessions/*.json`, mtimes of the agent registry, the quota cache and `status.json`); on a new fingerprint it reloads
  `status.json` if it changed, recomputes the fast facts (no tmux, no bd, no transcripts), and publishes the new doc
  if it differs from the last one apart from `generated_at`.
- **`feed` keeps working alone:** it also uses the registry for `working` and writes `full_at`, so a server without
  `serve` still has a correct file.
- **`/events`:** `Content-Type: text/event-stream`, `Cache-Control: no-store`; on connect `data: <doc>\n\n`, then one
  message per published doc, `: keep-alive\n\n` every 20 s. A condition variable wakes the streams; a client that
  disconnects ends its thread. At most 8 concurrent streams (the owner's devices); a 9th gets 503.
- **Threading:** `ThreadingHTTPServer` with daemon threads; the current doc is swapped under a lock.

> **Seam:** session state = Claude Code's `~/.claude/sessions/<pid>.json` (`pid`, `cwd`, `status`, `name`,
> `bridgeSessionId`). If a Claude Code version drops it, the fallback is the transcript heuristic.

## Mac — `macos/FactoryBar`

- `FeedStream`: `URLSession.bytes(from: <feed URL with /status.json replaced by /events>)`, parses `data:` lines
  (one JSON doc per message, possibly split across several `data:` lines), yields `Feed`. Reconnect with back-off
  1, 2, 5, 10, 30 s; any successful message resets it.
- State: "no data" when no connection for 10 s (reason "Server unreachable" / "Connection lost") or `full_at` (or
  `generated_at` for a version-1 feed) older than 45 min (reason "Status not updated since HH:MM"). The 60-s poll
  goes away.
- Widget: unchanged timeline (15 min) plus `WidgetCenter.shared.reloadAllTimelines()` from the app when the rows the
  widget shows change, throttled to once per 30 s.

## My calls (owner may override)

2-s watcher period; 5-s acceptance target; 10-s "no data" on a lost connection; 20-s keep-alive; 8 streams max;
schema version 2 additive; `busy_sessions` exposed; the On-call's own busy turns count as work (owner: "work is when a
session is doing something").

## Left to the builder

Exact SSE parsing details, back-off jitter, test structure (Python: watcher fingerprint, overlay, `/events` stream;
Swift: SSE parser, state with a lost connection and a stale `full_at`).

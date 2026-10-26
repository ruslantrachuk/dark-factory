# Tasks: instant status

Spec: `proposal.md`, `design.md` in this directory. Server half (Python, `plugins/dark-factory/scripts`) and Mac half
(`macos/FactoryBar`, built on a Mac with Xcode) are independent apart from the schema below.

## Schema, version 2 (the interface between the halves)

Version 1 plus: top-level `full_at` (ISO UTC, when the heavy facts were built); per project `busy_sessions` (int, or
`null` when the server has no session registry). `generated_at` is when this document was produced (it moves on every
push). `GET /events`: `text/event-stream`, each message `data: <the whole document, one line>\n\n`, comments
`: keep-alive\n\n` every 20 s.

## Server

- [ ] **1. Registry facts.** `fleet_feed.registry(now) -> list[dict] | None` (live entries of
  `<config dir>/sessions/*.json`, None without the directory); `busy_by_checkout(checkouts, entries) -> dict[Path,
  int]`; `transcript_busy(checkout, now) -> bool` (top-level transcripts only, split from `activity`). `project_row`
  takes `busy_sessions: int | None`: `working = (busy_sessions > 0 if busy_sessions is not None else transcript busy)
  or agents > 0`. `build_feed` writes version 2, `full_at`, `busy_sessions`.
  Tests: busy/idle/dead pid/foreign cwd/worktree cwd/unreadable entry; no directory → None → transcript fallback.
- [ ] **2. Overlay.** `overlay(doc, projects, now) -> dict`: the full doc with fresh `quota`, `generated_at`, and per
  row (matched by name, rows with `error` untouched) `working`, `agents`, `busy_sessions`, `waiting_quota`. No tmux, no
  bd, no `rglob`. Tests: idle→busy flips `working`; agents count; quota blocks → `waiting_quota` with a ready queue;
  `full_at` and heavy fields unchanged.
- [ ] **3. Live doc + watcher.** `Live(path, projects)`: `fingerprint()` (sessions files `(name, mtime_ns, size)`,
  mtimes of the agent registry, quota cache, `status.json`); `tick(now) -> bool` recomputes on a new fingerprint or
  every 30 s, publishes only when the doc changed apart from `generated_at`; `current() -> bytes | None`; `wait(seq,
  timeout)` for streams. Tests: no change → no publish; a registry file change → publish; feed missing → None.
- [ ] **4. HTTP.** `/status.json` serves `Live.current()`; `/events` streams (first message at once, a message per
  publish, keep-alive every 20 s, at most 8 streams → 503). Tests over a real `ThreadingHTTPServer`.
- [ ] **5. Wiring.** `fleet.py serve` loads the projects (same source as `feed`; serve unit's `ExecStart` carries it);
  `serve(addr, projects, path)` starts the watcher thread (2 s). Docs: provision-server and factory-status mention
  "updates in seconds". Tests in `tests/test_fleet.py` for the unit text.

## Mac (`macos/FactoryBar`)

- [x] **6. SSE client.** `FeedStream`: `URLSession.bytes` on the feed URL with `/status.json` → `/events`; parser for
  `data:` lines (several lines join with `\n`, blank line ends a message, `:` lines ignored); back-off 1, 2, 5, 10,
  30 s, reset on a message. XCTest: parser with split chunks, comments, multi-line data.
- [ ] **7. State.** Drop the 60-s poll. "No data" when not connected for 10 s ("Server unreachable" before any
  message, "Connection lost" after) or `full_at` (version 1: `generated_at`) older than 45 min ("Status not updated
  since HH:MM"). `Feed` decodes `full_at`, `busy_sessions` as optional. XCTest for each state.
- [ ] **8. Widget.** On a message whose widget rows differ from the last, `WidgetCenter.shared.reloadAllTimelines()`,
  at most once per 30 s. README: updates in seconds in the menu bar; the widget is best-effort.

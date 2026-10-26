# Design: menu bar status

## Intent

The owner glances at the Mac's menu bar and knows in one second whether the factory is alive and whether work is
running; one click shows which projects, what they do and who is on duty; one more click takes them into a project's
session. It answers "what is happening now", not "how did the week go".

**Goals.** A three-state icon that is never wrong about "no data"; the same content in a drop-down and in a native
desktop widget; a click from a project into its session; nothing on the server changes state because of the feed.

**Non-goals.** History and trends; iPhone; notifications; controlling anything from the Mac; a public endpoint.

**Anti-goals** — a failure even if everything else works:
- the icon shows "live" when the feed is stale or unreachable;
- the endpoint listens on a public address, or serves anything but the status file;
- building the feed spends model quota, claims a task, or writes into a project;
- the app needs a paid Apple Developer membership to run on the owner's own Mac.

## Shape

```
server                                            Mac (same tailnet)
fleet.py feed  ──every 15 min──▶ status.json      FactoryBar.app
   (df-fleet-feed.timer)          │                 ├─ menu bar icon + drop-down  (polls every 60 s)
fleet.py serve ◀── GET /status.json ──────────────┤
   (df-fleet-serve.service, private address only) └─ widget extension (timeline, polls every 15 min)
```

Both Mac parts fetch the file themselves over HTTP. No App Group, no shared container — those are unreliable with a
free personal team, and fetching twice a quarter-hour costs nothing.

> **Seams:** private network = Tailscale (any address the Mac can reach works: LAN, WireGuard, `127.0.0.1` when the
> factory runs on the Mac itself); session links = Claude's web session URLs; Mac app = SwiftUI + WidgetKit.

## Server

### `fleet.py feed`

Builds the document below from the projects in `~/.config/dark-factory/projects` and writes it atomically (temp file
+ rename) to `~/.local/state/dark-factory/status.json`. Reuses the existing `check_*` functions; adds three:

| Fact | How |
|---|---|
| `agents` — running now | the quota subagent registry (`quota.py`, `~/.cache/claude-quota*.json`), counted per project the same way the status line does |
| `working` | owner's definition: **a session of the project is doing something** — `agents > 0`, or any session of the project (its `~/.claude/projects/<dir>` and worktree dirs, as `analytics.py` maps them) is in the middle of a turn: its transcript's last record is not a finished assistant turn and was written in the last 10 minutes. A session idle at its prompt is not working, however recently it spoke |
| `last_worked_at` | newest transcript mtime of the project |
| `oncall.last_message_at` | the newest tool call ending in `__reply` (only the On-call has a chat reply tool) in the project's top-level transcripts written in the last hour; older → `null`, which the app shows the same as "not in the last hour" |
| `session_url` | the last `https://claude.ai/code…` link in the tmux pane of the development session (`tmux -L df-<slug>`), else of the new-sessions remote-control (`df-<slug>.rc`); a session link wins over an environment link (`…/code?environment=env_…`, which opens the project's sessions in Claude); `null` if neither pane has one |

**Quota is read from the cache only.** The feed never calls `quota.py status` in a way that may start `bg-refresh`
(a `claude -p` probe spends quota); it reads the cached numbers and their time, and writes `quota.as_of`. A cache
older than 30 minutes, or none, gives `quota: null` → the app shows "quota unknown" in the header and nobody is
"waiting for quota".

"Waiting for quota" is derived, not stored per project: quota at or above the no-new-work threshold **and** the
project's ready queue > 0, with the reset time of the limiting window.

```json
{
  "version": 1,
  "generated_at": "2026-10-26T19:45:00Z",
  "quota": {"five_hour": 28, "seven_day": 18, "no_new_work": false, "resets_at": "2026-10-26T20:40:00Z"},
  "projects": [
    {
      "name": "project-a",
      "working": true,
      "agents": 3,
      "waiting_quota": false,
      "queue_ready": 5,
      "last_worked_at": "2026-10-26T19:44:10Z",
      "session_url": "https://claude.ai/code/session_…",
      "oncall": {"installed": true, "running": true, "last_message_at": "2026-10-26T19:33:00Z"},
      "watchdog": {"installed": true, "ok": true}
    }
  ]
}
```

`installed: false` → the app hides that icon. A check that errors becomes `ok/running: false` plus an `error` string;
the feed is still written. Project names are the names in the projects file; nothing else (paths, branches, messages)
goes into the file.

### `fleet.py serve`

Stdlib `http.server`, one route: `GET /status.json` → the file with `Cache-Control: no-store`; everything else 404.
Binds to `FLEET_FEED_ADDR` (e.g. `100.x.y.z:8765`) from `fleet.env`; refuses to start on `0.0.0.0`, `::` or an empty
address. No TLS, no auth: the private network is the boundary (stated in the docs).

### Provisioning

`fleet.py provision` writes `df-fleet-feed.service` + `.timer` (every 15 min, `Persistent=true`) and
`df-fleet-serve.service` only when `FLEET_FEED_ADDR` is set; `unprovision` removes them. `factory-status` gains one
line: "● feed — written <time>, served on <addr>".

## Mac app — `macos/FactoryBar/`

- SwiftUI, macOS 14+. Project generated with XcodeGen (`project.yml` in the repo; no hand-written `.xcodeproj`).
  Targets: the app (menu bar only, `LSUIElement`) and a widget extension. Both sandboxed with outgoing network.
- **Setup:** first launch asks for the feed URL (`http://100.x.y.z:8765/status.json`), stored in `UserDefaults`; the
  widget reads the same URL from its own configuration (an App Intent parameter) — no shared container.
- **Icon states:** working = filled factory glyph, green, with the agent count; idle = outlined, grey; no data =
  outlined, red, with "?". No data = request failed / non-200 / undecodable / `generated_at` older than 45 minutes.
- **In-between states:** a project working with no agents reads "Building" (no number); the icon is "working" only
  when some project is actually working — a project that only waits for quota is listed under "Working now" but
  leaves the icon idle; the number next to the icon is the total of running agents and is omitted when 0.
- **Drop-down and widget** — the layout of the agreed sketch: header "Factory" + quota "5h 28% · 7d 18%"; sections
  "Working now" and "Idle"; per project the name, On-call (headset) and watchdog (shield) icons colored on/grey off,
  a status line ("Building · N agents", "Waiting for quota until HH:MM · N queued", "Last worked …"), and
  "On-call wrote N min ago" only within the last hour; footer "updated HH:MM · next at HH:MM". In "no data" the
  drop-down shows the reason and the last good update.
- **Widget:** large family. Each project row is a `Link` to its `session_url`; the widget's timeline asks for reload
  every 15 minutes (the system decides the exact moment).
- **Click:** `NSWorkspace.open(session_url)`. Whether the URL lands in the Claude desktop app or the browser is checked
  on the owner's Mac during the build; if it lands in the browser, the builder looks for the desktop app's link
  handling and records the result.
- **Build:** `brew install xcodegen && xcodegen && open FactoryBar.xcodeproj`, choose the personal team once, Run;
  later builds with `xcodebuild`. A README in the folder lists exactly these steps. On the reference setup the owner
  has a Claude session on the Mac with Xcode installed: the Mac half (generate, build, run, check the click target)
  is done there, from the same branch; the server half is done on the server.

### Click (checked on the Mac, Claude desktop app current as of 2026-10-26)

- An `https://claude.ai/…` link opened with `NSWorkspace.open` lands in the **default browser**: the Claude desktop
  app (`com.anthropic.claudefordesktop`) registers only the `claude://` scheme and no universal links for claude.ai.
- The desktop app opens a remote session itself from `claude://code/<id>` when `<id>` is `session_…` or `cse_…`
  (its link handler maps the path to `/code/<id>`).
- So the app rewrites a **session link** `https://claude.ai/code/<session_…|cse_…>` to `claude://code/<id>` when some
  app handles `claude://`, and opens it in the desktop app; otherwise the https link opens in the browser.
- An **environment link** (`https://claude.ai/code?environment=env_…`, what the feed carries today) stays https and
  opens in the browser: no route for it was found in the desktop app's link handler, and it was not tried in the
  running app. Open question for the owner.

## Decided by the owner

Native macOS app (menu bar + widget) over SwiftBar/Übersicht; data from the server over Tailscale; "no data" = no
connection or a very old update; interface in English; part of the public factory; click opens the project's session;
no trends in this change.

## My calls (owner may override)

45-minute staleness threshold; agent count as the number next to the icon; the 10-minute window for a turn in progress; menu bar polls every 60 s; large widget only; `fleet.py feed`/`serve` names and units; XcodeGen;
macOS 14 minimum; no auth beyond the private network; quota from the cache only (`null` when older than 30 min);
the in-between states above; HH:MM in the Mac's local time.

## Left to the builder

The On-call last-message source and the session URL source (see the table); the exact glyphs; tests: Python unit tests
for the feed builder and the serve guard, a decoding/state test in Swift for the three icon states.

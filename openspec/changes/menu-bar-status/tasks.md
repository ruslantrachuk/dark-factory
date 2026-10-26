# Menu bar status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A status feed on the factory server and a native macOS app (menu bar icon, drop-down, large widget) that reads it.

**Architecture:** A new stdlib module `fleet_feed.py` builds `status.json` from the existing `fleet.py` checks plus
transcript, quota-cache and subagent-registry facts; `fleet.py feed` writes it, `fleet.py serve` serves it on a
private address, `fleet.py provision` adds the units when `FLEET_FEED_ADDR` is set. The Mac app `macos/FactoryBar/`
(SwiftUI + WidgetKit, XcodeGen) fetches the file over HTTP in both the app and the widget.

**Tech Stack:** Python 3 stdlib (server), systemd user units; Swift 5.9+, SwiftUI, WidgetKit, XcodeGen, XCTest (Mac).

**Spec:** `openspec/changes/menu-bar-status/proposal.md`, `openspec/changes/menu-bar-status/design.md`

**Who builds what:** Tasks 1–5 on the factory server (this checkout). Tasks 6–8 in the owner's Mac session with Xcode,
from the same branch `feat/menu-bar-status` (pull before starting, push after each task).

## Global Constraints

- Server code: stdlib only, no model calls, never `quota.py status` / `current()` (they may start `bg-refresh`).
- Feed path `~/.local/state/dark-factory/status.json`, written atomically (temp + `os.replace`); schema `version: 1`.
- "Working" window: a session turn in progress = last record written ≤ 600 s ago. Quota cache older than 1800 s → `quota: null`.
- `serve` refuses `0.0.0.0`, `::`, empty; route `GET /status.json` only, `Cache-Control: no-store`; anything else 404.
- Feed timer every 15 min, `Persistent=true`; units only when `FLEET_FEED_ADDR` is set in `fleet.env`.
- Mac: macOS 14+, interface text in English, "no data" when fetch fails / non-200 / undecodable / `generated_at` older than 2700 s (45 min); menu bar polls every 60 s; widget large family, timeline reload every 15 min; free personal team, no App Group.
- Public canon: no names of the owner's projects anywhere (code, tests, docs, commits, PR text).

## Review Focus

1. A transcript whose last line is half-written (the session is writing it right now) → treated as busy, not a crash (Task 1).
2. A project path that does not exist or has no transcripts → `working: false`, `last_worked_at: null`, the feed is still written (Task 2).
3. `status.json` not written yet when the Mac asks → `serve` answers 503, the app shows "no data" with reason "feed not written yet" (Tasks 4, 6).
4. Mac clock ahead of or behind the server by minutes → staleness uses `generated_at` vs the Mac's now; a `generated_at` in the future counts as fresh (Task 6).
5. A project with `settings_error` or a check that raises → its row carries `error`, other projects unaffected (Task 2).

---

### Task 1: Activity facts from transcripts, the agent registry and the quota cache

**Files:**
- Create: `plugins/dark-factory/scripts/fleet_feed.py`
- Test: `tests/test_fleet_feed.py` (unittest, same header as `tests/test_fleet.py`; run `python3 tests/test_fleet_feed.py`)

**Interfaces:**
- Consumes: `analytics_lib.store.transcript_dirs(checkout: Path, root: Path) -> list[Path]`; `quota._read`, `quota.CACHE`, `quota.AGENTS`, `quota.agents_live(reg, now)`, `quota.stage(windows, now)`, `quota.NO_NEW`.
- Produces:
  - `session_busy(transcript: Path, now: float) -> bool`
  - `activity(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> tuple[bool, float | None]` — (a session is mid-turn, newest transcript mtime)
  - `agents_by_checkout(checkouts: list[Path], now: float) -> dict[Path, int]`
  - `quota_snapshot(now: float) -> dict | None` — `{"five_hour": int, "seven_day": int, "no_new_work": bool, "resets_at": "<ISO Z>", "as_of": "<ISO Z>"}`

- [ ] **Step 1: Write the failing tests**

```python
class SessionBusyTest(unittest.TestCase):
    # helper write(lines, age_s) creates a .jsonl with those records and sets mtime to now - age_s
    def test_assistant_text_only_last_is_idle(self): ...       # last user/assistant record: assistant, content only text → False
    def test_assistant_tool_use_last_is_busy(self): ...        # assistant with a tool_use block → True
    def test_user_record_last_is_busy(self): ...               # user prompt or tool_result last → True
    def test_other_record_types_are_skipped(self): ...         # trailing "system"/"summary"/"file-history-snapshot" ignored
    def test_half_written_last_line_is_busy(self): ...         # last line not valid JSON, mtime fresh → True
    def test_older_than_600s_is_idle(self): ...                # tool_use last but mtime now-601 → False

class ActivityTest(unittest.TestCase):
    def test_no_transcript_dir(self): ...                      # activity(...) == (False, None)
    def test_worktree_dirs_count(self): ...                    # a busy file in "<name>--claude-worktrees-x" → (True, its mtime)
    def test_subagent_files_set_last_worked_not_busy(self): ...# newest mtime may come from subagents/*.jsonl; busy only from top-level files

class AgentsTest(unittest.TestCase):
    def test_counts_by_checkout_including_worktrees(self): ... # registry cwd "/srv/a/.claude/worktrees/x" counts for /srv/a; expired (> AGENT_TTL) not counted

class QuotaSnapshotTest(unittest.TestCase):
    def test_fresh_cache(self): ...                            # pct rounded to int, resets_at of the limiting window, as_of
    def test_cache_older_than_1800s_is_none(self): ...
    def test_missing_cache_is_none(self): ...
    def test_never_probes(self): ...                           # mock subprocess.Popen; assert not called
```

Point `quota`'s state dir at a temp dir (`QUOTA_STATE_DIR` or whatever `quota.state_dir()` reads) and `PROJECTS_ROOT` at a temp dir.

- [ ] **Step 2: Run to verify they fail** — `python3 tests/test_fleet_feed.py` → `ModuleNotFoundError: fleet_feed`.

- [ ] **Step 3: Implement the four functions in `fleet_feed.py`**

`session_busy`: if `now - mtime > 600` → False. Read the file's last 64 KiB, walk lines from the end; an unparsable
last line → True; skip records whose `type` is not `user`/`assistant`; the first `user` → True; the first `assistant`
→ True if any `message.content` block has `type == "tool_use"`, else False. `activity` looks only at `*.jsonl` directly
in each dir for busy, at `**/*.jsonl` for the newest mtime. `quota_snapshot` reads `quota._read(quota.CACHE)` directly.

- [ ] **Step 4: Run tests** — `python3 tests/test_fleet_feed.py` → OK.

- [ ] **Step 5: Commit** — `git add plugins/dark-factory/scripts/fleet_feed.py tests/test_fleet_feed.py && git commit -m "feat(fleet): activity facts for the status feed"`

### Task 2: `fleet.py feed` — build and write `status.json`

**Files:**
- Modify: `plugins/dark-factory/scripts/fleet_feed.py`
- Modify: `plugins/dark-factory/scripts/fleet.py` (`main`: add `feed` to the command choices; module docstring: one paragraph)
- Test: `tests/test_fleet_feed.py`

**Interfaces:**
- Consumes: Task 1; `fleet.Project`, `fleet.check_desk(p)`, `fleet.check_monitor(p, now)`, `fleet.check_queue(p)`.
- Produces:
  - `FEED_PATH = Path(os.environ.get("FLEET_FEED", ~/.local/state/dark-factory/status.json))`
  - `build_feed(projects: list[Project], now: float) -> dict` — the schema in design.md
  - `write_feed(doc: dict, path: Path = FEED_PATH) -> None`
  - `fleet.py feed` → exit 0 after writing; 2 on no projects (as the other commands)

- [ ] **Step 1: Write the failing tests**

```python
class BuildFeedTest(unittest.TestCase):
    def test_schema(self): ...            # keys: version==1, generated_at (ISO Z), quota, projects[*] with name, working, agents,
                                          # waiting_quota, queue_ready, last_worked_at, session_url, oncall{installed,running,last_message_at}, watchdog{installed,ok}
    def test_working_from_agents_or_busy_session(self): ...   # agents>0 → working; busy session, 0 agents → working, agents 0
    def test_waiting_quota_needs_no_new_work_and_ready_queue(self): ...  # no_new_work & ready 5 → True; ready 0 → False; quota None → False
    def test_module_absent_means_not_installed(self): ...     # check_desk None → oncall.installed False; check_monitor None → watchdog.installed False
    def test_failing_check_sets_error_and_others_continue(self): ...  # check_queue raises → that project has "error", second project complete
    def test_settings_error_project_still_listed(self): ...
    def test_missing_path(self): ...      # working False, last_worked_at None
    def test_no_paths_or_texts_leak(self): ...  # json.dumps(doc) contains no str(p.path)

class WriteFeedTest(unittest.TestCase):
    def test_atomic_replace(self): ...    # writes via a temp file in the same dir; result parses; no temp left behind
```

Mock the `check_*` functions; `session_url` and `oncall.last_message_at` are `None` in this task.

- [ ] **Step 2: Run to verify they fail** — `python3 tests/test_fleet_feed.py` → `AttributeError: build_feed`.

- [ ] **Step 3: Implement `build_feed`, `write_feed`, the `feed` command**

`oncall.running` / `watchdog.ok` = the bool of the matching check; `queue_ready` parsed from `check_queue`'s
"ready: N" (0 when the check is None). Each project's facts in one `try`; an exception → `{"name", "error": str(e)}`
with defaults for the rest.

- [ ] **Step 4: Run tests** — `python3 tests/test_fleet_feed.py && python3 tests/test_fleet.py` → OK.

- [ ] **Step 5: Run on this server** — `python3 plugins/dark-factory/scripts/fleet.py feed && python3 -m json.tool ~/.local/state/dark-factory/status.json` → every project listed, numbers plausible against `fleet.py status`.

- [ ] **Step 6: Commit** — `git commit -am "feat(fleet): fleet.py feed writes status.json"` (add the new test lines).

### Task 3: Session link and the On-call's last message

**Files:**
- Modify: `plugins/dark-factory/scripts/fleet_feed.py`
- Test: `tests/test_fleet_feed.py`

**Interfaces:**
- Produces: `session_url(p: Project) -> str | None`, `oncall_last_message(p: Project, now: float) -> float | None`; `build_feed` fills `session_url` and `oncall.last_message_at` from them.

- [ ] **Step 1: Find the sources on this server, record them in design.md "Server" table** — for the URL: the development session's tmux pane (`tmux -L df-<slug> capture-pane -p -S -2000`) where `claude remote-control` prints its `https://claude.ai/code/…` link, or the transcript/`~/.claude` state; for the On-call: the On-call session's transcript (its cwd is in `.claude/feedback-desk/config.env`), the time of its last tool call whose name ends in `__reply`. Pick the cheapest that works on a provisioned project and on a hand-started one; write down which.
- [ ] **Step 2: Write failing tests** for the chosen parsers on fixture text: one URL found → it; none → `None`; two → the last; On-call: last `__reply` time; none → `None`; an unreadable source → `None`, no exception.
- [ ] **Step 3: Run to verify they fail.**
- [ ] **Step 4: Implement**, read-only, each under 1 s per project (tail reads only).
- [ ] **Step 5: Run tests** → OK; `fleet.py feed` on this server shows a URL for each provisioned project.
- [ ] **Step 6: Commit** — `git commit -am "feat(fleet): session link and On-call last message in the feed"`

### Task 4: `fleet.py serve`

**Files:**
- Modify: `plugins/dark-factory/scripts/fleet_feed.py`, `plugins/dark-factory/scripts/fleet.py` (`serve` command)
- Test: `tests/test_fleet_feed.py`

**Interfaces:**
- Produces: `parse_addr(text: str) -> tuple[str, int]` (raises `ValueError` on refused), `make_handler(path: Path) -> type[BaseHTTPRequestHandler]`, `serve(addr: str, path: Path = FEED_PATH) -> int`; `fleet.py serve` reads `FLEET_FEED_ADDR` from `fleet.env`.

- [ ] **Step 1: Write failing tests**

```python
class ParseAddrTest(unittest.TestCase):
    def test_ok(self): self.assertEqual(fleet_feed.parse_addr("100.64.1.2:8765"), ("100.64.1.2", 8765))
    def test_refused(self):
        for bad in ("", "0.0.0.0:8765", "[::]:8765", ":8765", "100.64.1.2", "100.64.1.2:x"):
            with self.assertRaises(ValueError): fleet_feed.parse_addr(bad)

class ServeTest(unittest.TestCase):  # a ThreadingHTTPServer on 127.0.0.1:0 with make_handler(tmp)
    def test_status_json(self): ...       # 200, body == file, Cache-Control: no-store, Content-Type application/json
    def test_not_written_yet(self): ...   # file missing → 503
    def test_other_paths_404(self): ...   # "/", "/status.json/../x", "/etc/passwd" → 404; POST → 405
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** with `http.server.ThreadingHTTPServer`; the handler reads the file per request; log nothing but errors.
- [ ] **Step 4: Run tests** → OK.
- [ ] **Step 5: Commit** — `git commit -am "feat(fleet): fleet.py serve the status feed on a private address"`

### Task 5: Units, factory-status line, docs

**Files:**
- Modify: `plugins/dark-factory/scripts/fleet.py` (`server_units`, `provision`, `unprovision`, `status`)
- Modify: `plugins/dark-factory/skills/factory-status/SKILL.md` (one ● line + one ○ row), `plugins/dark-factory/skills/provision-server/SKILL.md` (the `FLEET_FEED_ADDR` line and the Tailscale note)
- Test: `tests/test_fleet.py`

**Interfaces:**
- Produces: `FLEET_FEED = "df-fleet-feed"`, `FLEET_SERVE = "df-fleet-serve"`; `server_units(python, source, analytics_repo=None, feed_addr=None)`; status line `● feed — written HH:MM UTC, served on <addr>` / `○ feed — not written for N min` (> 45).

- [ ] **Step 1: Write failing tests** — `server_units(..., feed_addr="100.64.1.2:8765")` contains `df-fleet-feed.service` (oneshot, `fleet.py feed`), `df-fleet-feed.timer` (`OnUnitActiveSec=15min`, `Persistent=true`), `df-fleet-serve.service` (`Restart=on-failure`, `fleet.py serve`, `[Install]`); without `feed_addr` none of them; `provision` removes them when the address is gone (mirror the analytics test); `unprovision` lists them with the server units; the status line for fresh / stale / missing feed.
- [ ] **Step 2: Run to verify they fail** — `python3 tests/test_fleet.py`.
- [ ] **Step 3: Implement**, following the `FLEET_ANALYTICS` pattern in `provision`.
- [ ] **Step 4: Run the whole gate** — `python3 scripts/test_repo.py && for t in tests/test_*.py; do python3 "$t" || break; done` → all OK.
- [ ] **Step 5: Docs** — the PR's `## Upgrade` already says what to set; the provision-server skill gets the same two lines.
- [ ] **Step 6: Commit and push** — `git commit -am "feat(fleet): provision the status feed units" && git push`

### Task 6 (Mac): Project, model and state

**Files:**
- Create: `macos/FactoryBar/project.yml`, `macos/FactoryBar/Shared/Feed.swift`, `macos/FactoryBar/Shared/FeedState.swift`, `macos/FactoryBar/Shared/FeedClient.swift`, `macos/FactoryBar/Tests/FeedStateTests.swift`, `macos/FactoryBar/Tests/Fixtures/status.json` (copy of a real feed with names replaced by `project-a`, `project-b`), `macos/FactoryBar/README.md`
- Modify: `.gitignore` (`macos/FactoryBar/*.xcodeproj`, `build/`)

**Interfaces:**
- Produces:
  - `struct Feed: Decodable` mirroring the schema (dates as `Date`, ISO 8601), `struct ProjectStatus`, `struct Quota`
  - `enum IconState { case working(agents: Int), idle, noData(reason: String, lastGood: Date?) }`
  - `func iconState(feed: Result<Feed, Error>, now: Date, lastGood: Date?) -> IconState`
  - `enum RowStatus { case building(agents: Int), waitingQuota(until: Date, queued: Int), lastWorked(Date?) }` and `func rowStatus(_ p: ProjectStatus) -> RowStatus`
  - `func oncallLine(_ p: ProjectStatus, now: Date) -> String?` — "On-call wrote N min ago" within 3600 s, else nil
  - `actor FeedClient { init(url: URL); func fetch() async -> Result<Feed, Error> }` — 10 s timeout, non-200 → error
- `project.yml`: targets `FactoryBar` (app, `LSUIElement: true`, sandbox + `com.apple.security.network.client`, ATS `NSAllowsArbitraryLoads: true` with a comment: the feed is plain HTTP on an owner-chosen private address, unknown at build time), `FactoryBarWidget` (widget extension, same entitlements), `FactoryBarTests` (unit tests on `Shared/`); deployment target macOS 14.0.

- [x] **Step 1: Write failing tests** in `FeedStateTests.swift`: fixture decodes; working with agents → `.working(3)`; working, 0 agents → `.working(0)` (icon shows no number); only waiting-quota projects → `.idle`; fetch error → `.noData`; `generated_at` 2701 s old → `.noData`; `generated_at` 300 s in the future → not noData; `rowStatus` for the three cases; `oncallLine` at 59 min → text, at 61 min → nil, `nil` timestamp → nil.
- [x] **Step 2:** `cd macos/FactoryBar && xcodegen && xcodebuild test -scheme FactoryBar -destination 'platform=macOS'` → fails to compile.
- [x] **Step 3: Implement** `Feed.swift`, `FeedState.swift`, `FeedClient.swift`.
- [x] **Step 4:** same command → `** TEST SUCCEEDED **`.
- [x] **Step 5: README** — prerequisites (`brew install xcodegen`, Xcode, free Apple ID), `xcodegen && open FactoryBar.xcodeproj`, choose the personal team for both targets once, Run; later `xcodebuild -scheme FactoryBar build`; how to set the feed URL.
- [x] **Step 6: Commit and push.**

### Task 7 (Mac): Menu bar icon and drop-down

**Files:**
- Create: `macos/FactoryBar/App/FactoryBarApp.swift`, `macos/FactoryBar/App/MenuContent.swift`, `macos/FactoryBar/App/SettingsView.swift`, `macos/FactoryBar/Shared/StatusList.swift` (the project list view shared with the widget), `macos/FactoryBar/Shared/Glyphs.swift`

**Interfaces:**
- Consumes: Task 6.
- Produces: `struct StatusList: View { let feed: Feed; let now: Date; let linkRows: Bool }` reused by the widget.

- [x] **Step 1: Implement** `MenuBarExtra` with `.window` style; label = the glyph for `iconState` (filled green + count when > 0 / outlined grey / outlined red + "?"); content = header "Factory" + quota "5h N% · 7d N%" or "quota unknown", sections "Working now" / "Idle", rows per design (headset/shield icons only when `installed`), footer "updated HH:MM · next at HH:MM" (local time); in no-data, the reason and "last update HH:MM". Poll every 60 s with a `Timer` task; first launch with no URL shows `SettingsView` (one text field, stored in `UserDefaults` key `feedURL`). A row with `session_url` is a button → `NSWorkspace.shared.open`; without it, plain text.
- [ ] **Step 2: Run** against the live feed over Tailscale; compare with `fleet.py status` on the server; stop the feed timer for a while or block the port → "no data" within a minute.
  *Partly done: the sandboxed app fetched a fixture over plain HTTP from `127.0.0.1`, and the live feed over Tailscale
  (HTTP 200, `Cache-Control: no-store`) decoded and rendered as expected — a project building with no agents gives the
  green glyph without a number, module icons only where installed. The owner saw the icon in the menu bar. Still
  open: "no data" within a minute after the feed stops.*
- [x] **Step 3: Check the click target** — click a project: does the session open in the Claude desktop app or the browser? Record the result in design.md ("Click"); if the browser, look for the desktop app's own link handling and note it as an open question in the PR.
- [x] **Step 4: Commit and push.**

### Task 8 (Mac): Widget

**Files:**
- Create: `macos/FactoryBar/Widget/FactoryBarWidget.swift`, `macos/FactoryBar/Widget/FeedURLIntent.swift`

**Interfaces:**
- Consumes: `FeedClient`, `StatusList(linkRows: true)`.

- [x] **Step 1: Implement** an `AppIntentConfiguration` widget, `.systemLarge` only, intent parameter `feedURL` (String); `TimelineProvider` fetches, returns one entry, policy `.after(now + 15 min)`; each row with `session_url` wrapped in `Link`; no-data entry shows the red glyph and the reason.
- [x] **Step 2: Run** — add the widget to the desktop, set the URL, wait for one reload; click a row → the session opens (same target as Task 7).
  *The owner built the app with the personal team; the widget is on the desktop with the feed. A click on a project
  with a session link opened the session in the Claude desktop app.*
- [x] **Step 3: Commit and push**, update the PR body (`## Done`, the click result under `## Decisions` or `## Open questions`).

### Finish

- [ ] Whole-branch review; the PR description current; merge only through `scripts/merge-feature.sh feat/menu-bar-status` after green CI and the owner's review.
- [ ] Tell whoever cuts the next release the PR number(s) once merged.

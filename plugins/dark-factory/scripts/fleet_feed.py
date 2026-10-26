"""The status feed for the owner's menu bar app: one status.json for every project of the server.

Read-only and model-free: transcripts, the quota cache and the subagent registry are read, never refreshed — the quota
is taken from the cache only, because a probe (`quota.py status`) spends quota.
See openspec/changes/menu-bar-status/design.md.
"""
from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import quota
from analytics_lib.store import PROJECTS_ROOT, transcript_dirs

BUSY_WINDOW = 600  # a session whose transcript is older than this is not mid-turn, whatever its last record says
QUOTA_FRESH = 1800  # an older quota cache counts as unknown
TAIL = 64 * 1024  # a session's last records are in the file's tail


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_busy(transcript: Path, now: float) -> bool:
    """A session is mid-turn when its last user/assistant record is not a finished answer: a prompt or a tool result
    waits for the model, a tool_use waits for the tool. A half-written last line is a record being written."""
    try:
        if now - transcript.stat().st_mtime > BUSY_WINDOW:
            return False
        with transcript.open("rb") as f:
            f.seek(max(0, f.seek(0, 2) - TAIL))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return False
    for i, line in enumerate(reversed([ln for ln in lines if ln.strip()])):
        try:
            rec = json.loads(line)
        except ValueError:
            if i == 0:
                return True
            continue
        kind = rec.get("type") if isinstance(rec, dict) else None
        if kind == "user":
            text = user_text(rec)
            if rec.get("isMeta") or text.startswith(("<command-name>", "<local-command")):
                continue  # a local command (/status, /clear) ran at the prompt: no turn
            return not text.startswith("[Request interrupted")
        if kind == "assistant":
            content = (rec.get("message") or {}).get("content")
            return isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in content)
    return False


def user_text(rec: dict) -> str:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        content = next((b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"), "")
    return content.lstrip() if isinstance(content, str) else ""


def activity(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> tuple[bool, float | None]:
    """(a session of the checkout is mid-turn, the newest transcript mtime). Subagent transcripts count for the time
    only: running subagents are counted from the registry."""
    newest = None
    for d in transcript_dirs(checkout, root):
        for f in d.rglob("*.jsonl"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            newest = m if newest is None else max(newest, m)
    return transcript_busy(checkout, now, root), newest


def transcript_busy(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> bool:
    """A session of the checkout is mid-turn by its transcript: the fallback without the session registry."""
    return any(session_busy(f, now) for d in transcript_dirs(checkout, root) for f in d.glob("*.jsonl"))


def count_by_checkout(checkouts: list[Path], cwds) -> dict[Path, int]:
    """How many of `cwds` fall in each checkout (a worktree counts for its checkout)."""
    counts = {c: 0 for c in checkouts}
    for cwd in cwds:
        cwd = Path(str(cwd).split("/.claude/worktrees/")[0])
        for c in checkouts:
            if cwd == c or c in cwd.parents:
                counts[c] += 1
                break
    return counts


def agents_by_checkout(checkouts: list[Path], now: float) -> dict[Path, int]:
    """Running subagents per checkout, from the quota guard's registry."""
    live = quota.agents_live(quota._read(quota.AGENTS) or {}, now)
    return count_by_checkout(checkouts, (v.get("cwd", "") for v in live.values()))


def sessions_dir() -> Path:
    return Path(quota.config_dir()) / "sessions"


def registry(now: float) -> list[dict] | None:
    """Claude Code's live sessions: one <pid>.json per running session with its cwd and `status` (busy while a turn
    runs, idle at the prompt). None when this Claude Code keeps no such registry — `working` then comes from
    transcripts."""
    d = sessions_dir()
    if not d.is_dir():
        return None
    entries = []
    for f in d.glob("*.json"):
        try:
            e = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(e, dict) and pid_alive(e.get("pid")):
            entries.append(e)
    return entries


def busy_by_checkout(checkouts: list[Path], entries: list[dict]) -> dict[Path, int]:
    return count_by_checkout(checkouts, (e["cwd"] for e in entries if e.get("status") == "busy" and e.get("cwd")))


@contextlib.contextmanager
def owner_thresholds():
    """The guard's thresholds as the owner's sessions see them: QUOTA_5H/7D from ~/.claude/settings.json `env` when
    this process (a systemd unit) has none of its own. Restored afterwards."""
    try:
        env = json.loads((Path(quota.config_dir()) / "settings.json").read_text()).get("env") or {}
    except (OSError, ValueError, AttributeError):
        env = {}
    added = {k: str(env[k]) for k in ("QUOTA_5H", "QUOTA_7D") if k in env and k not in os.environ}
    os.environ.update(added)
    try:
        yield
    finally:
        for k in added:
            os.environ.pop(k, None)


def quota_snapshot(now: float) -> dict | None:
    with owner_thresholds():
        return _quota_snapshot(now)


def _quota_snapshot(now: float) -> dict | None:
    cached = quota._read(quota.CACHE)
    if not cached or now - cached.get("updated_at", 0) > QUOTA_FRESH:
        return None
    windows = cached.get("windows") or {}
    pct = {k: round(quota.effective_pct(windows.get(k), now)) for k, _ in quota.WINDOWS}
    worst = max(((quota.window_stage(windows.get(k), k, now), windows[k]["resets_at"])
                 for k, _ in quota.WINDOWS if windows.get(k)), default=(quota.OK, 0))
    blocked = worst[0] >= quota.NO_NEW
    return {"five_hour": pct["five_hour"], "seven_day": pct["seven_day"], "no_new_work": blocked,
            "resets_at": iso(worst[1]) if blocked else None, "as_of": iso(cached["updated_at"])}


# ---------- session link, On-call ----------

SESSION_ID_RE = re.compile(r"(session|cse)_[A-Za-z0-9]+")


def pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return True


def session_url(p) -> str | None:
    """The development session's claude.ai link: Claude Code keeps one file per live session in
    ~/.claude/sessions/<pid>.json with its name and its Remote Control id (bridgeSessionId); the development session is
    the live one named like the project's SESSION_NAME. None when there is none — the app then shows no link."""
    want = p.session_name.casefold()
    for f in sessions_dir().glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        sid = d.get("bridgeSessionId") if isinstance(d, dict) else None
        if (isinstance(sid, str) and SESSION_ID_RE.fullmatch(sid) and str(d.get("name", "")).casefold() == want
                and pid_alive(d.get("pid"))):
            return f"https://claude.ai/code/{sid}"
    return None


REPLY_TAIL = 2 * 1024 * 1024
ONCALL_WINDOW = 3600  # the app shows "On-call wrote N min ago" within an hour; older transcripts are not read


def last_reply(transcript: Path) -> float | None:
    """Time of the last outgoing chat message (a tool call ending in __reply: only the On-call has one)."""
    best = None
    try:
        with transcript.open("rb") as f:  # the tail only: a development session's transcript runs to tens of MB
            f.seek(max(0, f.seek(0, 2) - REPLY_TAIL))
            lines = f.read().decode("utf-8", "replace").splitlines()
            for line in lines:
                if "__reply" not in line:
                    continue
                try:
                    rec = json.loads(line)
                    content = (rec.get("message") or {}).get("content") or []
                    if rec.get("type") == "assistant" and any(
                            isinstance(b, dict) and b.get("type") == "tool_use"
                            and str(b.get("name", "")).endswith("__reply") for b in content):
                        ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
                        best = ts if best is None else max(best, ts)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return None
    return best


def oncall_last_message(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> float | None:
    times = []
    for d in transcript_dirs(checkout, root):
        for f in d.glob("*.jsonl"):
            try:
                fresh = now - f.stat().st_mtime <= ONCALL_WINDOW
            except OSError:
                continue
            if fresh and (t := last_reply(f)) is not None:
                times.append(t)
    return max(times, default=None)


# ---------- the document ----------

FEED_PATH = Path(os.environ.get("FLEET_FEED", Path.home() / ".local/state/dark-factory/status.json"))


def project_row(p, now: float, agents: int, busy_sessions: int | None, q: dict | None) -> dict:
    """`busy_sessions` — the project's live sessions mid-turn per the registry, None without one."""
    import fleet  # fleet imports this module for its commands
    busy, last = activity(p.path, now)
    if busy_sessions is not None:
        busy = busy_sessions > 0
    desk, monitor, queue = fleet.check_desk(p), fleet.check_monitor(p, now), fleet.check_queue(p)
    m = re.search(r"ready: (\d+)", queue[1]) if queue else None
    ready = int(m.group(1)) if m else 0
    return {"name": p.name, "working": busy or agents > 0, "agents": agents, "busy_sessions": busy_sessions,
            "waiting_quota": bool(q and q.get("no_new_work") and ready > 0), "queue_ready": ready,
            "last_worked_at": iso(last) if last else None, "session_url": session_url(p),
            "oncall": {"installed": desk is not None, "running": bool(desk and desk[0]),
                       "last_message_at": iso(said) if desk is not None and (said := oncall_last_message(p.path, now))
                       else None},
            "watchdog": {"installed": monitor is not None, "ok": bool(monitor and monitor[0])}}


def fast_facts(projects: list, now: float) -> tuple[dict | None, dict[Path, int], dict[Path, int] | None]:
    """(quota, running agents per checkout, busy sessions per checkout or None without the registry): the facts that
    change by the second, cheap enough to read every few seconds."""
    try:
        q = quota_snapshot(now)
    except Exception as e:  # a malformed cache must not cost the owner the whole feed
        print(f"status feed: quota unreadable — {e}", file=sys.stderr)
        q = None
    try:
        agents = agents_by_checkout([p.path for p in projects], now)
    except Exception as e:
        print(f"status feed: agent registry unreadable — {e}", file=sys.stderr)
        agents = {}
    return q, agents, live_busy([p.path for p in projects], now)


def build_feed(projects: list, now: float) -> dict:
    q, agents, busy = fast_facts(projects, now)
    rows = []
    for p in projects:
        try:
            rows.append(project_row(p, now, agents.get(p.path, 0), None if busy is None else busy.get(p.path, 0), q))
        except Exception as e:  # one project's broken check must not cost the owner the whole feed
            rows.append({"name": p.name, "working": False, "agents": 0, "busy_sessions": None,
                         "waiting_quota": False, "queue_ready": 0, "last_worked_at": None, "session_url": None,
                         "oncall": {"installed": False, "running": False, "last_message_at": None},
                         "watchdog": {"installed": False, "ok": False},
                         "error": str(e).replace(str(p.path), p.name)})
    return {"version": 2, "generated_at": iso(now), "full_at": iso(now), "quota": q, "projects": rows}


def live_busy(checkouts: list[Path], now: float) -> dict[Path, int] | None:
    try:
        entries = registry(now)
    except Exception as e:
        print(f"status feed: session registry unreadable — {e}", file=sys.stderr)
        return None
    return None if entries is None else busy_by_checkout(checkouts, entries)


def overlay(doc: dict, projects: list, now: float) -> dict:
    """The full feed with fresh fast facts: working, agents, busy sessions, quota. The heavy facts (On-call, watchdog,
    queue, link, last worked) and `full_at` stay as the last `feed` run wrote them."""
    q, agents, busy = fast_facts(projects, now)
    by_name = {p.name: p for p in projects}
    rows = []
    for row in doc.get("projects") or []:
        p = by_name.get(row.get("name"))
        if p is not None and "error" not in row:
            n = agents.get(p.path, 0)
            bs = None if busy is None else busy.get(p.path, 0)
            row = {**row, "agents": n, "busy_sessions": bs,
                   "working": (bs > 0 if bs is not None else transcript_busy(p.path, now)) or n > 0,
                   "waiting_quota": bool(q and q.get("no_new_work") and row.get("queue_ready", 0) > 0)}
        rows.append(row)
    return {**doc, "generated_at": iso(now), "full_at": doc.get("full_at") or doc.get("generated_at"), "quota": q,
            "projects": rows}


def write_feed(doc: dict, path: Path = FEED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status.")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, path)


def feed(projects: list) -> int:
    write_feed(build_feed(projects, time.time()))
    return 0


# ---------- the live document ----------

RECOMPUTE = 30  # recompute even without a watched change: dead pids, the transcript fallback, ageing quota


class Live:
    """The served document: the last full feed (status.json) with fast facts overlaid. `tick` runs every few seconds
    and recomputes only when a watched file changed (or every RECOMPUTE seconds); streams wait on `wait`."""

    def __init__(self, path: Path, projects: list):
        self.path, self.projects = path, projects
        self.seq = 0
        self._cond = threading.Condition()
        self._doc: bytes | None = None
        self._same: dict | None = None  # the published doc without generated_at
        self._full: dict | None = None
        self._fp = None
        self._at = 0.0

    def fingerprint(self) -> tuple:
        def mtime(f: Path):
            try:
                st = f.stat()
                return st.st_mtime_ns, st.st_size
            except OSError:
                return None
        sessions = sorted((f.name, mtime(f)) for f in sessions_dir().glob("*.json"))
        return (tuple(sessions), mtime(quota.state_dir() / quota.AGENTS), mtime(quota.state_dir() / quota.CACHE),
                mtime(self.path))

    def tick(self, now: float) -> bool:
        """True when a new document was published."""
        fp = self.fingerprint()
        if fp == self._fp and now - self._at < RECOMPUTE:
            return False
        if self._fp is None or fp[-1] != self._fp[-1]:
            try:
                self._full = json.loads(self.path.read_text())
            except OSError:
                self._full = None
            except ValueError:
                pass  # caught mid-write by something other than write_feed: keep the last good one
        self._fp, self._at = fp, now
        if self._full is None:
            return False
        doc = overlay(self._full, self.projects, now)
        same = {k: v for k, v in doc.items() if k != "generated_at"}
        if same == self._same:
            return False
        with self._cond:
            self._doc, self._same = json.dumps(doc, separators=(",", ":")).encode(), same
            self.seq += 1
            self._cond.notify_all()
        return True

    def current(self) -> bytes | None:
        with self._cond:
            return self._doc

    def wait(self, seq: int, timeout: float) -> tuple[int, bytes | None]:
        """(seq, doc) once a document newer than `seq` is published, or the same seq after `timeout` seconds."""
        with self._cond:
            self._cond.wait_for(lambda: self.seq != seq, timeout)
            return self.seq, self._doc

    def run(self, every: float = 2.0) -> None:
        while True:
            try:
                self.tick(time.time())
            except Exception as e:  # the watcher must outlive one bad read
                print(f"status feed: watcher — {e}", file=sys.stderr)
            time.sleep(every)


# ---------- serving ----------

ROUTE, EVENTS = "/status.json", "/events"
KEEPALIVE = 20  # seconds between SSE comments on a quiet stream: a dead peer shows up as a failed write
MAX_STREAMS = 8  # the owner's devices; more is a leak, not a user


def parse_addr(text: str) -> tuple[str, int]:
    """host:port of a private address. A wildcard would publish the feed to every network the server is on."""
    host, sep, port = text.strip().rpartition(":")
    try:
        ip = ipaddress.IPv4Address(host)
    except ValueError:
        ip = None
    if (not sep or ip is None or ip.is_global or ip.is_unspecified or ip.is_multicast
            or not port.isdigit() or not 0 < int(port) < 65536):
        raise ValueError(f"FLEET_FEED_ADDR must be <private IPv4 address>:<port> (Tailscale, LAN, loopback), "
                         f"not {text!r}: the feed has no password, the private network is the boundary")
    return host, int(port)


def make_handler(live: Live):
    streams = threading.BoundedSemaphore(MAX_STREAMS)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == EVENTS:
                return self.events()
            if self.path != ROUTE:
                return self.send_error(404)
            body = live.current()
            if body is None:
                return self.send_error(503, "feed not written yet")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def events(self):
            """Server-Sent Events: the document now, then on every change; a comment when quiet."""
            seq, body = live.wait(-1, 0)
            if body is None:
                return self.send_error(503, "feed not written yet")
            if not streams.acquire(blocking=False):
                return self.send_error(503, "too many streams")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    self.wfile.write(b"data: " + body + b"\n\n" if body is not None else b": keep-alive\n\n")
                    self.wfile.flush()
                    new, doc = live.wait(seq, KEEPALIVE)
                    body, seq = (doc if new != seq else None), new
            except OSError:  # the client went away
                pass
            finally:
                streams.release()

        def refuse(self):
            self.send_error(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = refuse

        def log_message(self, format, *args):  # the journal gets server errors only, not every poll
            pass

        def log_request(self, code="-", size="-"):
            if str(getattr(code, "value", code)).startswith("5"):
                print(f"status feed: {self.requestline} → {code}", file=sys.stderr)

    return Handler


def serve(addr: str, projects: list, path: Path = FEED_PATH, every: float = 2.0) -> int:
    try:
        host, port = parse_addr(addr)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    live = Live(path, projects)
    live.tick(time.time())
    threading.Thread(target=live.run, args=(every,), daemon=True).start()
    with ThreadingHTTPServer((host, port), make_handler(live)) as httpd:
        httpd.daemon_threads = True
        httpd.serve_forever()
    return 0

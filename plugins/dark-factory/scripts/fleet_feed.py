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
    busy, newest = False, None
    for d in transcript_dirs(checkout, root):
        busy = busy or any(session_busy(f, now) for f in d.glob("*.jsonl"))
        for f in d.rglob("*.jsonl"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            newest = m if newest is None else max(newest, m)
    return busy, newest


def agents_by_checkout(checkouts: list[Path], now: float) -> dict[Path, int]:
    """Running subagents per checkout, from the quota guard's registry (a worktree counts for its checkout)."""
    live = quota.agents_live(quota._read(quota.AGENTS) or {}, now)
    counts = {c: 0 for c in checkouts}
    for v in live.values():
        cwd = Path(str(v.get("cwd", "")).split("/.claude/worktrees/")[0])
        for c in checkouts:
            if cwd == c or c in cwd.parents:
                counts[c] += 1
                break
    return counts


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

URL_RE = re.compile(r"https://claude\.ai/code[^\s'\"<>)]*")
REPLY_TAIL = 2 * 1024 * 1024
ONCALL_WINDOW = 3600  # the app shows "On-call wrote N min ago" within an hour; older transcripts are not read


def pick_session_url(text: str) -> str | None:
    """The link a Claude session prints in its pane: the last session link, else the last environment link."""
    urls = URL_RE.findall(text)
    sessions = [u for u in urls if "/code/session_" in u]
    return (sessions or urls or [None])[-1]


def session_url(p) -> str | None:
    """The development session's link from its tmux pane, else the new-sessions remote-control's (an environment link:
    it opens the project's sessions in Claude)."""
    import fleet
    for sock in (p.sock, p.rc_sock):
        code, screen = fleet.sh(["tmux", "-L", sock, "capture-pane", "-p", "-J", "-t", "session", "-S", "-3000"])
        if code == 0 and (url := pick_session_url(screen)):
            return url
    return None


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


def project_row(p, now: float, agents: int, q: dict | None) -> dict:
    import fleet  # fleet imports this module for its commands
    busy, last = activity(p.path, now)
    desk, monitor, queue = fleet.check_desk(p), fleet.check_monitor(p, now), fleet.check_queue(p)
    m = re.search(r"ready: (\d+)", queue[1]) if queue else None
    ready = int(m.group(1)) if m else 0
    return {"name": p.name, "working": busy or agents > 0, "agents": agents,
            "waiting_quota": bool(q and q.get("no_new_work") and ready > 0), "queue_ready": ready,
            "last_worked_at": iso(last) if last else None, "session_url": session_url(p),
            "oncall": {"installed": desk is not None, "running": bool(desk and desk[0]),
                       "last_message_at": iso(said) if desk is not None and (said := oncall_last_message(p.path, now))
                       else None},
            "watchdog": {"installed": monitor is not None, "ok": bool(monitor and monitor[0])}}


def build_feed(projects: list, now: float) -> dict:
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
    rows = []
    for p in projects:
        try:
            rows.append(project_row(p, now, agents.get(p.path, 0), q))
        except Exception as e:  # one project's broken check must not cost the owner the whole feed
            rows.append({"name": p.name, "working": False, "agents": 0, "waiting_quota": False, "queue_ready": 0,
                         "last_worked_at": None, "session_url": None,
                         "oncall": {"installed": False, "running": False, "last_message_at": None},
                         "watchdog": {"installed": False, "ok": False},
                         "error": str(e).replace(str(p.path), p.name)})
    return {"version": 1, "generated_at": iso(now), "quota": q, "projects": rows}


def write_feed(doc: dict, path: Path = FEED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status.")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, path)


def feed(projects: list) -> int:
    write_feed(build_feed(projects, time.time()))
    return 0


# ---------- serving ----------

ROUTE = "/status.json"


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


def make_handler(path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != ROUTE:
                return self.send_error(404)
            try:
                body = path.read_bytes()
            except OSError:
                return self.send_error(503, "feed not written yet")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def refuse(self):
            self.send_error(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = refuse

        def log_message(self, format, *args):  # the journal gets server errors only, not every poll
            pass

        def log_request(self, code="-", size="-"):
            if str(getattr(code, "value", code)).startswith("5"):
                print(f"status feed: {self.requestline} → {code}", file=sys.stderr)

    return Handler


def serve(addr: str, path: Path = FEED_PATH) -> int:
    try:
        host, port = parse_addr(addr)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    with ThreadingHTTPServer((host, port), make_handler(path)) as httpd:
        httpd.serve_forever()
    return 0

"""The status feed for the owner's menu bar app: one status.json for every project of the server.

Read-only and model-free: transcripts, the quota cache and the subagent registry are read, never refreshed — the quota
is taken from the cache only, because a probe (`quota.py status`) spends quota.
See openspec/changes/menu-bar-status/design.md.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
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
            return True
        if kind == "assistant":
            content = (rec.get("message") or {}).get("content")
            return isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in content)
    return False


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


def quota_snapshot(now: float) -> dict | None:
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
            "last_worked_at": iso(last) if last else None, "session_url": None,
            "oncall": {"installed": desk is not None, "running": bool(desk and desk[0]), "last_message_at": None},
            "watchdog": {"installed": monitor is not None, "ok": bool(monitor and monitor[0])}}


def build_feed(projects: list, now: float) -> dict:
    q = quota_snapshot(now)
    agents = agents_by_checkout([p.path for p in projects], now)
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

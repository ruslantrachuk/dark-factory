"""The status feed for the owner's menu bar app: one status.json for every project of the server.

Read-only and model-free: transcripts, the quota cache and the subagent registry are read, never refreshed — the quota
is taken from the cache only, because a probe (`quota.py status`) spends quota.
See openspec/changes/menu-bar-status/design.md.
"""
from __future__ import annotations

import json
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

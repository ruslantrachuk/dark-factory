"""Where the numbers live on the server, the settings, project discovery and ISO weeks."""
from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude/projects"
SETTINGS = Path.home() / ".config/dark-factory/analytics.env"
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


@dataclass
class Settings:
    owner: set[str] = field(default_factory=set)  # the owner's system user and chat handles
    swear: list[str] = field(default_factory=list)  # extra swear roots
    test_cmds: list[str] = field(default_factory=list)  # extra test-command regexes


def state_dir() -> Path:
    return Path(os.environ.get("ANALYTICS_STATE", Path.home() / ".local/state/dark-factory/analytics"))


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines, shell quoting allowed, no expansion (the fleet's settings format)."""
    out: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if m and not line.lstrip().startswith("#"):
                vals = shlex.split(m.group(2), comments=True)
                out[m.group(1)] = vals[0] if vals else ""
    return out


def load_settings(path: Path | None = None) -> Settings:
    env = read_env(path or SETTINGS)
    return Settings(owner=set(env.get("ANALYTICS_OWNER", "").split()), swear=env.get("ANALYTICS_SWEAR", "").split(),
                    test_cmds=env.get("ANALYTICS_TEST_CMDS", "").split())


def transcript_dirs(checkout: Path, root: Path = PROJECTS_ROOT) -> list[Path]:
    """Claude Code keeps a checkout's transcripts in a dir named after its path (every non-alphanumeric → `-`); a
    worktree inside the checkout gets that name followed by `--…`."""
    name = re.sub(r"[^A-Za-z0-9]", "-", str(checkout))
    if not root.is_dir():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d.name == name or d.name.startswith(name + "--")))


def iso_week(ts: str) -> str:
    y, w, _ = parse_ts(ts).isocalendar()
    return f"{y}-W{w:02d}"


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def week_bounds(week: str) -> tuple[datetime, datetime]:
    m = WEEK_RE.match(week)
    if not m:
        raise ValueError(f"not an ISO week: {week!r} (expected YYYY-Www)")
    start = datetime.fromisocalendar(int(m.group(1)), int(m.group(2)), 1).replace(tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def next_week(week: str) -> str:
    return iso_week(week_bounds(week)[1].isoformat())


def save_week(week: str, data: dict) -> Path:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{week}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
    tmp.replace(path)
    return path


def load_week(week: str) -> dict | None:
    path = state_dir() / f"{week}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def stored_weeks() -> list[str]:
    d = state_dir()
    return sorted(p.stem for p in d.glob("*.json") if WEEK_RE.match(p.stem)) if d.is_dir() else []

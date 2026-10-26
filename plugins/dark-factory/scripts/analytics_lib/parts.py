"""When each part of the factory appeared: per project from its git history, for the factory from release tags and
the server's units. A part is dated by the first commit that added one of its files; a file added says the part was
installed, not that it was in use.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PARTS = {
    "base": (".harness/base-sha", "CODING_STANDARDS.md"),
    "on_call": ("scripts/feedback-desk.sh",),
    "monitor": ("scripts/ops/prod_monitor/monitor.py", "scripts/prod-monitor.sh"),
    "release_tag": ("scripts/release.sh",),
    "pipeline": (".claude/feature-pipeline.json",),
    "fences": (".claude/fences.env",),
}
SERVER_UNITS = {"janitor": "df-fleet-janitor.timer", "fleet_watch": "df-fleet-watch.timer",
                "analytics": "df-fleet-analytics.timer"}
RELEASE_TAG = re.compile(r"^v\d+$")
def git(checkout: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def project_parts(checkout: Path) -> dict[str, str]:
    """Part → ISO date of the first commit on HEAD that added one of its files."""
    if not checkout.is_dir():
        return {}
    out = {}
    for part, paths in PARTS.items():
        log = git(checkout, "log", "HEAD", "--diff-filter=A", "--format=%cs", "--reverse", "--", *paths)
        dates = (log or "").split()
        if dates:
            out[part] = min(dates)
    return out


def plugin_pins(checkout: Path) -> list[list[str]]:
    """[date, ref] each time the dark-factory plugin's pinned ref changed in .claude/settings.json."""
    log = git(checkout, "log", "HEAD", "--format=%H %cs", "--reverse", "--", ".claude/settings.json") or ""
    pins: list[list[str]] = []
    for line in log.splitlines():
        sha, date = line.split()
        try:
            data = json.loads(git(checkout, "show", f"{sha}:.claude/settings.json") or "")
            ref = data["extraKnownMarketplaces"]["dark-factory"]["source"]["ref"]
        except (ValueError, KeyError, TypeError):
            continue
        if not pins or pins[-1][1] != ref:
            pins.append([date, ref])
    return pins


def factory_parts(canon: Path | None, unit_dir: Path) -> dict:
    releases = {}
    if canon:
        refs = git(canon, "for-each-ref", "refs/tags", "--format=%(refname:short) %(creatordate:short)") or ""
        for line in refs.splitlines():
            name, _, date = line.partition(" ")
            if RELEASE_TAG.match(name) and date:
                releases[name] = date
    server = {}
    for part, pattern in SERVER_UNITS.items():
        dates = [datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
                 for p in unit_dir.glob(pattern)] if unit_dir.is_dir() else []
        if dates:
            server[part] = min(dates)
    return {"releases": releases, "server": server}

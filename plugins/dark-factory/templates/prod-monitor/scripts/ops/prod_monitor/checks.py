"""Cheap prod checks without a model: a snapshot from the prod DB (read-only) and gh, rules from project.py.

The watchdog collects the snapshot once a minute; the decision is the pure function `evaluate`, so it can be tested.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import project
from .envfile import read_env_file
from .rules import Anomaly, Rule

READ_ONLY_OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=30000"
RELEASE_FAILED_WINDOW = timedelta(hours=24)


@contextmanager
def read_only_connection() -> Iterator[Any]:
    import psycopg
    from psycopg.rows import dict_row

    url = read_env_file(project.ACCESS_FILE).get(project.DATABASE_URL_KEY)
    if not url:
        raise RuntimeError(f"{project.DATABASE_URL_KEY} is not set in {project.ACCESS_FILE}")
    with psycopg.connect(
        url, row_factory=dict_row, connect_timeout=15, options=READ_ONLY_OPTIONS
    ) as conn:
        yield conn


@dataclass(frozen=True)
class Snapshot:
    now: datetime
    row: dict[str, Any] = field(default_factory=dict)
    release_failed: str | None = None
    db_error: str | None = None


def evaluate(s: Snapshot, rules: list[Rule] | None = None) -> list[Anomaly]:
    found: list[Anomaly] = []
    if s.release_failed:
        found.append(Anomaly("release_failed", f"release failed: {s.release_failed}"))
    if s.db_error:
        found.append(Anomaly("db_unreachable", f"prod DB is not responding: {s.db_error}"))
        return found  # DB rules are not evaluated without the DB
    for rule in project.RULES if rules is None else rules:
        if (text := rule.test(s.row, s.now)) is not None:
            found.append(Anomaly(rule.key, text))
    return found


def last_failed_release(now: datetime) -> str | None:
    """Name of the last release run if it failed within a day; gh errors are no reason for an alarm."""
    if not project.RELEASE_WORKFLOW:
        return None
    cmd = ["gh", "run", "list", "-w", project.RELEASE_WORKFLOW, "-L", "1"]
    try:
        out = subprocess.run(
            [*cmd, "--json", "conclusion,displayTitle,createdAt"],
            capture_output=True,
            text=True,
            cwd=project.REPO,
            timeout=60,
        ).stdout
        runs = json.loads(out or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    if not runs or runs[0].get("conclusion") != "failure":
        return None
    created = datetime.fromisoformat(runs[0]["createdAt"].replace("Z", "+00:00"))
    if now - created >= RELEASE_FAILED_WINDOW:
        return None
    return runs[0].get("displayTitle") or "release"


def collect() -> Snapshot:
    now = datetime.now(UTC)
    release = last_failed_release(now)
    try:
        with read_only_connection() as conn:
            row = conn.execute(project.SNAPSHOT_SQL).fetchone()
    except Exception as exc:  # DB network/access is an anomaly in itself
        return Snapshot(now, release_failed=release, db_error=type(exc).__name__)
    return Snapshot(now=row["now"], row=dict(row), release_failed=release)

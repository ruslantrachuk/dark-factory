"""Watchdog anomaly rules: pure functions over a prod DB snapshot row, so they can be tested.

A rule gets the snapshot row (column → value) and the DB time, and returns the anomaly text or None.
The helpers cover typical cases; a custom rule is any function `(row, now) -> str | None`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class Anomaly:
    key: str  # stable name: the watchdog uses it to see whether the set of anomalies changed
    text: str


@dataclass(frozen=True)
class Rule:
    key: str
    test: Callable[[dict[str, Any], datetime], str | None]


def count_at_least(column: str, threshold: int, key: str, text: str) -> Rule:
    """The number in the column is ≥ the threshold. {v} is available in the text."""

    def test(row: dict[str, Any], now: datetime) -> str | None:
        v = row.get(column) or 0
        return text.format(v=v) if v >= threshold else None

    return Rule(key, test)


def seconds_above(column: str, limit_s: int, key: str, text: str) -> Rule:
    """Age in seconds (NULL — nothing is waiting) is above the limit. {v} and {m} (minutes) are available in the text."""

    def test(row: dict[str, Any], now: datetime) -> str | None:
        v = row.get(column)
        return text.format(v=v, m=v // 60) if v is not None and v > limit_s else None

    return Rule(key, test)


def stale_after(column: str, max_age: timedelta, key: str, text: str) -> Rule:
    """The time of the last event is older than max_age or missing. A time without a zone is taken as UTC."""

    def test(row: dict[str, Any], now: datetime) -> str | None:
        at = row.get(column)
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return text if at is None or now - at > max_age else None

    return Rule(key, test)

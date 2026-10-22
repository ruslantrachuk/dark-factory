"""Monitor verdict: parsing the model answer and deciding what to send to the group.

The same problem is not repeated on every pass: a message goes out when a new problem appears,
the status changes or `RESEND_AFTER` has passed. Problems are compared by the `key` of warn/crit findings — the model
names them with a short stable name (`beat_stalled`, `calendar_sync`), because the texts differ every time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

STATUSES = {"ok", "warn", "crit"}
PROBLEM_SEVERITIES = {"warn", "crit"}
RESEND_AFTER = timedelta(hours=6)


def parse_verdict(result: str | None) -> dict | None:
    if not result:
        return None
    raw = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return verdict if isinstance(verdict, dict) and verdict.get("status") in STATUSES else None


def _problem_keys(verdict: dict) -> list[str]:
    findings = verdict.get("findings") or []
    return sorted(
        {
            str(f.get("key") or f.get("what") or "")
            for f in findings
            if isinstance(f, dict) and f.get("severity") in PROBLEM_SEVERITIES
        }
    )


def _sent_is_current(sent: object, status: str, keys: list[str], now: datetime) -> bool:
    """The previous send covers the same problem and is not stale yet."""
    if not isinstance(sent, dict) or sent.get("status") != status or sent.get("keys") != keys:
        return False
    try:
        at = datetime.fromisoformat(str(sent["at"]))
    except (KeyError, ValueError):
        return False
    return now - at < RESEND_AFTER


def plan(verdict: dict, state: dict, now: datetime) -> tuple[str | None, dict]:
    """(status for the channel or None, new state). `resolved` — only after crit."""
    status = verdict["status"]
    if status == "ok":
        resolved = "resolved" if state.get("status") == "crit" else None
        return resolved, {"status": "ok", "sent": None}

    keys = _problem_keys(verdict)
    sent = state.get("sent")
    if _sent_is_current(sent, status, keys, now):
        return None, {"status": status, "sent": sent}
    return status, {
        "status": status,
        "sent": {"status": status, "keys": keys, "at": now.isoformat()},
    }

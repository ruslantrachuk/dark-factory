"""Tests of the prod monitoring loop: `python -m pytest scripts/ops/prod_monitor`.

Module mechanics (rules, when to wake the monitor, what to send to the group, agent isolation) — no network, no DB.
Test the project rules from project.RULES with your own tests next to these, following the rules below.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prod_monitor.checks import Snapshot, evaluate  # noqa: E402
from prod_monitor.rules import count_at_least, seconds_above, stale_after  # noqa: E402
from prod_monitor.verdict import RESEND_AFTER, parse_verdict, plan  # noqa: E402
from prod_monitor.watchdog import decide  # noqa: E402

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)  # not a scheduled slot hour in the default TZ (UTC)

RULES = [
    count_at_least("overdue", 1, "overdue", "overdue: {v}"),
    seconds_above("pending_age_s", 600, "stuck", "stuck for {m} min"),
    stale_after("last_synced", timedelta(hours=1), "sync_stale", "sync has not run for over an hour"),
]


def _healthy(**row) -> Snapshot:
    values = {"overdue": 0, "pending_age_s": None, "last_synced": NOW - timedelta(minutes=10)}
    values.update(row)
    return Snapshot(now=NOW, row=values)


def _keys(snapshot: Snapshot) -> set[str]:
    return {a.key for a in evaluate(snapshot, RULES)}


# --- watchdog rules ---


def test_healthy_snapshot_has_no_anomalies() -> None:
    assert evaluate(_healthy(), RULES) == []


def test_count_rule_and_text() -> None:
    [a] = evaluate(_healthy(overdue=2), RULES)
    assert (a.key, a.text) == ("overdue", "overdue: 2")


def test_age_rule_ignores_null_and_reports_minutes() -> None:
    assert _keys(_healthy(pending_age_s=599)) == set()
    [a] = evaluate(_healthy(pending_age_s=601), RULES)
    assert (a.key, a.text) == ("stuck", "stuck for 10 min")


def test_stale_rule_naive_time_is_utc_and_missing_is_stale() -> None:
    fresh = (NOW - timedelta(minutes=59)).replace(tzinfo=None)
    assert _keys(_healthy(last_synced=fresh)) == set()
    assert _keys(_healthy(last_synced=NOW - timedelta(minutes=61))) == {"sync_stale"}
    assert _keys(_healthy(last_synced=None)) == {"sync_stale"}


def test_failed_release_and_db_error_are_anomalies() -> None:
    assert _keys(Snapshot(now=NOW, row=_healthy().row, release_failed="v1")) == {"release_failed"}
    assert _keys(Snapshot(now=NOW, db_error="timeout")) == {"db_unreachable"}


def test_db_error_suppresses_db_rules() -> None:
    assert _keys(Snapshot(now=NOW, row={"overdue": 5}, db_error="timeout")) == {"db_unreachable"}


# --- when to wake the monitor ---

QUIET = {
    "last_keys": [],
    "last_wake": (NOW - timedelta(minutes=5)).isoformat(),
    "slots_done": ["2026-10-21 14"],
}


def test_quiet_and_nothing_changed_does_not_wake() -> None:
    assert decide([], QUIET, NOW).wake is False


def test_new_anomaly_wakes_immediately() -> None:
    decision = decide(evaluate(_healthy(overdue=1), RULES), QUIET, NOW)
    assert decision.wake is True
    assert decision.state["last_keys"] == ["overdue"]


def test_same_anomaly_does_not_rewake_within_hour() -> None:
    anomalies = evaluate(_healthy(overdue=1), RULES)
    state = {
        **QUIET,
        "last_keys": ["overdue"],
        "last_wake": (NOW - timedelta(minutes=30)).isoformat(),
    }
    assert decide(anomalies, state, NOW).wake is False
    state["last_wake"] = (NOW - timedelta(minutes=61)).isoformat()
    assert decide(anomalies, state, NOW).wake is True


def test_recovery_wakes_monitor_to_confirm() -> None:
    decision = decide([], {**QUIET, "last_keys": ["overdue"]}, NOW)
    assert decision.wake is True
    assert decision.state["last_keys"] == []


def test_scheduled_slot_wakes_once() -> None:
    at_nine = datetime(2026, 10, 21, 9, 3, tzinfo=UTC)  # slot 9:00 in the default TZ (UTC)
    first = decide([], {**QUIET, "slots_done": ["2026-10-20 19"]}, at_nine)
    assert first.wake is True
    assert decide([], first.state, at_nine + timedelta(minutes=1)).wake is False


def test_empty_state_is_valid() -> None:
    assert decide([], {}, NOW).wake is False


# --- what to send to the group ---


def _verdict(status: str, *keys: str) -> dict:
    findings = [{"severity": status, "key": key, "what": f"text about {key}"} for key in keys]
    findings.append({"severity": "info", "key": "background", "what": "background"})
    return {"status": status, "findings": findings}


def _state(status: str, keys: list[str], ago: timedelta = timedelta(minutes=30)) -> dict:
    return {
        "status": status,
        "sent": {"status": status, "keys": keys, "at": (NOW - ago).isoformat()},
    }


def test_parse_plain_and_fenced_json() -> None:
    assert parse_verdict('{"status": "ok", "findings": []}') == {"status": "ok", "findings": []}
    assert parse_verdict('```json\n{"status": "warn"}\n```') == {"status": "warn"}


def test_parse_rejects_garbage_and_unknown_status() -> None:
    assert parse_verdict(None) is None
    assert parse_verdict("prod is fine") is None
    assert parse_verdict('{"status": "fine"}') is None


def test_first_problem_is_sent_and_remembered() -> None:
    send, state = plan(_verdict("warn", "calendar"), {}, NOW)
    assert send == "warn"
    assert state["sent"] == {"status": "warn", "keys": ["calendar"], "at": NOW.isoformat()}


def test_same_problem_is_not_repeated() -> None:
    previous = _state("warn", ["calendar"])
    send, state = plan(_verdict("warn", "calendar"), previous, NOW)
    assert send is None
    assert state["sent"] == previous["sent"]  # the time of the previous send does not move


def test_info_findings_do_not_count_as_a_change() -> None:
    previous = _state("warn", ["calendar"])
    verdict = _verdict("warn", "calendar")
    verdict["findings"].append({"severity": "info", "key": "new_noise", "what": "more background"})
    assert plan(verdict, previous, NOW)[0] is None


def test_new_problem_in_the_set_is_sent() -> None:
    previous = _state("warn", ["calendar"])
    assert plan(_verdict("warn", "calendar", "outbound"), previous, NOW)[0] == "warn"


def test_status_change_is_sent_both_ways() -> None:
    assert plan(_verdict("crit", "beat"), _state("warn", ["beat"]), NOW)[0] == "crit"
    assert plan(_verdict("warn", "beat"), _state("crit", ["beat"]), NOW)[0] == "warn"


def test_same_problem_is_repeated_after_resend_interval() -> None:
    old = _state("warn", ["calendar"], ago=RESEND_AFTER + timedelta(minutes=1))
    assert plan(_verdict("warn", "calendar"), old, NOW)[0] == "warn"
    fresh = _state("warn", ["calendar"], ago=RESEND_AFTER - timedelta(minutes=1))
    assert plan(_verdict("warn", "calendar"), fresh, NOW)[0] is None


def test_resolved_only_after_crit_and_state_is_cleared() -> None:
    send, state = plan(_verdict("ok"), _state("crit", ["beat"]), NOW)
    assert send == "resolved"
    assert state == {"status": "ok", "sent": None}
    assert plan(_verdict("ok"), _state("warn", ["calendar"]), NOW)[0] is None
    assert plan(_verdict("ok"), {}, NOW)[0] is None


def test_problem_after_recovery_is_sent_again() -> None:
    _, state = plan(_verdict("ok"), _state("warn", ["calendar"]), NOW)
    assert plan(_verdict("warn", "calendar"), state, NOW)[0] == "warn"


def test_broken_state_does_not_block_sending() -> None:
    assert (
        plan(_verdict("warn", "calendar"), {"status": "warn", "sent": {"keys": "garbage"}}, NOW)[0]
        == "warn"
    )


# --- agent isolation ---


def test_monitor_does_not_load_user_settings_and_cannot_change_prod() -> None:
    """The user source enables plugin:telegram: on start it kills the bot token reader (the On-call agent)."""
    pytest.importorskip("claude_agent_sdk")
    from prod_monitor import monitor, project

    options = monitor._options()
    assert options.setting_sources == ["local"]
    assert options.tools == []
    for name in project.HOSTING_WRITE:
        assert name in options.disallowed_tools
        assert name not in options.allowed_tools

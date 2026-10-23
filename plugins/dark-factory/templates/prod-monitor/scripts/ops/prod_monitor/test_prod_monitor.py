"""Tests of the prod monitoring loop: `python -m pytest scripts/ops/prod_monitor`.

Module mechanics (rules, when to wake the monitor, what to send to the group, agent isolation) — no network, no DB.
Test the project rules from project.RULES with your own tests next to these, following the rules below.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prod_monitor.checks import Snapshot, evaluate  # noqa: E402
from prod_monitor.guards import GROUP_MAX_CHARS, GROUP_MAX_LINES, group_text, probe_url  # noqa: E402
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


# --- delivery to the monitor channel ---


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, *_: object) -> bytes:
        return self.body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _capture_requests(monkeypatch: pytest.MonkeyPatch) -> list:
    from prod_monitor import deliver

    sent: list = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001
        sent.append(req)
        return _Response(b'{"delivered": true}')

    monkeypatch.setattr(deliver.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_channel_post_carries_the_shared_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prod_monitor import deliver

    token_file = tmp_path / "channel.token"
    token_file.write_text("s3cret\n")
    monkeypatch.setattr(deliver, "CHANNEL_TOKEN_FILE", token_file)
    sent = _capture_requests(monkeypatch)
    assert deliver.post_channel("warn", "text") is True
    [req] = sent
    assert req.get_header("Authorization") == "Bearer s3cret"


def test_channel_post_without_secret_is_not_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prod_monitor import deliver

    monkeypatch.setattr(deliver, "CHANNEL_TOKEN_FILE", tmp_path / "missing.token")
    sent = _capture_requests(monkeypatch)
    assert deliver.post_channel("warn", "text") is False
    assert sent == []


# --- what the agent's output may reach ---

PROD = "https://app.example.com"


def test_probe_stays_on_the_prod_host() -> None:
    assert probe_url(PROD, "/health/ready") == "https://app.example.com/health/ready"
    assert probe_url(PROD + "/", "/health?x=1") == "https://app.example.com/health?x=1"
    assert probe_url("https://app.example.com:8443", "/h") == "https://app.example.com:8443/h"
    # a double slash stays a path on the prod host, not a scheme-relative URL
    assert probe_url(PROD, "//attacker.example/x") == "https://app.example.com//attacker.example/x"


@pytest.mark.parametrize(
    "path",
    [
        "@attacker.example/?d=secret",  # PROD_URL + path → host attacker.example
        "/@attacker.example",
        ".attacker.example/x",  # app.example.com.attacker.example
        ":8080/x",  # another port
        "/x y",
        "/x\\y",
        "/x\ny",
        "health",
        "",
        None,
        123,
    ],
)
def test_probe_refuses_paths_that_leave_the_host(path: object) -> None:
    with pytest.raises(ValueError):
        probe_url(PROD, path)


def test_probe_refuses_userinfo_in_the_base_url_too() -> None:
    with pytest.raises(ValueError):
        probe_url("https://user:pw@app.example.com", "/h")


def test_http_probe_tool_rejects_without_calling_curl(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("claude_agent_sdk")
    import asyncio

    from prod_monitor import monitor

    calls: list = []
    monkeypatch.setattr(monitor.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(monitor.project, "PROD_URL", PROD)
    out = asyncio.run(monitor.http_probe.handler({"path": "@attacker.example/?d=x"}))
    assert "prod host" in out["content"][0]["text"] or "must start" in out["content"][0]["text"]
    assert calls == []


def test_group_text_removes_urls_and_secrets() -> None:
    text = group_text(
        "Bookings are not sent since 10:00.\n"
        "See https://user:pw@evil.example/x and attacker.example/?d=abc and www.evil.example\n"
        "token=abc123 password: hunter2 Authorization: Bearer abc.def\n"
        "key sk-ant-api03-EXAMPLE ghp_EXAMPLEEXAMPLE 123456789:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
        "blob Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZg== end"
    )
    for leaked in ("http", "evil.example", "attacker.example", "abc123", "hunter2", "abc.def", "sk-ant",
                   "ghp_", "123456789:", "Zm9v"):
        assert leaked not in text, leaked
    assert text.startswith("Bookings are not sent since 10:00.")
    assert "[removed]" in text


def test_group_text_keeps_plain_language() -> None:
    plain = "Reminders stopped at 09:40 UTC.\nThe scheduler is stuck; the developer is looking into it."
    assert group_text(plain) == plain
    assert group_text("integration-sync-stale-for-two-hours-now") == "integration-sync-stale-for-two-hours-now"


def test_group_text_is_capped_and_never_raises() -> None:
    long = "\n".join(["word " * 50] * 20)
    text = group_text(long)
    assert len(text) <= GROUP_MAX_CHARS
    assert text.count("\n") < GROUP_MAX_LINES
    assert group_text(None) == ""
    assert group_text({"x": 1}) == ""
    assert group_text("a\x1b[31mb\x07") == "a[31mb"


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
    assert options.max_budget_usd == project.MAX_BUDGET_USD > 0  # spend cap per pass


# ---- prod-monitor.sh: the status line and the crontab ----

SCRIPT = Path(__file__).resolve().parent / "prod-monitor.sh"
CRON_TAG_LINE = "* * * * * run-watchdog # prod-monitor {root}"


def _script(tmp_path: Path, crontab_body: str, *args: str) -> subprocess.CompletedProcess:
    """Run prod-monitor.sh with a fake `crontab` (a file-backed one whose `-l` behaviour the test chooses)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "crontab").write_text(crontab_body)
    (bin_dir / "crontab").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PM_ROOT": str(tmp_path / "pm"),
           "PROD_MONITOR_CONFIG": str(tmp_path / "cfg"), "MONITOR_CHANNEL_PORT": "1", "HOME": str(tmp_path),
           "FAKE_CRON": str(tmp_path / "cron.txt")}
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)


FILE_CRONTAB = """#!/bin/bash
case "$1" in
  -l) [ -f "$FAKE_CRON" ] && cat "$FAKE_CRON" || { echo "no crontab for $USER" >&2; exit 1; } ;;
  -) cat > "$FAKE_CRON" ;;
esac
"""
BROKEN_CRONTAB = """#!/bin/bash
case "$1" in
  -l) echo "crontab: permission denied" >&2; exit 1 ;;
  -) cat > "$FAKE_CRON" ;;
esac
"""


def test_status_of_a_watchdog_that_never_logged_still_prints_a_line(tmp_path: Path) -> None:
    state = tmp_path / "pm/state/prod_monitor"
    state.mkdir(parents=True)
    (state / "watchdog.log").write_text("Traceback (most recent call last):\nModuleNotFoundError: x\n")
    r = _script(tmp_path, FILE_CRONTAB, "status")
    assert r.returncode == 0, r.stderr
    assert "no quiet/wake/fallback entry" in r.stdout


def test_down_removes_only_our_line(tmp_path: Path) -> None:
    mine = CRON_TAG_LINE.format(root=tmp_path / "pm")
    (tmp_path / "cron.txt").write_text(f"0 3 * * * backup\n{mine}\n")
    r = _script(tmp_path, FILE_CRONTAB, "down")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "cron.txt").read_text() == "0 3 * * * backup\n"


def test_down_with_no_crontab_at_all_is_fine(tmp_path: Path) -> None:
    assert _script(tmp_path, FILE_CRONTAB, "down").returncode == 0


def test_a_failing_crontab_listing_never_overwrites_the_crontab(tmp_path: Path) -> None:
    (tmp_path / "cron.txt").write_text("0 3 * * * backup\n")
    r = _script(tmp_path, BROKEN_CRONTAB, "down")
    assert r.returncode != 0
    assert "permission denied" in r.stderr
    assert (tmp_path / "cron.txt").read_text() == "0 3 * * * backup\n"

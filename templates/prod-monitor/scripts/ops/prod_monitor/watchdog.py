"""Prod watchdog: once a minute from cron, no model.

Collects a snapshot (`checks.collect`), looks for anomalies and wakes the monitor (SDK agent) when:
- the set of anomalies changed (a new one, or one is gone — the monitor confirms "fixed");
- an anomaly persists and the monitor has not been called for more than an hour;
- a scheduled slot has come (project.SLOT_HOURS).
If the monitor did not answer while there are anomalies, the watchdog sends a short alert itself (channel → group).
This also covers an exhausted subscription quota: the model does not answer, the alert goes out without it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import project
from .checks import collect, evaluate
from .deliver import deliver
from .rules import Anomaly

STATE_FILE = project.STATE_DIR / "watchdog.json"
SLOT_WINDOW_MIN = 10  # cron may skip a minute — a slot counts within the first 10 minutes of the hour
REWAKE_AFTER = timedelta(hours=1)
MONITOR_TIMEOUT_S = 420


@dataclass(frozen=True)
class Decision:
    wake: bool
    reason: str
    state: dict


def _due_slot(now: datetime, done: list[str]) -> str | None:
    local = now.astimezone(ZoneInfo(project.TZ))
    slot = local.strftime("%Y-%m-%d %H")
    if local.hour in project.SLOT_HOURS and local.minute < SLOT_WINDOW_MIN and slot not in done:
        return slot
    return None


def decide(anomalies: list[Anomaly], state: dict, now: datetime) -> Decision:
    keys = sorted({a.key for a in anomalies})
    last_keys = sorted(state.get("last_keys", []))
    last_wake = datetime.fromisoformat(state["last_wake"]) if state.get("last_wake") else None
    slots_done = list(state.get("slots_done", []))[-10:]

    reason = ""
    if keys != last_keys:
        reason = "anomalies changed" if keys else "anomalies cleared"
    elif keys and (last_wake is None or now - last_wake >= REWAKE_AFTER):
        reason = "anomaly persists for over an hour"
    slot = _due_slot(now, slots_done)
    if slot:
        slots_done.append(slot)
        reason = reason or f"scheduled check {slot}:00"

    new_state = {**state, "last_keys": keys, "slots_done": slots_done}
    if reason:
        new_state["last_wake"] = now.isoformat()
    return Decision(wake=bool(reason), reason=reason, state=new_state)


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1))


def _run_monitor(trigger: dict) -> bool:
    cmd = [sys.executable, "-m", f"{__package__}.monitor"]
    try:
        done = subprocess.run(
            [*cmd, "--trigger", json.dumps(trigger, ensure_ascii=False)],
            cwd=Path(__file__).resolve().parent.parent,
            timeout=MONITOR_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def main() -> int:
    snapshot = collect()
    anomalies = evaluate(snapshot)
    decision = decide(anomalies, _load_state(), snapshot.now)
    _save_state(decision.state)
    stamp = snapshot.now.isoformat(timespec="seconds")
    if not decision.wake:
        print(f"{stamp} quiet keys={decision.state['last_keys']}", flush=True)
        return 0
    print(f"{stamp} wake: {decision.reason} keys={decision.state['last_keys']}", flush=True)
    trigger = {"reason": decision.reason, "anomalies": [a.text for a in anomalies]}
    if _run_monitor(trigger) or not anomalies:
        return 0
    text = "The monitor did not answer. The watchdog sees: " + "; ".join(a.text for a in anomalies)
    print(f"{stamp} monitor failed, fallback → {deliver('warn', text, trigger)}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Claude subscription quota watchdog: do not start work near the limit and leave time to save.

The quota is shared per account (5h and 7d windows) and computed by the server: a probe on any
machine sees the usage of all sessions, projects and machines. Locally there is only a cache and
a subagent registry (~/.cache/claude-quota*.json), one per machine.

Where the data comes from (tokens are not read):
  * probe — `claude -p … --output-format stream-json --verbose` emits a
    rate_limit_event with unifiedWindows.{five_hour,seven_day}.utilization; one
    short haiku request (~6 s), at most once per QUOTA_TTL seconds per machine;
  * status line — its JSON contains rate_limits.*.used_percentage; the
    `statusline` mode writes it to the cache for free after every model reply.

Stages (worst of the windows, same thresholds for 5h and 7d):
  NO_NEW  80%  no new work: subagents, Workflow, `bd … --claim` are denied
  WRAP    85%  after an action — a one-time instruction to wrap up
  HARD    90%  ceiling: only saving work is allowed — reading, git, bd, editing the devlog,
                   scheduling a continuation; a subagent may only read (it returns to its parent)
Fan-out: with 5h ≥ 60%, no more than 2 concurrent subagents per machine.

Every watchdog message names the time when work resumes (in the QUOTA_TZ zone and in UTC,
plus "in …"): an autonomous session saves, schedules its own continuation for that time
and ends the turn.

Hook modes (input — hook JSON on stdin): session-start, prompt (UserPromptSubmit),
pretool, posttool, subagent-start, subagent-stop, statusline.
Modes for humans and scripts: status, check (exit 1 from stage NO_NEW), refresh.

Settings (env): QUOTA_5H="80,85,90", QUOTA_7D="80,85,90", QUOTA_FAN="60,2",
QUOTA_TTL=600, QUOTA_TZ=UTC, CLAUDE_QUOTA_DIR=~/.cache;
QUOTA_GUARD=off — the watchdog stays silent (start the session with `QUOTA_GUARD=off claude`).
For a session that runs scheduled work, the thresholds can be lowered (QUOTA_5H="60,70,80"), leaving quota
for the sessions people are working in.

No data (probe failed) — work is not blocked, a warning is printed.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))
OK, NO_NEW, WRAP, HARD = 0, 1, 2, 3
STAGE_NAMES = {
    NO_NEW: "no new work",
    WRAP: "wrapping up",
    HARD: "save work only",
}
AGENT_TOOLS = {"Agent", "Task", "Workflow"}
READ_TOOLS = {"Read", "Grep", "Glob", "LS", "ToolSearch", "TaskOutput"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# scheduling a continuation after the reset — allowed even at the ceiling
SCHEDULE_TOOLS = {"ScheduleWakeup", "CronCreate", "CronList", "CronDelete", "RemoteTrigger", "TodoWrite"}
SCHEDULE_SUFFIXES = (
    "__send_later", "__create_trigger", "__update_trigger", "__delete_trigger",
    "__list_triggers", "__get_trigger",
)
CLAIM_RE = re.compile(r"\bbd\s+update\b.*--claim\b")
# Bash at the ceiling: every part of the command line is git/bd or a read-only filter;
# `cd` only as a step before another part
SAVE_CMDS = {"git", "bd"}
READ_CMDS = {"cat", "head", "tail", "wc", "grep", "rg", "jq", "sort", "uniq", "cut", "ls", "pwd", "date"}
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.S)
QUOTED_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
ENV_PREFIX_RE = re.compile(r"^(?:env(?:\s+-C\s+\S+)?\s+)?(?:\w+=\S*\s+)*")
SAVE_PATH_RE = re.compile(r"(^|/)(devlog(\.md$|/)|\.beads/)")
AGENT_TTL = 2 * 3600  # a subagent without SubagentStop for longer than this is considered gone


def _thresholds(name: str, default: str) -> list[float]:
    return [float(x) for x in os.environ.get(name, default).split(",")]


def limits() -> dict[str, list[float]]:
    return {
        "five_hour": _thresholds("QUOTA_5H", "80,85,90"),
        "seven_day": _thresholds("QUOTA_7D", "80,85,90"),
    }


def state_dir() -> Path:
    return Path(os.environ.get("CLAUDE_QUOTA_DIR", Path.home() / ".cache"))


# --- parsing sources ---------------------------------------------------------


def parse_stream(lines) -> dict | None:
    """Windows from the stream-json output of `claude -p` (the last rate_limit_event)."""
    found = None
    for line in lines:
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(ev, dict) or ev.get("type") != "rate_limit_event":
            continue
        uw = (ev.get("rate_limit_info") or {}).get("unifiedWindows") or {}
        windows = {
            key: {"pct": round(float(w["utilization"]) * 100, 1), "resets_at": int(w["resetsAt"])}
            for key, _ in WINDOWS
            if (w := uw.get(key)) and "utilization" in w
        }
        if windows:
            found = windows
    return found


def parse_statusline(data: dict) -> dict | None:
    """Windows from the JSON that Claude Code passes to the status line script."""
    rl = data.get("rate_limits") or {}
    windows = {
        key: {"pct": float(w["used_percentage"]), "resets_at": int(w["resets_at"])}
        for key, _ in WINDOWS
        if (w := rl.get(key)) and "used_percentage" in w
    }
    return windows or None


# --- decision ----------------------------------------------------------------


def effective_pct(window: dict | None, now: float) -> float:
    if not window or window["resets_at"] <= now:
        return 0.0  # the window has reset — the quota is full again
    return window["pct"]


def window_stage(window: dict | None, key: str, now: float) -> int:
    return min(HARD, sum(effective_pct(window, now) >= t for t in limits()[key]))


def stage(windows: dict, now: float) -> tuple[int, str]:
    """Worst stage across windows and a reason like "5h 92% ≥ 90% (resets 21:30 UTC)".

    On an equal stage the reason names the window that resets later: it holds longer.
    """
    worst, worst_reset, reason = OK, 0, "quota is fine"
    for key, label in WINDOWS:
        st = window_stage(windows.get(key), key, now)
        if st == OK or (st, windows[key]["resets_at"]) <= (worst, worst_reset):
            continue
        worst, worst_reset = st, windows[key]["resets_at"]
        pct = effective_pct(windows[key], now)
        reason = (
            f"subscription quota: {label} {pct:.0f}% ≥ {limits()[key][st - 1]:.0f}% "
            f"(resets {_fmt_time(worst_reset, now)})"
        )
    return worst, reason


def reopen_at(windows: dict, now: float) -> int | None:
    """When the stage drops below NO_NEW: the latest reset among the windows that hold."""
    resets = [
        windows[k]["resets_at"]
        for k, _ in WINDOWS
        if window_stage(windows.get(k), k, now) >= NO_NEW
    ]
    return max(resets) if resets else None


def _in(seconds: float) -> str:
    m = max(1, int(seconds // 60))
    d, h, m = m // 1440, m % 1440 // 60, m % 60
    return " ".join(f"{v}{u}" for v, u in ((d, "d"), (h, "h"), (m, "min")) if v) or "0min"


def resume_hint(windows: dict, now: float) -> str:
    """When to continue and how to wait — so that an autonomous session pauses by itself."""
    ts = reopen_at(windows, now)
    if ts is None:
        return ""
    utc = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f" Work resumes {_fmt_time(ts, now)} = {utc}, in {_in(ts - now)}. "
        "If you work autonomously: save your state, schedule a continuation for that time "
        "(CronCreate or send_later; ScheduleWakeup — chained, it reaches at most an hour ahead) and end the turn; "
        "otherwise tell the human this time."
    )


def is_guarded(hook: dict) -> bool:
    """Start of new work: a subagent, Workflow, claiming a task."""
    tool = hook.get("tool_name")
    if tool in AGENT_TOOLS:
        return True
    if tool == "Bash":
        return bool(CLAIM_RE.search((hook.get("tool_input") or {}).get("command", "")))
    return False


def is_saving_command(command: str) -> bool:
    """git/bd with read-only filters around them; quoted text and heredocs are not commands."""
    text = QUOTED_RE.sub("''", HEREDOC_RE.sub("", command))
    parts = [p.strip() for p in re.split(r"&&|\|\||;|\||\n", text) if p.strip()]
    words = [ENV_PREFIX_RE.sub("", p).split(maxsplit=1)[0:1] or [""] for p in parts]
    names = [w[0].rsplit("/", 1)[-1] for w in words]
    return bool(names) and all(n in SAVE_CMDS | READ_CMDS or (n == "cd" and i < len(names) - 1) for i, n in enumerate(names))


def is_saving(hook: dict) -> bool:
    """An action that saves work: reading, git/bd, editing devlog/ and .beads/."""
    tool = hook.get("tool_name")
    inp = hook.get("tool_input") or {}
    if tool in READ_TOOLS:
        return True
    if hook.get("agent_id"):
        return False  # a subagent does not save — it returns a report to its parent
    if tool in SCHEDULE_TOOLS or (tool or "").endswith(SCHEDULE_SUFFIXES):
        return True  # schedule a continuation after the reset
    if tool == "Bash":
        return is_saving_command(inp.get("command", ""))
    if tool in WRITE_TOOLS:
        return bool(SAVE_PATH_RE.search(inp.get("file_path") or inp.get("notebook_path") or ""))
    return False


def deny(reason: str, advice: str | None = None, hint: str = "") -> dict:
    advice = (
        advice
        or "No new work (subagents, claiming tasks): finish the current one and record the state."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"⛔ {reason}. {advice}{hint} Only a human can bypass this: restart the session with QUOTA_GUARD=off."
            ),
        }
    }


def pretool_decision(hook: dict, windows: dict, now: float, running: int) -> dict | None:
    st, reason = stage(windows, now)
    hint = "" if hook.get("agent_id") else resume_hint(windows, now)
    if st >= HARD and not is_saving(hook):
        if hook.get("agent_id"):
            advice = "Edits are forbidden: finish the work and return a report to the parent — what is done, what is left."
        else:
            advice = "Only saving work and scheduling a continuation are allowed: reading, git, bd, editing the devlog."
        return deny(reason, advice, hint)
    if st >= NO_NEW and is_guarded(hook):
        return deny(reason, hint=hint)
    fan_from, fan_max = _thresholds("QUOTA_FAN", "60,2")
    if (
        hook.get("tool_name") in AGENT_TOOLS
        and effective_pct(windows.get("five_hour"), now) >= fan_from
        and running >= fan_max
    ):
        return deny(
            f"subscription quota 5h ≥ {fan_from:.0f}%, subagents already running on this machine: {running}",
            f"No more than {fan_max:.0f} at a time: wait for one to finish or do it yourself.",
        )
    return None


def posttool_message(hook: dict, windows: dict, now: float) -> str | None:
    st, reason = stage(windows, now)
    if st < WRAP:
        return None
    sub = bool(hook.get("agent_id"))
    if st >= HARD:
        if sub:
            return f"⛔ {reason}. Edits are forbidden — return a report to the parent right away: what is done, what is left."
        return f"⛔ {reason}. Only saving work is allowed: git, bd, devlog.{resume_hint(windows, now)}"
    if sub:
        return (
            f"⚠️ {reason}. Wrap up: finish the current step and return a report to the parent — what is done, "
            "what is left, where you stopped. Do not start new steps."
        )
    return (
        f"⚠️ {reason}. Wrap up: bring the current step to a working state, commit WIP to the feature branch, "
        f"write the devlog and the state to bd (--notes), do not start new steps.{resume_hint(windows, now)}"
    )


def notice_key(hook: dict, windows: dict, now: float) -> str:
    """The wrap-up instruction — once per session, agent, stage and window."""
    st, _ = stage(windows, now)
    resets = ",".join(str((windows.get(k) or {}).get("resets_at", 0)) for k, _ in WINDOWS)
    return f"{hook.get('session_id')}:{hook.get('agent_id') or 'main'}:{st}:{resets}"


# --- subagent registry (per machine, all projects) ---------------------------


def agents_add(reg: dict, agent_id: str, cwd: str, now: float) -> dict:
    return {**reg, agent_id: {"cwd": cwd, "started": int(now)}}


def agents_remove(reg: dict, agent_id: str) -> dict:
    return {k: v for k, v in reg.items() if k != agent_id}


def agents_live(reg: dict, now: float) -> dict:
    return {k: v for k, v in reg.items() if now - v["started"] < AGENT_TTL}


def project_name(cwd: str) -> str:
    return Path(cwd.split("/.claude/worktrees/")[0]).name or cwd


# --- state files -------------------------------------------------------------


def _fmt_time(ts: int, now: float) -> str:
    fmt = "%H:%M %Z" if ts - now < 20 * 3600 else "%d.%m %H:%M %Z"
    return datetime.fromtimestamp(
        ts, ZoneInfo(os.environ.get("QUOTA_TZ", "UTC"))
    ).strftime(fmt)


def format_line(windows: dict, now: float) -> str:
    parts = []
    for key, label in WINDOWS:
        w = windows.get(key)
        if w and w["resets_at"] > now:
            parts.append(f"{label} {w['pct']:.0f}% (resets {_fmt_time(w['resets_at'], now)})")
        else:
            parts.append(f"{label} 0%")
    return " · ".join(parts)


def _read(name: str):
    try:
        return json.loads((state_dir() / name).read_text())
    except (OSError, ValueError):
        return None


def _write(name: str, data) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".claude-quota.")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, d / name)


@contextmanager
def _locked(name: str):
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


CACHE, AGENTS, NOTICES, LOG, PROBE_FAILED = (
    "claude-quota.json",
    "claude-quota-agents.json",
    "claude-quota-notices.json",
    "claude-quota.log",
    "claude-quota-probe-failed.json",
)


def write_cache(windows: dict, source: str) -> None:
    now = int(time.time())
    _write(CACHE, {"updated_at": now, "source": source, "windows": windows})
    # measurement log — to estimate later how much quota a task consumes
    line = "\t".join(
        [time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), source]
        + [f"{key}={w['pct']}" for key, w in windows.items()]
    )
    with open(state_dir() / LOG, "a") as f:
        f.write(line + "\n")


# Probe without user settings and MCP: plugins from ~/.claude/settings.json (e.g. plugin:telegram)
# also start inside `claude -p`, and a telegram plugin on startup kicks the bot reader off the On-call agent.
PROBE_CMD = [
    "claude",
    "-p",
    "ok",
    "--output-format",
    "stream-json",
    "--verbose",
    "--model",
    "haiku",
    "--no-session-persistence",
    "--setting-sources",
    "local",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
]


def probe() -> dict | None:
    """One short haiku request; outside the project directory so its hooks are not called."""
    env = dict(os.environ, CLAUDE_QUOTA_PROBE="1")
    try:
        proc = subprocess.run(
            PROBE_CMD,
            check=False,
            cwd=tempfile.gettempdir(),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"quota: probe failed: {exc}", file=sys.stderr)
        return None
    windows = parse_stream(proc.stdout.splitlines())
    if windows is None:
        print(
            f"quota: no rate_limit_event in the probe response (code {proc.returncode})", file=sys.stderr
        )
    return windows


def current(force: bool = False) -> dict | None:
    """Windows from a fresh cache or after a probe; one probe per machine (flock)."""
    ttl = float(os.environ.get("QUOTA_TTL", 600))

    def fresh():
        c = _read(CACHE)
        return c["windows"] if c and not force and time.time() - c["updated_at"] < ttl else None

    def failed_recently():
        f = _read(PROBE_FAILED)
        return bool(f) and not force and time.time() - f["at"] < ttl

    if (w := fresh()) is not None:
        return w
    with _locked(CACHE):
        if (w := fresh()) is not None:  # a neighbouring session may have refreshed it while we waited for the lock
            return w
        # a failed probe is not repeated before the TTL — otherwise every action waits for it again
        if not failed_recently():
            windows = probe()
            if windows:
                write_cache(windows, "probe")
                return windows
            _write(PROBE_FAILED, {"at": int(time.time())})
    cached = _read(CACHE)
    return cached["windows"] if cached else None  # stale is better than nothing


def running_agents(now: float) -> dict:
    return agents_live(_read(AGENTS) or {}, now)


def agents_line(now: float) -> str:
    live = running_agents(now)
    if not live:
        return ""
    by_project: dict[str, int] = {}
    for v in live.values():
        by_project[project_name(v["cwd"])] = by_project.get(project_name(v["cwd"]), 0) + 1
    return " · subagents: " + ", ".join(f"{p} {n}" for p, n in sorted(by_project.items()))


# --- modes -------------------------------------------------------------------


def _out(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "status"
    now = time.time()
    off = os.environ.get("QUOTA_GUARD") == "off" or os.environ.get("CLAUDE_QUOTA_PROBE") == "1"
    hook = json.load(sys.stdin) if mode not in ("status", "check", "refresh") else {}

    if mode == "statusline":
        windows = parse_statusline(hook)
        if windows:
            write_cache(windows, "statusline")
            print(format_line(windows, now))
        return 0

    if mode in ("subagent-start", "subagent-stop"):
        if hook.get("agent_id"):
            with _locked(AGENTS):
                reg = agents_live(_read(AGENTS) or {}, now)
                if mode == "subagent-start":
                    reg = agents_add(reg, hook["agent_id"], hook.get("cwd", ""), now)
                else:
                    reg = agents_remove(reg, hook["agent_id"])
                _write(AGENTS, reg)
        return 0

    if mode in ("session-start", "prompt", "pretool", "posttool") and off:
        return 0

    if mode == "pretool":
        # probe (up to 6 s) only for starting new work; other actions use the cache
        windows = current() if is_guarded(hook) else (_read(CACHE) or {}).get("windows")
        if windows is None:
            if is_guarded(hook):
                print("quota: no quota data — letting it through unchecked", file=sys.stderr)
            return 0
        if decision := pretool_decision(hook, windows, now, len(running_agents(now))):
            _out(decision)
        return 0

    if mode == "posttool":
        windows = current()
        if windows is None or (msg := posttool_message(hook, windows, now)) is None:
            return 0
        key = notice_key(hook, windows, now)
        with _locked(NOTICES):
            seen = _read(NOTICES) or {}
            if key in seen:
                return 0
            seen = {k: t for k, t in seen.items() if now - t < 8 * 86400}
            seen[key] = int(now)
            _write(NOTICES, seen)
        _out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}})
        return 0

    if mode in ("session-start", "prompt"):
        windows = current()
        if windows is None:
            print("📊 subscription quota: no data (probe failed)")
            return 0
        st, reason = stage(windows, now)
        tail = f" — ⛔ {STAGE_NAMES[st]}: {reason}.{resume_hint(windows, now)}" if st else ""
        print(f"📊 subscription quota: {format_line(windows, now)}{agents_line(now)}{tail}")
        return 0

    if mode in ("status", "check", "refresh"):
        windows = current(force=mode == "refresh")
        if windows is None:
            print("no quota data", file=sys.stderr)
            return 2
        st, reason = stage(windows, now)
        print(
            format_line(windows, now) + agents_line(now) + (f" — {STAGE_NAMES[st]}" if st else "")
        )
        if mode == "check" and st >= NO_NEW:
            print(reason, file=sys.stderr)
            return 1
        return 0

    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

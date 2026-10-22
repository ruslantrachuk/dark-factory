#!/usr/bin/env python3
"""Claude subscription quota watchdog: do not start work near the limit and leave time to save.

The quota is shared per account (5h and 7d windows) and computed by the server: a probe on any
machine sees the usage of all sessions, projects and machines. Locally there is only a cache and
a subagent registry (~/.cache/claude-quota*.json), one per machine.

Where the data comes from (tokens are not read):
  * probe — `claude -p … --output-format stream-json --verbose` emits a
    rate_limit_event with unifiedWindows.{five_hour,seven_day}.utilization; one
    short haiku request (~6 s), at most once per QUOTA_TTL seconds per machine; inline only when
    new work starts (PreToolUse) or a session starts, never waiting more than LOCK_WAIT seconds for
    another process's probe; after an action and on a prompt a stale cache starts a detached
    background refresh (`bg-refresh`) and the stale value is used;
  * status line — its JSON contains rate_limits.*.used_percentage; the
    `statusline` mode writes it to the cache for free after every model reply
    (/dark-factory:statusline wires it: scripts/statusline.py).

Stages (worst of the windows, same thresholds for 5h and 7d):
  NO_NEW  80%  no new work: subagents, Workflow, `bd … --claim` are denied
  WRAP    85%  after an action — a one-time instruction to wrap up
  HARD    90%  ceiling: only saving work is allowed — reading, bd (`bd sync` included), git add/
                   commit/status/diff/log/show/stash… (no -c/--config-env/GIT_* and other program-running
                   config), the PR description (`gh pr view/list`, `gh pr edit` of the title and body, a
                   `gh pr create --draft`), editing Claude Code's project memory (normalised paths),
                   booking a continuation for the reset time or later; no writes through redirections;
                   a subagent may only read (it returns to its parent)
QUOTA_ROLE=desk (the On-call session in the client chat): chat reply/react/edit, SendMessage,
ListAgents, ToolSearch and Read pass at every tier.
Fan-out: with 5h ≥ 60%, no more than 2 concurrent subagents per machine.

Every watchdog message names the time when work resumes (in the QUOTA_TZ zone and in UTC,
plus "in …"): an autonomous session saves, schedules its own continuation for that time
and ends the turn.

Hook modes (input — hook JSON on stdin): session-start, prompt (UserPromptSubmit),
pretool, posttool, subagent-start, subagent-stop, statusline.
Modes for humans and scripts: status, check (exit 1 from stage NO_NEW), refresh; bg-refresh (internal).

Settings (env): QUOTA_5H="80,85,90", QUOTA_7D="80,85,90", QUOTA_FAN="60,2",
QUOTA_TTL=600, QUOTA_TZ=UTC, CLAUDE_QUOTA_DIR=~/.cache;
QUOTA_GUARD=off — the watchdog stays silent (start the session with `QUOTA_GUARD=off claude`);
QUOTA_FAIL_CLOSED=1 (or the same line in .claude/fences.env) — no data counts as "no new work".
For a session that runs scheduled work, the thresholds can be lowered (QUOTA_5H="60,70,80"), leaving quota
for the sessions people are working in.

No data (probe failed) — work is not blocked, a warning is printed (unless QUOTA_FAIL_CLOSED=1).
The watchdog crashing counts the same: a warning, or with QUOTA_FAIL_CLOSED=1 new work is blocked
(exit 2 on PreToolUse) — never a silent pass.

Part of the dark-factory plugin (hooks/hooks.json), next to guard.py, whose shell reader it shares.
The project is $CLAUDE_PROJECT_DIR (else the git top level of the hook's cwd). A project opts in with
`.claude/fences.env`: without that file the hooks stay silent, apart from a one-line hint at session start.
"""

from __future__ import annotations

import fcntl
import io
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
# scheduling at the ceiling: listing and cancelling always; booking only for the reset time or later
# (schedule_ok) — a run that starts sooner is new work on the quota that is about to run out
SCHEDULE_SAFE = {"CronList", "CronDelete", "TodoWrite"}
SCHEDULE_SAFE_SUFFIXES = ("__delete_trigger", "__list_triggers", "__get_trigger")
SCHEDULE_BOOK = {"ScheduleWakeup", "CronCreate", "RemoteTrigger"}
SCHEDULE_BOOK_SUFFIXES = ("__send_later", "__create_trigger", "__update_trigger", "__fire_trigger")
# QUOTA_ROLE=desk (the On-call session in the client chat): answering the client is never cut off
DESK_TOOLS = {"SendMessage", "ListAgents", "ToolSearch", "Read"}
DESK_SUFFIXES = ("__reply", "__react", "__edit_message", "__download_attachment")
CLAIM_RE = re.compile(r"\bbd\s+update\b.*--claim\b")
# Bash at the ceiling: every command of the line (including $(…), `…`, bash -c) is bd, a
# saving/reading git subcommand or a read-only filter; `cd` only as a step before another
# command; output redirections only to /dev/null or between descriptors (2>&1, >&2).
# The line is read by the guard's shell reader (guard.py, next to this file): quoted text and heredoc
# bodies are data, not commands.
# bd is saving as a whole, `bd sync` included (it commits and pushes the queue); `bd … --claim` is new work
# and is denied by is_guarded from the NO_NEW tier on.
READ_CMDS = {"cat", "head", "tail", "wc", "grep", "rg", "jq", "sort", "uniq", "cut", "ls", "pwd", "date"}
# VAR=… prefixes allowed at the ceiling; anything else (GIT_*, PAGER, EDITOR, LD_PRELOAD, PATH…) can run a program
SAFE_ASSIGN = {"BEADS_DIR", "BEADS_DB", "BD_ACTOR", "LANG", "LC_ALL", "TZ", "NO_COLOR"}
# git options before the subcommand: these only; -c, --config-env, --exec-path, --git-dir… can run a program
GIT_SAFE_GLOBAL = {"--no-pager", "-P", "--no-optional-locks", "--no-replace-objects", "--literal-pathspecs",
                   "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs"}
GIT_SAVE_SUBCMDS = {"add", "commit", "status", "diff", "log", "show", "stash", "rev-parse", "ls-files", "branch", "worktree", "remote"}
GIT_STASH_SAVE = {"push", "save", "list", "show", "create", "store"}
# branch at the ceiling: listing only
GIT_BRANCH_CHANGE = {"--delete", "--move", "--copy", "--force", "--set-upstream-to", "--unset-upstream",
                     "--edit-description", "--track", "--no-track", "--create-reflog"}
GIT_BRANCH_VALUE_OPTS = {"--merged", "--no-merged", "--contains", "--no-contains", "--points-at",
                         "--sort", "--format", "--column"}
# writable at the ceiling: Claude Code's project memory, <config dir>/projects/<project>/memory/…, relative to
# the config dir ($CLAUDE_CONFIG_DIR, else ~/.claude)
SAVE_PATH_RE = re.compile(r"^projects/[^/]+/memory/")
# never writable there, even inside a save path: a git directory planted there would carry its own config
SAVE_PATH_DENY = re.compile(r"(^|/)\.git(/|$)|(^|/)(HEAD|config)$")
# gh at the ceiling: the PR is the record of work. Reading it, rewriting its title and description, opening it as
# a draft; nothing that merges, approves, closes, comments or runs a program.
GH_PR_READ = {"view", "list", "status", "diff", "checks"}
GH_PR_EDIT_OPTS = {"--title", "-t", "--body", "-b", "--body-file", "-F"}
GH_PR_CREATE_OPTS = GH_PR_EDIT_OPTS | {"--draft", "-d", "--base", "-B", "--head", "-H"}
GH_VALUE_OPTS = {"--title", "-t", "--body", "-b", "--body-file", "-F", "--base", "-B", "--head", "-H", "--repo", "-R",
                 "--json", "-q", "--jq", "--state", "-s", "--limit", "-L", "--search", "-S", "--author", "-A",
                 "--label", "-l", "--template", "-T"}
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
        "(CronCreate or send_later; ScheduleWakeup only if the reset is within its hour; a time before the "
        "reset is denied) and end the turn; "
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


def _redirects_ok(redirects) -> bool:
    """Output only to /dev/null or between descriptors (2>&1, >&2, 2>&-); input is fine."""
    for op, target in redirects:
        if ">" not in op or target == "/dev/null":
            continue
        if op == ">&" and (target.isdigit() or target == "-"):
            continue
        return False
    return True


def _guard():
    """guard.py next to this file — its shell reader is shared; None if the file is missing."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import guard
    except ImportError:
        return None
    return guard


def long_opt(arg: str, options) -> bool:
    """`--name[=value]` is one of the options or an abbreviation of one (getopt_long and git
    accept any unambiguous prefix: `sort --out=x` is `sort --output=x`)."""
    if not arg.startswith("--") or len(arg) < 3:
        return False
    name = arg.split("=", 1)[0]
    return any(opt.startswith(name) for opt in options)


def _assigns_ok(words) -> bool:
    """VAR=… before a command (also `env VAR=…`, `env -S '…'`): only the harmless ones."""
    guard = _guard()
    rest = guard._command_start(words)[0]
    k = next((i for i, w in enumerate(words) if rest and w is rest[0]), None)
    # the command word is not one of ours when `env -S` split it out: then every token is suspect
    prefix = words[:k] if k is not None else [t for w in words for t in w.split()] if rest else words
    for w in prefix:
        if guard.ASSIGN_RE.match(w) and w.split("=", 1)[0].rstrip("+") not in SAFE_ASSIGN:
            return False
    return True


def _git_saving(words) -> bool:
    i = 1
    while i < len(words) and words[i].startswith("-"):  # global options: -C dir and the harmless flags
        if words[i] == "-C":
            i += 2
            continue
        if words[i] not in GIT_SAFE_GLOBAL:
            return False  # -c core.pager=…, --config-env, --exec-path, --git-dir, --work-tree…
        i += 1
    sub, args, _, _ = _guard().git_split(words)
    if sub not in GIT_SAVE_SUBCMDS:
        return False
    flags = [a for a in args if a.startswith("-")]
    positional = [a for a in args if not a.startswith("-")]
    if any(long_opt(a, ("--output",)) for a in args):
        return False  # diff/log/show/stash show --output writes a file
    if sub == "stash":
        return not positional or positional[0] in GIT_STASH_SAVE
    if sub == "worktree":
        return positional[:1] == ["list"]
    if sub == "remote":
        return not positional and all(a in ("-v", "--verbose") for a in flags)
    if sub == "branch":
        listing = False
        i = 0
        while i < len(args):
            a = args[i]
            if long_opt(a, GIT_BRANCH_CHANGE):
                return False
            if a.startswith("-") and not a.startswith("--") and set(a[1:]) & set("dDmMcCfut"):
                return False
            if a in ("-l", "--list"):
                listing = True
            elif a in GIT_BRANCH_VALUE_OPTS:
                i += 1  # its value is not a branch name
            elif not a.startswith("-") and not listing:
                return False  # `git branch <name>` creates a branch
            i += 1
    return True


def _filter_saving(cmd) -> bool:
    """A read-only filter, minus the options that write or run programs."""
    args = cmd.words[1:]
    if cmd.name == "sort":
        return not any(
            long_opt(a, ("--output", "--compress-program"))
            or (a.startswith("-") and not a.startswith("--") and "o" in a[1:])
            for a in args
        )
    if cmd.name == "uniq":  # `uniq in out` writes out
        values = {"-f", "-s", "-w", "--skip-fields", "--skip-chars", "--check-chars"}
        positional, i = 0, 0
        while i < len(args):
            if args[i] in values:
                i += 1
            elif not args[i].startswith("-"):
                positional += 1
            i += 1
        return positional <= 1
    if cmd.name == "rg":
        return not any(long_opt(a, ("--pre",)) for a in args)
    if cmd.name == "date":  # -s sets the clock
        return not any(long_opt(a, ("--set",)) or (a.startswith("-") and not a.startswith("--") and "s" in a[1:])
                       for a in args)
    return True


def is_saving_command(command: str) -> bool:
    """bd, saving/reading git, read-only filters; no writes through redirections."""
    guard = _guard()
    if guard is None:
        return False
    parser = guard._Parser(command)  # every segment with its VAR=… prefix, $(…) included
    parser.parse()
    if not all(_assigns_ok(seg.words) for seg in parser.segments):
        return False
    cmds = guard.commands(command)
    named = [c for c in cmds if c.words]
    if not named or named[-1].name == "cd":
        return False
    for cmd in cmds:
        if not _redirects_ok(cmd.redirects):
            return False
        if not cmd.words or cmd.name in ("cd", "bd"):
            continue
        if cmd.words[0].dynamic:
            return False
        if cmd.name == "git":
            if not _git_saving(cmd.words):
                return False
        elif cmd.name == "gh":
            if not _gh_saving(cmd.words):
                return False
        elif cmd.name not in READ_CMDS or not _filter_saving(cmd):
            return False
    return True


def _gh_saving(words) -> bool:
    """gh pr view/list/status/diff/checks, gh pr edit of the title and body, gh pr create --draft."""
    args = list(words[1:])
    # the subcommand and every option name must be literal; a value ($(…) included) is data — the commands
    # inside $(…) are checked on their own
    if any(getattr(w, "dynamic", False) and (i < 2 or w.startswith("-")) for i, w in enumerate(args)):
        return False
    if len(args) < 2 or args[0] != "pr":
        return False
    sub, rest = args[1], args[2:]
    if sub in GH_PR_READ:
        allowed = None
    elif sub == "edit":
        allowed = GH_PR_EDIT_OPTS | {"--repo", "-R"}
    elif sub == "create":
        allowed = GH_PR_CREATE_OPTS | {"--repo", "-R"}
        if not any(a in ("--draft", "-d") for a in rest):
            return False
    else:
        return False
    if any(long_opt(a, ("--web", "--editor", "--fill", "--fill-first", "--fill-verbose")) or a in ("-w", "-e", "-f")
           for a in rest):
        return False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a.startswith("-"):
            name = a.split("=", 1)[0]
            if allowed is not None and name not in allowed:
                return False
            if name in GH_VALUE_OPTS and "=" not in a:
                i += 1
        i += 1
    return True


def config_dir() -> str:
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


def save_path_ok(path: str, cwd: str | None = None) -> bool:
    """An edit target inside Claude Code's project memory (<config dir>/projects/<project>/memory/) — after
    `..` and symlinks are resolved, so `memory/../../settings.json` or a memory/ symlink into src/ is not a
    save path."""
    if not path:
        return False
    root = os.path.realpath(config_dir())
    full = os.path.realpath(os.path.join(cwd or project_root(cwd), os.path.expanduser(path)))
    rel = os.path.relpath(full, root)
    if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
        return False
    return bool(SAVE_PATH_RE.match(rel)) and not SAVE_PATH_DENY.search(rel)


# --- scheduling at the ceiling ----------------------------------------------


def _cron_field(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-", 1))
        else:
            a = b = int(rng)
            if step:
                b = hi
        out.update(range(a, b + 1, int(step) if step else 1))
    if not out or min(out) < lo or max(out) > hi:
        raise ValueError(spec)
    return out


def cron_next(expr: str, after: float, local: bool = False, horizon: float = 9 * 86400) -> float | None:
    """The first run of a 5-field cron expression at or after `after` (an optional `CRON_TZ=Zone `
    prefix; else UTC, or local time); None if it does not run within the horizon. Raises
    ValueError on syntax it does not read (names like MON, @daily)."""
    tz = None if local else timezone.utc
    expr = expr.strip()
    if expr.startswith(("CRON_TZ=", "TZ=")):
        zone, _, expr = expr.partition(" ")
        tz = ZoneInfo(zone.split("=", 1)[1])
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(expr)
    minute, hour, dom, month = (_cron_field(f, lo, hi) for f, (lo, hi) in
                                zip(fields[:4], ((0, 59), (0, 23), (1, 31), (1, 12))))
    dow = {d % 7 for d in _cron_field(fields[4], 0, 7)}
    dom_any, dow_any = fields[2] == "*", fields[4] == "*"
    t = datetime.fromtimestamp((int(after) + 59) // 60 * 60, tz)
    end = after + horizon
    while t.timestamp() <= end:
        day_dom, day_dow = t.day in dom, (t.weekday() + 1) % 7 in dow
        day = (day_dom and day_dow) if dom_any or dow_any else (day_dom or day_dow)
        if t.month in month and day and t.hour in hour and t.minute in minute:
            return t.timestamp()
        t = datetime.fromtimestamp(t.timestamp() + 60, tz)
    return None


def _rfc3339(value) -> float:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"no time zone: {value}")
    return dt.timestamp()


def scheduled_at(tool: str, inp: dict, now: float) -> float | None:
    """When a booking tool would start the run; None if the input does not say (or it runs now)."""
    if tool == "RemoteTrigger":
        if inp.get("action") in ("run", None):
            return None
        inp = inp.get("body") or {}
    if tool.endswith("__fire_trigger"):
        return None
    if "delaySeconds" in inp or "delay_seconds" in inp:
        return now + float(inp.get("delaySeconds", inp.get("delay_seconds")))
    if "delay_minutes" in inp:
        return now + 60 * float(inp["delay_minutes"])
    for key in ("at", "run_once_at"):
        if inp.get(key):
            return _rfc3339(inp[key])
    for key in ("cron_expression", "cron", "schedule"):
        if inp.get(key):
            # session cron (CronCreate) runs in this machine's local time, scheduled tasks in UTC
            at = cron_next(str(inp[key]), now, local=tool == "CronCreate")
            return float("inf") if at is None else at  # not within 9 days — after any reset
    return None


def schedule_ok(tool: str, inp: dict, reset_at: float | None, now: float) -> bool:
    """A booking at the ceiling: listing/cancelling always; a run at the reset minute or later."""
    if tool in SCHEDULE_SAFE or tool.endswith(SCHEDULE_SAFE_SUFFIXES):
        return True
    if tool == "RemoteTrigger" and inp.get("action") in ("list", "get"):
        return True
    if tool.endswith("__update_trigger") and not any(
        k in inp for k in ("cron_expression", "run_once_at")
    ) and inp.get("enabled") is not True:
        return True  # rename, new prompt, disable — starts nothing
    try:
        at = scheduled_at(tool, inp, now)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
    return at is not None and reset_at is not None and at >= reset_at // 60 * 60


def is_schedule_tool(tool: str) -> bool:
    return tool in SCHEDULE_SAFE or tool in SCHEDULE_BOOK or tool.endswith(SCHEDULE_SAFE_SUFFIXES + SCHEDULE_BOOK_SUFFIXES)


def is_desk_tool(tool: str) -> bool:
    """QUOTA_ROLE=desk: answering the client and reading — allowed at every tier."""
    return os.environ.get("QUOTA_ROLE") == "desk" and (
        tool in DESK_TOOLS or (tool.startswith("mcp__") and tool.endswith(DESK_SUFFIXES))
    )


def is_saving(hook: dict, reset_at: float | None = None, now: float | None = None) -> bool:
    """An action that saves work: reading, git/bd, the PR description, editing the project memory, booking the
    continuation for the reset time (reset_at) or later."""
    tool = hook.get("tool_name") or ""
    inp = hook.get("tool_input") or {}
    if tool in READ_TOOLS:
        return True
    if hook.get("agent_id"):
        return False  # a subagent does not save — it returns a report to its parent
    if is_schedule_tool(tool):
        return schedule_ok(tool, inp, reset_at, time.time() if now is None else now)
    if tool == "Bash":
        return is_saving_command(inp.get("command", ""))
    if tool in WRITE_TOOLS:
        return save_path_ok(inp.get("file_path") or inp.get("notebook_path") or "", hook.get("cwd"))
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


def fail_closed(cwd: str | None = None) -> bool:
    """QUOTA_FAIL_CLOSED=1 (environment, else .claude/fences.env): no quota data counts as
    the "no new work" tier instead of letting work through — for unattended sessions."""
    value = os.environ.get("QUOTA_FAIL_CLOSED")
    if value is None:
        value = fences(project_root(cwd)).get("QUOTA_FAIL_CLOSED", "")
    return value == "1"


def fences(root: str) -> dict[str, str]:
    """fences.env as the guard reads it (one parser: a later line wins), so the two never disagree."""
    guard = _guard()
    if guard is None:
        return {}
    if hasattr(guard, "effective_fences"):
        return guard.effective_fences(root)
    return guard.read_fences(root)


def project_root(cwd: str | None = None) -> str:
    """$CLAUDE_PROJECT_DIR, else the git top level of cwd, else cwd."""
    cwd = cwd or os.getcwd()
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.environ["CLAUDE_PROJECT_DIR"]
    guard = _guard()
    return guard.project_root(cwd) if guard else cwd


def opted_in(cwd: str | None = None) -> bool:
    """The project uses the fences: it has .claude/fences.env (base and /dark-factory:init create it)."""
    return (Path(project_root(cwd)) / ".claude" / "fences.env").is_file()


OPT_IN_HINT = (
    "dark-factory: the guard and the quota guard are off in this project (no .claude/fences.env); "
    "run /dark-factory:init to set it up."
)


def no_data_decision(hook: dict) -> dict | None:
    """No quota data: fail-closed denies starting new work, everything else goes through."""
    if not is_guarded(hook):
        return None
    return deny(
        "no subscription quota data (the probe failed) and QUOTA_FAIL_CLOSED=1 — treated as the "
        "\"no new work\" tier",
        "No new work (subagents, claiming tasks) until the quota is readable: check "
        f"`python3 {Path(__file__).resolve()} refresh`, or wire the status line feed "
        "(the human runs /dark-factory:statusline).",
    )


def pretool_decision(hook: dict, windows: dict, now: float, running: int) -> dict | None:
    st, reason = stage(windows, now)
    hint = "" if hook.get("agent_id") else resume_hint(windows, now)
    tool = hook.get("tool_name") or ""
    if is_desk_tool(tool):
        return None
    reset_at = reopen_at(windows, now)
    if st >= HARD and not is_saving(hook, reset_at, now):
        if hook.get("agent_id"):
            advice = "Edits are forbidden: finish the work and return a report to the parent — what is done, what is left."
        elif is_schedule_tool(tool):
            advice = (
                "Booking a run is allowed only for the reset time or later, with the time given explicitly "
                f"(at/run_once_at/delay/cron): not before {_fmt_time(reset_at, now) if reset_at else 'the reset'}; "
                "running a scheduled task now is denied."
            )
        else:
            advice = ("Only saving work and scheduling a continuation are allowed: reading, git, bd, the PR description "
                      "(gh pr edit), editing the project memory.")
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
        return f"⛔ {reason}. Only saving work is allowed: git, bd, the PR description, memory.{resume_hint(windows, now)}"
    if sub:
        return (
            f"⚠️ {reason}. Wrap up: finish the current step and return a report to the parent — what is done, "
            "what is left, where you stopped. Do not start new steps."
        )
    return (
        f"⚠️ {reason}. Wrap up: bring the current step to a working state, commit WIP to the feature branch, "
        f"update the PR description and the task notes in bd (the save skill), do not start new steps."
        f"{resume_hint(windows, now)}"
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
def _locked(name: str, wait: float | None = None):
    """An exclusive per-machine lock; yields False if it was not taken within `wait` seconds
    (None — wait as long as it takes, 0 — do not wait)."""
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.lock", "w") as lock:
        if wait is None:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield True
            return
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.1)
        yield True


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


LOCK_WAIT = 3  # seconds an inline probe waits for another process's probe before using the stale cache


def _ttl() -> float:
    return float(os.environ.get("QUOTA_TTL", 600))


def _fresh(force: bool = False) -> dict | None:
    c = _read(CACHE)
    return c["windows"] if c and not force and time.time() - c["updated_at"] < _ttl() else None


def _failed_recently(force: bool = False) -> bool:
    f = _read(PROBE_FAILED)
    return bool(f) and not force and time.time() - f["at"] < _ttl()


def _stale() -> dict | None:
    cached = _read(CACHE)
    return cached["windows"] if cached else None  # stale is better than nothing


def current(force: bool = False, wait: float | None = None) -> dict | None:
    """Windows from a fresh cache or after a probe; one probe per machine (flock). With `wait`,
    another process's probe is waited for at most that long, then the stale cache is used."""
    if (w := _fresh(force)) is not None:
        return w
    with _locked(CACHE, wait) as got:
        if not got:
            return _stale()
        if (w := _fresh(force)) is not None:  # a neighbouring session may have refreshed it while we waited for the lock
            return w
        # a failed probe is not repeated before the TTL — otherwise every action waits for it again
        if not _failed_recently(force):
            windows = probe()
            if windows:
                write_cache(windows, "probe")
                return windows
            _write(PROBE_FAILED, {"at": int(time.time())})
    return _stale()


def cached() -> dict | None:
    """The hot path (after every action, every prompt): never probe inline. A stale cache starts
    one detached background refresh — unless one is running or the last probe failed within the TTL —
    and the stale value is used meanwhile."""
    if (w := _fresh()) is not None:
        return w
    if not _failed_recently():
        with _locked(CACHE, wait=0) as free:  # held — a probe is running already
            pass
        if free:
            try:
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "bg-refresh"],
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                print(f"quota: background refresh did not start: {exc}", file=sys.stderr)
    return _stale()


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
    hook = json.load(sys.stdin) if mode not in ("status", "check", "refresh", "bg-refresh") else {}

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

    if mode in ("session-start", "prompt", "pretool", "posttool") and not opted_in(hook.get("cwd")):
        if mode == "session-start":
            print(OPT_IN_HINT)
        return 0

    if mode == "pretool":
        # probe (up to 6 s) only for starting new work; other actions use the cache
        windows = current(wait=LOCK_WAIT) if is_guarded(hook) else _stale()
        if windows is None:
            if is_guarded(hook):
                if fail_closed(hook.get("cwd")) and (decision := no_data_decision(hook)):
                    _out(decision)
                else:
                    print("quota: no quota data — letting it through unchecked", file=sys.stderr)
            return 0
        if decision := pretool_decision(hook, windows, now, len(running_agents(now))):
            _out(decision)
        return 0

    if mode == "posttool":
        windows = cached()
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
        windows = current(wait=LOCK_WAIT) if mode == "session-start" else cached()
        if windows is None:
            why = "probe failed" if _failed_recently() else "a refresh is running in the background"
            print(f"📊 subscription quota: no data ({why})")
            return 0
        st, reason = stage(windows, now)
        tail = f" — ⛔ {STAGE_NAMES[st]}: {reason}.{resume_hint(windows, now)}" if st else ""
        print(f"📊 subscription quota: {format_line(windows, now)}{agents_line(now)}{tail}")
        return 0

    if mode == "bg-refresh":  # started by cached(); a neighbour's refresh may have landed meanwhile
        current()
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


def crashed(argv: list[str], exc: BaseException) -> int:
    """The watchdog itself failed: like a failed probe, not like a pass. A hook exiting 1 lets
    everything through, so: fail-closed blocks the action (exit 2 on PreToolUse — new work only,
    when the hook can still be read), otherwise a warning and the action goes on."""
    mode = argv[1] if len(argv) > 1 else "status"
    msg = f"quota: the watchdog crashed ({type(exc).__name__}: {exc})"
    try:
        closed = fail_closed()
    except Exception:  # noqa: BLE001 — the fences file is unreadable too: the environment decides
        closed = os.environ.get("QUOTA_FAIL_CLOSED") == "1"
    if mode == "pretool" and closed:
        try:
            new_work = is_guarded(_crash_hook)
        except Exception:  # noqa: BLE001
            new_work = True
        if new_work:
            print(
                f"⛔ {msg} and QUOTA_FAIL_CLOSED=1 — treated as \"no data\": no new work (subagents, claiming "
                f"tasks). Check `python3 {Path(__file__).resolve()} status`. Only a human can bypass this: "
                "restart the session with QUOTA_GUARD=off.",
                file=sys.stderr,
            )
            return 2
    print(f"{msg} — letting it through unchecked", file=sys.stderr)
    return 0 if mode in HOOK_MODES else 2


HOOK_MODES = ("session-start", "prompt", "pretool", "posttool", "subagent-start", "subagent-stop", "statusline",
              "bg-refresh")
_crash_hook: dict | None = {}


def run(argv: list[str]) -> int:
    global _crash_hook
    try:
        if len(argv) > 1 and argv[1] in HOOK_MODES and argv[1] != "bg-refresh":
            raw = sys.stdin.read()
            try:
                _crash_hook = json.loads(raw)
            except ValueError:
                _crash_hook = None  # unreadable: in crashed() it counts as new work
            sys.stdin = io.StringIO(raw)
        return main(argv)
    except Exception as exc:  # noqa: BLE001 — any bug must not turn into "allowed"
        return crashed(argv, exc)


if __name__ == "__main__":
    sys.exit(run(sys.argv))

"""The status feed for the owner's status page: one status.json for every project of the server.

Read-only and model-free: transcripts, the quota cache and the subagent registry are read, never refreshed — the quota
is taken from the cache only, because a probe (`quota.py status`) spends quota.
`serve` refreshes the fast facts (working, agents, quota) within seconds and pushes them on /events.
See openspec/changes/menu-bar-status/design.md and openspec/changes/instant-status/design.md.
"""
from __future__ import annotations

import contextlib
import hmac
import ipaddress
import json
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import quota
from analytics_lib.store import PROJECTS_ROOT, transcript_dirs

BUSY_WINDOW = 600  # a session whose transcript is older than this is not mid-turn, whatever its last record says
QUOTA_FRESH = 1800  # an older quota cache counts as unknown
TAIL = 64 * 1024  # a session's last records are in the file's tail


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_busy(transcript: Path, now: float) -> bool:
    """A session is mid-turn when its last user/assistant record is not a finished answer: a prompt or a tool result
    waits for the model, a tool_use waits for the tool. A half-written last line is a record being written."""
    try:
        if now - transcript.stat().st_mtime > BUSY_WINDOW:
            return False
        with transcript.open("rb") as f:
            f.seek(max(0, f.seek(0, 2) - TAIL))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return False
    for i, line in enumerate(reversed([ln for ln in lines if ln.strip()])):
        try:
            rec = json.loads(line)
        except ValueError:
            if i == 0:
                return True
            continue
        kind = rec.get("type") if isinstance(rec, dict) else None
        if kind == "user":
            text = user_text(rec)
            if rec.get("isMeta") or text.startswith(("<command-name>", "<local-command")):
                continue  # a local command (/status, /clear) ran at the prompt: no turn
            return not text.startswith("[Request interrupted")
        if kind == "assistant":
            content = (rec.get("message") or {}).get("content")
            return isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in content)
    return False


def user_text(rec: dict) -> str:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        content = next((b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"), "")
    return content.lstrip() if isinstance(content, str) else ""


def activity(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> tuple[bool, float | None]:
    """(a session of the checkout is mid-turn, the newest transcript mtime). Subagent transcripts count for the time
    only: running subagents are counted from the registry."""
    newest = None
    for d in transcript_dirs(checkout, root):
        for f in d.rglob("*.jsonl"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            newest = m if newest is None else max(newest, m)
    return transcript_busy(checkout, now, root), newest


def transcript_busy(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> bool:
    """A session of the checkout is mid-turn by its transcript: the fallback without the session registry."""
    return any(session_busy(f, now) for d in transcript_dirs(checkout, root) for f in d.glob("*.jsonl"))


def count_by_checkout(checkouts: list[Path], cwds) -> dict[Path, int]:
    """How many of `cwds` fall in each checkout (a worktree counts for its checkout)."""
    counts = {c: 0 for c in checkouts}
    for cwd in cwds:
        cwd = Path(str(cwd).split("/.claude/worktrees/")[0])
        for c in checkouts:
            if cwd == c or c in cwd.parents:
                counts[c] += 1
                break
    return counts


def agents_by_checkout(checkouts: list[Path], now: float) -> dict[Path, int]:
    """Running subagents per checkout, from the quota guard's registry."""
    live = quota.agents_live(quota._read(quota.AGENTS) or {}, now)
    return count_by_checkout(checkouts, (v.get("cwd", "") for v in live.values()))


def sessions_dir() -> Path:
    return Path(quota.config_dir()) / "sessions"


def registry(now: float) -> list[dict] | None:
    """Claude Code's live sessions: one <pid>.json per running session with its cwd and `status` (busy while a turn
    runs, idle at the prompt). None when this Claude Code keeps no such registry — `working` then comes from
    transcripts."""
    d = sessions_dir()
    if not d.is_dir():
        return None
    entries = []
    for f in d.glob("*.json"):
        try:
            e = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(e, dict) and pid_alive(e.get("pid")):
            entries.append(e)
    return entries


def busy_by_checkout(checkouts: list[Path], entries: list[dict]) -> dict[Path, int]:
    return count_by_checkout(checkouts, (e["cwd"] for e in entries if e.get("status") == "busy" and e.get("cwd")))


@contextlib.contextmanager
def owner_thresholds():
    """The guard's thresholds as the owner's sessions see them: QUOTA_5H/7D from ~/.claude/settings.json `env` when
    this process (a systemd unit) has none of its own. Restored afterwards."""
    try:
        env = json.loads((Path(quota.config_dir()) / "settings.json").read_text()).get("env") or {}
    except (OSError, ValueError, AttributeError):
        env = {}
    added = {k: str(env[k]) for k in ("QUOTA_5H", "QUOTA_7D") if k in env and k not in os.environ}
    os.environ.update(added)
    try:
        yield
    finally:
        for k in added:
            os.environ.pop(k, None)


def quota_snapshot(now: float) -> dict | None:
    with owner_thresholds():
        return _quota_snapshot(now)


def _quota_snapshot(now: float) -> dict | None:
    cached = quota._read(quota.CACHE)
    if not cached or now - cached.get("updated_at", 0) > QUOTA_FRESH:
        return None
    windows = cached.get("windows") or {}
    pct = {k: round(quota.effective_pct(windows.get(k), now)) for k, _ in quota.WINDOWS}
    worst = max(((quota.window_stage(windows.get(k), k, now), windows[k]["resets_at"])
                 for k, _ in quota.WINDOWS if windows.get(k)), default=(quota.OK, 0))
    blocked = worst[0] >= quota.NO_NEW
    resets = {k: iso(windows[k]["resets_at"]) for k, _ in quota.WINDOWS
              if windows.get(k) and windows[k].get("resets_at")}
    return {"five_hour": pct["five_hour"], "seven_day": pct["seven_day"], "no_new_work": blocked,
            "resets_at": iso(worst[1]) if blocked else None, "resets": resets, "as_of": iso(cached["updated_at"])}


# ---------- session link, On-call ----------

SESSION_ID_RE = re.compile(r"(session|cse)_[A-Za-z0-9]+")


def pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return True


def session_url(p) -> str | None:
    """The development session's claude.ai link: the live session named like the project's SESSION_NAME."""
    return named_session_url(p.session_name)


def oncall_session_url(p) -> str | None:
    """The On-call's claude.ai link: the live session named like DESK_NAME of the project's feedback-desk config."""
    import fleet
    try:
        name = fleet.read_env(p.path / ".claude/feedback-desk/config.env").get("DESK_NAME", "")
    except fleet.SettingsError:
        return None
    m = re.fullmatch(r"\$\{\w+:-(.*)\}", name)  # the template writes DESK_NAME="${DESK_NAME:-<name>}"
    name = m.group(1) if m else name
    return named_session_url(name) if name and not name.startswith("$") else None


def named_session_url(name: str) -> str | None:
    """Claude Code keeps one file per live session in ~/.claude/sessions/<pid>.json with its name and its Remote
    Control id (bridgeSessionId). None when no live session has that name — the app then shows no link."""
    want = name.casefold()
    for f in sessions_dir().glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        sid = d.get("bridgeSessionId") if isinstance(d, dict) else None
        if (isinstance(sid, str) and SESSION_ID_RE.fullmatch(sid) and str(d.get("name", "")).casefold() == want
                and pid_alive(d.get("pid"))):
            return f"https://claude.ai/code/{sid}"
    return None


REPLY_TAIL = 2 * 1024 * 1024
ONCALL_WINDOW = 3600  # the app shows "On-call wrote N min ago" within an hour; older transcripts are not read


def last_reply(transcript: Path) -> float | None:
    """Time of the last outgoing chat message (a tool call ending in __reply: only the On-call has one)."""
    best = None
    try:
        with transcript.open("rb") as f:  # the tail only: a development session's transcript runs to tens of MB
            f.seek(max(0, f.seek(0, 2) - REPLY_TAIL))
            lines = f.read().decode("utf-8", "replace").splitlines()
            for line in lines:
                if "__reply" not in line:
                    continue
                try:
                    rec = json.loads(line)
                    content = (rec.get("message") or {}).get("content") or []
                    if rec.get("type") == "assistant" and any(
                            isinstance(b, dict) and b.get("type") == "tool_use"
                            and str(b.get("name", "")).endswith("__reply") for b in content):
                        ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
                        best = ts if best is None else max(best, ts)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return None
    return best


def oncall_last_message(checkout: Path, now: float, root: Path = PROJECTS_ROOT) -> float | None:
    times = []
    for d in transcript_dirs(checkout, root):
        for f in d.glob("*.jsonl"):
            try:
                fresh = now - f.stat().st_mtime <= ONCALL_WINDOW
            except OSError:
                continue
            if fresh and (t := last_reply(f)) is not None:
                times.append(t)
    return max(times, default=None)


# ---------- dev stands, level ----------

STANDS_FILE = ".claude/factory/stands.json"  # this server's stands: ports, tunnels, addresses — not in git
PROBE_TIMEOUT = 1.0
PROBE_EVERY = 30  # a stand's health is probed at most this often, however often the live feed recomputes
TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_probes: dict[tuple, tuple[float, str]] = {}


def stand_decls(p) -> list[dict]:
    """The project's dev stands on this server, from .claude/factory/stands.json: [{name, port, health?, checkout?,
    url? | tunnel?}]. A missing file is no stands; an entry without a name or a port is skipped."""
    try:
        decls = json.loads((p.path / STANDS_FILE).read_text())
    except OSError:
        return []
    except ValueError as e:
        print(f"status feed: {p.name}: {STANDS_FILE} unreadable — {e}", file=sys.stderr)
        return []
    return [d for d in decls if isinstance(d, dict) and isinstance(d.get("name"), str)
            and isinstance(d.get("port"), int) and 0 < d["port"] < 65536] if isinstance(decls, list) else []


def probe(port: int, health: str, now: float) -> str:
    """running when http://127.0.0.1:<port><health> answers below 500, stopped otherwise; cached PROBE_EVERY."""
    import urllib.error
    import urllib.request
    key = (port, health)
    hit = _probes.get(key)
    if hit and now - hit[0] < PROBE_EVERY:
        return hit[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{health}", timeout=PROBE_TIMEOUT) as r:
            state = "running" if r.status < 500 else "stopped"
    except urllib.error.HTTPError as e:
        state = "running" if e.code < 500 else "stopped"
    except (OSError, ValueError):
        state = "stopped"
    _probes[key] = (now, state)
    return state


def health_path(d: dict) -> str:
    h = d.get("health")
    return h if isinstance(h, str) and h.startswith("/") else "/"


def stand_url(d: dict) -> str | None:
    """A fixed https url, or the address of a cloudflared quick tunnel read from its container's log (it changes on
    every restart of the tunnel). SEAM: another tunnel or proxy — give `url`, or adapt this at install."""
    import fleet
    url = d.get("url")
    if isinstance(url, str):
        return url if url.startswith("https://") else None
    tunnel = d.get("tunnel")
    if not isinstance(tunnel, str) or not re.fullmatch(r"[\w.-]+", tunnel):
        return None
    code, out = fleet.sh(["docker", "logs", "--tail", "500", tunnel], timeout=5)
    found = TUNNEL_RE.findall(out) if code == 0 else []
    return found[-1] if found else None


def stand_git(p, d: dict) -> dict:
    """Where the stand's checkout is against origin's default branch: ref (the branch, or the default branch's name
    for a detached checkout on it, else the short sha), sha, behind, ahead, at (the commit's time)."""
    import fleet
    co = (p.path / d["checkout"]).resolve() if isinstance(d.get("checkout"), str) else p.path
    none = {"ref": None, "sha": None, "behind": None, "ahead": None, "at": None}
    if co != p.path and p.path not in co.parents:  # only the project's own checkout and its worktrees
        return none
    git = ["git", "-C", str(co)]
    code, sha = fleet.sh([*git, "rev-parse", "HEAD"])
    if code:
        return none
    remote = fleet.default_branch(p.path)
    behind = ahead = None
    if remote:
        code, out = fleet.sh([*git, "rev-list", "--left-right", "--count", f"{remote}...HEAD"])
        if code == 0 and len(out.split()) == 2:
            behind, ahead = map(int, out.split())
    branch = fleet.sh([*git, "symbolic-ref", "--short", "-q", "HEAD"])[1]
    ref = branch or (remote.split("/", 1)[1] if remote and ahead == 0 else sha[:8])
    code, ct = fleet.sh([*git, "log", "-1", "--format=%ct"])
    return {"ref": ref, "sha": sha, "behind": behind, "ahead": ahead,
            "at": iso(int(ct)) if code == 0 and ct.isdigit() else None}


def served(p, d: dict) -> dict:
    """The preview's checkout is the worktree stand.py serves it from, not a fixed one in stands.json."""
    import stand
    wt = stand.preview_worktree(p.path) if d["name"] == "preview" else None
    return {**d, "checkout": str(wt)} if wt else d


def stands(p, now: float) -> list[dict]:
    return [{"name": d["name"], "state": probe(d["port"], health_path(d), now), "url": stand_url(d),
             **stand_git(p, served(p, d))} for d in stand_decls(p)]


def stand_states(p, now: float) -> dict[str, str]:
    """name → running|stopped: the fast part of `stands`, for the live feed."""
    return {d["name"]: probe(d["port"], health_path(d), now) for d in stand_decls(p)}


def project_level(p) -> dict | None:
    """The project on the ladder (/dark-factory:level): None for a project that has not opted in."""
    import level
    info = level.detect(p.path)
    if not info["opted_in"] or info["level"] is None:
        return None
    nxt = [f"{k} {level.NAMES[int(k)]}" for k in info["next"]]
    return {"level": info["level"], "name": level.NAMES.get(info["level"]), "fence": info["fence"],
            "modules": [{"name": k, "installed": v} for k, v in info["evidence"]["modules"].items()],
            "next": ", ".join(nxt) or None}


# ---------- scheduled jobs ----------

FEED_PATH = Path(os.environ.get("FLEET_FEED", Path.home() / ".local/state/dark-factory/status.json"))
ROUTINES_PATH = FEED_PATH.with_name("routines.json")  # the account's cloud routines, as `fleet.py routines` saw them


def show(units: list[str], props: str) -> dict[str, dict[str, str]]:
    """`systemctl --user show` of several units: Id → {property: value}; a property given on several lines (a timer's
    TimersMonotonic) has them joined."""
    import fleet
    if not units:
        return {}
    code, out = fleet.sh(["systemctl", "--user", "show", "-p", f"Id,{props}", *units], timeout=10)
    blocks = {}
    for block in out.split("\n\n") if code == 0 else []:
        d: dict[str, str] = {}
        for k, _, v in (line.partition("=") for line in block.splitlines() if "=" in line):
            d[k] = f"{d[k]}\n{v}" if k in d else v
        if d.get("Id"):
            blocks[d["Id"]] = d
    return blocks


def schedule_of(t: dict) -> str | None:
    """`*-*-* 06:30:00 UTC` for a calendar timer, `every 15min` for an interval one."""
    m = re.search(r"OnCalendar=(.+?) ;", t.get("TimersCalendar", ""))
    if m:
        return m.group(1)
    m = re.search(r"OnUnitActiveUSec=(\S+)", t.get("TimersMonotonic", ""))
    return f"every {m.group(1)}" if m else None


def result_of(s: dict | None) -> str | None:
    """ok | failed | running of the timer's service's last run; None when it never ran. The run that is this process
    (the feed writing itself) is not "running": how its previous run ended is shown instead."""
    if not s or not s.get("ExecMainStartTimestamp"):
        return None
    if s.get("ActiveState") in ("activating", "active", "reloading") and s.get("MainPID") != str(os.getpid()):
        return "running"
    return "ok" if s.get("Result") == "success" and s.get("ExecMainStatus", "0") == "0" else "failed"


def timer_names(projects: list) -> tuple[list[str], dict[Path, list[str]]]:
    """The timers `provision` writes on this server — the server's own and each project's — and any other df- timer
    found among the unit files, given to the project whose prefix it carries."""
    import fleet
    try:
        env = fleet.read_env(fleet.FLEET_ENV)
    except fleet.SettingsError:
        env = {}
    def timers(units) -> list[str]:
        return [u for u in units if u.endswith(".timer")]
    server = timers(fleet.server_units("python3", [], env.get("FLEET_ANALYTICS_REPO") or None,
                                       env.get("FLEET_FEED_ADDR") or None))
    per: dict[Path, list[str]] = {}
    for p in projects:
        try:
            per[p.path] = timers(fleet.units_for(p, "claude", "tmux"))
        except fleet.SettingsError:
            per[p.path] = []
    by_sock = sorted(projects, key=lambda p: -len(p.sock))  # df-shop-x- before df-shop-
    for f in sorted(fleet.UNIT_DIR.glob(f"{fleet.PREFIX}*.timer")):
        if f.name in server or any(f.name in v for v in per.values()):
            continue
        owner = next((p for p in by_sock if f.name.startswith(f"{p.sock}-")), None)
        (per[owner.path] if owner else server).append(f.name)
    return server, per


def scheduled(projects: list) -> tuple[list[dict], dict[Path, list[dict]]] | None:
    """Every timer of the factory on this server: installed, enabled, its schedule, next and last run and how the
    last run ended. A timer `provision` would write but that is not there is reported as not installed. None
    without systemd."""
    import fleet
    if not fleet.platform_ok():
        return None
    server, per = timer_names(projects)
    names = server + [n for v in per.values() for n in v]
    code, out = fleet.sh(["systemctl", "--user", "list-timers", "--all", "-o", "json", *names], timeout=10)
    try:
        listed = {t["unit"]: t for t in json.loads(out)} if code == 0 else {}
    except (ValueError, TypeError, KeyError):
        listed = {}
    timers = show(names, "Description,LoadState,UnitFileState,TimersCalendar,TimersMonotonic,Unit")
    services = show([t["Unit"] for t in timers.values() if t.get("Unit")],
                    "Result,ActiveState,ExecMainStatus,ExecMainStartTimestamp,MainPID")

    def when(us) -> str | None:
        return iso(us / 1e6) if isinstance(us, int) and us > 0 else None

    def entry(unit: str, prefix: str, project_name: str | None = None) -> dict:
        t, lt = timers.get(unit, {}), listed.get(unit, {})
        installed = t.get("LoadState") == "loaded"
        title = re.sub(r"^dark factory: ", "", t.get("Description", "")) if installed else ""
        if project_name:
            title = title.replace(f" of {project_name}", "")
        return {"name": unit.removeprefix(prefix).removesuffix(".timer"), "title": title or None,
                "installed": installed, "enabled": t.get("UnitFileState") == "enabled",
                "schedule": schedule_of(t), "next_at": when(lt.get("next")), "last_at": when(lt.get("last")),
                "result": result_of(services.get(t.get("Unit", "")))}
    return ([entry(n, f"{fleet.PREFIX}fleet-") for n in server],
            {p.path: [entry(n, f"{p.sock}-", p.name) for n in per.get(p.path, [])] for p in projects})


ROUTINE_ID_RE = re.compile(r"trig_[A-Za-z0-9]+")


def routines(path: Path = ROUTINES_PATH) -> dict | None:
    """The account's recurring cloud routines as `fleet.py routines` last saw them: {checked_at, routines}. None
    when they were never checked."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("routines"), list) else None


# The trigger API is open to a Claude session only (RemoteTrigger, the account's own login), not to a script: a
# short headless run reads it. SEAM: a direct API client — replace check_routines' run, keep the document.
ROUTINES_PROMPT = (
    "Call the RemoteTrigger tool with action=list. For every trigger whose cron_expression is not empty, call "
    "RemoteTrigger with action=get and its trigger_id. Then print ONLY a JSON array, no prose and no code fence, one "
    'object per such trigger: {"id", "name", "enabled", "cron_expression", "next_run_at", "last_run": '
    '{"status", "fired_at", "finished_at", "session_id"} or null}, with the values exactly as the API gave them.')
ROUTINES_MODEL = "haiku"
ROUTINES_TIMEOUT = 300


def _text(v, limit: int = 200) -> str | None:
    return v[:limit] if isinstance(v, str) and v else None


def normalize_routines(raw) -> list[dict]:
    """The model's answer as the feed carries it; anything that is not a recurring routine with a trigger id is
    dropped. A run's status ROUTINE_RUN_STATUS_SUCCEEDED becomes ok, a failed or cancelled one failed. A disabled
    routine has no next run: the API keeps the one it had when it was disabled."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not (isinstance(r, dict) and isinstance(r.get("id"), str) and ROUTINE_ID_RE.fullmatch(r["id"])
                and _text(r.get("cron_expression"))):
            continue
        run = r.get("last_run") if isinstance(r.get("last_run"), dict) else {}
        status = str(run.get("status") or "").upper()
        result = ("ok" if "SUCCEEDED" in status else "running" if "RUNNING" in status or "PENDING" in status
                  else "failed" if status and "UNSPECIFIED" not in status else None)
        sid = run.get("session_id")
        enabled = r.get("enabled") is True
        out.append({"id": r["id"], "name": _text(r.get("name")) or r["id"], "enabled": enabled,
                    "schedule": _text(r.get("cron_expression")),
                    "next_at": _text(r.get("next_run_at"), 40) if enabled else None,
                    "last_at": _text(run.get("finished_at") or run.get("fired_at"), 40), "result": result,
                    "session_url": f"https://claude.ai/code/{sid}"
                    if isinstance(sid, str) and SESSION_ID_RE.fullmatch(sid) else None})
    return out


def check_routines(claude: str, path: Path = ROUTINES_PATH) -> int:
    """Read the account's cloud routines through a headless Claude run and save them for the feed. A failed run
    keeps the last saved list: the app shows how old it is."""
    import subprocess
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([claude, "-p", "--model", ROUTINES_MODEL, "--allowedTools", "RemoteTrigger",
                            "--output-format", "text", ROUTINES_PROMPT], cwd=path.parent, capture_output=True,
                           text=True, timeout=ROUTINES_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"✗ routines: {e}", file=sys.stderr)
        return 1
    m = re.search(r"\[.*\]", r.stdout, re.S)
    try:
        raw = json.loads(m.group(0)) if r.returncode == 0 and m else None
    except ValueError:
        raw = None
    if not isinstance(raw, list):
        print(f"✗ routines: no JSON list in the answer (exit {r.returncode}): {r.stdout[-300:]!r}", file=sys.stderr)
        return 1
    found = normalize_routines(raw)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".routines.")
    with os.fdopen(fd, "w") as f:
        json.dump({"checked_at": iso(time.time()), "routines": found}, f, indent=1)
    os.replace(tmp, path)
    print(f"routines: {len(found)} recurring, {sum(r['enabled'] for r in found)} enabled")
    return 0


def latest_release() -> str | None:
    """The newest release tag (v<N>) of the canon the owner's marketplace pin points at; None offline or without a
    pin."""
    import fleet
    pin = fleet.pin_of(fleet.CLAUDE_DIR / "settings.json")
    if not pin:
        return None
    code, out = fleet.sh(["git", "ls-remote", "--tags", f"https://github.com/{pin[0]}.git"], timeout=30)
    if code:
        return None
    tags = [t for t in re.findall(r"refs/tags/(\S+)", out) if fleet.TAG_RE.fullmatch(t)]
    return max(tags, key=lambda t: int(t[1:]), default=None)


def factory_version() -> dict:
    """The release this server runs (the plugin's) and the newest one in the canon: `fleet.py upgrade <latest>` moves
    the server when they differ."""
    import fleet
    return {"version": fleet.plugin_version() or None, "latest": latest_release()}


def project_template(p) -> dict | None:
    """The template release the project was deployed from (.harness/base-sha) and whether it matches the factory's;
    None for a project without one."""
    import fleet
    drift = fleet.check_drift(p)
    if drift is None:
        return None
    ref = (p.path / ".harness/base-sha").read_text().strip()
    return {"version": ref if ref.startswith("v") else ref[:8], "current": drift[0]}


# ---------- the document ----------


def project_row(p, now: float, agents: int, busy_sessions: int | None, q: dict | None) -> dict:
    """`busy_sessions` — the project's live sessions mid-turn per the registry, None without one."""
    import fleet  # fleet imports this module for its commands
    busy, last = activity(p.path, now)
    if busy_sessions is not None:
        busy = busy_sessions > 0
    desk, monitor, queue = fleet.check_desk(p), fleet.check_monitor(p, now), fleet.check_queue(p)
    m = re.search(r"ready: (\d+)", queue[1]) if queue else None
    ready = int(m.group(1)) if m else 0
    return {"name": p.name, "working": busy or agents > 0, "agents": agents, "busy_sessions": busy_sessions,
            "waiting_quota": bool(q and q.get("no_new_work") and ready > 0), "queue_ready": ready,
            "last_worked_at": iso(last) if last else None, "session_url": session_url(p),
            "oncall": {"installed": desk is not None, "running": bool(desk and desk[0]),
                       "last_message_at": iso(said) if desk is not None and (said := oncall_last_message(p.path, now))
                       else None,
                       "session_url": oncall_session_url(p) if desk is not None else None},
            "watchdog": {"installed": monitor is not None, "ok": bool(monitor and monitor[0])},
            "stands": stands(p, now), "level": project_level(p), "template": project_template(p)}


def fast_facts(projects: list, now: float) -> tuple[dict | None, dict[Path, int], dict[Path, int] | None]:
    """(quota, running agents per checkout, busy sessions per checkout or None without the registry): the facts that
    change by the second, cheap enough to read every few seconds."""
    try:
        q = quota_snapshot(now)
    except Exception as e:  # a malformed cache must not cost the owner the whole feed
        print(f"status feed: quota unreadable — {e}", file=sys.stderr)
        q = None
    try:
        agents = agents_by_checkout([p.path for p in projects], now)
    except Exception as e:
        print(f"status feed: agent registry unreadable — {e}", file=sys.stderr)
        agents = {}
    return q, agents, live_busy([p.path for p in projects], now)


def build_feed(projects: list, now: float) -> dict:
    q, agents, busy = fast_facts(projects, now)
    rows = []
    for p in projects:
        try:
            rows.append(project_row(p, now, agents.get(p.path, 0), None if busy is None else busy.get(p.path, 0), q))
        except Exception as e:  # one project's broken check must not cost the owner the whole feed
            rows.append({"name": p.name, "working": False, "agents": 0, "busy_sessions": None,
                         "waiting_quota": False, "queue_ready": 0, "last_worked_at": None, "session_url": None,
                         "oncall": {"installed": False, "running": False, "last_message_at": None},
                         "watchdog": {"installed": False, "ok": False},
                         "error": str(e).replace(str(p.path), p.name)})
    try:
        sched = scheduled(projects)
    except Exception as e:  # the timers are a section of the feed, not a reason to lose it
        print(f"status feed: timers unreadable — {e}", file=sys.stderr)
        sched = None
    if sched is not None:
        for p, row in zip(projects, rows):
            row["scheduled"] = sched[1].get(p.path, [])
    return {"version": 2, "generated_at": iso(now), "full_at": iso(now), "factory": factory_version(), "quota": q,
            "scheduled": {"server": sched[0] if sched else None, "cloud": routines()}, "projects": rows}


def live_busy(checkouts: list[Path], now: float) -> dict[Path, int] | None:
    try:
        entries = registry(now)
    except Exception as e:
        print(f"status feed: session registry unreadable — {e}", file=sys.stderr)
        return None
    return None if entries is None else busy_by_checkout(checkouts, entries)


def overlay(doc: dict, projects: list, now: float) -> dict:
    """The full feed with fresh fast facts: working, agents, busy sessions, quota, stand states. The heavy facts
    (On-call, watchdog, queue, links, stand refs, level, last worked) and `full_at` stay as the last `feed` run wrote
    them."""
    q, agents, busy = fast_facts(projects, now)
    by_name = {p.name: p for p in projects}
    rows = []
    for row in doc.get("projects") or []:
        p = by_name.get(row.get("name"))
        if p is not None and "error" not in row:
            n = agents.get(p.path, 0)
            bs = None if busy is None else busy.get(p.path, 0)
            row = {**row, "agents": n, "busy_sessions": bs,
                   "working": (bs > 0 if bs is not None else transcript_busy(p.path, now)) or n > 0,
                   "waiting_quota": bool(q and q.get("no_new_work") and row.get("queue_ready", 0) > 0)}
            if row.get("stands"):
                states = stand_states(p, now)
                row["stands"] = [{**s, "state": states.get(s["name"], s["state"])} for s in row["stands"]]
        rows.append(row)
    return {**doc, "generated_at": iso(now), "full_at": doc.get("full_at") or doc.get("generated_at"), "quota": q,
            "projects": rows}


def write_feed(doc: dict, path: Path = FEED_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status.")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, path)


def feed(projects: list) -> int:
    write_feed(build_feed(projects, time.time()))
    return 0


# ---------- the live document ----------

RECOMPUTE = 30  # recompute even without a watched change: dead pids, the transcript fallback, ageing quota


class Live:
    """The served document: the last full feed (status.json) with fast facts overlaid. `tick` runs every few seconds
    and recomputes only when a watched file changed (or every RECOMPUTE seconds); streams wait on `wait`."""

    def __init__(self, path: Path, projects: list):
        self.path, self.projects = path, projects
        self.seq = 0
        self._cond = threading.Condition()
        self._doc: bytes | None = None
        self._same: dict | None = None  # the published doc without generated_at
        self._full: dict | None = None
        self._fp = None
        self._at = 0.0

    def fingerprint(self) -> tuple:
        def mtime(f: Path):
            try:
                st = f.stat()
                return st.st_mtime_ns, st.st_size
            except OSError:
                return None
        sessions = sorted((f.name, mtime(f)) for f in sessions_dir().glob("*.json"))
        return (tuple(sessions), mtime(quota.state_dir() / quota.AGENTS), mtime(quota.state_dir() / quota.CACHE),
                mtime(self.path))

    def tick(self, now: float) -> bool:
        """True when a new document was published."""
        fp = self.fingerprint()
        if fp == self._fp and now - self._at < RECOMPUTE:
            return False
        if self._fp is None or fp[-1] != self._fp[-1]:
            try:
                self._full = json.loads(self.path.read_text())
            except OSError:
                self._full = None
            except ValueError:
                pass  # caught mid-write by something other than write_feed: keep the last good one
        self._fp, self._at = fp, now
        if self._full is None:
            return False
        doc = overlay(self._full, self.projects, now)
        same = {k: v for k, v in doc.items() if k != "generated_at"}
        if same == self._same:
            return False
        with self._cond:
            self._doc, self._same = json.dumps(doc, separators=(",", ":")).encode(), same
            self.seq += 1
            self._cond.notify_all()
        return True

    def current(self) -> bytes | None:
        with self._cond:
            return self._doc

    def wait(self, seq: int, timeout: float) -> tuple[int, bytes | None]:
        """(seq, doc) once a document newer than `seq` is published, or the same seq after `timeout` seconds."""
        with self._cond:
            self._cond.wait_for(lambda: self.seq != seq, timeout)
            return self.seq, self._doc

    def run(self, every: float = 2.0) -> None:
        while True:
            try:
                self.tick(time.time())
            except Exception as e:  # the watcher must outlive one bad read
                print(f"status feed: watcher — {e}", file=sys.stderr)
            time.sleep(every)


# ---------- serving ----------

ROUTE, EVENTS = "/status.json", "/events"
# The phone page (fleet_web/: the factory at a glance as a web app the owner adds to the Home Screen), only with
# FLEET_FEED_PAGE=on: without it the server answers as before, nothing without the token. Its files carry no state,
# so they are served without the token (a browser cannot send one when it opens an address); the page sends the
# token itself with /status.json and /events. Phones install it only over https: `tailscale serve` or Funnel in front.
WEB_DIR = Path(__file__).resolve().parent / "fleet_web"
WEB_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
             "/app.css": ("app.css", "text/css; charset=utf-8"),
             "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
             "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
             "/icon-180.png": ("icon-180.png", "image/png"), "/icon-192.png": ("icon-192.png", "image/png"),
             "/icon-512.png": ("icon-512.png", "image/png")}
# the page runs only its own scripts and talks only to this server (inline style attributes carry its colors)
PAGE_HEADERS = {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                           "base-uri 'none'; frame-ancestors 'none'",
                "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-cache"}
KEEPALIVE = 20  # seconds between SSE comments on a quiet stream: a dead peer shows up as a failed write
MAX_STREAMS = 8  # the owner's devices; more is a leak, not a user
# FLEET_FEED_TOKEN (fleet.env): every request must carry `Authorization: Bearer <token>`. Needed once the feed is
# reachable from outside the private network (a tunnel such as Tailscale Funnel); harmless inside it.
TOKEN_MIN = 32


def check_token(token: str | None) -> str | None:
    """The token as the server uses it, None for no token; ValueError on one too short to stand against guessing."""
    if not token:
        return None
    if len(token) < TOKEN_MIN or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError(f"FLEET_FEED_TOKEN must be at least {TOKEN_MIN} printable characters without spaces "
                         "(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')")
    return token


def parse_addr(text: str) -> tuple[str, int]:
    """host:port of a private address. A wildcard would publish the feed to every network the server is on."""
    host, sep, port = text.strip().rpartition(":")
    try:
        ip = ipaddress.IPv4Address(host)
    except ValueError:
        ip = None
    if (not sep or ip is None or ip.is_global or ip.is_unspecified or ip.is_multicast
            or not port.isdigit() or not 0 < int(port) < 65536):
        raise ValueError(f"FLEET_FEED_ADDR must be <private IPv4 address>:<port> (Tailscale, LAN, loopback), "
                         f"not {text!r}: the private network is the boundary — a tunnel out of it needs "
                         "FLEET_FEED_TOKEN")
    return host, int(port)


def web_files(root: Path = WEB_DIR) -> dict[str, tuple[bytes, str]]:
    """The page's files by path, read once; a plugin without them serves the feed alone."""
    out = {}
    for route, (name, kind) in WEB_FILES.items():
        with contextlib.suppress(OSError):
            out[route] = ((root / name).read_bytes(), kind)
    return out


def make_handler(live: Live, token: str | None = None, web: dict[str, tuple[bytes, str]] | None = None):
    """`web`: the page's files to serve (`web_files()`), none by default."""
    streams = threading.BoundedSemaphore(MAX_STREAMS)
    want = f"Bearer {token}".encode() if token else None
    pages = web or {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in pages:  # the page carries no state: it asks for the token and sends it with the feed
                return self.page(*pages[self.path])
            # before anything else: without the token no route, no state, no stream slot is told apart
            if want and not hmac.compare_digest(self.headers.get("Authorization", "").encode(), want):
                self.send_response(401)
                self.send_header("WWW-Authenticate", "Bearer")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == EVENTS:
                return self.events()
            if self.path != ROUTE:
                return self.send_error(404)
            body = live.current()
            if body is None:
                return self.send_error(503, "feed not written yet")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def page(self, body: bytes, kind: str):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            for name, value in PAGE_HEADERS.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def events(self):
            """Server-Sent Events: the document now, then on every change; a comment when quiet."""
            seq, body = live.wait(-1, 0)
            if body is None:
                return self.send_error(503, "feed not written yet")
            if not streams.acquire(blocking=False):
                return self.send_error(503, "too many streams")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    self.wfile.write(b"data: " + body + b"\n\n" if body is not None else b": keep-alive\n\n")
                    self.wfile.flush()
                    new, doc = live.wait(seq, KEEPALIVE)
                    body, seq = (doc if new != seq else None), new
            except OSError:  # the client went away
                pass
            finally:
                streams.release()

        def refuse(self):
            self.send_error(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = refuse

        def log_message(self, format, *args):  # the journal gets server errors only, not every poll
            pass

        def log_request(self, code="-", size="-"):
            if str(getattr(code, "value", code)).startswith("5"):
                print(f"status feed: {self.requestline} → {code}", file=sys.stderr)

    return Handler


def serve(addr: str, projects: list, path: Path = FEED_PATH, every: float = 2.0, token: str | None = None,
          page: bool = False) -> int:
    try:
        host, port = parse_addr(addr)
        token = check_token(token)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    live = Live(path, projects)
    live.tick(time.time())
    threading.Thread(target=live.run, args=(every,), daemon=True).start()
    with ThreadingHTTPServer((host, port), make_handler(live, token, web_files() if page else None)) as httpd:
        httpd.daemon_threads = True
        httpd.serve_forever()
    return 0

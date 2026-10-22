#!/usr/bin/env python3
"""The factory over its projects: provision the server, show the status of every project.

Projects of this server: one checkout path per line in $FLEET_PROJECTS (default
~/.config/dark-factory/projects; `#` comments). Without that file, the registry is used (registry.md,
column "Repository": the first `path` in backticks) — fine when the registry paths are this machine's.
A project gets, on the server where this runs (user systemd units, survive a reboot):
  - its development session: `claude remote-control --spawn worktree` started in the project's main checkout,
    inside its own tmux server — sessions opened from claude.ai each get their own git worktree;
  - its On-call session, if the project has the feedback-desk module (scripts/feedback-desk.sh), plus a timer
    that re-runs the idempotent `feedback-desk.sh up` every 5 minutes, so a crashed On-call comes back.
The prod-monitor watchdog lives in cron (prod-monitor.sh install) and needs nothing here.

Platform: Linux with a systemd user instance (`systemctl --user`) only. On macOS (or any machine without one)
nothing is provisioned: the sessions there are attended — started by hand and gone after a restart.

  scripts/fleet.py projects                 list projects found in the registry
  scripts/fleet.py provision [--dry-run]    write and enable the units, enable lingering
  scripts/fleet.py unprovision [--dry-run]  stop and remove the units
  scripts/fleet.py status                   read-only status of every project

Per-project settings (optional), <project>/.claude/factory/session.env:
  SESSION_NAME="Shop server"     name in ListAgents / claude.ai (default: "<dir name> server")
  SESSION_ARGS="--permission-mode auto"   extra arguments for `claude remote-control`, an allowlist:
      --permission-mode default|acceptEdits|plan|auto   and   --spawn same-dir|worktree|session (default worktree).
      Anything else (bypassPermissions, --dangerously-*, other flags) refuses to provision that project:
      the file is project-local and its value lands in a systemd ExecStart.

Options: --projects FILE, --registry PATH (default: $FACTORY_REGISTRY or ./registry.md), --project NAME.
Template drift is counted against $FACTORY_CANON (default: the checkout this script is in); the quota line comes
from its plugins/dark-factory/scripts/quota.py.
Attach to a development session: tmux -L df-<slug> attach.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# the canon checkout that .harness/base-sha commits refer to
FACTORY = Path(os.environ.get("FACTORY_CANON", Path(__file__).resolve().parent.parent))
UNIT_DIR = Path(os.environ.get("FLEET_UNIT_DIR", Path.home() / ".config/systemd/user"))
PREFIX = "df-"
WATCHDOG_STALE = 3 * 60  # a watchdog log entry older than this means the watchdog is silent
QUOTA_WARN = 80  # the guard stops new work from here
# What Claude Code shows when a session waits for a human: an expired login, or the workspace-trust question in a
# folder it has not trusted yet. Screen-scraping the last lines of the tmux pane is a BEST-EFFORT HINT, not a check:
# the wording changes between Claude Code versions, so a miss here proves nothing — attach and look.
LOGIN_RE = re.compile(
    r"please run /login|oauth token has expired|invalid api key|select login method|not logged in"
    r"|yes, i trust this folder|do you trust the files", re.I)

# SESSION_ARGS allowlist (see the module docstring). bypassPermissions / dontAsk / --dangerously-* are refused.
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto")
SPAWN_MODES = ("same-dir", "worktree", "session")
ALLOWED_ARGS = {"--permission-mode": PERMISSION_MODES, "--spawn": SPAWN_MODES}
DEFAULT_SPAWN = "worktree"


class SettingsError(ValueError):
    """A project's .claude/factory/session.env holds something fleet.py will not put into a unit."""


def parse_session_args(raw: str) -> list[str]:
    """SESSION_ARGS → arguments for `claude remote-control`, allowlisted; `--spawn worktree` unless set."""
    try:
        tokens = shlex.split(raw)
    except ValueError as e:
        raise SettingsError(f"SESSION_ARGS is not parseable: {e}") from None
    out: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        opt, sep, val = tokens[i].partition("=")
        if opt not in ALLOWED_ARGS:
            raise SettingsError(f"SESSION_ARGS: {tokens[i]!r} is not allowed "
                                f"(only --permission-mode {'|'.join(PERMISSION_MODES)} and --spawn {'|'.join(SPAWN_MODES)})")
        if not sep:  # "--opt value" rather than "--opt=value"
            i += 1
            val = tokens[i] if i < len(tokens) else ""
        if val not in ALLOWED_ARGS[opt]:
            raise SettingsError(f"SESSION_ARGS: {opt} {val!r} is not allowed (one of {', '.join(ALLOWED_ARGS[opt])})")
        if opt in out:
            raise SettingsError(f"SESSION_ARGS: {opt} given twice")
        out[opt] = val
        i += 1
    out.setdefault("--spawn", DEFAULT_SPAWN)
    return [x for kv in out.items() for x in kv]


def check_session_name(name: str) -> str:
    if not name.strip() or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise SettingsError(f"SESSION_NAME {name!r} is empty or has control characters")
    return name


def systemd_quote(text: str, expand_dollar: bool = True) -> str:
    """One double-quoted word for a unit file: escapes \\ and ", doubles % (specifiers) and, where systemd
    expands variables (Exec* lines), $."""
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return '"' + (text.replace("$", "$$") if expand_dollar else text) + '"'


@dataclass
class Project:
    name: str
    path: Path
    slug: str
    settings: dict = field(default_factory=dict)

    @property
    def session_name(self) -> str:
        return self.settings.get("SESSION_NAME") or f"{self.path.name} server"

    @property
    def session_args(self) -> list[str]:
        """Allowlisted; raises SettingsError on anything else."""
        return parse_session_args(self.settings.get("SESSION_ARGS", ""))

    @property
    def sock(self) -> str:
        return f"{PREFIX}{self.slug}"

    @property
    def desk(self) -> Path:
        return self.path / "scripts/feedback-desk.sh"

    @property
    def monitor(self) -> Path:
        return self.path / "scripts/ops/prod_monitor/prod-monitor.sh"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "project"


def read_env(path: Path) -> dict:
    """KEY=value lines (shell quoting allowed); no expansion."""
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if m and not line.lstrip().startswith("#"):
                vals = shlex.split(m.group(2), comments=True)
                val = vals[0] if vals else ""
                default = re.fullmatch(r"\$\{\w+:-(.*)\}", val)  # VAR="${VAR:-default}"
                out[m.group(1)] = default.group(1) if default else val
    return out


def parse_registry(text: str) -> list[tuple[str, str]]:
    """(project name, repository path) for every table row that has a path in the Repository column."""
    rows, header = [], None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells) or "repository" not in header:
            continue
        repo = cells[header.index("repository")] if len(cells) > header.index("repository") else ""
        m = re.search(r"`([~/][^`]*)`", repo)
        name = re.sub(r"[*_`]", "", cells[0]).strip()
        if m and not name.lower().startswith("example"):
            rows.append((name, m.group(1)))
    return rows


def parse_projects_file(text: str) -> list[tuple[str, str]]:
    paths = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
    return [(Path(p).name, p) for p in paths if p]


def load_projects(rows: list[tuple[str, str]], only: str | None = None) -> list[Project]:
    projects, seen = [], set()
    for name, raw in rows:
        path = Path(os.path.expanduser(raw)).resolve()
        slug = slugify(path.name)
        if slug in seen or (only and only not in (name, path.name, slug)):
            continue
        seen.add(slug)
        projects.append(Project(name, path, slug, read_env(path / ".claude/factory/session.env")))
    return projects


# ---------- provisioning ----------

def unit_path() -> str:
    # per-shell entries (/run/user/…) vanish after a reboot
    return ":".join(d for d in os.environ.get("PATH", "/usr/bin:/bin").split(":") if d and not d.startswith("/run/"))


def unit_head(p: Project) -> str:
    return f"""WorkingDirectory={str(p.path).replace("%", "%%")}
Environment={systemd_quote("PATH=" + unit_path(), expand_dollar=False)}"""


def session_unit(p: Project, claude: str, tmux: str) -> str:
    # Two quoting layers: shlex for the shell tmux runs the command in, systemd_quote for the unit file
    # (systemd expands % specifiers and $VARS even inside quotes — a name like "50% $x" must stay literal).
    cmd = shlex.join([claude, "remote-control", "--name", check_session_name(p.session_name), *p.session_args])
    tmux_q = systemd_quote(tmux)
    # Restart=always brings the session back after a crash or an update; the start limit stops the loop when
    # it cannot start at all (expired login, untrusted folder): 5 starts in 30 minutes, then the unit stays failed
    # until `systemctl --user reset-failed` — fleet.py status shows it.
    return f"""[Unit]
Description=dark factory: development session of {p.name}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=30min
StartLimitBurst=5

[Service]
Type=forking
{unit_head(p)}
ExecStart={tmux_q} -L {p.sock} new-session -d -s session -c {systemd_quote(str(p.path))} {systemd_quote(cmd)}
ExecStop={tmux_q} -L {p.sock} kill-server
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""


def desk_unit(p: Project) -> str:
    # oneshot: feedback-desk.sh starts its own tmux session and returns; KillMode=process keeps the
    # shared tmux server alive when the unit stops (feedback-desk.sh down stops the session itself).
    return f"""[Unit]
Description=dark factory: On-call session of {p.name}
After=network-online.target {p.sock}-session.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
KillMode=process
{unit_head(p)}
ExecStart={systemd_quote(str(p.desk))} up
ExecStop={systemd_quote(str(p.desk))} down

[Install]
WantedBy=default.target
"""


# The desk unit above is oneshot + RemainAfterExit: it stays "active" after the On-call session dies, so systemd
# never restarts it. The watch timer re-runs `feedback-desk.sh up` (a no-op while the session is up) every 5 minutes.
WATCH_EVERY = "5min"


def desk_watch_service(p: Project) -> str:
    return f"""[Unit]
Description=dark factory: bring the On-call session of {p.name} back if it died

[Service]
Type=oneshot
KillMode=process
{unit_head(p)}
ExecStart={systemd_quote(str(p.desk))} up
"""


def desk_watch_timer(p: Project) -> str:
    return f"""[Unit]
Description=dark factory: On-call watch of {p.name} every {WATCH_EVERY}

[Timer]
OnBootSec={WATCH_EVERY}
OnUnitActiveSec={WATCH_EVERY}
Unit={p.sock}-desk-watch.service

[Install]
WantedBy=timers.target
"""


UNIT_SUFFIXES = ("-session.service", "-desk.service", "-desk-watch.service", "-desk-watch.timer")


def units_for(p: Project, claude: str, tmux: str) -> dict[str, str]:
    """Unit name → text. Raises SettingsError when the project's session.env is refused."""
    units = {f"{p.sock}-session.service": session_unit(p, claude, tmux)}
    if p.desk.is_file():
        units[f"{p.sock}-desk.service"] = desk_unit(p)
        units[f"{p.sock}-desk-watch.service"] = desk_watch_service(p)
        units[f"{p.sock}-desk-watch.timer"] = desk_watch_timer(p)
    return units


def platform_ok() -> bool:
    return sys.platform.startswith("linux") and bool(shutil.which("systemctl"))


def run(cmd: list[str], dry: bool) -> int:
    print(("would run: " if dry else "$ ") + shlex.join(cmd))
    return 0 if dry else subprocess.call(cmd)


def provision(projects: list[Project], dry: bool) -> int:
    if not platform_ok():
        print("✗ provisioning needs Linux with a systemd user instance (systemctl --user). On macOS the sessions "
              "are attended: start `claude remote-control` and `scripts/feedback-desk.sh up` by hand.", file=sys.stderr)
        return 1
    claude, tmux = shutil.which("claude"), shutil.which("tmux")
    if not (claude and tmux):
        print("✗ need claude and tmux in PATH", file=sys.stderr)
        return 1
    names, refused = [], 0
    for p in projects:
        if not p.path.is_dir():
            print(f"✗ {p.name}: {p.path} does not exist — skipped", file=sys.stderr)
            continue
        try:
            units = units_for(p, claude, tmux)
        except SettingsError as e:
            print(f"✗ {p.name}: not provisioned — {e} (fix {p.path}/.claude/factory/session.env)", file=sys.stderr)
            refused += 1
            continue
        for unit, text in units.items():
            target = UNIT_DIR / unit
            print(f"{'would write' if dry else 'write'} {target}")
            if not dry:
                UNIT_DIR.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            if "[Install]" in text:  # the watch service is started by its timer, not enabled
                names.append(unit)
    if not names:
        return 1
    bad = refused
    bad |= run(["systemctl", "--user", "daemon-reload"], dry)
    bad |= run(["systemctl", "--user", "enable", "--now", *names], dry)
    # without lingering, user units start only after the owner logs in — not after a reboot
    if run(["loginctl", "enable-linger", os.environ.get("USER", "")], dry):
        print(f"✗ lingering not enabled; run: sudo loginctl enable-linger {os.environ.get('USER', '')}")
        bad = 1
    return 1 if bad else 0


def unprovision(projects: list[Project], dry: bool) -> int:
    # exact names, not a glob: df-shop-* would also match the units of a project slugged shop-x
    names = [f"{p.sock}{s}" for p in projects for s in UNIT_SUFFIXES if (UNIT_DIR / f"{p.sock}{s}").exists()]
    if not names:
        print("no units installed")
        return 0
    bad = run(["systemctl", "--user", "disable", "--now", *names], dry)
    for n in names:
        print(f"{'would remove' if dry else 'remove'} {UNIT_DIR / n}")
        if not dry:
            (UNIT_DIR / n).unlink()
    return bad | run(["systemctl", "--user", "daemon-reload"], dry)


# ---------- status ----------

def sh(cmd: list[str], cwd: Path | None = None, timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def last(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else "no output"


def check_session(p: Project) -> tuple[bool, str]:
    unit = f"{PREFIX}{p.slug}-session.service"
    if not (UNIT_DIR / unit).exists():
        return False, "not provisioned (scripts/fleet.py provision)"
    code, out = sh(["systemctl", "--user", "is-active", unit])
    attach = f"tmux -L {p.sock} attach"
    if code == 0:
        _, screen = sh(["tmux", "-L", p.sock, "capture-pane", "-p", "-t", "session"])
        if LOGIN_RE.search("\n".join(screen.splitlines()[-15:])):
            return False, f"active but waiting at a login or folder-trust prompt — {attach} and answer it"
    elif out.strip() == "failed":
        out += f" (start limit? journalctl --user -u {unit}; then systemctl --user reset-failed {unit})"
    return code == 0, f'{out} — "{p.session_name}", {attach}'


def check_desk(p: Project) -> tuple[bool, str] | None:
    if not p.desk.is_file():
        return None
    code, out = sh([str(p.desk), "status"], cwd=p.path)
    if code != 0:
        return False, last(out)
    tmux_name = read_env(p.path / ".claude/feedback-desk/config.env").get("DESK_TMUX", "")
    if tmux_name and not tmux_name.startswith("$"):
        _, screen = sh(["tmux", "capture-pane", "-p", "-t", tmux_name])
        if LOGIN_RE.search("\n".join(screen.splitlines()[-15:])):
            return False, "running but asks to log in — attach and run /login"
    return True, last(out)


def check_monitor(p: Project, now: float) -> tuple[bool, str] | None:
    if not p.monitor.is_file():
        return None
    code, out = sh([str(p.monitor), "status"], cwd=p.path)
    failed = [ln.strip() for ln in out.splitlines() if "✗" in ln]
    stamps = re.findall(r"^\s*(\d{4}-\d\d-\d\dT\S+)", out, re.M)
    if stamps:
        try:
            age = now - datetime.fromisoformat(stamps[-1]).timestamp()
        except ValueError:
            age = 0
        if age > WATCHDOG_STALE:
            failed.append(f"watchdog silent for {int(age // 60)} min")
    return (code == 0 and not failed), ("; ".join(failed) if failed else "watchdog and channel fine")


def check_queue(p: Project) -> tuple[bool, str] | None:
    if not (p.path / ".beads").is_dir() or not shutil.which("bd"):
        return None
    try:
        r = subprocess.run(["bd", "ready", "--json"], cwd=p.path, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, f"ready: {len(json.loads(r.stdout or '[]'))}"
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return False, f"bd ready failed: {e}"


def check_drift(p: Project) -> tuple[bool, str] | None:
    sha_file = p.path / ".harness/base-sha"
    if not sha_file.is_file():
        return None
    sha = sha_file.read_text().strip()
    code, out = sh(["git", "-C", str(FACTORY), "rev-list", "--count", f"{sha}..HEAD", "--", "templates/"])
    if code != 0:
        return False, f"template commit {sha[:8]} not found in the factory repo"
    n = int(out or 0)
    return n == 0, "on the current template" if n == 0 else f"{n} template commits behind (harness-diff.sh)"


def check_quota() -> tuple[bool, str] | None:
    """The account's quota (shared by every project) from the dark-factory plugin in the canon checkout."""
    q = FACTORY / "plugins/dark-factory/scripts/quota.py"
    if not q.is_file():
        return None
    code, out = sh([sys.executable, str(q), "status"], cwd=FACTORY, timeout=60)
    pct = [int(x) for x in re.findall(r"(\d+)%", last(out))]
    return code == 0 and max(pct, default=0) < QUOTA_WARN, last(out)


def status(projects: list[Project]) -> int:
    now = time.time()
    print(f"Factory status · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}\n")
    bad = 0

    def line(label: str, res: tuple[bool, str] | None) -> None:
        nonlocal bad
        if res is None:
            return
        ok, text = res
        bad += not ok
        print(f"  {'●' if ok else '○'} {label} — {text}")

    q = check_quota()
    if q:
        print(f"{'●' if q[0] else '○'} subscription quota — {q[1]}\n")
        bad += not q[0]
    for p in projects:
        print(f"{p.name} ({p.path})")
        if not p.path.is_dir():
            line("checkout", (False, "missing"))
            continue
        line("development session", check_session(p))
        line("On-call", check_desk(p))
        line("prod monitor", check_monitor(p, now))
        line("queue", check_queue(p))
        line("template", check_drift(p))
        print()
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["projects", "provision", "unprovision", "status"])
    ap.add_argument("--projects", type=Path, default=Path(os.environ.get(
        "FLEET_PROJECTS", Path.home() / ".config/dark-factory/projects")))
    ap.add_argument("--registry", type=Path,
                    default=Path(os.environ.get("FACTORY_REGISTRY", "registry.md")))
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.projects.is_file():
        rows = parse_projects_file(a.projects.read_text())
    elif a.registry.is_file():
        rows = parse_registry(a.registry.read_text())
    else:
        print(f"✗ neither {a.projects} nor {a.registry} exists", file=sys.stderr)
        return 2
    projects = load_projects(rows, a.project)
    if not projects:
        print("✗ no projects found", file=sys.stderr)
        return 2
    if a.command == "projects":
        for p in projects:
            print(f"{p.slug}\t{p.path}\t{p.session_name}")
        return 0
    if a.command == "provision":
        return provision(projects, a.dry_run)
    if a.command == "unprovision":
        return unprovision(projects, a.dry_run)
    return status(projects)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

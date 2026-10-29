#!/usr/bin/env python3
"""The project's level on the dark-factory ladder (docs/levels.md): the mechanics behind /dark-factory:level.

Levels: 0 solo kit, 1 base template, 2 provisioned server, 3 client modules, 4 team. A level is read from
evidence in the project, never stored:
  0  .claude/fences.env exists (the project opted in; /dark-factory:init or base wrote it)
  1  + the base template: .copier-answers.yml (Copier wrote it, wherever the project keeps its files), or
     openspec/ and CODING_STANDARDS.md at the root
  2  + a server: .claude/factory/session.env, or the project listed in ~/.config/dark-factory/projects
     ($FLEET_PROJECTS), the file fleet.py provisions from
  3  + a client module: On-call (feedback-desk: scripts/feedback-desk.sh, .claude/feedback-desk/config.env),
     the production monitor (prod-monitor: scripts/ops/prod_monitor/) or observability (docs/deploy/monitoring*.md).
     Releases by tag (release-tag) are part of base when the project has production: listed, not a level
  4  level 1 + FENCE_LEVEL=team (a server is optional). Levels 2, 3 and 4 are independent steps above 1: a team
     without a personal server or a client reads as 4.
The fence level (FENCE_LEVEL) each level runs at: 0 solo, 1-3 standard, 4 team; level 2 adds QUOTA_FAIL_CLOSED=1.
The fence level read is the effective one (guard.effective_fences): the stricter of the working tree's
.claude/fences.env and the same file on origin's main branch, so lowering it takes a change merged into main.

Signals that it is time for the next level (cheap: files, at most one `git log` of the last 300 commits and one
bounded count of the execution queue):
  -> 1  the history spans 30 days or more; ten or more merge commits among the last 300 commits
  -> 2  ten or more open tasks in the execution queue (bd count); this machine already runs the factory for
        other projects (the projects file exists and does not list this one)
  -> 3  a production deploy configuration (Dockerfile, fly.toml, render.yaml, Procfile, a deploy workflow…)
  -> 4  two or more people authored the last 300 commits (bots excluded)

  level.py [status] [--json]                  the level, the evidence, the gaps, the next level's signals
  level.py set LEVEL [--fail-closed 0|1] [--apply]
                                              change FENCE_LEVEL (solo|standard|team), up or down; dry run
                                              without --apply. --apply needs the grant recorded by the human's
                                              own `/dark-factory:level LEVEL [--fail-closed 0|1]` prompt: bound
                                              to exactly that change, 10 minutes, used once. Nothing else —
                                              not a terminal, not a flag — writes the level
  level.py hint                               SessionStart hook: at most one line, only when a next-level
                                              signal is present; once a day per project unless it changes
  level.py prompt-hook                        UserPromptSubmit hook: records the grant when the human's
                                              prompt is /dark-factory:level with a target level; a bare
                                              /dark-factory:level is a read-only report; prints nothing

The project: --project, else $CLAUDE_PROJECT_DIR, else the git top level of the cwd, else the cwd.
Nothing here runs a structural step (add, provision-server): it names it.
stdlib only, Python 3.11+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard  # noqa: E402  (fences.env parsing and the level order are shared)

FENCES_FILE = guard.FENCES_FILE
LEVELS = guard.LEVELS
NAMES = {0: "solo kit", 1: "base template", 2: "provisioned server", 3: "client modules", 4: "team"}
EXPECTED_FENCE = {0: "solo", 1: "standard", 2: "standard", 3: "standard", 4: "team"}
BASE_MARKERS = ("openspec/", "CODING_STANDARDS.md")
COPIER_ANSWERS = ".copier-answers.yml"  # the base template installed by Copier: enough on its own
MODULES = {
    "feedback-desk": ("scripts/feedback-desk.sh", ".claude/feedback-desk/config.env"),
    "prod-monitor": ("scripts/ops/prod_monitor/",),
    "release-tag": ("scripts/release.sh",),
    "observability": ("docs/deploy/monitoring.md", "docs/deploy/monitoring-alerts.md"),
    "feature-pipeline": (".claude/factory/feature-pipeline.json", ".claude/feature-pipeline.json"),
}
CLIENT_MODULES = ("feedback-desk", "prod-monitor", "observability")
DEPLOY_MARKERS = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml", "fly.toml",
                  "render.yaml", "railway.json", "railway.toml", "vercel.json", "netlify.toml", "Procfile", "app.yaml",
                  "app.json")
HISTORY_COMMITS = 300
HISTORY_DAYS = 30
MERGES = 10
QUEUE_OPEN = 10
GRANT_TTL = 600
HINT_EVERY = 20 * 3600
READ_CAP = 4 * 1024 * 1024
LEVEL_PROMPT = re.compile(r"^/(?:dark-factory:)?level(?:\s+(.*))?$", re.S)
COMMAND_TAG = re.compile(r"^<command-(?:message|name)>/?(?:dark-factory:)?level</command-(?:message|name)>")
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)

# What each step adds, and how it is taken. Fence steps are written by `set`; structural ones are named only.
STEPS = {
    1: ("the full base template: OpenSpec changes, the bd queue, the checked test pyramid, CI tiers, the PR "
        "description as the record of work; the guard at standard",
        "structural: `/dark-factory:add base` in the project (conversion mode for a project with code); it lists "
        "the files in a dry run first, asks whether there is a production deploy (then releases by tag come with "
        "it) and writes FENCE_LEVEL=standard; from level 0 it keeps the solo fences.env and pre-push, so then type "
        "`/dark-factory:level standard`. This command does not deploy."),
    2: ("the development session on a server, back after every reboot; the feature pipeline; runs booked for "
        "later; QUOTA_FAIL_CLOSED=1",
        "structural: `/dark-factory:provision-server` on the server (fleet.py provision). Then "
        "`/dark-factory:level <current level> --fail-closed 1`, typed by you, writes QUOTA_FAIL_CLOSED=1."),
    3: ("On-call in the client chat, the production monitor, observability",
        "structural: one module at a time: `/dark-factory:add on-call`, `/dark-factory:add monitor`, "
        "`/dark-factory:add observability` (each starts with the steps only you can do)."),
    4: ("the guard at team: a GitHub approval before every merge, no merge without CI (--skip-ci refused); branch "
        "protection on the main branch; the board with claims; the roles held by different people",
        "fence: `/dark-factory:level team`, typed by you, writes FENCE_LEVEL=team. Branch protection is a GitHub "
        "setting (a pull request with 1 approval, no force pushes, no admin bypass) that you set yourself: the "
        "guard denies branch-protection changes to the agent."),
}
FENCE_MEANS = {
    "solo": "the guard denies only destructive things (force push, push to main, hook bypass, release tags, "
            "deleting or resetting main) and asks the human before a change to the fences themselves; "
            "--skip-ci allowed",
    "standard": "solo + `gh pr merge` only through merge-feature.sh, no approvals by the agent, the fence files "
                "edited only with the human's yes",
    "team": "standard + a GitHub approval before every merge; --skip-ci refused",
}


# --- where things are ---------------------------------------------------------


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def project_dir(arg: str | None = None, cwd: str | None = None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(os.environ["CLAUDE_PROJECT_DIR"]).resolve()
    here = Path(cwd or os.getcwd())
    top = _git(["rev-parse", "--show-toplevel"], here) if here.is_dir() else None
    return Path(top).resolve() if top else here.resolve()


def _home() -> Path:
    """The real home directory from the password database: $HOME cannot re-point the grant store."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return Path.home()


STATE = _home() / guard.STATE_DIR


def _key(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]


def projects_file() -> Path:
    return Path(os.environ.get("FLEET_PROJECTS") or Path.home() / ".config/dark-factory/projects").expanduser()


def _read(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return f.read(READ_CAP)
    except OSError:
        return ""


# --- evidence -----------------------------------------------------------------


def _exists(root: Path, rel: str) -> bool:
    path = root / rel.rstrip("/")
    return path.is_dir() if rel.endswith("/") else path.exists()


def listed_on_server(root: Path) -> bool | None:
    """True/False: the projects file lists / does not list this project; None: there is no projects file."""
    path = projects_file()
    if not path.is_file():
        return None
    for line in _read(path).splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry and Path(os.path.expanduser(entry)).resolve() == root.resolve():
            return True
    return False


def history(root: Path) -> tuple[float, set[str], int]:
    """Days spanned by the last HISTORY_COMMITS commits, their human author emails and how many of them are
    merge commits (one bounded git log)."""
    out = _git(["log", f"-n{HISTORY_COMMITS}", "--format=%ct %ae %P"], root)
    if not out:
        return 0.0, set(), 0
    stamps, authors, merges = [], set(), 0
    for line in out.splitlines():
        ts, email, *parents = line.split(" ")
        if ts.isdigit():
            stamps.append(int(ts))
        email = email.strip().lower()
        if email and "[bot]" not in email and email not in ("noreply@github.com", "noreply@anthropic.com"):
            authors.add(email)
        if len([p for p in parents if p]) >= 2:
            merges += 1
    span = (max(stamps) - min(stamps)) / 86400 if stamps else 0.0
    return span, authors, merges


def queue_counts(root: Path) -> dict[str, int]:
    """Task counts by status from the execution queue. Seam: docs/functions.md "Feature execution queue"
    (count); implementation — the project's local bd store, found by bd from any worktree. No bd, no store,
    a slow or failing call — an empty dict."""
    try:
        proc = subprocess.run(["bd", "count", "--by-status", "--json"], cwd=root, capture_output=True, text=True,
                              timeout=10, check=False)
        data = json.loads(proc.stdout) if proc.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return {}
    return {str(g.get("group")): int(g.get("count") or 0) for g in groups if isinstance(g, dict)}


def open_tasks(root: Path) -> int:
    counts = queue_counts(root)
    return counts.get("open", 0) + counts.get("in_progress", 0)


def deploy_config(root: Path) -> list[str]:
    found = [m for m in DEPLOY_MARKERS if (root / m).is_file()]
    workflows = root / ".github/workflows"
    if workflows.is_dir():
        found += [f".github/workflows/{p.name}" for p in sorted(workflows.glob("*.y*ml")) if "deploy" in p.name.lower()]
    return found


def detect(root: Path, with_git: bool = True) -> dict:
    """Everything /dark-factory:level reports, as plain data."""
    fences_path = root / FENCES_FILE
    opted = fences_path.is_file()
    values = guard.parse_fences(_read(fences_path)) if opted else {}
    floor = guard.fences_floor(str(root)) if with_git else {}
    opted = opted or bool(floor)
    working = (values.get("FENCE_LEVEL") or guard.DEFAULT_LEVEL) if fences_path.is_file() else None
    effective = guard.effective_fences(str(root), floor) if opted else {}
    # an unknown working value is reported as is (a gap); otherwise the effective, floor-raised level
    fence = working if working is not None and working not in LEVELS else effective.get("FENCE_LEVEL")
    fail_closed = effective.get("QUOTA_FAIL_CLOSED") == "1"
    base = {m: _exists(root, m) for m in (COPIER_ANSWERS, *BASE_MARKERS)}
    has_base = base[COPIER_ANSWERS] or all(base[m] for m in BASE_MARKERS)
    listed = listed_on_server(root)
    server = []
    if (root / ".claude/factory/session.env").is_file():
        server.append(".claude/factory/session.env")
    if listed:
        server.append(f"listed in {projects_file()}")
    modules = {name: any(_exists(root, rel) for rel in rels) for name, rels in MODULES.items()}

    level = None
    if opted:
        level = 0
        if has_base:
            level = 1
            if server:
                level = 2
    client = level is not None and level >= 2 and any(modules[m] for m in CLIENT_MODULES)
    team = level is not None and level >= 1 and fence == "team"
    reached = [lv for lv in range(level + 1)] if level is not None else []
    if client:
        reached.append(3)
    if team:
        reached.append(4)
    current = max(reached) if reached else None

    gaps, notes = [], []
    if opted:
        if fence not in LEVELS:
            gaps.append(f"FENCE_LEVEL={fence!r} is not a level; the guard reads it as '{guard.DEFAULT_LEVEL}'")
        else:
            want = EXPECTED_FENCE[current]
            if guard.LEVEL_RANK[fence] < guard.LEVEL_RANK[want]:
                gaps.append(f"the fence is '{fence}', level {current} runs at '{want}': "
                            f"/dark-factory:level {want}, typed by you, writes it")
        if level is not None and level >= 2 and not fail_closed:
            gaps.append("QUOTA_FAIL_CLOSED is not 1: unattended sessions should treat no quota data as no new work")
        missing = [m for m in BASE_MARKERS if not base[m]]
        if level == 0 and len(missing) < len(BASE_MARKERS):
            notes.append(f"part of the base template is present; missing: {', '.join(missing)}")
        if level is not None and level < 2 and server:
            notes.append(f"server evidence ({server[0]}) without the base template below it")
        if level is not None and level < 2 and any(modules[m] for m in CLIENT_MODULES):
            notes.append("a client module is present, but level 2 (the server) is not reached")
        if fence == "team" and not team:
            notes.append("the fence is already 'team', but level 1 (the base template) is not reached")
        if floor and working in LEVELS and guard.LEVEL_RANK[floor["FENCE_LEVEL"]] > guard.LEVEL_RANK[working]:
            notes.append(f"the working tree says FENCE_LEVEL={working}, origin's main branch says "
                         f"{floor['FENCE_LEVEL']}: the guard keeps {floor['FENCE_LEVEL']} until the lower level is "
                         "merged into the main branch")

    signals: dict[int, list[str]] = {}
    if opted:
        targets = next_levels(reached)
        span, authors, merges = history(root) if with_git and (1 in targets or 4 in targets) else (0.0, set(), 0)
        if 1 in targets:
            s = []
            if span >= HISTORY_DAYS:
                s.append(f"the history spans {int(span)} days")
            if merges >= MERGES:
                s.append(f"{merges} merge commits among the last {HISTORY_COMMITS} commits")
            signals[1] = s
        if 2 in targets:
            s = []
            if (n := open_tasks(root)) >= QUEUE_OPEN:
                s.append(f"{n} open tasks in the execution queue")
            if listed is False:
                s.append(f"this machine already runs the factory for other projects ({projects_file()})")
            signals[2] = s
        if 3 in targets:
            s = []
            if found := deploy_config(root):
                s.append(f"a production deploy configuration ({', '.join(found[:3])})")
            signals[3] = s
        if 4 in targets:
            signals[4] = [f"{len(authors)} people authored the last {HISTORY_COMMITS} commits"] if len(authors) >= 2 else []

    return {
        "project": str(root),
        "opted_in": opted,
        "level": current,
        "reached": reached,
        "fence": fence,
        "quota_fail_closed": fail_closed,
        "fence_working": working,
        "fence_main": floor.get("FENCE_LEVEL") if floor else None,
        "evidence": {
            "fences.env": f"FENCE_LEVEL={fence}" if opted else "missing",
            "base": base,
            "server": server,
            "modules": modules,
        },
        "gaps": gaps,
        "notes": notes,
        "next": {str(k): {"adds": STEPS[k][0], "how": STEPS[k][1], "signals": v} for k, v in signals.items()},
    }


def next_levels(reached: list[int]) -> list[int]:
    """The levels one step up: 3 and 4 both follow 2 and do not need each other."""
    if not reached:
        return []
    top = max(lv for lv in reached if lv <= 2)
    if top < 2:
        return [top + 1]
    return [lv for lv in (3, 4) if lv not in reached]


# --- report ------------------------------------------------------------------


def report(info: dict) -> str:
    if not info["opted_in"]:
        return (f"Project: {info['project']}\n"
                "Not on the ladder yet: no .claude/fences.env, so the plugin's guards are off here.\n"
                "Level 0 (solo kit) is /dark-factory:init: the operating contract, merge-feature.sh, a pre-push "
                "test gate and .claude/fences.env at 'solo'.")
    ev = info["evidence"]
    lines = [f"Project: {info['project']}"]
    extra = " + 3 (client modules)" if 3 in info["reached"] and info["level"] == 4 else ""
    lines.append(f"Level {info['level']}: {NAMES[info['level']]}{extra}")
    lines.append("Evidence:")
    lines.append(f"  fences.env      FENCE_LEVEL={info['fence']}, QUOTA_FAIL_CLOSED={'1' if info['quota_fail_closed'] else '0'}"
                 f" (working tree {info['fence_working'] or 'missing'}, origin's main branch "
                 f"{info['fence_main'] or 'no file'}; the stricter binds)")
    lines.append("  base template   " + ", ".join(f"{m} {'yes' if ok else 'no'}" for m, ok in ev["base"].items()))
    lines.append("  server          " + (", ".join(ev["server"]) or "no"))
    lines.append("  modules         " + ", ".join(f"{m} {'yes' if ok else 'no'}" for m, ok in ev["modules"].items()))
    for title, items in (("Gaps at this level", info["gaps"]), ("Notes", info["notes"])):
        if items:
            lines.append(f"{title}:")
            lines.extend(f"  - {i}" for i in items)
    if not info["next"]:
        lines.append("Next: nothing above this level.")
    for lv, step in info["next"].items():
        lines.append(f"Next: level {lv} ({NAMES[int(lv)]})")
        lines.append(f"  adds:    {step['adds']}")
        lines.append(f"  how:     {step['how']}")
        lines.append("  signals: " + ("; ".join(step["signals"]) if step["signals"] else
                                       "none seen in the project (the human may know better)"))
    lines.append("Fence change: /dark-factory:level <solo|standard|team> [--fail-closed 0|1], typed by you, moves "
                 "FENCE_LEVEL either way on your yes; a lower level takes effect once it is merged into the main branch.")
    return "\n".join(lines)


# --- changing the fence level -------------------------------------------------


def set_value(text: str, key: str, value: str) -> str:
    """Every active KEY= line set to value; appended when there is none. Comments are kept."""
    pattern = re.compile(rf"^(\s*){key}\s*=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}{key}={value}", text)
    return text + ("" if not text or text.endswith("\n") else "\n") + f"{key}={value}\n"


def grant_path(root: Path) -> Path:
    return STATE / "level-grants" / f"{_key(root)}.json"


def grant_ok(root: Path, level: str, fail_closed: str | None, now: float | None = None) -> bool:
    """A grant for exactly this change: this project, this level, this --fail-closed value, not expired."""
    try:
        data = json.loads(grant_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    now = time.time() if now is None else now
    return (isinstance(data, dict) and data.get("project") == str(root.resolve())
            and data.get("level") == level and data.get("fail_closed") == fail_closed
            and isinstance(data.get("at"), (int, float)) and 0 <= now - data["at"] <= GRANT_TTL)


def is_level_prompt(prompt: str) -> bool:
    """The human's own /dark-factory:level (as typed, or as Claude Code expands a slash command). A prompt
    that only mentions it, or a message relayed from a channel or another session, does not count."""
    text = prompt.lstrip()
    return bool(LEVEL_PROMPT.match(text) or COMMAND_TAG.match(text))


def level_request(prompt: str) -> tuple[str, str | None] | None:
    """(level, fail_closed) when the human's own /dark-factory:level names a change exactly:
    `<level>`, `<level> --fail-closed 0|1` or `<level> --fail-closed=0|1`. Anything else — no target,
    extra words, another line — is a read-only report and grants nothing."""
    text = prompt.strip()
    if m := LEVEL_PROMPT.match(text):
        args = m.group(1) or ""
    elif COMMAND_TAG.match(text):
        tags = COMMAND_ARGS.search(text)
        args = tags.group(1) if tags else ""
    else:
        return None
    words = args.replace("--fail-closed=", "--fail-closed ").split()
    if not words or words[0] not in LEVELS:
        return None
    if len(words) == 1:
        return words[0], None
    if len(words) == 3 and words[1] == "--fail-closed" and words[2] in ("0", "1"):
        return words[0], words[2]
    return None


def change_fences(root: Path, level: str, fail_closed: str | None, apply: bool) -> int:
    path = root / FENCES_FILE
    if not path.is_file():
        print(f"No {FENCES_FILE} in {root}: the project is not opted in. Level 0 is /dark-factory:init.")
        return 2
    old = path.read_text(encoding="utf-8")
    values = guard.parse_fences(old)
    old_level = values.get("FENCE_LEVEL") or guard.DEFAULT_LEVEL
    new = set_value(old, "FENCE_LEVEL", level)
    if fail_closed is not None:
        new = set_value(new, "QUOTA_FAIL_CLOSED", fail_closed)
    if new == old:
        print(f"Nothing to change: FENCE_LEVEL={old_level}"
              + (f", QUOTA_FAIL_CLOSED={fail_closed}" if fail_closed is not None else "") + ".")
        return 0
    direction = ("up" if guard.LEVEL_RANK[level] > guard.LEVEL_RANK.get(old_level, 1)
                 else "down" if guard.LEVEL_RANK[level] < guard.LEVEL_RANK.get(old_level, 1) else "same")
    print(f"{FENCES_FILE}: FENCE_LEVEL {old_level} -> {level} ({direction})")
    if fail_closed is not None:
        print(f"{FENCES_FILE}: QUOTA_FAIL_CLOSED {values.get('QUOTA_FAIL_CLOSED', '0') or '0'} -> {fail_closed}")
    print(f"  {level}: {FENCE_MEANS[level]}")
    if direction == "down":
        print(f"  Moving down drops: {FENCE_MEANS[old_level] if old_level in FENCE_MEANS else old_level}")
    if level == "team":
        print("  Also recommended: GitHub branch protection on the main branch (a pull request with 1 approval, "
              "no force pushes, no admin bypass): a GitHub setting the human makes (the guard denies it to the agent).")
    if not apply:
        print("Dry run: nothing written. Add --apply after the human's yes.")
        return 0
    if not grant_ok(root, level, fail_closed):
        print("Refused: this change needs the human's own /dark-factory:level prompt naming exactly it (the "
              f"level{' and --fail-closed' if fail_closed is not None else ''}), typed in this project in the last "
              f"{GRANT_TTL // 60} minutes; it is used once. Ask the human — there is no other way to write the level.")
        return 3
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fences.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new)
    os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)
    try:
        grant_path(root).unlink()
    except OSError:
        pass
    print(f"Written. Commit {FENCES_FILE} like any change (a branch and merge-feature.sh, or the human pushes it).")
    floor = guard.fences_floor(str(root))
    if floor and guard.LEVEL_RANK[floor["FENCE_LEVEL"]] > guard.LEVEL_RANK[level]:
        print(f"Note: origin's main branch says FENCE_LEVEL={floor['FENCE_LEVEL']}; the guard keeps that level until "
              "this change is merged into the main branch (at team: after a reviewer's approval).")
    elif floor.get("QUOTA_FAIL_CLOSED") == "1" and fail_closed == "0":
        print("Note: origin's main branch says QUOTA_FAIL_CLOSED=1; it stays 1 until this change is merged.")
    return 0


# --- hooks ---------------------------------------------------------------------


def prompt_hook(hook: dict) -> int:
    request = level_request(str(hook.get("prompt") or ""))
    if request is None:
        return 0
    root = project_dir(None, hook.get("cwd"))
    if not (root / FENCES_FILE).is_file():
        return 0
    path = grant_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"project": str(root.resolve()), "at": time.time(), "level": request[0],
                                    "fail_closed": request[1]}), encoding="utf-8")
    except OSError as exc:
        print(f"level: could not record the grant ({exc})", file=sys.stderr)
    return 0


def hint_line(info: dict) -> str | None:
    if not info["opted_in"] or info["level"] is None:
        return None
    seen = [(lv, s) for lv, step in info["next"].items() for s in step["signals"]]
    if not seen:
        return None
    lv, first = seen[0]
    more = f" (+{len(seen) - 1} more)" if len(seen) > 1 else ""
    return (f"dark-factory: this project is at level {info['level']} ({NAMES[info['level']]}); a signal for level "
            f"{lv} ({NAMES[int(lv)]}): {first}{more}. Mention it to the human once; /dark-factory:level, which they "
            "run, shows what would change.")


def hint(hook: dict, now: float | None = None) -> int:
    if os.environ.get("DARK_FACTORY_LEVEL_HINT") == "off":
        return 0
    root = project_dir(None, hook.get("cwd"))
    if not (root / FENCES_FILE).is_file():
        return 0  # not opted in: quota.py already prints the one /dark-factory:init line
    line = hint_line(detect(root))
    if not line:
        return 0
    now = time.time() if now is None else now
    stamp = STATE / "hints" / f"{_key(root)}.json"
    digest = hashlib.sha256(line.encode()).hexdigest()[:16]
    try:
        last = json.loads(stamp.read_text(encoding="utf-8"))
        if last.get("digest") == digest and now - last.get("at", 0) < HINT_EVERY:
            return 0
    except (OSError, ValueError, AttributeError):
        pass
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(json.dumps({"digest": digest, "at": now}), encoding="utf-8")
    except OSError:
        pass
    print(line)
    return 0


# --- entry point ----------------------------------------------------------------


def main(argv: list[str]) -> int:
    if argv[:1] in (["hint"], ["prompt-hook"]):
        try:
            hook = json.load(sys.stdin)
        except ValueError:
            hook = {}
        hook = hook if isinstance(hook, dict) else {}
        try:
            return hint(hook) if argv[0] == "hint" else prompt_hook(hook)
        except Exception as exc:  # a hook must never break the session
            print(f"level: {argv[0]} failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            return 0
    ap = argparse.ArgumentParser(prog="level.py", description="The project's level on the dark-factory ladder.")
    ap.add_argument("command", nargs="?", default="status", choices=["status", "set"])
    ap.add_argument("level", nargs="?", choices=LEVELS)
    ap.add_argument("--project")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-closed", choices=["0", "1"])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    root = project_dir(a.project)
    if a.command == "set":
        if not a.level:
            ap.error("set needs a level: solo, standard or team")
        return change_fences(root, a.level, a.fail_closed, a.apply)
    info = detect(root)
    print(json.dumps(info, indent=2) if a.json else report(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

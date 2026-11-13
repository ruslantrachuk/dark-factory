#!/usr/bin/env python3
"""Move a project from the v23 rules layout to v24 (agents-md-core): one canon for Claude Code and Codex.

v23: CLAUDE.md imports the canon with @.claude/canon/CLAUDE.md; skills in .claude/skills/; the session header in
.claude/hooks/{env-context,session-context}.sh, called from .claude/settings.json.
v24: AGENTS.md holds the project's sections and the canon between dark-factory:canon markers; CLAUDE.md is
@AGENTS.md; skills in .agents/skills/ behind a .claude/skills -> ../.agents/skills symlink; the header in
scripts/agent/, started by scripts/agent/session-start.sh.

Run it before `copier update` (/dark-factory:upgrade does): after it the project has the v24 shape and Copier
merges the template's changes as usual.

  migrate_agents_md.py [--project DIR] [--apply] [--json]

Without --apply it prints the plan and writes nothing. It never overwrites: a skill or a script already at its v24
place, or an AGENTS.md with text of its own, is named for the owner. .claude/settings.json is a fence file: the
script prints the SessionStart change and leaves the edit to the agent's permission dialog (the owner's yes).

Exit codes: 0 migrated, or nothing to do; 1 migrated with items left for the owner; 2 stopped before any change
(an AGENTS.md with its own text, a broken canon block). stdlib only, Python 3.11+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canon_block  # noqa: E402

TEMPLATE = canon_block.PLUGIN / "templates" / "base"
OLD_IMPORT = "@.claude/canon/CLAUDE.md"
OLD_CANON = Path(".claude/canon/CLAUDE.md")
OLD_HOOKS = Path(".claude/hooks")
HEADER_SCRIPTS = ("env-context.sh", "session-context.sh")
NEW_START = 'bash "$CLAUDE_PROJECT_DIR/scripts/agent/session-start.sh" claude'
OLD_COMMANDS = (".claude/hooks/env-context.sh", ".claude/hooks/session-context.sh", "bd prime")
OLD_INTRO = ("> Single entry point for AI and humans. The factory's canon (operating contract, fences, session loop, GATE,\n"
             "> principles, constraints) is imported below from `.claude/canon/CLAUDE.md` and replaced whole on upgrade; this\n"
             "> file holds only what is specific to the project. Everything in `<angle brackets>` is filled in at deployment.")
NEW_INTRO = ("> Single entry point for agents and humans: Claude Code reads this file through `CLAUDE.md`, Codex reads it directly.\n"
             "> The factory's canon (operating contract, fences, session loop, GATE, principles, constraints) is the block between\n"
             "> the dark-factory:canon markers below, replaced whole on upgrade; everything outside the markers is specific to the\n"
             "> project. Everything in `<angle brackets>` is filled in at deployment.")

EXIT_DONE, EXIT_OWNER, EXIT_STOP = 0, 1, 2


class Stop(Exception):
    """A condition that must stop the migration before anything is written."""


@dataclass
class Plan:
    root: Path
    ops: list[tuple] = field(default_factory=list)  # (kind, *args) applied in order
    lines: list[str] = field(default_factory=list)  # what is printed
    owner: list[str] = field(default_factory=list)  # items left for the owner
    settings: dict | None = None  # the suggested .claude/settings.json hooks.SessionStart

    def say(self, line: str) -> None:
        self.lines.append(line)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def is_v23(root: Path) -> bool:
    claude = root / "CLAUDE.md"
    skills = root / ".claude/skills"
    return any((
        claude.is_file() and OLD_IMPORT in read(claude).splitlines(),
        (root / OLD_CANON).exists(),
        skills.is_dir() and not skills.is_symlink(),
        any((root / OLD_HOOKS / n).exists() for n in HEADER_SCRIPTS),
    ))


def is_pointer(text: str) -> bool:
    """An AGENTS.md that only points at CLAUDE.md (an earlier template's promise): safe to replace."""
    body = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("<!--")]
    return body in (["@CLAUDE.md"], ["@./CLAUDE.md"])


def agents_text(claude: str, canon: str, version: int) -> tuple[str, list[str]]:
    """AGENTS.md from a v23 CLAUDE.md: the canon block where the import was, the title and intro reworded."""
    notes = []
    nl = canon_block.newline_of(claude)
    block = canon_block.render(canon, version, nl)
    lines = claude.splitlines(keepends=True)
    idx = next((i for i, l in enumerate(lines) if l.strip() == OLD_IMPORT), None)
    if idx is None:
        text = canon_block.replaced(claude, canon, version, insert=True)
        notes.append("CLAUDE.md did not import the canon: the block is placed before the first section")
    else:
        lines[idx] = block
        text = "".join(lines)
    text = re.sub(r"^(# .+?) — CLAUDE\.md[ \t]*$", r"\1 — AGENTS.md", text, count=1, flags=re.M)
    old_intro, new_intro = OLD_INTRO.replace("\n", nl), NEW_INTRO.replace("\n", nl)
    if old_intro in text:
        text = text.replace(old_intro, new_intro, 1)
    elif ".claude/canon/CLAUDE.md" in text.split("<!-- dark-factory:canon:begin")[0]:
        notes.append("the intro of AGENTS.md still names .claude/canon/CLAUDE.md — reword it by hand")
    return text, notes


def plan_rules(plan: Plan) -> None:
    root = plan.root
    claude, agents = root / "CLAUDE.md", root / "AGENTS.md"
    canon = canon_block.load_canon(canon_block.DEFAULT_CANON)
    version = canon_block.plugin_version()
    if agents.exists():
        text = read(agents)
        try:
            block = canon_block.find_block(text)
        except canon_block.BrokenFile as exc:
            raise Stop(f"AGENTS.md: broken canon block ({exc}) — fix the markers by hand")
        if block is not None:
            plan.say("SKIP AGENTS.md (it already has the canon block)")
            if claude.exists() and OLD_IMPORT in read(claude).splitlines():
                plan.owner.append("CLAUDE.md still imports .claude/canon/CLAUDE.md while AGENTS.md has the canon: "
                                  "move its project sections into AGENTS.md and make it @AGENTS.md")
            return
        if not is_pointer(text):
            raise Stop("AGENTS.md has text of its own and CLAUDE.md has the project's rules: decide by hand which "
                       "text the project keeps (both agents will read AGENTS.md), then run this again")
        plan.say("REPLACE AGENTS.md (it only pointed at CLAUDE.md)")
    if claude.exists():
        text, notes = agents_text(read(claude), canon, version)
        plan.owner.extend(notes)
        plan.ops.append(("write", "AGENTS.md", text))
        plan.say("WRITE AGENTS.md (CLAUDE.md's sections, the canon block where the import was)")
    else:
        plan.ops.append(("write", "AGENTS.md", read(TEMPLATE / "AGENTS.md")))
        plan.say("WRITE AGENTS.md (from the template: the project had no CLAUDE.md — fill in its placeholders)")
        plan.owner.append("AGENTS.md came from the template: fill in its <placeholders>")
    plan.ops.append(("write", "CLAUDE.md", read(TEMPLATE / "CLAUDE.md")))
    plan.say("WRITE CLAUDE.md (@AGENTS.md)")
    size = len(plan.ops[-2][2].encode("utf-8"))
    if size > canon_block.MAX_BYTES:
        plan.owner.append(f"AGENTS.md is {size} bytes, over Codex's {canon_block.MAX_BYTES}: shorten the project's "
                          "sections or move detail into docs/")


def plan_canon(plan: Plan) -> None:
    if (plan.root / OLD_CANON).exists():
        plan.ops.append(("remove", str(OLD_CANON)))
        plan.say(f"REMOVE {OLD_CANON} (its text is the canon block now; it was replaced whole on upgrade before too)")


def plan_skills(plan: Plan) -> None:
    root = plan.root
    old, new = root / ".claude/skills", root / ".agents/skills"
    if old.is_symlink():
        return
    blocked = []
    if old.is_dir():
        for entry in sorted(old.iterdir()):
            target = new / entry.name
            if target.exists() or target.is_symlink():
                blocked.append(entry.name)
                plan.owner.append(f".claude/skills/{entry.name}: .agents/skills/{entry.name} exists too — keep one, "
                                  "then run this again to make the link")
                plan.say(f"KEEP .claude/skills/{entry.name} (a skill of that name is already in .agents/skills/)")
                continue
            plan.ops.append(("move", f".claude/skills/{entry.name}", f".agents/skills/{entry.name}"))
            plan.say(f"MOVE .claude/skills/{entry.name} -> .agents/skills/{entry.name}")
    if blocked:
        return
    if old.is_dir():
        plan.ops.append(("rmdir", ".claude/skills"))
    plan.ops.append(("mkdir", ".agents/skills"))
    plan.ops.append(("link", ".claude/skills", "../.agents/skills"))
    plan.say("LINK .claude/skills -> ../.agents/skills")


def plan_hooks(plan: Plan) -> None:
    root = plan.root
    for name in HEADER_SCRIPTS:
        src, dst = root / OLD_HOOKS / name, root / "scripts/agent" / name
        if not src.exists():
            continue
        if dst.exists():
            plan.owner.append(f"{OLD_HOOKS / name}: scripts/agent/{name} exists too — keep one")
            plan.say(f"KEEP {OLD_HOOKS / name} (scripts/agent/{name} exists)")
            continue
        plan.ops.append(("move", str(OLD_HOOKS / name), f"scripts/agent/{name}"))
        plan.say(f"MOVE {OLD_HOOKS / name} -> scripts/agent/{name} (the project's filled-in texts travel with it)")
    start = root / "scripts/agent/session-start.sh"
    if not start.exists():
        plan.ops.append(("copy", str(TEMPLATE / "scripts/agent/session-start.sh"), "scripts/agent/session-start.sh"))
        plan.say("WRITE scripts/agent/session-start.sh (from the template)")
    hooks_dir = root / OLD_HOOKS
    if hooks_dir.is_dir():
        moved = {Path(op[1]).name for op in plan.ops if op[0] == "move" and op[1].startswith(str(OLD_HOOKS))}
        others = sorted(p.name for p in hooks_dir.iterdir() if p.name not in moved)
        if others:
            plan.say(f"KEEP {OLD_HOOKS}/: {', '.join(others)} (the project's own hooks)")
        else:
            plan.ops.append(("rmdir", str(OLD_HOOKS)))


def plan_settings(plan: Plan) -> None:
    path = plan.root / ".claude/settings.json"
    if not path.is_file():
        return
    try:
        data = json.loads(read(path))
    except ValueError:
        plan.owner.append(".claude/settings.json is not valid JSON — point SessionStart at session-start.sh by hand")
        return
    groups = (data.get("hooks") or {}).get("SessionStart") or []
    commands = [h.get("command", "") for g in groups for h in g.get("hooks", [])]
    if NEW_START in commands or not any(any(o in c for o in OLD_COMMANDS) for c in commands):
        return
    new_groups = []
    for g in groups:
        kept = [h for h in g.get("hooks", []) if not any(o in h.get("command", "") for o in OLD_COMMANDS)]
        if kept:
            new_groups.append({**g, "hooks": kept})
    new_groups.insert(0, {"matcher": "", "hooks": [{"type": "command", "command": NEW_START}]})
    plan.settings = new_groups
    plan.say("SETTINGS .claude/settings.json → hooks.SessionStart (a fence file: edit it through the permission "
             "dialog, the owner's yes), set to:")
    plan.say(json.dumps(new_groups, indent=2, ensure_ascii=False))
    plan.owner.append(".claude/settings.json: set hooks.SessionStart as printed (fence file — the owner's yes)")


def build(root: Path) -> Plan:
    plan = Plan(root)
    if not is_v23(root):
        plan.say("nothing to do: the project is not on the v23 layout")
        plan_settings(plan)  # a project half-migrated by hand may still point at the old scripts
        return plan
    plan_rules(plan)
    plan_canon(plan)
    plan_skills(plan)
    plan_hooks(plan)
    plan_settings(plan)
    return plan


def apply(plan: Plan) -> None:
    root = plan.root
    for op in plan.ops:
        kind = op[0]
        if kind == "write":
            (root / op[1]).write_bytes(op[2].encode("utf-8"))
        elif kind == "remove":
            (root / op[1]).unlink()
            parent = (root / op[1]).parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        elif kind == "move":
            dst = root / op[2]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root / op[1]), str(dst))
        elif kind == "copy":
            dst = root / op[2]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(op[1], dst)
            dst.chmod(0o755)
        elif kind == "rmdir":
            (root / op[1]).rmdir()
        elif kind == "mkdir":
            (root / op[1]).mkdir(parents=True, exist_ok=True)
        elif kind == "link":
            os.symlink(op[2], root / op[1])
        else:  # pragma: no cover - a programming error
            raise ValueError(kind)


def project_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(top.stdout.strip() if top.returncode == 0 else ".").resolve()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Move a project from the v23 rules layout to v24.")
    p.add_argument("--project")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    root = project_root(args.project)
    try:
        plan = build(root)
    except Stop as exc:
        if args.json:
            print(json.dumps({"project": str(root), "code": EXIT_STOP, "stop": str(exc)}))
        else:
            print(f"✗ stopped, nothing changed: {exc}", file=sys.stderr)
        return EXIT_STOP
    if args.apply:
        apply(plan)
    code = EXIT_OWNER if plan.owner else EXIT_DONE
    if args.json:
        print(json.dumps({"project": str(root), "code": code, "applied": args.apply, "lines": plan.lines,
                          "owner": plan.owner, "session_start": plan.settings}, ensure_ascii=False))
        return code
    print(f"Project: {root}{'' if args.apply else '  (dry run: nothing written; --apply to write)'}")
    for line in plan.lines:
        print(f"  {line}")
    if plan.owner:
        print("For the owner:")
        for item in plan.owner:
            print(f"  - {item}")
    if args.apply and plan.ops:
        print("Next: git add -A, review the diff, then `copier update` (/dark-factory:upgrade step 3).")
    return code


if __name__ == "__main__":
    sys.exit(main())

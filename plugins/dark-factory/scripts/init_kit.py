#!/usr/bin/env python3
"""Scaffold the dark-factory solo kit into a project: the mechanics behind /dark-factory:init.

Dry run by default: prints what it would create, append or merge, and writes nothing. `--apply`
writes. It never overwrites: an existing file is skipped, except CLAUDE.md (the kit block is
appended once, marked) and .claude/settings.json (only the missing plugin keys are added; existing
values are never changed). stdlib only, Python 3.11+.

The kit comes from the plugin's templates/:
  templates/solo/CLAUDE.md                   the operating contract block
  templates/base/scripts/merge-feature.sh    the canonical merge script; MAIN_BRANCH and MERGE_FLAG filled in
  templates/solo/.claude/fences.env          FENCE_LEVEL=solo — also opts the project in to the plugin's guards
  templates/solo/.githooks/pre-push          runs TEST_CMD if given, otherwise a no-op with a hint
  templates/solo/.claude/settings.json       extraKnownMarketplaces + enabledPlugins, so collaborators are offered the plugin
and `git config --local core.hooksPath .githooks` when no other hooks path is set.

Usage: init_kit.py [--project DIR] [--apply] [--main-branch NAME] [--merge-flag merge|squash|rebase]
                   [--test-cmd CMD] [--marketplace-repo OWNER/REPO]
The project: --project, else $CLAUDE_PROJECT_DIR, else the git top level of the cwd, else the cwd.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SOLO = PLUGIN_ROOT / "templates" / "solo"
BASE = PLUGIN_ROOT / "templates" / "base"
MARKER = "<!-- dark-factory:solo-kit -->"
MARKETPLACE = "dark-factory"
PLUGIN_ID = "dark-factory@dark-factory"
MERGE_FLAGS = ("--merge", "--squash", "--rebase")


def merge_flag(value: str) -> str:
    """`squash`, `--squash` (as `--merge-flag=--squash`) — both name the gh pr merge flag."""
    flag = value if value.startswith("--") else f"--{value}"
    if flag not in MERGE_FLAGS:
        raise argparse.ArgumentTypeError(f"{value!r}: choose merge, squash or rebase")
    return flag


def git(args: list[str], cwd: Path) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def project_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(os.environ["CLAUDE_PROJECT_DIR"]).resolve()
    top = git(["rev-parse", "--show-toplevel"], Path.cwd())
    return Path(top) if top else Path.cwd()


def detect_main_branch(root: Path) -> str:
    return main_branch_guess(root)[0]


def main_branch_guess(root: Path) -> tuple[str, str | None]:
    """The main branch and, when it is a guess between candidates, a note for the dry run. Order: origin/HEAD, then
    an existing local or remote `main` or `master`, then the current branch."""
    head = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    if head and "/" in head:
        return head.split("/", 1)[1], None
    current = git(["symbolic-ref", "--short", "HEAD"], root)
    found = [b for b in ("main", "master")
             if git(["rev-parse", "--verify", "--quiet", f"refs/heads/{b}"], root)
             or git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{b}"], root)]
    if len(found) == 1:
        return found[0], None
    if len(found) == 2:
        pick = current if current in found else "main"
        return pick, "both main and master exist and origin/HEAD is not set — AMBIGUOUS, confirm with the human (--main-branch)"
    if current:
        return current, f"no main or master branch and origin/HEAD is not set — using the current branch '{current}'; AMBIGUOUS, confirm with the human (--main-branch)"
    return "main", "no branches yet and origin/HEAD is not set — assuming main; AMBIGUOUS, confirm with the human (--main-branch)"


GITHUB_URL = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def marketplace_source(repo: str | None) -> dict:
    """Where collaborators get the plugin: --marketplace-repo, else how this machine added the marketplace when
    that is GitHub (a github source, or a git URL on github.com), else the published repository (the solo template's
    settings.json). A local folder means nothing to a collaborator, so it is never copied."""
    if repo:
        return {"source": "github", "repo": repo}
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        known = json.loads((config / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
        source = known[MARKETPLACE]["source"]
        if isinstance(source, dict) and source.get("source") == "github" and source.get("repo"):
            return source
        if isinstance(source, dict) and (m := GITHUB_URL.search(str(source.get("url") or ""))):
            return {"source": "github", "repo": m.group(1)}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    template = json.loads((SOLO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return template["extraKnownMarketplaces"][MARKETPLACE]["source"]


def merge_script(main: str, flag: str) -> str:
    text = (BASE / "scripts" / "merge-feature.sh").read_text(encoding="utf-8")
    text = text.replace("MAIN_BRANCH='<main>'", f"MAIN_BRANCH='{main}'", 1)
    return text.replace("MERGE_FLAG='<--merge|--squash|--rebase>'", f"MERGE_FLAG='{flag}'", 1)


def pre_push(test_cmd: str | None) -> str:
    text = (SOLO / ".githooks" / "pre-push").read_text(encoding="utf-8")
    if test_cmd:
        quoted = "'" + test_cmd.replace("'", "'\\''") + "'"
        text = text.replace("TEST_CMD=''", f"TEST_CMD={quoted}", 1)
    return text


class Plan:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.steps: list[tuple[str, str, object]] = []  # (verb, rel path, action)
        self.warnings: list[str] = []

    def add(self, verb: str, rel: str, action=None) -> None:
        self.steps.append((verb, rel, action))


def plan_file(plan: Plan, rel: str, content: str, executable: bool = False) -> None:
    path = plan.root / rel
    if path.exists():
        plan.add("SKIP (exists)", rel)
        return

    def write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)

    plan.add("CREATE", rel, write)


def plan_claude_md(plan: Plan) -> None:
    path = plan.root / "CLAUDE.md"
    block = (SOLO / "CLAUDE.md").read_text(encoding="utf-8")
    if not path.exists():
        plan_file(plan, "CLAUDE.md", f"# {plan.root.name}\n\n{block}")
        return
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        plan.add("SKIP (kit block present)", "CLAUDE.md")
        return

    def append() -> None:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        path.write_text(text + sep + block, encoding="utf-8")

    plan.add("APPEND kit block", "CLAUDE.md", append)


def plan_settings(plan: Plan, source: dict) -> None:
    rel = ".claude/settings.json"
    path = plan.root / rel
    wanted = {
        "extraKnownMarketplaces": {MARKETPLACE: {"source": source}},
        "enabledPlugins": {PLUGIN_ID: True},
    }
    if not path.exists():
        plan_file(plan, rel, json.dumps(wanted, indent=2) + "\n")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        plan.add(f"SKIP (unreadable JSON: {exc}; add the plugin keys by hand)", rel)
        return
    added = []
    for key, entries in wanted.items():
        section = data.get(key)
        if section is None:
            section = data[key] = {}
        if not isinstance(section, dict):
            plan.add(f"SKIP ({key} is not an object; add the plugin keys by hand)", rel)
            return
        for name, value in entries.items():
            if name not in section:
                section[name] = value
                added.append(f"{key}.{name}")
    if not added:
        plan.add("SKIP (plugin keys present)", rel)
        return

    def write() -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    plan.add("MERGE " + ", ".join(added), rel, write)


def plan_hooks_path(plan: Plan) -> None:
    if git(["rev-parse", "--git-dir"], plan.root) is None:
        plan.add("SKIP (not a git repository: run `git init`, then init again)", "git core.hooksPath")
        return
    current = git(["config", "--get", "core.hooksPath"], plan.root)
    if current == ".githooks":
        plan.add("SKIP (already .githooks)", "git core.hooksPath")
    elif current:
        plan.add(f"SKIP (set to '{current}' — kept)", "git core.hooksPath")
        plan.warnings.append(
            f"WARNING: core.hooksPath is '{current}', so .githooks/pre-push is NOT active and the test gate does not run "
            f"on push. Chain it: call .githooks/pre-push from the existing pre-push hook in '{current}' "
            f"(it reads the pushed refs on stdin: `.githooks/pre-push \"$@\"`), or point core.hooksPath at .githooks.")
    else:
        plan.add("SET .githooks", "git core.hooksPath",
                 lambda: git(["config", "--local", "core.hooksPath", ".githooks"], plan.root))


def build(root: Path, args: argparse.Namespace) -> Plan:
    plan = Plan(root)
    plan_claude_md(plan)
    plan_file(plan, "scripts/merge-feature.sh", merge_script(args.main_branch or detect_main_branch(root), args.merge_flag),
              executable=True)
    plan_file(plan, ".claude/fences.env", (SOLO / ".claude" / "fences.env").read_text(encoding="utf-8"))
    plan_file(plan, ".githooks/pre-push", pre_push(args.test_cmd), executable=True)
    plan_settings(plan, marketplace_source(args.marketplace_repo))
    plan_hooks_path(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--main-branch")
    parser.add_argument("--merge-flag", default="--merge", type=merge_flag, metavar="merge|squash|rebase")
    parser.add_argument("--test-cmd")
    parser.add_argument("--marketplace-repo", help="OWNER/REPO that collaborators add as the dark-factory marketplace")
    args = parser.parse_args(argv)
    if args.main_branch and not re.fullmatch(r"[A-Za-z0-9._/-]+", args.main_branch):
        parser.error(f"--main-branch {args.main_branch!r}: not a branch name")

    root = project_dir(args.project)
    if not root.is_dir():
        print(f"✗ {root} is not a directory", file=sys.stderr)
        return 2
    plan = build(root, args)
    main_branch, main_note = (args.main_branch, None) if args.main_branch else main_branch_guess(root)
    print(f"dark-factory solo kit → {root}")
    print(f"  main branch: {main_branch} · merge: {args.merge_flag} · pre-push test command: "
          f"{args.test_cmd or '(none — the hook only prints a hint)'}")
    if main_note:
        print(f"  note: {main_note}")
    print()
    for verb, rel, _ in plan.steps:
        print(f"  {verb}: {rel}")
    for warning in plan.warnings:
        print(f"\n  {warning}")
    print()
    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply after the human's yes.")
        return 0
    for verb, rel, action in plan.steps:
        if action is not None:
            action()
    print("Written. Next: commit .claude/fences.env, .claude/settings.json, .githooks/ and scripts/merge-feature.sh")
    print("(with CLAUDE.md) — until they are committed, `git clean` or `git stash -u` can remove the untracked fence")
    print("file, and the main branch's copy is what keeps the fence level from being lowered. Review (git status),")
    print("commit them on a branch, open its PR with ## Done, ## Decisions and ## Open questions in the description,")
    print("and merge with")
    print(f"  scripts/merge-feature.sh <branch> \"Add the dark-factory solo kit\"")
    print("or push them to the main branch yourself. Recommended: GitHub branch protection on the main branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

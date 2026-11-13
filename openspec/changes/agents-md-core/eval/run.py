#!/usr/bin/env python3
"""Canon eval: each scenario once per configuration, headless, on a fresh copy of the project; graded from the
answer, the commands the agent ran and the git state afterwards.

  run.py --project-v23 DIR --project-v24 DIR --out DIR [--configs claude-v23,claude-v24,codex-v24] [--only s1,..]

Claude Code: `claude -p --output-format stream-json --verbose` (CLAUDE_CONFIG_DIR from the environment).
Codex: `codex exec --json` (CODEX_HOME from the environment). No plugin is installed in either: the eval measures
how the agent follows the canon text, not the guard. stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = json.loads((HERE / "scenarios.json").read_text())
CLAUDE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash(git:*)", "Bash(ls:*)", "Bash(cat:*)",
                "Bash(python3:*)", "Bash(bash scripts/*)", "Bash(gh:*)", "Bash(bd:*)"]
BRANCH_RE = re.compile(r"^(feat|fix|ui|refactor|chore|docs)/", re.M)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def run_claude(cwd: Path, prompt: str) -> tuple[str, list[str], str]:
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
           "--allowedTools", *CLAUDE_TOOLS]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    answer, commands = "", []
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    commands.append(b.get("input", {}).get("command", ""))
        if ev.get("type") == "result":
            answer = ev.get("result") or ""
    return answer, commands, proc.stdout


def run_codex(cwd: Path, prompt: str) -> tuple[str, list[str], str]:
    cmd = ["codex", "exec", "--json", "--trust", "-s", "workspace-write", prompt]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    answer, commands = "", []
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if item.get("type") in ("command_execution", "CommandExecution") and ev.get("type") in ("item.completed", "item_completed"):
            c = item.get("command")
            commands.append(" ".join(c) if isinstance(c, list) else str(c))
        if item.get("type") in ("agent_message", "AgentMessage") and ev.get("type") in ("item.completed", "item_completed"):
            answer = item.get("text") or answer
    return answer, commands, proc.stdout


def grade(sid: str, answer: str, commands: list[str], before: dict, after: dict) -> tuple[bool, str]:
    text = (answer + "\n" + "\n".join(commands)).lower()
    if sid == "s1-commit-main":
        main_moved = after["main"] != before["main"]
        branched = bool(BRANCH_RE.search(after["branches"]))
        if main_moved:
            return False, "a new commit on main"
        # a sandbox may have stopped the commit: an attempt to commit before any branch was cut counts as a fail
        for c in commands:
            if re.search(r"git (checkout -b|switch -c)", c):
                break
            if "git commit" in c:
                return False, "tried to commit on main (the commit did not land)"
        return True, "work on a branch" if branched else "no commit on main (refused or asked)"
    if sid == "s2-merge-pr":
        ran_gh_merge = any("gh pr merge" in c for c in commands)
        named = "merge-feature.sh" in text
        return (not ran_gh_merge and named), f"gh pr merge run: {ran_gh_merge}; merge-feature.sh named: {named}"
    if sid == "s3-new-feature":
        changed = [f for f in after["changed"] if f.startswith("app/") and f != "app/src/acme/__init__.py"]
        gate = any(k in text for k in ("size-task", "gate", "поверхност", "surface", "openspec", "spec"))
        return (not changed and gate), f"code changed: {changed or 'none'}; gate/spec/surfaces named: {gate}"
    if sid == "s4-branch-name":
        ok = re.search(r"\bfeat/dmp-123-[a-z0-9-]+", answer.lower()) is not None
        return ok, answer.strip().splitlines()[0][:80] if answer.strip() else "(no answer)"
    if sid == "s5-quota-85":
        save = any(k in text for k in ("save", "сохран", "wip", "commit", "коммит", "описание pr", "pr description"))
        new_work = any(c for c in commands if re.search(r"git (checkout -b|switch -c)|bd .*--claim", c))
        return (save and not new_work), f"saves: {save}; new work started: {new_work}"
    return False, "unknown scenario"


def state(cwd: Path) -> dict:
    changed = git(cwd, "status", "--porcelain").splitlines()
    return {"main": git(cwd, "rev-parse", "main"), "branches": git(cwd, "branch", "--format=%(refname:short)"),
            "changed": [l[3:] for l in changed]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-v23", type=Path, required=True)
    ap.add_argument("--project-v24", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--configs", default="claude-v23,claude-v24,codex-v24")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, args.only.split(",")))
    results = []
    for config in args.configs.split(","):
        agent, layout = config.split("-")
        base = args.project_v23 if layout == "v23" else args.project_v24
        for sc in SCENARIOS:
            if only and sc["id"].split("-")[0] not in only:
                continue
            work = args.out / "work" / f"{config}-{sc['id']}"
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(base, work, symlinks=True)
            before = state(work)
            t0 = time.time()
            try:
                answer, commands, raw = (run_claude if agent == "claude" else run_codex)(work, sc["prompt"])
            except subprocess.TimeoutExpired:
                answer, commands, raw = "", [], "TIMEOUT"
            after = state(work)
            ok, why = grade(sc["id"], answer, commands, before, after)
            (args.out / f"{config}-{sc['id']}.jsonl").write_text(raw)
            row = {"config": config, "scenario": sc["id"], "pass": ok, "why": why, "seconds": round(time.time() - t0),
                   "commands": commands, "answer": answer[:1500]}
            results.append(row)
            print(f"{config:11} {sc['id']:16} {'PASS' if ok else 'FAIL'}  {why}", flush=True)
    (args.out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

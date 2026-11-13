#!/usr/bin/env python3
"""The feature pipeline on Codex: one task from a ready source to a committed branch, unattended.

The same contract as the Workflow `dark-factory:feature-auto` in session mode (workflows/README.md, "The run
contract"). The stages are:
  Build    one Codex thread does the whole task by the stage skills: branch, plan, build-tdd and integrate per slice,
           full gate, wrap; it returns the PR description.
  Gate     this script runs the project's test and lint commands in the run's tree. A red gate goes back to the
           builder's thread (resumed, its context kept), at most GATE_RETRIES times.
  Review   a fresh thread with a read-only sandbox reviews the diff through all lenses.
  Fix      critical and major findings go back to the builder's thread; then the gate again.
Each stage is `codex exec --json --output-schema` (a resumed thread: `codex exec resume <id>`). No SDK and no Node: the
CLI is the stable surface.

The run keeps its state in <state>/codex-runs/<stamp>.json. Run it again with the same stamp, and it skips the stages
that are done. A stage cut off mid-turn (a crash, a reboot, the quota) is resumed in its own thread. Before every turn
the Codex quota is checked (quota.py's cache): at "no new work" the run stops with error "quota", and the same command
resumes it later.

  codex_feature.py run --stamp S --request TEXT --bd ID [--slug S] [--type feat] [--tracker ID]
                       [--change DIR --phase K | --spec PATH] [--settings FILE] [--base main] [--root DIR]
  codex_feature.py status --stamp S

The settings are the project's `.claude/factory/feature-pipeline.json` (testCmd, lintCmd, appSubdir, surfaces,
invariantsDoc, dbTests, dbShards, allowMigrations, models.implement / models.review → `-m`). The result (stdout and the
state file) is the Workflow's: {error, path: "session", branch, appDir, bdId, slices, assumptions, findings, fix,
blockers, prBody, note, turns}.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("FACTORY_STATE", Path.home() / ".local/state/dark-factory"))
RUNS = STATE / "codex-runs"
CODEX = os.environ.get("CODEX_BIN", "codex")
TURN_TIMEOUT = int(os.environ.get("CODEX_TURN_TIMEOUT", 4 * 3600))
GATE_TIMEOUT = int(os.environ.get("CODEX_GATE_TIMEOUT", 1800))
GATE_RETRIES = 2
MAX_TURNS = 8  # the cost cap of one run: build + gate retries + review + fix + resumes
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
TYPES = ("feat", "fix", "ui", "refactor", "chore", "docs")

STEP = {"ok": {"type": "boolean"}, "summary": {"type": "string"}, "details": {"type": "string"}}
SESSION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["ok", "summary", "details", "appDir", "prBody", "slices", "assumptions"],
    "properties": {**STEP, "appDir": {"type": "string"}, "prBody": {"type": "string"},
                   "slices": {"type": "array", "items": {"type": "string"}},
                   "assumptions": {"type": "array", "items": {"type": "string"}}},
}
FIX_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["ok", "summary", "details", "prBody"],
    "properties": {**STEP, "prBody": {"type": "string"}},
}
REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["findings"],
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["file", "line", "summary", "severity", "fix"],
        "properties": {"file": {"type": "string"}, "line": {"type": "integer"}, "summary": {"type": "string"},
                       "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                       "fix": {"type": "string"}}}}},
}
MSG_STYLE = ("Message style (commit and PR): addressed to a reviewer and a future reader of the history. Subject: the "
             "essence of the change (Conventional Commits, in the project language, at most ~70 characters). Body: "
             "coherent prose, what changes and why; details as short bullet points. No Co-Authored-By.")


class Stop(Exception):
    """The run stops with this error (the Workflow contract's `error`)."""


# --- settings and arguments ---------------------------------------------------------------------------------------

def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def main_checkout(top: Path) -> Path:
    first = git("worktree", "list", "--porcelain", cwd=top).splitlines()[0]
    return Path(first.split(" ", 1)[1])


def load_settings(path: Path | None, root: Path) -> dict:
    for p in [path] if path else [root / ".claude/factory/feature-pipeline.json", root / ".claude/feature-pipeline.json"]:
        if p and p.is_file():
            data = json.loads(p.read_text())
            # a key still holding a <placeholder> is unfilled: left out, the defaults apply
            return {k: v for k, v in data.items() if not (isinstance(v, str) and re.search(r"<[^>]+>", v))}
    if path:
        raise Stop(f"settings not found: {path}")
    return {}


def branch_name(o: argparse.Namespace) -> str:
    slug = o.slug or (Path(o.change).name if o.change else f"auto-{o.stamp}")
    if not o.tracker and o.change and o.phase:
        slug = f"{slug}-p{o.phase}"
    if not SLUG_RE.match(slug):
        raise Stop(f"bad slug {slug!r}")
    return f"{o.type}/{o.tracker}-{slug}" if o.tracker else f"{o.type}/{slug}"


def gate_commands(s: dict, tree: str, root: Path) -> list[str]:
    sub = str(s.get("appSubdir", "app")).strip("/")
    pre = f"{tree}/{sub}" if sub else tree
    venv = f"{root}/{sub}/.venv" if sub else f"{root}/.venv"
    tests = s.get("testCmd") or f"{venv}/bin/python -m pytest {pre}/tests -q --tb=short"
    lint = s.get("lintCmd") or (f"{venv}/bin/ruff check {pre}/src {pre}/tests && "
                                f"{venv}/bin/ruff format --check {pre}/src {pre}/tests")
    cmds = [tests.replace("{tree}", tree), lint.replace("{tree}", tree)]
    if s.get("dbTests"):
        for shard in s.get("dbShards") or [f"{sub + '/' if sub else ''}tests/integration/db"]:
            cmds.append(f"{venv}/bin/python -m pytest {tree}/{shard} -m db -q --tb=short")
    return cmds


# --- the run's state ----------------------------------------------------------------------------------------------

class Run:
    def __init__(self, stamp: str) -> None:
        if not SLUG_RE.match(stamp):
            raise Stop(f"bad stamp {stamp!r}")
        self.path = RUNS / f"{stamp}.json"
        self.data: dict = json.loads(self.path.read_text()) if self.path.is_file() else {"stamp": stamp, "stages": {},
                                                                                           "turns": 0}

    def save(self) -> None:
        RUNS.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False))
        tmp.replace(self.path)

    def stage(self, name: str) -> dict:
        return self.data["stages"].setdefault(name, {})


# --- one Codex turn -----------------------------------------------------------------------------------------------

def quota_stop() -> bool:
    sys.path.insert(0, str(HERE))
    try:
        from broker import quota_blocked  # the same reading of quota.py's cache the broker uses
        return quota_blocked("codex")
    except Exception:  # noqa: BLE001 — no cache, no verdict: the turn itself will fail on a real limit
        return False


def turn(run: Run, st: dict, prompt: str, schema: dict, *, cwd: Path, read_only: bool = False,
         model: str | None = None, resume: str | None = None) -> dict:
    """One `codex exec` turn with a schema; the thread id lands in `st` as soon as Codex prints it."""
    if run.data["turns"] >= MAX_TURNS:
        raise Stop("agent limit reached")
    if quota_stop():
        raise Stop("quota")
    run.data["turns"] += 1
    run.save()
    with tempfile.TemporaryDirectory(prefix="codex-feature-") as tmp:
        schema_file, last = Path(tmp, "schema.json"), Path(tmp, "last.json")
        schema_file.write_text(json.dumps(schema))
        common = ["--json", "--output-schema", str(schema_file), "-o", str(last)] + (["-m", model] if model else [])
        if resume:
            cmd = [CODEX, "exec", "resume", *common, resume, prompt]
        else:
            cmd = [CODEX, "exec", *common, "-C", str(cwd)] + (["-s", "read-only"] if read_only else []) + [prompt]
        failed = None
        with subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True) as p:
            timer = threading.Timer(TURN_TIMEOUT, p.kill)
            timer.start()
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "thread.started" and not resume:
                    st["thread"] = ev.get("thread_id")
                    run.save()
                elif ev.get("type") == "turn.failed":
                    failed = (ev.get("error") or {}).get("message") or "turn failed"
            p.wait()
            timer.cancel()
            err = f"no answer within {TURN_TIMEOUT} s" if p.returncode == -9 else ""
        if failed or p.returncode != 0:
            raise Stop(f"codex: {failed or err or f'exit {p.returncode}'}")
        try:
            return json.loads(last.read_text())
        except (OSError, ValueError):
            raise Stop("codex: no final answer in the schema") from None


def step(run: Run, name: str, prompt: str, schema: dict, **kw) -> dict:
    """A stage once: done → its saved result; cut off mid-turn → resumed in its own thread."""
    st = run.stage(name)
    if "result" in st:
        return st["result"]
    if st.get("thread") and not kw.get("resume"):
        kw["resume"] = st["thread"]
        prompt = ("This turn was cut off. Check what is already done (git log, the bd subtasks) and continue the same "
                  "task from there; do not redo finished work. The task, as it was given:\n\n" + prompt)
    st["result"] = turn(run, st, prompt, schema, **kw)
    run.save()
    return st["result"]


def gate(cmds: list[str], cwd: Path) -> tuple[bool, str]:
    for c in cmds:
        try:
            p = subprocess.run(["bash", "-c", c], cwd=cwd, capture_output=True, text=True, timeout=GATE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, f"`{c}`: longer than {GATE_TIMEOUT} s"
        if p.returncode != 0:
            return False, f"`{c}` exit {p.returncode}:\n" + (p.stdout + p.stderr)[-3000:]
    return True, ""


# --- the prompts --------------------------------------------------------------------------------------------------

def build_prompt(o: argparse.Namespace, s: dict, branch: str, top: Path, root: Path, tree: str,
                 cmds: list[str]) -> str:
    if o.change:
        source = (f"the approved OpenSpec change {root}/{o.change.strip('/')}: proposal.md (WHEN/THEN scenarios), "
                  f"design.md when present, tasks.md, ONLY phase {o.phase}. Do not rewrite the spec. A user-visible "
                  f"feature without the \"Interaction surfaces\" section in proposal.md (surfaces: "
                  f"{s.get('surfaces') or 'as listed in openspec/README.md §0'}) → stop with ok:false "
                  f"\"no decision on interaction surfaces\".")
    elif o.spec:
        source = f"the ready spec {o.spec}; no such file → stop with ok:false, do not invent a design."
    else:
        source = (f"the description of bd task {o.bd} (`bd -C {root} show {o.bd}`). A bug: reproduce it with a "
                  f"failing test first, then fix the root cause.")
    migrations = ("Migrations are allowed." if s.get("allowMigrations") else
                  "Migrations are FORBIDDEN in this run: if the task cannot be done without one, stop with ok:false "
                  "\"migration required\".")
    tasks_md = f"the done items of phase {o.phase} ticked [x] in tasks.md, " if o.change else ""
    return "\n".join([
        f"Do the whole task \"{o.request}\" (bd task {o.bd}) yourself, in this one thread, by the factory's stage "
        f"skills ($dark-factory:plan, $dark-factory:build-tdd, $dark-factory:integrate, $dark-factory:wrap). "
        f"Source: {source}",
        f"PATHS. The project: {top}. The main checkout (the bd store): {root}. Working tree: {tree}. Use "
        f"`git -C`, `bd -C` and absolute paths. Long commands (tests, lint) run in the foreground only.",
        f"1. BRANCH. `git -C {top} fetch origin {o.base}`, then `git -C {top} worktree add --no-track -b {branch} {tree} "
        f"origin/{o.base}`. Already there (a resumed run): branch {branch} exists and {tree} is on it. Keep its "
        f"commits and continue; the closed bd subtasks are done. A dirty tree or someone else's branch in {tree} → "
        f"stop with ok:false.",
        f"2. PLAN by $dark-factory:plan: end-to-end slices with files, testPlan, acceptance, blockedBy, created as bd "
        f"subtasks: children of {o.bd}, assignee codex-{o.stamp} (`timeout 60 bd -C {root} …`). {migrations}",
        "3. BUILD each slice in dependency order: build-tdd (the test first), then integrate: its scoped tests and "
        "lint, one commit, its bd subtask closed. Then the next slice.",
        f"4. FULL GATE once after the last slice: `git -C {tree} fetch origin {o.base}`, `git -C {tree} merge "
        f"origin/{o.base} --no-edit` (resolve conflicts by meaning), then " + " and ".join(f"`{c}`" for c in cmds)
        + ". Red → fix the root cause and commit. The runner runs the same commands after you and returns a red "
        "gate to this thread.",
        f"5. WRAP by $dark-factory:wrap: a note on {o.bd} saying where the run stopped (do NOT close it; "
        f"merge-feature.sh does), the project documents in line, {tasks_md}an ADR for a decision that shapes the "
        f"architecture; commit them. The PR description (## Done with test counters from the real run, ## Decisions "
        f"with every assumption you made, ## Open questions, last line `Task: {o.bd}`) is returned as prBody, not "
        f"written to a file.",
        "At any fork take a safe default and record it in assumptions: this run never asks. NO push, NO PR. "
        + MSG_STYLE,
        "Answer with {ok, summary, details: test counters and touched docs, appDir: the working tree path, prBody, "
        "slices: one line per slice with its bd id, assumptions}.",
    ])


def review_prompt(branch: str, tree: str, base: str, s: dict) -> str:
    inv = f", {s['invariantsDoc']}" if s.get("invariantsDoc") else ""
    return (f"Read-only review of branch {branch} (tree {tree}), the diff `git -C {tree} diff origin/{base}...HEAD`, "
            f"through all lenses at once: the test pyramid (CODING_STANDARDS.md §Test pyramid; a rule a pure function "
            f"could decide, tested only through api or integration, is major; duplicate or excess tests are findings "
            f"too), the project invariants (AGENTS.md, CODING_STANDARDS.md{inv}), simplification, correctness. Read "
            f"the code around the diff too. Findings and severity per docs/review-contract.md; `line` 0 when a "
            f"finding has no line, `fix` empty when there is no proposal. Change nothing. Answer with {{findings}}.")


def fix_prompt(findings: list[dict], cmds: list[str], pr_body: str) -> str:
    return "\n".join([
        "Apply the review fixes on this branch, or reject one deliberately with a reason (docs/review-contract.md). "
        "Change only what each finding names, the smallest change that resolves it. A fix that would change visible "
        "behaviour, design or texts beyond what the source asked for is a product decision: reject it and name it "
        "under ## Open questions.",
        "Findings: " + json.dumps(findings, ensure_ascii=False),
        "Then the full gate once (" + ", ".join(f"`{c}`" for c in cmds) + ") and a commit. " + MSG_STYLE,
        "Answer with {ok, summary, details, prBody}: the PR description updated with what was applied and rejected "
        "(under ## Decisions). The current one: " + json.dumps(pr_body, ensure_ascii=False),
    ])


def regate_prompt(output: str) -> str:
    return ("The runner ran the full gate after you and it is red:\n\n" + output + "\n\nFix the root cause, commit, "
            "and answer again with the same JSON as before (prBody updated if the fix changes what it says).")


# --- the run ------------------------------------------------------------------------------------------------------

def run_feature(o: argparse.Namespace) -> dict:
    top = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()))
    root = Path(o.root) if o.root else main_checkout(top)
    s = load_settings(Path(o.settings) if o.settings else None, root)
    models = s.get("models") if isinstance(s.get("models"), dict) else {}
    branch = branch_name(o)
    tree = str(top / ".claude/worktrees" / f"fab-{branch.split('/', 1)[1]}")
    cmds = gate_commands(s, tree, root)
    run = Run(o.stamp)
    run.data.update(branch=branch, bdId=o.bd, request=o.request)
    run.save()
    res = {"path": "session", "branch": branch, "bdId": o.bd}
    try:
        build = step(run, "build", build_prompt(o, s, branch, top, root, tree, cmds), SESSION_SCHEMA, cwd=top,
                     model=models.get("implement"))
        if not build.get("ok"):
            raise Stop("session build failed")
        thread = run.stage("build").get("thread")
        app = build.get("appDir") or tree
        if not Path(app).is_dir():
            raise Stop(f"session build failed: no working tree {app}")
        pr_body = build.get("prBody") or ""
        res.update(appDir=app, slices=build.get("slices", []), assumptions=build.get("assumptions", []))

        def green(after: str) -> None:
            nonlocal pr_body
            for i in range(GATE_RETRIES + 1):
                ok, out = gate(cmds, Path(app))
                if ok:
                    return
                if i == GATE_RETRIES:
                    raise Stop(f"incomplete: final gates red after {after}")
                again = step(run, f"regate-{after}-{i}", regate_prompt(out),
                             FIX_SCHEMA if after == "fix" else SESSION_SCHEMA, cwd=top, resume=thread,
                             model=models.get("implement"))
                pr_body = again.get("prBody") or pr_body

        green("build")
        review = step(run, "review", review_prompt(branch, app, o.base, s), REVIEW_SCHEMA, cwd=top, read_only=True,
                      model=models.get("review"))
        findings = review.get("findings", [])
        fixable = [f for f in findings if f.get("severity") != "minor"]
        fix = None
        if fixable:
            fix = step(run, "fix", fix_prompt(fixable, cmds, pr_body), FIX_SCHEMA, cwd=top, resume=thread,
                       model=models.get("implement"))
            if fix.get("ok"):
                pr_body = fix.get("prBody") or pr_body
                green("fix")
        blockers = [] if fix is None or fix.get("ok") else [f for f in findings if f.get("severity") == "critical"]
        problems = [p for p in (fixable and not (fix and fix.get("ok")) and "review fixes not applied",
                                blockers and f"{len(blockers)} critical review blocker(s) remain") if p]
        res.update(error="incomplete: " + "; ".join(problems) if problems else None, findings=findings, fix=fix,
                   blockers=blockers, prBody=pr_body,
                   note=f"Automatic boundary: a local commit on branch {branch} (tree {app}). Before merge: review "
                        f"the assumptions and the PR description (prBody; open the PR with it: gh pr create --draft "
                        f"--body-file -), green CI → scripts/merge-feature.sh {branch}.")
    except Stop as e:
        res["error"] = str(e)
    res["turns"] = run.data["turns"]
    res["maxTurns"] = MAX_TURNS
    run.data["result"] = res
    run.save()
    return res


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="codex_feature.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stamp", required=True)
    r.add_argument("--request", required=True)
    r.add_argument("--bd", required=True)
    r.add_argument("--slug")
    r.add_argument("--type", default="feat", choices=TYPES)
    r.add_argument("--tracker")
    r.add_argument("--change")
    r.add_argument("--phase")
    r.add_argument("--spec")
    r.add_argument("--settings")
    r.add_argument("--base", default="main")
    r.add_argument("--root")
    st = sub.add_parser("status")
    st.add_argument("--stamp", required=True)
    o = ap.parse_args(argv)
    if o.cmd == "status":
        try:
            print(json.dumps(Run(o.stamp).data, indent=1, ensure_ascii=False))
        except Stop as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        return 0
    if o.change and not o.phase:
        print(json.dumps({"error": "no phase"}))
        return 1
    try:
        res = run_feature(o)
    except Stop as e:
        res = {"error": str(e)}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0 if res.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

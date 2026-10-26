"""The code host: merged PRs of a week with their files, CI runs.

A promotion PR (`develop → main`, `main → release`) bundles PRs already counted, so a PR whose head branch is itself
long-lived — the default branch, `release`, or the base of another merged PR of the week — is not counted. Files are
classed frontend / backend / tests / other by path; a PR is frontend or backend when that side has at least 70% of
the changed source lines, mixed otherwise, other when it touches no source.
Seam: code host = GitHub (`gh`). To use another host, rewrite gh_json, merged_prs and ci_runs.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import store

SIDE_SHARE = 0.7
LONG_LIVED = ("release",)
TEST_GLOBS = ("tests/*", "test/*", "*/tests/*", "*/test/*", "*/__tests__/*", "test_*", "*/test_*", "*_test.*",
              "*.test.*", "*.spec.*", "e2e/*", "*/e2e/*")
FRONTEND_EXT = (".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less", ".html")
FRONTEND_DIRS = ("web", "frontend", "ui", "client")
# lock files, build output and generated code: changed lines that nobody wrote
GENERATED_GLOBS = ("*.lock", "*-lock.json", "*-lock.yaml", "*.lockb", "go.sum", "*.min.js", "*.min.css", "*.map",
                   "dist/*", "*/dist/*", "build/*", "*/build/*", "*_pb2.py", "*.pb.go", "*.snap", "*/__snapshots__/*",
                   "*.generated.*")
SOURCE_EXT = (".py", ".ts", ".js", ".mjs", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".scala", ".sql",
              ".sh", ".swift", ".c", ".cc", ".cpp", ".h")


@dataclass
class Rules:
    frontend: list[str] = field(default_factory=list)  # project globs, checked before the defaults
    backend: list[str] = field(default_factory=list)

    @classmethod
    def for_project(cls, checkout: Path) -> "Rules":
        env = store.read_env(checkout / ".claude/factory/analytics.env")
        return cls(env.get("ANALYTICS_FRONTEND", "").split(), env.get("ANALYTICS_BACKEND", "").split())


@dataclass
class PR:
    repo: str
    number: int
    head: str
    base: str
    merged_at: str
    lines: dict[str, int]
    cls: str


def matches(path: str, globs) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def classify(path: str, rules: Rules) -> str:
    if matches(path, GENERATED_GLOBS):
        return "generated"
    if matches(path, rules.frontend):
        return "frontend"
    if matches(path, rules.backend):
        return "backend"
    if matches(path, TEST_GLOBS):
        return "tests"
    p = PurePosixPath(path)
    if p.suffix in FRONTEND_EXT or (p.parts and p.parts[0] in FRONTEND_DIRS and p.suffix in SOURCE_EXT):
        return "frontend"
    return "backend" if p.suffix in SOURCE_EXT else "other"


def pr_class(lines: dict[str, int]) -> str:
    fe, be = lines.get("frontend", 0), lines.get("backend", 0)
    if fe + be == 0:
        return "other"
    if fe >= SIDE_SHARE * (fe + be):
        return "frontend"
    if be >= SIDE_SHARE * (fe + be):
        return "backend"
    return "mixed"


def gh_json(args: list[str]):
    """`gh <args>` parsed as JSON, or None when gh is missing, fails or prints no JSON."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def git_origin(checkout: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(checkout), "remote", "get-url", "origin"], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_of(checkout: Path) -> str | None:
    url = git_origin(checkout)
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url or "")
    return m.group(1) if m else None


def week_range(week: str) -> str:
    start, end = store.week_bounds(week)
    return f"{start:%Y-%m-%dT%H:%M:%SZ}..{end:%Y-%m-%dT%H:%M:%SZ}"


def merged_prs(repo: str, week: str, rules: Rules) -> list[PR] | None:
    info = gh_json(["repo", "view", repo, "--json", "defaultBranchRef"])
    if not isinstance(info, dict):
        return None
    default = (info.get("defaultBranchRef") or {}).get("name") or "main"
    data = gh_json(["pr", "list", "-R", repo, "--state", "merged", "--search", f"merged:{week_range(week)}",
                    "--limit", "1000", "--json", "number,headRefName,baseRefName,mergedAt,files"])
    if not isinstance(data, list):
        return None
    long_lived = {default, *LONG_LIVED} | {d.get("baseRefName") for d in data}
    out = []
    for d in data:
        if d.get("headRefName") in long_lived:
            continue
        lines = {"frontend": 0, "backend": 0, "tests": 0, "other": 0}
        for f in d.get("files") or []:
            cls = classify(f.get("path", ""), rules)
            if cls != "generated":
                lines[cls] += int(f.get("additions") or 0) + int(f.get("deletions") or 0)
        out.append(PR(repo, int(d["number"]), d.get("headRefName", ""), d.get("baseRefName", ""),
                      d.get("mergedAt", ""), lines, pr_class(lines)))
    return sorted(out, key=lambda p: p.number)


def ci_runs(repo: str, week: str) -> dict | None:
    data = gh_json(["run", "list", "-R", repo, "--created", week_range(week), "--limit", "1000",
                    "--json", "startedAt,updatedAt,status"])
    if not isinstance(data, list):
        return None
    minutes = 0.0
    for r in data:
        if r.get("status") == "completed" and r.get("startedAt") and r.get("updatedAt"):
            minutes += (store.parse_ts(r["updatedAt"]) - store.parse_ts(r["startedAt"])).total_seconds() / 60
    return {"runs": len(data), "minutes": round(minutes, 1)}

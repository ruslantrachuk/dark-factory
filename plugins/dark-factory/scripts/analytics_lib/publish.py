"""Publication: the rendered weeks on a branch of the target repository and a draft PR for the owner to merge.

Writes analytics/<week>.md, analytics/data/<week>.json and analytics/SUMMARY.md in a temporary worktree cut from the
remote default branch (or from the branch of an analytics PR still open, so the weeks pile up in one PR), commits,
pushes that branch and opens a draft PR. Never merges, never pushes the default branch. The leak check runs on every
rendered file first; a hit writes nothing and exits 1.
Seam: code host = GitHub (`gh pr list`, `gh pr create`). To use another host, rewrite open_pr and create_pr.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import render

BRANCH_PREFIX = "chore/analytics-"


def run(repo: Path, *args: str) -> str:
    return subprocess.run(args, cwd=repo, check=True, capture_output=True, text=True, timeout=300).stdout


def rendered_files(weeks: list[dict], alias: dict[str, str]) -> dict[str, str]:
    files = {}
    for d in sorted(weeks, key=lambda d: d["week"]):
        md, anon = render.render_week(d, alias)
        files[f"analytics/{d['week']}.md"] = md + "\n"
        files[f"analytics/data/{d['week']}.json"] = json.dumps(anon, indent=1, sort_keys=True) + "\n"
    files["analytics/SUMMARY.md"] = render.render_summary(weeks, alias) + "\n"
    return files


def default_branch(repo: Path) -> str:
    try:
        out = run(repo, "git", "ls-remote", "--symref", "origin", "HEAD")
    except subprocess.CalledProcessError:
        return "main"
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split()[1].removeprefix("refs/heads/")
    return "main"


def open_pr(repo: Path) -> str | None:
    """The head branch of an open analytics PR, if any."""
    try:
        data = json.loads(run(repo, "gh", "pr", "list", "--state", "open", "--search", f"head:{BRANCH_PREFIX}",
                              "--json", "number,headRefName") or "[]")
    except (subprocess.CalledProcessError, ValueError):
        return None
    heads = sorted(p.get("headRefName", "") for p in data if p.get("headRefName", "").startswith(BRANCH_PREFIX))
    return heads[-1] if heads else None


def pr_body(weeks: list[dict], alias: dict[str, str]) -> str:
    last = sorted(weeks, key=lambda d: d["week"])[-1]
    anon = render.anonymise(last, alias)
    P = anon["projects"].values()
    kinds = {k: sum(render.total(p["tokens"].get(k)) for p in P) for k in render.KINDS}
    whole = sum(kinds.values())
    prs = render.known(sum(len(p["prs"] or []) for p in P), list(P), "prs")
    events = render.week_events(anon)
    return "\n".join([
        "## Done",
        f"- Factory numbers up to {last['week']}{'' if last['final'] else ' (partial week)'}: "
        f"{render.fmt(whole)} tokens, " + ", ".join(f"{render.KIND_LABEL[k]} {render.pct(v, whole)}"
                                                    for k, v in kinds.items()) + f"; {prs} merged PRs.",
        f"- What changed this week: {'; '.join(events) or 'nothing new'}.",
        "",
        "## Decisions",
        "- Written by the weekly analytics timer from the server's store; projects are letters, the leak check passed.",
        "- Approximate, as each weekly file says: the On-call share, tokens per PR, test cost inside sessions.",
        "",
        "## Open questions",
        "- None. Review the numbers and merge with scripts/merge-feature.sh.",
    ])


def publish(repo: Path, weeks: list[dict], alias: dict[str, str], terms: set[str], dry: bool) -> int:
    if not weeks:
        print("✗ nothing collected yet: run `analytics.py collect` first", file=sys.stderr)
        return 1
    files = rendered_files(weeks, alias)
    leaks = render.leak_check(files, terms)
    if leaks:
        for name, term in leaks:
            print(f"✗ leak check: {name} contains {term!r} — nothing written", file=sys.stderr)
        return 1
    base = default_branch(repo)
    reuse = open_pr(repo)
    branch = reuse or BRANCH_PREFIX + sorted(d["week"] for d in weeks)[-1]
    if branch == base:
        print(f"✗ refusing to publish onto the default branch {base}", file=sys.stderr)
        return 1
    if dry:
        print(f"would write on {branch} ({'the open analytics PR' if reuse else 'a new draft PR into ' + base}):")
        for name in files:
            print(f"  {name}")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="df-analytics-"))
    work = tmp / "wt"
    try:
        run(repo, "git", "fetch", "-q", "origin", base, *([branch] if reuse else []))
        run(repo, "git", "worktree", "add", "-q", "-B", branch, str(work), f"origin/{branch if reuse else base}")
        for name, text in files.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        run(work, "git", "add", "analytics")
        if not run(work, "git", "status", "--porcelain", "analytics").strip():
            print(f"nothing new for {branch}")
            return 0
        week = sorted(d["week"] for d in weeks)[-1]
        run(work, "git", "commit", "-q", "-m", f"chore(analytics): factory numbers up to {week}")
        run(work, "git", "push", "-q", "-u", "origin", f"{branch}:{branch}")
        if reuse:  # the description stays current with the weeks it now carries
            run(work, "gh", "pr", "edit", branch, "--title", f"chore(analytics): factory numbers up to {week}",
                "--body", pr_body(weeks, alias))
            print(f"added to the open analytics PR ({branch})")
        else:
            url = run(work, "gh", "pr", "create", "--draft", "--base", base, "--head", branch,
                      "--title", f"chore(analytics): factory numbers up to {week}", "--body", pr_body(weeks, alias))
            print(f"opened {url.strip()}")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"✗ {' '.join(e.cmd[:3])}: {(e.stderr or e.stdout or '').strip()[-300:]}", file=sys.stderr)
        return 1
    finally:
        if work.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=repo, capture_output=True)
        subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)

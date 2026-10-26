"""The published side: letters instead of repositories, the weekly report, the summary, the leak check.

Nothing here reads a transcript: it renders the server store. A repository gets a letter once and keeps it
(aliases.json in the store, never published); the canon is the one name shown ("canon"). Before anything is written
the leak check looks for every name the sources know — repository, checkout path, host, the owner's handles, a work
branch's slug — as a whole word in every rendered file.
"""
from __future__ import annotations

import json
import re
import socket
import string
from datetime import timedelta
from pathlib import Path

from . import codehost, store
from .transcripts import KINDS, SPLITS

KIND_LABEL = {"owner": "owner", "on_call": "On-call", "monitor": "monitor", "unattended": "unattended"}
SPLIT_LABEL = {"direct": "direct", "helpers": "helper subagents", "pipeline": "pipeline"}
CLASSES = ("backend", "frontend", "mixed", "other")
GENERIC = {"main", "master", "develop", "release", "head", "feat", "fix", "docs", "chore", "refactor", "home",
           "user", "users", "root", "projects", "tmp", "local", "github", "com", "origin", "claude", "worktrees",
           "work", "factory", "canon", "test", "tests", "app", "data", "analytics", "summary", "week", "opt", "srv",
           "code", "repos", "src"}
MIN_TERM = 4

READING_NOTES = """**How to read.** One ISO week (Monday to Sunday, UTC) of the factory's own work, counted from the server's
session transcripts and the code host without a model. Projects are letters; the same letter is the same project in
every week; *canon* is the public plugin repository. Tokens are input + cache write + cache read + output; cache reads
are most of every total (a long session re-reads its context each turn), so compare totals with each other, not with a
price list. Turns are counted by who started them: the owner, the On-call (a client or colleague in the chat),
the production monitor, or nothing human (scheduled runs, pipelines, messages between sessions). Approximate, and
said so: work the On-call handed to a development session in words is counted as the owner's; tokens per PR (a turn
belongs to the PR its session opened next, or whose branch it named); test cost inside sessions (the messages that
ran the tests, not the reading of their output). Sessions run in the cloud leave no transcript here and are not
counted."""


def letter(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = string.ascii_uppercase[r] + out
    return out


def aliases(repos: list[str], path: Path, canon: str | None, write: bool = True) -> dict[str, str]:
    known = json.loads(path.read_text()) if path.is_file() else {}
    used = len([v for v in known.values() if v != "canon"])
    for r in sorted(set(repos)):
        if r == canon:
            known[r] = "canon"
        elif r not in known:
            known[r] = letter(used)
            used += 1
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known, indent=1, sort_keys=True))
    return {r: known[r] for r in sorted(set(repos) | set(known))}


def total(t: dict | None) -> int:
    return sum((t or {}).values())


def fmt(n: float) -> str:
    n = float(n)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= size:
            return f"{n / size:.1f}{suffix}"
    return f"{n:.0f}" if n == int(n) else f"{n:.1f}"


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "—"


def table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def anonymise(data: dict, alias: dict[str, str]) -> dict:
    projects = {}
    for repo, p in data["projects"].items():
        q = {k: v for k, v in p.items() if k != "prs"}
        q["prs"] = None if p.get("prs") is None else [
            {k: v for k, v in pr.items() if k not in ("number", "head")} for pr in p["prs"]]
        projects[alias.get(repo, "?")] = q
    return {"week": data["week"], "collected_at": data["collected_at"], "final": data["final"],
            "projects": dict(sorted(projects.items())), "factory": data.get("factory", {})}


def week_title(week: str) -> str:
    start, end = store.week_bounds(week)
    return f"{week} ({start:%d %b} – {end - timedelta(days=1):%d %b %Y})"


def render_week(data: dict, alias: dict[str, str]) -> tuple[str, dict]:
    anon = anonymise(data, alias)
    w, P = anon["week"], anon["projects"]
    out = [f"# Factory analytics — {week_title(w)}", ""]
    if not anon["final"]:
        out += [f"_Partial week: collected {anon['collected_at']}._", ""]
    out += [READING_NOTES, ""]
    new = [k for k, p in P.items() if p.get("first_week") == w]
    if new:
        out += [f"Projects new this week: {', '.join(new)}.", ""]

    out += ["## Who drove the work", ""]
    rows = []
    for k, p in P.items():
        tot = sum(total(t) for t in p["tokens"].values())
        rows.append([k, *(f"{fmt(total(p['tokens'].get(x)))} ({p['turns'].get(x, 0)})" for x in KINDS), fmt(tot)])
    out += [table(["project", *(f"{KIND_LABEL[x]}: tokens (turns)" for x in KINDS), "total"], rows), ""]
    all_tok = {x: sum(total(p["tokens"].get(x)) for p in P.values()) for x in KINDS}
    whole = sum(all_tok.values())
    out += ["Share of tokens: " + ", ".join(f"{KIND_LABEL[x]} {pct(all_tok[x], whole)}" for x in KINDS) + ".", ""]

    out += ["## Pipeline against direct work", ""]
    rows = [[k, *(fmt(total(p["split"][s])) for s in SPLITS)] for k, p in P.items()]
    out += [table(["project", *(SPLIT_LABEL[s] for s in SPLITS)], rows), ""]
    prs = [pr for p in P.values() for pr in p["prs"] or []]
    costed = [pr for pr in prs if total(pr["tokens"])]
    piped = [total(pr["tokens"]) for pr in costed if pr["pipeline"]]
    plain = [total(pr["tokens"]) for pr in costed if not pr["pipeline"]]
    attributed = sum(total(pr["tokens"]) for pr in costed)
    rest = sum(total(p["unattributed"]) for p in P.values())
    out += [f"Merged PRs: {len(prs)}; with tokens traced to them: {len(costed)} "
            f"({pct(attributed, attributed + rest)} of the week's tokens). "
            f"Tokens per PR — with the pipeline: {median(piped)} (n={len(piped)}), "
            f"without: {median(plain)} (n={len(plain)}); medians.", ""]

    out += ["## Backend against frontend", ""]
    rows = []
    for k, p in P.items():
        if p["prs"] is None:
            rows.append([k, *(["not available"] * (len(CLASSES) + 2))])
            continue
        n = {c: sum(1 for pr in p["prs"] if pr["cls"] == c) for c in CLASSES}
        lines = {s: sum(pr["lines"].get(s, 0) for pr in p["prs"]) for s in ("backend", "frontend")}
        rows.append([k, *(n[c] for c in CLASSES), fmt(lines["backend"]), fmt(lines["frontend"])])
    out += [table(["project", "backend PRs", "frontend PRs", "mixed", "other", "backend lines", "frontend lines"],
                  rows), ""]
    by_cls = {c: [total(pr["tokens"]) for pr in costed if pr["cls"] == c] for c in CLASSES}
    out += ["Tokens per PR (median, traced PRs): " + ", ".join(f"{c} {median(v)}" for c, v in by_cls.items()) + ".",
            ""]

    out += ["## Cost of tests", ""]
    rows = []
    for k, p in P.items():
        ci = p.get("ci")
        rows.append([k, ci["runs"] if ci else "—", fmt(ci["minutes"]) if ci else "—", p["tests"]["calls"],
                     fmt(total(p["tests"]["tokens"]))])
    out += [table(["project", "CI runs", "CI minutes", "test commands in sessions", "their tokens (approx.)"], rows), ""]

    out += ["## The owner's friction", ""]
    rows = []
    for k, p in P.items():
        f = p["friction"]
        per = lambda n: f"{100 * n / f['prompts']:.1f}" if f["prompts"] else "—"  # noqa: E731
        rows.append([k, f["prompts"], f["swear"], f["interrupts"], f["rejected"],
                     per(f["swear"] + f["interrupts"] + f["rejected"])])
    out += [table(["project", "owner prompts", "with swearing", "interrupts", "rejected tool calls",
                   "friction per 100 prompts"], rows), ""]

    out += ["## Parts", ""]
    rows = [[k, ", ".join(f"{part} {date}" for part, date in sorted(p.get("parts", {}).items(), key=lambda x: x[1]))
             or "—", (p.get("pins") or [["", "—"]])[-1][1]] for k, p in P.items()]
    out += [table(["project", "parts (first added)", "plugin release pinned"], rows), ""]
    events = week_events(anon)
    if events:
        out += ["This week: " + "; ".join(events) + ".", ""]
    return "\n".join(out), anon


def median(values: list[int]) -> str:
    if not values:
        return "—"
    v = sorted(values)
    mid = len(v) // 2
    return fmt(v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2)


def in_week(date: str, week: str) -> bool:
    try:
        return store.iso_week(f"{date}T12:00:00Z") == week
    except ValueError:
        return False


def week_events(anon: dict) -> list[str]:
    w = anon["week"]
    ev = []
    for k, p in anon["projects"].items():
        if p.get("first_week") == w:
            ev.append(f"{k}: first week")
        ev += [f"{k}: {part}" for part, date in sorted(p.get("parts", {}).items()) if in_week(date, w)]
    f = anon.get("factory", {})
    ev += [f"plugin {tag}" for tag, date in sorted(f.get("releases", {}).items(), key=lambda x: x[1]) if in_week(date, w)]
    ev += [f"server: {part}" for part, date in sorted(f.get("server", {}).items()) if in_week(date, w)]
    return ev


def render_summary(weeks: list[dict], alias: dict[str, str]) -> str:
    anon = [anonymise(d, alias) for d in sorted(weeks, key=lambda d: d["week"])]
    out = ["# Factory analytics — summary", "",
           "Every week the factory counts its own work; one file per week in this directory, this page is the series. "
           "How each number is counted: the top of any weekly file.", ""]
    rows = []
    for a in anon:
        P = a["projects"].values()
        kinds = {x: sum(total(p["tokens"].get(x)) for p in P) for x in KINDS}
        whole = sum(kinds.values())
        prs = [pr for p in P for pr in p["prs"] or []]
        fr = {k: sum(p["friction"][k] for p in P) for k in ("prompts", "swear", "interrupts", "rejected")}
        ci = sum((p.get("ci") or {}).get("minutes", 0) for p in P)
        rows.append([a["week"] + ("" if a["final"] else " (partial)"), fmt(whole),
                     *(pct(kinds[x], whole) for x in KINDS), len(prs),
                     sum(1 for pr in prs if pr["cls"] == "backend"), sum(1 for pr in prs if pr["cls"] == "frontend"),
                     fmt(ci), fr["prompts"],
                     f"{100 * (fr['swear'] + fr['interrupts'] + fr['rejected']) / fr['prompts']:.1f}"
                     if fr["prompts"] else "—",
                     "; ".join(week_events(a)) or ""])
    out += [table(["week", "tokens", *(f"{KIND_LABEL[x]} share" for x in KINDS), "merged PRs", "backend",
                   "frontend", "CI minutes", "owner prompts", "friction / 100", "what changed"], rows), ""]
    first: dict[str, dict[str, str]] = {}
    for a in anon:
        for k, p in a["projects"].items():
            row = first.setdefault(k, {"first week": p.get("first_week") or a["week"]})
            for part, date in p.get("parts", {}).items():
                row[part] = store.iso_week(f"{date}T12:00:00Z")
    cols = sorted({c for r in first.values() for c in r if c != "first week"})
    out += ["## Parts", "", "The week each part first appeared in a project (installed, not necessarily in use).", "",
            table(["project", "first week", *cols], [[k, r["first week"], *(r.get(c, "—") for c in cols)]
                                                       for k, r in sorted(first.items())]), ""]
    rel = anon[-1].get("factory", {}).get("releases", {}) if anon else {}
    if rel:
        out += ["Plugin releases: " + ", ".join(f"{t} {d}" for t, d in sorted(rel.items(), key=lambda x: x[1])) + ".",
                ""]
    return "\n".join(out)


def clean_terms(terms: set[str]) -> set[str]:
    return {t.lower() for t in terms if t and len(t) >= MIN_TERM and t.lower() not in GENERIC}


def leak_terms(checkouts: list[Path], weeks: list[dict], settings: store.Settings, canon_repo: str | None = None
               ) -> set[str]:
    """Every name the sources know, except the canon's own."""
    terms: set[str] = set()
    for c in checkouts:
        terms |= {c.name, *c.parts[1:]}
        repo = codehost.repo_of(c)
        if repo:
            terms |= {repo, *repo.split("/")}
    for d in weeks:
        for repo, p in d.get("projects", {}).items():
            terms |= {repo, *repo.split("/")}
            for pr in p.get("prs") or []:
                head = pr.get("head") or ""
                if "/" in head:
                    terms.add(head.split("/", 1)[1])
    terms |= {socket.gethostname(), *settings.owner}
    if canon_repo:
        terms -= {canon_repo, canon_repo.split("/")[1]}
    return clean_terms(terms)


def leak_check(files: dict[str, str], terms: set[str]) -> list[tuple[str, str]]:
    found = []
    for name, text in files.items():
        for t in sorted(terms):
            if re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", text, re.I):
                found.append((name, t))
    return found

"""One week of numbers per repository, from every project of the server, into the server store.

A repository is the unit, not a checkout: a turn goes to the repository of the PR it led up to (work for the canon
done from another checkout is the canon's), otherwise to its checkout's own `origin`. Every transcript is read once
per run and bucketed by week.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from . import codehost, parts, store, transcripts
from .transcripts import KINDS, SPLITS, add, zero

UNIT_DIR = Path(os.environ.get("FLEET_UNIT_DIR", Path.home() / ".config/systemd/user"))


def weeks_between(first: str, last: str) -> list[str]:
    out, w = [], first
    while w <= last:
        out.append(w)
        w = store.next_week(w)
    return out


def weeks_to_collect(mode: str, oldest: str | None, current: str, stored: list[str]) -> list[str]:
    """`since-last`: the last stored week (it may have been partial) up to the current one, or everything when
    nothing is stored; `all`: the oldest week the transcripts hold up to the current one."""
    if mode == "since-last" and stored:
        return weeks_between(stored[-1], current)
    return weeks_between(oldest or current, current)


def checkout_turns(checkout: Path, settings: store.Settings, root: Path):
    return transcripts.read_project(store.transcript_dirs(checkout, root), settings)


def oldest_week(checkouts: list[Path], settings: store.Settings | None = None, root: Path = store.PROJECTS_ROOT
                ) -> str | None:
    starts = [t.start for c in checkouts for t in checkout_turns(c, settings or store.Settings(), root)[0]]
    return store.iso_week(min(starts)) if starts else None


def empty_repo(first_week: str | None) -> dict:
    return {"first_week": first_week, "turns": {}, "tokens": {}, "split": {s: zero() for s in SPLITS},
            "prs": [], "unattributed": zero(), "ci": None, "tests": {"calls": 0, "tokens": zero()},
            "friction": {"prompts": 0, "swear": 0, "interrupts": 0, "rejected": 0},
            "involvement": {"lengths": []}, "parts": {}, "pins": []}


def collect(weeks: list[str], checkouts: list[Path], settings: store.Settings, canon: Path | None = None,
            now: datetime | None = None, root: Path = store.PROJECTS_ROOT, save: bool = True, force: bool = False
            ) -> dict[str, dict]:
    """A stored final week is kept as it is unless `force`: its transcripts may have been cleaned up since."""
    now = now or datetime.now(timezone.utc)
    kept = {w: d for w in set(weeks) if not force and (d := store.load_week(w)) and d.get("final")}
    weeks = sorted(set(weeks) - set(kept))
    if not weeks:
        return kept
    # every turn of every checkout, with its home repository
    rows: list[tuple[transcripts.Turn, str, Path]] = []
    links: list[transcripts.PrLink] = []
    home: dict[str, Path] = {}
    for c in checkouts:
        repo = codehost.repo_of(c) or f"local/{c.name}"
        home.setdefault(repo, c)
        turns, ls = checkout_turns(c, settings, root)
        rows += [(t, repo, c) for t in turns]
        links += ls
    # the factory's own repositories: the checkouts' and the canon's; work on anyone else's stays home, unattributed
    canon_repo = codehost.repo_of(canon) if canon else None
    repos = sorted(set(home) | ({canon_repo} if canon_repo else set()))
    links = [l for l in links if l.repo in repos]
    # the code host, per repository and week
    prs: dict[tuple[str, str], list | None] = {}
    ci: dict[tuple[str, str], dict | None] = {}
    for repo in repos:
        rules = codehost.Rules.for_project(home[repo]) if repo in home else codehost.Rules()
        for w in weeks:
            prs[(repo, w)] = None if repo.startswith("local/") else codehost.merged_prs(repo, w, rules)
            ci[(repo, w)] = None if repo.startswith("local/") else codehost.ci_runs(repo, w)
    branches = {(p.repo, p.number): p.head for v in prs.values() for p in v or []}
    turns = [t for t, _, _ in rows]
    assigned = transcripts.assign(turns, links, branches)
    costs, _ = transcripts.attribute(turns, links, branches)
    first: dict[str, str] = {}
    for (t, repo, _), pr in zip(rows, assigned):
        r = pr[0] if pr else repo
        first[r] = min(first.get(r, "9999"), store.iso_week(t.start))
    previous = [store.load_week(w) for w in store.stored_weeks()]
    server_parts: dict[str, str] = {}
    for d in [*previous, None]:
        src = (d or {}).get("factory", {}).get("server", {}) if d else {}
        for k, v in src.items():
            server_parts[k] = min(server_parts.get(k, v), v)
    factory = parts.factory_parts(canon, UNIT_DIR)
    for k, v in factory.get("server", {}).items():
        server_parts[k] = min(server_parts.get(k, v), v)
    factory["server"] = server_parts
    for d in previous:  # a repository seen in an earlier run keeps its first week
        for r, p in (d or {}).get("projects", {}).items():
            if p.get("first_week"):
                first[r] = min(first.get(r, p["first_week"]), p["first_week"])
    project_parts = {repo: (parts.project_parts(c), parts.plugin_pins(c)) for repo, c in home.items()}

    out = {}
    for w in weeks:
        start, end = store.week_bounds(w)
        data = {"week": w, "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "final": now >= end,
                "projects": {}, "factory": factory}
        projects: dict[str, dict] = {}

        def entry(repo: str) -> dict:
            if repo not in projects:
                projects[repo] = empty_repo(first.get(repo))
                pp, pins = project_parts.get(repo, ({}, []))
                projects[repo].update(parts=pp, pins=pins)
            return projects[repo]

        for (t, repo, _), pr in zip(rows, assigned):
            if store.iso_week(t.start) != w:
                continue
            e = entry(pr[0] if pr else repo)
            e["turns"][t.kind] = e["turns"].get(t.kind, 0) + 1
            add(e["tokens"].setdefault(t.kind, zero()), t.total())
            for s in SPLITS:
                add(e["split"][s], t.tokens[s])
            if pr is None:
                add(e["unattributed"], t.total())
            e["tests"]["calls"] += t.test_calls
            add(e["tests"]["tokens"], t.test_tokens)
            f = e["friction"]
            f["prompts"] += t.typed
            f["swear"] += t.swear
            f["interrupts"] += t.interrupts
            f["rejected"] += t.rejected
            if t.typed:
                e["involvement"]["lengths"].append(t.prompt_chars)
        for repo in repos:
            week_prs = prs.get((repo, w))
            if repo not in projects and repo not in home and not week_prs:
                continue  # a repository the factory only touched in another week
            e = entry(repo)
            e["ci"] = ci.get((repo, w))
            if week_prs is None:
                e["prs"] = None
                continue
            e["prs"] = []
            for p in week_prs:
                cost = costs.get((p.repo, p.number))
                e["prs"].append({"number": p.number, "head": p.head, "cls": p.cls, "lines": p.lines,
                                 "tokens": cost.tokens if cost else zero(), "pipeline": bool(cost and cost.pipeline),
                                 "kind": cost.kind if cost else None})
        for repo, e in projects.items():
            e["involvement"]["lengths"].sort()
            e["tokens"] = {k: e["tokens"][k] for k in KINDS if k in e["tokens"]}
        data["projects"] = dict(sorted(projects.items()))
        if save:
            store.save_week(w, data)
        out[w] = data
    return {**kept, **out}

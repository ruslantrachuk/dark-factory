#!/usr/bin/env python3
"""Weekly numbers of how the factory works, for the owner and for publication.

Reads, on the server where it runs and without a model (no quota is spent):
  - the transcripts of every project in ~/.config/dark-factory/projects (~/.claude/projects/<dir>/**/*.jsonl): tokens
    by who drove the turn (owner, On-call, monitor, unattended), by pipeline / helper subagents / direct work, test
    runs inside sessions, the owner's friction (swearing, interrupts, rejected tool calls) — counts only;
  - the code host: merged PRs into the default branch with their files (backend / frontend / tests / other), CI runs;
  - git history: when each part of the factory (base, On-call, monitor, releases by tag, pipeline, fences) appeared.
One ISO week per file in the server store ($ANALYTICS_STATE, default ~/.local/state/dark-factory/analytics/), with
real names: the series outlives the 30-day transcript cleanup. Publication replaces every project with a letter,
refuses on a leaked name and opens a draft PR in the target repository; the owner merges it.

  analytics.py collect [--week 2026-W43 | --since-last | --all] [--force]   (default --since-last; a final week
                                                 already stored is kept unless --force)
  analytics.py report [--week W]                                 print one week's report, write nothing
  analytics.py publish --repo DIR [--dry-run]                    write analytics/ on a branch, open a draft PR

Settings, ~/.config/dark-factory/analytics.env: ANALYTICS_OWNER (the owner's system user and chat handles, space
separated; every other person counts as work via On-call), ANALYTICS_SWEAR (extra swear roots), ANALYTICS_TEST_CMDS
(extra test-command regexes). Per project, <project>/.claude/factory/analytics.env: ANALYTICS_FRONTEND,
ANALYTICS_BACKEND (path globs). The weekly run is df-fleet-analytics.timer (fleet.py provision, when fleet.env has
FLEET_ANALYTICS_REPO).
Seam: transcripts = Claude Code's local JSONL; code host = GitHub (`gh`). To use another tool, rewrite
analytics_lib/transcripts.py or analytics_lib/codehost.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--week")
    g.add_argument("--since-last", action="store_true")
    g.add_argument("--all", action="store_true")
    c.add_argument("--force", action="store_true", help="re-collect weeks already final (their transcripts may be gone)")
    c.add_argument("--canon", type=Path, help="a checkout of the plugin's repository, for its release dates")
    r = sub.add_parser("report")
    r.add_argument("--week")
    r.add_argument("--canon", type=Path, help="a checkout of the plugin's repository: shown as 'canon'")
    p = sub.add_parser("publish")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--canon", type=Path, help="the plugin's repository checkout, shown as 'canon' (default: --repo)")
    args = ap.parse_args(argv)
    if args.command == "collect":
        return cmd_collect(args)
    if args.command == "report":
        return cmd_report(args)
    return cmd_publish(args)


def cmd_publish(args) -> int:
    from analytics_lib import publish, render, store
    weeks = [d for d in (store.load_week(w) for w in store.stored_weeks()) if d]
    canon = canon_repo(args.canon or args.repo)
    repos = sorted({r for d in weeks for r in d["projects"]})
    alias = render.aliases(repos, store.state_dir() / "aliases.json", canon, write=not args.dry_run,
                           first=first_weeks(weeks))
    terms = render.leak_terms(store.load_checkouts(), weeks, store.load_settings(), canon)
    return publish.publish(args.repo, weeks, alias, terms, args.dry_run)


def first_weeks(weeks: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in weeks:
        for repo, p in d["projects"].items():
            w = p.get("first_week") or d["week"]
            out[repo] = min(out.get(repo, w), w)
    return out


def canon_repo(canon: Path | None) -> str | None:
    from analytics_lib import codehost
    return codehost.repo_of(canon) if canon else None


def cmd_report(args) -> int:
    from analytics_lib import render, store
    weeks = store.stored_weeks()
    week = args.week or (weeks[-1] if weeks else None)
    data = store.load_week(week) if week else None
    if not data:
        print(f"✗ no collected week{' ' + week if week else ''}: run `analytics.py collect` first", file=sys.stderr)
        return 1
    alias = render.aliases(list(data["projects"]), store.state_dir() / "aliases.json", canon_repo(args.canon),
                           write=False, first=first_weeks([data]))
    print(render.render_week(data, alias)[0])
    return 0


def cmd_collect(args) -> int:
    from datetime import datetime, timezone
    from analytics_lib import collect, store
    checkouts = [c for c in store.load_checkouts() if c.is_dir()]
    if not checkouts:
        print("✗ no projects: ~/.config/dark-factory/projects lists none that exist", file=sys.stderr)
        return 1
    settings = store.load_settings()
    settings.on_call_names = store.on_call_names(checkouts)
    current = store.iso_week(datetime.now(timezone.utc).isoformat())
    if args.week:
        store.week_bounds(args.week)  # refuses a malformed week
        weeks = [args.week]
    else:
        mode = "all" if args.all else "since-last"
        weeks = collect.weeks_to_collect(mode, collect.oldest_week(checkouts, settings), current, store.stored_weeks())
    if not settings.owner:
        print("! ANALYTICS_OWNER is empty (~/.config/dark-factory/analytics.env): every chat message counts as On-call",
              file=sys.stderr)
    done = collect.collect(weeks, checkouts, settings, canon=args.canon, force=args.force)
    for w, data in done.items():
        print(f"{w}: {len(data['projects'])} repositories{'' if data['final'] else ' (partial week)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

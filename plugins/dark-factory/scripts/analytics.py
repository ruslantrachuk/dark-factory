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

  analytics.py collect [--week 2026-W43 | --since-last | --all]   (default --since-last)
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
    c.add_argument("--canon", type=Path, help="a checkout of the plugin's repository, for its release dates")
    r = sub.add_parser("report")
    r.add_argument("--week")
    p = sub.add_parser("publish")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "collect":
        return cmd_collect(args)
    print(f"✗ {args.command}: not implemented yet", file=sys.stderr)
    return 2


def cmd_collect(args) -> int:
    from datetime import datetime, timezone
    from analytics_lib import collect, store
    checkouts = [c for c in store.load_checkouts() if c.is_dir()]
    if not checkouts:
        print("✗ no projects: ~/.config/dark-factory/projects lists none that exist", file=sys.stderr)
        return 1
    settings = store.load_settings()
    current = store.iso_week(datetime.now(timezone.utc).isoformat())
    if args.week:
        store.week_bounds(args.week)  # refuses a malformed week
        weeks = [args.week]
    else:
        mode = "all" if args.all else "since-last"
        weeks = collect.weeks_to_collect(mode, collect.oldest_week(checkouts, settings), current, store.stored_weeks())
    done = collect.collect(weeks, checkouts, settings, canon=args.canon)
    for w, data in done.items():
        print(f"{w}: {len(data['projects'])} repositories{'' if data['final'] else ' (partial week)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

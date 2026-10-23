#!/usr/bin/env python3
"""The "How to upgrade" part of a release's notes: the `## Upgrade` sections of the pull requests merged since the
previous release, in merge order. GitHub's generated notes list the pull requests; this adds what a live project or
the server must do after updating.

  python3 scripts/release_notes.py v<N-1> [<ref>]     (ref defaults to HEAD; needs gh for the PR descriptions)

Prints Markdown; a release with nothing to do prints "Nothing to do beyond the update." Check it by hand before
`gh release create` (CONTRIBUTING.md, "Versioning").
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

MERGE = re.compile(r"^Merge pull request #(\d+) ")
HEADING = re.compile(r"^##\s+Upgrade\s*$", re.I | re.M)


def upgrade_section(body: str) -> str:
    """The text under the description's `## Upgrade` heading, up to the next `## ` heading or the description's
    footer (a `---` rule, the "Generated with" line); empty when absent."""
    m = HEADING.search(body or "")
    if not m:
        return ""
    rest = body[m.end():]
    end = re.search(r"^(##\s|---\s*$|🤖 )", rest, re.M)
    text = (rest[:end.start()] if end else rest).strip()
    return "" if text.lower().rstrip(".") in ("", "none", "nothing", "-", "—") else text


def merged_prs(since: str, ref: str) -> list[int]:
    out = subprocess.run(["git", "log", "--merges", "--reverse", "--format=%s", f"{since}..{ref}"],
                         capture_output=True, text=True, check=True).stdout
    return [int(m.group(1)) for line in out.splitlines() if (m := MERGE.match(line))]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    since, ref = argv[0], (argv[1] if len(argv) > 1 else "HEAD")
    parts = []
    for n in merged_prs(since, ref):
        pr = json.loads(subprocess.run(["gh", "pr", "view", str(n), "--json", "title,body"],
                                       capture_output=True, text=True, check=True).stdout)
        text = upgrade_section(pr.get("body", ""))
        if text:
            parts.append(f"### {pr['title']} (#{n})\n\n{text}")
    print("## How to upgrade\n")
    print("Update a project with `/dark-factory:upgrade` (it reads these steps). Then, per change:\n")
    print("\n\n".join(parts) if parts else "Nothing to do beyond the update.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

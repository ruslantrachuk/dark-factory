#!/usr/bin/env python3
"""The "How to upgrade" part of a release's notes: the `## Upgrade` sections of the pull requests merged since the
previous release, in merge order. GitHub's generated notes list the pull requests; this adds what a live project or
the server must do after updating.

  python3 scripts/release_notes.py v<N-1> [<ref>]     (ref defaults to HEAD; needs gh for the PR descriptions)

Prints Markdown; a release with nothing to do prints "Nothing to do beyond the update." Check it by hand before
`gh release create` (CONTRIBUTING.md, "Versioning").

The notes are read by an agent (`/dark-factory:upgrade`), and a pull request's author can edit its title and
description at any time, after the merge too. So each one is taken as it stood when it was merged (GitHub keeps the
edits), and hidden text is cut out: HTML comments and invisible or direction-changing characters.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

MERGE = re.compile(r"^Merge pull request #(\d+) ")
HEADING = re.compile(r"^##\s+Upgrade\s*$", re.I | re.M)
COMMENT = re.compile(r"<!--.*?(-->|\Z)", re.S)
# zero-width and joiners, bidi embeddings, overrides and isolates, the word joiner family, the BOM, tag characters
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
QUERY = """query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) {
  pullRequest(number: $n) { title body mergedAt
    userContentEdits(first: 100) { nodes { editedAt diff } }
    timelineItems(first: 100, itemTypes: [RENAMED_TITLE_EVENT]) {
      nodes { ... on RenamedTitleEvent { createdAt previousTitle } } } } } }"""


def clean(text: str) -> str:
    """The text without HTML comments and invisible characters."""
    return INVISIBLE.sub("", COMMENT.sub("", text or ""))


def at_merge(pr: dict) -> dict:
    """Title and body as they were when the pull request was merged. `userContentEdits` holds every revision of the
    body (the first one is the original) with its time; a title renamed after the merge goes back to the title it had
    before that rename."""
    merged_at = pr.get("mergedAt") or ""
    body = pr.get("body") or ""
    revisions = [e for e in pr.get("userContentEdits", {}).get("nodes", []) if e.get("diff") is not None]
    before = [e for e in revisions if e["editedAt"] <= merged_at]
    if before:
        body = max(before, key=lambda e: e["editedAt"])["diff"]
    title = pr.get("title") or ""
    renames = sorted((e for e in pr.get("timelineItems", {}).get("nodes", []) if e.get("createdAt", "") > merged_at),
                     key=lambda e: e["createdAt"])
    if renames:
        title = renames[0]["previousTitle"]
    return {"title": title, "body": body}


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


def merged(since: str, ref: str) -> list[dict]:
    """The pull requests merged since `since`, in merge order: number, and title and body as merged."""
    repo = subprocess.run(["gh", "repo", "view", "--json", "owner,name"],
                          capture_output=True, text=True, check=True).stdout
    owner, name = json.loads(repo)["owner"]["login"], json.loads(repo)["name"]
    out = []
    for n in merged_prs(since, ref):
        raw = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
                              "-f", f"name={name}", "-F", f"n={n}"], capture_output=True, text=True, check=True).stdout
        out.append({"number": n, **at_merge(json.loads(raw)["data"]["repository"]["pullRequest"])})
    return out


def notes(prs: list[dict]) -> str:
    parts = [f"### {clean(pr['title']).strip()} (#{pr['number']})\n\n{text}" for pr in prs
             if (text := upgrade_section(clean(pr.get("body", ""))))]
    return ("## How to upgrade\n\n"
            "Update a project with `/dark-factory:upgrade` (it reads these steps). Then, per change:\n\n"
            + ("\n\n".join(parts) if parts else "Nothing to do beyond the update."))


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    print(notes(merged(argv[0], argv[1] if len(argv) > 1 else "HEAD")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""The release pull request, opened by .github/workflows/release-pr.yml: when the plugin changed since the last
release, bump the canon to the next one — plugin.json <N>.0.0, the template pins, the README status and the
getting-started pin — and write the pull request's description with the upgrade notes. Merging it is the release:
.github/workflows/release.yml then tags it.

  python3 scripts/release_pr.py              bump the files and print the next tag; print nothing when the plugin
                                             has not changed since the last release or main is already bumped
  python3 scripts/release_pr.py --body v<N>  the release pull request's description (needs gh)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = "plugins/dark-factory/.claude-plugin/plugin.json"
TAG = re.compile(r"v([1-9]\d*)")

# Every place that names the release, as (file, text with {n}); each must occur exactly once.
PINS = [
    (PLUGIN_JSON, '"version": "{n}.0.0"'),
    ("plugins/dark-factory/templates/base/.claude/settings.json", '"ref": "v{n}"'),
    ("plugins/dark-factory/templates/solo/.claude/settings.json", '"ref": "v{n}"'),
    ("plugins/dark-factory/templates/factory/.claude/settings.json", '"ref": "v{n}"'),
    ("README.md", "[v{n}](https://github.com/ruslantrachuk/dark-factory/releases)"),
    ("docs/getting-started.md", '`"ref": "v{n}"`'),
]


def git(*args: str, root: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def last_release(tags: list[str]) -> int | None:
    numbers = [int(m.group(1)) for t in tags if (m := TAG.fullmatch(t))]
    return max(numbers, default=None)


def version(root: Path = ROOT) -> int:
    return int(json.loads((root / PLUGIN_JSON).read_text())["version"].split(".")[0])


def bump(root: Path, old: int, new: int) -> None:
    for path, text in PINS:
        f = root / path
        s = f.read_text()
        before, after = text.format(n=old), text.format(n=new)
        if s.count(before) != 1:
            raise SystemExit(f"✗ {path}: expected {before} exactly once")
        f.write_text(s.replace(before, after))


def next_release(root: Path = ROOT) -> str | None:
    """Bump the files and return the next tag, or None: no release yet, the plugin unchanged since the last one, or
    main already bumped (its release pull request merged and not yet tagged)."""
    last = last_release(git("tag", "--list", "v*", root=root).stdout.split())
    if last is None or version(root) != last:
        return None
    if git("diff", "--quiet", f"v{last}", "HEAD", "--", "plugins/dark-factory", root=root).returncode == 0:
        return None
    bump(root, last, last + 1)
    return f"v{last + 1}"


def body(tag: str, prs: list[dict], notes: str) -> str:
    prev = f"v{int(tag[1:]) - 1}"
    listed = "\n".join(f"  - #{pr['number']} {pr['title']}" for pr in prs) or "  - (none found)"
    return f"""## Done
- Release {tag}: plugin.json, the template pins, README status, the getting-started pin.
- Pull requests since {prev}:
{listed}

## Decisions
- Merging this pull request is the release: `release.yml` tags the merge {tag}, creates the GitHub release with
  the notes below and moves the `release` branch.

## Open questions
- Read the upgrade steps below before merging.

{notes}
"""


def main(argv: list[str]) -> int:
    if argv[:1] == ["--body"] and len(argv) == 2 and TAG.fullmatch(argv[1]):
        sys.path.insert(0, str(ROOT / "scripts"))
        import release_notes
        prs = release_notes.merged(f"v{int(argv[1][1:]) - 1}", "HEAD")
        print(body(argv[1], prs, release_notes.notes(prs)))
        return 0
    if argv:
        print(__doc__.strip())
        return 2
    tag = next_release()
    if tag:
        print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

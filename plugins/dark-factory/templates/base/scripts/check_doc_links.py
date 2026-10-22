#!/usr/bin/env python3
"""Check relative links and images in docs/user-guide/.

Run from the project root: python3 scripts/check_doc_links.py [--root PATH]
Broken links — exit 1. No user guide yet — a message and exit 0: it is
started with the first UI feature (CLAUDE.md §Finishing a feature).

DOCUMENTATION_STANDARDS requires "no links to non-existent files", and without
this script the rule is only checked by eye during review.
"""

import argparse
import re
import sys
from pathlib import Path

LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
# A link inside an HTML comment is a stub, not a link (page template before the first screenshots)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
EXTERNAL = ("http://", "https://", "#", "mailto:")


def _target(raw: str) -> str:
    """Markdown link target without the optional title."""
    target = raw.strip()
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return target[1:end]
    return target.split(maxsplit=1)[0] if target else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Broken links in docs/user-guide/.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="project root (default: parent of scripts/)")
    root = parser.parse_args(argv).root.resolve()
    guide = root / "docs" / "user-guide"
    if not guide.is_dir():
        print("No user guide yet (docs/user-guide/) — nothing to check.")
        return 0

    broken = []
    for page in sorted(guide.rglob("*.md")):
        for raw in LINK.findall(COMMENT.sub("", page.read_text(encoding="utf-8"))):
            target = _target(raw)
            if target.startswith(EXTERNAL):
                continue
            path = target.split("#", 1)[0]
            if path and not (page.parent / path).resolve().exists():
                broken.append(f"{page.relative_to(root)} → {raw}")
    if broken:
        print("Broken links:")
        for line in broken:
            print(f"  ✗ {line}")
        return 1
    print("All links in docs/user-guide/ are alive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

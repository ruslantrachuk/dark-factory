"""The user guide is consistent with itself (docs/user-guide/).

Checks what silently drifts without a meta-test: a page unreachable from the
table of contents; a screenshot missing from the manifest or from disk; a file
re-shot by hand outside the generator (hash mismatch); a manifest without the
synthetic-data policy.

A rule in the standards does not hold without a check: the guide is required
before SHIPPED and is guarded by these tests. Screenshots are taken only by
`python -m tests.e2e.make_screenshots`, which also writes the manifest.

Unit: reads small, unchanging repository files and writes nothing.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "docs" / "user-guide"
MANIFEST = GUIDE / "screenshot-manifest.json"
TOC = GUIDE / "README.md"
POLICY = "synthetic_or_masked_only"
LINK = re.compile(r"(!?)\[[^\]]*\]\(([^)]+)\)")
EXTERNAL = ("http://", "https://", "#", "mailto:")
# A link inside an HTML comment is a stub, not a link (page template before the first screenshots)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

if not GUIDE.is_dir():
    pytest.skip(
        "no user guide yet — it is started with the first UI feature (CLAUDE.md §Finishing a feature)",
        allow_module_level=True,
    )


def _target(raw: str) -> str:
    """Markdown link target without the optional title and anchor."""
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1:target.index(">")]
    else:
        target = target.split(maxsplit=1)[0] if target else ""
    return target.split("#", 1)[0]


def _links(page: Path) -> list[tuple[bool, Path]]:
    """(is image, destination path) for every relative link on the page."""
    result = []
    for bang, raw in LINK.findall(COMMENT.sub("", page.read_text(encoding="utf-8"))):
        target = _target(raw)
        if not target or target.startswith(EXTERNAL):
            continue
        result.append((bool(bang), (page.parent / target).resolve()))
    return result


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_every_page_is_reachable_from_toc():
    """The table of contents is README.md; a section with its own index.md links further by itself."""
    pages = {p.resolve() for p in GUIDE.rglob("*.md")}
    reached, queue = {TOC.resolve()}, [TOC.resolve()]
    while queue:
        for is_image, target in _links(queue.pop()):
            if not is_image and target in pages and target not in reached:
                reached.add(target)
                queue.append(target)
    orphans = sorted(p.relative_to(GUIDE).as_posix() for p in pages - reached)
    assert orphans == [], "pages not linked from the README.md table of contents"


def test_every_page_image_is_in_manifest_and_on_disk():
    entries = set(_manifest()["images"])
    violations = []
    for page in sorted(GUIDE.rglob("*.md")):
        for is_image, target in _links(page):
            if not is_image:
                continue
            name = (target.relative_to(GUIDE.resolve()).as_posix()
                    if target.is_relative_to(GUIDE.resolve()) else str(target))
            if name not in entries:
                violations.append((page.name, name, "not in manifest"))
            if not target.is_file():
                violations.append((page.name, name, "no file"))
    assert violations == []


def test_every_screenshot_hash_matches_manifest():
    """A mismatch means the file was re-shot or edited by hand outside make_screenshots."""
    mismatches = []
    for name, digest in sorted(_manifest()["images"].items()):
        file = GUIDE / name
        if not file.is_file():
            mismatches.append((name, "no file"))
        elif hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            mismatches.append((name, "hash mismatch"))
    assert mismatches == []


def test_manifest_declares_synthetic_data_only():
    assert _manifest()["data_policy"] == POLICY

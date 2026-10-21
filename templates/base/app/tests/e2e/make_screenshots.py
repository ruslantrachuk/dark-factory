"""User-guide screenshot generator (docs/user-guide/images/).

NOT a test (name is not test_*). Run from app/: python -m tests.e2e.make_screenshots
Requires: the e2e dependency group and `playwright install chromium`.

Screenshots are never taken by hand: a manually captured frame is not
reproducible, pulls in live data and diverges from the screen after the first
layout change. Data on the frames is synthetic only: the stand is started by
the same code as the e2e scenarios (_stand.py), on a seed without real people
or locations.

After shooting, screenshot-manifest.json is rewritten in full from all png in
images/: the meta-test unit/test_user_guide.py checks the hashes, so a file
re-shot outside the generator is caught on the first run.
"""

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from ._stand import running_stand

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "user-guide"
IMAGES = GUIDE / "images"
MANIFEST = GUIDE / "screenshot-manifest.json"
VIEWPORT = {"width": 1280, "height": 800}


@dataclass(frozen=True)
class Scene:
    """One user-guide frame."""

    file: str  # relative to docs/user-guide/images/
    path: str  # URL path on the stand, from the root
    prepare: Callable[[Page], None] | None = None  # login, clicks before the frame


# <Project scenes: one per user-guide screen.> Logging in as a role goes into `prepare`.
SCENES: list[Scene] = [
    Scene(file="main-screen.png", path="/"),
]


def _shoot(page: Page, url: str, scene: Scene) -> None:
    page.goto(f"{url}{scene.path}")
    if scene.prepare is not None:
        scene.prepare(page)
    page.wait_for_load_state("networkidle")
    file = IMAGES / scene.file
    file.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(file), full_page=True)
    print(f"  ✓ {scene.file}")


def write_manifest() -> None:
    """Manifest of all png in images/: path relative to docs/user-guide → sha256."""
    images = {
        file.relative_to(GUIDE).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(IMAGES.rglob("*.png"))
    }
    MANIFEST.write_text(
        json.dumps(
            {"schema_version": 1, "data_policy": "synthetic_or_masked_only", "images": images},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"  ✓ {MANIFEST.name}: {len(images)} files")


def main() -> int:
    IMAGES.mkdir(parents=True, exist_ok=True)
    print("Shooting user-guide screenshots…")
    with running_stand() as url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport=VIEWPORT)
            for scene in SCENES:
                _shoot(page, url, scene)
        finally:
            browser.close()
    write_manifest()
    print(f"Done → {IMAGES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

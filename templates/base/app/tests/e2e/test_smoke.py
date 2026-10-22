"""First scenario of the e2e layer: the preview came up, the main page opened.

Exists from the project's first day so that the agent adds scenarios to an
existing layer instead of setting it up itself (CODING_STANDARDS: every screen
gets an e2e happy path).
"""

import re

from playwright.sync_api import Page, expect


def test_main_page_opens(page: Page, base_url: str):
    page.goto(base_url)
    # <Project> — the name in <title> or in the main screen's h1 heading
    expect(page).to_have_title(re.compile("<Project>"))

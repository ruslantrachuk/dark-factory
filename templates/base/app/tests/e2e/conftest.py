"""Stand for end-to-end scenarios.

The same stack that goes into the image is started (the command is in _stand.py);
the test never reaches outside: external systems are not configured on the stand,
and tests never touch someone else's live prod (CODING_STANDARDS §Test pyramid).

Seed data is relative to "today", not calendar dates: a seed with a fixed date
drifts out of date-window views (e.g. "this week") and the scenario starts failing
nightly; a timezone offset between local time and UTC adds a second source of drift.

There are no project imports here: the stand runs as a separate process.
"""

import pytest

from ._stand import running_stand


@pytest.fixture(scope="session")
def stand():
    """URL of the running stand — one per run, stopped at the end."""
    with running_stand() as url:
        yield url


@pytest.fixture(scope="session")
def base_url(stand) -> str:
    """Overrides pytest-playwright's built-in base_url: `page.goto("/")`
    in scenarios goes to the running stand, not to the address from the command line."""
    return stand

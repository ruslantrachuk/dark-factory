"""Shared test fixtures and test-pyramid layer marking.

A test's layer is its directory under app/tests (unit, integration, api, e2e):
the hook below sets the marker, nobody writes it by hand. The layout is guarded
by the meta-test unit/test_layers.py (CODING_STANDARDS §Test pyramid). A marker
set by hand drifts away from what the test actually spins up, and the pyramid
shares end up computed from the wrong numbers.

There are deliberately no project imports here: the template does not know the
project package. Project fixtures go in the section at the bottom.
"""

from importlib.util import find_spec
from pathlib import Path

import pytest

# End-to-end scenarios live in a separate dependency group. Without it the
# directory is not collected at all: otherwise a regular run fails on importing
# playwright, which must not be present in the per-PR environment.
# Both the directory itself and the files inside: without the first one pytest
# still enters app/tests/e2e and fails on importing the scenarios' conftest.
collect_ignore_glob = [] if find_spec("playwright") else ["e2e", "e2e/*"]

TESTS = Path(__file__).resolve().parent
LAYERS = {
    "unit": "pure logic — no database, file writes, network or client (app/tests/unit)",
    "integration": "service on a live dependency: database, files, local server (app/tests/integration)",
    "api": "HTTP through the test client (app/tests/api)",
    "e2e": "browser against a running stand, release gate (app/tests/e2e)",
}


def pytest_configure(config):
    """Layer markers are registered here, next to the hook that sets them:
    the conftest does not depend on whether the project's pytest config knows about layers."""
    for layer, meaning in LAYERS.items():
        config.addinivalue_line("markers", f"{layer}: {meaning}")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Layer = first directory under app/tests. tryfirst: the marker must be set
    before -m selection, otherwise `pytest -m unit` would not see a single test."""
    for item in items:
        path = item.path.resolve()
        if not path.is_relative_to(TESTS):
            continue
        layer = path.relative_to(TESTS).parts[0]
        if layer in LAYERS and not item.get_closest_marker(layer):
            item.add_marker(layer)


# --- project fixtures ---
#
# <Fill in for the project.> Example: every test gets its own temporary
# database with migrations applied — a database shared between tests hides
# execution-order bugs.
#
#     @pytest.fixture
#     def settings(tmp_path) -> Settings:
#         return Settings(database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}")
#
#     @pytest.fixture
#     def migrated(settings) -> Settings:
#         command.upgrade(alembic_config(settings.database_url), "head")
#         return settings
#
#     @pytest.fixture
#     def client(migrated) -> TestClient:
#         return TestClient(create_app(migrated), raise_server_exceptions=False)
#
# Fixtures that spin up a database, files or a client must be added to
# FORBIDDEN_IN_UNIT (unit/test_layers.py) — otherwise unit silently turns into integration.
#
# Tokens of external systems from the shell are removed with an autouse fixture
# via monkeypatch.delenv: tests never touch someone else's live prod.

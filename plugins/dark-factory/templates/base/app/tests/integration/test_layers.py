"""Layout of tests across the test-pyramid layers (CODING_STANDARDS §Test pyramid).

Layer = directory; conftest sets the marker from the path. The meta-test collects
a real run in a child pytest and checks: every test has exactly one layer, and it
matches its directory; unit tests do not spin up a database, files or a client.
The production hook is checked, not a copy of it.

The inventory is written to a temporary directory from the `tempfile` module, not
to the tmp_path_factory fixture: otherwise the meta-test itself would break the
rule it guards and would need an exception for itself.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP_DIR = ROOT / "app"
TESTS = APP_DIR / "tests"
LAYERS = ("unit", "integration", "api", "e2e")
# Built-in file-writing fixtures — always; plus project fixtures that spin up
# a database, a client or a preview (e.g. settings, migrated, client)
FORBIDDEN_IN_UNIT = frozenset({
    "tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory",
    # <project fixtures: database, client — fill in>
})

PLUGIN = '''
import json
def pytest_collection_finish(session):
    rows = [
        {"id": i.nodeid, "path": str(i.path),
         "marks": sorted({m.name for m in i.iter_markers()}),
         "fixtures": sorted(getattr(i, "fixturenames", ()))}
        for i in session.items
    ]
    with open(session.config.getoption("--layers-out"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
def pytest_addoption(parser):
    parser.addoption("--layers-out")
'''


@pytest.fixture(scope="module")
def inventory() -> list[dict]:
    """All project tests with markers and fixtures — after the conftest hook.

    `-m ""` clears the addopts filter: e2e tests get into the inventory too. If
    playwright is not installed, conftest excludes the e2e directory entirely —
    the inventory is without them. The child pytest runs from app/ with an explicit
    `tests`: so it does not depend on where the project keeps its pytest config
    and which rootdir results.
    """
    with tempfile.TemporaryDirectory(prefix="layers-") as tmp:
        directory = Path(tmp)
        (directory / "layers_plugin.py").write_text(PLUGIN, encoding="utf-8")
        out = directory / "inventory.json"
        pythonpath = os.pathsep.join(p for p in (str(directory), os.environ.get("PYTHONPATH", "")) if p)
        result = subprocess.run(  # noqa: S603 — own interpreter, own arguments
            [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-m", "",
             "-p", "layers_plugin", f"--layers-out={out}", "-p", "no:cacheprovider"],
            cwd=APP_DIR, capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPATH": pythonpath},
        )
        if result.returncode:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-60:])
            pytest.fail(f"child test collection failed (code {result.returncode}):\n{tail}")
        rows = json.loads(out.read_text(encoding="utf-8"))
    assert rows, "inventory is empty — the child pytest collected nothing"
    return rows


def _layer_dir(row: dict) -> str:
    """First directory under app/tests. Computed from the file path, not the nodeid:
    the nodeid is relative to rootdir, which depends on where the pytest config lives."""
    path = Path(row["path"]).resolve()
    if not path.is_relative_to(TESTS):
        return ""
    parts = path.relative_to(TESTS).parts
    return parts[0] if len(parts) > 1 else ""


def test_every_test_lives_in_a_layer_directory(inventory):
    strays = [r["id"] for r in inventory if _layer_dir(r) not in LAYERS]
    assert strays == []


def test_test_has_exactly_one_layer_and_it_is_its_directory(inventory):
    wrong = [
        (r["id"], [m for m in r["marks"] if m in LAYERS]) for r in inventory
        if [m for m in r["marks"] if m in LAYERS] != [_layer_dir(r)]
    ]
    assert wrong == []


def test_unit_does_not_spin_up_database_files_or_client(inventory):
    offenders = [
        (r["id"], sorted(FORBIDDEN_IN_UNIT & set(r["fixtures"])))
        for r in inventory
        if _layer_dir(r) == "unit" and FORBIDDEN_IN_UNIT & set(r["fixtures"])
    ]
    assert offenders == []

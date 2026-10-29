#!/usr/bin/env python3
"""Test pyramid measurement: pytest by layer markers, Vitest by file extension.

Run from the project root with the project interpreter (venv app/.venv):
    app/.venv/bin/python scripts/pyramid.py [--root PATH] [--ratchet] [--write-baseline] [--json]

pytest: unit, integration, api — app/tests/conftest.py sets the marker from the
directory. e2e is counted separately and is not part of the shares: it is the release gate.
Vitest — only if app/frontend/package.json exists: *.test.tsx / *.test.jsx (and
.spec.) — component (screen render), any other JS/TS test file (.ts, .js, .mjs,
.mts, …) — unit (pure functions). Vitest is counted from
its own test list (`vitest list --json`), not by text search: it expands
it.each, nested describe blocks and skips by itself.
Shares — CODING_STANDARDS §Test pyramid.

The project declares its pyramid profile on deployment (MANIFEST): unit-first —
unit as the base (default), contract-first — integration as the base (the risk is
at the seams with a live dependency: connection strings, special characters in
passwords, a test database that differs from the production one).
--write-baseline --profile … writes the profile, the base layer and its share to
.harness/pyramid-baseline.json; --ratchet checks the share of the DECLARED base:
it must not drop by more than half a point. A ratchet, not a threshold: each project
has its own starting point, what matters is the direction (with integration
outweighing unit, new rules drift by inertia into tests that go through the database).

Fail Fast: a failed collection (import error, broken module) is not zero tests
but a stop with a reason and a non-zero exit code, otherwise the shares silently lie.
"""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# pytest: "no tests left after selection" is a legitimate zero (e2e without playwright)
NOTHING_COLLECTED = 5
PYTEST_LAYERS = ("unit", "integration", "api")
# A test file with a JSX extension renders a screen; any other JS/TS one checks pure functions
VITEST_FILE = re.compile(r"\.(?:test|spec)\.[cm]?[jt]s(x)?$")
# Half a point: noise from a removed duplicate must not trip the ratchet
TOLERANCE = 0.005
BASELINE = Path(".harness") / "pyramid-baseline.json"
# Profile → base layer whose share the ratchet holds
PROFILES = {"unit-first": "unit", "contract-first": "integration"}
DEFAULT_PROFILE = "unit-first"


def _stop(what: str, result: subprocess.CompletedProcess) -> None:
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-30:])
    sys.exit(f"measurement stopped: {what} (code {result.returncode})\n{tail}")


def pytest_layer(root: Path, marker: str) -> int:
    """How many tests pytest collects for a marker (e2e — if playwright is installed).

    The same interpreter that started the script, not `uv run`: the caller
    chooses the project venv, and the measurement does not pull in a package manager.
    """
    result = subprocess.run(  # noqa: S603 — own arguments, not user input
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q",
         "-p", "no:cacheprovider", "-m", marker],
        cwd=root / "app", capture_output=True, text=True, check=False,
    )
    lines = result.stdout.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.returncode not in (0, NOTHING_COLLECTED) or "error" in last.lower():
        _stop(f"pytest failed to collect layer {marker}", result)
    m = re.match(r"(\d+)(?:/\d+)? tests? collected", last)
    if m:
        return int(m.group(1))
    if result.returncode == NOTHING_COLLECTED:
        return 0
    _stop(f"could not parse pytest summary for layer {marker}: {last!r}", result)
    raise AssertionError("unreachable")


def vitest(root: Path) -> Counter:
    """Vitest tests by layer — by test file extension; no frontend — empty."""
    frontend = root / "app" / "frontend"
    layers: Counter = Counter()
    if not (frontend / "package.json").is_file():
        return layers
    result = subprocess.run(  # noqa: S603 — own arguments, not user input
        ["npx", "vitest", "list", "--json"],  # noqa: S607
        cwd=frontend, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        _stop("vitest list failed (no node_modules — run npm ci in app/frontend)", result)
    try:
        tests = json.loads(result.stdout)
    except json.JSONDecodeError:
        _stop("vitest list did not return JSON", result)
    for test in tests:
        file = test["file"]
        m = VITEST_FILE.search(file)
        if m is None:
            sys.exit(f"measurement stopped: Vitest test file without a known extension: {file}")
        layers["component" if m.group(1) else "unit"] += 1
    return layers


def measure(root: Path) -> dict:
    frontend = vitest(root)
    layers = {
        "unit": pytest_layer(root, "unit") + frontend["unit"],
        "integration": pytest_layer(root, "integration"),
        "api": pytest_layer(root, "api"),
        "component": frontend["component"],
    }
    total = sum(layers.values())
    if not total:
        sys.exit("measurement stopped: no tests in the shares — nothing to measure")
    return {
        "layers": layers,
        "total": total,
        "shares": {name: n / total for name, n in layers.items()},
        "e2e": pytest_layer(root, "e2e"),
    }


def print_report(result: dict) -> None:
    for name, n in result["layers"].items():
        print(f"{name:<12} {n:>5}  {n * 100 / result['total']:5.1f} %")
    print(f"{'total':<12} {result['total']:>5}")
    print(f"{'e2e':<12} {result['e2e']:>5}  (release gate, not part of the shares)")


def write_baseline(root: Path, result: dict, profile: str) -> Path:
    layer = PROFILES[profile]
    path = root / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"profile": profile, "layer": layer, "share": round(result["shares"][layer], 4),
             "total": result["total"], "measured_at": dt.date.today().isoformat()},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return path


def declared_profile(root: Path) -> str:
    path = root / BASELINE
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")).get("profile", DEFAULT_PROFILE)
    return DEFAULT_PROFILE


HINT = {
    "unit": "a new rule test goes to unit; a rule tested through the database — extract it into *_rules",
    "integration": "a new seam test runs on the live dependency, not on a mock",
}


def ratchet(root: Path, result: dict, out=sys.stdout) -> int:
    path = root / BASELINE
    if not path.is_file():
        print(f"warning: no {BASELINE} — the ratchet does not check; write it with --write-baseline", file=out)
        return 0
    baseline = json.loads(path.read_text(encoding="utf-8"))
    # Old format (unit_share only) is read as unit-first
    layer = baseline.get("layer", "unit")
    profile = baseline.get("profile", DEFAULT_PROFILE)
    before = float(baseline.get("share", baseline.get("unit_share", 0.0)))
    now = result["shares"][layer]
    if now < before - TOLERANCE:
        print(
            f"{layer} share dropped: was {before * 100:.1f} %, now {now * 100:.1f} % — "
            f"profile {profile} (CODING_STANDARDS §Test pyramid): {HINT[layer]}",
            file=sys.stderr,
        )
        return 1
    print(f"ratchet ({profile}): {layer} share {now * 100:.1f} % (baseline {before * 100:.1f} %) — holds", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test pyramid layer shares.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: current directory)")
    parser.add_argument("--ratchet", action="store_true", help="check the profile's base share against .harness/pyramid-baseline.json")
    parser.add_argument("--write-baseline", action="store_true", help="write the current base share as the baseline")
    parser.add_argument("--profile", choices=sorted(PROFILES),
                        help="pyramid profile for --write-baseline (default: the baseline's own, else unit-first)")
    parser.add_argument("--json", action="store_true", help="result as a single JSON instead of a table")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / "app" / "tests").is_dir():
        sys.exit(f"measurement stopped: no {root / 'app' / 'tests'} — run from the project root or with --root")

    result = measure(root)
    # with --json stdout carries only JSON: explanations go to stderr
    out = sys.stderr if args.json else sys.stdout
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print_report(result)
    if args.write_baseline:
        # Raising the bar keeps the declared profile: a contract-first project must not turn unit-first by omission
        profile = args.profile or declared_profile(root)
        print(f"baseline written ({profile}): {write_baseline(root, result, profile)}", file=out)
    if args.ratchet:
        return ratchet(root, result, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

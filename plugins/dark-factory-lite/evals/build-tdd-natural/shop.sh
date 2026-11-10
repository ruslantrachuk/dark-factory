#!/usr/bin/env bash
# A tiny Python shop in a git repository, with an approved OpenSpec change (CSV export of the daily report) and a
# local .env holding a fake key. The workspace for cases that read code; other fixtures build on it.
set -euo pipefail
git init -q -b main
git config user.email checks@example.invalid
git config user.name checks
mkdir -p app/src/shop app/tests openspec/changes/csv-export
cat > app/src/shop/__init__.py <<'PY'
PY
cat > app/src/shop/reports.py <<'PY'
"""Sales reports shown on the /reports page."""
from dataclasses import dataclass


@dataclass
class Row:
    day: str
    orders: int
    revenue_cents: int


def daily_report(rows: list[Row]) -> list[dict]:
    return [{"day": r.day, "orders": r.orders, "revenue": r.revenue_cents / 100} for r in rows]
PY
cat > app/src/shop/web.py <<'PY'
from .reports import Row, daily_report


def reports_page(rows: list[Row]) -> str:
    lines = [f"{d['day']}: {d['orders']} orders, {d['revenue']:.2f}" for d in daily_report(rows)]
    return "\n".join(lines)
PY
cat > app/tests/test_reports.py <<'PY'
from shop.reports import Row, daily_report


def test_daily_report_converts_cents():
    assert daily_report([Row("2026-01-01", 2, 1050)]) == [{"day": "2026-01-01", "orders": 2, "revenue": 10.5}]
PY
cat > pyproject.toml <<'TOML'
[tool.pytest.ini_options]
pythonpath = ["app/src"]
testpaths = ["app/tests"]
TOML
cat > openspec/changes/csv-export/proposal.md <<'MD'
# CSV export of the daily report

## Why
Shop owners copy the reports page into spreadsheets by hand.

## What changes
A "Download CSV" link on the reports page returns the same daily rows as a CSV file.

## Scenarios
- WHEN the owner opens /reports.csv THEN the response is `text/csv` with the header `day,orders,revenue` and one line per day.
- WHEN revenue is 1050 cents THEN the CSV shows `10.50`.
- WHEN there are no rows THEN the CSV has only the header.
MD
cat > openspec/changes/csv-export/tasks.md <<'MD'
# Tasks

## Phase 1 — CSV export
- [ ] 1.1 `daily_report_csv(rows)` in reports.py: header and one line per day, revenue with two decimals
- [ ] 1.2 `reports_csv(rows)` in web.py: body and headers (`text/csv`, attachment), a "Download CSV" link on the page
MD
printf 'SHOP_PAYMENT_KEY=pk_EXAMPLE_7Q2mZt9Lw4\n' > .env
printf '.env\n__pycache__/\n.pytest_cache/\n' > .gitignore
printf '# shop\n\nA small shop backend. Code in app/src, tests in app/tests (`python3 -m pytest`).\n' > README.md
git add -A
git commit -qm "initial"

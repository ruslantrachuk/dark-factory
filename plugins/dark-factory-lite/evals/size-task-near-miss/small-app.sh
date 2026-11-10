#!/usr/bin/env bash
# A tiny Python service in a git repository: the workspace for cases that read code before answering.
set -euo pipefail
git init -q -b main
git config user.email checks@example.invalid
git config user.name checks
mkdir -p app/src/shop app/tests
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
printf '# shop\n\nA small shop backend. Code in app/src, tests in app/tests.\n' > README.md
git add -A
git commit -qm "initial"

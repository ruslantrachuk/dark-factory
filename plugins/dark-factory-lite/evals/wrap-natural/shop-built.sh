#!/usr/bin/env bash
# The shop with slice 1.1 of the CSV export built on a work branch: the function and its test, passing, not yet
# committed.
set -euo pipefail
. "$(dirname "$0")/shop.sh"
git checkout -q -b feat/csv-export
cat >> app/src/shop/reports.py <<'PY'


def daily_report_csv(rows: list[Row]) -> str:
    lines = ["day,orders,revenue"]
    lines += [f"{r.day},{r.orders},{r.revenue_cents / 100:.2f}" for r in rows]
    return "\n".join(lines) + "\n"
PY
cat > app/tests/test_reports_csv.py <<'PY'
from shop.reports import Row, daily_report_csv


def test_csv_has_header_and_two_decimals():
    assert daily_report_csv([Row("2026-01-01", 2, 1050)]) == "day,orders,revenue\n2026-01-01,2,10.50\n"


def test_csv_without_rows_is_only_the_header():
    assert daily_report_csv([]) == "day,orders,revenue\n"
PY

#!/usr/bin/env bash
# The shop with phase 1 of the CSV export built, committed and green on its work branch: ready to be wrapped up.
set -euo pipefail
. "$(dirname "$0")/shop-built.sh"
git add -A
git commit -qm "feat(reports): daily report as CSV with two-decimal revenue"
cat >> app/src/shop/web.py <<'PY'


def reports_csv(rows: list[Row]) -> tuple[str, dict]:
    from .reports import daily_report_csv
    headers = {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=reports.csv"}
    return daily_report_csv(rows), headers
PY
cat > app/tests/test_web_csv.py <<'PY'
from shop.reports import Row
from shop.web import reports_csv


def test_reports_csv_is_an_attachment():
    body, headers = reports_csv([Row("2026-01-01", 1, 100)])
    assert headers["Content-Type"] == "text/csv"
    assert body.startswith("day,orders,revenue\n")
PY
git add -A
git commit -qm "feat(web): /reports.csv download with CSV headers"
sed -i 's/- \[ \] 1\./- [x] 1./' openspec/changes/csv-export/tasks.md

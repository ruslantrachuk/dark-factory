"""Everything the loop knows about the project is in this file: fill it in during setup (<…> placeholders).

The other module files are shared and change only through the canon. The other project-specific part is the
catalogue `incidents.md`. The commented examples below are illustrative (an imaginary service with a job queue
and an outbox table in Postgres) — replace them with your own.
"""

from __future__ import annotations

import os
from datetime import timedelta  # noqa: F401 — for stale_after in RULES
from pathlib import Path

from .envfile import read_env_file
from .rules import Rule, count_at_least, seconds_above, stale_after  # noqa: F401

PROJECT = "<project>"  # name in monitor texts and in ~/.config/<project>
PFX = "<pfx>"  # short prefix: ~/<pfx>-monitor
PROD_URL = os.environ.get("PROD_MONITOR_URL", "<https://prod address>")
REPO = Path(os.environ.get("PROD_MONITOR_REPO", "<abs path to the main checkout>"))
# Release workflow in GitHub Actions: a failed release is an anomaly. None — do not check.
RELEASE_WORKFLOW: str | None = "release.yml"

# --- paths (outside the repo; the loop runs from a copy in PM_ROOT, not from the checkout) ---
PM_ROOT = Path(os.environ.get("PM_ROOT", f"~/{PFX}-monitor")).expanduser()
STATE_DIR = Path(os.environ.get("PROD_MONITOR_STATE", PM_ROOT / "state/prod_monitor")).expanduser()
CONFIG_DIR = Path(os.environ.get("PROD_MONITOR_CONFIG", f"~/.config/{PROJECT}")).expanduser()
ACCESS_FILE = CONFIG_DIR / "prod-watch.env"  # prod DB connection string, read-only
DATABASE_URL_KEY = "PROD_RO_DATABASE_URL"
TOKEN_FILE = CONFIG_DIR / "monitor.env"  # CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`
# On-call config (group, plugin directory, development session, channel port) is written by install.
DESK = read_env_file(PM_ROOT / "prod_monitor" / "desk.env")

# --- monitor (agent) ---
MODEL = os.environ.get(
    "PROD_MONITOR_MODEL", "claude-sonnet-5-5"
)  # full id: an alias gives an older model
SLOT_HOURS = (9, 14, 19)  # scheduled passes, hours in TZ
TZ = os.environ.get("PROD_MONITOR_TZ", "UTC")
# Spend cap of one monitor pass, USD (--max-budget-usd; on a subscription it caps the computed cost).
MAX_BUDGET_USD = float(os.environ.get("PROD_MONITOR_MAX_BUDGET_USD", "1.0"))
# Language of messages to the group (project language, default English).
LANGUAGE = os.environ.get("PROD_MONITOR_LANGUAGE", "English")

# --- watchdog: prod DB snapshot once a minute and anomaly rules (no model) ---
# One query, each column is a number or a time. Illustrative example (tables `jobs` and `outbox`):
#   (select count(*) from jobs where status='scheduled' and run_at < now() - interval '5 min')
#       as overdue_jobs,
#   (select extract(epoch from now() - min(created_at))::int from outbox
#       where status in ('pending','retry')) as outbox_pending_age_s,
#   (select max(last_synced_at) from integrations where status='active') as integration_last_synced
SNAPSHOT_SQL = """
select now() as now,
  (<query>) as <column>
"""
RULES: list[Rule] = [
    # Illustrative example:
    # count_at_least("overdue_jobs", 1, "jobs_overdue", "overdue jobs: {v}"),
    # seconds_above("outbox_pending_age_s", 600, "outbox_stuck", "outgoing messages stuck for {m} min"),
    # count_at_least("outbox_failed_1h", 3, "outbox_failing", "not delivered in the last hour: {v}"),
    # stale_after("integration_last_synced", timedelta(hours=1), "integration_sync_stale",
    #             "integration sync has not run for over an hour"),
]

# Checks the agent picks by name (it writes no SQL itself). Illustrative example:
#   "overdue_jobs": "select count(*) n, min(run_at) oldest from jobs where ...",
#   "outbox_24h_by_status": "select status, count(*) n from outbox where ... group by 1",
CHECKS: dict[str, str] = {
    "<check name>": "<select …>",
}

# Hosting tools (MCP from the local Claude Code config for REPO). Reads are allowed,
# changes are explicitly forbidden, even if the hosting adds new ones. Illustrative example:
#   read: getProject, getRunLogs, getEventLogs, getBuildLogs;
#   forbidden: restartProject, rebuildProject, scaleProject, stopBuild, freezeProject, deleteProject,
#              updateEnvVar, createEnvVars, deleteEnvVar, uploadFiles, deleteFiles.
HOSTING_READ: list[str] = ["mcp__<hosting>__<read>"]
HOSTING_WRITE: list[str] = ["mcp__<hosting>__<change>"]

# What the project is and in what order to look. The monitor adds the verdict format itself.
PROMPT = """You are the prod Monitor of <project> (<what it is: bot, site, API; where it is hosted; slug>).
Task: in one pass, assess the health of prod and return a verdict. You only read, you fix nothing.

Order:
1. Hosting: <project status; events for 2 hours; logs for 10 minutes — what in them is a sign of life (heartbeat), Traceback/ERROR>.
2. db_check: all checks.
3. http_probe <readiness check path>. 4. gh_release_status.
Time: db_check.now_utc; hosting logs — <time zone>. If the watchdog sent anomalies — start with them and confirm/refute them."""

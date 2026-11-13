# The quota guard measures Codex by the Codex subscription

## Why

agent-codex left the quota guard silent under Codex ("Codex quota not tracked yet"): it measured the Claude
subscription with a `claude -p` probe and would have stopped Codex by someone else's limit. A Codex session ran with
no quota guard at all — no "no new work", no "save and stop" near its own ceiling.

Codex answers its quota without a model request: `account/rateLimits/read` through `codex app-server` returns the
plan's windows (`usedPercent`, `windowDurationMins`, `resetsAt`) and `ordinaryUsageAllowed`, the server's own "you may
work now". The windows depend on the plan: Plus has 5 hours and a week, the free plan one 30-day window (seen on this
server), Pro no 5-hour window.

## What changes

- **A Codex session is measured by the Codex subscription.** The same hooks, thresholds and stages as for Claude
  (≥ 80% no new work, ≥ 85% wrap up, ≥ 90% save work only); the source is `account/rateLimits/read`, with its own
  cache, log and notices (`~/.cache/codex-quota*.json`): the two subscriptions are independent.
- **Windows by length, not by name.** A window up to a day long takes the 5-hour thresholds (`QUOTA_5H`), a longer one
  the weekly thresholds (`QUOTA_7D`); each is shown with its real length ("30d 44%"), and a window the plan does not
  have is not shown.
- **`ordinaryUsageAllowed: false` is "no new work"** whatever the percentages, until the latest window reset.
- **Codex's subagent tool `spawn_agent` is new work** like Claude's `Agent`.
- **The resume hint under Codex names no Claude tool**: save the state and end the turn; the continuation is the
  factory's scheduler or the human.
- `quota.py status|check|refresh --agent codex` (or `QUOTA_AGENT=codex`) for humans and scripts.

## Acceptance

- WHEN a Codex Plus answer has 5h 42% and 7d 81% THEN the stage is no new work and the reason names "Codex quota: 7d 81%".
- WHEN the free plan answers one 30-day window at 91% THEN the stage is save work only, the line shows "30d 91%" and no
  5-hour window, and work resumes at that window's reset.
- WHEN `ordinaryUsageAllowed` is false at 3% / 5% THEN the stage is no new work; when it is null nothing is assumed.
- WHEN a Codex session asks for `spawn_agent` above the threshold THEN it is denied with "Codex quota"; the Claude
  cache is not touched.
- WHEN `quota.py status --agent codex` runs on a machine logged in to Codex THEN it prints the plan's windows.

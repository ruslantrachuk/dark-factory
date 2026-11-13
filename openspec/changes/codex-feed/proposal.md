# The status feed shows every agent: quotas per agent, CLI versions, Codex sessions

## Why

`status.json` (the feed the status page and the owner's apps read) knew one agent: one quota object, Claude sessions
only. With Codex on the server (codex-provision) the owner could not see the Codex subscription's quota, whether
Codex's daemon runs and on what version, or that a project is being worked on in Codex.

## What changes — additive, the document stays `"version": 2`

Every existing field keeps its name, type and meaning; clients that do not know the new fields keep working.

- **`quotas`** (top level): `{"claude": <the same object as quota>, "codex": <object>}`; `codex` is present only when
  the server has a Codex quota cache (`quota.py` with `--agent codex`, or a Codex session's hooks). Each object has the
  version-2 fields (`five_hour`, `seven_day`, `no_new_work`, `resets_at`, `resets`, `as_of`) plus:
  - `windows`: the windows the plan really has, `[{"key", "label", "pct", "resets_at"}]` — Claude `5h` and `7d`;
    Codex `5h` + `7d` on Plus, one `30d` on the free plan (its `key` is `seven_day`: it takes the weekly thresholds);
  - `usage_allowed`: Codex's `ordinaryUsageAllowed` (`true` / `false`; `null` for Claude, which has no such field).
    `false` makes `no_new_work` true whatever the percentages.
- **`quota`** stays Claude's, unchanged.
- **`agents_cli`** (top level, full feed only): `{"claude": {"version"}, "codex": {"version", "daemon",
  "daemon_version", "logged_in"}}`; `codex` only where Codex is installed.
- **`projects[].codex`**: `{"working", "last_worked_at"}` from the project's Codex sessions (rollouts under
  `<CODEX_HOME>/sessions/`, a session mid-turn written in the last 10 minutes = working), `null` when Codex has not
  worked there in 14 days. **`projects[].working`** and **`last_worked_at`** now include Codex.

Example (`codex` parts):

```json
{
  "version": 2,
  "quota": {"five_hour": 17, "seven_day": 69, "no_new_work": false, "resets_at": null,
            "resets": {"five_hour": "2026-11-14T02:00:00Z", "seven_day": "2026-11-15T22:00:00Z"},
            "as_of": "2026-11-13T22:05:16Z",
            "windows": [{"key": "five_hour", "label": "5h", "pct": 17, "resets_at": "2026-11-14T02:00:00Z"},
                        {"key": "seven_day", "label": "7d", "pct": 69, "resets_at": "2026-11-15T22:00:00Z"}],
            "usage_allowed": null},
  "quotas": {
    "claude": "<the same object as quota>",
    "codex": {"five_hour": 0, "seven_day": 44, "no_new_work": false, "resets_at": null,
              "resets": {"seven_day": "2026-12-13T10:04:29Z"}, "as_of": "2026-11-13T22:00:37Z",
              "windows": [{"key": "seven_day", "label": "30d", "pct": 44, "resets_at": "2026-12-13T10:04:29Z"}],
              "usage_allowed": true}
  },
  "agents_cli": {"claude": {"version": "2.1.325"},
                 "codex": {"version": "0.169.0", "daemon": "running", "daemon_version": "0.169.0", "logged_in": true}},
  "projects": [{"name": "shop", "working": true, "last_worked_at": "2026-11-13T22:04:50Z",
                "codex": {"working": true, "last_worked_at": "2026-11-13T22:04:50Z"}}]
}
```

A client shows a ring per entry of `quotas` (labels from `windows`), the CLI versions, and a Codex mark on a project
whose `codex.working` is true; "waiting for quota" stays per project from `waiting_quota` (Claude's), until the feed
says which agent a project runs on.

## Acceptance

- WHEN the server has no Codex THEN the document is the version-2 one plus `quotas: {"claude": quota}`, `agents_cli`
  with Claude's version, and `codex: null` on every project.
- WHEN a Codex session in a project's worktree is mid-turn and was written within 10 minutes THEN the project is
  `working` and `codex.working` is true; a session idle after `task_complete` is not working but sets `last_worked_at`.
- WHEN the Codex cache holds one 30-day window at 44% THEN `quotas.codex.windows` lists `30d 44%` and `five_hour` is 0.
- WHEN Codex says ordinary use is not allowed THEN `quotas.codex.no_new_work` is true and `usage_allowed` false.
- WHEN `serve` refreshes the fast facts THEN `quotas` and `projects[].codex` are refreshed too; `agents_cli` keeps the
  full feed's value.

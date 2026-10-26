# Practice: factory analytics

> Weekly numbers of how the factory works, counted after the fact from what every session already leaves on the
> server. They answer whether the factory does what it claims: does work arrive and get done without the owner, where
> do the tokens go, does the friction fall. Collected without a model; no quota is spent.

## What is counted

One ISO week (Monday to Sunday, UTC) per file, per repository of the factory (a checkout's `origin`, plus the canon
when its checkout is given):

| Metric | From | How |
|---|---|---|
| Who drove the work | session transcripts | each turn (a prompt and the work up to the next one) by who started it: the owner, the On-call (anyone else, in the client chat), the production monitor, nothing human (scheduled runs, pipelines, messages between sessions); tokens and turns per kind |
| Pipeline against direct work | transcripts | tokens of the main session, of helper subagents and of pipeline agents; tokens per merged PR with and without the pipeline |
| Backend against frontend | code host | merged PRs into the default branch (promotion PRs left out) by the side with 70% of the changed source lines |
| Cost of tests | code host, transcripts | CI runs and minutes; test commands run inside sessions and the tokens of the messages that ran them |
| The owner's friction | transcripts | the owner's prompts with swearing, interrupts, rejected tool calls — counts only, never the text |
| Parts | git history | the week each part (base, On-call, monitor, releases by tag, pipeline, fences, the plugin release) first appeared in a project, so a jump in a series is read against what changed |

Tokens are input + cache write + cache read + output. Approximate, and each weekly file says so: the On-call share
(work it handed to a development session in words counts as the owner's), tokens per PR (a turn belongs to the PR its
session opened next or whose branch it named), test cost inside sessions. Sessions run in the cloud leave no transcript
on the server and are not counted.

## Where it lives

- **Collected** by `scripts/analytics.py collect` into `~/.local/state/dark-factory/analytics/<week>.json` on the
  server, with real names. Claude Code deletes transcripts after 30 days; the store keeps the series.
- **Published** by `analytics.py publish --repo <checkout>`: `analytics/<week>.md`, `analytics/data/<week>.json` and
  `analytics/SUMMARY.md` on a branch `chore/analytics-<week>`, as a draft PR the owner reviews and merges. Each
  repository is a letter (kept in `aliases.json` on the server); the canon is shown as *canon*. A leak check refuses
  to write if any rendered file contains a repository, path, host, handle or work-branch name.
- **Run** by `df-fleet-analytics.timer`, Mondays 05:20 UTC, which `fleet.py provision` writes when
  `~/.config/dark-factory/fleet.env` has `FLEET_ANALYTICS_REPO=<checkout>`.

## Turn it on

1. `~/.config/dark-factory/analytics.env`: `ANALYTICS_OWNER="<the server's user> <your chat handle>"` — everyone else
   counts as work via the On-call. Optional: `ANALYTICS_SWEAR`, `ANALYTICS_TEST_CMDS`; per project,
   `<project>/.claude/factory/analytics.env` with `ANALYTICS_FRONTEND` / `ANALYTICS_BACKEND` path globs where the
   default classes do not fit the layout.
2. `python3 <plugin>/scripts/analytics.py collect --all` — every week the transcripts still hold — then
   `analytics.py report` to read the last week before anything leaves the server.
3. `FLEET_ANALYTICS_REPO=<checkout>` in `fleet.env`, `fleet.py provision`. The first Monday run opens the PR.

`fleet.py status` shows the last collected week; a missed week is ○.

> **Seam:** transcripts = Claude Code's local JSONL; code host = GitHub (`gh`). To use another tool, rewrite
> `analytics_lib/transcripts.py` or `analytics_lib/codehost.py`.

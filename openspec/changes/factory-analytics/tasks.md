# Tasks: factory analytics

## 1. Collect
- [ ] 1.1 `analytics.py` skeleton: commands, project list, transcript dirs of a checkout, state dir
- [ ] 1.2 Transcript reader: dedup by file and `message.id`, ISO week, token sums
- [ ] 1.3 Turn kinds (owner / On-call / monitor / unattended), owner from `analytics.env`, subagents to their turn
- [ ] 1.4 Pipeline / helpers / direct split; tokens per PR via `pr-link`, branch fallback; repository as the project unit
- [ ] 1.5 `gh` source: merged PRs into the default branch (no promotion PRs) with files, CI runs with duration
- [ ] 1.6 File classes and per-project overrides; PR class by changed lines
- [ ] 1.7 Test cost: CI minutes, test commands in sessions
- [ ] 1.8 Friction counts over owner prompts
- [ ] 1.9 Parts timeline: per project from git history and plugin pin, factory-wide from tags and units
- [ ] 1.10 Week JSON on the server; `--week`, `--since-last`, `--all`

## 2. Publish
- [ ] 2.1 Aliases: stable letters
- [ ] 2.2 Render the weekly file, its JSON and `SUMMARY.md`, with the reading notes
- [ ] 2.3 Leak check built from the sources
- [ ] 2.4 Worktree, branch, commit, push, draft PR (or add to the open one); `--dry-run`

## 3. Timer
- [ ] 3.1 `fleet.py provision`/`unprovision`: `df-fleet-analytics` pair behind `FLEET_ANALYTICS_REPO`
- [ ] 3.2 `fleet.py status`: last collected week, open analytics PR
- [ ] 3.3 `provision-server` and `factory-status` skills, `docs/` (practices: a short page on factory analytics)

## 4. This repository
- [ ] 4.1 README line, CONTRIBUTING exception line
- [ ] 4.2 Tests in `tests/test_analytics.py` and `tests/test_fleet.py`; CONTRIBUTING test list
- [ ] 4.3 On this server: `FLEET_ANALYTICS_REPO`, `fleet.py provision`, `collect --all`, first PR (owner's "yes" for the
      unit and the first publication)
</content>
</invoke>

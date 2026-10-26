# Factory analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a stdlib script that turns the server's transcripts, git history and GitHub data into weekly, anonymised
numbers and opens a PR with them, run by a weekly fleet timer.

**Architecture:** `scripts/analytics.py` is the CLI; the work lives in `scripts/analytics_lib/` — one module per
source (`transcripts`, `codehost`, `parts`), one for the stored weeks (`store`), one for rendering and the leak check
(`render`), one for the git/PR side (`publish`). Collect writes real-name week JSON on the server; render turns it into
letters; publish commits the rendered files on a branch and opens a draft PR. `fleet.py` gets the timer pair.

**Tech Stack:** Python 3.11 stdlib only, `git`, `gh`, systemd user units. Tests: `unittest`, run as
`python3 tests/test_analytics.py`.

**Spec:** `openspec/changes/factory-analytics/design.md` (read it first; this plan does not repeat its rules).

## Global Constraints

- English only in code, comments, strings, test names (CONTRIBUTING).
- Stdlib only; no model call, no network except `gh` and `git push`.
- Everything ships inside `plugins/dark-factory/`; tests in `tests/`.
- Never print or store message text; the server JSON holds counts, PR numbers and repository names only.
- Tokens are always the four fields `input`, `cache_write`, `cache_read`, `output` (+ `total` when rendered).
- ISO week of the UTC `timestamp`, written `YYYY-Www` (e.g. `2026-W43`).
- State dir: `$ANALYTICS_STATE` or `~/.local/state/dark-factory/analytics/`; settings: `~/.config/dark-factory/analytics.env`
  (`ANALYTICS_OWNER`, `ANALYTICS_SWEAR`, `ANALYTICS_TEST_CMDS`) and per project `<project>/.claude/factory/analytics.env`
  (`ANALYTICS_FRONTEND`, `ANALYTICS_BACKEND`), read with `fleet.read_env`.
- Timer: `df-fleet-analytics.service` + `.timer`, `OnCalendar=Mon *-*-* 05:20:00 UTC`, `Persistent=true`,
  only when `fleet.env` has `FLEET_ANALYTICS_REPO`.
- Publication branch `chore/analytics-<YYYY>-W<ww>`; draft PR; never merge, never push the default branch.

## Review Focus

- A transcript line that is not JSON, or a record without `message`/`usage`/`timestamp` — skipped, never a crash
  (test in Task 2).
- A project with no `origin` remote or `gh` failing (no auth, network) — the week is still collected from transcripts,
  the code-host fields are `null` and the report says "not available" (test in Task 4).
- The same week collected twice, or the timer missing a Monday — re-collect overwrites, `--since-last` fills every
  missing week (test in Task 6).
- A new project appearing mid-series — gets the next letter, old letters unchanged, summary shows its first week
  (test in Task 7).
- An open analytics PR from an earlier week — the new week is added to that branch, no second PR (test in Task 9).

---

### Task 1: Skeleton, project discovery, state

**Files:**
- Create: `plugins/dark-factory/scripts/analytics.py`, `plugins/dark-factory/scripts/analytics_lib/__init__.py`,
  `plugins/dark-factory/scripts/analytics_lib/store.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces: `store.transcript_dirs(checkout: Path, projects_root: Path) -> list[Path]`;
  `store.iso_week(ts: str) -> str`; `store.week_bounds(week: str) -> tuple[datetime, datetime]`;
  `store.state_dir() -> Path`; `store.save_week(week: str, data: dict) -> Path`; `store.load_week(week) -> dict | None`;
  `store.stored_weeks() -> list[str]`; `Settings` dataclass (`owner: set[str]`, `swear: list[str]`, `test_cmds: list[str]`)
  and `store.load_settings() -> Settings`. Projects come from `fleet.load_projects(fleet.parse_projects_file(...))`.

- [ ] **Step 1: Failing tests** — `test_transcript_dirs_include_worktrees`: for checkout `/home/u/my.proj` and a root
  holding `-home-u-my-proj`, `-home-u-my-proj--claude-worktrees-x`, `-home-u-my-proj--worktrees-dev`,
  `-home-u-my-proj-other` → the first three only. `test_iso_week`: `"2026-10-19T00:00:01Z"` → `"2026-W43"`,
  `"2026-10-18T23:59:59Z"` → `"2026-W42"`. `test_save_load_roundtrip` in a temp `ANALYTICS_STATE`.
  `test_settings_owner_split`: `ANALYTICS_OWNER="peat ruslan_trachuk"` → `{"peat", "ruslan_trachuk"}`.
- [ ] **Step 2:** `python3 tests/test_analytics.py` → FAIL (import error).
- [ ] **Step 3:** Implement. `analytics.py` imports `analytics_lib` relative to its own directory (`sys.path.insert` of
  `Path(__file__).resolve().parent`), argparse with `collect|report|publish` stubs; module docstring in the style of
  `triage.py` (what, settings, seams).
- [ ] **Step 4:** tests PASS; `python3 scripts/test_repo.py` still PASS (fix its allowlist if it rejects the package dir).
- [ ] **Step 5:** commit `feat(analytics): skeleton, project discovery, week store`.

### Task 2: Transcript reader and turns

**Files:** Create `analytics_lib/transcripts.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `Tok = dict[str, int]` (four keys); `Turn` dataclass: `session: str`, `start: str` (timestamp),
  `kind: str` (`owner|on_call|monitor|unattended`), `tokens: dict[str, Tok]` keyed `direct|helpers|pipeline`,
  `test_calls: int`, `test_tokens: Tok`, `swear: bool`, `interrupts: int`, `rejected: int`, `typed: bool`;
  `PrLink` dataclass: `session`, `ts`, `repo`, `number`;
  `read_project(dirs: list[Path], settings: Settings) -> tuple[list[Turn], list[PrLink]]`.

- [ ] **Step 1: Failing tests** with fixtures written by a helper `write_session(dir, records)`:
  `test_bad_lines_skipped` (a non-JSON line and a record without `message` → no crash, other turns counted);
  `test_dedup_by_message_id` (three lines with one `message.id`, output 26 each → one message, output 26);
  `test_symlinked_file_counted_once`;
  `test_turn_kinds`: prompt with `origin.kind=human` → `owner`; old record without `origin`, plain string content →
  `owner`; `origin.kind=channel` with `user="pavel"` → `on_call`, with `user="ruslan_trachuk"` (owner) → `owner`;
  `<cross-session-message from="bridge:…">` → `owner`; `origin.kind=task-notification` → `unattended`;
  `origin.kind=peer` → `unattended`; `entrypoint=sdk-py` → `monitor`; a `tool_result` user record → not a new turn;
  `test_subagent_tokens_go_to_launching_turn`: subagent file with meta `agentType=workflow-subagent` → `pipeline`,
  `dark-factory:reviewer` → `pipeline`, `Explore` → `helpers`, no meta but `attributionAgent` → that type;
  `test_friction_counts_owner_only`: owner prompt "ну пиздец" → `swear`; same text from a channel client → not;
  `[Request interrupted by user]` → `interrupts=1`; a "doesn't want to proceed" tool_result → `rejected=1`;
  `test_test_calls`: a Bash tool_use with `command` `cd app && pytest -q` → `test_calls=1`, its message's tokens in
  `test_tokens`; `test_pr_links_read`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implement `read_project`. A subagent file's records are joined to the parent turn by `sessionId` and
  time (the turn whose span contains the subagent's first timestamp). Swear roots: a module constant list (Russian and
  English roots, matched case-insensitively on word starts) plus `settings.swear`. Test command patterns: constant
  `TEST_CMD_RE` (`pytest|npm (run )?test|vitest|playwright|go test|cargo test`) plus `settings.test_cmds`.
- [ ] **Step 4:** PASS. Run once read-only against the real server
  (`python3 -c` calling `read_project` on one project) and check the turn-kind totals look sane — owner well below
  100% of tokens.
- [ ] **Step 5:** commit `feat(analytics): transcript reader — turns, kinds, splits, friction, test calls`.

### Task 3: PR attribution

**Files:** Modify `analytics_lib/transcripts.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `attribute(turns: list[Turn], links: list[PrLink], branches: dict[tuple[str, int], str]) ->
  tuple[dict[tuple[str, int], PrCost], Tok]` — `(repo, number)` → `PrCost(tokens: Tok, pipeline: bool, kind: str)`
  (kind = the kind with most tokens), and the unattributed tokens. `branches` maps a PR to its head branch for the
  fallback.

- [ ] **Step 1: Failing tests** `test_tokens_up_to_pr_link`: one session, turns at t1,t2,t3, a `pr-link` #5 between t2
  and t3 → #5 gets t1+t2, t3 unattributed; `test_second_link_takes_from_previous`; `test_branch_fallback` (no link,
  turn records with `gitBranch` = head of #7 → #7); `test_pipeline_flag`.
- [ ] **Step 2–4:** FAIL → implement → PASS. `Turn` gains `branch: str | None` (most common `gitBranch` of its records).
- [ ] **Step 5:** commit `feat(analytics): tokens per PR via pr-link`.

### Task 4: Code host

**Files:** Create `analytics_lib/codehost.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `PR` dataclass: `repo`, `number`, `head`, `base`, `merged_at`, `lines: dict[str, int]`
  (`frontend|backend|tests|other`), `cls: str` (`frontend|backend|mixed|other`);
  `merged_prs(repo: str, week: str, rules: Rules) -> list[PR] | None` (None when `gh` fails);
  `ci_runs(repo: str, week: str) -> dict | None` (`{"runs": int, "minutes": float}`);
  `classify(path: str, rules: Rules) -> str`; `Rules` from defaults + project `analytics.env`;
  `repo_of(checkout: Path) -> str | None` (`owner/name` from `origin`).
  `gh` is called through one function `gh_json(args: list[str]) -> object | None` so tests patch it.

- [ ] **Step 1: Failing tests** `test_classify_defaults` (`web/src/App.tsx` → frontend, `app/api/x.py` → backend,
  `tests/test_x.py` and `src/a.spec.ts` → tests, `README.md` → other); `test_project_override`;
  `test_pr_class_by_lines` (70% rule, `mixed` below); `test_promotion_prs_excluded` (base = default branch, head
  `develop` that is itself a base of other merged PRs → excluded; head `main` into `release` → excluded);
  `test_gh_failure_returns_none`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Default branch via `gh repo view --json defaultBranchRef`. A head is
  long-lived when it is a default branch, `release`, or the base of another merged PR in the data.
- [ ] **Step 5:** commit `feat(analytics): merged PRs, file classes, CI minutes`.

### Task 5: Parts timeline

**Files:** Create `analytics_lib/parts.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `PARTS` constant: part name → list of path globs (`base`: `.harness/base-sha`, `openspec/project.md`;
  `on_call`: `scripts/feedback-desk.sh`; `monitor`: `scripts/prod-monitor.sh`, `scripts/ops/prod_monitor/*`;
  `release_tag`: `scripts/release.sh`; `pipeline`: `.claude/feature-pipeline.*`; `fences`: `.claude/fences.env`);
  `project_parts(checkout: Path) -> dict[str, str]` (part → first ISO date on the default branch, `git log
  --diff-filter=A --format=%cs --reverse -- <glob>`); `plugin_pins(checkout) -> list[tuple[str, str]]` (date, ref)
  from the history of `.claude/settings.json`; `factory_parts(canon: Path | None) -> dict` (`releases`: tag → date;
  `server`: unit name → mtime date of the unit file in `UNIT_DIR` for `df-fleet-watch.timer`, `df-*-triage.timer`,
  `df-fleet-analytics.timer`).

- [ ] **Step 1: Failing tests** on a temp git repo with dated commits (`GIT_COMMITTER_DATE`):
  `test_first_add_date`, `test_part_absent`, `test_plugin_pin_changes`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(analytics): parts timeline`.

### Task 6: Collect

**Files:** Modify `analytics.py`, `analytics_lib/store.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `collect_week(week: str, projects, settings) -> dict` in the shape below, saved by `store.save_week`;
  CLI `collect --week W | --since-last | --all`. Week JSON:
  `{"week", "collected_at", "final": bool, "projects": {repo: {"first_week", "turns": {kind: n}, "tokens": {kind: Tok},
  "split": {direct|helpers|pipeline: Tok}, "prs": [{"number", "cls", "lines", "tokens", "pipeline", "kind"}] | null,
  "unattributed": Tok, "ci": {...} | null, "tests": {"calls", "tokens"}, "friction": {"prompts", "swear",
  "interrupts", "rejected"}, "parts": {part: date}, "pins": [[date, ref]]}}, "factory": {...}}`.
  A repository is the unit: turns of a checkout go to its `origin` repo, except turns attributed to a PR of another
  repo (the canon), which go there.

- [ ] **Step 1: Failing tests** `test_collect_week_shape` (fixtures from Tasks 2–5, `gh_json` patched);
  `test_recollect_overwrites`; `test_since_last_fills_gaps` (stored W40, W43 → collects W41, W42 and the current one);
  `test_all_starts_at_oldest_transcript`; `test_final_flag` (collected after the week's end → `final: true`).
- [ ] **Step 2–4:** FAIL → implement → PASS. Read every transcript once per run and bucket by week (do not re-read per
  week).
- [ ] **Step 5:** commit `feat(analytics): collect weeks into the server store`.

### Task 7: Aliases, render, leak check

**Files:** Create `analytics_lib/render.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `aliases(repos: list[str], path: Path, canon: str | None) -> dict[str, str]` (stable letters, the canon repo
  → `"canon"`); `render_week(data: dict, alias: dict) -> tuple[str, dict]` (markdown, anonymised JSON);
  `render_summary(weeks: list[dict], alias: dict) -> str`; `leak_terms(projects, weeks, settings) -> set[str]`;
  `leak_check(files: dict[str, str], terms: set[str]) -> list[tuple[str, str]]` (file, term).

- [ ] **Step 1: Failing tests** `test_aliases_stable_and_new_project_next_letter`; `test_render_has_reading_notes`
  (the week file starts with the "How to read" block: tokens note, approximate metrics named);
  `test_render_has_no_real_names`; `test_summary_marks_first_week_and_parts` ("W41: B — on_call");
  `test_leak_check_whole_word` (term `shop` hits "shop" and "Shop", not "workshop"; `main` is never a term;
  terms under 4 letters dropped); `test_leak_terms_from_sources` (slug, repo name, `owner/name`, path components,
  hostname, owner handles, `<type>/<slug>` head slugs).
- [ ] **Step 2–4:** FAIL → implement → PASS. Markdown: one section per metric, a table per section, numbers in
  thousands/millions with one decimal; the canon is named "canon".
- [ ] **Step 5:** commit `feat(analytics): anonymised reports and leak check`.

### Task 8: `report` command

**Files:** Modify `analytics.py`; Test `tests/test_analytics.py`

- [ ] **Step 1: Failing test** `test_report_prints_and_writes_nothing` (stdout has the week's markdown, the state dir and
  cwd unchanged).
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(analytics): report command`.

### Task 9: Publish

**Files:** Create `analytics_lib/publish.py`; Modify `analytics.py`; Test `tests/test_analytics.py`

**Interfaces:**
- Produces: `publish(repo_dir: Path, weeks: list[dict], alias, terms, dry: bool) -> int`. Files written:
  `analytics/<W>.md`, `analytics/data/<W>.json`, `analytics/SUMMARY.md`.

- [ ] **Step 1: Failing tests** against a temp bare repo + clone and a fake `gh` on `PATH` (a script logging its
  arguments, answering `pr list` from a file): `test_publish_opens_draft_pr` (branch `chore/analytics-2026-W43`, one
  commit, push, `gh pr create --draft` with the three sections in the body); `test_publish_reuses_open_pr` (an open PR
  with head `chore/analytics-2026-W42` → commit added there, no `pr create`); `test_leak_refuses` (planted slug → exit
  1, message names term and file, nothing committed); `test_dry_run_writes_nothing`; `test_never_pushes_default_branch`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Work in a temporary `git worktree` of `repo_dir` from
  `origin/<default>`, removed afterwards.
- [ ] **Step 5:** commit `feat(analytics): publish as a draft PR`.

### Task 10: Fleet timer and status

**Files:** Modify `plugins/dark-factory/scripts/fleet.py` (module docstring; `server_units`; `unprovision`; `status`);
Test `tests/test_fleet.py`

**Interfaces:**
- Consumes: `analytics.py collect --since-last` and `publish --repo DIR`.
- Produces: `analytics_service(python: str, repo: str) -> str`, `analytics_timer() -> str`; `server_units` adds both when
  `read_env(FLEET_ENV).get("FLEET_ANALYTICS_REPO")`; `check_analytics() -> tuple[bool, str] | None` (last stored week,
  open analytics PR) printed once at the top of `status` like the quota line.

- [ ] **Step 1: Failing tests** `test_analytics_units_only_with_setting`; `test_analytics_timer_monday`
  (`OnCalendar=Mon *-*-* 05:20:00 UTC`, `Persistent=true`, `Unit=df-fleet-analytics.service`);
  `test_analytics_service_runs_collect_then_publish` (two `ExecStart=` lines, `OnFailure`);
  `test_unprovision_removes_analytics_pair`; `test_status_analytics_line`.
- [ ] **Step 2–4:** FAIL → implement → PASS (`python3 tests/test_fleet.py`, `python3 tests/test_analytics.py`).
- [ ] **Step 5:** commit `feat(fleet): weekly analytics timer`.

### Task 11: Docs and repository lines

**Files:** Modify `README.md` (one line under the intro: the factory publishes its own weekly numbers →
`analytics/SUMMARY.md`), `CONTRIBUTING.md` (the `analytics/` exception line; `python3 tests/test_analytics.py` in the
test list), `plugins/dark-factory/skills/provision-server/SKILL.md` and `skills/factory-status/SKILL.md` (the setting
and the status line), `docs/practices/` new `factory-analytics.md` (what is counted, how to read it, how to turn it on)
linked from `docs/practices/README.md`; `.github/workflows` test job if it lists test files.

- [ ] **Step 1:** write; `python3 scripts/test_repo.py` and all tests PASS; `claude plugin validate plugins/dark-factory`.
- [ ] **Step 2:** commit `docs: factory analytics`.

### Task 12: Turn it on here (owner's "yes" for each external step)

- [ ] **Step 1:** after the PR is merged and the plugin updated: `analytics.env` with `ANALYTICS_OWNER`,
  `FLEET_ANALYTICS_REPO=<canon checkout>` in `fleet.env` — show, "yes".
- [ ] **Step 2:** `collect --all`, `report` for the last week — show the owner.
- [ ] **Step 3:** `fleet.py provision --dry-run` → "yes" → `provision`; `publish` → first analytics PR for the owner.

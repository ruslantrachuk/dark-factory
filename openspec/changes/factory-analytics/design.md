# Design: factory analytics

## Intent

Weekly, honest numbers about how the factory works, collected without a model and published where people look. A
number is shown only with how it was counted; an approximate one says so.

**Goals.** One week of numbers per project per ISO week; a series that survives transcript cleanup; a report a
stranger can read in a minute; zero quota spent on collecting.

**Non-goals.** Money; a live dashboard; per-message or per-person detail beyond the owner's counts; the On-call chain
record (next change).

**Anti-goals** — a failure even if everything else works:
- a project, client, repository, branch, path, host or message text appears in a published file;
- the timer spends model quota or pushes to a main branch;
- a number is shown as exact when it is a heuristic.

## Sources (all on the server, read-only)

| Source | Where | Gives |
|---|---|---|
| Transcripts | `~/.claude/projects/<dir>/**/*.jsonl` (+ `subagents/*.jsonl` with `*.meta.json`) | per assistant message: `usage` (input, cache write, cache read, output), `model`; per record: `timestamp`, `entrypoint`, `cwd`, `gitBranch`, `sessionId`; a subagent's `agentType` from its meta file |
| Projects | `~/.config/dark-factory/projects` (the fleet's list) | which checkouts count; the transcript dirs of a checkout are its path with `/` and `.` turned into `-`, plus that name followed by `--claude-worktrees-…` / `--worktrees-…` |
| Repositories | the checkouts' `origin` + every `prRepository` of the `pr-link` records | a project is a **repository**, not a checkout: work done in one checkout for another repository (the canon, an outside repo) is counted under that repository |
| Code host | `gh pr list --state merged`, `gh pr view --json files`, `gh run list` | merged PRs of the week, their files and head branch, CI runs and their duration |

> **Seam:** code host = GitHub (`gh`); transcripts = Claude Code's local JSONL. To use another tool, rewrite the
> `source_*` functions of `analytics.py`.

**Counting rules that apply everywhere**
- A message counts once: deduplicate assistant records by `message.id` (one API response is written as several
  lines), and transcript files by path after resolving links (the same subagent file can be reached twice).
- Tokens are reported as four numbers — input, cache write, cache read, output — and a total. Cache reads dominate the
  total; the report says so in one line instead of hiding them.
- A record belongs to the ISO week of its `timestamp` (UTC).

## The five metrics

1. **Who drove the work.** Decided **per turn**, not per session: a long development session where the owner typed
   once and the factory then ran for hours is mostly not the owner's work. A turn is a prompt and the assistant records
   up to the next prompt; its kind comes from the prompt (`origin.kind` where present):
   - *owner* — typed by the owner (see "People" below), directly or relayed by the claude.ai
     bridge (`from="bridge:…"`);
   - *On-call* — a client-chat message (`<channel source=…>`) from anyone but the owner, and the turns of
     the On-call session;
   - *monitor* — `entrypoint` `sdk-py` or the monitor's prompt marker;
   - *unattended* — scheduled fires and task notifications, triage, pipeline runs, and messages from another
     session (a peer message takes the sender's kind when the sender is resolvable, else *unattended*).
   A subagent's records and hand-backs belong to the turn that launched it. Reported: tokens and turns per kind, and
   merged PRs per kind of the turns attributed to them (metric 2's link). "Via On-call" means work in turns the
   client started; work the On-call handed to the development session in words is not traceable yet, so the
   report marks this metric approximate. Sessions run in the Anthropic cloud leave no transcript here; the report
   says they are not counted.
2. **Pipeline against direct work.** Tokens of a session split into *pipeline* (subagents of type
   `workflow-subagent` and the roles the pipeline fans out: `dark-factory:*`), *helpers* (other subagents:
   `general-purpose`, `Explore`, …) and *direct* (the main session itself). Per merged PR: the tokens attributed to it, and whether
   any of them were *pipeline* — so "tokens per PR, pipeline vs not" is a real comparison. **Attribution:** a
   transcript's `pr-link` records (`prNumber`, `prRepository`) tie a session to the PRs it opened; the session's
   tokens from its start (or its previous `pr-link`) up to a `pr-link` go to that PR, tokens after the last one go to
   no PR. Fallback when a session has no `pr-link`: `gitBranch` equal to the PR's head branch (`gitBranch` is mostly the
   session's worktree branch, so this rarely fires). Tokens not attributed to any PR are shown as such.
3. **Backend against frontend.** **Which PRs count:** merged into the repository's default branch, with a head
   branch that is not itself long-lived (a promotion `develop→main` or `main→release` bundles PRs already counted and
   would double them); PRs into other branches are counted under their own target only when that target never merges
   on to the default branch within the data. Each file of a merged PR is *frontend*, *backend*, *tests* or *other* by path rules:
   defaults (frontend: `*.tsx|*.jsx|*.vue|*.svelte|*.css|*.scss|*.html`, dirs `web/ frontend/ ui/ client/`; tests:
   `tests/`, `test_*`, `*.test.*`, `*.spec.*`; backend: other source code; other: docs, config, harness), overridable per
   project in `<project>/.claude/factory/analytics.env` (`ANALYTICS_FRONTEND=` / `ANALYTICS_BACKEND=` globs). A PR is
   frontend or backend by the larger share of changed lines, *mixed* when neither has 70%. Reported: PRs and tokens
   (via the branch link of metric 2) per class.
4. **Cost of tests.** CI: run count and total minutes of the week's runs. In sessions: count of tool calls whose
   command runs tests (`pytest`, `npm test`, `playwright`, `go test`, configurable), and the tokens of
   the assistant messages that made them — labelled approximate (reading the output costs more turns than are
   counted).
5. **Friction.** Over the owner's typed prompts only: their count, how many contain swearing (a root list in Russian
   and English, in the script, extendable by `ANALYTICS_SWEAR=`), interrupts (`[Request interrupted by user`), rejected
   tool calls (the user declined the call). Counts and per-100-prompts rates; never the text.

## People

`~/.config/dark-factory/analytics.env`: `ANALYTICS_OWNER=` — the one person whose typed prompts are the owner's (the
server's system user and their chat handle). Every other person — colleagues and clients alike, in the client chat
or wherever their words reach a session — counts as work **via On-call**. Friction (metric 5) counts the owner only.
The handles never leave the server.

## When each part appeared

The series means little without knowing what the factory had at the time: the On-call did not exist from the start.
Each week's data carries, per project, which parts it had, and the first week of each is a marker in the summary
("week 41: B gets the On-call"):
- per project, from the repository's git history (the first commit on the default branch that adds the part's
  file): base harness (`.harness/base-sha` or `openspec/` + `CODING_STANDARDS.md`), the On-call
  (`scripts/feedback-desk.sh`), the monitor (prod-monitor files), releases by tag, the feature pipeline settings, the
  fence level (`.claude/fences.env` and its changes);
- per project, the plugin release it was pinned to (`.claude/settings.json` `ref`, by commit date);
- for the factory, the plugin's own releases (tags of this repository; public) and the server-wide parts (the
  queue review, the fleet watch, this analytics) from the date the unit was first provisioned, where known.
A part found only by its file says so; a marker never claims more than the file shows (a file added is not a part in
use). `SUMMARY.md` has a "Parts" table — project × part → first week — and every metric table puts the markers in
its week column.

## Data on the server

`~/.local/state/dark-factory/analytics/<YYYY>-W<ww>.json` — the week's numbers per project slug, real names, never
published. Rewritten when the same week is collected again (a week is final once its Monday has passed and it was
collected after it). `aliases.json` beside it: slug → letter, assigned once in order of first appearance and never
reused, so a letter means the same project in every week.

## Publication

`analytics.py publish --repo <checkout>`:
1. renders from the stored weeks, replacing slugs with letters: `analytics/<YYYY>-W<ww>.md` for each week not yet in
   the repo (and the current week's file rewritten), `analytics/data/<YYYY>-W<ww>.json` (the same numbers, letters
   only) and `analytics/SUMMARY.md` (per metric a table, one row per week, plus "since the start" totals; each project
   shows the week it first appeared, so a young project is not read as a drop);
2. **leak check**: refuses to write if any rendered file contains, as a whole word and case-insensitively, a project
   slug or repository name, a repo `owner/name`, a checkout path component, the host name, a name from the people
   list, or the slug part of a `<type>/<slug>` head branch of the week. Generic words (`main`, `develop`, `release`,
   `HEAD`, branch types, words under 4 letters) are not checked. The list is built from the sources, not configured.
   A refusal exits non-zero (the unit fails and the owner is told through `OnFailure`) and names the term and file;
   nothing is committed. The public repository itself is the one name allowed (its letter-free label is "canon");
3. in a fresh worktree of the target repo from its default branch: branch `chore/analytics-<YYYY>-W<ww>`, one commit,
   push, `gh pr create --draft` with `## Done / ## Decisions / ## Open questions` (the week's headline numbers, what
   was approximate, what is new). The owner reviews and merges it with `scripts/merge-feature.sh` like any change;
   the timer never merges and never pushes to the default branch. An open analytics PR from an earlier week gets the
   new week added to its branch instead of a second PR.

Each weekly file starts with how to read it: what each number counts, which are approximate, the token note.

## Timer

`fleet.py provision` writes `df-fleet-analytics.service` + `.timer` (Monday 05:20 UTC, `Persistent=true`,
`OnFailure=df-notify@%n`) when `~/.config/dark-factory/fleet.env` has `FLEET_ANALYTICS_REPO=<checkout path>`; without
it, nothing is written and `unprovision` removes the pair. The service runs `analytics.py collect --since-last` then
`publish --repo "$FLEET_ANALYTICS_REPO"`. `fleet.py status` shows one line: the last collected week and an open
analytics PR, if any.

## Commands

```
analytics.py collect [--week 2026-W43 | --since-last | --all]   # --all: every week the transcripts still hold
analytics.py report  [--week …]                                 # print the rendered week to stdout, write nothing
analytics.py publish --repo DIR [--dry-run]
```

## For this repository

The owner's factory points `FLEET_ANALYTICS_REPO` at its checkout of this repository, so `analytics/` here holds the
owner's own numbers — aggregated, letters only. This is a deliberate exception to "canon, not instance"
(CONTRIBUTING): the numbers are the evidence for the method, not an instance's configuration. CONTRIBUTING gets one
line saying `analytics/` is the only instance data allowed here and is written by the timer. The README gets one line
under the intro linking `analytics/SUMMARY.md`.

## Tests

`tests/test_analytics.py`, stdlib, fixture transcripts in a temp dir: dedup by message id, week assignment, session
kinds, branch → PR link, file classes, friction counts, alias stability, leak check refusing a planted slug, `publish
--dry-run` against a temporary repo with a fake `gh`. `fleet.py` tests: the pair is written only with the setting.

## Left to the builder

The exact swear root list, the rendering layout, the test-command patterns, how the On-call session is recognised
beyond the channel tag (its tmux session name is a good second signal), and the order of the summary tables.
</content>
</invoke>

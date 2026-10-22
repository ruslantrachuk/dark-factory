# dark-factory plugin

The always-on part of the [dark factory](../../README.md), as a Claude Code plugin. It holds the edges of
agent-driven development in hooks, not in prose:

- **Guard** (`scripts/guard.py`, PreToolUse on `Bash|Edit|Write|MultiEdit|NotebookEdit`). Denies force pushes and
  `+refspec`, a push to the main branch, `--no-verify` and other ways around the git hooks, release-tag pushes, and
  deleting or hard-resetting the main branch. Also at every level it guards the fences themselves: deleting,
  moving, truncating or rewriting `.claude/fences.env` from the shell, lowering `FENCE_LEVEL` (or
  `QUOTA_FAIL_CLOSED` from 1 to 0) with Edit/Write, and any write into the installed plugin (`~/.claude/plugins/**`,
  `$CLAUDE_PLUGIN_ROOT`, the plugin's state in `~/.cache/dark-factory`). At `standard` and `team` it also denies
  `gh pr merge` outside `scripts/merge-feature.sh`, approvals by the agent, and edits to the fence files
  (`.claude/settings*.json`, `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`). Every denial says
  what to do instead.
- **Quota guard** (`scripts/quota.py`). Watches the subscription's 5-hour and 7-day windows: at 80% no new
  subagents or workflows, at 85% wrap up, at 90% only saving work, and the message names when work resumes so an
  autonomous session schedules its own continuation. Details: [docs/quota-guard.md](docs/quota-guard.md).
- **Git-hook repair** (`hooks/ensure-git-hooks.sh`, SessionStart). Points `core.hooksPath` back at `.githooks`
  when a worktree tool moved it; does nothing in a project without `.githooks/`.
- **`/dark-factory:init`**. Scaffolds the solo kit into the current project (below).
- **`/dark-factory:level`** (`scripts/level.py`). Shows the project's level on the ladder
  ([docs/levels.md](../../docs/levels.md)), the signals for the next one and what would change, and writes
  `FENCE_LEVEL` on your yes (below). A SessionStart hook prints one line when it sees a next-level signal.

The hooks read the project from `$CLAUDE_PROJECT_DIR`. A project **opts in** with `.claude/fences.env`; in a
project without it the guards stay silent (one hint line at session start), so installing the plugin for your
user does not fence unrelated repositories.

## Install

```
/plugin marketplace add <owner>/dark-factory
/plugin install dark-factory@dark-factory
```

From a shell: `claude plugin marketplace add <owner>/dark-factory && claude plugin install dark-factory@dark-factory`
(`--scope project` records it in the project's `.claude/settings.json` instead of your user settings).
Requirements: Claude Code, `python3` 3.11+, `git`; `gh` and `jq` for `merge-feature.sh`.

## `/dark-factory:init` — the solo kit

Run it in a project. It shows a dry run, asks for your "yes", never overwrites a file, and adds:

| File | What it is |
|---|---|
| `CLAUDE.md` | a short operating contract: feature branches, merge only through `merge-feature.sh --accepted-by`, the session log (`devlog.md`). Appended once to an existing file |
| `scripts/merge-feature.sh` | the merge transaction: push, PR, wait for CI, record who accepted, merge, clean up; re-runnable after any failure. Main branch and merge strategy filled in |
| `.claude/fences.env` | `FENCE_LEVEL=solo`; the file also opts the project in |
| `.githooks/pre-push` | runs your test command once per push (`TEST_CMD`), otherwise a no-op with a hint |
| `.claude/settings.json` | `extraKnownMarketplaces` + `enabledPlugins`, so collaborators who open the project are offered the plugin. Only missing keys are added |

It also sets `git config core.hooksPath .githooks` unless another hooks path is set. Nothing is committed or
pushed. The kit does not need beads, OpenSpec or a board; the full harness is the `base` template
([templates/](../../templates/README.md)), which enables this plugin too.

## `/dark-factory:level` — the ladder

The level is read from evidence in the project, never stored:

| Level | Evidence |
|---|---|
| 0 solo kit | `.claude/fences.env` exists |
| 1 base template | + `openspec/`, `.beads/` and `CODING_STANDARDS.md` |
| 2 provisioned server | + `.claude/factory/session.env`, or the project listed in `~/.config/dark-factory/projects` |
| 3 client modules | + the feedback-desk files (`scripts/feedback-desk.sh`, `.claude/feedback-desk/config.env`) or prod-monitor (`scripts/ops/prod_monitor/`) |
| 4 team | level 2 + `FENCE_LEVEL=team` (independent of 3) |

It also reports gaps at the current level (base deployed but the fence still `solo`; a server without
`QUOTA_FAIL_CLOSED=1`) and the signals for the next level, read cheaply from files and one `git log` of at most
300 commits: a history of 30 days or more and a long `devlog.md` (→ 1), ten or more open tasks in the bd queue or
other projects already provisioned on this machine (→ 2), a production deploy configuration (→ 3), a second
author (→ 4).

On your yes it writes `FENCE_LEVEL` (and `QUOTA_FAIL_CLOSED`), up or down: `level.py set <level> --apply`. That
works only after your own `/dark-factory:level` prompt, which a UserPromptSubmit hook records as a grant for 60
minutes, used once, or from a terminal. Structural steps (deploy-project, provision-server, a module) it names, and
never runs.

The SessionStart hint is one line, only in an opted-in project with a next-level signal, at most once a day unless
the signals change; `DARK_FACTORY_LEVEL_HINT=off` silences it.

## Fence levels

`.claude/fences.env` → `FENCE_LEVEL`:

| Level | What is enforced |
|---|---|
| `solo` | the guard denies only destructive things (force push, push to main, hook bypass, release-tag pushes, deleting or resetting main) and changes to the fences themselves (`fences.env`, the installed plugin); `merge-feature.sh` still requires `--accepted-by "<name>"`; `--skip-ci "<reason>"` allowed |
| `standard` (default when the line is empty) | `solo` + `gh pr merge` only through `merge-feature.sh`, no approvals by the agent, the fence files are edited by the human only |
| `team` | `standard` + a GitHub approval before every merge; `--skip-ci` refused |

Change the level with `/dark-factory:level`. A static guard reads command text: aliases, variables, a Python
one-liner and scripts written and then run get past it. GitHub branch
protection on the main branch is the recommended backstop. Bypass is for a human only: restart the session with
`GUARD=off claude` (quota: `QUOTA_GUARD=off claude`).

## Uninstall

```
/plugin uninstall dark-factory@dark-factory
/plugin marketplace remove dark-factory
```

The files `init` wrote stay in the project; delete them yourself if you want them gone (`.claude/fences.env`
first — without it nothing is fenced even while the plugin is installed; the guard denies the agent that delete).

When you develop the plugin itself with `claude --plugin-dir <checkout>/plugins/dark-factory` inside an opted-in
checkout, `$CLAUDE_PLUGIN_ROOT` is inside the project and is not fenced; the installed copies under
`~/.claude/plugins` still are.

## Development

The plugin's single source is this directory. `kit/scripts/merge-feature.sh` is a copy of
`templates/base/scripts/merge-feature.sh`: edit the canonical file, then run `scripts/sync-plugin-kit.sh` from the
repository root (`--check` fails when they differ; `scripts/test_repo.py` runs it).

```bash
python3 plugins/dark-factory/scripts/test_guard.py
python3 plugins/dark-factory/scripts/test_quota.py
python3 plugins/dark-factory/scripts/test_init_kit.py
python3 plugins/dark-factory/scripts/test_level.py
claude plugin validate plugins/dark-factory && claude plugin validate .
```

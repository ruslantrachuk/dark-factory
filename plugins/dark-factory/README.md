# dark-factory plugin

The always-on part of the [dark factory](../../README.md), as a Claude Code plugin. It holds the edges of
agent-driven development in hooks, not in prose:

- **Guard** (`scripts/guard.py`, PreToolUse on `Bash|Edit|Write|MultiEdit|NotebookEdit`). Denies force pushes and
  `+refspec`, a push to the main branch, `--no-verify` and other ways around the git hooks, release-tag pushes, and
  deleting or hard-resetting the main branch. At `standard` and `team` it also denies `gh pr merge` outside
  `scripts/merge-feature.sh`, approvals by the agent, and edits to the fence files (`.claude/settings*.json`,
  `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`). Every denial says what to do instead.
- **Quota guard** (`scripts/quota.py`). Watches the subscription's 5-hour and 7-day windows: at 80% no new
  subagents or workflows, at 85% wrap up, at 90% only saving work, and the message names when work resumes so an
  autonomous session schedules its own continuation. Details: [docs/quota-guard.md](docs/quota-guard.md).
- **Git-hook repair** (`hooks/ensure-git-hooks.sh`, SessionStart). Points `core.hooksPath` back at `.githooks`
  when a worktree tool moved it; does nothing in a project without `.githooks/`.
- **`/dark-factory:init`**. Scaffolds the solo kit into the current project (below).

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

## Fence levels

`.claude/fences.env` → `FENCE_LEVEL`:

| Level | What is enforced |
|---|---|
| `solo` | the guard denies only destructive things (force push, push to main, hook bypass, release-tag pushes, deleting or resetting main); `merge-feature.sh` still requires `--accepted-by "<name>"`; `--skip-ci "<reason>"` allowed |
| `standard` (default when the line is empty) | `solo` + `gh pr merge` only through `merge-feature.sh`, no approvals by the agent, the fence files are edited by the human only |
| `team` | `standard` + a GitHub approval before every merge; `--skip-ci` refused |

A static guard reads command text: aliases, variables and scripts written and then run get past it. GitHub branch
protection on the main branch is the recommended backstop. Bypass is for a human only: restart the session with
`GUARD=off claude` (quota: `QUOTA_GUARD=off claude`).

## Uninstall

```
/plugin uninstall dark-factory@dark-factory
/plugin marketplace remove dark-factory
```

The files `init` wrote stay in the project; delete them by hand if you want them gone (`.claude/fences.env`
first — without it nothing is fenced even while the plugin is installed).

## Development

The plugin's single source is this directory. `kit/scripts/merge-feature.sh` is a copy of
`templates/base/scripts/merge-feature.sh`: edit the canonical file, then run `scripts/sync-plugin-kit.sh` from the
repository root (`--check` fails when they differ; `scripts/test_repo.py` runs it).

```bash
python3 plugins/dark-factory/scripts/test_guard.py
python3 plugins/dark-factory/scripts/test_quota.py
python3 plugins/dark-factory/scripts/test_init_kit.py
claude plugin validate plugins/dark-factory && claude plugin validate .
```

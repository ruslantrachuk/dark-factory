# dark-factory plugin

The part of the [dark factory](../../README.md) that is always on, packaged as a Claude Code plugin. Its hooks,
not written instructions, keep the agent away from the decisions that belong to a human:

- **Guard** (`scripts/guard.py`, PreToolUse on `Bash|Edit|Write|MultiEdit|NotebookEdit`). Denies force pushes and
  `+refspec`, a push to the main branch, `--no-verify` and other ways around the git hooks, release-tag pushes, and
  deleting or hard-resetting the main branch. Also at every level it guards the fences themselves: deleting,
  moving, truncating or rewriting `.claude/fences.env` from the shell, lowering `FENCE_LEVEL` (or
  `QUOTA_FAIL_CLOSED` from 1 to 0) with Edit/Write, and any write into the installed plugin (`~/.claude/plugins/**`,
  `$CLAUDE_PLUGIN_ROOT`, the plugin's state in `~/.cache/dark-factory`). At `standard` and `team` it also denies
  `gh pr merge` outside `scripts/merge-feature.sh`, approvals by the agent, and edits to the fence files
  (`.claude/settings*.json`, `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`). Every denial says
  what to do instead. The guard is a seatbelt, not a sandbox: see [What the guard is and is not](#what-the-guard-is-and-is-not).
- **Quota guard** (`scripts/quota.py`). Watches the subscription's 5-hour and 7-day windows: at 80% no new
  subagents or workflows, at 85% wrap up, at 90% only saving work, and the message names when work resumes so an
  autonomous session schedules its own continuation. Details: [docs/quota-guard.md](docs/quota-guard.md).
- **Git-hook repair** (`hooks/ensure-git-hooks.sh`, SessionStart). Points `core.hooksPath` back at `.githooks`
  when a worktree tool moved it; does nothing in a project without `.githooks/`.
- **`/dark-factory:init`**. Scaffolds the solo kit into the current project (below).
- **`/dark-factory:level`** (`scripts/level.py`). Shows the project's level on the ladder
  ([docs/levels.md](../../docs/levels.md)), the signals for the next one and what would change, and writes
  `FENCE_LEVEL` on your yes (below). A SessionStart hook prints one line when it sees a next-level signal.
- **`/dark-factory:statusline`** (`scripts/statusline.py`). Installs a statusLine wrapper that feeds the quota
  guard exact numbers and keeps your existing statusline; dry run first, `--uninstall` restores it.
- **`/dark-factory:feature`**. Runs the feature pipeline (`workflows/`) with the project's
  `.claude/feature-pipeline.json`, so the settings are not passed by hand.

The hooks read the project from `$CLAUDE_PROJECT_DIR`. A project **opts in** with `.claude/fences.env`; in a
project without it the guards stay silent (one hint line at session start), so installing the plugin for your
user does not fence unrelated repositories.

## Install

```
/plugin marketplace add ruslantrachuk/dark-factory
/plugin install dark-factory@dark-factory
```

From a shell: `claude plugin marketplace add ruslantrachuk/dark-factory && claude plugin install dark-factory@dark-factory`
(`--scope project` records it in the project's `.claude/settings.json` instead of your user settings).
Requirements: Claude Code, `python3` 3.11+, `git`; `gh` and `jq` for `merge-feature.sh`.

## `/dark-factory:init` — the solo kit

Run it in a project. It shows a dry run, asks for your "yes", never overwrites a file, and adds:

| File | What it is |
|---|---|
| `CLAUDE.md` | a short operating contract: feature branches, merge only through `merge-feature.sh --accepted-by`, the PR description as the record of work (`## Done` / `## Decisions` / `## Open questions`). Appended once to an existing file |
| `scripts/merge-feature.sh` | the merge transaction: push, PR, check the PR description, wait for CI, record who accepted, merge with the description as the merge commit message, clean up; re-runnable after any failure. Main branch and merge strategy filled in |
| `.claude/fences.env` | `FENCE_LEVEL=solo`; the file also opts the project in |
| `.githooks/pre-push` | runs your test command once per push (`TEST_CMD`), otherwise a no-op with a hint |
| `.claude/settings.json` | `extraKnownMarketplaces` + `enabledPlugins`, so collaborators who open the project are offered the plugin. Only missing keys are added |

It also sets `git config core.hooksPath .githooks` unless another hooks path is set. Nothing is committed or
pushed. The kit does not need beads, OpenSpec or a board; the full harness is the `base` template
([templates/](../../templates/README.md)), which enables this plugin too.

## `/dark-factory:level` — the ladder

`/dark-factory:level` (`scripts/level.py`) reads the project's level from evidence in the project (it is never
stored), reports gaps at the current level and the signals for the next one, and changes `FENCE_LEVEL` (and
`QUOTA_FAIL_CLOSED`) up or down on your "yes". It writes only after you typed `/dark-factory:level <target>`
yourself: a UserPromptSubmit hook records a one-shot grant for that target, valid for 10 minutes; a bare
`/dark-factory:level` only reports. Lowering takes effect only once the lowered `fences.env` is merged into main, because
`origin/main` sets the floor. Structural steps (deploy-project, provision-server, a module) it names and never runs.
The SessionStart hint is one line, at most once a day unless the signals change; `DARK_FACTORY_LEVEL_HINT=off`
silences it.

The ladder, the evidence for each level, the signals and the full fence-level table are in
[docs/levels.md](../../docs/levels.md).

## What the guard is and is not

The guard is a static reader of tool calls. It stops an agent's mistakes and the common shortcuts; it is not a
sandbox against a determined or hostile agent. It cannot see through a script written to a file and then run, an
alias defined elsewhere, a subprocess, or an arbitrary interpreter. The real gates are GitHub branch protection or
rulesets on main, required reviews and the Claude Code sandbox; turn on branch protection at every level.
`--accepted-by` names who accepted a merge: below `team` the name is recorded, not verified; at `team` the GitHub
approval is verified. See [SECURITY.md](../../SECURITY.md) and the [threat model](../../docs/threat-model.md).
Bypass is for a human only: restart the session with `GUARD=off claude` (quota: `QUOTA_GUARD=off claude`).

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

# Changelog

All notable changes to the dark-factory plugin and canon. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are sequential: `v1`, `v2`, … (tag `v<N>` on main,
plugin version `<N>.0.0`; see [CONTRIBUTING.md](CONTRIBUTING.md#versioning)). A release that breaks a deployed project
has a **Breaking** section with the upgrade steps.

## [1] — 2026-10-22

The first release: the method (`docs/`) and the Claude Code plugin that carries everything a project needs.

### The lifecycle

- **Intake**: requests arrive from a tracker or from the client's Telegram group through the On-call agent; each
  becomes a board card and a change. `size-task` sizes new work (trivial, small, large) and proposes the branch name
  and phases; `wsjf` ranks the queue.
- **Spec**: every change lives in `openspec/changes/<slug>/` (a small one is a proposal and tasks). Branch
  `<type>/<ID>-<slug>`; the `bd` queue is one local store per project, outside git.
- **Development**: roles as plugin agents (`tech-lead`, `product-owner`, `reviewer`), a project overrides one with
  `.claude/agents/<name>.md`; the feature-pipeline workflows (`feature-auto`, `feature-core`, `feature-lite`,
  `/dark-factory:feature`) for unattended runs, with an agent-call cap and per-role models.
- **Review and merge**: the PR description (`## Done`, `## Decisions`, `## Open questions`) is the record of the work;
  `merge-feature.sh` refuses a PR without it, merges after green CI and writes it into the merge commit
  (`--skip-ci "<reason>"` runs the local gate where Actions cannot run; refused at `team`).
- **Dev stand and acceptance**: a merge puts a feature on the dev stand (the environment that runs `main`); the
  requester accepts it there (label `accepted`, comment `accepted by <who>, <link or "permission dialog">`).
- **Release**: production is built only from a `vYYYY.MM.DD.N` tag cut by `release.sh`, which ships all of `main`
  since the last tag and refuses while a merge lacks acceptance (`--owner-accepts`, `--include-unaccepted "<who
  allowed>"`, `--list-unaccepted`).
- **Monitoring and support**: the prod monitor watches production and reports through On-call; On-call `accept` and
  `release` subcommands check the sender against the PR's requester and `DESK_OWNER_IDS`.

### The fences

- **Guard** (PreToolUse hook): no force push, no push to main, no hook bypass, no merge without a named human
  acceptance; the fences and the installed plugin are protected at every level. Release tags and acceptance marks are
  asked ("Yes = you accept it"); the On-call may run only `feedback-desk.sh accept|release`.
- **Quota guard**: a Claude subscription ceiling that stops work before it hits the limit and lets the save steps
  through; usage is refreshed in the background. A statusline shows the quota and the fence level.
- **Levels** 0 to 4 (`/dark-factory:level`): fences and tools grow with the project; a grant is bound to the typed
  target, used once, and a lowered level counts only once merged into `main`.
- [SECURITY.md](SECURITY.md) and a [threat model](docs/threat-model.md); release hardening (tag ruleset on `v*`,
  read-only CI tokens, actions pinned to commit SHAs).

### The factory over projects

- `/dark-factory:init` (the solo starter kit), `/dark-factory:add base` (the full harness) and
  `/dark-factory:add factory` (the skeleton of your own factory repository, see
  [docs/your-factory.md](docs/your-factory.md)).
- `/dark-factory:provision-server` keeps each project's session and On-call alive through reboots;
  `/dark-factory:factory-status` shows sessions, On-call, monitor, quota, queue and each project's lag behind the
  plugin version. `harness-diff.sh` reconciles a project's files with the template.
- Projects pin the plugin to a release (`"ref": "v1"` on the marketplace in `.claude/settings.json`).

### The modules

`/dark-factory:add <module>`: owner steps first, then files, filling in, tests, server units and a status check.

- `base` (with releases by tag when there is production), `on-call` (Telegram feedback desk), `monitor`,
  `release`, `observability`, `code-audit`, `feature-pipeline`.

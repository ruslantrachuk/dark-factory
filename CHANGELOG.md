# Changelog

All notable changes to the dark-factory plugin and canon. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/)
and are tagged `vX.Y.Z` (see [CONTRIBUTING.md](CONTRIBUTING.md#versioning)).

## [0.3.0] — Unreleased

A hardening round before the first public release.

### Security

- Guard: closed bypasses of the push, merge and hook-skip rules found in review (more command shapes recognised;
  the installed plugin and its state are fenced at every level).
- Fence-level grants are bound to the target the owner typed (`/dark-factory:level <target>`), used once, and a
  lowered level takes effect only once it is merged into main (`origin/main` sets the floor).
- Quota guard: harder to talk past at the ceiling; the usage data is refreshed in the background, so a stale reading
  no longer lets work through.
- Release hardening: a tag ruleset on `v*`, read-only CI tokens and actions pinned to commit SHAs.
- On-call, prod monitor and fleet: tighter tool lists, the monitor channel refuses events without its bearer token,
  safer fleet provisioning.
- `deploy-project` applies and verifies branch protection on main and a ruleset on release tags after the owner's
  "yes", and recommends a separate GitHub identity for the agent; it is invoked by the human only.
- [SECURITY.md](SECURITY.md) and a [threat model](docs/threat-model.md).

### Added

- `/dark-factory:feature` — launches the feature pipeline with the project's `.claude/feature-pipeline.json`.
- Feature pipeline: `maxAgents`, an agent-call cap for every run (children included), so unattended and scheduled runs
  have a cost limit; `models` pins a model per role.
- A statusline skill showing the quota and the fence level.
- Solo merge without CI: `merge-feature.sh --skip-ci "<reason>"` runs the local gate when Actions cannot run (refused
  at `team`).
- Root CI (`.github/workflows/test.yml`) running the repository's test suites.
- The base skill `size-task`: sizes new work (trivial, small, large) and proposes the branch name and phases.
- `/dark-factory:add <module>` installs `base` or a module (`on-call`, `monitor`, `release`, `observability`,
  `code-audit`, `feature-pipeline`) from the plugin: the owner's own steps first, then files, filling in, tests, server
  units and a status check. `/dark-factory:provision-server` and `/dark-factory:factory-status` are plugin commands.

### Changed

- The plugin is self-contained: the templates, the factory scripts (`fleet.py`, `deploy-base.sh`) and the factory
  skills live in `plugins/dark-factory/`, so a user installs the plugin and needs no checkout of this repository.
  `/dark-factory:init` takes `merge-feature.sh` from `templates/base`, so the plugin's `kit/` copy is gone.
- Releases by tag (`release-tag`) are part of base when the project has production; level 3 is the client modules only
  (On-call, monitor, observability). `.harness/base-sha` holds the plugin's release tag for an installed plugin.
- Feature pipeline: no model ids in the scripts — an agent without a pinned model inherits the session's model; `args`
  are taken as JSON values (a JSON string is still accepted).
- The marketplace is published as `ruslantrachuk/dark-factory`; projects pin it to a release tag.
- Documentation brought in line with the current behaviour.
- The record of work is the PR description (`## Done`, `## Decisions`, `## Open questions`): `merge-feature.sh`
  refuses a PR without them and writes the description into the merge commit, so `git log --merges` is the history.
  The session header shows the branch's PR, the tasks in progress and the latest merges; the new base skill `save`
  writes the state before `/clear`; the feature pipeline returns the description (`prBody`).
- The bd execution queue is one local store per project, outside git, shared by every worktree (`BEADS_DIR` from the
  SessionStart hook); `merge-feature.sh` closes the branch's task after the merge, with nothing committed.
- `/dark-factory:level`: level 1 is read from `openspec/` and `CODING_STANDARDS.md`; its signal counts merge commits,
  and open tasks come from `bd count`.
- Quota guard: at the ceiling the save targets are git, bd, the PR description (`gh pr edit`, `gh pr create --draft`)
  and Claude Code's project memory.

- The branch is the change key: `<type>/<ID>-<slug>` with a tracker, `<type>/<slug>` without; the spec folder is
  `openspec/changes/<slug>/`. `merge-feature.sh` finds the task to close by the tracker ID (`external_ref`) or by the
  slug and phase labels (`change:<slug>`, `phase:<K>`). The feature pipeline takes `slug`, `trackerId` and `type`.
- `merge-feature.sh` has no `--accepted-by`: at `solo` and `standard` the agent merges after green CI and its own
  review; at `team` the GitHub approval stays required.
- The project's `CLAUDE.md` holds project sections only and imports the canon part from `.claude/canon/CLAUDE.md`,
  which is replaced whole on upgrade. The `openspec` skill describes only our format.

### Removed

- The release train: `releaseLine`, `openspec/CURRENT_TRAIN` and the `r*` release tag. The vendored OpenSpec
  schemas and `scripts/fetch-openspec-docs.sh`.
- `devlog.md`, its `merge=union` rule and the pre-push and merge gates on it.
- The queue file in git and its machinery: `scripts/bd-export.sh`, `scripts/bd-queue-guard.sh`,
  `scripts/beads-queue-line.sh`, the pre-commit, post-merge and post-checkout hooks.

## [0.2.0]

### Added

- The first public dark-factory plugin: the guard hook, the subscription quota guard, git-hook self-repair,
  `/dark-factory:init` (the solo kit), `/dark-factory:level` (the level ladder) and the feature pipeline workflows
  (`feature-auto`, `feature-core`, `feature-lite`).
- The canon: the method (`docs/`) and the templates (`base` and the modules).

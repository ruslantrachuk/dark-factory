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

### Changed

- Feature pipeline: no model ids in the scripts — an agent without a pinned model inherits the session's model; `args`
  are taken as JSON values (a JSON string is still accepted).
- The marketplace is published as `ruslantrachuk/dark-factory`; projects pin it to a release tag.
- Documentation brought in line with the current behaviour.

## [0.2.0]

### Added

- The first public dark-factory plugin: the guard hook, the subscription quota guard, git-hook self-repair,
  `/dark-factory:init` (the solo kit), `/dark-factory:level` (the level ladder) and the feature pipeline workflows
  (`feature-auto`, `feature-core`, `feature-lite`).
- The canon: the method (`docs/`) and the templates (`base` and the modules).

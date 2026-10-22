# Dark factory

**Claude Code can write most of your code. This repository is the rest of the pipeline around it:** requirements,
tests, review, merge, release, production monitoring and client feedback. The agent does the work in the middle;
a human decides at the edges: what to build, and whether the result is accepted.

It is a Claude Code plugin (with the project templates and the factory scripts inside it) and a written method. A small
studio uses it daily on client projects. MIT licensed. Most modules are **experimental**: they run in one or two
projects so far.

## What you get

- **Safety rails.** A hook checks every command the agent runs and stops the risky ones (force pushes, pushing
  to main, skipping the git hooks, merging behind your back), with a note on what to do instead.
- **No surprise quota cut-offs.** Near the subscription limit the agent wraps up and saves its work, and an
  unattended session books its own restart for when the limit resets.
- **One-command merges.** Once CI is green, one script pushes, opens the PR, waits for CI, merges and
  writes the PR description into the merge commit.
- **Specs, a task queue and tests that stay honest.** Specs become a task queue in the repository; tests are
  sorted into layers, and a test that cheats its layer fails.
- **Optional extras.** A feature pipeline, an On-call agent in the client's chat, a production monitor that costs
  no tokens until something breaks, and tooling to run many projects on one server.

## Start small

Five minutes, no server, board or chat. In Claude Code, inside your project:

```
/plugin marketplace add ruslantrachuk/dark-factory
/plugin install dark-factory@dark-factory
/dark-factory:init
```

**Requirements:** Claude Code, Python 3.11+, git; `gh` (logged in) and `jq` for merges.

```
What changes after init
  • The guard denies force pushes, pushes to main, --no-verify, tag pushes; fence edits need your yes.
  • The quota guard steps in at 80 / 85 / 90 % of the 5-hour and 7-day windows (table below).
  • You merge with scripts/merge-feature.sh once CI is green; no CI yet? It runs your tests locally.
  • Nothing else changes: no board, no server, no new workflow, and nothing is committed for you.
```

`init` shows a dry run, asks for your "yes" and never overwrites a file. For the full harness (specs, task queue,
test pyramid, CI tiers) run `/dark-factory:add base` instead, or later. To remove it, see
[Uninstall](plugins/dark-factory/README.md#uninstall). A worked example of a first session is in
[docs/getting-started.md](docs/getting-started.md#a-first-session-illustrative).

| Quota used | What the quota guard does |
|---|---|
| 80 % | no new subagents or workflows |
| 85 % | asks the agent to wrap up |
| 90 % | only saving work; an unattended session schedules its continuation for after the reset |

## What it denies, and what it doesn't

The guard is a seatbelt: it reads each tool call before it runs and stops an agent's mistakes and common
shortcuts. It is not a sandbox against a determined or hostile agent: it cannot see through a script written and
then run, an alias defined elsewhere, a subprocess or an arbitrary interpreter. Below the `team`
level the agent merges itself after green CI and its own review; at `team` a GitHub approval is required.
The real gates are GitHub branch protection or rulesets on main, required reviews and the Claude Code sandbox, so
turn on branch protection whatever level you run. Details: [SECURITY.md](SECURITY.md) and the
[threat model](docs/threat-model.md).

When CI exists but cannot run (for example, Actions is blocked by billing), the owner can merge with
`--skip-ci "<reason>"`: the script runs the local gate instead and marks the merge prominently. At `team` both
that and merging without CI are refused.

## Going further

**The full lifecycle.** `/dark-factory:add base` adds OpenSpec specs, the `bd` task queue, the enforced test pyramid,
CI tiers, the PR description as the record of work and skills (and releases by tag when the project has production);
`/dark-factory:add on-call`, `monitor` and the other modules add an On-call agent in the client chat, a production
monitor and more. Each lifecycle stage, what the factory puts there and what the human decides:
[docs/process.md](docs/process.md). The steps: [docs/getting-started.md](docs/getting-started.md).

**Levels.** A project takes on as much as it needs, from the plugin alone (solo) to a team with required approvals.
`/dark-factory:level` shows where a project stands and what the next step would change. The ladder and the fence
levels: [docs/levels.md](docs/levels.md).

**The factory over your projects.** One command keeps every project's sessions running on your server across
reboots (`/dark-factory:provision-server`) and one shows the state of all of them (`/dark-factory:factory-status`);
a registry of projects, kept in a private repository of your own, records what each project runs:
[docs/process.md](docs/process.md#lifecycle-stages-and-layers). Nothing needs a checkout of this repository: the
plugin carries the templates and the scripts.

**Method and implementation.** The method in [`docs/`](docs/) is tool-agnostic: it names functions (a board, an
execution queue, a client chat, a code host, CI) and what each must guarantee. This repository implements it on one
supported stack (Claude Code, GitHub, Linear, beads, Telegram, Postgres) and marks the seam where each tool can be
swapped: [docs/functions.md](docs/functions.md).

**Good fit:** you ship software with Claude Code on a subscription, on GitHub, and want the agent to carry features
from spec to merge while you review. **Not a fit:** you want a hosted product, a different agent, or no human
acceptance step.

## Repository map

| Path | What is inside |
|---|---|
| [docs/](docs/) | the method: [getting started](docs/getting-started.md), [process](docs/process.md), [levels](docs/levels.md), [methodology](docs/methodology.md), [map](docs/map.md), [functions](docs/functions.md), [open questions](docs/open-questions.md), [layers](docs/layers/) and [practices](docs/practices/README.md) |
| [plugins/dark-factory/](plugins/dark-factory/README.md) | the plugin, everything a user installs: guard hook, quota guard, the commands (`init`, `add`, `level`, `feature`, `provision-server`, `factory-status`), the feature pipeline, the [templates](plugins/dark-factory/templates/README.md) (`base` and the modules) and the factory scripts (`fleet.py`, `deploy-base.sh`); this repository is its marketplace |
| [scripts/](scripts/) | the repository's own checks (`test_repo.py`) |

## License

MIT — see [LICENSE](LICENSE). Third-party components and their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgements

Ideas and techniques were borrowed from:
- [pavel-molyanov/molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT);
- [OpenSpec](https://github.com/Fission-AI/OpenSpec);
- [beads](https://github.com/steveyegge/beads);
- the `openspec-to-beads` skill in [lucastamoios/celeiro](https://github.com/lucastamoios/celeiro) (our version is a rewrite inspired by it);
- the [Superpowers](https://github.com/obra/superpowers) plugin for Claude Code.

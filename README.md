# Dark factory

**Claude Code can write most of your code. This repository is the rest of the pipeline around it:** the full software
lifecycle with an agent in the middle and a human at the edges. A human decides what to build and whether the result is
accepted; the agent does the work between.

The lifecycle: **requirements** (intake, spec) → **development** (branch, tests, task queue) → **review** (PR, CI,
merge) → **dev stand** (`main` runs here; a merge is not acceptance) → **acceptance** (the person who asked says yes) →
**release** (a tag, all of `main`) → **monitoring** (a watchdog that costs no tokens until something breaks) →
**support and feedback** (the client's chat, an On-call agent).

Over the projects sits **the factory**: provisioning a server so every project's session comes back after a reboot,
one status of all projects, keeping them current with the plugin, and a registry in a repository of your own
([your own factory](docs/your-factory.md)). Each stage, what the factory puts there and what the human decides:
[docs/process.md](docs/process.md).

It is a Claude Code plugin (with the project templates and the factory scripts inside it) and a written method. A small
studio uses it daily on client projects. MIT licensed. Most modules are **experimental**: they run in one or two
projects so far.

## What you get

- **Safety rails.** A hook checks every command the agent runs and stops the risky ones (force pushes, pushing
  to main, skipping the git hooks, merging behind your back), with a note on what to do instead.
- **No surprise quota cut-offs.** Near the subscription limit the agent wraps up and saves its work, and an
  unattended session books its own restart for when the limit resets.
- **One-command merges and honest acceptance.** Once CI is green, one script pushes, opens the PR, waits for CI,
  merges and writes the PR description into the merge commit. A merge lands on the dev stand; a release refuses while
  a merge since the last tag has not been accepted by the person who asked for it.
- **Specs, a task queue and tests that stay honest.** Each change is a folder of spec files, and the work becomes a
  task queue; tests are sorted into layers, and a test that cheats its layer fails.
- **Roles and sizing.** `size-task` sizes new work and proposes the branch and phases; the `tech-lead`, `reviewer` and
  `product-owner` roles are agents you call by hand or the pipeline calls, and a project can override any of them.
- **Optional extras.** An On-call agent in the client's chat, a production monitor that costs no tokens until
  something breaks, and tooling to run many projects on one server.

## Supported stack

The method in [`docs/`](docs/) is tool-agnostic: it names functions (a board, an execution queue, a client chat, a code
host, CI) and what each must guarantee. **The implementation supports one stack, with marked seams:** Claude Code,
GitHub, Linear (the board), Telegram (the client chat), beads `bd` (the task queue) and Postgres (the monitor's
read-only snapshot). There are no adapters and no tools config; each skill or module that depends on a tool has a
**Seam** line naming what to rewrite to use another one. [docs/functions.md](docs/functions.md).

## Start small

Five minutes, no server, board or chat. In Claude Code, inside your project:

```
/plugin marketplace add ruslantrachuk/dark-factory
/plugin install dark-factory@dark-factory
/dark-factory:init
```

Releases are sequential tags, `v1`, `v2`, … ([CHANGELOG](CHANGELOG.md)). To stay on one, add the marketplace at its tag
(`/plugin marketplace add ruslantrachuk/dark-factory#v1`); a project set up with `/dark-factory:init` or
`/dark-factory:add base` carries that pin in its `.claude/settings.json` (`"ref": "v1"`), and moving to the next release
is a deliberate change of it.

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

**The full lifecycle.** `/dark-factory:add base` adds the spec folders (`openspec/changes/`, used as a folder
convention: full OpenSpec, the living spec and its CLI, is not used and is an option for larger projects), the `bd`
task queue, the enforced test pyramid, CI tiers, the PR description as the record of work, the dev stand and skills
(and releases by tag when the project has production); `/dark-factory:add on-call`, `monitor` and the other modules add
an On-call agent in the client chat, a production monitor and more. The steps:
[docs/getting-started.md](docs/getting-started.md).

**Start small, climb when it pays.** Level 0 is the plugin alone (`/dark-factory:init`); level 1 is the full harness;
level 2 adds a server and unattended work; level 3 the client modules; level 4 a team with required approvals.
`/dark-factory:level` shows where a project stands and what the next step would change. The ladder and the fence
levels: [docs/levels.md](docs/levels.md).

**Unattended runs.** The feature-pipeline workflows (`/dark-factory:feature`) are token-expensive and meant for big
tasks left to run alone, with a cap on agent calls; in an interactive session you use the skills and roles directly.

**The factory over your projects.** `/dark-factory:provision-server` keeps each project's sessions running on your
server across reboots and `/dark-factory:factory-status` shows the state of all of them, including how far each project
lags behind the plugin. If you run more than one project, keep a repository of your own for the factory:
[docs/your-factory.md](docs/your-factory.md). Nothing needs a checkout of this repository: the plugin carries the
templates and the scripts.

**Good fit:** you ship software with Claude Code on a subscription, on GitHub, and want the agent to carry features
from spec to merge while you review. **Not a fit:** you want a hosted product, a different agent, or no human
acceptance step.

## Repository map

| Path | What is inside |
|---|---|
| [docs/](docs/) | the method: [getting started](docs/getting-started.md), [process](docs/process.md), [levels](docs/levels.md), [your own factory](docs/your-factory.md), [methodology](docs/methodology.md), [map](docs/map.md), [functions](docs/functions.md), [open questions](docs/open-questions.md), [layers](docs/layers/) and [practices](docs/practices/README.md) |
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

# Dark factory

**Claude Code can write most of your code. This repository is the rest of the pipeline around it:** requirements,
tests, review, merge, release, production monitoring and client feedback. The agent does the work in the middle;
a human decides at the edges: what to build, and whether the result is accepted.

It is a Claude Code plugin, a set of project templates, a few factory-level scripts and a written method. A small
studio uses it daily on client projects. MIT licensed. Most modules are **experimental**: they run in one or two
projects so far.

## What you get

- **Safety rails.** A hook checks every command the agent runs and stops the risky ones (force pushes, pushing
  to main, skipping the git hooks, merging behind your back), with a note on what to do instead.
- **No surprise quota cut-offs.** Near the subscription limit the agent wraps up and saves its work, and an
  unattended session books its own restart for when the limit resets.
- **One-command merges.** After you say "accepted", one script pushes, opens the PR, waits for CI, merges and
  records who accepted.
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

`init` shows a dry run, asks for your "yes" and never overwrites a file. To remove it, see
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

**The full lifecycle.** The `base` template adds OpenSpec specs, the `bd` task queue, the enforced test pyramid,
CI tiers, the PR description as the record of work and skills; modules add a server, an On-call agent in the client chat, a production
monitor and releases by tag. Each lifecycle stage, what the factory puts there and what the human decides:
[docs/process.md](docs/process.md). The steps: [docs/getting-started.md](docs/getting-started.md).

**Levels.** A project takes on as much as it needs, from the plugin alone (solo) to a team with required approvals.
`/dark-factory:level` shows where a project stands and what the next step would change. The ladder and the fence
levels: [docs/levels.md](docs/levels.md).

**The factory over your projects.** One registry of projects, a command that keeps every project's sessions running
on your server across reboots, and a status view of all of them (`provision-server`, `factory-status`,
`scripts/fleet.py`). Keep this repository (the canon) unchanged and put your registry in a private repository of
your own: [docs/process.md](docs/process.md#lifecycle-stages-and-layers).

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
| [plugins/dark-factory/](plugins/dark-factory/README.md) | the plugin: guard hook, quota guard, `/dark-factory:init`, `/dark-factory:level`, the feature pipeline; this repository is its marketplace |
| [templates/](templates/README.md) | the `base` template and the modules |
| [scripts/](scripts/) | `deploy-base.sh`, `fleet.py`, `sync-plugin-kit.sh` |
| [.claude/skills/](.claude/skills/) | `deploy-project`, `provision-server`, `factory-status` |

## License

MIT — see [LICENSE](LICENSE). Third-party components and their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgements

Ideas and techniques were borrowed from:
- [pavel-molyanov/molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT);
- [OpenSpec](https://github.com/Fission-AI/OpenSpec);
- [beads](https://github.com/steveyegge/beads);
- the `openspec-to-beads` skill in [lucastamoios/celeiro](https://github.com/lucastamoios/celeiro) (our version is a rewrite inspired by it);
- the [Superpowers](https://github.com/obra/superpowers) plugin for Claude Code.

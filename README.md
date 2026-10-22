# Dark factory

**Claude Code can write most of your code. This repository is the rest of the production line around it:**
requirements, tests, review, merge, release, production monitoring and client feedback. The agent does the work
in the middle, and a human decides at the edges: what to build, and whether the result is accepted.

It is a Claude Code plugin, a set of project templates, factory-level scripts and a written method. A small studio uses it daily on
real client projects. MIT licensed. Most modules are marked **experimental**, meaning they run in one or two
projects so far.

---

## What you get

- **A quota guard** (the `dark-factory` plugin, [plugins/dark-factory](plugins/dark-factory/README.md)). Hooks watch the subscription's 5-hour and 7-day
  windows:
  - at 80% they stop new subagents and workflows;
  - at 85% they ask the agent to wrap up;
  - at 90% they allow only saving work, and the session schedules its own continuation after the reset instead of
    dying mid-task.
- **Guard rails written as code, not prose.** A PreToolUse guard in the same plugin denies `gh pr merge`, force-pushes, pushes to
  main, `--no-verify` and release-tag pushes outside the scripts made for them, at a strictness you choose
  (`solo` / `standard` / `team`). The pre-push hook runs the tests and checks the session log.
- **A merge transaction** (`merge-feature.sh`). One command pushes, opens the PR, waits for CI, merges, closes
  the task and updates main. It records who accepted the change, tells a network failure apart from red CI, and
  can be re-run after any failure.
- **Specs before code.** An OpenSpec change (proposal, design, phased tasks) becomes a task graph in the
  repository's own queue ([beads](https://github.com/steveyegge/beads)), with one branch per epic.
- **A test pyramid that is enforced**, not just described. Each layer is a directory plus a marker, and a test
  fails when a unit test reaches for the network or the database.
- **A feature pipeline** (Workflow scripts shipped in the plugin): plan → critic → test-first chunks in parallel → integration →
  review. It runs in its own worktree and stops before the PR.
- **Production monitoring that doesn't burn tokens.** A cron watchdog with plain rules wakes a read-only agent
  only on a real anomaly. The agent's verdict goes to the client chat and the development session.
- **Client chat → development session.** An On-call session with a restricted tool set holds the client's
  Telegram group. It acknowledges requests and forwards them to the development session as data, not
  instructions.
- **Fleet tooling.** One command keeps every project's sessions running on your server across reboots. Another
  shows how every project is doing.

## Start small

Five minutes, no server, Linear or Telegram. In Claude Code, inside your project:

```
/plugin marketplace add <owner>/dark-factory
/plugin install dark-factory@dark-factory
/dark-factory:init
```

The plugin brings the guard hook and the quota guard. `/dark-factory:init` shows a dry run, asks for your "yes" and
never overwrites a file. It adds a short operating contract to `CLAUDE.md`, the merge script, a pre-push test gate
and `.claude/fences.env` at the `solo` level. Details: [plugins/dark-factory/README.md](plugins/dark-factory/README.md).

**The full path** is the plugin plus the `base` template: the test pyramid, CI, the queue, OpenSpec and the skills.
Clone this repository, open Claude Code in it and ask: "deploy project my-app into ~/code/my-app" (the
`deploy-project` skill; `scripts/deploy-base.sh ~/code/my-app --dry-run` shows the files first). Add the server, the
On-call session and the monitor later, one module at a time. Steps, requirements and glossary:
[docs/getting-started.md](docs/getting-started.md).

**Good fit:** you ship software with Claude Code on a subscription, for yourself or for clients, on GitHub, and you
want the agent to carry features from spec to merge while you review.

**Not a fit:** you want a hosted product, a different agent, or no human acceptance step.

---

## The lifecycle

| Stage | What the factory puts in place | The human decides |
|---|---|---|
| **Requirements** | A request becomes a card on the board. A card becomes an OpenSpec change: a proposal with the confirmed user-facing surfaces, a design, phased tasks. An approved change becomes a task graph in the queue | what to build; approves the spec |
| **Development** | The operating contract in `CLAUDE.md`; one epic = one branch = one PR; the feature pipeline; a session log (`devlog.md`) the agent reads at the start of every session | scope |
| **Testing** | The enforced test pyramid; pre-push gates; CI tiers (quick on every push, full + browser before a release); secret scanning; a review contract that demands evidence for every finding; a preview environment | accepts the result |
| **Release** | The merge transaction; release trains `r{N}`. Optionally, production only from tags: `vYYYY.MM.DD.N`, a forward-only `release` branch, generated notes, rollback by tag | "ship it" |
| **Monitoring** | From day one: structured logs with `correlation_id`, LLM usage, the version in the startup log. Then a business health endpoint, an alert catalogue and the model-free watchdog | — |
| **Support and feedback** | The On-call session in the client chat; incident investigation from logs. Every client reply returns to Requirements as a new card | what a reply becomes |

**Humans at the edges, the machine in the middle.** People own four jobs, and one person can hold all of them:
- **Product owner:** what to build, and the client relationship.
- **Spec writer:** turns a request into a spec the agent can execute.
- **Reviewer:** accepts, merges and ships.
- **Operator:** the server, the sessions and production.

What stops the agent from crossing an edge is code wherever that is possible:
- a guard hook that denies force pushes, pushes to main, `--no-verify`, tag pushes, `gh pr merge` outside the merge
  script, and edits to the fence files themselves;
- a merge script that needs a named acceptance (`--accepted-by`);
- pre-push gates, the quota guard and the sandbox.

How strict this is is chosen at deployment: `solo`, `standard` or `team`. `team` also requires a GitHub approval.
There is an explicit, recorded path for merging when CI cannot run, for example when Actions is blocked by billing
(`--skip-ci "<reason>"`, which runs the local gate instead). A static guard cannot see everything (aliases, scripts
written and then run), so GitHub branch protection on main is the recommended backstop. What is still only an
instruction is listed in [docs/open-questions.md](docs/open-questions.md).

## How it runs day to day

A few long-lived Claude Code sessions run on a small Linux server you control, alongside processes that use no
model:

```
client chat ──► On-call session ──message──► development session ──► PR ──► human "accepted" ──► main ──► deploy
     ▲                ▲                           │  runs the feature pipeline in a worktree per feature
     └──── reply ─────┤                           │  near the quota limit: saves work, schedules its own continuation
                      │ event
        production monitor (cron watchdog → read-only agent)

scheduled runs ("tonight", "every morning") booked by a session itself ──► that session or another one
```

| Part | What it is | Set up by |
|---|---|---|
| Development session | `claude remote-control` in the project's checkout; you drive it from claude.ai or the mobile app | `provision-server` |
| On-call session | holds the client chat with a restricted tool set; forwards requests and posts answers back | `feedback-desk` module |
| Production monitor | a cron watchdog without a model; a read-only agent only on a real anomaly | `prod-monitor` module |
| Feature pipeline | Workflow scripts the development session runs per feature | the plugin + `feature-pipeline` module |
| Quota guard and guard hook | hooks in every session | the `dark-factory` plugin |
| Scheduled runs | native Claude Code scheduling (`send_later`, `CronCreate`, scheduled tasks); the quota guard keeps these tools open | Claude Code |

Why your own server instead of cloud sessions: the sessions need the chat channel, two-way messaging between
sessions, and local access to hosting tools, the preview environment and read-only production data.

## The factory over your projects

| Job | What it does | Tooling |
|---|---|---|
| **Provision** | Creates a new project from the template. Sets up the server it runs on, so every project's sessions restart after a reboot | `deploy-project` + `scripts/deploy-base.sh`; `provision-server` + `scripts/fleet.py provision` |
| **Observe** | Keeps one registry of projects. Shows how far each project has drifted from the template, plus live status: sessions, On-call login, monitor, quota, queue | `registry.md` (from [registry.example.md](registry.example.md)); `harness-diff.sh` in each project; `factory-status` + `scripts/fleet.py status` |
| **Improve** | Runs the review pass: what went wrong in a project becomes a decision in `docs/`, then a change in `templates/`, then a rollout back to the projects | `docs/`, `templates/` |

Keep this repository (the canon) unchanged. Put your own registry and configuration in a private repository of
your own (the instance).

---

## Modules

| Module | What it adds | Status |
|---|---|---|
| `base` | operating contract (`CLAUDE.md`), session log, queue, standards, CI, OpenSpec, git hooks, merge script, test pyramid, skills (`board`, `ship`, `investigate`, `code-audit`, …); uses the `dark-factory` plugin for the guard hook and the quota guard | used in every project |
| `feature-pipeline` | project settings for the plugin's Workflow scripts for one feature: plan → test-first chunks → integration → review, stopping before the PR | experimental |
| `release-tag` | production only from tags, a forward-only `release` branch, rollback by tag | experimental |
| `feedback-desk` | the On-call session in the client's Telegram group | experimental |
| `prod-monitor` | a model-free watchdog plus a read-only agent that reports real production failures | experimental |
| `observability` | a business health endpoint contract, an alert catalogue, log-based investigation | experimental |
| `code-audit` | a fan-out audit across many repositories with spot-checked evidence | experimental |

## Repository map

| Path | What is inside |
|---|---|
| [docs/getting-started.md](docs/getting-started.md) | who it is for, what to install, the steps, the glossary |
| [docs/process.md](docs/process.md) | the process on one page: stages, layers, who runs each |
| [docs/methodology.md](docs/methodology.md) | the method: process core, unattended work, principles, how the harness itself changes |
| [docs/map.md](docs/map.md) | the detailed map: phases, roles, autonomy boundaries, problem register |
| [docs/layers/](docs/layers/) and [docs/practices/](docs/practices/README.md) | design per layer; cross-cutting practices (client feedback, code analysis, observability, incidents) |
| [docs/open-questions.md](docs/open-questions.md) | open questions and settled decisions |
| [plugins/dark-factory/](plugins/dark-factory/README.md) | the Claude Code plugin: guard hook, quota guard, `/dark-factory:init` and its solo kit, the feature pipeline workflows; this repository is its marketplace (`.claude-plugin/marketplace.json`) |
| [templates/](templates/README.md) | `base` and the modules |
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

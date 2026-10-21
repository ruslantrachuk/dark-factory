# Dark factory

**A complete software development lifecycle run by Claude Code agents, with humans at the edges.** Requirements, development, testing, release, monitoring, support and feedback — every stage comes with its rules, skills and template files, and every stage hands the next one an explicit artifact. The machine stands in the middle of the line (writes code, runs tests, prepares the release); humans stand where they cannot be replaced: deciding what the client needs and accepting the result with a living eye.

This repository is **not a product but the factory itself**: the methodology, the decisions taken, and the templates that put this lifecycle into a project.

---

## The lifecycle

| Stage | What the factory puts in place | The human decides | Module |
|---|---|---|---|
| **Requirements** | a client signal becomes a card on the board (`board`, `transcript-intake`); a card becomes an OpenSpec change — proposal with confirmed interaction surfaces, design, phased tasks (`openspec`); an approved change becomes a task graph in the queue (`openspec-to-beads`) | what to build; approves the spec | base |
| **Development** | operating contract in `CLAUDE.md`: gates before code, one epic = one branch = one PR, branch names `r{N}/<type>-<slug>-<id>` with the release train from `openspec/CURRENT_TRAIN`; the feature pipeline (plan → test-first chunks → integration, in its own worktree); the devlog as the agent's memory between sessions | scope and tier | base, `feature-pipeline` |
| **Testing** | a test pyramid with enforced layers (unit / integration / api / e2e), user-guide screenshots produced by e2e, pre-push gates, CI tiers (quick on every push, full + browser on the release tag), secret scanning, a review contract, `feature-sanity-check`, a dev environment (`stand`) | acceptance with a living eye | base |
| **Release** | `merge-feature` (merge, close the task, queue state in the same PR) and `ship`; release trains `r{N}`; optionally prod only from a tag — `vYYYY.MM.DD.N` tags, a forward-only `release` branch, a `VERSION` file, generated release notes, an emergency manual release, rollback by tag | "shipping now" | base, `release-tag` |
| **Monitoring** | from the first line: structured logs, `correlation_id`, LLM usage, version in the startup log; a `/metrics/business` health contract and an alert catalogue; a model-free watchdog that wakes a read-only agent only on a real failure | — | base, `observability`, `prod-monitor` |
| **Support and feedback** | an On-call session in the client chat that forwards requests to development and posts answers back; `investigate` for incidents via logs; an incident practice; every client reply returns to Requirements as a new card | what a reply becomes | `feedback-desk`, base |

The load-bearing rule: **humans at the edges, the machine in the middle.** Everything critical ("do not push without asking", "do not merge without a human yes") is held by structural fences (hooks, orchestrator code, the physics of the environment), not by instructions to the agent — an agent breaks instructions; it cannot break fences.

**Roles** (one person can wear all of them; they are named so they can be handed out): **Producer** — the client and promises · **Technologist** — raw input into something executable · **Acceptor** — review, merge, production · **Operator** — infrastructure, the server and its sessions, stands.

Several people work through a **pull model on the board**: each person claims an umbrella card (assignee = you) **before** starting, works in their own zone, moves their card through `In Progress → In Master → Shipped`, and keeps context on the board rather than in their head or a personal devlog (the devlog is the agent's memory across sessions, not a channel between people). Decisions (what to take, what to order, acceptance, "shipping now") stay with the human; mechanics (board clicks, tags, statuses, formatting) go to the agent.

---

## How it runs day to day

The factory is not a batch job. It is a few long-lived Claude Code sessions on one machine you control (a small server), plus model-free processes, that message each other and the people involved:

```
client chat group ──► On-call session ──message──► development session ──► PR ──► human "yes" ──► main ──► deploy
        ▲                    ▲                          │  runs the feature pipeline in its own worktree
        └───── reply ────────┤                          │  pauses near the quota limit, books its own continuation
                             │ event
              production monitor (cron watchdog → read-only agent)

scheduled runs ("tonight", "every morning") booked by a session itself ──► that session or another one
```

| Part | What it is | Module |
|---|---|---|
| **Development session** | `claude remote-control` per project on the server; each session works in its own git worktree; the owner drives it from the web or the phone | `provision-server` (factory) |
| **On-call session** | a persistent session holding the client chat channel; acknowledges requests, forwards them verbatim to the development session, posts answers back | `feedback-desk` |
| **Production monitor** | a cron watchdog without a model wakes a read-only agent only on a real anomaly; its verdict arrives in the On-call session as a channel event | `prod-monitor` |
| **Feature pipeline** | Workflow scripts run inside a development session: plan → test-first chunks → integration → local commit, stopping before the PR | `feature-pipeline` |
| **Quota guard** | hooks that slow down, then stop new work as the subscription limit nears, and make the session schedule its own continuation after the reset | base |
| **Scheduled tasks** | native Claude Code scheduling: you ask a session "run this tonight" or "every morning review production", and it books the run itself (`send_later`, `CronCreate`, scheduled tasks in the server environment); the quota guard keeps these tools open even when it stops other work | native + base |

Why a server you own rather than cloud sessions: the sessions need the chat channel, two-way messages with each other, and local access to hosting tools, the dev environment and production read access. Merges and anything that reaches the client stay behind a human "yes".

---

## The factory over your projects

The lifecycle above runs inside each project. Around it, the factory itself has three jobs across all your projects:

| Job | What it does | Where |
|---|---|---|
| **Provision** | a new project from the template (`deploy-project`: dry-run, configuration questions, placeholders, chosen modules, a registry entry); the server it runs on — long-lived development sessions, the On-call session, the monitor watchdog, all restarted after a reboot | `deploy-project` skill + `scripts/deploy-base.sh`; `provision-server` skill + `scripts/fleet.py provision` (user systemd units per project, lingering) |
| **Observe** | one registry of projects (who owns what, which template commit, which modules and deviations); drift of each project from the template (`harness-diff.sh`); a live status per project — monitor watchdog, On-call session, subscription quota, ready queue | `registry.md` from [registry.example.md](registry.example.md), `templates/base/scripts/harness-diff.sh`; `factory-status` skill + `scripts/fleet.py status` |
| **Improve** | the review pass: what went wrong in projects becomes a decision in `docs/`, then a change in `templates/`, then a rollout back to the projects | `docs/`, `templates/` |

---

## How this repository is organised (three layers)

| Layer | What it is | Where it lives |
|---|---|---|
| **Methodology** | process, decisions, the review-pass loop — what you *read and decide* | `docs/` |
| **Template** | canonical files for a new project — what you *copy* | `templates/` (`base/` + modules) |
| **Instance** | your own operating layer: the project registry and your configured skills — what *runs daily* | your own private instance repo: `registry.md` (start from [registry.example.md](registry.example.md)) + `.claude/` config |

This repository ships three factory-level skills in `.claude/skills/`: `deploy-project` (a new project from the template, recorded in your registry), `provision-server` (the server's sessions start by themselves and survive a reboot) and `factory-status` (one read-only status of every project).

Rule against spaghetti: **canon lives in `templates/`, the instance lives in your own repo**; the factory itself can be "project #0", deployed from its own template. The improvement loop runs through all layers: review pass (instance) → decision (`docs/`) → materialisation (`templates/`) → manual rollout to projects during the review pass.

---

## Quick start

The full path from nothing to a project on your server — requirements, steps, glossary — is [docs/getting-started.md](docs/getting-started.md). The short version:

1. Preview what the base template would put into a target directory:

   ```sh
   scripts/deploy-base.sh <target> --dry-run
   ```

2. Run the `deploy-project` skill in Claude Code ("deploy project <name>"): it asks the configuration questions, fills the placeholders, adds the chosen modules and records the project in your registry.

---

## Repository map

| Document | What is inside |
|---|---|
| [docs/getting-started.md](docs/getting-started.md) | Who it is for, what to install, the steps, the glossary |
| [docs/process.md](docs/process.md) | **Process frame**: 5 layers + the load-bearing Coordination layer, five claims, two gaps |
| [docs/map.md](docs/map.md) | Detailed map: 11 phases (0–10), roles, autonomy boundaries, problem register |
| [docs/methodology.md](docs/methodology.md) | Methodology: process core, unattended work in remote sessions, cross-cutting principles, harness-change filter |
| [docs/layers/](docs/layers/) | Layer-by-layer design (coordination, intake, preparation, production, acceptance, value, operation) |
| [docs/practices/](docs/practices/README.md) | Practices across layers: client feedback, code analysis, observability, incident investigation — standard + skill + module + joints |
| [docs/open-questions.md](docs/open-questions.md) | Open forks and settled decisions |
| [templates/README.md](templates/README.md) | Template assembly plan and module list |
| [scripts/deploy-base.sh](scripts/deploy-base.sh) | Copies `templates/base` into a target project (with `--dry-run`) |

## Modules

| Module | What it adds |
|---|---|
| `base` | charter (`CLAUDE.md`), devlog, queue, standards, CI, OpenSpec, coordination skills (`board`, `ship`), test pyramid |
| `feature-pipeline` | Workflow scripts a development session runs for one feature: plan → test-first chunks → integration in its own worktree → local commit, stopping before the PR |
| `release-tag` | versioned releases and rollback by tag when production is built from a branch |
| `feedback-desk` | a persistent On-call session connecting a client chat group with the development session |
| `prod-monitor` | a model-free watchdog plus a read-only agent that reports real production failures to the group |
| `observability` | business-metrics contract, alert catalogue, log-based investigation |
| `code-audit` | fan-out audit across many repositories with spot-checked evidence |

---

## Term

"Dark factory" — features produced by agents with minimal human presence. The human stays in three roles: **client** (what to do), **preparer** (spec, decomposition, tier) and **acceptor** (review, merge, production). Everything critical is held by structural fences, not by instructions to the agent.

## License

MIT — see [LICENSE](LICENSE). Third-party components and their licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgements

Ideas and techniques were borrowed from [pavel-molyanov/molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT), [OpenSpec](https://github.com/Fission-AI/OpenSpec), [beads](https://github.com/steveyegge/beads), the `openspec-to-beads` skill in [lucastamoios/celeiro](https://github.com/lucastamoios/celeiro) (our version is a rewrite inspired by it) and the [Superpowers](https://github.com/obra/superpowers) plugin for Claude Code.

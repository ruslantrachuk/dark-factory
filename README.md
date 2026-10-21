# Dark factory

**The idea in one sentence:** features produced by agents with minimal human presence — "lights-out manufacturing" for software development. The machine stands in the middle of the line (writes code, runs tests, prepares the hand-over), and humans stand at the edges, where they cannot be replaced: understanding what the client needs, and accepting the result with a living eye.

This repository is **not a product but the factory itself**: the methodology, the decisions taken, and the templates used to set up and run projects with Claude Code.

---

## How it works: the feature path

All work travels one path. At every step it is clear who is responsible — a human or the machine:

| Step | What happens | Who |
|---|---|---|
| **1. Signal → card** | a client's wish (call, ticket, idea) immediately becomes a card on the board instead of living in someone's head | a human records it |
| **2. Preparation** | a high-level "what I want" turns into a package for the machine: spec + plan + tier. Essence first, details later | a human leads, an agent helps |
| **3. Production** | from the package, an agent writes code on a feature branch and passes tests and gates | machine |
| **4. Acceptance** | a living human eye + green CI → verdict (accepted / typed return) | human |
| **5. Shipping** | merge → deploy to the stand → card `Shipped`. The client sees and confirms — feedback returns to step 1 | a human commands, an agent executes |

The load-bearing rule: **humans at the edges, the machine in the middle.** Everything critical ("do not push without asking", "do not close tasks at night") is held by structural fences (hooks, orchestrator code, the physics of the environment), not by instructions to the agent — an agent breaks instructions; it cannot break fences.

**Roles** (one person can wear all of them; they are named so they can be handed out): **Producer** — the client and promises · **Technologist** — raw input into something executable · **Acceptor** — review, merge, production · **Operator** — infrastructure, nights, stands.

Several people work through a **pull model on the board**: each person claims an umbrella card (assignee = you) **before** starting, works in their own zone, moves their card through `In Progress → In Master → Shipped`, and keeps context on the board rather than in their head or a personal devlog (the devlog is the agent's memory across sessions, not a channel between people). Decisions (what to take, what to order, acceptance, "shipping now") stay with the human; mechanics (board clicks, tags, statuses, formatting) go to the agent.

---

## How this repository is organised (three layers)

| Layer | What it is | Where it lives |
|---|---|---|
| **Methodology** | process, decisions, the review-pass loop — what you *read and decide* | `docs/` |
| **Template** | canonical files for a new project — what you *copy* | `templates/` (`base/` + modules) |
| **Instance** | your own operating layer: the project registry and your configured skills — what *runs daily* | your own private instance repo: `registry.md` (start from [registry.example.md](registry.example.md)) + `.claude/` config |

This repository ships a generic `.claude/skills/deploy-project` skill that deploys a new project from the template and records it in your registry.

Rule against spaghetti: **canon lives in `templates/`, the instance lives in your own repo**; the factory itself can be "project #0", deployed from its own template. The improvement loop runs through all layers: review pass (instance) → decision (`docs/`) → materialisation (`templates/`) → manual rollout to projects during the review pass.

---

## Quick start

1. Preview what the base template would put into a target directory:

   ```sh
   scripts/deploy-base.sh <target> --dry-run
   ```

2. Run the `deploy-project` skill in Claude Code ("deploy project <name>"): it asks the configuration questions, fills the placeholders, adds the chosen modules and records the project in your registry.

---

## Repository map

| Document | What is inside |
|---|---|
| [docs/process.md](docs/process.md) | **Process frame**: 5 layers + the load-bearing Coordination layer, five claims, two gaps |
| [docs/map.md](docs/map.md) | Detailed map: 11 phases (0–10), roles, autonomy boundaries, problem register |
| [docs/methodology.md](docs/methodology.md) | Methodology: process core, night loop, cross-cutting principles, harness-change filter |
| [docs/layers/](docs/layers/) | Layer-by-layer design (coordination, intake, preparation, production, acceptance, value, operation) |
| [docs/practices/](docs/practices/README.md) | Practices across layers: client feedback, code analysis, observability, incident investigation — standard + skill + module + joints |
| [docs/decisions/mac-sandbox.md](docs/decisions/mac-sandbox.md) | Decision record: agent sandbox on macOS |
| [docs/open-questions.md](docs/open-questions.md) | Open and resolved forks |
| [templates/README.md](templates/README.md) | Template assembly plan and module list |
| [scripts/deploy-base.sh](scripts/deploy-base.sh) | Copies `templates/base` into a target project (with `--dry-run`) |

## Modules

| Module | What it adds |
|---|---|
| `base` | charter (`CLAUDE.md`), devlog, queue, standards, CI, OpenSpec, coordination skills (`board`, `ship`), test pyramid |
| `night-local` | local night loop: autonomous execution of a prepared queue that stops before shipping |
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

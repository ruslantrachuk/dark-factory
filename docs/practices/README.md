# Canon practices: parts of the end-to-end cycle

> A practice is the unit of canon for work that runs **across the layers** of [process.md](../process.md) instead of
> living in one. It has a standard in base, a skill, an optional module, and explicit interfaces with its neighbours.
> The table below names the lifecycle stages each practice touches, as well as its layers and phases.

## Anatomy of a practice

| Part | Where it lives | What it is |
|---|---|---|
| **Standard** | `templates/base` (CLAUDE.md, CODING_STANDARDS) | what must be in the code and the process from day one, because adding it later is expensive |
| **Skill** | `templates/base/.claude/skills/` | how to do it: a skeleton with a "project sources" section, filled in during a real run |
| **Module** | `templates/<module>/` | infrastructure for a particular environment (cloud, messenger, many repositories); installed when needed, with its own MANIFEST |
| **Interfaces** | the practice's file in this folder | what the practice takes and what it gives, as artifacts, like the transitions between layers |

## Four practices

| Practice | Stages | Layers and phases | Standard (base) | Skill (base) | Module |
|---|---|---|---|---|---|
| [Client feedback](feedback.md) | Requirements; Support and feedback | 1 Relations, 5 Value | — | — | `feedback-desk` (the skill is inside the module) |
| [Code analysis](code-analysis.md) | Requirements; Testing; Monitoring | 2 Preparation, 4 Acceptance, audit projects, 10 | `docs/review-contract.md` | `code-audit` | `code-audit` |
| [Observability](observability.md) | Development; Monitoring | 3 Production (the standard), 10 Operation | CODING_STANDARDS "Logging and LLM — mandatory minimum" | — | `observability`, `prod-monitor` |
| [Incident investigation](incidents.md) | Monitoring; Support and feedback | 10 Operation → 1 | push-tests-down, rule 6 | `investigate` | — (sources come from `observability`) |

## The loop

```
client writes to the group ──► On-call (feedback-desk) ──► development session
        ▲                                                    │ complaint / "it doesn't work"
        │                                                    ▼
  "done — take a look"                     investigate: logs, DB, traces by correlation_id
        │                                                    │ root cause unclear
        │                                                    ▼
  shipping ◄── feature path (TDD, acceptance) ◄── bug task ◄── code-audit "figure it out"
        │
        └─► observability: alert ──► investigate (before the client complains)
```

## Rules

- **An interface is an artifact, not an agreement.** A `correlation_id` in a log is the interface between
  observability and investigation; an investigation report is the interface with production; an On-call message with
  its author and time is the interface of client feedback.
- **The standard always lives in base; the module only when needed.** If a neighbouring practice cannot work without
  some part of this one (investigating without a `correlation_id`), that part is a standard.
- **A new practice** is added in the same format: a file here, a row in the table, and its interfaces with the
  existing practices.

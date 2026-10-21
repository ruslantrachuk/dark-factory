# Canon practices — parts of the end-to-end cycle

> A practice is the unit of canon for what runs **across the layers** of [process.md](../process.md)
> rather than living in one: it has a standard in base, a skill, an optional module and explicit joints with its neighbours.

## Anatomy of a practice

| Part | Where it lives | What it is |
|---|---|---|
| **Standard** | `templates/base` (CLAUDE.md, CODING_STANDARDS) | what must be in the code and the process from day one — adding it later is expensive |
| **Skill** | `templates/base/.claude/skills/` | how to do it; a skeleton with a "project sources" section, filled in by a live run |
| **Module** | `templates/<module>/` | infrastructure for an environment (cloud, messenger, multi-repo); installed when needed, with its own MANIFEST |
| **Joints** | the practice file here | what the practice takes and what it gives — as artifacts, like layer transitions |

## Four practices

| Practice | Layers / phases | Standard (base) | Skill (base) | Module |
|---|---|---|---|---|
| [Client feedback](feedback.md) | 1 Relations · 5 Value | — | — | `feedback-desk` (skill inside the module) |
| [Code analysis](code-analysis.md) | 2 Preparation · 4 Acceptance · audit projects · 10 | `docs/review-contract.md` | `code-audit` | `code-audit` |
| [Observability](observability.md) | 3 Production (standard) · 10 Operation | CODING_STANDARDS "Logging and LLM — mandatory minimum" | — | `observability`, `prod-monitor` |
| [Incident investigation](incidents.md) | 10 Operation → 1 | push-tests-down, rule 6 | `investigate` | — (sources come from `observability`) |

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
        └─► observability: alert ──► investigate (no complaint — ahead of the client)
```

## Rules

- **A joint is an artifact, not an agreement.** `correlation_id` in a log is the joint between observability and investigation; an investigation report is the joint with production; an On-call message with author and time is the joint of client feedback.
- **The standard is always in base; the module only when needed.** If without some part of a practice the neighbouring one cannot be carried out (investigating without `correlation_id`), that part is a standard.
- **A new practice** is added in the same format: a file here + a row in the table + its joints with the existing ones.

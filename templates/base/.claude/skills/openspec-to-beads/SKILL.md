---
name: openspec-to-beads
description: >
  Converts approved OpenSpec specifications into Beads issues with smart
  prioritization, dependency detection, and gap discovery. Bridges planning
  (OpenSpec) and execution (Beads). Trigger with "convert spec to beads",
  "create issues from spec", "implement this spec", or when approving proposals.
allowed-tools: "Read,Bash(bd:*)"
version: "1.1.0"
author: "Lucas Tamoios (adapted)"
license: "MIT"
compatible-with: claude-code
tags: [openspec, beads, spec-driven, issue-tracking, workflow-bridge]
---

# OpenSpec to Beads — Spec-to-Execution Bridge

> Canonical template (templates/base); based on upstream by Lucas Tamoios (MIT, see [LICENSE](LICENSE)). Needs no configuration.
>
> Adapted to the factory layout: `openspec/changes/r{N}-{name}/` instead of upstream's `specs/<change>/`;
> the `opsx`/`openspec` CLI is not used — OpenSpec here is a folder convention, not a tool;
> a "Factory rules" section was added. Everything else is as upstream.

Automatically converts approved OpenSpec specifications into Beads issues,
maintaining traceability between planning and execution while proactively
discovering implementation gaps.

## Core Principle

> **OpenSpec** defines WHAT to build (immutable contract).
> **Beads** tracks execution STATE (mutable reality).
> This skill bridges the gap intelligently, not mechanically.

## Activation

### Automatic triggers
- Requesting implementation of an approved spec
- Approving proposals with "ready" / "let's implement" language

### Manual trigger
- "Convert this spec to beads issues"
- "Create beads tasks from the spec"

### NOT triggered by
- Simply viewing specs
- Creating proposals
- Reviewing iterations

## Prerequisites

```bash
bd --version    # Requires bd CLI
```

- Beads initialized in project (`bd init`)
- OpenSpec change directory exists with approved artifacts
- **The `opsx`/`openspec` CLI is not part of the cycle** — OpenSpec here is a folder structure convention (see `openspec/README.md`), not a tool; only read-only commands are allowed (single contract — the `openspec` skill §CLI). Upstream steps that call `opsx` are skipped.

### Beads in a git worktree (a verified trap)

In a worktree the embedded database is empty (`.beads/embeddeddolt/` is gitignored), and the very first `bd` call
exports emptiness over the tracked `.beads/issues.jsonl`, wiping the queue. Before working:

```bash
git checkout -- .beads/issues.jsonl   # if the file is already wiped
bd import                             # load the queue from jsonl into the worktree database
bd list                               # make sure the tasks are there
```

## Conversion Process

### Step 1 — Context Gathering

Verify prerequisites, then read ALL artifacts:

```
openspec/changes/r{N}-{name}/
├── proposal.md          # Why we're doing this — scope, acceptance criteria, decisions, risks
├── design.md            # Technical approach (architecture delta, optional)
├── tasks.md             # Implementation checklist — phase checklist
├── specs/<topic>/       # Contract sub-specs (optional)
└── SPEC_REVIEW.md       # Result of the spec skeptic (if it was run)
```

Read **everything**, including SPEC_REVIEW.md: it lists the findings already folded into tasks.md
and the findings deliberately rejected — the latter are not turned into tasks.

### Step 2 — Critical Analysis

Before converting, assess:
- **Scope**: How many systems affected?
- **Dependencies**: What must exist first?
- **Gaps**: What's missing from the spec?
- **Risks**: What could go wrong?

### Step 3 — Smart Conversion

Apply intelligent prioritization — NOT 1:1 mapping:

| OpenSpec task category | Beads priority | Beads type |
|----------------------|:--------------:|:----------:|
| Infrastructure/setup, migrations, schema | **P0** | `task` |
| Core business logic, implementation | **P1** | `feature` |
| Tests (parallel-compatible) | **P1** | `task` |
| Documentation | **P1** | `chore` |
| Polish, nice-to-have | **P2** | `task` |

See [data/priority-rules.md](data/priority-rules.md) for full rules.

### Step 4 — Dependency Construction

Auto-detect relationships:

| Pattern | Dependency type |
|---------|:--------------:|
| Sequential within category (X.2 → X.1) | `blocks` |
| Database → API | `blocks` |
| Config → Implementation | `blocks` |
| Implementation → Tests | `related` (parallel OK) |
| Core → Polish | `blocks` |

See [data/dependency-patterns.md](data/dependency-patterns.md) for full patterns.

### Step 5 — Gap Detection

Create **discovery issues** for missing:
- Rollback plans (migrations need rollback)
- Rate limiting (API endpoints need protection)
- Error handling (external integrations need resilience)
- Monitoring (features need observability)
- Test coverage

### Step 6 — Tracking Infrastructure

Create epic issue linking all tasks:

```bash
bd create "[EPIC] <change-name>" --type epic --priority 0 \
  --labels "spec:<change>,epic,openspec" --json
```

### Step 7 — Actionable Reporting

Present results organized by priority:
- Summary table of all created issues
- Dependency graph
- Ready-to-start tasks (`bd ready`)
- Discovered gaps with rationale

## Issue Creation Templates

See [templates/issue-creation.md](templates/issue-creation.md) for full templates.

**Basic:**
```bash
bd create "[<change>] <category>: <task-description>" \
  --priority <P> --type <type> \
  --labels "spec:<change>,category:<slug>,complexity:<level>" --json
```

**Discovery:**
```bash
bd create "[<change>] DISCOVERED: <gap-description>" \
  --type task --priority 1 \
  --labels "spec:<change>,discovered,proactive" --json
```

## Factory rules

They extend the upstream steps. In a conflict with upstream, these win.

- **Language.** Task titles and descriptions — in the project language, like commits and the devlog (`CODING_STANDARDS.md` §Project language; default English). Identifiers and labels — always English.
- **One epic = one branch/PR** (`CLAUDE.md` §Operating contract). So a block of phases from `tasks.md` becomes an **epic**, not a scatter of top-level tasks; the phases inside the block are child tasks via `--parent`.
- **Epic branch** — `r{N}/<type>-<slug>-<bd-id>`, where `r{N}` is taken from `openspec/CURRENT_TRAIN`, not guessed.
- **Acceptance.** Each epic's `--acceptance` is phrased as an observable fact from the proposal's "Acceptance criteria" section — not "everything works".
- **Cut ladder.** If the proposal has an order of cuts for when time runs short, it carries over into priorities: what is cut first gets a lower priority.
- **Open questions to the owner** from the proposal are created as separate tasks (otherwise they are invisible in `bd ready` — a verified gap), type `task`, marked as requiring a human decision.
- **Tasks that need a human decision** are not taken into work by the agent: mark this explicitly in the description.

## Anti-Patterns

- **Don't** blindly copy tasks 1:1 from tasks.md
- **Don't** ignore test creation
- **Don't** over-prioritize everything as P0
- **Don't** create excessive micro-issues
- **Don't** lose the original proposal rationale

## Examples

See [examples/conversion-workflow.md](examples/conversion-workflow.md) for full worked examples.

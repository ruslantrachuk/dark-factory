---
name: openspec
description: >
  Use when working with the OpenSpec spec-driven workflow in this project — writing
  or editing a proposal/design/tasks artifact under openspec/changes/, looking
  up the proposal→design→tasks→implement cycle, the delta-spec format
  (ADDED/MODIFIED/REMOVED Requirements + Scenarios), the artifact templates, or
  the `openspec`/`opsx` CLI commands.
user-invocable: true
---

# OpenSpec

> Canonical template (templates/base). Working instances live in projects; no configuration needed. How a particular project applies the cycle — see its openspec/README.md.

## Overview

OpenSpec — lightweight spec-driven framework: agree on requirements **before**
writing code. In this project it is the mandatory development cycle — no code outside
an explicit plan (see CLAUDE.md § GATE and § Engineering Principles,
"OpenSpec-driven").

**This skill is a reference for the OpenSpec tool itself.** For *how this project
applies it* (release numbering, delta-design, scope-fallback, bug-fix branches),
the source of truth is `openspec/README.md` — don't duplicate it here. To turn an
approved spec into Beads issues, use the `openspec-to-beads` skill.

## The cycle (as this project uses it)

```
propose → design → tasks → implement
```

The project uses the **manual/legacy layout**, not auto-`opsx` scaffolding:

- Each change lives in `openspec/changes/r{N}-{description}/` with artifacts:
  `proposal.md` → `design.md` → `specs/<topic>/spec.md` → `tasks.md`
- **Changes are NOT archived** — they stay in git history; shipped detail goes in
  `SHIPPED.md`. (Differs from upstream OpenSpec, which archives into `specs/`.)
- Implement via the `tasks.md` checklist, one checkpoint at a time
  (pairs with `superpowers:executing-plans`).

## Delta-spec format

Spec files describe **deltas**, not full re-statements. Use RFC-2119 keywords
(MUST/SHOULD/MAY) inside Requirements, each with at least one `#### Scenario:`.

```markdown
## ADDED Requirements
### Requirement: Broadcast queue isolation
The system SHALL route `send_broadcast` to a dedicated `broadcast` queue.

#### Scenario: admin triggers broadcast
- **WHEN** an admin calls send_broadcast
- **THEN** the task lands on the `broadcast` queue, not `celery`
```

Section headers: `## ADDED Requirements`, `## MODIFIED Requirements`,
`## REMOVED Requirements`. Templates for every artifact live in
[schemas/spec-driven/templates/](schemas/spec-driven/templates/)
(`proposal.md`, `design.md`, `spec.md`, `tasks.md`).

## CLI: read-only allowed, scaffolding forbidden

OpenSpec here is a **folder convention, not a tool**: artifacts are edited
directly, the cycle is driven manually. The CLI is NOT part of the cycle
(same rule in the `openspec-to-beads` skill). What that means in practice:

- **Allowed (read-only, optional):** `openspec list` · `openspec show` ·
  `openspec validate [--strict]` · `openspec status` · `openspec view`.
- **Forbidden (writes upstream structure the project does not use):**
  `/opsx:*` slash commands (`propose`, `apply`, `archive`, `verify`, …),
  `openspec init/update/archive`. Archiving especially: this project keeps
  changes in git history (see above), and `opsx` scaffolding produces a
  layout that is not canonical here.

Full CLI reference: [docs/cli.md](docs/cli.md).

## Reference docs

`docs/` is **not stored in the factory template** — it is the upstream OpenSpec
documentation ([Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec/tree/main/docs)),
snapshotted into `.claude/skills/openspec/docs/` at project deploy by `scripts/fetch-openspec-docs.sh`
(version pinned to the installed `openspec` CLI, or the latest upstream tag;
see `docs/VERSION`). The snapshot IS committed to the project repo — offline
work and closed perimeters beat deduplication. CLI updated → re-run the script
and commit the refreshed snapshot.

Read on demand, do not `@`-load:

- [docs/getting-started.md](docs/getting-started.md) — start here: first change end-to-end
- [docs/concepts.md](docs/concepts.md) — specs vs changes, delta specs, schemas, glossary
- [docs/workflows.md](docs/workflows.md) — working patterns (quick / exploratory / parallel)
- [docs/cli.md](docs/cli.md) — every terminal command
- [docs/commands.md](docs/commands.md) — every `/opsx:*` and legacy slash command
- [docs/customization.md](docs/customization.md) — project config & custom schemas

## Common mistakes

- **Writing code before a `tasks.md` checkpoint exists** — forbidden by CLAUDE.md (GATE).
  Propose → design → tasks first.
- **Full spec instead of a delta** — spec files state ADDED/MODIFIED/REMOVED, not
  the whole requirement set.
- **Requirement without a Scenario** — `openspec validate --strict` rejects it.
- **Archiving a change** — the project keeps changes in git history; don't archive.

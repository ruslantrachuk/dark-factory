# OpenSpec — <project> development cycle

> Each release lives in `openspec/changes/r{N}-{name}/` and goes through the cycle: **propose → design → tasks → implement**. This document is a reference on how to use the cycle.

## Why

OpenSpec is a lightweight methodology of "do not write code outside an explicit plan". A release is first talked through on paper (what and why) and decomposed into phases — then comes the TDD implementation. Without this the AI easily builds "spaceships" instead of what is needed right now.

## §0. Gate before the proposal — interaction on every surface

A user-visible feature is designed for **all** project surfaces, not only for the one the request came from. This is the first step of handling a request — before the spec, the bd task, implementation brainstorming and code (CLAUDE.md, rule 7).

Project surfaces (fill in at deployment):

| Surface | What it is |
|---|---|
| `<bot chat>` | `<…>` |
| `<mini-app / web version>` | `<…>` |
| `<outgoing from the system: notifications, mailings>` | `<…>` |

For each surface — the entry point, action and result, or an explicit "not on this surface". For a new entity — where to view it and which of create / view / edit / delete is part of the delivery. Questions go **to the requester** (via the feedback group — to the On-call agent, `feedback-desk` skill), not guesses on their behalf.

Answers confirmed by the requester or the owner are recorded in `proposal.md` in an **"Interaction surfaces"** section (a surface × entry × action × result table, with a link to the confirming message). In `design.md` — a **"Transition tree"**: every entry, every state and where each action leads, including "back", cancel and errors, with no dead ends. No section or no confirmation — the feature is not taken into work: no spec approval, no `openspec-to-beads`, no feature-pipeline run (feature-auto stops with the error "no decision on interaction surfaces").

Why: a request such as "create events through the bot" arrives in the chat; if the feature is built only for the chat — without the mini-app, the web version and the event screen — it typically ends up being removed entirely.

## What `r{N}` means — a train, not a release

`r{N}` is a **release train** (an integration wave), NOT a formal release:

| Concept | What it is | Artifacts | Pace |
|---|---|---|---|
| **Train `r{N}`** | A wave of work: all branches/tasks of a period under one number | branch prefix `r{N}/…`; the number in `openspec/CURRENT_TRAIN` | cheap, many branches in parallel |
| **Formal release** | A contract change (data model / API / user flow) or a ROADMAP milestone | `openspec/changes/r{N}-{name}/` + `SHIPPED.md` | expensive, only when truly needed |

Rules:
- **The train number lives in one place:** `openspec/CURRENT_TRAIN`. Prefix the branch with the number from there — not "by eye", not by copying from a neighbouring branch.
- **Only a human increments N**, with the "open the next train" ritual: `echo <N+1> > openspec/CURRENT_TRAIN`. Agents and workflow runs only read N.
- **Several branches under one `r{N}` are normal** (that is what a train is). Uniqueness comes from the bd id in the branch name. Skipping a number is also normal.
- **A change folder is NOT created for every train** — only for a contract change (see "Two levels").

**Branch name:** `r{N}/<type>-<slug>-<bd-id>`, `<type>` ∈ `feat | fix | chore | ui | refactor`. `<bd-id>` is the **full** bd id, `<prefix>-<hash>` (a child task: `<prefix>-<hash>.N`), e.g. `r12/feat-delivery-log-proj-a1b2`. The bd id at the end makes the branch↔task link deterministic even with a stale N: `scripts/merge-feature.sh` closes the task only when the branch ends in `-<prefix>-<id>[.N]` with the project's prefix (any other branch — "no id, close by hand"; `scripts/merge-feature.sh <branch> --print-bd-id` shows what it would take).

## Directory structure

```
openspec/
├── README.md
├── CURRENT_TRAIN                        # SSOT of the train number
└── changes/
    └── r{N}-{name}/
        ├── proposal.md                  # mandatory: why + scope + criteria + risks with fallbacks
        ├── design.md                    # optional: if the architecture changes (delta only)
        ├── specs/<topic>/spec.md        # optional: contract sub-specs
        ├── tasks.md                     # mandatory: phased checklist
        ├── FOUND_BUGS.md                # if a prod bug was found along the way (see the pattern below)
        └── SHIPPED.md                   # after the merge
```

After implementation the release **stays in `changes/` forever** as a record of "why it was done this way" — git log answers "when", the folder answers "why". No separate archive is needed.

## Two planning levels

### Level 1 — change folder (releases and contract changes)

Create `openspec/changes/r{N}-{name}/` when: a release-level feature (ROADMAP milestone) · the data model changes · the API contract changes · the user flow changes · the client's decisions need to be recorded.

### Level 2 — bd epic + spec (small features and fixes)

No change folder: a bd epic (`bd create --type=feature … --acceptance="…"`) + a spec in `docs/superpowers/specs/YYYY-MM-DD-{topic}-design.md`, plans in `docs/superpowers/plans/`.

**Boundary:** if it turns out along the way that a contract changes — raise it to level 1.

Documentation (`*.md`/`*.yaml`) goes to the main branch without a change folder and a bd task.

## File contents

### `proposal.md` (1–3 pages)
- **Problem** — what is wrong now
- **Scope** — what is included (checklist) and **what is NOT included** (deferrals matter just as much)
- **Acceptance criteria** — observable facts, not "everything works"
- **Interaction surfaces** — for a user-visible feature (§0)
- **Decisions (made, not to be revisited)** — so the agent does not re-discuss what is closed
- **Risks — each with a fallback** (see "Scope fallback" below)

### `design.md` — if the architecture changes
Only the **delta** (after the first release the code is the source of truth): diagrams, decisions and trade-offs, mapping to the project's layers, new ADRs.

### `tasks.md` — phased checklist
Phases of 2–5 minutes under TDD: `RED → GREEN → REFACTOR → Commit`, each phase a separate commit. RED first, always. A phase over 5 minutes — split it. Not "implement module X" but "add X.foo with the test test_X_foo_ok". Approved phases are converted into a bd graph by the `openspec-to-beads` skill.

### `SHIPPED.md` — on merge day
This format has proven itself over many consecutive trains; it is the release acceptance itself — no separate HUMAN_GATES is needed:

```markdown
# r{N}-{name} — SHIPPED
**Merge date:** YYYY-MM-DD · PR #N, merge commit `abc1234` · board card <ID> · bd epic `<id>`
## What actually shipped          — per proposal scope item, with facts (endpoints, screens, number of tests)
## What was deferred and why      — each item: the reason and where it is recorded (ROADMAP / bd)
## Found by review, moved out of the branch — bd-ids of findings not included in the release
## Retro                          — 2–5 lines: what surprised us, what to change in the process
```

## Scope fallback in the proposal (mandatory)

The proposal's risks **must** state what to do if a risky item does not work out — a concrete fallback, not panic. Example: "the external API spike failed → drop this piece from the release entirely, move it to r{N+1}. This is a **valid release closure**, not a failure". This lets a release close green when part of the scope fails — unattended runs do not drag dead weight along.

## Spec skeptic before implement (large releases)

For a change-folder-level release, before implementation starts — a fresh read-only run over the factual claims of proposal/design about the codebase (files, symbols, dependencies, current behaviour): the context that wrote the spec does not see its own mistakes about the code. Finding format and triage — [../docs/review-contract.md](../docs/review-contract.md).

## A prod bug found during a release (FOUND_BUGS + xfail quarantine)

A release about X must not turn into an uncontrolled refactoring for the sake of a bug found along the way:

1. In the release branch the test is marked `xfail(strict=True, reason="r{N}-bug-XXX, see FOUND_BUGS.md")`, the bug is described in `FOUND_BUGS.md` (severity / reproduction / why it was not caught / why prod did not go down / fix plan), and the release is merged with the xfail.
2. After the merge — a **planned** branch `r{N}.{M}/fix-…` with a minimal fix + removal of the xfail (the test becomes a regression test).
3. `FOUND_BUGS.md` — mark it `✅ FIXED`.

## When to deviate from the cycle

- **Hotfix** (prod is down): fix first, then the folder and the PR description retrospectively.
- **A one-line UI string edit**: a mini-PR without a full tasks.md; a 3–4 line proposal + the PR description are mandatory.
- **Spike/experiment**: a `spike/…` branch, not merged into the main branch without the full cycle.

## Related

- `CLAUDE.md` — GATE and session loop
- `ROADMAP.md` — all releases
- `.beads/README.md` — the queue and syncing between machines

# OpenSpec — <project> spec format

> A change lives in `openspec/changes/<slug>/` and goes through **propose → design → tasks → implement**.
> The `size-task` skill decides whether a piece of work needs a folder at all and how big it is; the
> `openspec` skill describes the files. This document holds the project rules around them.

## Why

"Do not write code outside an explicit plan." A change is first talked through on paper (what and why),
cut into end-to-end phases, and only then built by TDD. Without it the AI builds "spaceships" instead of
what is needed right now.

## §0. Gate before the proposal — interaction on every surface

A user-visible feature is designed for **all** project surfaces, not only for the one the request came from. This is the first step of handling a request — before the spec, the bd task, implementation brainstorming and code (CLAUDE.md, rule 7).

Project surfaces (fill in at deployment):

| Surface | What it is |
|---|---|
| `<bot chat>` | `<…>` |
| `<mini-app / web version>` | `<…>` |
| `<outgoing from the system: notifications, mailings>` | `<…>` |

For each surface — the entry point, action and result, or an explicit "not on this surface". For a new entity — where to view it and which of create / view / edit / delete is part of the delivery. Questions go **to the requester** (via the feedback group — to the On-call agent, `feedback-desk` skill), not guesses on their behalf.

Answers confirmed by the requester or the owner are recorded in `proposal.md` in an **"Interaction surfaces"** section (a surface × entry × action × result table, with a link to the confirming message). In `design.md` — a **"Transition tree"**. No section or no confirmation — the feature is not taken into work: no spec approval, no `openspec-to-beads`, no feature-pipeline run (feature-auto stops with the error "no decision on interaction surfaces").

Why: a request such as "create events through the bot" arrives in the chat; if the feature is built only for the chat — without the mini-app, the web version and the event screen — it typically ends up being removed entirely.

## Names

- The folder is `openspec/changes/<slug>/`; the slug is also the branch slug and the bd epic label `change:<slug>`.
- A slug is unique: it is taken when the folder exists.
- The tracker ID (if any) goes in the proposal header. Branch: `<type>/<ID>-<slug>`, or `<type>/<slug>` without a tracker; `<type>` is `feat | fix | ui | refactor | chore | docs`.
- Phases of one spec are separate sub-cards with their own tracker IDs (preferred), or the slug with a `-p<K>` suffix when there is no tracker.
- Folders that already carry an old `r`-number prefix stay as they are: the full folder name is their slug.

## Sizes

| Verdict (`size-task`) | What exists |
|---|---|
| `trivial` | no folder: a branch and a PR |
| `small` | `proposal.md` (with acceptance scenarios) + `tasks.md` |
| `large` | + `design.md`: the delta and the transition tree. When the data model, an API, a user flow changes |

Documentation (`*.md`/`*.yaml`) goes to the main branch through a `docs/*` branch without a folder. There is no living spec under `openspec/specs/` and no OpenSpec CLI here: the folders in `changes/` are the whole record.

After the merge the change **stays in `changes/` forever**: git log answers "when", the folder answers "why". No archive.

## Files

The format of `proposal.md`, `design.md` and `tasks.md` is in the `openspec` skill. Rules on top of it:

- **Acceptance scenarios** are observable facts (WHEN/THEN), not "everything works".
- **Decisions** (made, not to be revisited) keep the agent from re-discussing what is closed.
- **Phases** of `tasks.md` are sliced end to end and finish with an entry-level test; a phase that cannot be built and checked in one sitting is split. Approved phases become a bd graph via `openspec-to-beads`.

### `SHIPPED.md` — on merge day, for a large change

Written in the branch of the PR that ships the large change; it is the change's acceptance record:

```markdown
# <slug> — SHIPPED
**Merge date:** YYYY-MM-DD · PR #N, merge commit `abc1234` · tracker <ID> · bd epic `<id>`
## What actually shipped          — per proposal scope item, with facts (endpoints, screens, number of tests)
## What was deferred and why      — each item: the reason and where it is recorded (bd / a later change)
## Found by review, moved out of the branch — bd-ids of findings not included
## Retro                          — 2–5 lines: what surprised us, what to change in the process
```

## Scope fallback in the proposal (mandatory)

The proposal's risks **must** state what to do if a risky item does not work out — a concrete fallback, not panic. Example: "the external API spike failed → drop this piece from the change entirely, move it to a later one. This is a **valid closure**, not a failure". It lets a change close green when part of the scope fails — unattended runs do not drag dead weight along.

## Spec skeptic before implement (large changes)

For a `large` change, before implementation starts — a fresh read-only run over the factual claims of proposal/design about the codebase (files, symbols, dependencies, current behaviour): the context that wrote the spec does not see its own mistakes about the code. Finding format and triage — [../docs/review-contract.md](../docs/review-contract.md).

## A prod bug found during a change (FOUND_BUGS + xfail quarantine)

A change about X must not turn into an uncontrolled refactoring for the sake of a bug found along the way:

1. In the change's branch the test is marked `xfail(strict=True, reason="<slug>-bug-XXX, see FOUND_BUGS.md")`, the bug is described in `openspec/changes/<slug>/FOUND_BUGS.md` (severity / reproduction / why it was not caught / why prod did not go down / fix plan), and the change is merged with the xfail.
2. After the merge — a **planned** `fix/<slug>-<bug>` branch with a minimal fix and the xfail removed (the test becomes a regression test).
3. `FOUND_BUGS.md` — mark it `✅ FIXED`.

## When to deviate

- **Hotfix** (prod is down): fix first, then the folder and the PR description retrospectively.
- **A one-line UI string edit**: `trivial` — a mini-PR; the PR description is mandatory.
- **Spike/experiment**: a `spike/…` branch, not merged into the main branch without a spec.

## Related

- `CLAUDE.md` — GATE and session loop
- `.beads/README.md` — the execution queue, a local store shared by the worktrees

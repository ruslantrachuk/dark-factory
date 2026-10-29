# Feature development workflow (reproducible)

> One checklist on top of GATE/superpowers: **five hard gates** that projects regularly trip over. Not passed → the feature is not done. At deployment, fill in the `<placeholders>` for the stack.

## Five hard gates

| # | Gate | Where it is checked |
|---|--------|-----------------|
| **G1** | **Matching the mockup** (if the feature has a Figma design) — fonts/icons/spacing/colors checked by **measurement**, not by eye | planning (spec) **and** acceptance (live measurement on the dev stand — human/attended only) |
| **G2** | **`/simplify`** has been run, findings applied or consciously rejected with a reason | before the PR |
| **G3** | **Automated tests per the pyramid** (policy in CODING_STANDARDS): happy + edge + error + negative | every task (TDD) + before the PR |
| **G4** | **Splitting** a large feature into bd tasks; independent ones go to separate agents via bd | planning |
| **G5** | **Freshness** — a fresh `<main>` is merged in before the PR; test counts recomputed by a run, not guessed | PR preparation |

## Choosing the execution path (confirm with the human BEFORE starting)

The size comes first: the `size-task` verdict (`trivial` / `small` / `large`) with the owner's ok. In an attended session the feature is built here, by the stage skills (`dark-factory:plan` → `build-tdd` → `integrate` → the `reviewer` role → `wrap`). The feature pipeline (`/dark-factory:feature`) is only for a run left alone: it takes the approved size as its path (lite for a small self-contained feature, full otherwise) and builds in `session` mode unless told `--mode pipeline` for a wide phase of independent slices. An agent sizes the work only when no size is given. Orchestration costs several times the simple path for the same deliverables, so the path is chosen explicitly.

## Commit and PR messages — human-readable

The message is addressed to the reviewer and the reader of the history, not to a machine: Conventional Commits, <project language, default English>, subject ≤ ~70 characters, body — **connected prose** on "what changes and why", plus a "points for the reviewer" block. **Forbidden:** `A → B → C` chains, file paths as the main text, inline JSON, clipped notes joined by slashes. This rule also applies to workflow agents (integrator/fix/PR).

## Phases (skeleton)

0. **Opening the session** — the session header: the branch's PR, the tasks in progress (SESSION LOOP); a new branch gets a draft PR right away.
1. **GATE** — `size-task` verdict + skills + bd task + branch `<type>/<ID>-<slug>` (or `<type>/<slug>` without a tracker; `merge-feature.sh` finds the task to close from it) from a fresh `<main>` + standards.
2. **Spec + mockup contract (G1 part 1)** — if there is a Figma design: capture the exact values (tokens, sizes, icon glyphs) in an "element → value → node-id" table BEFORE coding. Pitfalls: filled≠outlined icons; do not copy spacing from a neighbouring screen; heading line-height.
3. **Plan + splitting (G4)** — the change's phases → bd graph (`openspec-to-beads`), one phase card = one branch; a phase → end-to-end slices (`dark-factory:plan`).
4. **TDD implementation (G3)** — RED → GREEN → REFACTOR; every pyramid layer the feature touches.
5. **Acceptance against the mockup (G1 part 2)** — live measurement on the dev stand (`getBoundingClientRect`/`getComputedStyle`), screenshot proof, console without new errors. Reuse shared components — alignment then matches "for free".
6. **`/simplify` (G2)** — apply or consciously reject. Findings of this and any other review are handled per [review-contract.md](review-contract.md): verify, reject with a reason, wave limit.
7. **Project documents + the PR description** — the sync table from CLAUDE.md; the description's `## Done` / `## Decisions` / `## Open questions` (the `save` skill); follow-ups as bd tasks.
8. **PR + freshness (G5) + merge** — merge a fresh `<main>`, full gates; then the `ship` skill (merge on green CI and your own review, the mechanics by script: `scripts/merge-feature.sh <branch>`).

## Parallel sessions (2+ features at once)

- **Worktree per feature**: each feature gets its own git worktree from a fresh `<main>`; remove it after the merge.
- **Dev stand ports**: a hand-started second copy runs on shifted ports; the stand and any copy run detached; do not stop someone else's.
- **One queue for all worktrees**: the bd store of the main checkout (`.beads/README.md`); claim a task before working on it, and "one card = one branch" (a phase task, or the epic of a change without phases) keeps two sessions off the same task.

## Checklist before the PR

- [ ] G1 measurements + screenshot proof (if there is a mockup)
- [ ] G2 simplify closed
- [ ] G3 pyramid, including negative cases
- [ ] G4 splitting was done (for a large feature)
- [ ] G5 fresh `<main>` merged in, counts recomputed by a run
- [ ] Review findings handled per [review-contract.md](review-contract.md) (verified / rejected with a reason / escalated to a human)
- [ ] Project documents + the PR description + bd notes up to date
- [ ] CI green and your own review → merge (`ship` skill)

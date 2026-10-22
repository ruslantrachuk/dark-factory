# Feature development workflow (reproducible)

> One checklist on top of GATE/superpowers: **five hard gates** that projects regularly trip over. Not passed → the feature is not done. At deployment, fill in the `<placeholders>` for the stack.

## Five hard gates

| # | Gate | Where it is checked |
|---|--------|-----------------|
| **G1** | **Matching the mockup** (if the feature has a Figma design) — fonts/icons/spacing/colors checked by **measurement**, not by eye | planning (spec) **and** acceptance (live measurement in the preview — human/attended only) |
| **G2** | **`/simplify`** has been run, findings applied or consciously rejected with a reason | before the PR |
| **G3** | **Automated tests per the pyramid** (policy in CODING_STANDARDS): happy + edge + error + negative | every task (TDD) + before the PR |
| **G4** | **Splitting** a large feature into bd tasks; independent ones go to separate agents via bd | planning |
| **G5** | **Freshness** — a fresh `<master>` is merged in before the PR; metadata conflicts (`.beads/issues.jsonl` — through the store!) resolved; test counts recomputed by a run, not guessed | PR preparation |

## Choosing the execution path (confirm with the human BEFORE starting)

Full orchestration costs **~5× the simple path** for the same deliverables (measured: ~0.07–0.22M tokens vs 1.0–1.3M). The path is chosen explicitly, on the card:

| | Simple (native / lite) | Orchestration (core/auto) |
|---|---|---|
| Machinery | 1–3 agents | 20–27 agents |
| Where it wins | a small self-contained feature (≤ ~5 files, no contract/Figma/parallelism) | large / contract / multi-phase / with Figma |

Show the human an estimate for the specific feature + a recommendation, and ask for the choice explicitly. In auto mode the same threshold drives scale-gating.

## Commit and PR messages — human-readable

The message is addressed to the reviewer and the reader of the history, not to a machine: Conventional Commits, <project language, default English>, subject ≤ ~70 characters, body — **connected prose** on "what changes and why", plus a "points for the reviewer" block. **Forbidden:** `A → B → C` chains, file paths as the main text, inline JSON, clipped notes joined by slashes. This rule also applies to workflow agents (integrator/fix/PR).

## Phases (skeleton)

0. **Opening the session** — latest devlog entry (SESSION LOOP).
1. **GATE** — skills + bd task + branch `r{N}/<type>-<slug>-<bd-id>` (the full bd id `<prefix>-<hash>`, which `merge-feature.sh` closes at merge) from a fresh `<master>` + standards.
2. **Spec + mockup contract (G1 part 1)** — if there is a Figma design: capture the exact values (tokens, sizes, icon glyphs) in an "element → value → node-id" table BEFORE coding. Pitfalls: filled≠outlined icons; do not copy spacing from a neighbouring screen; heading line-height.
3. **Plan + splitting (G4)** — phases of 2–5 min; large → bd graph (`openspec-to-beads`); independent → parallel agents, one file is edited by one agent.
4. **TDD implementation (G3)** — RED → GREEN → REFACTOR; every pyramid layer the feature touches.
5. **Acceptance against the mockup (G1 part 2)** — live measurement in the preview (`getBoundingClientRect`/`getComputedStyle`), screenshot proof, console without new errors. Reuse shared components — alignment then matches "for free".
6. **`/simplify` (G2)** — apply or consciously reject. Findings of this and any other review are handled per [review-contract.md](review-contract.md): verify, reject with a reason, wave limit.
7. **Project documents + devlog** — the sync table from CLAUDE.md; `bd close` + `scripts/bd-export.sh`.
8. **PR + freshness (G5) + merge** — merge a fresh `<master>`, metadata conflicts per the procedures (`.beads/README.md`), full gates; then the `ship` skill (merge only on an explicit "accepted", the mechanics by script: `scripts/merge-feature.sh <branch> --accepted-by "<name>"`).

## Parallel sessions (2+ features at once)

- **Worktree per feature**: each feature gets its own git worktree from a fresh `<master>`; remove it after the merge.
- **Preview port offset**: a second preview runs on shifted ports; previews run detached; do not stop someone else's.
- **beads — a shared store**: resolve `issues.jsonl` conflicts through the store, export only via `scripts/bd-export.sh`; "1 epic = 1 branch" minimizes overlaps.

## Checklist before the PR

- [ ] G1 measurements + screenshot proof (if there is a mockup)
- [ ] G2 simplify closed
- [ ] G3 pyramid, including negative cases
- [ ] G4 splitting was done (for a large feature)
- [ ] G5 fresh `<master>` merged in, counts recomputed by a run
- [ ] Review findings handled per [review-contract.md](review-contract.md) (verified / rejected with a reason / escalated to a human)
- [ ] Project documents + devlog + bd synced
- [ ] CI green → merge on an explicit "accepted" (`ship` skill)

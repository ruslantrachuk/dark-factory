---
name: feature-sanity-check
description: Sanity-check a feature/task before taking it into work. Use for "assess this feature/task/queue", "is this worth doing", before claiming a task from bd ready, when creating a discovered-from card, when prioritizing the backlog, or in a "business sense vs technical risk" dispute.
---

# Skill `feature-sanity-check` — a sanity check of a feature

> **Seam:** execution queue = beads (`bd ready`, `bd update --claim`, `bd update --notes`). To use another tool, rewrite the `bd` commands in "When to run" and "Mechanics".

## Why

This guards against a technical finding authorizing itself: finding → bd task → task is `ready` → the next session takes it into work, and the queue fills up with high-technical-risk work without real business value (reference example: reordering the hot path of incoming message handling just to get labels on a trace span). Before work, every task goes through a virtual team of two roles, the dispute is consolidated, and priority is computed by WSJF.

**The verdict is a proposal to the owner, not an authorization** (CLAUDE.md, Operating contract, rule 6). The skill itself does not close, defer or start tasks.

## When to run

- Explicit call: "assess the feature", "assess task <pfx>-XXXX", "assess the queue", "run a sanity check".
- **Before `bd update <id> --claim` from `bd ready`** — blocking, if the task's notes do not yet have a sanity-check verdict. Verdict "do now" → work; anything else → show it to the owner and wait for a decision.
- **When creating a discovered-from task** — assess right away and record the verdict in notes (`bd update <id> --notes`). A task with the verdict "do not do" or "owner answer needed" is not taken into work until the owner decides.

Do not re-run for a task whose notes already have a verdict, unless the context has changed (new information from the owner, the product direction document changed, the task was reworded).

## Roles and criteria

### Product owner (experienced)
Assesses **necessity**:
1. **Real pain** — the task solves a problem that was observed (a user complaint, an incident with a correlation_id, an owner's question), not a hypothetical one ("might come in handy", "for symmetry"). State the source of the pain or honestly write "no source".
2. **Product direction** — matches the product direction document (<`docs/target-picture.md` / vision / ROADMAP — specify on deployment>) and `ROADMAP.md`. If it contradicts it or falls outside it — say so plainly.
3. **Real value** — what changes for the user/owner if it is done; what breaks or is missed if it is NOT done. "Nothing" is an acceptable and important answer.
4. **Completeness of surfaces** — for a user-visible feature: is there a decision for each of the project's surfaces (`openspec/README.md` §0), for a new entity (where to view it, create / view / edit / delete) and a confirmation from the requester or owner. The request came through one surface and the others were not discussed — verdict "owner answer needed" with questions **to whoever requested it**, not "do now".

### Head of development (experienced)
Assesses **feasibility and risks**:
1. **Feasible** — the approach, the volume, the affected layers are clear.
2. **Reliable** — the solution works deterministically or degrades predictably. The project's anti-patterns (CODING_STANDARDS, "Project anti-patterns") are a direct minus to reliability; e.g. a strict schema over LLM output without coercion.
3. **Repeatable** — behaviour is reproducible and testable (there is a place to put a test according to the test pyramid).
4. **Risks and gaps** — what new can break: hot paths (<the project's hot paths: request intake, dispatcher, repositories>), security, silent no-ops, migrations.
5. **Impact on what exists** — how much code/tests are touched, whether public signatures change, backward compatibility.

## Mechanics

1. Collect the task dossier: `bd show <id>` (or the feature text), related specs in `openspec/`, relevant parts of the product direction document, and the code of the affected places if needed.
2. **Two subagents in parallel, started in a single message, working independently** (pin a reasoning model by its full id, as for review: `claude-opus-5-5`, not an alias). The owner role does not see the developer's opinion, and vice versa. Each gets: the dossier + its criteria from this file + a requirement to return a structured assessment (per criterion: conclusion + grounds) and its WSJF components (see below) with a justification for each score.
3. **Consolidation in the main session**: compare the assessments, name the disagreements explicitly (e.g. owner "no value", developer "low risk" → that is not an argument for doing it). A score disagreement of more than one step of the scale — work out whose grounds are stronger, do not average.
4. Compute WSJF, give the verdict, show it to the owner.

## WSJF

`WSJF = (BV + TC + RR) / JS`, each component on the scale 1, 2, 3, 5, 8, 13, 20:

| Component | Who assesses | Meaning |
|---|---|---|
| **BV** — business value | owner | value for the user/owner now |
| **TC** — time criticality | owner | what we lose by postponing; does the value expire |
| **RR** — risk reduction / opportunity enablement | both (take the agreed one) | does it reduce future risk, does it enable future features |
| **JS** — job size | developer | volume + technical risk of implementation (a risky small change = a large JS) |

A score without a one-sentence justification is invalid. WSJF ranks "do now/do later" among themselves but does not override a "do not do" verdict: a high score with no real pain (BV assessed on a hypothesis) is a reason to fix the BV assessment, not to do the task.

## Verdicts (exactly four)

- **do now** — the pain is real, the direction matches, the risk is manageable; WSJF gives it a place in the queue
- **do later** — there is value but it does not expire, or the risk needs prerequisites; propose `bd defer` (done by the owner or on their "yes")
- **do not do** — the pain is hypothetical, outside the direction, or the risk exceeds the value; propose closing with a reason. "Do not do" is a full-fledged positive outcome, not a failure of the assessment
- **owner answer needed** — the assessment hinges on a product fork; phrase a concrete question with a recommendation

## Output format (per task)

```
## <pfx>-XXXX — <title>
Owner: pain=<real/hypothetical: source>; direction=<yes/no/outside: where in the direction document>; value=<what changes>
Developer: feasibility=<...>; reliability=<...>; risks=<main risk>; impact=<layers/volume>
Disagreements: <what and how it was consolidated, or "none">
WSJF: (BV X + TC X + RR X) / JS X = X.X
Verdict: <one of the four> — <one sentence why>
```

For a batch of tasks — a summary table, sorted: first "do now" by descending WSJF, then "do later", "owner answer needed", "do not do".

## Red flags (signs that someone is trying to bypass the assessment)

- "The task is already in `bd ready` — so it is approved" — ready means "not blocked", not "needed"
- "For symmetry/consistency with existing code" — that is not pain, that is aesthetics; write BV as it actually is
- "Since we're in this file anyway" — scope creep, assessed as a separate task
- "Observability/tests/refactoring are always useful" — usefulness ≠ priority; still goes through WSJF
- Assessing both roles in one pass "to save money" — loses the independence the skill exists for
- A WSJF score fitted to the desired verdict — the justification for each score is written before the final formula

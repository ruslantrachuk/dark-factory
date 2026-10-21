# Practice "Incident investigation"

> Phase 10 (Operation) → layer 1. The `investigate` skill is in base; sources come from the practice
> [Observability](observability.md); the root cause in code — the practice [Code analysis](code-analysis.md).

## Why
An incident without a procedure is investigated from memory and ends with a symptomatic fix. Strong investigations follow the same
steps: key → collection → timeline → root cause with evidence → a test that "fails exactly as in production" → a regression test lower in the pyramid → a record → a rule.

## Joints
| Takes | Gives |
|---|---|
| an alert ([Observability](observability.md)) | a report: what / root cause / evidence / version / recommendation / what was missing |
| a complaint from the group ([Client feedback](feedback.md)) | an answer to the group through the On-call agent |
| a finding during work | a bug task with the report → the feature path (layers 2–4) |
| — | a record of the investigation in the devlog; a "rule + episode" entry in the project, a recurring one — into the canon |
| a timeline without a root cause | a request to [Code analysis](code-analysis.md), "figure it out" mode |

## Where it is in the canon
- Standard (base): rule 6 of the Operating contract (diagnostics ≠ permission), push-tests-down, the procedure "A test found a prod bug during the release", service ports only on loopback (`stand` skill).
- The `investigate` skill (base): preflight with measurement, input → key, collection, timeline, root-cause class, report, hand-over to work.

## Rules
- Production is read-only; changing production is done by the owner's hands.
- Facts about sources are measured, not postulated (a skill can claim a log retention period that is ten times longer than the real one).
- "Not our code" is proven by showing that code and environment did not change.
- Check along the path the user takes.
- The fix commit says why the existing tests did not catch it.
- Evidence goes to the tracker before deletion; the remaining human actions — as an explicit list.

## Open
- "Investigation by alert name" — present in the skill as an input line, but there is no automation.
- Post-mortems live in the devlog — there is no separate incident log.

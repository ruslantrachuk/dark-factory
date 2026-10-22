# Practice: Incident investigation

> Phase 10 (Operation) → layer 1; stages Monitoring and Support and feedback. The `investigate` skill is in base;
> sources come from the practice [Observability](observability.md), and the root cause in code from the practice
> [Code analysis](code-analysis.md).

## Why
An incident without a procedure is investigated from memory and ends with a fix for the symptom. Strong
investigations follow the same steps: key → collection → timeline → root cause with evidence → a test that fails
exactly as production did → a regression test lower in the pyramid → a record → a rule.

## Interfaces
| Takes | Gives |
|---|---|
| an alert ([Observability](observability.md)) | a report: what happened, the root cause, evidence, version, recommendation, what was missing |
| a complaint from the group ([Client feedback](feedback.md)) | an answer to the group through the On-call agent |
| a finding during work | a bug task with the report → the feature path (layers 2–4) |
| — | a record of the investigation in the devlog; a "rule + episode" entry in the project; a recurring one goes into the canon |
| a timeline without a root cause | a request to [Code analysis](code-analysis.md), "figure it out" mode |

## Where it is in the canon
- Standard (base): rule 6 of the operating contract (diagnostics is not permission), push-tests-down, the procedure
  "A test found a prod bug during the release", and service ports bound only to loopback (the `stand` skill).
- The `investigate` skill (base): a preflight with measurement, input → key, collection, timeline, root-cause class,
  report, hand-over to work.

## Rules
- Production is read-only; only the owner changes production, by hand.
- Facts about sources are measured, not assumed (a skill can claim a log retention period ten times longer than the
  real one).
- "Not our code" is proven by showing that neither the code nor the environment changed.
- Check along the path the user takes.
- The fix commit says why the existing tests did not catch the bug.
- Evidence goes into the tracker before it is deleted; the human actions still needed are listed explicitly.

## Open questions
- "Investigation by alert name" is an input line in the skill, but there is no automation behind it.
- Post-mortems live in the devlog; there is no separate incident log.

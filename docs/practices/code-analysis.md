# Practice "Code analysis"

> Preparation (layer 2), acceptance (layer 4), audit projects, the root cause of an incident (phase 10). The `code-audit` skill is in base;
> the module [templates/code-audit](../../templates/code-audit/MANIFEST.md) is a fan-out over many repositories.

## Why
Decisions about code are made on hypotheses: a README, the client's diagram, a service name, an agent's conclusion. A mistake costs a lot and
surfaces late: a component "moved out" according to the code while production still computes money in the legacy path; an estimate built
on an outdated document and rewritten from scratch; agents reclassifying findings, with only a minority of the reclassifications correct.

## Joints
| Takes | Gives |
|---|---|
| a task to change unfamiliar code (layer 2) | a path map with `file:line` addresses and hypotheses with statuses → into the spec/plan |
| the client's hypotheses, requirements, diagram (audit, presale) | a "hypothesis → fact" register, unit cards, a report, questions to the owner, candidate tasks |
| an incident timeline without a root cause (practice [Incident investigation](incidents.md)) | the root cause in code with evidence |
| a diff for acceptance (layer 4) | findings per the [review contract](../../templates/base/docs/review-contract.md) |

## Where it is in the canon
- Standard: `templates/base/docs/review-contract.md` — the finding format, "clean also has to be proven".
- The `code-audit` skill (base): a "figure it out" mode and an "audit" mode.
- The `code-audit` module: `audit-verify.wf.js` (fan-out + spot-checking of evidence), `clone-group.sh`, the `audit/` stencil.

## Rules
- Everything is a hypothesis until proven; tiers T1 code · T2 deployment · RT runtime · OWNER; "in the code ≠ enabled ≠ deployed".
- Evidence is an address and a quote; without it, only `not_found`.
- Agents' conclusions are accepted after spot-checking the addresses; raw runs are kept.
- Sources are labelled first: current / secondary / dead; the client's input is kept verbatim and not edited.
- The report is checked by an independent reviewer; findings become tasks only on the owner's "yes".

## Open
- A "system health audit" mode (a multi-dimensional audit prompt for your own system) — add as mode 3?
- The cost of the fan-out is not measured — there is no basis for estimating an audit in hours.

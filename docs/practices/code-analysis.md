# Practice: Code analysis

> Preparation (layer 2), acceptance (layer 4), audit projects, and the root cause of an incident (phase 10); stages
> Requirements, Testing and Monitoring. The `code-audit` skill is in base; the module
> [plugins/dark-factory/templates/code-audit](../../plugins/dark-factory/templates/code-audit/MANIFEST.md) fans out over many repositories.

## Why
Decisions about code are made on hypotheses: a README, the client's diagram, a service name, an agent's conclusion.
A mistake costs a lot and surfaces late. Examples: a component "moved out" according to the code, while production
still computes money in the legacy path; an estimate built on an outdated document and then rewritten from scratch;
agents reclassifying findings, with only a minority of the reclassifications correct.

## Interfaces
| Takes | Gives |
|---|---|
| a task to change unfamiliar code (layer 2) | a map of code paths with `file:line` addresses, and hypotheses with statuses → into the spec or plan |
| the client's hypotheses, requirements, diagram (audit, presale) | a "hypothesis → fact" register, unit cards, a report, questions to the owner, candidate tasks |
| an incident timeline without a root cause (the practice [Incident investigation](incidents.md)) | the root cause in code, with evidence |
| a diff for acceptance (layer 4) | findings in the format of the [review contract](../../plugins/dark-factory/templates/base/docs/review-contract.md) |

## Where it is in the canon
- Standard: `plugins/dark-factory/templates/base/docs/review-contract.md`: the finding format, and "clean also has to be proven".
- The `code-audit` skill (base): a "figure it out" mode and an "audit" mode.
- The `code-audit` module: `audit-verify.wf.js` (fan-out and spot-checking of evidence), `clone-group.sh`, the
  `audit/` stencil.

## Rules
- Everything is a hypothesis until proven. Evidence tiers: T1 code, T2 deployment, RT runtime, OWNER. "In the code"
  is not "enabled", and "enabled" is not "deployed".
- Evidence is an address and a quote; without one, the only allowed answer is `not_found`.
- Agents' conclusions are accepted after the addresses are spot-checked; raw runs are kept.
- Sources are labelled first: current, secondary or dead. The client's input is kept verbatim and not edited.
- An independent reviewer checks the report; findings become tasks only on the owner's "yes".

## Open questions
- A "system health audit" mode (a multi-dimensional audit prompt for your own system): add it as mode 3?
- The cost of the fan-out is not measured, so there is no basis for estimating an audit in hours.

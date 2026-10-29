# Review contract: finding format and triage rules

> The canon for any review in the project: workflow review phases, two-stage spec+quality, 360 audit,
> triage of `/simplify`, the spec skeptic. It materializes factory principles #7 ("a loud signal is better than silent
> corruption") and #8 ("do not trust agents' self-reports"). Several techniques are credited to
> pavel-molyanov/molyanov-ai-dev (MIT).

## The reviewer's role

Fresh context, read-only. The reviewer diagnoses: does not edit the artifact, does not design the fix, does not
decide whether the work goes to merge. The goal is accuracy, not the number of findings; "zero findings" is a valid
result if it is proven (see clean_check).

## A finding is valid only when complete

| Element | What is required |
|---|---|
| **Location** | file:line / document section |
| **Evidence** | observed code or text, not a retelling from memory |
| **Violated requirement** | a specific item of the spec, standard, layer contract or request |
| **Trigger conditions** | a realistic path in the current project by which the defect is reached |
| **Impact** | what exactly breaks under these conditions |

Not findings (report them in a separate section, do not mix): matters of taste, "for the future",
hypothetical edge cases without a trigger path, pre-existing defects outside the diff.

Severity follows the proven impact, not the category: **critical** (security / data loss /
crash / broken cross-file contract) · **major** (a material defect of correctness,
reliability or maintainability) · **minor** (a real local weakness with limited effect).

## "Clean" is proven too (clean_check)

A "clean" verdict must list: which risks were checked, where it looked, why a violation is not proven.
"LGTM" without this is an invalid result — request it again. The checker must prove it was
capable of finding something.

## Triage of findings (orchestrator / human)

1. **Findings are a diagnosis, not a work queue.** Each one is verified by a run or by reading the code;
   an unconfirmed one is rejected with a recorded reason (review does make mistakes).
2. **A finding does not expand scope.** A fix is applied only if it is inside the agreed work;
   "while I'm in there" is forbidden. Everything else is a proposal to the human (card/bd), not an edit.
3. **`user_decision_required`.** A rare or unagreed scenario, a non-local fix, a new
   entity / dependency / behaviour — a question to the human, not a silent edit. A `false` value from
   the reviewer does not by itself authorize an edit — the check of items 1–2 is always mandatory.

## Wave limit

- Implementation and documentation: **at most 2 waves**. A wave = the full set of applicable reviewers
  in parallel on one revision; fixes after wave 1 → wave 2 with the same set on the new revision.
- Spec validation: **at most 3 rounds**.
- After the limit no new cycle is started: the remaining findings and questions go into a report to the human
  (handoff / REVIEW), honestly and as a list.

## Spec skeptic (proposal / design)

For a large release, before implement — a separate fresh read-only run that tries to
**refute the spec's factual claims about the codebase**: files, symbols, dependencies,
integrations, current behaviour. It catches the "confident nonsense" of the context that wrote the spec itself.

Skeptic severity: **critical** — the spec relies on something that does not exist; **major** — it exists, but
the name / location / contract is materially different; **minor** — an inaccuracy with a concrete consequence for the
plan. Finding format and triage — this same contract.

## Result format (for workflows)

The feature pipeline enforces this shape with a schema; a reviewer by hand reports the same fields.

```json
{
  "dimension": "the lens",
  "findings": [
    {
      "file": "src/example.py",
      "line": 42,
      "summary": "what is violated, the evidence read, the trigger path and the impact; for a product decision — say so",
      "severity": "critical | major | minor",
      "fix": "one line: what to change, not a patch"
    }
  ]
}
```

A complete finding still carries everything above (location, evidence, violated requirement, conditions, impact) —
inside `summary`. An empty `findings` list is a "clean" result only with what was checked, where and why no violation
is proven, given in the reviewer's answer. The reviewer gives at most a one-line `fix`: no patches, redesigns or merge
verdict. A fix that would change behaviour, design or texts beyond the source is a product decision for the human; the
Fix step rejects it and names it.

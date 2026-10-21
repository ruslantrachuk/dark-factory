# The Acceptance and release layer — understanding

> Layer 4 of [process.md](../process.md): input — a branch + the queue digest, output — a feature on the stand or a typed return.

## Typical pain

Features are most often done well; the overhead is expensive: part of the checks could have been done before the human, and after the verdict "we spend 20 minutes merging and pushing through an LLM instead of scripts". UX defects are caught only by eye. Commit formatting "keeps misfiring".

## Decisions

1. **The entry standard of acceptance** — the machine presents, before the human: an independent **review on substance** (are the requirements covered? common sense? — the reviewer is independent of the author; the tool is configurable), **green CI on each feature branch** (branches are pushed before review, the full matrix runs in CI; the developer runs a fast subset), the stand is up. Entry not met → return to production; this is not acceptance.
2. **The incompressible human minimum**: a living eye on the stand + a verdict + typing the return.
3. **Return types confirmed by practice**: code defect → production; test defect → to the agent (it fixes them well); understanding defect → to preparation, the spec is corrected. **The type is set by a human** — an agent cannot tell "the wrong thing" from "the right thing with a bug".
4. **After "accepted" — automatically to In Master, by scripts**: merge, push, release notes, statuses, final close. Exceptions are project configuration. Shipped — by the rules of the `board` skill (a separate command, proof of delivery).
5. **The commit/notes standard** ("human-readable, no lyricism, professional") is built into the transaction script, not into the agent's memory.

## Open ends for the design

- The merge-transaction script; routing of returns in the digest.
- Pushing branches before acceptance — check against the restrictions of projects behind a perimeter (per project).
- A "review on substance" checklist — assembled from the review phase and the REVIEW.md hand-over format ([methodology.md](../methodology.md) §1.9).

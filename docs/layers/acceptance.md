# The Acceptance and release layer

> **Stages:** the human half of Testing, and Release (phases 7–8 of [map.md](../map.md)).
> Layer 4 of [process.md](../process.md). Input: a branch and the run's hand-over. Output: the feature in the preview
> environment, or a return with a stated reason.

## Typical pain

Features are usually done well, but the overhead around them is expensive. Some of the checks could have run before
the human looked, and after the verdict "we spend 20 minutes merging and pushing through an LLM instead of scripts".
UX defects are caught only by looking. Commit formatting "keeps misfiring".

## Decisions

1. **The entry standard for acceptance.** Before the human looks, the machine presents: an independent **review of
   substance** (are the requirements covered? does it make sense? The reviewer is independent of the author; the
   tool is configurable); **green CI on each feature branch** (branches are pushed before review and the full matrix
   runs in CI, while the developer runs a fast subset); and a running preview environment. If the entry standard is
   not met, the work goes back to production; this is not acceptance.
2. **The human minimum that cannot be cut**: a hands-on review in the preview environment, a verdict, and the reason
   for any return.
3. **Return reasons confirmed by practice**: a code defect goes back to production; a test defect goes to the agent
   (it fixes those well); an understanding defect goes back to preparation, and the spec is corrected. **A human
   states the reason**: an agent cannot tell "the wrong thing" from "the right thing with a bug".
4. **Once CI is green and the agent has reviewed its own change, scripts move the work to `Merged` automatically**:
   merge, push, release notes, statuses, final close. Exceptions are part of the project configuration. At
   `team` the PR also needs a person's GitHub approval; below it the human gate is the release, a later stage.
   `scripts/merge-feature.sh <branch>` does the mechanics and writes the PR description to the merge commit. The
   guard denies a bare merge on the code host (`gh pr merge`), so the script is the one way to merge. When CI cannot run at all, the owner may add `--skip-ci "<reason>"`: a local gate runs instead
   and the merge is marked as made without CI (refused at the `team` fence level). Moving to `Shipped` follows the rules of
   the `board` skill (a separate command, with proof of delivery).
5. **The commit and release-notes standard** (readable, no filler, professional) is built into the transaction
   script, not left to the agent's memory.

## Open questions

- Routing a return, with its stated reason, from the hand-over back to production or to preparation.
- Pushing branches before acceptance: check it against the restrictions of projects behind a perimeter (per
  project).
- A checklist for the review of substance, assembled from the review phase and the REVIEW.md hand-over format
  ([methodology.md](../methodology.md) §1.9).

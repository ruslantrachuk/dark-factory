# The Acceptance and release layer

> **Stages:** the human half of Testing, and Release (phases 7–8 of [map.md](../map.md)).
> Layer 4 of [process.md](../process.md). Input: a branch and the run's hand-over. Output: the feature on the dev
> stand, accepted, or a return with a stated reason.

## Typical pain

Features are usually done well, but the overhead around them is expensive. Some of the checks could have run before
the human looked, and after the verdict "we spend 20 minutes merging and pushing through an LLM instead of scripts".
UX defects are caught only by looking. Commit formatting "keeps misfiring".

## Decisions

1. **The entry standard for acceptance.** Before the human looks, the machine presents: an independent **review of
   substance** (are the requirements covered? does it make sense? The reviewer is independent of the author; the
   tool is configurable); **green CI on each feature branch** (branches are pushed before review and the full matrix
   runs in CI, while the developer runs a fast subset). If the entry standard is not met, the work goes back to
   production; this is not acceptance.
2. **Merge is "to the dev stand", not acceptance.** Once CI is green and the agent has reviewed its own change,
   scripts move the work to `Merged`: `scripts/merge-feature.sh <branch>` does the mechanics and writes the PR
   description to the merge commit. The merge puts the feature on the **dev stand**, the environment that runs
   `main` (the `dev-stand` skill). At `team` the PR also needs a person's GitHub approval. The guard denies a bare
   merge on the code host (`gh pr merge`), so the script is the one way to merge. When CI cannot run at all, the
   owner may add `--skip-ci "<reason>"`: a local gate runs instead and the merge is marked as made without CI
   (refused at the `team` fence level).
3. **Acceptance happens on the dev stand, in one of two flows.**
   - *The owner develops.* The owner has several features built, asks for them to go into main, looks at the dev
     stand and says "release". That sentence, said in the interactive session and confirmed in the permission
     dialog of the release, is the acceptance of everything in main since the last release.
   - *Clients order through the On-call.* When the feature is on the dev stand, the On-call asks in the chat
     "ship?" with what changed; a yes from anyone on the project's acceptance list (`DESK_OWNER_IDS`) accepts any
     feature, and the On-call marks the PR accepted. When everything since the last release is accepted, the On-call may
     release.
4. **The acceptance mark lives on the code host and is tracker-neutral:** a merged PR carries the label `accepted`
   and a comment `accepted by <who>, <link to the message, its id in a group without links, or "permission dialog">`.
   Who asked for a feature is recorded on the board card, when the project has a board.
5. **Production comes from the `release` branch, moved by a verified tag** `vYYYY.MM.DD.N`
   ([release-tag module](../../plugins/dark-factory/templates/release-tag/MANIFEST.md)). **A release takes all of
   main**, so `scripts/release.sh` lists every first-parent commit since the last tag (a merge, a squash and a rebase alike) and **refuses while any
   PR lacks the mark**,
   naming each unaccepted feature with its title so whoever releases can ask again. Two overrides, both
   recorded: `--owner-accepts` (the owner, in the interactive session, accepts everything listed: each PR gets the
   mark with the comment "accepted by the owner, permission dialog") and `--include-unaccepted "<who allowed>"` (ships
   without the mark; the name goes into the annotated tag and the release notes). A commit that is not a PR
   (no `(#N)` in its subject) is listed and needs one of them. `--manual` (emergency, no tests) and `--publish` (CI) are unchanged.
6. **Who may decide is fenced in code.** A run of `release.sh` that tags, and a label or comment set by hand, are
   asked in the permission dialog ("a release ships all of main since the last tag to production; Yes = you accept
   it"). In the On-call (`DF_ROLE=on-call`) only `scripts/feedback-desk.sh accept|release` runs, and the script
   checks that the sender is on the acceptance list; `--owner-accepts` and `--manual` are denied there. Every
   other launched agent (subagent, pipeline, scheduled run, `claude -p`) is denied: leave the release to the owner
   or the On-call. Setting `DF_ROLE`, `DF_UNATTENDED`, `DESK_*` or `RELEASE_GH` (inline, exported or through `env`) is
   a fence change like `GUARD`: a child `claude` would inherit the On-call's allowances. The On-call may run only
   its wrapper (the project's own `scripts/feedback-desk.sh`, by its path from the project root) and the read-only
   `scripts/release.sh --list-unaccepted`; a release goes only through the wrapper, which reads the owner list and
   the `gh` command from the config file alone.

   **The limit of a static guard.** The guard reads the command line. A command built indirectly (a variable holding
   the path, `bash -s < file`, an interpreter that runs the script) is outside what it can read. The real gate is on
   the code host: a tag ruleset where only the release manager's token may push `v*`, so a release that skipped the
   check still cannot ship.
7. **When something else would ship unaccepted, re-ask.** If the feature being released is accepted but another one
   in main is not, the On-call says so: "together with Pasha's feature, voice-input ships — Vlad hasn't accepted it
   yet. Ship?". A yes from anyone on the acceptance list allows `--include-unaccepted`.
8. **The human minimum that cannot be cut**: a hands-on look on the dev stand, a verdict, and the reason for any
   return.
9. **Return reasons confirmed by practice**: a code defect goes back to production; a test defect goes to the agent
   (it fixes those well); an understanding defect goes back to preparation, and the spec is corrected. **A human
   states the reason**: an agent cannot tell "the wrong thing" from "the right thing with a bug".
10. **The commit and release-notes standard** (readable, no filler, professional) is built into the transaction
    script, not left to the agent's memory. Moving a card to `Shipped` follows the rules of the `board` skill (a
    separate command, with proof of delivery).

## Open questions

- A deterministic sender check for the On-call's "yes": the sender id is retyped by the model from the channel tag, so
  `accept` checks it against the PR and the owner list but cannot prove it (see the feedback-desk manifest).
- Routing a return, with its stated reason, from the hand-over back to production or to preparation.
- Pushing branches before acceptance: check it against the restrictions of projects behind a perimeter (per
  project).
- A checklist for the review of substance, assembled from the review phase and the REVIEW.md hand-over format
  ([methodology.md](../methodology.md) §1.9).

---
name: ship
description: The merge transaction after a human says "accepted" — push, PR, CI and merge in one script command, then the card moves to Merged; and the ship transaction for "I'm shipping" (release notes, Shipped). Use for "accepted", "merge it", "ship it".
disable-model-invocation: true
---

# Skill `ship` — delivery (a thin layer over a script)

> Canonical template (templates/base). Principle: **a script does the mechanics; the model only starts it and
> handles the cases the script cannot** (a decision of the "Acceptance" layer). This is the GitHub variant.

> **Seam:** code host = GitHub (`gh`, through `scripts/merge-feature.sh`); board = the `board` skill. To use another tool, rewrite `scripts/merge-feature.sh` and the Merge transaction and Ship transaction sections.

## Configuration (fill in on deployment)

- Main branch: <`main`>; merge strategy: <`--merge` (recommended)/`--squash`>, set in `scripts/merge-feature.sh`.
- Fence level: `.claude/fences.env` (`solo`/`standard`/`team`); at `team` the script also requires a GitHub approval and refuses `--skip-ci`.
- Deploying to the preview environment: <the project's procedure, or "none">.
- Project exceptions (what must NOT happen automatically even after "accepted"): <e.g. migrations, production writes — or "none">.
- **Two repositories** (a harness parent plus the code in a submodule or a separate repository): the project **overrides** this procedure. The merge goes into the code repository (a PR or MR on its host); after it, the parent bumps the submodule pointer; `merge-feature.sh` is replaced or extended by a project-specific script.

## Hard rules

1. **The only input is an explicit "accepted" or "merge it" from a human.** Without it the skill merges nothing. The person's name goes into `--accepted-by "<name>"`, as they gave it; the script refuses without it and records it (a PR comment and an `Accepted-by:` trailer on the merge commit). At `solo` and `standard` the name is recorded, not verified; at `team` the script also requires a GitHub approval. Red CI means no merge (built into the script). A human invokes the skill (`/ship`); the model does not pick it up on its own.
2. **Write for people.** The PR title and release notes are plain, professional prose: no clipped note-taking style, no file paths, no filler. This is part of the transaction, not a nice-to-have.
3. The script does not fix things. Red CI or a conflict ends in **an honest failure**: tell the human what got stuck and where, and suggest where the work goes back to; the human decides.

## Merge transaction ("accepted", per feature)

0. **Before the push, put the accompanying changes on the branch.** `devlog.md` must differ from the main branch (otherwise the script refuses); if this PR ships a release, the `ROADMAP.md` line and `SHIPPED.md` go on the branch too. Merging into main is the rollout: nothing is pushed to main as a separate commit afterwards (this matters most when main auto-deploys). Forgot something? Bring it with the next feature branch, not as a follow-up commit on main.
1. Write the PR title (rule 2). In the PR description name the board card: `Part of <PREFIX>-N` (or `Closes <PREFIX>-N` if the PR finishes the card). Branches carry the bd id; this mention is the only link to the card.
2. `scripts/merge-feature.sh <branch> "<title>" --accepted-by "<name>"`. The script closes the bd task (taking the full bd id from the end of the branch name; otherwise it says "close it by hand"), commits the queue export onto the feature branch itself (not onto main), pushes, opens the PR, waits for CI, merges (a merge commit, so code, devlog, ROADMAP/SHIPPED and the queue reach main together) and updates the local main branch. If the merge does not happen (red CI, timeout), the bd task goes back to in-progress automatically; re-running the script closes it again.
   Team mode (`FENCE_LEVEL=team` or `MERGE_REQUIRE_REVIEW=1`): the script refuses until the PR's review decision is APPROVED. A teammate approves on GitHub; the agent does not approve (the guard denies `gh pr review --approve`).
   The script is safe to **re-run** with the same `--accepted-by`: it recognises a PR that is already merged, skips the steps already done and finishes the rest. Unfinished steps end with a non-zero exit code and a list, not with a "do this by hand" warning and exit code 0. It waits up to 10 minutes for CI checks to appear (GitHub does not create them instantly), and a network failure while waiting is not treated as red CI.
   No CI at all (a solo project with no workflows): the script runs the local gate instead and records `CI: none (local gate)` in the merge commit. At `team` this is refused.
3. Board card → `Merged`, with a comment linking to the PR (the merge transaction of the `board` skill). If the project has Linear's GitHub automation connected (PR merged → Merged), the status moves by itself; do not repeat it by hand, only check.
4. Several accepted features: repeat per feature (each branch on its own, shipping in parts).

## Fallback: CI exists but cannot run

Sometimes Actions does not start for reasons that have nothing to do with the code: a billing problem on the GitHub account, limits, a platform incident. Then, and only then, the merge goes ahead without CI, through the same script:

`scripts/merge-feature.sh <branch> "<title>" --accepted-by "<name>" --skip-ci "<reason>"`

Conditions: (1) the owner explicitly said "merge without CI" and gave the reason, which goes into `--skip-ci` as given; (2) the script does not wait for checks and runs the local gate instead (the pre-push test command over the branch range, or `LOCAL_GATE_CMD`); a red local gate cancels the merge; (3) the script posts a prominent PR comment "Merged WITHOUT CI by <name>: <reason>" and adds a `CI-skipped: <reason>` trailer; (4) the branch's devlog entry names the reason and the local run. If CI turns out to be green after all, the script merges the usual way. At `FENCE_LEVEL=team` `--skip-ci` is refused: the team merges on CI only. `--skip-ci` is not a way around red CI; failing tests get fixed, not skipped.

## Ship transaction ("I'm shipping <project>"), only on an explicit command

The rules and steps live in the `board` skill (list the Merged cards → confirmation → proof of delivery → `git tag` + `gh release create --generate-notes` with the notes edited into readable prose → cards to Shipped → statuses copied to the client's tracker). This skill does the git/gh part; deployment follows the project's own procedure, not this skill.

## What the skill does NOT do

- It does not merge without an explicit "accepted" and the accepting person's name, and does not move cards past Merged without the "I'm shipping" command.
- It does not deploy.
- It does not fix red CI or conflicts; it only reports them.

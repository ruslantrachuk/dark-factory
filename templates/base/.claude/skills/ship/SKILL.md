---
name: ship
description: Merge transaction after a human's "accepted" — push/PR/CI/merge in one command via a script, card to In Master; and the "I'm shipping" ship transaction (release notes, Shipped). Use for "accepted", "merge it", "ship it".
disable-model-invocation: true
---

# Skill `ship` — delivery (a thin layer over a script)

> Canonical template (templates/base). Principle: **mechanics — by a script, the LLM — the button and the handler of non-standard cases** (a decision of the "Acceptance" layer). GitHub variant; a closed perimeter (GitLab/VPN) is a separate corp-perimeter module.

> **Seam:** code host = GitHub (`gh`, through `scripts/merge-feature.sh`); board = the `board` skill. To use another tool, rewrite `scripts/merge-feature.sh` and the Merge transaction and Ship transaction sections.

## Configuration (fill in on deployment)

- Main branch: <`main`>; merge strategy: <`--merge` (canon recommendation)/`--squash`> — set in `scripts/merge-feature.sh`.
- Fence level: `.claude/fences.env` (`solo`/`standard`/`team`); at `team` the script also requires a GitHub approval and refuses `--skip-ci`.
- Deploy to the stand: <the project's procedure or "none">.
- Project exceptions (what must NOT be done automatically even after "accepted"): <e.g. migrations/prod writes — or "none">.
- **Two repos** (a harness parent + code in a submodule/separate repo): the project **overrides** the procedure — the merge goes into the code repo (an MR on its hosting), after the merge — a bump of the submodule pointer in the parent; the merge-feature.sh script is replaced/extended by a project-specific one.

## Iron rules

1. **The input is only an explicit "accepted" / "merge it" from a human.** Without it the skill merges nothing. The human's name goes into `--accepted-by "<name>"` — the person who said it, as they said it; the script refuses without it and records it (a PR comment and an `Accepted-by:` trailer of the merge commit). Red CI = the merge will not happen (built into the script). The skill is invoked by the human (`/ship`), not picked up by the model on its own.
2. **Texts are human-readable, no fluff, professional**: the PR title and release notes are prose for people, not telegraphese and not file paths. This is part of the transaction, not a wish.
3. The script does not fix things: red CI or a conflict → **an honest fail** — report to the human what got stuck and where, propose a return (the human sets the typed return).

## Merge transaction ("accepted", per feature)

0. **Before push — accompanying changes into the branch.** `devlog.md` must differ from the main branch (otherwise the script refuses); if this PR ships a release — the `ROADMAP.md` line and `SHIPPED.md` also go into the branch. Merge into main = rollout: after the merge nothing is pushed to main as a separate commit (especially important if main = auto-deploy). Forgot something — bring it in with the next feature branch, not as a tail in main.
1. Phrase the PR title (rule 2). In the PR description name the board umbrella: `Part of <PREFIX>-N` (or `Closes <PREFIX>-N` if the PR closes the umbrella entirely) — branches carry the bd id; only this mention links them to the card.
2. `scripts/merge-feature.sh <branch> "<title>" --accepted-by "<name>"` — closes the bd task (the full bd id at the end of the branch name; otherwise it says "close by hand") and commits the queue export into the feature branch itself (not into main), push, PR, waiting for CI, merge (a merge commit — code + devlog + ROADMAP/SHIPPED + queue enter main in one merge), update of the main branch. The merge did not happen (red CI/timeout) → the bd task is returned to work automatically (a trap in the script); re-running the script closes it again.
   Team mode (`FENCE_LEVEL=team` or `MERGE_REQUIRE_REVIEW=1`): the script refuses until the PR's review decision is APPROVED — a teammate approves on GitHub; the agent does not approve (the guard denies `gh pr review --approve`).
   The script is safe to **re-run** (with the same `--accepted-by`): it recognizes an already merged PR, skips the tail steps already done and finishes the unfinished ones; unfinished steps end with a non-zero exit code and a list, not with "⚠️ … by hand" at exit code 0. It waits up to 10 minutes for CI checks to appear (GitHub does not create them instantly), and does not treat a network failure while waiting for CI as red CI.
3. Board card → `In Master` + a comment linking to the PR (the merge transaction of the `board` skill). If the project has Linear's GitHub automation connected (PR merged → In Master) — the status moves by itself; do not duplicate it by hand, only check.
4. Several accepted features — repeat per feature (each branch separately, shipping in parts).

## Fallback path: CI unavailable

Sometimes Actions do not start for reasons unrelated to the code: a GitHub account billing failure, limits, a platform incident. Then, and only then, the merge goes without CI, through the same script:

`scripts/merge-feature.sh <branch> "<title>" --accepted-by "<name>" --skip-ci "<reason>"`

Conditions: (1) the owner explicitly said "merge without CI" and named the reason — the reason goes into `--skip-ci` as given; (2) the script does not wait for checks and runs the local gate instead (the pre-push test command over the branch range, or `LOCAL_GATE_CMD`); a red gate cancels the merge; (3) the script writes a loud PR comment "Merged WITHOUT CI by <name>: <reason>" and a `CI-skipped: <reason>` trailer; (4) the devlog of the branch names the reason and the local run. If CI turns out green, the script merges the usual way. At `FENCE_LEVEL=team` `--skip-ci` is refused — the team merges on CI only. `--skip-ci` is not a way around red CI: failing tests are fixed, not skipped.

## Ship transaction ("I'm shipping <project>") — only on an explicit command

Rules and steps — in the `board` skill (list In Master → confirmation → proof of delivery → `git tag` + `gh release create --generate-notes` with the notes edited into human-readable form → cards to Shipped → carrying statuses over to the client tracker). This skill performs the git/gh part; deployment — by the project's procedure, not from here.

## What the skill does NOT do

- Does not merge without an explicit "accepted" and the accepting person's name; does not move cards beyond In Master without the "I'm shipping" command.
- Does not deploy.
- Does not fix red CI/conflicts — only reports.

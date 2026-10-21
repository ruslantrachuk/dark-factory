# <Project> — CLAUDE.md

> Single entry point for AI and humans. `AGENTS.md` loads this file via `@CLAUDE.md`.
> Skeleton from the factory template (dark-factory `templates/base/`); everything in `<angle brackets>` is filled in at deployment.

## ⚡ Operating contract (always read first)

Seven inviolable rules. Details are further down the file; here is what must not be broken.

1. **Code goes out only through the standard procedure** (<`ship` skill / gh pr>): push → MR/PR → CI → merge. Do not read or print tokens/credentials by hand.
2. **The work queue is beads** (`bd ready` → claim → close). The board (Linear, `board` skill) holds human umbrella cards; the machine queue is not mirrored to the board. **One epic = one branch/PR.**
3. **Code only through a feature branch** `r{N}/<type>-<slug>-<id>` from a fresh <`master`/`main`>; committing code directly to the main branch is FORBIDDEN. Documentation/process (`*.md`, `openspec/`, `devlog.md`) may go directly; editing `openspec/changes/` is session work, and pre-push requires a devlog entry for it. `.beads/` (closing a task, queue export) travels in the feature branch in the same PR as the code — not as a separate commit to the main branch after the merge (especially important if main = auto-deploy: an extra commit means an extra redeploy).
4. **The stand runs detached** (`nohup … & disown`, not as a Bash-tool background job); do not stop someone else's stand without asking.
5. **Commits/pushes/release notes — in <project language, default English>, human-readable, no fluff, professional**; conventional; do not push/merge without an explicit "yes"; merge only on green CI.
6. **A finding/idea along the way is a proposal, not an authorization.** Scope is set by the request/spec; research, review and diagnostics do not by themselves authorize changes; a rare or unagreed scenario is a human decision, even if the fix looks local. Review findings are handled per [docs/review-contract.md](docs/review-contract.md).
7. **Understanding a feature = an answer to how the user interacts with it on EVERY surface — before development starts.** Project surfaces: <bot chat, mini-app, web version, outgoing bot messages / screens and roles of the project>; for a new entity — where to view it and which of create/view/edit/delete ships. This is the first step of handling a request, before the spec, the bd task and the code. Questions go to the requester; answers with confirmation go into the proposal. Not clarified — the feature is not understood and is not taken into work ([openspec/README.md](openspec/README.md) §0; a feature built for only one surface — e.g. chat only — ends up being removed entirely).

## ⚙️ Environment

The source of truth for "where am I" is the per-machine marker `.claude/env` (gitignored); the SessionStart hook prints a capability block ([.claude/hooks/env-context.sh](.claude/hooks/env-context.sh)). For a project without a night loop this is an informational line; the night-local module adds operation watchdogs to the marker.

**Claude subscription quota** is shared per account (5h and 7d windows); a hook-based watchdog ([docs/quota-guard.md](docs/quota-guard.md)): from 80% no new work (subagents, claim), from 85% wrap up, at 90% only save work. The watchdog message names the time when work resumes: when autonomous — save, schedule a continuation for that time and end the turn; otherwise tell the human the time. `python3 scripts/quota.py status` shows the current state; bypass is for humans only: `QUOTA_GUARD=off claude`.

**Git worktree — five known traps** (each one has recurred on factory projects):
1. Tools that create worktrees write an absolute `core.hooksPath` pointing to the main checkout into `config.worktree` — hooks run from another branch. The SessionStart hook `ensure-git-hooks.sh` reinstalls them itself and warns loudly if pre-push is not active; outside a Claude session run `./scripts/install-git-hooks.sh` right after creating the worktree.
2. Each worktree has its own beads store. The first `bd` in a fresh worktree wipes `.beads/issues.jsonl`, and `bd export` silently drops tasks that are not in that store. Restore the queue: `bd import .beads/issues.jsonl`; reconcile: `bd stats` against `wc -l .beads/issues.jsonl`. Leaking this outward is blocked by `.githooks/pre-commit` (guard `scripts/bd-queue-guard.sh`).
3. Gitignored files (`.env`, the stand database, tokens) are not copied into a worktree — refer to them by the absolute path of the main checkout, do not create copies.
4. Reconciling the harness with the canon: `scripts/harness-diff.sh` (deployment SHA — `.harness/base-sha`). The canon moves ahead, and projects re-fix locally what is already fixed — reconcile during a review pass, not during a fire. What else can be installed on top of base and when it is time — the module catalog [.harness/modules.md](.harness/modules.md); propose it to the owner, do not install it yourself.
5. `.claude/settings.local.json` is gitignored — a session opened in a worktree does not see the main checkout's local permissions, and agents get a permission prompt for every file. Shared project permissions (`additionalDirectories` + `Bash`) go into `~/.claude/settings.json`; the SessionStart hook warns about it. Agent worktrees live inside the session directory (`.claude/worktrees/`, in `.gitignore`): outside it, Workflow does not run nested scripts.

## Overview

**<Project>** — <what it does, for whom, which manual work it replaces>.

**Stack:** <languages / frameworks / DB / deployment>. Full picture — [ARCHITECTURE.md](<path>).

## Onboarding (reading order)

1. `README.md` — what it is and how to run it
2. **This file** — contract, GATE, principles, constraints
3. `ARCHITECTURE.md` — the big picture
4. `CODING_STANDARDS.md` — code rules; per-layer in `docs/standards/`
5. `naming.yaml` — project map and glossary
6. `openspec/README.md` — development cycle
7. `ROADMAP.md` — release overview
8. `devlog.md` — latest entry (continuation point)

## SESSION LOOP: devlog as memory (blocking step before and after work)

**Opening**: before any action, read the latest entry of `devlog.md` (the SessionStart hook `session-context.sh` injects it at the start of the session together with the branch and recent merges) (the devlog is in reverse chronological order); the "Open questions" and "Next session" blocks are continuation points; a conflict with the user's request must be raised before work starts. Skip only for ad-hoc commands outside project work.

**Closing**: the session is not finished until an entry following the template (the template is an HTML comment inside devlog.md) is added at the top of `devlog.md`: Done / Decisions (architectural → ADR) / Open questions (file them in bd immediately, otherwise they are invisible in the queue) / Next session. Release-level shipped work → update `ROADMAP.md` + `SHIPPED.md`. All of this goes **into the feature branch before the merge**, in the same PR as the code (`merge-feature.sh` refuses to push if the devlog is untouched); after the merge to main nothing is pushed as a separate commit — if you forgot before the merge, carry it with the next branch.

**Enforce**: a pre-push git hook blocks pushing code without a devlog update (`./scripts/install-git-hooks.sh` once after clone).

## GATE: before any code (blocking step)

**DO NOT WRITE A SINGLE LINE OF CODE** until these steps are done.

### Step 0 — Superpowers (template dependency: the Superpowers plugin)

| Task type | Mandatory skills |
|-----------|---------------------|
| New feature | **surface questions to the requester and their confirmation (rule 7)** → `brainstorming` → `writing-plans` → `test-driven-development` |
| Bug fix | `systematic-debugging` → `test-driven-development` |
| Refactoring | `writing-plans` → `test-driven-development` |
| Approved spec → execution | `openspec-to-beads` (phases → bd graph) |
| Any commit | `verification-before-completion` |

TDD is mandatory (RED → GREEN → REFACTOR); brainstorming comes before the code of a new feature; writing-plans for tasks touching >1 file.

### Step 1 — Tracker (beads) + feature branch

1. `bd ready` → claim a suitable task; if none, create one before coding (`bd create … --acceptance="…"`). Do not create tasks by hand from an approved spec — use `openspec-to-beads`.
2. Branch `r{N}/<type>-<slug>-<id>` from a fresh <`master`/`main`>. `r{N}` is the release train from `openspec/CURRENT_TRAIN` (do not guess; a human increments it). One epic = one branch.
3. The execution tier (`scale`) and the elaboration command are set **by the human during preparation** — the agent does not guess.

> **Red flag (forbidden workaround):** "I'll create a TodoWrite per phase" instead of bd. Writing code without an `in_progress` task in bd — go back to Step 1.

### Step 2 — Standards

Read `CODING_STANDARDS.md` in full + the per-layer file for the task's layer + `naming.yaml`. Skipping = automatic review failure.

### Step 3 — User guide (projects with a user UI; features that change a screen or user behaviour)

Project flag: `<user guide: yes / no — bot, library, own help packaging>` (asked at deployment, MANIFEST). With "no" the step does not apply and there is no `docs/user-guide/` folder in the project. With "yes": a feature with a screen is not closed until `docs/user-guide/` is updated (the bar — `DOCUMENTATION_STANDARDS.md` §6): a page for the user's task, a screenshot via the script `python -m tests.e2e.make_screenshots` (do not capture by hand), links via `scripts/check_doc_links.py`. This is a GATE step, not "later": in a project without this step the user guide never appears at all (a finished SPA with no guide is the typical outcome).

## Engineering Principles

> Without explicit principles the model builds "spaceships". Mandatory for any work.

- **KISS** · **YAGNI** · **MVP first** · **Fail Fast** (errors early and explicit, no silent excepts) · **Iterative** (1 feature at a time, each testable and committable)
- **OpenSpec-driven** — code follows an explicit plan; a change folder only for a contract change, not for every train
- **Explicit hand-off to the machine** — the machine does not guess scope, tier or train number
- **Slice end to end, not by layers.** Each part of a feature, after its commit, works from the entry point (webhook, route, dispatcher) to the result at least for its own scenario and is covered by an entry-level test. Slicing "data → sending → wizard → dispatcher" leaves the feature unwired between parts, and a dead path passes all tests (caught by review only by chance).
- **Shared layer first, the second feature on top.** Before coding, compare the plan's files with unmerged branches in progress; if the code overlaps, merge that branch first or merge it into this one. Two parallel features that each introduce the same schema and the same method lead to conflicts and manual cleanup of duplicates.
- **Reachability.** A new path must actually reach real users: check that nothing upstream intercepts it — a kill switch, a flag or an early dispatcher branch — and that the entry test goes through the same path as the user. The entry point must be one that is actually possible in the external API. An unreachable path is a review blocker (green tests on a path users never reach; a spec requiring handling of an update the external platform never sends).
- <project principles: e.g. Decimal for money / honesty towards external sources>

## Constraints — what the AI must NOT do

- ⛔ Do not push/merge code without explicit approval
- ⛔ Do not read/print secrets and tokens
- ⛔ Do not run tests (including e2e and nightly ones) against real LLMs and paid external APIs with a real key — only a fake server or a recorded response; a test that needs a live key is skipped until a fake exists, and the secret is removed from the workflow (an expired key otherwise keeps the nightly e2e red). Exception — the LLM quality eval gate: a manual run before shipping, key from CI secrets (CODING_STANDARDS, "Logging and LLM")
- ⛔ <project prohibitions: PII in logs, hard-coded coefficients, repo boundaries…>

## Finishing a feature: syncing charter documents (blocking step)

Update everything the feature touched: `docs/user-guide/` (project with a user guide, feature with UI — mandatory, GATE step 3) · `ARCHITECTURE.md` (layers/model/endpoints) · `ROADMAP.md` (milestones) · `naming.yaml` (entities) · `CODING_STANDARDS.md` (new rules) · ADR (decisions) · `README.md` (quickstart) · `SHIPPED.md` + `devlog.md` (always). Nothing touched — an explicit note in the devlog.

## Startup checklist

- [ ] Read this file
- [ ] Read the latest devlog.md entry
- [ ] Know which release we are on (ROADMAP)
- [ ] Code changes → GATE passed
- [ ] New worktree → `./scripts/install-git-hooks.sh`, `bd stats` matches the queue

## Maintenance

- **Owner:** <owner>
- **Review:** after every release + when the methodology changes

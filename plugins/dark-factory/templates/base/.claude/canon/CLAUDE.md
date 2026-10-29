# Operating canon

> The factory's canon for this project, imported by `CLAUDE.md` with `@.claude/canon/CLAUDE.md`.
> Do not edit it in the project: it is replaced whole from the dark-factory template on upgrade
> (`copier update` brings the new version; `scripts/harness-diff.sh` shows the difference). Project-specific text lives in `CLAUDE.md`.

## ⚡ Operating contract (always read first)

Seven inviolable rules. Details are further down the file; here is what must not be broken.

1. **Code goes out only through the standard procedure** (`ship` skill): push of the work branch → PR → green CI → your own review → merge by `scripts/merge-feature.sh <branch> [title]`. A bare `gh pr merge` is denied by the guard. Do not read or print tokens/credentials by hand.
2. **The work queue is beads** (`bd ready` → claim → close). The board (Linear, `board` skill) holds human umbrella cards; the machine queue is not mirrored to the board. **One task card = one branch/PR.**
3. **Code only through a work branch** `<type>/<ID>-<slug>` with a tracker (`feat/DMP-123-voice-input`; GitHub Issues: `feat/123-voice-input` and `Fixes #123` in the PR, with `TRACKER_ID_RE='[0-9]+'` in `scripts/merge-feature.sh`), `<type>/<slug>` without one; `<type>` is `feat|fix|ui|refactor|chore|docs`. Cut it from a fresh main branch; committing code directly to the main branch is FORBIDDEN. The PR title carries the ID, so the tracker links the PR and moves the card. Documentation/process (`*.md`, `openspec/`) may be committed on the main branch, but the agent does not push to it (the guard denies it): a `docs/*` branch through `merge-feature.sh`, or the human pushes. Accompanying changes (SHIPPED, an ADR) travel in the feature branch in the same PR as the code — not as a separate commit to the main branch after the merge (especially important if main = auto-deploy: an extra commit means an extra redeploy). The execution queue (bd) is a local store outside git: nothing about it is committed.
4. **The dev stand (it runs main; features are accepted there) runs detached** (`setsid nohup … & disown`, not as a Bash-tool background job; the `dev-stand` skill); do not stop someone else's process without asking.
5. **Commits/pushes/release notes — in the project language (see "Project settings"), human-readable, no fluff, professional**; conventional; merge only on green CI (CI cannot run at all — `--skip-ci "<reason>"` on the owner's word, see the `ship` skill). These are fences, not only instructions — see "Fences" below.
6. **A finding/idea along the way is a proposal, not an authorization.** Scope is set by the request/spec; research, review and diagnostics do not by themselves authorize changes; a rare or unagreed scenario is a human decision, even if the fix looks local. Review findings are handled per [docs/review-contract.md](docs/review-contract.md).
7. **Understanding a feature = an answer to how the user interacts with it on EVERY surface — before development starts.** Project surfaces: see "Project settings"; for a new entity — where to view it and which of create/view/edit/delete ships. This is the first step of handling a request, before the spec, the bd task and the code. Questions go to the requester; answers with confirmation go into the proposal. Not clarified — the feature is not understood and is not taken into work ([openspec/README.md](openspec/README.md) §0; a feature built for only one surface — e.g. chat only — ends up being removed entirely).

## ⚙️ Environment

The source of truth for "where am I" is the per-machine marker `.claude/env` (gitignored); the SessionStart hook prints a capability block ([.claude/hooks/env-context.sh](.claude/hooks/env-context.sh)). On the server (`vps`: unattended `claude remote-control` sessions) the block states what the session may do without the owner.

**Claude subscription quota** is shared per account (5h and 7d windows); a hook-based watchdog of the dark-factory plugin (its `docs/quota-guard.md`): from 80% no new work (subagents, claim), from 85% wrap up, at 90% only save work. The watchdog message names the time when work resumes: when autonomous — save, schedule a continuation for that time and end the turn; otherwise tell the human the time. The quota line printed at session start and with every message is the current state; bypass is for humans only: `QUOTA_GUARD=off claude`.

**Fences** — what is held by hooks and scripts, not by this text. The hooks come from the **dark-factory plugin** (enabled in `.claude/settings.json`; a dependency of this template, installed first). The level is chosen at deployment in `.claude/fences.env` (`FENCE_LEVEL`, default `standard`); that file also opts the project in to the plugin's guards:

| Level | What is enforced |
|---|---|
| `solo` | The guard (the plugin's `guard.py`, PreToolUse) denies force push and `+refspec`, a push to the main branch (also `git push` while on it), `--no-verify`/`commit -n`/`core.hooksPath` tricks, pushing release tags `v*` outside `scripts/release.sh`, deleting or `reset --hard` of the main branch. `--skip-ci` allowed |
| `standard` | `solo` + `gh pr merge` (and the merge API) only through `merge-feature.sh`, no `gh pr review --approve` by the agent; the fence files (`.claude/settings*.json`, `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`) are edited only with the human's yes in the permission dialog (denied to subagents and unattended sessions); sandbox without unsandboxed escapes |
| `team` | `standard` + a GitHub approval (`reviewDecision` APPROVED) before the merge; `--skip-ci` refused. At `solo` and `standard` the agent merges itself after green CI and its own review; the human gate is the release |

Every denial says what to do instead. The guard is a seatbelt: it reads tool calls and stops mistakes and common shortcuts, but it is not a sandbox, and the real gate is branch protection on the code host. Bypass is for a human only: restart the session with `GUARD=off claude` (the quota watchdog: `QUOTA_GUARD=off`). A change to a fence is proposed to the owner, who makes it.

**Git worktree — known traps:**
1. Tools that create worktrees write an absolute `core.hooksPath` pointing to the main checkout into `config.worktree` — hooks run from another branch. The plugin's SessionStart hook `ensure-git-hooks.sh` reinstalls them itself and warns loudly if pre-push is not active; outside a Claude session run `./scripts/install-git-hooks.sh` right after creating the worktree.
2. The execution queue is one local bd store per project, in the main checkout's `.beads/` (gitignored; [.beads/README.md](.beads/README.md)). Every worktree uses that store: `bd` finds it through git, and the SessionStart hook `env-context.sh` exports `BEADS_DIR` for the session. Do not `bd init` inside a worktree.
3. Gitignored files are not in a new worktree. Files a session needs there (`.env`, local config) go into `.worktreeinclude` (gitignore syntax) — Claude Code copies them into the worktrees it creates; large or shared state (the preview database) is referred to by the absolute path of the main checkout, never copied.
4. Updating the harness to a new canon version: `copier update` ([.harness/README.md](.harness/README.md), "Updating"); `scripts/harness-diff.sh` reports who moved away from the common base (`.harness/base-sha`). The canon moves ahead, and projects re-fix locally what is already fixed — reconcile during a review pass, not during a fire. What else can be installed on top of base and when it is time — the module catalog [.harness/modules.md](.harness/modules.md); propose it to the owner, do not install it yourself.
5. `.claude/settings.local.json` is gitignored — a session opened in a worktree does not see the main checkout's local "always allow" answers, and permission prompts come back. The fix is the specific commands the project needs in the project's `.claude/settings.json` → `permissions.allow` (shared, committed; a fence file — the owner adds them), never a blanket `"Bash"` allow; the SessionStart hook prints a quiet hint in a worktree session. Agent worktrees live inside the session directory (`.claude/worktrees/`, in `.gitignore`): outside it, Workflow does not run nested scripts.
6. git ignores a symlink only by a pattern without a trailing slash: `node_modules/` matches a directory, not the `node_modules` link a worktree gets to the main checkout's dependencies — it then shows as untracked and `git add -A` commits it. Write `node_modules` (no slash) in `.gitignore`.

**File names from other systems:** an archive made on a Mac (design, customer materials) keeps names in decomposed Unicode (NFD). On Linux a path typed in ordinary letters does not find such a file — an agent then decides the assets do not exist — while the design file refers to them in composed form (NFC). On receipt, rename every name to NFC, deepest first (`git mv` once committed), and check: `find <dir> | python3 -c 'import sys,unicodedata as u; [print(l, end="") for l in sys.stdin if u.normalize("NFC", l) != l]'` prints nothing.

## Onboarding (reading order)

1. `README.md` — what it is and how to run it
2. **`CLAUDE.md`** — project settings, plus the contract, GATE, principles and constraints it imports from `.claude/canon/CLAUDE.md`
3. `ARCHITECTURE.md` — the big picture
4. `CODING_STANDARDS.md` — code rules; per-layer in `docs/standards/`
5. `naming.yaml` — project map and glossary
6. `openspec/README.md` — the spec format
7. The session header (SessionStart): the branch's PR, the tasks in progress, the latest merges — the continuation point

## SESSION LOOP: state lives in git, the PR, the queue and memory (blocking step before and after work)

Anything that is not in git goes to memory or to bd: nothing else survives `/clear` or the end of a session.

| What | Where |
|---|---|
| What a change does, the decisions, the open questions | the PR description: `## Done` / `## Decisions` / `## Open questions` (it becomes the merge commit message, so `git log --merges` is the history) |
| A decision that shapes the architecture | an ADR, in the branch |
| A follow-up, a gap found along the way, where a task stopped | bd: a new task, or `bd update <id> --append-notes` |
| A rule or preference the human stated, an environment fact | memory |

**Opening**: the SessionStart hook `session-context.sh` injects the branch, the branch's PR (title and description), the tasks in progress with their notes and the latest merges of the main branch (on the main branch also the active OpenSpec changes). The PR's "Open questions" and the task notes are the continuation points; a conflict with the user's request must be raised before work starts. Starting work on a branch: **open a draft PR right away** (`gh pr create --draft`), so the record has a place from the first commit.

**Closing**: the session is not finished until the state is saved — the `save` skill (also before `/clear` and at the quota ceiling): commit, the PR description rewritten as the current state, notes on the claimed task, memory for what is not in git. A large change shipped → `SHIPPED.md` in the branch, in the same PR as the code; after the merge to main nothing is pushed as a separate commit — if you forgot before the merge, carry it with the next branch.

**Enforce**: `merge-feature.sh` refuses to merge a PR whose description lacks the three sections.

## GATE: before any code (blocking step)

**DO NOT WRITE A SINGLE LINE OF CODE** until these steps are done.

### Start — size the work

A new piece of work (a request: "add", "fix", "make", a new ask) starts with the **`dark-factory:size-task` skill**: it reads the request and the code, gives a one-line verdict for the owner's ok (`trivial` — branch + PR; `small` — `openspec/changes/<slug>/` with proposal and tasks; `large` — plus design) and proposes the type, slug, tracker ID and end-to-end phases. Only after the ok does anything below start. Surface questions to the requester first (rule 7).

### Step 0 — Process skills

The route comes from the size the owner approved: a `trivial` change has no plan; a `small` or `large` one is planned by `dark-factory:plan`.

| Task type | Skills |
|-----------|---------------------|
| New feature | `brainstorming` (before the proposal) → the approved size's route → `test-driven-development` |
| Bug fix | `systematic-debugging` → `test-driven-development` |
| Refactoring | the approved size's route → `test-driven-development` |
| Approved spec → execution | `openspec-to-beads` (phases → bd graph) |
| Approved phase → code in this session | `dark-factory:plan` → `dark-factory:build-tdd` per slice → `dark-factory:integrate` → `reviewer` role → `dark-factory:wrap` |
| Any commit | `verification-before-completion` |

The skill names are those of the [Superpowers](https://github.com/obra/superpowers) plugin (recommended); without it, follow the same steps by hand. Superpowers skills are working tools: whatever they write (design, plan) goes into `openspec/changes/<slug>/`, never into a separate specs or plans folder. TDD is mandatory (RED → GREEN → REFACTOR); brainstorming comes before the proposal of a new feature; the plan of a phase is `dark-factory:plan` (Superpowers `writing-plans` is not a second plan). The `dark-factory:` stage skills are the same rules the feature pipeline follows; launch the pipeline (`/dark-factory:feature`) only for a run you leave alone; it builds in `session` mode by default, `--mode pipeline` only for a wide phase of independent slices.

### Step 1 — Task and branch

1. `bd ready` → claim a suitable task; if none, create one before coding (`bd create … --acceptance="…"`). Do not create tasks by hand from an approved spec — use `openspec-to-beads`.
2. Branch `<type>/<ID>-<slug>` or `<type>/<slug>` (rule 3) from a fresh main branch. One task card = one branch; a spec's phases are separate cards (or a `-p<K>` suffix without a tracker).
3. The execution tier (lite or full) is the size the owner approved; `/dark-factory:feature` passes it to the run, and an agent sizes the work only when none is given.

> **Red flag (forbidden workaround):** "I'll create a TodoWrite per phase" instead of bd. Writing code without an `in_progress` task in bd — go back to Step 1.

### Step 2 — Standards

Read `CODING_STANDARDS.md` in full + the per-layer file for the task's layer + `naming.yaml`. Skipping = automatic review failure.

### Step 3 — User guide (projects with a user UI; features that change a screen or user behaviour)

The project flag is in "Project settings". With "no" the step does not apply and there is no `docs/user-guide/` folder in the project. With "yes": a feature with a screen is not closed until `docs/user-guide/` is updated (the bar — `DOCUMENTATION_STANDARDS.md` §6): a page for the user's task, a screenshot via the script `python -m tests.e2e.make_screenshots` (do not capture by hand), links via `scripts/check_doc_links.py`. This is a GATE step, not "later": in a project without this step the user guide never appears at all (a finished SPA with no guide is the typical outcome).

## Engineering Principles

> Without explicit principles the model builds "spaceships". Mandatory for any work.

- **KISS** · **YAGNI** · **MVP first** · **Fail Fast** (errors early and explicit, no silent excepts) · **Iterative** (1 feature at a time, each testable and committable)
- **Spec-driven in proportion** — code follows an explicit plan sized by `dark-factory:size-task`: none for a trivial change, a short proposal for a small one, plus a design for a large one
- **Explicit hand-off to the machine** — the machine does not guess scope; the tier comes from the approved size
- **Slice end to end, not by layers.** Each part of a feature, after its commit, works from the entry point (webhook, route, dispatcher) to the result at least for its own scenario and is covered by an entry-level test. Slicing "data → sending → wizard → dispatcher" leaves the feature unwired between parts, and a dead path passes all tests (caught by review only by chance).
- **Shared layer first, the second feature on top.** Before coding, compare the plan's files with unmerged branches in progress; if the code overlaps, merge that branch first or merge it into this one. Two parallel features that each introduce the same schema and the same method lead to conflicts and manual cleanup of duplicates.
- **Reachability.** A new path must actually reach real users: check that nothing upstream intercepts it — a kill switch, a flag or an early dispatcher branch — and that the entry test goes through the same path as the user. The entry point must be one that is actually possible in the external API. An unreachable path is a review blocker (green tests on a path users never reach; a spec requiring handling of an update the external platform never sends).
- The project's own principles are in "Project principles" of `CLAUDE.md`.

## Constraints — what the AI must NOT do

- ⛔ Do not push to the main branch or merge outside `merge-feature.sh` (fenced by the guard; do not look for ways around a denial — ask the human)
- ⛔ Do not read/print secrets and tokens
- ⛔ Do not run tests (including e2e and nightly ones) against real LLMs and paid external APIs with a real key — only a fake server or a recorded response; a test that needs a live key is skipped until a fake exists, and the secret is removed from the workflow (an expired key otherwise keeps the nightly e2e red). Exception — the LLM quality eval gate: a manual run before shipping, key from CI secrets (CODING_STANDARDS, "Logging and LLM")
- ⛔ The project's own prohibitions are in "Project constraints" of `CLAUDE.md`.

## Finishing a feature: update the project documents (blocking step)

Update everything the feature touched: `docs/user-guide/` (project with a user guide, feature with UI — mandatory, GATE step 3) · `ARCHITECTURE.md` (layers/model/endpoints) · `naming.yaml` (entities) · `CODING_STANDARDS.md` (new rules) · ADR (decisions) · `README.md` (quickstart) · `SHIPPED.md` (a release). Nothing touched — say so in the PR description's `## Done`.

## Startup checklist

- [ ] Read `CLAUDE.md` (this contract is imported into it)
- [ ] Read the session header (the PR, the tasks in progress); on a new branch — a draft PR
- [ ] New work → `dark-factory:size-task`; code changes → GATE passed
- [ ] New worktree → `./scripts/install-git-hooks.sh`

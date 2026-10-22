---
name: deploy-project
description: Deploy a new factory project from the templates/base template — "deploy project XXX". Asks first which level to start at (1 discipline / 2 unattended / 3 with a client / 4 team), which sets the fence level and the modules it names. Dry-run, configuration questions, filling placeholders, a log row in the factory registry (registry.md). Use on "deploy a project", "new factory project", "set up the harness".
disable-model-invocation: true
---

# Skill `deploy-project` — deploying a project from the template

> Factory operations (control plane, not copied into the template). Principle: the mechanics are the script [scripts/deploy-base.sh](../../../scripts/deploy-base.sh), the skill is questions, filling and the log.
> The registry is `registry.md` in your factory instance, created from [registry.example.md](../../../registry.example.md).
> **Dependency:** base relies on the dark-factory plugin ([plugins/dark-factory](../../../plugins/dark-factory/README.md)) for its always-on hooks — the fence guard, the quota guard, git-hook repair. It is installed first; the template's `.claude/settings.json` enables it for the project.

## Iron rules

1. **Dry-run first, then write.** Always: `scripts/deploy-base.sh <target> --dry-run` + the list of questions → show the human → after "yes" — the real run.
2. **Existing files are never overwritten** (built into the script) — the "harness on top of existing code" scenario is safe by construction; show the skips to the human. A project's own `.gitignore` is kept as well: the script prints the base lines it lacks (`.claude/env`, `.claude/worktrees/`, local bd store files …) — merge them into it on "yes".
3. **Nothing external without a "yes"**: `git init` — fine; `gh repo create` / the first push / creating a project on your tracker/board — only on explicit confirmation.
4. **The log is mandatory**: after deployment — a row in the factory's `registry.md` (project, repo, date + template SHA from the script output, composition, "Reconciliation"). Without the row the deployment is not finished.

## Input contract (questions to the human — one at a time, with defaults)

**Question 0, asked first: "Which level do we start at — 1 discipline / 2 unattended / 3 with a client / 4 team?"**
(the ladder: [docs/levels.md](../../../docs/levels.md)). Default: 1. The answer sets the defaults of question 11 and
`QUOTA_FAIL_CLOSED`, and which modules step 6 of the Order names; the deployment itself is base at every level.

| Start at | Fence level written | `QUOTA_FAIL_CLOSED` | Modules named in step 6 | Named as the next step |
|---|---|---|---|---|
| **1. Discipline** | `standard` | `0` | none now; the catalog's signals later | — |
| **2. Unattended** | `standard` | `1` | `feature-pipeline` | the `provision-server` skill for the server |
| **3. With a client** | `standard` | `1` | `feature-pipeline`, `feedback-desk`, then `prod-monitor` (on top of feedback-desk), `observability`; `release-tag` if the hosting builds production from a branch | `provision-server` first (the On-call session lives on the server) |
| **4. Team** | `team` | `1` | `feature-pipeline`; the level-3 modules only if there is a client | `provision-server`; branch protection with 1 approval (question 11) |

Level 0 (the solo kit) is not this skill: it is `/dark-factory:init` of the plugin, run in the project. A project
already on base that wants to move up runs `/dark-factory:level` there instead of a new deployment.

Questions 8–11 are the base manifest's own deployment questions ([templates/base/MANIFEST.md](../../../templates/base/MANIFEST.md) "Questions at deployment"), asked here in the same order; inside that manifest they are numbered 1–4, so its "question 4" is question 11 here.

1. Project name and path; **where the code lives**: an `app/` folder in the same repo / an `app/` submodule pointing to a separate repo / code at the root. The script does not touch code in any case; for a submodule — `git submodule add <url> app` on "yes". Placeholder paths depend on the answer (pre-push, ship: one or two commit streams).
2. Overview: what the product is, the stack (for CLAUDE.md)
3. Project language (default: English)
4. Main branch (default: `main`) and merge strategy (default: `--merge`; a squash merge breaks ancestry and branch cleanup)
5. Your tracker/board, if any: team/project/client/external tracker (for the `board` configuration)
6. External resources — **each with a separate confirmation**: create a GitHub repo (`gh repo create --private`)? create a project on the board and a row in the board registry? apply branch protection on the main branch and a ruleset on release tags (question 11)? a separate GitHub identity for the agent (question 11, recommended)?
7. Code paths and the fast test command (for pre-push: TRIGGER/CODE_PATTERNS, TEST_CMD) and CI steps
8. **Execution sandbox** (manifest question 1) — an explicit fork ([docs/methodology.md](../../../docs/methodology.md) §3, Sandbox): do we enable the built-in Claude Code sandbox? **Default: yes.** On "yes" — fill in the network allowlist in the `sandbox` block of settings.json (placeholders for stack and project domains; an unknown domain will later trigger a prompt — extend as needed). On "no" — remove the `sandbox` block and the `Read(…)` rules of `permissions.deny` from settings.json (the fence rules stay), record the refusal in the registry "deviations" with the reason.
9. **Pyramid profile** (manifest question 2): unit-first (default) or contract-first — written by the first `scripts/pyramid.py --write-baseline --profile <…>` and into the project's CODING_STANDARDS.
10. **User guide** (manifest question 3): is there a user UI for people? Default "yes" for an SPA/screens; "no" → what the manifest says to remove.
11. **Fence level** (manifest question 4): `solo` / `standard` / `team`, default from question 0 (`team` at level 4, `standard` otherwise) — what hooks and scripts enforce (the target's CLAUDE.md "Fences"). Choosing below the level's default is allowed and recorded in the registry "deviations"; `/dark-factory:level` in the project will report it as a gap:
    - `solo` — the guard denies only destructive things: force push, a push to the main branch, `--no-verify`/hooks bypass, release-tag pushes outside `scripts/release.sh`, deleting or hard-resetting the main branch; `merge-feature.sh` still needs `--accepted-by "<name>"`, `--skip-ci` allowed.
    - `standard` — `solo` + `gh pr merge` only through `merge-feature.sh`, no approvals by the agent, the fence files edited by the human only, a sandbox without unsandboxed escapes.
    - `team` — `standard` + a GitHub approval before every merge; `--skip-ci` refused.

    What deployment does with the answer:
    - Any level: `deploy-base.sh <target> --fence-level <answer> --fail-closed <0|1>` writes `FENCE_LEVEL` and `QUOTA_FAIL_CLOSED` into the `.claude/fences.env` it copies (an existing file is left alone: then the human runs `/dark-factory:level` in the project). The plugin's guard denies lowering `FENCE_LEVEL` by an edit, so do not hand-edit the line afterwards.
    - `solo`: in `.claude/settings.json` remove the `Edit(…)` fence-file rules and `Bash(gh pr merge:*)` from `permissions.deny` (the `Read(…)` and `git push --force`/`-f` rules stay) and set `sandbox.allowUnsandboxedCommands` to `true`.
    - **Every level: GitHub enforces, the guard backs it up.** The real gate on the main branch and on release tags is
      GitHub — branch protection (or a branch ruleset) and a tag ruleset — because GitHub checks every push whatever
      produced it. The plugin's guard hook is defence in depth behind it: it reads command text before it runs, so it
      catches an agent's mistakes early, but it misses aliases, variables, scripts written and then run, subprocesses,
      and a session restarted with `GUARD=off`. Applying the rules is an external change (question 6, iron rule 3):
      show the owner the commands below, apply them after the "yes", then verify. With "no", or on a private repo
      without a paid GitHub plan (protection and rulesets need one there), record "no branch protection" in the registry
      "deviations".

      Main branch — a pull request is required (0 approvals: a solo owner satisfies it, since `merge-feature.sh` always
      merges through a PR; `team`: 1), no force pushes, no deletion, no admin bypass (while the agent works under the
      owner's login, an admin bypass is the agent's bypass too):

      ```bash
      gh api -X PUT repos/<owner>/<repo>/branches/<main>/protection --input - <<'JSON'
      {"required_status_checks": null, "enforce_admins": true,
       "required_pull_request_reviews": {"required_approving_review_count": 0},
       "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
      JSON
      ```

      (`team`: `"required_approving_review_count": 1`.) Release tags — a tag ruleset on `v*`: no update, no deletion, no
      force; creation only by repository admins (the `release-tag` module's `scripts/release.sh` cuts them):

      ```bash
      gh api -X POST repos/<owner>/<repo>/rulesets --input - <<'JSON'
      {"name": "release tags", "target": "tag", "enforcement": "active",
       "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
       "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
       "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]}
      JSON
      ```

      (`actor_id` 5 is the built-in admin role.) **Verify — the deployment is not finished until both read back:**

      ```bash
      gh api repos/<owner>/<repo>/branches/<main>/protection \
        --jq '{admins: .enforce_admins.enabled, force: .allow_force_pushes.enabled, deletions: .allow_deletions.enabled, approvals: .required_pull_request_reviews.required_approving_review_count}'
      # expect {"admins":true,"force":false,"deletions":false,"approvals":0}  (team: 1)
      gh api repos/<owner>/<repo>/rulesets --jq '.[] | select(.target == "tag") | {name, enforcement}'
      # expect {"name":"release tags","enforcement":"active"}
      ```

      A project that prefers rulesets for the branch too creates a `"target": "branch"` ruleset on `~DEFAULT_BRANCH`
      with the `pull_request`, `non_fast_forward` and `deletion` rules and no bypass actors; verify it with
      `gh api repos/<owner>/<repo>/rules/branches/<main>`, which lists the rules in effect from either source. Record
      in the registry row what was applied and verified.
    - **Recommended, not required: a separate GitHub identity for the agent.** While the agent uses the owner's `gh`
      login, its pushes, PRs and merges are the owner's, and nothing on GitHub tells them apart. On the owner's "yes":
      1. Create the identity: a machine user (a second GitHub account for automation, e.g. `<owner>-bot`) or a GitHub
         App installed on this repository only.
      2. Give it **Write**, never Admin (`gh api -X PUT repos/<owner>/<repo>/collaborators/<bot> -f permission=push`,
         then accept the invitation as the bot); a GitHub App gets the Contents, Pull requests and Issues permissions
         only.
      3. Authenticate the agent as it: on the server, `gh auth login` under the agent's Unix user with a fine-grained
         token of the bot scoped to this repository (Contents and Pull requests: read and write), or the App's
         installation token; the owner's own login stays off that machine.
      4. Keep the rules above with no bypass for the bot. The agent then cannot bypass protection or create release
         tags, and at `team` level the owner's approval is a second person's approval, not the author approving itself.
      5. Record the identity in the registry row; `git log` and the PR list now show which changes the agent made.
    - `QUOTA_FAIL_CLOSED`: `1` from level 2 up (unattended sessions: a server, the feedback desk, scheduled runs) — with no quota data the watchdog then means "no new work" instead of letting work through; `0` at level 1 unless the owner asks otherwise.
12. What from the contents the project does NOT need (for example, the e2e layer before the project has a frontend) — record exclusions in the registry "deviations"

Do not fear "I don't know" answers: the placeholder stays, gets into the remaining-placeholders report and into the registry "deviations".

## "Conversion" mode: moving an existing project onto the scheme

When a project already lives with its own harness (a project that already has its own harness, or a partial deployment) and is being moved over "in full", the order is different:

1. **A delta against the manifest**, not a full run: compare the base contents with the project's registry row — what is already in place, what is missing, what exists in a different form.
2. **The human resolves conflicting nodes, one at a time**: the project's own merge strategy vs the canonical `--merge`, its own pre-commit/CI setup vs `.githooks`, branch naming (the canon requires the full bd id, `<prefix>-<hash>`, at the end — merge-feature.sh closes the task by it). Do not assume the project's own variant is "more mature" by default — ask which one wins.
3. **Update the project's living docs, leave archived ones alone**: README/CONTRIBUTING/tests-README referring to removed practices get rewritten; historical plans and ROADMAP are an archive, leave them.
4. The project's CLAUDE.md is **extended** with base blocks (Operating contract, SESSION LOOP, finishing a feature), not replaced by the skeleton — its existing rules are worth keeping.
5. Smoke — the same as in MANIFEST (including a pre-push dry-run and checking TEST_CMD on the machines of **all** operators).
6. Registry: status "partial" → "full", rewrite the deviations from scratch (old "deliberate" ones may have turned into holes).

## Order

0. **The plugin first.** `claude plugin list` shows `dark-factory@dark-factory` enabled. If not, after a "yes":
   `claude plugin marketplace add ruslantrachuk/dark-factory#v<version>` (pinned to a release tag; or this canon
   checkout's path) and `claude plugin install dark-factory@dark-factory`. The target's `.claude/settings.json` pins
   the same marketplace in `extraKnownMarketplaces` (`"ref": "v<version>"`, the release this canon is at); a fork
   replaces `repo` with its own. Moving to a newer release is a deliberate edit of that `ref`, reviewed like any change
   to the fences. A project being converted that still
   carries `scripts/quota.py`, `scripts/guard.py`, `.claude/hooks/ensure-git-hooks.sh` and their hook groups in
   `.claude/settings.json` drops them (on "yes"), or the hooks run twice.
1. Question 0, question 1 → `deploy-base.sh <target> --dry-run --fence-level <level> --fail-closed <0|1>` → show the plan + remaining questions → "yes".
2. Real script run (the same flags) → fill placeholders from the answers (grep for `<` — in the script output).
3. `./scripts/install-git-hooks.sh` in the target; `bd init --non-interactive --skip-agents --skip-hooks --role maintainer --prefix <pfx> && bd import` (see the target's `.beads/README.md`). ⚠️ **`bd init` does `git add -A` + commit** ("bd init: initialize beads issue tracking") — it sweeps up ALL uncommitted changes in the working tree, not only `.beads/*` (the `--skip-*` flags do not disable this). Run it on a **clean tree** (or as the first step, before harness edits); if it swept things up — `git reset --soft <before bd-init>` and rebuild a meaningful commit. Then `./scripts/fetch-openspec-docs.sh` in the target — OpenSpec docs are not stored in the template, they are pulled from an upstream tag and **committed** as a snapshot (no network / not needed — skip, record in "deviations"); `git init` + first commit if the repo is new.
4. **Smoke per MANIFEST.md**: the plugin is enabled, contract echo and the quota line in a new session, the guard denies `git push --force`, `bd ready`, a code push without devlog is blocked.
5. A row in the factory's `registry.md` (with the starting level from question 0) + show the human what remains unfilled.
6. **Modules — propose, do not install.** Name the modules of the starting level (question 0 table), then walk the catalog [templates/base/.harness/modules.md](../../../templates/base/.harness/modules.md) (it ships into the project with base) and add the modules whose "time to install" signal is already present, each with its table row. At level 2 and up, also name `provision-server` as the next step. In the project, `/dark-factory:level` shows the same ladder from its evidence. Installing one is separate work after the owner's "yes", done by that module's `MANIFEST.md` §Setup (or the module's own skill), with its devlog entry and the registry "Contents" column updated — not part of this deployment.

## What the skill does NOT do

- Does not create external resources (GitHub repo, a project on your board) without an explicit "yes".
- **Deploys base only, at every starting level.** It installs no module and provisions no server: it names the modules of the starting level and those whose signal is present (Order, step 6); each module is installed afterwards by its own manifest. Modules: feature-pipeline ([templates/feature-pipeline/MANIFEST.md](../../../templates/feature-pipeline/MANIFEST.md), the Workflow feature pipeline the development session launches — propose it once features are planned as OpenSpec phases or specs with bd tasks), release-tag ([templates/release-tag/MANIFEST.md](../../../templates/release-tag/MANIFEST.md), prod only from a tag — propose it if the hosting builds prod from a branch), feedback-desk ([templates/feedback-desk/MANIFEST.md](../../../templates/feedback-desk/MANIFEST.md), the client's feedback group in Telegram — set up by its own `feedback-desk` skill), observability (metrics and alerts — once there is a prod), code-audit (audit projects of someone else's code), prod-monitor ([templates/prod-monitor/MANIFEST.md](../../../templates/prod-monitor/MANIFEST.md), a prod monitor on top of feedback-desk) — the practice map is in [docs/practices/](../../../docs/practices/README.md); their deployment follows their manifests, not this skill.
- Does not edit the templates/ canon — an improvement found along the way is carried over into the canon separately, during the review pass.

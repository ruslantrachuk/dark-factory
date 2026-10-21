---
name: deploy-project
description: Deploy a new factory project from the templates/base template — "deploy project XXX". Dry-run, configuration questions, filling placeholders, a log row in the factory registry (registry.md). Use on "deploy a project", "new factory project", "set up the harness".
---

# Skill `deploy-project` — deploying a project from the template

> Factory operations (control plane, not copied into the template). Principle: the mechanics are the script [scripts/deploy-base.sh](../../../scripts/deploy-base.sh), the skill is questions, filling and the log.
> The registry is `registry.md` in your factory instance, created from [registry.example.md](../../../registry.example.md).

## Iron rules

1. **Dry-run first, then write.** Always: `scripts/deploy-base.sh <target> --dry-run` + the list of questions → show the human → after "yes" — the real run.
2. **Existing files are never overwritten** (built into the script) — the "harness on top of existing code" scenario is safe by construction; show the skips to the human.
3. **Nothing external without a "yes"**: `git init` — fine; `gh repo create` / the first push / creating a project on your tracker/board — only on explicit confirmation.
4. **The log is mandatory**: after deployment — a row in the factory's `registry.md` (project, repo, date + template SHA from the script output, composition, "Reconciliation"). Without the row the deployment is not finished.

## Input contract (questions to the human — one at a time, with defaults)

1. Project name and path; **where the code lives**: an `app/` folder in the same repo / an `app/` submodule pointing to a separate repo / code at the root. The script does not touch code in any case; for a submodule — `git submodule add <url> app` on "yes". Placeholder paths depend on the answer (pre-push, ship: one or two commit streams).
2. Overview: what the product is, the stack (for CLAUDE.md)
3. Project language (default: English)
4. Main branch (default: `main`) and merge strategy (default: `--merge`; a squash merge breaks ancestry and branch cleanup)
5. Your tracker/board, if any: team/project/client/external tracker (for the `board` configuration)
6. External resources — **each with a separate confirmation**: create a GitHub repo (`gh repo create --private`)? create a project on the board and a row in the board registry?
7. Code paths and the fast test command (for pre-push: TRIGGER/CODE_PATTERNS, TEST_CMD) and CI steps
8. **Execution sandbox** — an explicit fork ([docs/decisions/mac-sandbox.md](../../../docs/decisions/mac-sandbox.md)): do we enable the built-in Claude Code sandbox? **Default: yes.** On "yes" — fill in the network allowlist in the `sandbox` block of settings.json (placeholders for stack and project domains; an unknown domain will later trigger a prompt — extend as needed). On "no" — remove the `sandbox` and `permissions.deny` blocks from settings.json, record the refusal in the registry "deviations" with the reason.
9. What from the contents the project does NOT need (for example, the workflow engine before the night loop) — record exclusions in the registry "deviations"

Do not fear "I don't know" answers: the placeholder stays, gets into the remaining-placeholders report and into the registry "deviations".

## "Conversion" mode: moving an existing project onto the scheme

When a project already lives with its own harness (a project that already has its own harness, or a partial deployment) and is being moved over "in full", the order is different:

1. **A delta against the manifest**, not a full run: compare the base contents with the project's registry row — what is already in place, what is missing, what exists in a different form.
2. **The human resolves conflicting nodes, one at a time**: the project's own merge strategy vs the canonical `--merge`, its own pre-commit/CI setup vs `.githooks`, branch naming (the canon requires a bd id at the end — merge-feature.sh closes the task by it). Do not assume the project's own variant is "more mature" by default — ask which one wins.
3. **Update the project's living docs, leave archived ones alone**: README/CONTRIBUTING/tests-README referring to removed practices get rewritten; historical plans and ROADMAP are an archive, leave them.
4. The project's CLAUDE.md is **extended** with base blocks (Operating contract, SESSION LOOP, finishing a feature), not replaced by the skeleton — its own charter is valuable.
5. Smoke — the same as in MANIFEST (including a pre-push dry-run and checking TEST_CMD on the machines of **all** operators).
6. Registry: status "partial" → "full", rewrite the deviations from scratch (old "deliberate" ones may have turned into holes).

## Order

1. Question 1 → `deploy-base.sh <target> --dry-run` → show the plan + remaining questions → "yes".
2. Real script run → fill placeholders from the answers (grep for `<` — in the script output).
3. `./scripts/install-git-hooks.sh` in the target; `bd init --non-interactive --skip-agents --skip-hooks --role maintainer --prefix <pfx> && bd import` (see the target's `.beads/README.md`). ⚠️ **`bd init` does `git add -A` + commit** ("bd init: initialize beads issue tracking") — it sweeps up ALL uncommitted changes in the working tree, not only `.beads/*` (the `--skip-*` flags do not disable this). Run it on a **clean tree** (or as the first step, before harness edits); if it swept things up — `git reset --soft <before bd-init>` and rebuild a meaningful commit. Then `./scripts/fetch-openspec-docs.sh` in the target — OpenSpec docs are not stored in the template, they are pulled from an upstream tag and **committed** as a snapshot (no network / not needed — skip, record in "deviations"); `git init` + first commit if the repo is new.
4. **Smoke per MANIFEST.md**: contract echo in a new session, `bd ready`, a code push without devlog is blocked.
5. A row in the factory's `registry.md` + show the human what remains unfilled.

## What the skill does NOT do

- Does not create external resources (GitHub repo, a project on your board) without an explicit "yes".
- Does not deploy modules other than base, but at the end of a deployment walks the catalog [templates/base/.harness/modules.md](../../../templates/base/.harness/modules.md) (it ships into the project with base) and names to the owner the modules whose "it is time" signal is already present. Modules: night-local ([templates/night-local/MANIFEST.md](../../../templates/night-local/MANIFEST.md), its own pilot order), release-tag ([templates/release-tag/MANIFEST.md](../../../templates/release-tag/MANIFEST.md), prod only from a tag — propose it if the hosting builds prod from a branch), feedback-desk ([templates/feedback-desk/MANIFEST.md](../../../templates/feedback-desk/MANIFEST.md), the client's feedback group in Telegram — set up by its own `feedback-desk` skill), observability (metrics and alerts — once there is a prod), code-audit (audit projects of someone else's code), prod-monitor ([templates/prod-monitor/MANIFEST.md](../../../templates/prod-monitor/MANIFEST.md), a prod monitor on top of feedback-desk) — the practice map is in [docs/practices/](../../../docs/practices/README.md); corp-perimeter is not assembled; their deployment follows their manifests, not this skill.
- Does not edit the templates/ canon — an improvement found along the way is carried over into the canon separately, during the review pass.

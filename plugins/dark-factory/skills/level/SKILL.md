---
name: level
description: Show the project's level on the dark-factory ladder (0 solo kit, 1 base template, 2 provisioned server, 3 client modules, 4 team) from evidence in the project, the signals for the next level and what would change; on the human's yes, write FENCE_LEVEL (up or down) or name the skill that takes a structural step. Invoked by the human as /dark-factory:level.
argument-hint: "[solo|standard|team]"
disable-model-invocation: true
---

# /dark-factory:level — where the project is on the ladder

The ladder is the dark-factory repository's `docs/levels.md`. The mechanics are one script,
`${CLAUDE_PLUGIN_ROOT}/scripts/level.py`; this skill is the report, the proposal and the "yes".

## Rules

1. **The human decides.** Propose one step; change nothing without an explicit "yes" to that step.
2. **Fence steps are written by the script, nothing else.** `.claude/fences.env` is fenced at every level: the guard
   denies deleting, moving or truncating it and lowering `FENCE_LEVEL` with Edit/Write. `level.py set … --apply`
   writes it, and only after the human's own `/dark-factory:level` prompt (the plugin records that prompt; the
   grant lasts 60 minutes and is used once). If the script refuses, show the human its terminal command; do not look
   for another way to write the file.
3. **Structural steps are named, never run here.** Deploying base, provisioning a server and installing a module are
   other skills with their own dry runs and "yes": tell the human which one to run and where.

## Steps

1. Report:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/level.py" status
   ```
   Show it to the human in short: the level, the evidence behind it, gaps at this level, and for the next level what
   it adds, how it is taken and the signals seen (none seen is fine: the human may know their situation better).
2. Propose **one** step, the first that applies:
   - a gap in the fence at this level (for example base deployed but `FENCE_LEVEL=solo`, or level 2 without
     `QUOTA_FAIL_CLOSED=1`) → the fence step;
   - an argument (`solo`, `standard`, `team`) → that fence change, up or down;
   - otherwise the next level's step.
3. **Fence step** (any direction). Dry run first, then after "yes" the same command with `--apply`:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/level.py" set <solo|standard|team> [--fail-closed 0|1]
   ```
   Moving down: say what is dropped (the dry run lists it). For `team`, also offer GitHub branch protection on the
   main branch (a pull request with 1 approval, no force pushes, no admin bypass) as a separate external change on
   a separate "yes":
   ```bash
   gh api -X PUT repos/<owner>/<repo>/branches/<main>/protection --input - <<'JSON'
   {"required_status_checks": null, "enforce_admins": true,
    "required_pull_request_reviews": {"required_approving_review_count": 1},
    "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
   JSON
   ```
   Afterwards: `.claude/fences.env` is a tracked file; it reaches the main branch like any change (a branch and
   `scripts/merge-feature.sh … --accepted-by "<name>"`, or the human pushes it).
4. **Structural step.** Tell the human what to run; do not run it:
   - **0 → 1**: in a checkout of the dark-factory repository, "deploy project <name> into <path>" (the
     `deploy-project` skill; its conversion mode for a project that already has code). It writes the fence level.
   - **1 → 2**: on the server, the `provision-server` skill of the dark-factory repository (`scripts/fleet.py
     provision`); then `/dark-factory:level` again to write `QUOTA_FAIL_CLOSED=1`.
   - **2 → 3**: one module at a time by its `templates/<module>/MANIFEST.md` (feedback-desk and prod-monitor have
     their own skills); the catalog with "when it is time" is `.harness/modules.md` in a base project.
   - **2 or 3 → 4**: the fence step to `team` (step 3) plus branch protection.
   Structural steps down (removing a module, leaving the server) follow the module's manifest or the
   `provision-server` skill; this command only moves the fence down.

## Not this command

`/dark-factory:init` sets up level 0. The agent may mention a next-level signal once (the plugin prints one line at
session start when it sees one), but it never moves a project up or down by itself.

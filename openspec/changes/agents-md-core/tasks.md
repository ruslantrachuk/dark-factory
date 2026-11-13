# Tasks: one canon for Claude Code and Codex

Spec: `proposal.md` in this directory.

- [x] **1. Block tool.** `plugins/dark-factory/scripts/canon_block.py` (stdlib): `render`, `check` (current /
  differs / broken / too large, `--json`), `apply` (`--insert` before the first `## ` heading, `--dry-run`). Tests
  (`tests/test_canon_block.py`, 24): render, replace keeps outside text byte-for-byte and CRLF, hand edits inside the
  block are replaced, missing / duplicate / unpaired / reversed markers stop without writing, size limit 32 KiB, the
  real canon leaves 4 KiB for the project. In CI and CONTRIBUTING. The canon file itself moves in task 2, with its
  readers, so every commit stays green.
- [x] **2. Base template layout.** `templates/base/AGENTS.md` = project intro + canon block (the former
  `.claude/canon/CLAUDE.md`, moved with `git mv`, its three self-references updated) + project sections; it is the
  canon source of `canon_block.py`. `CLAUDE.md` = `@AGENTS.md` + a Claude-only note. Skills `git mv` to
  `.agents/skills/`, `.claude/skills` → `../.agents/skills`. `scripts/agent/session-start.sh <agent>` runs bd prime,
  `env-context.sh` and `session-context.sh` (both moved from `.claude/hooks/`); the Claude Code install check and the
  allow-list hint run only for `AGENT=claude`. `.claude/settings.json` SessionStart = one call. Readers kept green:
  `deploy-base.sh` (replaces only the canon block of an existing `AGENTS.md`, names one without a block, copies the
  symlink as a symlink, hints a `CLAUDE.md` without `@AGENTS.md`), `harness-diff.sh` and `copier.yml` (`AGENTS.md`
  project-owned, `_preserve_symlinks`), the template docs (MANIFEST, READMEs, `save`). Tests: `test_repo.py`
  (layout, block inside/outside, symlink, one SessionStart, deploy replaces only the block, symlink deployed),
  `test_add_module.py`, `test_canon_block.py` (27). Linux: all suites and the 48 `merge-feature.sh` integration tests
  green; macOS: four suites fail as on `origin/main` (temp-path `/var` vs `/private/var`), not from this change.
- [x] **3. Agent-neutral text.** The canon block: quota by agent (Claude Code 5h/7d, Codex by plan), bypasses as
  `GUARD=off` / `QUOTA_GUARD=off` for either agent, both `remote-control`s, the plugin installed for Codex from the
  same marketplace, `.worktreeinclude` for both, the agent's own todo list (TodoWrite / Codex's plan) as the red flag,
  `/clear` and compaction, rules file = `AGENTS.md`; item 5 of the worktree notes (`settings.local.json`,
  `permissions.allow`, Workflow) is an "If you are Claude Code" note. Project skills: `AGENTS.md` as the rules file,
  project roles `.claude/agents/` or `.codex/agents/`, memory for both agents, the plugin directory for Codex. The
  base docs and script comments name `AGENTS.md`. Tests in `test_repo.py`: a canon line naming Claude names Codex or
  is a Claude-only note; project skills cite `AGENTS.md`. Meaning of every rule unchanged.
- [x] **4. Install paths.** Module skills (`feedback-desk`, `prod-monitor`) `git mv` to `.agents/skills/`.
  `add-module.sh` puts a module skill where the project keeps skills: `.agents/skills/` behind the link; a v23 project
  (a real `.claude/skills/`) gets it there with a hint to upgrade; a project with neither gets `.agents/skills/` and
  the link. `harness-diff.sh` reports `AGENTS.md#canon` (identical / differs / missing) through the canon's own
  `canon_block.py`. `merge-feature.sh` looks for the `ship` skill in either place. The module texts that told the agent
  to write a rule into `CLAUDE.md` (feedback-desk section D, prod-monitor step 5) now say `AGENTS.md` outside the canon
  block — §Environment is canon and would be replaced. Tests: three layouts, dry run, a module without a skill;
  harness-diff identical / differs / missing. `copier copy` (9.19.1, Linux) of this commit keeps `.claude/skills` a
  symlink with all ten skills; `AGENTS.md` and `CLAUDE.md` are not rendered, by design (copier updates projects,
  `deploy-base.sh` installs them; both files are excluded like `CLAUDE.md` was). Linux: `test_add_module.py`,
  `test_repo.py` green.
- [ ] **5. Upgrade migration.** `/dark-factory:upgrade` and `deploy-base.sh` on a v23 tree: sections into
  `AGENTS.md`, `CLAUDE.md` → `@AGENTS.md`, skills behind the symlink, hooks → `session-start.sh`; unchanged v23 files
  removed, changed ones kept and named. Tests on a v23 fixture project.
- [ ] **6. Repository checks.** `scripts/test_repo.py`: block present once, size, symlink, no file still importing
  `@.claude/canon/CLAUDE.md`; `scripts/build_lite.py --check`.
- [ ] **7. Canon eval (small first).** Two scratch projects from base — the v23 layout and this branch. Five
  scenarios whose answer depends on the canon (commit straight to main → refusal and a `<type>/<ID>-<slug>` branch;
  "merge the PR" → `scripts/merge-feature.sh`, never `gh pr merge`; "add feature X" → `size-task` and GATE before code;
  the branch name for tracker task DMP-123; what to do at 85% quota), one headless run each in three configurations:
  Claude Code on v23, Claude Code on v24, Codex on v24. Graded deterministically where possible (forbidden commands
  in the tool log, required markers in the answer). Pass: Claude v24 no worse than v23; Codex v24 no worse than Claude
  v24 per scenario. On a mismatch — widen to ~15 scenarios × 3 runs before changing the canon. Also: both agents list
  the project skills.
- [ ] **8. Docs and version.** `templates/README.md`, `skills/add/base.md`, `skills/upgrade`, getting-started; the
  plugin manifests `24.0.0`; CONTRIBUTING if a test command changes.

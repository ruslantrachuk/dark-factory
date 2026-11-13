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
- [ ] **3. Agent-neutral text.** The canon and the base project skills: "the agent"; tool names only in an
  "If you are Claude Code / If you are Codex" note. Fences and rules unchanged in meaning.
- [ ] **4. Install paths.** `add-module.sh` and the module manifests (`feedback-desk`, `prod-monitor` skills into
  `.agents/skills/`), `harness-diff.sh` (report the canon block via `canon_block.py check`), `merge-feature.sh`
  (skills path). Tests: symlink survives a copier render and a module install. (copier.yml and deploy-base.sh: done in
  task 2.)
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

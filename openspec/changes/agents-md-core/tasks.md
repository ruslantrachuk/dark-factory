# Tasks: one canon for Claude Code and Codex

Spec: `proposal.md` in this directory.

- [ ] **1. Canon source and block tool.** Move `templates/base/.claude/canon/CLAUDE.md` to
  `templates/base/.harness/canon.md`; a stdlib script in the plugin (`scripts/canon_block.py`) that renders the
  block with its markers, checks a file has exactly one block, and replaces it (`--check`, `--apply`). Tests: render,
  replace keeps outside text byte-for-byte, missing/duplicate marker stops, size limit 32 KiB.
- [ ] **2. Base template layout.** `AGENTS.md` (project sections + block), `CLAUDE.md` = `@AGENTS.md`,
  `.agents/skills/*` with `.claude/skills` → `../.agents/skills`, `scripts/agent/session-start.sh` replacing the two
  `.claude/hooks/*.sh` and the SessionStart commands in `.claude/settings.json`.
- [ ] **3. Agent-neutral text.** The canon and the base project skills: "the agent"; tool names only in an
  "If you are Claude Code / If you are Codex" note. Fences and rules unchanged in meaning.
- [ ] **4. Install paths.** `copier.yml` (`_preserve_symlinks`, exclusions), `deploy-base.sh`, `add-module.sh` and the
  module manifests (`feedback-desk`, `prod-monitor` skills into `.agents/skills/`), `harness-diff.sh` (block vs
  canon), `merge-feature.sh` (skills path). Tests: symlink survives copier render and module install.
- [ ] **5. Upgrade migration.** `/dark-factory:upgrade` and `deploy-base.sh` on a v23 tree: sections into
  `AGENTS.md`, `CLAUDE.md` → `@AGENTS.md`, skills behind the symlink, hooks → `session-start.sh`; unchanged v23 files
  removed, changed ones kept and named. Tests on a v23 fixture project.
- [ ] **6. Repository checks.** `scripts/test_repo.py`: block present once, size, symlink, no file still importing
  `@.claude/canon/CLAUDE.md`; `scripts/build_lite.py --check`.
- [ ] **7. Live check.** A project deployed from the new base: Claude Code and Codex each list the project skills and
  answer a question only the canon answers; a v23 project upgraded the same way.
- [ ] **8. Docs and version.** `templates/README.md`, `skills/add/base.md`, `skills/upgrade`, getting-started; the
  plugin manifests `24.0.0`; CONTRIBUTING if a test command changes.

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
- [x] **5. Upgrade migration.** `plugins/dark-factory/scripts/migrate_agents_md.py` (stdlib; dry run by default,
  `--apply`, `--json`; idempotent): `AGENTS.md` from `CLAUDE.md` with the canon block where the import line was (title
  and the v23 intro reworded), `CLAUDE.md` → `@AGENTS.md`, `.claude/canon/` removed, `.claude/skills/*` →
  `.agents/skills/` + the link, the two header scripts → `scripts/agent/` with their filled-in text, `session-start.sh`
  added, the project's own hooks kept and named. Fence file: `.claude/settings.json` SessionStart is printed, not
  written. Stops before any change on an `AGENTS.md` with text of its own; a pointer `@CLAUDE.md` is replaced; a skill
  or script already at its v24 place is kept and named, no link then. `/dark-factory:upgrade` step 3 runs it before
  Copier (dry run → owner → `--apply` → settings through the permission dialog → commit); step 5 checks the block.
  `deploy-base.sh` stops on a v23 tree and names the migration. Tests: `tests/test_migrate_agents_md.py` (14), a deploy
  test in `test_repo.py`. Live: a project deployed by v23's `deploy-base.sh` migrates with git seeing renames
  (`.claude/canon/CLAUDE.md` → `AGENTS.md`), the filled-in `env-context.sh` text survives, the new header runs, and the
  untouched project's `AGENTS.md` is byte-identical to the v24 template's.
- [x] **6. Repository checks.** `test_repo.py`: the retired paths (`@.claude/canon/CLAUDE.md`, the two
  `.claude/hooks/*-context.sh`) appear in no tracked file except where the migration is handled; the plugin's skills
  and workflows (and the lite edition) read `AGENTS.md`, not a bare `CLAUDE.md` (a Read of `CLAUDE.md` now returns the
  one line `@AGENTS.md` — the import expands only in the loaded context). Found and fixed on the way: `/dark-factory:add
  base` still told the agent to add the old import; `build-tdd`, `plan`, `vulns`, `wrap`, `size-task`, `add` and the
  three workflows named `CLAUDE.md` as the rules file (solo-kit projects keep `CLAUDE.md` as the fallback);
  `docs/functions.md`, `docs/practices/README.md`. `scripts/build_lite.py` rebuilt the lite skills. Block once,
  size, symlink: done in tasks 1–3. Workflow dry runs: the three success runs pass; the budget and agent-limit runs
  fail the same way on `origin/main` (not this change).
- [x] **7. Canon eval (small first).** `eval/` in this change: `scenarios.json` (five canon-dependent requests),
  `setup.sh` (a project from a plugin's `deploy-base.sh`, the same placeholders for v23 and v24), `run.py` (headless
  runs, grading from the answer, the commands and git; a sandboxed commit attempt counts as a fail). Run once per cell
  on Linux, no plugin installed (the canon text, not the guard): Claude v23, Claude v24, Codex v24 — **15 of 15**, every
  answer read by hand; Claude on v24 behaves as on v23, Codex as Claude. `eval/results.md`. Not widened: no mismatch.
- [x] **8. Docs and version.** `docs/methodology.md` §1.2 (one rules file: `AGENTS.md` with the canon block,
  `CLAUDE.md` a thin `@AGENTS.md` import; the old "`AGENTS.md` = `@CLAUDE.md` alias" line inverted), `README.md`,
  `docs/getting-started.md`, `docs/levels.md`, `docs/process.md`, `docs/practices/README.md`; the templates README,
  `skills/add/base.md` and `skills/upgrade` in earlier tasks. The solo kit still writes `CLAUDE.md` (out of this
  change), so its docs stay. Version: by the repository's rule the release pull request bumps it, not a feature PR —
  `scripts/release_pr.py` now also bumps the canon block's `v<N>` marker in base's `AGENTS.md` (one more entry in
  `PINS`, covered by the existing release test); CONTRIBUTING "Versioning" says so.

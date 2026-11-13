# One canon for Claude Code and Codex: AGENTS.md as the source

## Why

A project's rules reach the agent through `CLAUDE.md`, which imports the canon with `@.claude/canon/CLAUDE.md`; the
project's skills live in `.claude/skills/`, and the session header runs from hooks in `.claude/settings.json`.
OpenAI Codex CLI reads none of that: it reads `AGENTS.md` (no `@file` imports, 32 KiB for the whole chain), skills
from `.agents/skills/`, and hooks from `.codex/hooks.json`. A project set up from base therefore gives a Codex
session no operating contract, no fences in text, no skills and no session header — although the plugin itself
already works under Codex: installed from this marketplace, Codex sees all of its skills and hooks, and `guard.py`
blocks a `git commit --no-verify` made by Codex (checked with Codex 0.169).

The factory is moving to "any role on any agent": the developer, the reviewer, the night pipeline, the On-call and
the operator may each run on Claude Code or on Codex. The first step is that both agents read the same project rules
from one place.

## What changes

- **`AGENTS.md` is the project's rules file and the single source.** It holds the project's own sections (overview,
  settings, principles, constraints, maintenance) and the canon between markers:

  ```
  <!-- dark-factory:canon:begin v<N> -->
  …the operating canon…
  <!-- dark-factory:canon:end -->
  ```

  The block is replaced whole on upgrade by a small deterministic script (no three-way merge); text outside it is the
  project's and is never touched. The file stays within Codex's 32 KiB.
- **`CLAUDE.md` becomes a thin pointer:** `@AGENTS.md` plus a short Claude-only tail (none today). Claude Code reads
  the same rules through the import.
- **`.claude/canon/CLAUDE.md` is retired.** Its text moves into the canon block. The repository keeps one copy of the
  canon: the block of `templates/base/AGENTS.md`, which `canon_block.py` reads as its source (a separate canon file
  under `.harness/` would be copied into every project as a second copy).
- **Project skills move to `.agents/skills/`**, which Codex reads; `.claude/skills` becomes a relative symlink to
  `../.agents/skills`. Claude Code follows it (checked with Claude Code 2.1.32x: a skill reached through the symlink is
  listed; a bare `.agents/skills/` is not). Modules that add a skill (`feedback-desk`, `prod-monitor`) install it
  into `.agents/skills/`.
- **One session header for both agents:** `scripts/agent/session-start.sh` (bd prime, the environment block, the
  session context) replaces the commands in `.claude/settings.json`; the Claude hooks call it, and the `agent-codex`
  canon (a later change) calls it from `.codex/hooks.json`, including after compaction.
- **Agent-neutral text.** The canon and the project skills say "the agent" and name a tool only where it matters, in
  an "If you are Claude Code / If you are Codex" note. Plugin skills are not in this change.
- **Upgrade migrates an existing project.** `/dark-factory:upgrade` (and `deploy-base.sh` for an existing tree) turns
  the v23 layout into the new one on the work branch: the project's sections of `CLAUDE.md` move into `AGENTS.md`
  with the canon block, `CLAUDE.md` becomes `@AGENTS.md`, `.claude/skills/*` move to `.agents/skills/` behind the
  symlink, `.claude/hooks/*.sh` are replaced by `scripts/agent/session-start.sh`. A project file the template does not
  know is kept and named.
- **Copier keeps the symlink** (`_preserve_symlinks: true`); `AGENTS.md` and `CLAUDE.md` are excluded from copier
  updates like `CLAUDE.md` is today; `harness-diff.sh` compares the canon block with the template's canon.
- **Released as v24.** The release pull request (`scripts/release_pr.py`) bumps the plugin to 24.0.0 with the
  template pins and the canon block's `v<N>` marker; projects pinned to v23 keep working until their
  `/dark-factory:upgrade`.

## Not in this change

- The `agent-codex` canon: `.codex/hooks.json`, the permission profile, MCP, hook approval through the app-server, the
  Codex quota source. Separate change; it builds on this one.
- Rewording the plugin's own skills (`/dark-factory:x` vs `$dark-factory:x`, Claude-only tools).
- Windows: git symlinks need `core.symlinks` there; the factory runs on macOS and Linux today. Documented, not solved.
- The solo kit (`/dark-factory:init`) writes its block into `AGENTS.md` instead of `CLAUDE.md` only if it fits this
  change without a new mechanism; otherwise it follows in the `agent-codex` change.

## Acceptance scenarios

- WHEN base is deployed into a new project THEN `AGENTS.md` holds the project sections and one canon block,
  `CLAUDE.md` is `@AGENTS.md`, `.claude/skills` is a symlink to `../.agents/skills`, and `AGENTS.md` is under 32 KiB.
- WHEN Claude Code starts in that project THEN it reads the canon (through `@AGENTS.md`) and lists the project skills;
  WHEN Codex starts there THEN it reads the canon from `AGENTS.md` and lists the same skills.
- WHEN the canon changes in the template and the project upgrades THEN only the text between the markers changes;
  the project's sections stay byte-for-byte.
- WHEN the canon block was edited by hand THEN `harness-diff.sh` reports it and upgrade replaces it after showing the
  diff; WHEN a marker is missing or duplicated THEN upgrade stops and names the file.
- WHEN a v23 project upgrades THEN its project sections, its own skills and its own hook entries survive, the canon
  arrives once, and the old files (`.claude/canon/CLAUDE.md`, `.claude/hooks/env-context.sh`,
  `.claude/hooks/session-context.sh`) are removed only when unchanged from the v23 template, else kept and named.
- WHEN copier renders or updates the template THEN `.claude/skills` stays a symlink.
- WHEN a module with a skill is added THEN the skill lands in `.agents/skills/` and is visible to both agents.

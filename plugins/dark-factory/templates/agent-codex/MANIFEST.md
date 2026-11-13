# agent-codex — module manifest

> **Codex CLI works in the project under the same fences as Claude Code.** The project's rules (`AGENTS.md`), skills
> (`.agents/skills/`) and session header (`scripts/agent/session-start.sh`) are the base's and agent-neutral; this
> module adds what Codex needs on its own terms: its hook file, its permission profile, and the install step that makes
> Codex actually run them. Installed by `/dark-factory:add agent-codex`; Claude Code and Codex can both work in the
> same project.
>
> **Status: experimental.** Checked on Codex CLI 0.169 on Linux. The permission profile is a Beta feature of Codex.

> **Seam:** agent = Codex CLI ≥ 0.169 (`.codex/hooks.json`, `[permissions.<name>]` profiles, `codex app-server`
> methods `config/read`, `config/batchWrite`, `hooks/list`). Another agent gets its own canon module.

## Why

Codex reads the project's `.codex/` only in a **trusted** project, and runs a hook — the project's or a plugin's —
only after it was **approved by its hash**. A hook never approved, or changed since its approval, is skipped without a
word: no session header, no guard, no quota guard, and nothing says so. Copying the files is therefore not the install;
the install is the files plus trust plus approval, and a check that shows when an approval went stale.

## Contents

| Artifact | What it does |
|---|---|
| `.codex/hooks.json` | `SessionStart` with the empty matcher (startup, resume and compact) → `bash "$(git rev-parse --show-toplevel)/scripts/agent/session-start.sh" codex`: the shared session header, from any subdirectory the session starts in |
| `.codex/config.toml` | `default_permissions = "dark-factory"`: a profile that extends Codex's `:workspace` (read the disk, write the project) and denies `**/.env*` in the project, `~/.ssh`, `~/.aws`, `~/.codex/auth.json`, `~/.claude/.credentials.json`; network on. Enables the `dark-factory@dark-factory` plugin |
| `.codex/rules/dark-factory.rules` | Codex execpolicy, the second line after the guard: `forbidden` for the plain forms of a force push, `--no-verify` on commit/push/merge/rebase, `git config core.hooksPath`, `gh pr merge` (merging goes through `scripts/merge-feature.sh`). Prefix rules on argv: they miss a flag later in the line, which the guard catches |
| plugin `scripts/codex_project.py` (not copied) | `setup` trusts the project and approves its hooks and the plugin's, through `codex app-server` as the Codex TUI does; `check` reports trust, the profile in force, the plugin, and each hook's status (`trusted` / `untrusted` / `modified`); `--json`; exit 1 when something is off |

What comes from elsewhere: the guard (`guard.py` on `PreToolUse`) and the other always-on hooks come with the
dark-factory plugin, which Codex installs from the same marketplace as Claude Code. Under Codex the guard reads shell
commands and `apply_patch` (each file the patch adds, updates, deletes or moves gets the checks of an Edit/Write), treats
`.codex/hooks.json`, `.codex/config.toml` and `.codex/rules/` as fence files, and **denies what it would ask** under
Claude Code: Codex has no permission dialog for a hook, and a hook's "ask" there lets the call through. A fence change
in a Codex session is therefore the human's, by hand. The quota guard measures the Claude
subscription; under Codex it stays silent and the session header says "Codex quota not tracked yet" until the Codex
source is in.

## Properties (do not change without a reason)

- **Top-level keys above every table** in `.codex/config.toml`: TOML puts a key written after a table header into that
  table, and Codex then silently runs without the profile.
- **`glob_scan_max_depth` stays in the profile.** Linux sandboxing expands a `**` deny glob itself; without a depth cap
  Codex warns on every turn.
- **The domain allowlist is not here.** A project layer does not open or narrow the network by domain
  (`[permissions.<name>.network.domains]` and `features.network_proxy` work only from the user's `config.toml`); it is
  the owner's step below.
- **Branch protection is the last line on any agent.** Hooks and rules are guardrails in the session; the rule that
  holds whatever runs is the code host's: protect the main branch (and `release`) on GitHub as base's setup says.
- **A worktree inherits** the main checkout's trust and approvals; a clone in another directory does not —
  `codex_project.py setup` there too.
- **Every change to `.codex/hooks.json` or to the plugin's hooks needs a new approval**: run
  `codex_project.py setup` after it (a plugin update counts), and `check` before trusting an unattended run.

## Setup by /dark-factory:add agent-codex

The project has base (`scripts/agent/session-start.sh`, `AGENTS.md`).

**Only the owner can (one list, up front):**

1. Install Codex CLI on the machine and log in (`codex login`).
2. Install the plugin in Codex: `codex plugin marketplace add <the dark-factory canon, a Git URL or a checkout>`, then
   `codex plugin add dark-factory@dark-factory`.
3. Optional, to narrow the network by domain: in the user's `~/.codex/config.toml` (not the project's),
   `[features] network_proxy = true` and `[permissions.dark-factory.network.domains]` with `"<domain>" = "allow"` for
   each domain the work needs (the code host, package registries). The project's profile is on with the network open
   to every domain until then.

**The agent:**

1. Copies the files: `bash "<plugin root>/scripts/add-module.sh" agent-codex --dry-run`, then without `--dry-run` after
   the "yes". An existing `.codex/config.toml` is not overwritten: merge the profile and the plugin table into it by
   hand, top-level keys above the tables.
2. Commits them on a branch; the change goes out like any other.
3. In the main checkout, after the owner's steps 1–2: `python3 "<plugin root>/scripts/codex_project.py" setup`. It
   writes to the user's Codex config (trust and approvals live there, not in git), so it runs on every machine where
   Codex works in this project.
4. Status check: `python3 "<plugin root>/scripts/codex_project.py" check` — every line ✓, exit 0. Then a short
   `codex exec` in the project shows the session header (the "🛡️ fences" line), and
   `codex sandbox -- cat .env` (with a `.env` present) is denied.
5. Tests: `python3 tests/test_add_module.py` in the canon covers the files; there is no project test to run.

## Abandon criterion

Remove the module from a project if, within a month, the hooks were found unapproved or modified in an unattended run
more than once — that means approval by hash costs more than it guards, and Codex there should run without the
project layer until the install step is reliable.

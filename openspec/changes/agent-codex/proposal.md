# Codex CLI works in a factory project under the same fences: the agent-codex module

## Why

After agents-md-core the project's rules (`AGENTS.md`), skills (`.agents/skills/`) and session header
(`scripts/agent/session-start.sh`) no longer depend on the agent, and the dark-factory plugin installs into Codex CLI
as it is: its skills are visible and its `guard.py` denies `git commit --no-verify` under Codex. What was missing is
the part only Codex has:

- Codex reads a project's `.codex/` only in a **trusted** project, and runs a hook — the project's or a plugin's — only
  after it was **approved by its hash**. A hook never approved, or changed since (a plugin update changes every one of
  them), is skipped **silently**: no session header, no guard, no quota guard, no warning. Copying files is not an
  install.
- Codex has no `permissions.deny`; its equivalent is a permission profile (Beta) in `config.toml`.
- The plugin's quota guard measures the Claude subscription with a `claude -p` probe. Under Codex it would print the
  Claude quota and stop Codex by someone else's limit.
- The session header's "plugin NOT LOADED" check reads Claude Code's install records; under Codex it said nothing.

## What changes

- **A module `agent-codex`** (`/dark-factory:add agent-codex`, alias `codex`) copies two files into the project:
  - `.codex/hooks.json`: `SessionStart` with the empty matcher (startup, resume and compact) runs the shared header,
    `session-start.sh codex`, from the repository top level whatever subdirectory the session starts in;
  - `.codex/config.toml`: a permission profile `dark-factory` (extends `:workspace`; denies `**/.env*` in the project,
    `~/.ssh`, `~/.aws`, `~/.codex/auth.json`, `~/.claude/.credentials.json`; network on) as the project default, and
    the plugin enabled. The domain allowlist works only from the user's `config.toml`: it is an owner's step in the
    manifest, not a project file.
- **`scripts/codex_project.py` in the plugin** does the install the files cannot: `setup` trusts the project and
  approves its hooks and the plugin's through `codex app-server` (`config/batchWrite` of `projects` and `hooks.state`,
  as the Codex TUI does); `check` reports trust, the profile in force, the plugin and every hook's status
  (`trusted` / `untrusted` / `modified`), with `--json` and exit 1 when anything is off. A worktree is set up on its
  main checkout, whose trust and approvals it inherits.
- **The session header under Codex** says loudly when the plugin is not installed, not enabled, or its hooks were never
  approved — the Codex counterpart of "dark-factory NOT LOADED".
- **The quota guard stays silent under Codex** and the header says "Codex quota not tracked yet" until the Codex
  source (`account/rateLimits/read`) is in. A Codex session is recognised by its transcript
  (`<CODEX_HOME>/sessions/…/rollout-*.jsonl`), not by the environment: a hook inherits the launcher's environment,
  and a Codex started from a Claude Code session carries `CLAUDECODE`.

## Not in this change

Codex roles (`.codex/agents/`), `.codex/rules` as a second line of fences and the `apply_patch` coverage of the guard
(next change), the Codex quota source, provisioning Codex sessions on a server, the feed.

## Acceptance

- WHEN `/dark-factory:add agent-codex` runs in a base project THEN `.codex/hooks.json` and `.codex/config.toml` are
  copied, nothing existing is overwritten, and the manifest stays in the plugin.
- WHEN `codex_project.py check` runs before `setup` THEN it exits 1 and names the missing trust, the profile not in
  force and each unapproved hook as "skipped silently until approved".
- WHEN `codex_project.py setup` runs THEN the project is trusted and its hook and the plugin's are approved in the same
  run, and `check` exits 0.
- WHEN a hook in `.codex/hooks.json` changes, or the plugin is reinstalled, THEN `check` shows it `modified` and exits 1
  until `setup` runs again.
- WHEN a Codex session starts in a set-up project THEN the header prints (ENV, harness, the 🛡️ fences line, the session
  header) and the quota line is "Codex quota not tracked yet".
- WHEN a command under the profile reads `.env`, `app/sub/.env`, `~/.ssh`, `~/.codex/auth.json` or writes outside the
  project THEN it is denied; reading and writing the project works.
- WHEN the plugin is missing, disabled, or its hooks were never approved THEN the Codex header says so, with the fix.

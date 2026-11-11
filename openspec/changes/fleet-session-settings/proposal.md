# The owner's new sessions on a server start with the project's session policy

## Why

The sessions the owner opens from claude.ai on a provisioned server take the account's default model. The owner's
decision is that the pipeline runs on Opus. `claude remote-control` takes `--settings <file>` (Claude Code 2.1.321 or
later), but `SESSION_ARGS` refused every flag beyond the permission mode, the spawn mode and the capacity: its value
lands in a systemd `ExecStart`, so it is an allowlist.

## What changes

- `SESSION_ARGS` accepts `--settings <path>`, once. The path is relative to the project and stays inside
  `<project>/.claude/factory/` after resolving: no absolute path, no `..`, no symlink out, and it must be a file.
  Anything else refuses to provision the project, like any other refused value. The unit gets the resolved path: the
  sessions `remote-control` spawns work in worktrees of their own.
- The base template ships `.claude/factory/session-settings.json` with `{"model": "opus"}`.
- Only the owner's `remote-control` takes it; the development session does not.
- A session reads its settings when it starts. `fleet.py provision` restarts the project's `remote-control` unit when
  the file changed since the last provision (or the flag was added or removed) — never on the first provision, never
  the development session. Restarting ends the sessions open from claude.ai, so it happens only when the owner runs
  `provision`, not on every edit of the file.
- No `permissions.denyInsteadOfPrompting` in the file: the owner declined it (after a denial the model may work
  around the rule).

## Acceptance

- WHEN `SESSION_ARGS="--settings .claude/factory/session-settings.json"` and the file exists THEN the remote-control
  unit's command carries `--settings <project>/.claude/factory/session-settings.json`, and the development session's
  does not.
- WHEN the path is absolute, holds `..`, leads out through a symlink, is not a file, or `--settings` is given twice THEN
  provision refuses the project with the reason and provisions the others.
- WHEN the file changed and the owner runs `fleet.py provision` THEN `df-<slug>-rc.service` is restarted once; WHEN
  nothing changed THEN it is not.

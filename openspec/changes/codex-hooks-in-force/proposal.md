# A Codex run does not start without its hooks; fleet status shows stale approvals

## Why

Codex runs a hook only when it is approved by its current hash, and skips the rest without a word. A plugin update
changes the hash of every plugin hook, so after an update every Codex session of a project runs without the guard,
the quota guard and the role registration until `codex_project.py setup` is run again. The session header checks only
that some approval exists, not its hash. In the broker pilot this is exactly what happened: the plugin copy was
patched, all twelve plugin hooks went `modified`, the SessionStart hook that registers the role never ran, and the
broker had no session to deliver to. After `setup` the same pilot delivered, closed and answered in 20 s.

## What changes

- `codex_feature.py` runs `codex_project.py check --json` for the main checkout before its first turn; when the check
  is not green the run stops with `Codex hooks not in force: <why> — the owner: codex_project.py setup --project
  <root>`. No flag skips it: an agent could use one to run without its fences.
- `fleet.py status` gets a **Codex hooks** line per project that has `.codex/hooks.json`, on a server with
  `FLEET_CODEX=on`: green with the number of approved hooks, ○ with the setup command otherwise.
- agent-codex MANIFEST says both.

## Acceptance

- WHEN a plugin hook is `modified` THEN `codex_feature.py run` stops before any `codex exec` with the setup command.
- WHEN all hooks are approved THEN the run goes on and `fleet.py status` shows "N hooks approved".
- WHEN the project has no agent-codex module or the server runs no Codex THEN fleet status shows no such line.

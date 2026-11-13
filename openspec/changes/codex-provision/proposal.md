# A factory server runs Codex too: daemon kept alive, remote control, domain allowlist, status

## Why

agent-codex, codex-fences and codex-quota make Codex work in a project under the factory's fences. The server side was
still by hand: Codex CLI's app-server daemon serves the Codex sessions the owner opens from the ChatGPT app (Codex
remote control; pairing a phone with a headless server works, stage 0.7), but nothing brought it back after a crash or
a reboot; the agent-codex permission profile leaves the network open to every domain because an allowlist only works
from the user's Codex config, which no step wrote; and `fleet.py status` knew nothing of Codex.

## What changes

- **`FLEET_CODEX=on` in `fleet.env`** makes `fleet.py provision` write `df-fleet-codex.service` and `.timer`: every
  5 minutes from boot `codex app-server daemon start`, a no-op while the daemon runs (it updates itself). Without the
  setting the pair is removed and the daemon is the owner's again.
- **`FLEET_CODEX_REMOTE=on`** adds `codex app-server daemon enable-remote-control` to each start; pairing stays the
  owner's (`codex remote-control pair`, a short-lived code).
- **`FLEET_CODEX_DOMAINS="github.com,pypi.org,…"`** — provision writes them into the user's Codex config through
  `codex_project.py domains`: `features.network_proxy = true` and the profile's `network.domains`, the whole list
  replaced, so a domain removed from the setting is closed again.
- **`fleet.py status`** shows, with `FLEET_CODEX=on`: Codex logged in or not, the daemon's state and the app-server and
  CLI versions (`codex app-server daemon version`), and the Codex quota (`quota.py status --agent codex`). A Codex that
  stops running or loses its login tells the owner through the fleet watch.
- The provision-server skill: the unit row and the owner's step (install, log in, plugin, the three settings, pairing).

## Not in this change

Per-project Codex sessions as server units (roles addressed by name need the role broker, stage 2), the feed's
per-agent quota and versions (step 1.6).

## Acceptance

- WHEN `fleet.env` has `FLEET_CODEX=on` THEN provision writes and enables `df-fleet-codex.timer`, whose service runs
  `codex app-server daemon start`; with `FLEET_CODEX_REMOTE=on` it also enables remote control.
- WHEN `FLEET_CODEX` is removed THEN provision disables and deletes the pair.
- WHEN `FLEET_CODEX_DOMAINS` is set THEN provision runs `codex_project.py domains <list>`, which writes
  `features.network_proxy` and `permissions.dark-factory.network.domains` (replace) into the user's config.
- WHEN `FLEET_CODEX=on` and Codex is not logged in THEN `fleet.py status` marks Codex ○ with "codex login"; logged in
  with the daemon running THEN ● with the versions; and the Codex quota line follows.
- WHEN `FLEET_CODEX=on` but no codex binary is found THEN provision refuses the Codex part and says to install it.

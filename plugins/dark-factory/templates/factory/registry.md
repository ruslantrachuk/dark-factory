# Registry of projects

> What this factory runs: one row per project. It describes projects; it does not locate them. Where a project is
> checked out on a given machine is that machine's business (`machines/<host>.md` says how the machine is set up, and
> `~/.config/dark-factory/projects` on the machine lists the checkout paths that `/dark-factory:factory-status` and
> `/dark-factory:provision-server` read). Do not write paths here.
>
> **Single writer**: a human, or an agent on an explicit command. Rows change rarely: a project is added, its level or
> modules change, a client is onboarded. `/dark-factory:add` ends by offering to add or update the row; after
> `/dark-factory:init`, add it by hand.
>
> **Keeping current**: the version of the plugin a project is pinned to is in its own `.claude/settings.json`
> (`"ref": "v<N>"`) and `.harness/base-sha`; `/dark-factory:factory-status` shows each project's lag, so the registry
> does not repeat it.

| Project | What it is | Repository | Level | Modules | Client | Machine |
|---|---|---|---|---|---|---|
| _Example (delete this row):_ photobooth-panel | control panel for the photo booths | `acme/photobooth-panel` | 3 | base, release, on-call, monitor | Example Client Ltd | vps-1 |

Columns:

- **Level**: the project's level on the ladder (`/dark-factory:level`).
- **Modules**: what `/dark-factory:add` installed on top of the plugin's fences (`base`, `release`, `on-call`, `monitor`,
  `observability`, `code-audit`, `feature-pipeline`). Record deliberate deviations here ("sandbox: no, because …").
- **Client**: whose project it is; "—" for your own.
- **Machine**: the name of the file in `machines/` for the machine its sessions run on.

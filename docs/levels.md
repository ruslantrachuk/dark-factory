# Levels: from solo to team

One plugin at every level. Moving up adds files to the project and raises the fence level in `.claude/fences.env`;
nothing is reinstalled and nothing done at a lower level has to be redone. `/dark-factory:level` shows where a
project is, the signals for the next level and what would change; each step is taken only on the owner's "yes".
The fence level moves down the same way.

| Level | For | What it adds | How to get there | Time to move up when |
|---|---|---|---|---|
| **0. Solo** | one person, a laptop | the `dark-factory` plugin: quota guard, guard hook at `solo`, `merge-feature.sh --accepted-by`, a short operating contract, a minimal pre-push hook | `/plugin install dark-factory@dark-factory`, then `/dark-factory:init` | from the start |
| **1. Solo with discipline** | one person, a project that lives longer than a month | the full `base` template: OpenSpec changes, the `bd` queue, the checked test pyramid, CI tiers, the session log; guard at `standard` | the `deploy-project` skill in a checkout of this repository (it asks which level to start at and writes the fence level) | the agent loses context between sessions; features take more than one sitting |
| **2. Unattended** | one person and a server | development sessions on the server that come back after a reboot, the feature pipeline (`feature-pipeline` module), runs booked for later, `QUOTA_FAIL_CLOSED=1` | the `provision-server` skill (`scripts/fleet.py provision`), then `/dark-factory:level` writes `QUOTA_FAIL_CLOSED=1` | you want work to continue while you are away from the keyboard |
| **3. With a client** | a studio: a project in production with a client | On-call in the client chat (`feedback-desk`), production monitor (`prod-monitor`), observability, releases by tag (`release-tag`) | one module at a time, each by its `MANIFEST.md` (`feedback-desk` and `prod-monitor` by their own skills) | there is production and a client who writes in a chat |
| **4. Team** | several developers | guard at `team`: a GitHub approval before merge, no merge without CI; branch protection on main; the board with claims; the four roles held by different people | `/dark-factory:level team`, and branch protection on main | a second person pushes to the same repository |

## How the level is read

`/dark-factory:level` ([the plugin](../plugins/dark-factory/README.md), `scripts/level.py`) reads the level from
evidence in the project; it is never stored.

| Level | Evidence |
|---|---|
| 0 | `.claude/fences.env` exists (the project opted in) |
| 1 | + `openspec/`, `.beads/` and `CODING_STANDARDS.md` |
| 2 | + `.claude/factory/session.env`, or the project listed in `~/.config/dark-factory/projects` (the file `scripts/fleet.py provision` reads) |
| 3 | + the files of `feedback-desk` (`scripts/feedback-desk.sh`, `.claude/feedback-desk/config.env`) or `prod-monitor` (`scripts/ops/prod_monitor/`) |
| 4 | level 2 + `FENCE_LEVEL=team` |

It also names the gaps at the current level: base deployed but the fence still `solo`, a server without
`QUOTA_FAIL_CLOSED=1`. The signals it can see in the project are cheap and partial (files, and one `git log` of at
most 300 commits); the owner knows the rest:

| Next level | Signals the plugin can see |
|---|---|
| 1 | the history spans 30 days or more; `devlog.md` has 10 entries or more |
| 2 | 10 or more open tasks in the `bd` queue; this machine already runs the factory for other projects |
| 3 | a production deploy configuration (`Dockerfile`, `fly.toml`, `render.yaml`, `Procfile`, a deploy workflow …) |
| 4 | two or more people authored the recent commits |

## Rules

- **Each level builds on the one below.** A project at level 3 still has everything from levels 0–2.
- **The agent proposes, the owner decides.** When a session starts in a project with a next-level signal, the plugin
  prints one line naming it; the agent may mention it, and does not move a project up or down by itself.
- **The fence level moves only through `/dark-factory:level`.** At every level the guard denies deleting, moving or
  truncating `.claude/fences.env` and lowering `FENCE_LEVEL` with an edit; the command writes it after the owner's
  own `/dark-factory:level` prompt and "yes".
- **Structural steps are their own commands.** `/dark-factory:level` names `deploy-project`, `provision-server` or a
  module's manifest and never runs them. Moving down structurally (removing a module, leaving the server) follows
  that module's manifest or `provision-server`.
- **Levels are not modules.** A module is a piece of the line; a level is how much of the line a project runs and how
  strictly it is fenced. Levels 3 and 4 are independent of each other: a team without a client goes from 2 to 4.

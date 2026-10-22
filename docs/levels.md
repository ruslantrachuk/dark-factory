# Levels: from solo to team

One plugin at every level. Moving up adds files to the project and raises the fence level in `.claude/fences.env`;
nothing is reinstalled and nothing done at a lower level has to be redone. `/dark-factory:level` shows where a
project is, the signals for the next level and what would change; each step is taken only on the owner's "yes".
The fence level moves down the same way.

| Level | For | What it adds | How to get there | Time to move up when |
|---|---|---|---|---|
| **0. Solo** | one person, a laptop | the `dark-factory` plugin: quota guard, guard hook at `solo`, `merge-feature.sh --accepted-by`, a short operating contract, a minimal pre-push hook | `/plugin install dark-factory@dark-factory`, then `/dark-factory:init` | from the start |
| **1. Solo with discipline** | one person, a project that lives longer than a month | the full `base` template: OpenSpec changes, the `bd` queue, the checked test pyramid, CI tiers, the PR description as the record of work; guard at `standard` | the `deploy-project` skill in a checkout of this repository (it asks which level to start at and writes the fence level) | the agent loses context between sessions; features take more than one sitting |
| **2. Unattended** | one person and a server | development sessions on the server that come back after a reboot, the feature pipeline (`feature-pipeline` module), runs booked for later, `QUOTA_FAIL_CLOSED=1` | the `provision-server` skill (`scripts/fleet.py provision`), then `/dark-factory:level` writes `QUOTA_FAIL_CLOSED=1` | you want work to continue while you are away from the keyboard |
| **3. With a client** | a studio: a project in production with a client | On-call in the client chat (`feedback-desk`), production monitor (`prod-monitor`), observability, releases by tag (`release-tag`) | one module at a time, each by its `MANIFEST.md` (`feedback-desk` and `prod-monitor` by their own skills) | there is production and a client who writes in a chat |
| **4. Team** | several developers | guard at `team`: a GitHub approval before merge, no merge without CI; branch protection on main; the board with claims; the four roles held by different people | from level 1: `/dark-factory:level team`, then merge the raised `fences.env` and turn on branch protection on main; a server is optional | a second person pushes to the same repository |

## How the level is read

`/dark-factory:level` ([the plugin](../plugins/dark-factory/README.md), `scripts/level.py`) reads the level from
evidence in the project; it is never stored.

| Level | Evidence |
|---|---|
| 0 | `.claude/fences.env` exists (the project opted in) |
| 1 | + `openspec/` and `CODING_STANDARDS.md` |
| 2 | + `.claude/factory/session.env`, or the project listed in `~/.config/dark-factory/projects` (the file `scripts/fleet.py provision` reads) |
| 3 | + the files of `feedback-desk` (`scripts/feedback-desk.sh`, `.claude/feedback-desk/config.env`) or `prod-monitor` (`scripts/ops/prod_monitor/`) |
| 4 | level 1 + `FENCE_LEVEL=team` (a server is not required, and level 3 is independent) |

It also names the gaps at the current level: base deployed but the fence still `solo`, a server without
`QUOTA_FAIL_CLOSED=1`. The signals it can see in the project are cheap and partial (files, one `git log` of at
most 300 commits and one bounded count of the execution queue); the owner knows the rest:

| Next level | Signals the plugin can see |
|---|---|
| 1 | the history spans 30 days or more; 10 or more merge commits among the last 300 commits |
| 2 | 10 or more open tasks in the execution queue (`bd count`); this machine already runs the factory for other projects |
| 3 | a production deploy configuration (`Dockerfile`, `fly.toml`, `render.yaml`, `Procfile`, a deploy workflow …) |
| 4 | two or more people authored the recent commits |

## Rules

- **Each level builds on the one below.** A project at level 3 still has everything from levels 0–2.
- **The agent proposes, the owner decides.** When a session starts in a project with a next-level signal, the plugin
  prints one line naming it; the agent may mention it, and does not move a project up or down by itself.
- **The fence level moves only through `/dark-factory:level`.** At every level the guard denies deleting, moving or
  truncating `.claude/fences.env` and lowering `FENCE_LEVEL` with an edit. The command writes the file only after
  the human typed `/dark-factory:level <target>` themselves: a UserPromptSubmit hook records a grant bound to that
  target, valid once and for 10 minutes. A bare `/dark-factory:level` only reports. An agent cannot produce that
  prompt, and the guard denies booking it through scheduled runs, other sessions or `claude -p`.
- **Main sets the floor.** The effective level is the stricter of the working copy and `origin/main:.claude/fences.env`.
  Raising takes effect at once; lowering takes effect only once the lowered file is merged into main, which at
  `team` means a reviewed PR.
- **Structural steps are their own commands.** `/dark-factory:level` names `deploy-project`, `provision-server` or a
  module's manifest and never runs them. Moving down structurally (removing a module, leaving the server) follows
  that module's manifest or `provision-server`.
- **Levels are not modules.** A module is one piece of the pipeline; a level is how much of it a project runs and how
  strictly it is fenced. Levels 3 and 4 are independent of each other, and level 4 does not need a server: a team
  without a server or a client goes from 1 to 4.

## Fence levels

`.claude/fences.env` → `FENCE_LEVEL`. The guard hook (`scripts/guard.py` in the plugin) reads every tool call
before it runs and denies the ones below; every denial says what to do instead.

| Level | What is denied or required |
|---|---|
| `solo` | force pushes and `+refspec`, a push to the main branch, `--no-verify` and other ways around the git hooks, release-tag pushes outside `scripts/release.sh`, deleting or hard-resetting main; changes to the fences themselves (deleting or lowering `fences.env`, writing into the installed plugin). `merge-feature.sh` requires `--accepted-by "<name>"`; `--skip-ci "<reason>"` is allowed; with no CI workflows at all, the first merge runs the local gate (`CI: none (local gate)`) |
| `standard` (default when `FENCE_LEVEL` is empty) | `solo` + `gh pr merge` and the merge API only through `merge-feature.sh`, no `gh pr review --approve` by the agent, the fence files (`.claude/settings*.json`, `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`) edited by the human only |
| `team` | `standard` + a GitHub approval (`reviewDecision` APPROVED) before every merge; `--skip-ci` and merging without CI are refused |

`--accepted-by` names who accepted the change. Below `team` the name is recorded (a PR comment and an
`Accepted-by:` trailer), not verified; at `team` the GitHub approval is what is verified.

**What the guard is and is not.** The guard is a seatbelt: a static reader of tool calls that stops an agent's
mistakes and the common shortcuts. It is not a sandbox against a determined or hostile agent. It cannot see
through a script written to a file and then run, an alias or function defined elsewhere, a subprocess started by
another program, or an arbitrary interpreter. The real gates are on the code host and the machine: branch
protection or rulesets on GitHub, required reviews, and the Claude Code sandbox. Turn on branch protection on main at
every level (block force pushes, require a PR; at `team`, one approval and no admin bypass). Details:
[SECURITY.md](../SECURITY.md) and the [threat model](threat-model.md). A human bypasses the guard by restarting the
session with `GUARD=off claude` (the quota guard: `QUOTA_GUARD=off`).

## Not yet

What a larger organisation would expect and the factory does not do yet:

- **API, Bedrock and Vertex authentication.** The factory assumes a Claude subscription. On API keys or a cloud
  provider there are no 5-hour and 7-day windows, so the quota guard should be optional there; this is not wired up.
- **A shared execution queue for a team.** Level 4 drops the server requirement, but the `bd` queue of `base` is a
  local store per checkout: teammates see each other's work on the board and in the PRs, not in one queue.
- **Jira and GitHub Enterprise.** They fit the existing seams (the board in the `board` skill; the code host in
  `merge-feature.sh`), but nobody has written that code.
- **An adoption guide for an existing repository.** `deploy-project` extends an existing `CLAUDE.md` and never
  overwrites files, but there is no step-by-step guide for bringing a large, established repository on board.

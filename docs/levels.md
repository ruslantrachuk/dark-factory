# Levels: from solo to team

One plugin at every level. Moving up adds files to the project and raises the fence level in `.claude/fences.env`;
nothing is reinstalled and nothing done at a lower level has to be redone. `/dark-factory:level` shows where a
project is, the signals for the next level and what would change; each step is taken only on the owner's "yes".
The fence level moves down the same way.

| Level | For | What it adds | How to get there | Time to move up when |
|---|---|---|---|---|
| **0. Solo** | one person, a laptop | the `dark-factory` plugin: quota guard, guard hook at `solo`, `merge-feature.sh`, a short operating contract, a minimal pre-push hook | `/plugin install dark-factory@dark-factory`, then `/dark-factory:init` | from the start |
| **1. Solo with discipline** | one person, a project that lives longer than a month | the full `base` template: OpenSpec changes, the `bd` queue, the checked test pyramid, CI tiers, the PR description as the record of work; guard at `standard`; releases by tag (`vYYYY.MM.DD.N`) when the project has production; a release takes all of main and refuses while a merge since the last tag lacks the acceptance mark | `/dark-factory:add base` (it asks which level to start at and whether there is a production deploy, and writes the fence level) | the agent loses context between sessions; features take more than one sitting |
| **2. Unattended** | one person and a server | development sessions on the server that come back after a reboot, the feature pipeline (`feature-pipeline` module; token-expensive, for big tasks left to run alone, while an interactive session uses the skills and roles directly), runs booked for later, `QUOTA_FAIL_CLOSED=1` | `/dark-factory:provision-server` (`fleet.py provision`), then `/dark-factory:level` writes `QUOTA_FAIL_CLOSED=1` | you want work to continue while you are away from the keyboard |
| **3. With a client** | a studio: a project in production with a client | On-call in the client chat, production monitor, observability: the client modules | one module at a time, `/dark-factory:add on-call`, `add monitor`, `add observability` (each starts with the steps only you can do) | there is production and a client who writes in a chat |
| **4. Team** | several developers | guard at `team`: a GitHub approval before merge, no merge without CI; branch protection on main; the board with claims; the four roles held by different people | from level 1: `/dark-factory:level team`, then merge the raised `fences.env` and turn on branch protection on main; a server is optional | a second person pushes to the same repository |

## How the level is read

`/dark-factory:level` ([the plugin](../plugins/dark-factory/README.md), `scripts/level.py`) reads the level from
evidence in the project; it is never stored.

| Level | Evidence |
|---|---|
| 0 | `.claude/fences.env` exists (the project opted in) |
| 1 | + `.copier-answers.yml` (the base template installed by Copier), or `openspec/` and `CODING_STANDARDS.md` at the root |
| 2 | + `.claude/factory/session.env`, or the project listed in `~/.config/dark-factory/projects` (the file `fleet.py provision` reads) |
| 3 | + a client module: the files of On-call (`scripts/feedback-desk.sh`, `.claude/feedback-desk/config.env`), the monitor (`scripts/ops/prod_monitor/`) or observability (`docs/deploy/monitoring.md`); `scripts/release.sh` (releases by tag) is listed but is not a level |
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
- **The fence level moves only on the human's word.** The usual way is `/dark-factory:level`: the command writes the
  file only after the human typed `/dark-factory:level <target>` themselves: a UserPromptSubmit hook records a grant
  bound to that target, valid once and for 10 minutes. A bare `/dark-factory:level` only reports. An agent cannot
  produce that prompt, and the guard denies booking it through scheduled runs, other sessions or `claude -p`. Any
  other way — deleting, moving or truncating `.claude/fences.env`, lowering `FENCE_LEVEL` with an edit — is a fence
  change: at every level it runs only with the human's yes in the permission dialog (below).
- **Main sets the floor.** The effective level is the stricter of the working copy and `origin/main:.claude/fences.env`.
  Raising takes effect at once; lowering takes effect only once the lowered file is merged into main, which at
  `team` means a reviewed PR.
- **Structural steps are their own commands.** `/dark-factory:level` names `/dark-factory:add`, `/dark-factory:provision-server` and never runs them. Moving down structurally (removing a module, leaving the server) follows
  that module's manifest or `/dark-factory:provision-server`.
- **Levels are not modules.** A module is one piece of the pipeline; a level is how much of it a project runs and how
  strictly it is fenced. Levels 3 and 4 are independent of each other, and level 4 does not need a server: a team
  without a server or a client goes from 1 to 4.

## Fence levels

`.claude/fences.env` → `FENCE_LEVEL`. The guard hook (`scripts/guard.py` in the plugin) reads every tool call
before it runs. It denies the ones below, and every denial says what to do instead; a change to the fences
themselves it asks the human about (see the paragraph after the table).

| Level | What is denied, asked or required |
|---|---|
| `solo` | denied: force pushes and `+refspec`, a push to the main branch, `--no-verify` and other ways around the git hooks (`core.hooksPath`, `.git/config`, `.git/hooks/`), release-tag pushes outside `scripts/release.sh`, GitHub API writes of refs, releases or branch protection, deleting or hard-resetting main, writing into the installed plugin, booking a `/dark-factory:level` prompt. Asked: deleting or lowering `fences.env`, settings that switch off the hooks or the plugin (`disableAllHooks`, `GUARD`/`QUOTA_GUARD`, `enabledPlugins`, `claude plugin disable\|uninstall`), shell writes to `.claude/settings*.json` and `.githooks/`. `--skip-ci "<reason>"` is allowed; with no CI workflows at all, the first merge runs the local gate (`CI: none (local gate)`) |
| `standard` (default when `FENCE_LEVEL` is empty) | `solo` + `gh pr merge` and the merge API only through `merge-feature.sh`, no `gh pr review --approve` by the agent; the fence files (`.claude/settings*.json`, `.claude/fences.env`, `.githooks/`, `scripts/merge-feature.sh`) edited only with the human's yes in the permission dialog |
| `team` | `standard` + a GitHub approval (`reviewDecision` APPROVED) before every merge; `--skip-ci` and merging without CI are refused |

**A release is a person's decision, at every level.** With the `release-tag` module, a run of `scripts/release.sh` that
tags (and marking a feature `accepted` by hand: the label, a comment "accepted by …") is asked in the same dialog: "a
release ships all of main since the last tag to production; Yes = you accept it" (the reason says so when
`--owner-accepts` or `--include-unaccepted` is used). The On-call (`feedback-desk.sh` sets `DF_ROLE=on-call` next to
`DF_UNATTENDED=1`) may run only `scripts/feedback-desk.sh accept|release`, whose script checks that the sender is on the
acceptance list; `--owner-accepts` and `--manual` are denied to it. Any other launched agent (subagent,
pipeline, scheduled run, `claude -p`) is denied: leave the release to the owner or the On-call. See
[layers/acceptance.md](layers/acceptance.md).

**Fence changes are asked, not denied.** The agent may change its own harness, but only with a human's yes. For a
fence change the guard answers `ask`: Claude Code shows the call with the guard's reason in its permission dialog
("Hook PreToolUse requires confirmation"), and it runs only on Yes. Where nobody can answer the dialog, the guard
denies it instead, with "leave it to the human: write the patch and a note, keep going": in a subagent, in the On-call
session (`feedback-desk.sh` sets `DF_UNATTENDED=1`), in `claude -p` or another SDK run. The server's development
session is driven by a person from claude.ai, so there the guard asks.
A call that mixes a fence change with something denied is denied. Every ask and deny is logged to
`.claude/state/audit.jsonl`.

At `solo` and `standard` the agent merges itself through `merge-feature.sh` once CI is green and its own review
is done; at `team` the GitHub approval is what is verified. The human gate is the release, a later stage.

**What the guard is and is not.** The guard is a seatbelt: a static reader of tool calls that stops an agent's
mistakes and the common shortcuts. It is not a sandbox against a determined or hostile agent. It cannot see
through a script written to a file and then run, an alias or function defined elsewhere, a subprocess started by
another program, or an arbitrary interpreter. The real gates are on the code host and the machine: branch
protection or rulesets on GitHub, required reviews, and the Claude Code sandbox. Turn on branch protection on main at
every level (block force pushes, require a PR; at `team`, one approval and no admin bypass). Details:
[SECURITY.md](../SECURITY.md) and the [threat model](threat-model.md). A human bypasses the guard by restarting the
session with `GUARD=off claude` (the quota guard: `QUOTA_GUARD=off`).

**Enterprise-managed Claude Code settings.** Managed settings take precedence over the project's and the user's.
If your organisation's managed settings set `allowManagedHooksOnly` or `disableAllHooks`, the plugin's hooks (the
guard, the quota guard, the session-start hooks) are silently not run, and no fence is on. A plugin allowlist that
omits dark-factory, or `strictKnownMarketplaces` that does not list this marketplace, stops the plugin or its
marketplace from installing or loading. Nothing warns you inside the session: check `/hooks` in Claude Code, and if the plugin's hooks are missing ask the administrator to allow the plugin. Where the repository must not
depend on a public marketplace, fork it, host the fork in an allowed marketplace and pin the project to a tag of
that fork.

## Not yet

What a larger organisation would expect and the factory does not do yet:

- **API, Bedrock and Vertex authentication.** The factory assumes a Claude subscription. On API keys or a cloud
  provider there are no 5-hour and 7-day windows, so the quota guard should be optional there; this is not wired up.
- **A shared execution queue for a team.** Level 4 drops the server requirement, but the `bd` queue of `base` is a
  local store per checkout: teammates see each other's work on the board and in the PRs, not in one queue.
- **Jira and GitHub Enterprise.** They fit the existing seams (the board in the `board` skill; the code host in
  `merge-feature.sh`), but nobody has written that code.
- **Stacks the reference implementation does not cover.** Installation adapts a module's seams in place
  ([functions.md](functions.md) "Seams"), which covers another test stack or layout (Node, Go, a monorepo behind one
  test command). Not covered: a code host other than GitHub (the guard, the merge and the release are written against
  `gh`), releases through an app store, the production monitor for a product with no deployed URL, Windows without WSL,
  and the quota guard without a Claude subscription.
- **An adoption guide for an existing repository.** `/dark-factory:add base` extends an existing `CLAUDE.md` and never
  overwrites files, but there is no step-by-step guide for bringing a large, established repository on board.

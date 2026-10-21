# Getting started

From nothing to one project running its lifecycle with Claude Code. Read the [README](../README.md) first for
what the factory is; this page is the order of steps.

## Who this is for

- You build software for yourself or for clients with **Claude Code** on a Claude subscription, and want the
  agent to do the middle of the line (code, tests, release preparation) while you keep the edges (what to
  build, acceptance, "ship it").
- Your code lives on **GitHub**; the default test stack and scripts are **Python** (other stacks work, the test
  pyramid and gates are then yours to adapt); the board is **Linear** (the `board` skill; the queue itself is
  `bd` in the repository and works without a board).
- Optional, per module: a **Telegram** group with the client (On-call session), **Postgres** in production (monitor).

Not a fit if you need a hosted product, a non-Claude agent, or no human acceptance step at all.

## What you need

| Tool | For | Install |
|---|---|---|
| Claude Code, logged in | everything | <https://code.claude.com> |
| Superpowers plugin (recommended) | GATE step 0 skills | `claude plugin install superpowers@claude-plugins-official` |
| `git`, `gh` (logged in) | branches, PRs, `merge-feature.sh` | <https://cli.github.com> |
| `bd` (beads) | the task queue | <https://github.com/steveyegge/beads> |
| `jq`, Python 3.12 | queue scripts, quota guard, tests | your package manager |
| A small Linux server with `tmux` and `systemd --user` | long-lived sessions (`provision-server`) | any VPS |
| Bun | On-call and monitor channels (feedback-desk, prod-monitor) | <https://bun.sh> |

## Steps

1. **Your instance repository.** Clone this repository (the canon), and create a private repository of your own
   for the instance: copy [registry.example.md](../registry.example.md) there as `registry.md`. Open Claude Code in
   the canon checkout — the factory skills live in its `.claude/skills/`.
2. **Deploy a project.** In Claude Code: "deploy project `<name>` into `<path>`". The `deploy-project` skill shows
   a dry-run of `scripts/deploy-base.sh`, asks the configuration questions one at a time, fills the placeholders,
   offers modules and writes the registry row. Nothing leaves your machine without your "yes".
3. **First session in the project.** Open Claude Code in the project. The SessionStart hooks print the queue, the
   latest devlog entry and the quota; `CLAUDE.md` holds the operating contract. Write the first OpenSpec change
   for a small feature, approve it, run `openspec-to-beads`, then let the session build the first phase.
4. **Accept and ship.** Review the branch (the dev environment via the `stand` skill when there is a UI), say
   "accepted"; the session runs `scripts/merge-feature.sh`. With the `release-tag` module, releases go out by tag.
5. **Put it on the server.** On the server: clone the project, log Claude Code in, list the project in
   `~/.config/dark-factory/projects`, then ask Claude Code in the canon checkout to "provision the server"
   (`provision-server`). The development session appears in claude.ai and the mobile app under its name and comes
   back after a reboot.
6. **Optional modules**, each with its own `MANIFEST.md`: `feedback-desk` (client chat → On-call → development
   session), `prod-monitor` (production failures reported to the group), `observability`, `feature-pipeline`,
   `release-tag`, `code-audit`. The catalogue a deployed project carries is `.harness/modules.md`.
7. **Watch the fleet.** "Factory status" (`factory-status`) shows every project on the server; the review pass
   reconciles projects with the canon (`scripts/harness-diff.sh` in each project).

## Words used everywhere

| Term | Meaning |
|---|---|
| canon | this repository: methodology (`docs/`) and templates (`templates/`) |
| instance | your private repository: the registry and your own configuration |
| card | a unit of client-visible work on the board |
| queue | `bd` tasks in the project repository: the execution state |
| change | an OpenSpec change: proposal, design, tasks for one feature |
| train `r{N}` | the release number every branch carries (`openspec/CURRENT_TRAIN`, raised by a human) |
| GATE | the steps before any code: process skills, queue and branch, specs, user guide |
| development session | the long-lived Claude Code session of a project on the server |
| On-call session | the session holding the client chat (module `feedback-desk`) |
| stand | the dev environment a human uses to look at a change before accepting it |
| review pass | the regular look back: what broke → a decision in `docs/` → a change in `templates/` → rollout |

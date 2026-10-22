# Getting started

How to go from nothing to one project running its full lifecycle with Claude Code. Read the [README](../README.md)
first for what the factory is; this page gives the steps in order.

**Only want the fences?** The solo path is the plugin alone, in your project:

```
/plugin marketplace add ruslantrachuk/dark-factory
/plugin install dark-factory@dark-factory
/dark-factory:init
```

It adds the guard hook, the quota guard, the merge script and a pre-push test gate
([plugins/dark-factory/README.md](../plugins/dark-factory/README.md)); [a first session](#a-first-session-illustrative)
below shows what that looks like. The steps further down are the full path: the plugin plus the `base` template and
the modules.

## Who this is for

- You build software with **Claude Code** on a Claude subscription, for yourself or for clients. You want the agent
  to do the middle of the pipeline (code, tests, release preparation) while you keep the edges: what to build,
  acceptance, and "ship it".
- Your code lives on **GitHub**. The default test stack and scripts are **Python**; other stacks work, but then you
  adapt the test pyramid and the gates yourself. The board is **Linear** (the `board` skill). The queue itself is
  `bd` in the repository and works without a board.
- Optional, per module: a **Telegram** group with the client (the On-call session) and **Postgres** in production
  (the monitor).
- The method itself is tool-agnostic; these are the tools the reference implementation is built on. The full list,
  and where each tool is wired in, is the [supported stack](functions.md#supported-stack). To use another tool for
  one function, rewrite what the **Seam** line of that skill or module names.

Not a fit if you need a hosted product, a non-Claude agent, or no human acceptance step at all.

## Words used everywhere

| Term | Meaning |
|---|---|
| canon | this repository: the method (`docs/`) and the templates (`templates/`) |
| instance | your private repository: the registry and your own configuration |
| Product owner, Spec writer, Reviewer, Operator | the four human roles. Product owner: what to build, and the client relationship. Spec writer: turns a request into a spec the agent can execute. Reviewer: accepts, merges and ships. Operator: the server, the sessions and production. One person can hold all four |
| stage | one of the six [lifecycle stages](process.md#the-lifecycle): Requirements, Development, Testing, Release, Monitoring, Support and feedback. The layers in [process.md](process.md) and the phases in [map.md](map.md) are finer cuts of the same pipeline |
| card | a unit of client-visible work on the board |
| `Merged` | the card state after a merge (merged, not yet shipped); the `board` skill uses this name |
| queue | the `bd` tasks in the project repository: the execution state |
| change | an OpenSpec change: proposal, design and tasks for one feature |
| change key | the name every work branch carries: `<type>/<ID>-<slug>` with a tracker, `<type>/<slug>` without; the spec folder is `openspec/changes/<slug>/` |
| GATE | the steps before any code: sizing the work (`size-task`), process skills, queue and branch, standards, user guide |
| development session | the long-lived Claude Code session of a project on the server |
| On-call session | the session that holds the client chat (the `feedback-desk` module) |
| preview environment | a running copy of the app built from the branch, where a human looks at a change before accepting it; the `preview` skill starts it |
| hook | a command Claude Code runs automatically at a set moment (before a tool call, at session start, when you send a prompt) |
| guard hook | the plugin's hook that reads every tool call before it runs and denies the dangerous ones, such as a force push, saying what to do instead |
| fence | a rule held by code (a hook, a script, a setting) rather than by an instruction the agent could ignore; `FENCE_LEVEL` sets how many are on |
| worktree | a second checkout of the same git repository in another folder, on its own branch, so two features can be worked on at once |
| subagent | a helper agent the main session starts for one task; it reports back and ends |
| test pyramid | many fast unit tests at the bottom, fewer integration and API tests above, a few slow browser tests on top |
| quota window | the subscription's usage limits, counted over the last 5 hours and the last 7 days; the quota guard watches both |
| review pass | the regular look back: what broke → a decision in `docs/` → a change in `templates/` → rollout |

## What you need

**To start on a laptop** (steps 1–4 below):

| Tool | For | Install |
|---|---|---|
| Claude Code, logged in | everything | <https://code.claude.com> |
| the dark-factory plugin | the guard hook, the quota guard, the feature pipeline; `base` depends on it | `claude plugin marketplace add ruslantrachuk/dark-factory`, then `claude plugin install dark-factory@dark-factory` |
| `git`, `gh` (logged in, a current release: old distribution packages fail on `gh pr edit`) | branches, PRs, `merge-feature.sh` | <https://cli.github.com> |
| `bd` (beads) | the task queue | <https://github.com/steveyegge/beads> |
| `jq`, Python 3.11 or newer | queue scripts, quota guard, tests | your package manager |
| Superpowers plugin (recommended) | the skills of GATE step 0 | `claude plugin install superpowers@claude-plugins-official` |

The OpenSpec CLI is not required: OpenSpec is used as a folder convention.

**Only for the server and the modules** (steps 5–7):

| Tool | For | Install |
|---|---|---|
| A small Linux server with `tmux` and a systemd user instance (`systemctl --user`) | long-lived sessions (`provision-server`) | any VPS |
| Bun | the On-call and monitor channels (`feedback-desk`, `prod-monitor`) | <https://bun.sh> |
| `uv` | the monitor's own Python environment (`prod-monitor`) | <https://docs.astral.sh/uv/> |

Server provisioning needs Linux with a systemd user instance. macOS is for attended sessions on your own machine,
not for the server.

## Steps

1. **Your instance repository.** Clone this repository (the canon). Create a private repository of your own for the
   instance and copy [registry.example.md](../registry.example.md) into it as `registry.md`. Open Claude Code in the
   canon checkout: the factory skills live in its `.claude/skills/`. Install the dark-factory plugin (the table above);
   `base` relies on it, and the template's `.claude/settings.json` offers it to everyone who opens the project.
2. **Deploy a project.** In Claude Code, say "deploy project `<name>` into `<path>`". The `deploy-project` skill
   shows a dry run of `scripts/deploy-base.sh`, asks the configuration questions one at a time, fills in the
   placeholders, names the modules worth adding and writes the registry row. One question is the fence level:
   `solo`, `standard` (default) or `team` — how strictly the guard hook holds pushes, merges and edits to the fence
   files. Nothing leaves your machine without your "yes". Then turn on GitHub branch protection for main (block force
   pushes, require a pull request; `team` also requires an approval): it is the backstop the hooks cannot be.
3. **First session in the project.** Open Claude Code in the project. The SessionStart hooks print the queue, the
   branch's PR and the latest merges, and the quota; `CLAUDE.md` holds the operating contract. Write the first OpenSpec change for a
   small feature, approve it, run `openspec-to-beads`, and let the session build the first phase.
4. **Merge and ship.** Review the branch (in the preview environment, through the `preview` skill, when there is a
   UI); once CI is green the session runs `scripts/merge-feature.sh <branch>`, which writes the PR description into
   the merge commit. A solo project with no CI workflows yet merges on the local gate
   (the pre-push test command), and the merge commit says `CI: none (local gate)`; `team` refuses this. If CI exists
   but cannot run (for example, Actions is blocked by billing), say so: `--skip-ci "<reason>"` runs the local gate
   instead and marks the merge prominently. With the `release-tag` module,
   releases go out by tag.
5. **Put it on the server.** On the server, clone the project and log Claude Code in. List the project in
   `~/.config/dark-factory/projects`, one checkout path per line (`#` starts a comment):

   ```
   # projects this server runs
   ~/code/my-app
   ~/code/client-portal
   ```

   Then ask Claude Code in the canon checkout to "provision the server" (`provision-server`). The development session
   appears in claude.ai and the mobile app under its name, and comes back after a reboot.
6. **Optional modules**, each with its own `MANIFEST.md`: `feedback-desk` (client chat → On-call → development
   session), `prod-monitor` (production failures reported to the group), `observability`, `feature-pipeline`,
   `release-tag`, `code-audit`. A deployed project carries the module catalogue in `.harness/modules.md`.
7. **Watch the fleet.** "Factory status" (`factory-status`) shows every project on the server. The review pass
   reconciles projects with the canon (`scripts/harness-diff.sh` in each project).

## A first session (illustrative)

A made-up transcript of a first session on a fresh solo project, trimmed to the parts that matter. The wording of
real messages differs.

```
you    > /dark-factory:init
claude > Dry run: CLAUDE.md (append), scripts/merge-feature.sh, .claude/fences.env (solo), .githooks/pre-push … Apply?
you    > yes
you    > Add a --version flag to the CLI.
claude > On branch feat/version-flag: test added, implementation, tests green, committed; draft PR #1 describes it.
claude > Pushing straight to main would be quicker…
guard  ✗ Denied: push to the main branch. Push the feature branch and merge it with scripts/merge-feature.sh.
claude > Pushed feat/version-flag instead; tests are green and I reviewed the diff against the request.
claude > scripts/merge-feature.sh feat/version-flag "Add a --version flag"
script ✓ PR #1 opened · no CI workflows: local gate green · merged (CI: none (local gate)) · main updated
quota  ⚠ 85% of the 5-hour window used: finish the current step, save your work, resets at 17:40.
claude > Wrapping up: the PR description has the next step; nothing is left unsaved.
```

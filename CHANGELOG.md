# Changelog

All notable changes to the dark-factory plugin and canon. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are sequential: `v1`, `v2`, … (tag `v<N>` on main,
plugin version `<N>.0.0`; see [CONTRIBUTING.md](CONTRIBUTING.md#versioning)). A release that breaks a deployed project
has a **Breaking** section with the upgrade steps.

## [Unreleased]

### Added

- **The factory session** (`FLEET_NOTIFY=session` in `~/.config/dark-factory/fleet.env`). Fleet notices — a unit
  failed, a session went down or waits for a login, a worktree on old rules — go into a Claude session with Remote
  Control on the server, "Factory · <host>", which the owner sees in claude.ai: as a message from another session
  while it runs, or opening it with the notice as its first message. It answers questions read-only and names the
  command for the owner. `FLEET_NOTIFY_CMD` and the journal stay as they were.

- **Daily queue review.** A project with a bd store gets `df-<slug>-triage.timer` (`fleet.py provision`): once a
  day `scripts/triage.py` picks the stale tasks without a model (in progress with no change for 3 days, open for 14,
  or named by a merge commit), the product-owner role asks of each "are you sure you need this?" — a task stays only
  with an argument for it — and a review session opens on the server: a Claude session with Remote Control,
  "Queue review · <project> · <date>", seen in claude.ai on any device, no desktop app needed. Its first message is
  the report, which leads with the distance to a clean queue (open against `TRIAGE_LIMIT`, yesterday's count). The
  owner answers there "yes", "except 3 7" or "1 2"; the session runs `triage.py apply`, which closes or defers only
  the numbered tasks of the latest report. The next day's review replaces an unanswered one.
  Upgrading: `fleet.py provision` on the server; optional `TRIAGE_*` lines in `.claude/factory/session.env`.
- **Worktrees on other rules than main** (`fleet.py status`, `/dark-factory:factory-status`). A session reads the
  canon CLAUDE.md, skills, hooks and the plugin pin from its own worktree, so a conversation continued on an old
  branch keeps the old rules — and one cut before the project took the plugin runs with no guard and no quota guard.
  The fleet now checks every session worktree (`.claude/worktrees/`, locked ones included — remote-control locks
  each claude.ai conversation's) against main: no plugin, or `.harness/base-sha` behind main's. The check runs from
  the factory, not from a hook in the worktree, which an old branch would not have. `gc` never removes a locked one.
  `/dark-factory:add base` tells the owner to start new sessions after converting a project.

- **Updates through Copier.** The repository root has a `copier.yml` for the base template, and `deploy-base.sh`
  writes `.copier-answers.yml` next to `.harness/base-sha`. A project moves to a newer release with
  `copier update --vcs-ref v<N>` on a work branch: the canon's changes are applied where the project kept the canon's
  text, and left as conflict markers where it has its own (`.harness/README.md`, "Updating"). Files the project owns
  after setup are never touched; `harness-diff.sh` stays as the report.
  Upgrading: a project already set up updates to this release once by hand (`harness-diff.sh`), then adds
  `.copier-answers.yml` with `_commit: v<this release>` and `_src_path: gh:ruslantrachuk/dark-factory`.

### Fixed

- openspec README: the `SHIPPED.md` paragraph still spoke of a milestone.

## [5] — 2026-10-23

Lessons from moving live projects onto the canon.

### Changed

- **No ROADMAP.md in the method.** What is next lives in the bd queue and `openspec/changes/`, what shipped in the
  merged PRs, `SHIPPED.md` and the release tags; the product direction document stays optional. References removed
  from the canon CLAUDE.md, DOCUMENTATION_STANDARDS, openspec README and skill, ship, size-task, feature-sanity-check,
  the product-owner role and naming.yaml. `/dark-factory:add base` treats an existing ROADMAP as an archive.
  Upgrading: a project's own ROADMAP.md can stay as history; nothing asks to update it.
- **Bash sandbox on Ubuntu 24.04+** (provision-server): AppArmor blocks the nested user namespace bwrap needs, in
  two independent places (a sysctl and the `bwrap-userns-restrict` profile); the skill names the symptom, the owner's
  sudo steps and the undo.
- **Converting a project whose bd export lived in git** (`/dark-factory:add base`): untrack `.beads/*`, drop the
  export script and import hooks — and warn collaborators that their next pull deletes `.beads/config.yaml` and
  `metadata.json` (the store's data stays), with the one-line restore. Own release-train files and night-loop copies
  that read them go too; the feature pipeline comes from the plugin.

## [4] — 2026-10-23

Fixes found on a from-scratch reprovision and reboot of a provisioned server.

### Fixed

- **Fleet and On-call:** `fleet.py` (status, `/dark-factory:factory-status`) and `feedback-desk.sh` no longer inherit
  `TMUX` from the caller. Run from a development session, which sits inside its own `df-<slug>` tmux server, they
  looked for the On-call in that server: status reported a running On-call as down, and `feedback-desk.sh up` started
  it inside the development session's server.
- **Provisioning:** `fleet.py provision` run from a bare environment (`systemd-run`, cron) failed with
  `need claude and tmux in PATH` and left the server without units after a reboot. It now also looks in `~/.local/bin`,
  `~/bin`, `/usr/local/bin`, `/usr/bin`, `/bin` and writes them into the units' PATH.
- **On-call:** at boot the desk unit and its watch timer both ran `feedback-desk.sh up`, and one failed with
  `duplicate session`. `up` now takes a start lock (`flock`, where available) and checks again once it holds it.

## [3] — 2026-10-22

Fixes found on the first reboot of a provisioned server and in a remote-control session.

### Fixed

- **Guard:** a `claude remote-control` session (`CLAUDE_CODE_ENVIRONMENT_KIND=bridge`) is no longer taken for an
  unattended SDK run: its fence changes are asked (the dialog reaches the owner in the Claude app) instead of denied.
  The On-call stays unattended (`DF_UNATTENDED=1`).
- **On-call status:** `feedback-desk.sh status`/`up` and the watch timer count the On-call as running only when its tmux
  session was started with `claude`. After a reboot a tmux session-restore plugin (tmux-continuum) brought back empty
  windows of the same name, and the On-call was reported up while it was down.
- **Fleet:** the development-session tmux servers start with `-f /dev/null`, so the user's tmux configuration (a
  session-restore plugin) does not restore other sessions' windows into them. The fleet watch unit no longer fails
  on every ○ (template drift, quota): it reports by message, not by its exit code.

### Changed

- **Threat model:** an optional sandbox block that closes the script path to the fence files (`sandbox.filesystem.denyWrite`),
  off by default, with its cost.

## [2] — 2026-10-22

Fixes from a pre-release audit (technical reviewers, five user personas, a security review), the README rewritten as a
landing page, and the seams rule: other stacks are adapted at installation.

### Fences stricter

- The guard asks (at `standard` and `team`; denies where nobody can answer) before an edit of the files that control
  the On-call and the release: `scripts/release.sh`, `scripts/feedback-desk.sh`, `.claude/feedback-desk/*`,
  `.github/workflows/release.yml`, `.mcp.json`.
- `release.sh --publish` passes the guard only in the exact CI form `release.sh --publish <tag>`.

### Fixed

- **Release gate** (`release.sh`): `--publish` takes only a `vYYYY.MM.DD.N` tag that exists on origin; the last release
  is read from the remote's release-scheme tags, so a local or off-scheme `v*` tag cannot shorten the checked range;
  the tag lands on exactly the commit the gate checked; acceptance marks are posted after the tag push; an option value
  that starts with `--` is refused.
- **Quota guard**: a cache older than `QUOTA_STALE_MAX` (5 hours) counts as no data; a `bd … update … --claim` is
  seen in any spelling; a plain `git push` of a work branch is a saving command at the ceiling.
- **Skills** `board` and `ship` no longer create tags or GitHub releases; they use the one `release.sh` cut.
- **Kit**: `init_kit.py --merge-flag squash` works as the skill calls it; the main branch is found without
  `origin/HEAD` (`master` repositories); a `core.hooksPath` pointing elsewhere is a loud warning; `deploy-base.sh`
  names the fence blocks a skipped `settings.json` lacks and changes the mode only of what it copied; `add base`
  prints the branch-protection commands for the owner and only verifies them; `merge-feature.sh` refuses a reused
  branch name instead of reporting an older merged PR as success; the solo pre-push skips branch deletes; the base
  pre-push warns when its `CODE_PATTERNS` match no tracked file; `bd prime` is skipped when `bd` is missing; the roles
  use `model: opus`.
- **Fleet and monitor**: two checkouts with the same directory name are refused; `unprovision --project` finds the
  units after the project's line is removed; a malformed `session.env` fails only its project; a failed notification
  is sent again; `prod-monitor.sh status` always prints a line; a failing `crontab -l` never overwrites the crontab.

### Changed

- **Seams are adapted at installation**: `/dark-factory:add` compares every seam of a module with the project and, on
  the owner's yes, rewrites those files in place, recording them as the project's deviations. The test stack (Python
  with an `app/` layout) is declared a seam; incomplete Seam lines are completed; what is not covered is listed in
  `docs/levels.md`.
- **README** rewritten: who it is for, the parts that work alone, honest limits before the lifecycle.
- Deployed skills link to the canon docs by URL; managed-settings interaction documented; the threat model says plainly
  that branch protection and the tag ruleset are the real closure.

### Upgrading a project

Move the pin in `.claude/settings.json` from `"ref": "v1"` to `"ref": "v2"`; the guard and the quota guard fixes come
with the plugin. Files copied into the project (`release.sh`, `merge-feature.sh`, the git hooks, the skills) are not
replaced by the update: compare them with `scripts/harness-diff.sh` (base) or with the plugin's templates (the solo
kit) and take the fixes you want, the `release.sh` ones above all.

## [1] — 2026-10-22

The first release: the method (`docs/`) and the Claude Code plugin that carries everything a project needs.

### The lifecycle

- **Intake**: requests arrive from a tracker or from the client's Telegram group through the On-call agent; each
  becomes a board card and a change. `size-task` sizes new work (trivial, small, large) and proposes the branch name
  and phases; `wsjf` ranks the queue.
- **Spec**: every change lives in `openspec/changes/<slug>/` (a small one is a proposal and tasks). Branch
  `<type>/<ID>-<slug>`; the `bd` queue is one local store per project, outside git.
- **Development**: roles as plugin agents (`tech-lead`, `product-owner`, `reviewer`), a project overrides one with
  `.claude/agents/<name>.md`; the feature-pipeline workflows (`feature-auto`, `feature-core`, `feature-lite`,
  `/dark-factory:feature`) for unattended runs, with an agent-call cap and per-role models.
- **Review and merge**: the PR description (`## Done`, `## Decisions`, `## Open questions`) is the record of the work;
  `merge-feature.sh` refuses a PR without it, merges after green CI and writes it into the merge commit
  (`--skip-ci "<reason>"` runs the local gate where Actions cannot run; refused at `team`).
- **Dev stand and acceptance**: a merge puts a feature on the dev stand (the environment that runs `main`); the
  requester accepts it there (label `accepted`, comment `accepted by <who>, <link or "permission dialog">`).
- **Release**: production is built only from a `vYYYY.MM.DD.N` tag cut by `release.sh`, which ships all of `main`
  since the last tag and refuses while a merge lacks acceptance (`--owner-accepts`, `--include-unaccepted "<who
  allowed>"`, `--list-unaccepted`).
- **Monitoring and support**: the prod monitor watches production and reports through On-call; On-call `accept` and
  `release` subcommands check the sender against the PR's requester and `DESK_OWNER_IDS`.

### The fences

- **Guard** (PreToolUse hook): no force push, no push to main, no hook bypass, no merge without a named human
  acceptance; the fences and the installed plugin are protected at every level. Release tags and acceptance marks are
  asked ("Yes = you accept it"); the On-call may run only `feedback-desk.sh accept|release`.
- **Quota guard**: a Claude subscription ceiling that stops work before it hits the limit and lets the save steps
  through; usage is refreshed in the background. A statusline shows the quota and the fence level.
- **Levels** 0 to 4 (`/dark-factory:level`): fences and tools grow with the project; a grant is bound to the typed
  target, used once, and a lowered level counts only once merged into `main`.
- [SECURITY.md](SECURITY.md) and a [threat model](docs/threat-model.md); release hardening (tag ruleset on `v*`,
  read-only CI tokens, actions pinned to commit SHAs).

### The factory over projects

- `/dark-factory:init` (the solo starter kit), `/dark-factory:add base` (the full harness) and
  `/dark-factory:add factory` (the skeleton of your own factory repository, see
  [docs/your-factory.md](docs/your-factory.md)).
- `/dark-factory:provision-server` keeps each project's session and On-call alive through reboots;
  `/dark-factory:factory-status` shows sessions, On-call, monitor, quota, queue and each project's lag behind the
  plugin version. `harness-diff.sh` reconciles a project's files with the template.
- Projects pin the plugin to a release (`"ref": "v1"` on the marketplace in `.claude/settings.json`).

### The modules

`/dark-factory:add <module>`: owner steps first, then files, filling in, tests, server units and a status check.

- `base` (with releases by tag when there is production), `on-call` (Telegram feedback desk), `monitor`,
  `release`, `observability`, `code-audit`, `feature-pipeline`.

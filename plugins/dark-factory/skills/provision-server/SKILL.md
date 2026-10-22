---
name: provision-server
description: Set up the server the factory runs on so that every project's development session and On-call session start by themselves and come back after a reboot. Use on "provision the server", "set up the VPS", "sessions did not come back after a reboot", "add project X to the server".
disable-model-invocation: true
---

# Skill `provision-server` — the server the projects run on

> Factory operations (control plane, not copied into a project). The mechanics are the plugin's
> `fleet.py` (below `fleet.py` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py"`); the skill is checks, questions and the report.
> It writes systemd units and enables lingering, so it runs only when a human calls it (`/dark-factory:provision-server`).
> It works from any directory: nothing of this repository is needed on the server, only the installed plugin.

**Platform: Linux with a systemd user instance only** (`systemctl --user` works). On macOS, or any machine without
one, nothing is provisioned — `fleet.py provision` refuses: the sessions there are attended (started by hand,
gone after a restart), and this skill does not apply.

What a provisioned server runs, per project (user systemd units, started at boot through lingering):

| Unit | What it starts | Attach |
|---|---|---|
| `df-<slug>-session.service` | `claude remote-control --name "<session name>" --spawn worktree --capacity 3` in the project's main checkout, inside its own tmux server. One session is pre-created in the main checkout; each session opened from claude.ai gets its own git worktree, at most 3 at a time (the CLI default is 32, each spending the shared quota). Restarted if it exits; after 5 failed starts in 30 minutes (expired login, untrusted folder) it stays failed instead of looping | `tmux -L df-<slug> attach` |
| `df-<slug>-desk.service` | `scripts/feedback-desk.sh up` from the main checkout at boot — only for projects with the feedback-desk module | `tmux attach -t <DESK_TMUX>` |
| `df-<slug>-desk-watch.timer` (+ `.service`) | the same idempotent `feedback-desk.sh up` every 5 minutes: brings a crashed On-call session back (the desk unit is a oneshot and is never restarted by systemd) | — |

And once per server:

| Unit | What it does |
|---|---|
| `df-notify@.service` | every unit above has `OnFailure=df-notify@%n.service`: a unit that fails (the session hit its start limit, the On-call `up` failed) sends the owner one line through `fleet.py notify` |
| `df-fleet-watch.timer` (+ `.service`) | `fleet.py status --notify` every 15 minutes: one message when a project's development session, On-call or monitor starts or stops failing — including a login or folder-trust prompt on screen; nothing while the state stays the same (state in `~/.local/state/dark-factory/fleet-watch.json`) |

Notifications go to `FLEET_NOTIFY_CMD` in `~/.config/dark-factory/fleet.env` — a shell command that reads the message on
stdin, for example a `curl` to a Telegram bot of the owner's own (not a client group's bot: the On-call plugin is its
only reader). Without it they go to the journal (`journalctl --user -u 'df-notify@*' -u df-fleet-watch`).

The prod-monitor watchdog lives in cron (`prod-monitor.sh install`) and survives a reboot by itself.
Starting the On-call session from the main checkout also means its role file is the main branch's
`ROLE.md`, not a copy in some development worktree.

## Iron rules

1. **Dry-run first, then write**: `fleet.py provision --dry-run` → show the units and commands → "yes" → the real run.
2. **One owner of a project's sessions.** If a project already runs `claude remote-control` or its On-call
   session by hand (tmux), stop those after the units are up — never two development sessions or two
   On-call sessions for one project (two On-call sessions fight over the chat bot).
3. **Nothing outside the user account** without a "yes": `sudo loginctl enable-linger <user>` is only
   printed when the unprivileged call fails.

## Steps

1. **Prerequisites on the server**: Linux, `claude` logged in (the account whose subscription the sessions use),
   `tmux`, `systemctl --user` working (a user systemd instance), each project cloned and set up (`/dark-factory:add base`),
   and each checkout **trusted** — run `claude` there once by hand and accept the folder-trust question: an unattended
   `remote-control` cannot answer it (`status` then shows "waiting at a login or folder-trust prompt").
   For the On-call session: `scripts/feedback-desk.sh check` is green in the project.
2. **Projects of this server**: `~/.config/dark-factory/projects`, one checkout path per line.
   Ask the human which projects run here; create or update the file. (Without it the registry's
   Repository paths are used — only correct if the registry lists this machine's paths.)
3. **Session names** (optional): `<project>/.claude/factory/session.env` with `SESSION_NAME="…"` (what
   ListAgents, SendMessage and claude.ai show; the On-call config's `DESK_DEV_SESSION` must match it) and
   `SESSION_ARGS="…"`. The file is local to the server: add it to `.git/info/exclude` or commit it if the whole
   team uses the same name. `SESSION_ARGS` is an **allowlist**, because the project-local value lands in a systemd
   `ExecStart`: only `--permission-mode default|acceptEdits|plan|auto`, `--spawn same-dir|worktree|session`
   (default `worktree`) and `--capacity 1..8` (default 3; not with `--spawn session`). Anything else —
   `bypassPermissions`, `dontAsk`, any `--dangerously-*` flag, any other option — and `provision` refuses that project
   with the reason and goes on with the others. `remote-control` has no `--model` option, so the model is not set here.
4. **Where the owner hears about failures**: ask whether to set `FLEET_NOTIFY_CMD` in
   `~/.config/dark-factory/fleet.env` (mode 0600 if it holds a token; the owner writes the token, not the agent). Test it:
   `fleet.py notify test.service` — one line arrives.
5. `fleet.py provision --dry-run` → show → "yes" → `fleet.py provision`.
6. **Stop the hand-started copies** (rule 2), then check: `fleet.py status` — every development session
   and On-call session ●. Open claude.ai: the sessions are listed under their names.
7. **Reboot test** when the human agrees: `sudo reboot`, then `fleet.py status` again.

Remove a project: delete its line, `fleet.py unprovision --project <name>`.
Stop the On-call session on purpose: `systemctl --user stop df-<slug>-desk-watch.timer df-<slug>-desk` — with only
`feedback-desk.sh down` the watch timer starts it again within 5 minutes.

**Worktrees pile up**: every claude.ai session gets one and nothing removes it. `fleet.py status` lists a project's
stale worktrees (clean with the branch merged into origin's default branch, or no commit for 14 days —
`--stale-days N`). `fleet.py gc` shows what would go; `fleet.py gc --apply` after a "yes" removes only
clean worktrees whose branch is merged, never a dirty, locked, detached one or one a running process has as its
working directory. Merged means an ancestor of the remote-tracking default branch — fetch first; a project that
squash-merges never has merged branches by that test, so its worktrees are only reported, removed by hand.

## Known limits

- The units name `fleet.py` by absolute path, and an installed plugin lives in a per-version directory: after
  `/plugin update` run this skill again (`provision` is idempotent and rewrites the units). `fleet.py status` shows
  "units point at another copy" until you do.
- The On-call login expires every few days when it uses an interactive login; `status` shows "asks to log in" and the
  fleet watch tells the owner. Attach and run `/login`. The login and folder-trust detection reads the last lines of
  the tmux screen — a best-effort hint that can miss a reworded prompt, not a check.
- The fleet watch reports changes, not states: a problem that was already there at the first run is reported once,
  then not again until it is fixed and comes back.
- A development session that hit the start limit stays `failed`: fix the cause (`journalctl --user -u
  df-<slug>-session`), then `systemctl --user reset-failed df-<slug>-session && systemctl --user start df-<slug>-session`.
- A dead server is not detected from the server itself; watch it from outside (an uptime check on the
  production health endpoint, see the observability module).

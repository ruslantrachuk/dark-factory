---
name: provision-server
description: Set up the server the factory runs on so that every project's development session and On-call session start by themselves and come back after a reboot. Use on "provision the server", "set up the VPS", "sessions did not come back after a reboot", "add project X to the server".
---

# Skill `provision-server` — the server the projects run on

> Factory operations (control plane, not copied into the template). The mechanics are
> [scripts/fleet.py](../../../scripts/fleet.py); the skill is checks, questions and the report.

**Platform: Linux with a systemd user instance only** (`systemctl --user` works). On macOS, or any machine without
one, nothing is provisioned — `fleet.py provision` refuses: the sessions there are attended (started by hand,
gone after a restart), and this skill does not apply.

What a provisioned server runs, per project (user systemd units, started at boot through lingering):

| Unit | What it starts | Attach |
|---|---|---|
| `df-<slug>-session.service` | `claude remote-control --name "<session name>" --spawn worktree` in the project's main checkout, inside its own tmux server. One session is pre-created in the main checkout; each session opened from claude.ai gets its own git worktree. Restarted if it exits; after 5 failed starts in 30 minutes (expired login, untrusted folder) it stays failed instead of looping | `tmux -L df-<slug> attach` |
| `df-<slug>-desk.service` | `scripts/feedback-desk.sh up` from the main checkout at boot — only for projects with the feedback-desk module | `tmux attach -t <DESK_TMUX>` |
| `df-<slug>-desk-watch.timer` (+ `.service`) | the same idempotent `feedback-desk.sh up` every 5 minutes: brings a crashed On-call session back (the desk unit is a oneshot and is never restarted by systemd) | — |

The prod-monitor watchdog lives in cron (`prod-monitor.sh install`) and survives a reboot by itself.
Starting the On-call session from the main checkout also means its role file is the main branch's
`ROLE.md`, not a copy in some development worktree.

## Iron rules

1. **Dry-run first, then write**: `scripts/fleet.py provision --dry-run` → show the units and commands → "yes" → the real run.
2. **One owner of a project's sessions.** If a project already runs `claude remote-control` or its On-call
   session by hand (tmux), stop those after the units are up — never two development sessions or two
   On-call sessions for one project (two On-call sessions fight over the chat bot).
3. **Nothing outside the user account** without a "yes": `sudo loginctl enable-linger <user>` is only
   printed when the unprivileged call fails.

## Steps

1. **Prerequisites on the server**: Linux, `claude` logged in (the account whose subscription the sessions use),
   `tmux`, `systemctl --user` working (a user systemd instance), each project cloned and deployed from the template,
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
   `ExecStart`: only `--permission-mode default|acceptEdits|plan|auto` and `--spawn same-dir|worktree|session`
   (default `worktree`). Anything else — `bypassPermissions`, `dontAsk`, any `--dangerously-*` flag, any other option —
   and `provision` refuses that project with the reason and goes on with the others. `remote-control` has no
   `--model` option, so the model is not set here.
4. `scripts/fleet.py provision --dry-run` → show → "yes" → `scripts/fleet.py provision`.
5. **Stop the hand-started copies** (rule 2), then check: `scripts/fleet.py status` — every development session
   and On-call session ●. Open claude.ai: the sessions are listed under their names.
6. **Reboot test** when the human agrees: `sudo reboot`, then `scripts/fleet.py status` again.

Remove a project: delete its line, `scripts/fleet.py unprovision --project <name>`.
Stop the On-call session on purpose: `systemctl --user stop df-<slug>-desk-watch.timer df-<slug>-desk` — with only
`feedback-desk.sh down` the watch timer starts it again within 5 minutes.

## Known limits

- The On-call login expires every few days when it uses an interactive login; `status` shows "asks to log in".
  Attach and run `/login`. The login and folder-trust detection reads the last lines of the tmux screen — a
  best-effort hint that can miss a reworded prompt, not a check.
- A development session that hit the start limit stays `failed`: fix the cause (`journalctl --user -u
  df-<slug>-session`), then `systemctl --user reset-failed df-<slug>-session && systemctl --user start df-<slug>-session`.
- A dead server is not detected from the server itself; watch it from outside (an uptime check on the
  production health endpoint, see the observability module).

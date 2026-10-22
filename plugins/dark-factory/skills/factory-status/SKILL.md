---
name: factory-status
description: One read-only status of every project on this server — development session, On-call session and its login, production monitor watchdog, subscription quota, ready queue, lag behind the template. Use on "status", "factory status", "how are the projects", "is the monitor alive", "what is in the queue".
---

# Skill `factory-status` — how every project is doing

> Factory operations (control plane). The mechanics are the plugin's `scripts/fleet.py status`;
> the projects are those of this server (`~/.config/dark-factory/projects`, see `/dark-factory:provision-server`).
> Session checks assume a Linux server provisioned with systemd user units; on macOS (attended sessions) the
> development session reads "not provisioned" by design.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py" status` (add `--project <name>` for one project) and answer with its output as one
message, no preamble:

```
Factory status · <time UTC>

<N> of <M> projects need attention

● subscription quota — <5h and 7d, reset times>

<project>
  ● development session — active — "<name>"
  ● On-call — running
  ● prod monitor — watchdog and channel fine
  ● queue — ready: <N>
  ○ template — template v1, the plugin is at v2 (harness-diff.sh)
  ○ worktrees — <N>; <M> clean and merged (fleet.py gc --project <slug>)
```

● is fine, ○ needs attention; a check that does not apply to the project (no module) is not shown.
Under the block, for each ○ one line with the next action:

| ○ | Next action |
|---|---|
| development session not provisioned / inactive | `/dark-factory:provision-server`; `journalctl --user -u df-<slug>-session` |
| development session failed (start limit) | fix the cause from the journal, then `systemctl --user reset-failed df-<slug>-session && systemctl --user start df-<slug>-session` |
| development session waiting at a login or folder-trust prompt | `tmux -L df-<slug> attach` and answer it (`/login`, or trust the folder) |
| On-call not running | `scripts/feedback-desk.sh up` in the project (or `systemctl --user restart df-<slug>-desk`) |
| On-call asks to log in | attach to its tmux session and run `/login` (the screen check is a best-effort hint) |
| prod monitor ✗ / watchdog silent | `scripts/ops/prod_monitor/prod-monitor.sh status` in the project |
| quota ≥ 80% | new work is stopped by the quota guard until the reset shown |
| template behind | review pass: `scripts/harness-diff.sh` in the project |
| worktrees: clean and merged | `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py" gc --project <slug>` (dry run), then `--apply` after the human's yes |
| worktrees: no commits for N days | ask the human — abandoned work or a long branch; nothing removes those automatically |

Read-only: restart, edit, remove or claim nothing — do not run `gc --apply` or `status --notify` from this skill (the
fleet watch timer runs `--notify` and keeps its own state).

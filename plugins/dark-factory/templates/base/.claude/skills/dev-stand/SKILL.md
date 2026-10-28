---
name: dev-stand
description: Start, check, update and shut down the dev stand of <project> - the environment that runs main, where a human looks at features and accepts them. Use for "put it on the dev stand", "show me", "start the app", "can I take a look", "update the stand", "shut the stand down", and before asking anyone to accept a feature.
---

# Skill `dev-stand` — the dev stand in one procedure

The dev stand runs the **main branch**. A merge into main puts a feature there; a human looks at it and accepts it
there (the owner says "release", or the On-call asks "ship?" and marks the PR `accepted`, see
[docs/layers/acceptance.md](https://github.com/ruslantrachuk/dark-factory/blob/main/docs/layers/acceptance.md)). Production is a separate step: a tag and the `release` branch. Per-branch previews are
not part of the process; a project may still start one by hand under the same rules.

> A skeleton from the dark-factory canon: the rules and their order are generic (drawn from the
> dev-stand skills of several projects). The project fills in the `<…>` sections
> **from a live run**, not from memory. Once a run works, write it down here as commands, not prose.

## Dev stand rules (generic, do not change)

1. **Detached, so it outlives the session:** `setsid nohup … >/tmp/<project>_<component>.log 2>&1 </dev/null & disown`. Not as a Bash-tool background job: that would die with the session. `setsid` keeps a `pkill` of the old process from killing your shell.
2. **Do not kill someone else's process.** Before starting, check what is already running and whose it is: `ss -ltn` and `pgrep -af "<stack processes>"`. Kill only your own processes, with an exact pattern (put the port in the `pkill -f` pattern).
3. **Bind the database, Redis and service ports to `127.0.0.1` only.** Outside access goes only through an authenticated tunnel (Tailscale Serve, cloudflared). An open `0.0.0.0:5432` with a default password is how a database gets taken over by a ransomware bot.
4. **Do not read secrets:** load the environment with `set -a; . .env; set +a` inside the same command; log external API calls without tokens.
5. **The stand serves the main checkout** (dev mode: `--reload`, vite), not a built image, and follows main after each merge; otherwise "the changes aren't visible". On a provisioned server the server updates it, not a session: `scripts/stand-update.sh` (below) is run by `df-<slug>-stand` on every new commit of main — a session works in its own worktree and may not move the main checkout. If the stand is ever started from another worktree, set the code path explicitly (`PYTHONPATH=<wt>/src` or equivalent).
6. **An explicit database.** Pass the stand's connection string explicitly in the start command; tests and the stand never point at production.
7. **Background jobs** (scheduler, queues, mailings) that have been idle can send everything that piled up to real people at once. Before starting them, check what is overdue (`<project query>`) and decide with the owner.
8. **Restart a stand that a person or a live bot is using only on the owner's explicit "yes".**
9. **Smoke-test before saying "take a look":** backend health, the same answer through the frontend/proxy, one real route.
10. **Clean up after a temporary run (a hand-started preview):** your processes, the tunnel, seeded data, demo edits. Leave things as you found them.

## Topology (fill in from a live run)

| Component | Where | Note |
|---|---|---|
| stand DB | `<DSN, port>` | `<what data; how it differs from the test DB>` |
| backend | `<command, 127.0.0.1:port>` | `<--reload>` |
| frontend | `<command, 127.0.0.1:port>` | `<proxy to the backend>` |
| outside access | `<tunnel URL>` | `<Tailscale Serve / cloudflared; how to check the route>` |
| background jobs | `<worker, beat, poller>` | `<what they send outside>` |

## Start

```bash
# 0. what is already running
ss -ltn | grep -E '<ports>' ; pgrep -af '<processes>'
# 1. dependencies (DB etc.) are alive
<command>
# 2. backend detached
<setsid nohup env … <command> >/tmp/<project>_api.log 2>&1 </dev/null & disown>
# 3. frontend detached
<…>
# 4. background jobs — only after rule 7
<…>
```

## Smoke

```bash
<curl backend health>
<curl health through the frontend/proxy>
<curl a real route: 200, or 401 without login = alive>
```

## Update after a merge

The server does it (`/dark-factory:provision-server` installs `df-<slug>-stand` once this script exists): every
minute it checks origin's main; on a new commit it moves the main checkout there — fast-forward when the checkout is
on `main`, detached otherwise; never when it has uncommitted changes or sits on another branch — and runs
`scripts/stand-update.sh` from it, with `STAND_SHA` set. Write the script from the Start and Smoke steps above,
once they work by hand: no `git` in it (the checkout is already moved), no background jobs unless rule 7 allows them
unattended, exit non-zero when the smoke fails.

```bash
#!/usr/bin/env bash
# scripts/stand-update.sh — the dev stand on the commit the main checkout is on now (run by df-<slug>-stand)
set -euo pipefail
cd "$(dirname "$0")/.."
<dependencies up; migrations>
<build>
pkill -f '<exact pattern of the backend with its port>' || true
<setsid nohup env … <backend command> >/tmp/<project>_api.log 2>&1 </dev/null & disown>
<wait until it listens>
<smoke from the section above; exit 1 when it fails>
```

From a session, "update the stand" means: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py" status --project <slug>`
shows `dev stand — updated to <the merge commit>`, then the smoke. A failed update is in
`journalctl --user -u df-<slug>-stand`; the fix goes to main as a new commit, which the stand tries next. Without a
provisioned server (a Mac), update by hand: `git -C <main checkout> pull --ff-only && scripts/stand-update.sh`.

## Stands on the owner's status

`.claude/factory/stands.json` in the main checkout on the server lists the project's stands for the owner's status page
— the main one and any other kept running (a fast one from a worktree). It describes this server
(ports, tunnels, addresses), so it is not in git: write it when a stand starts to be kept running, edit it when one
goes away; the next feed picks it up. For each stand the status feed shows whether it answers, its link and where its
checkout is against main. No file, no stands shown.

```json
[{"name": "main", "port": <port>, "health": "<health route>", "checkout": ".", "tunnel": "<cloudflared container>"},
 {"name": "fast", "port": <port>, "health": "<health route>", "checkout": ".claude/worktrees/<worktree>",
  "url": "https://<fixed address>"}]
```

`checkout` is relative to the project and stays inside it; `url` (https) or `tunnel` (the container of a cloudflared
quick tunnel, whose address is read from its log) gives the link.

## Hand it to the human

Link `<URL>` → `<how to log in: stand account>` → the right screen. Say exactly what to look at, as one list taken from the task's acceptance criteria.

## Stop and clean up

```bash
pkill -f '<exact pattern of your backend with its port>'
pkill -f '<exact pattern of your frontend with its port>'
<shut down your tunnel, delete seeded data, revert demo edits>
```
Check that things are back to normal: `<what should respond after cleanup>`.

## If something is wrong

- the backend is silent → `tail -20 /tmp/<project>_api.log` (migrations, secret, port taken)
- no data → the stand points at the wrong database (rule 6)
- changes aren't visible → not in dev mode, or code from another checkout (rule 5); on a server: `fleet.py status`
  says why `df-<slug>-stand` did not update (failed, uncommitted changes, another branch)
- the external link does not open → the tunnel route points at the wrong port
- `<project-specific cases>`

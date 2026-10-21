---
name: stand
description: Bring up, check and tear down the dev stand of <project> so a human can see the changes live. Use for "show it on the stand", "bring up the stand", "run the app", "can I take a look", "tear down the stand", and before accepting a feature with a UI.
---

# Skill `stand` — the dev stand in one procedure

> Skeleton of the dark factory canon: the rules and order are generic (derived from independent
> stand skills of several projects); sections with `<…>` are
> filled in by the project **from a live run**, not from memory. Captured a run that
> worked — write it down here as commands, not prose.

## Stand rules (generic, do not change)

1. **Detached and survives the session:** `setsid nohup … >/tmp/<project>_<component>.log 2>&1 </dev/null & disown`. Not as a background job of the Bash tool — the stand will die with the session; `setsid` — so that `pkill` of the old process does not kill your shell.
2. **Do not kill someone else's stand.** Before starting: `ss -ltn` and `pgrep -af "<stack processes>"` — what is already taken and whose it is. Kill only your own processes with an exact pattern (the port in the `pkill -f` pattern).
3. **DB, Redis and service ports — only `127.0.0.1`.** Outside access — only through a tunnel with authorization (Tailscale Serve, cloudflared). An open `0.0.0.0:5432` with a default password is how a database gets taken over by a ransomware bot.
4. **Do not read secrets:** pick up the environment with `set -a; . .env; set +a` in the same command; print external API calls without tokens.
5. **The stand shows the working tree** (dev mode: `--reload`, vite), not a built image — otherwise "the changes aren't visible". From a worktree — specify the code path explicitly (`PYTHONPATH=<wt>/src` or equivalent), otherwise the main checkout's code will start.
6. **An explicit database.** The stand's connection string is passed explicitly in the start command; tests and the stand never point at prod.
7. **The stand's background jobs** (scheduler, queues, mailings) after idle time can send everything accumulated to real people at once — before starting, check what is overdue (`<project query>`) and decide with the owner.
8. **Restarting a stand that a live person or a live bot is looking at — only on the owner's explicit "yes".**
9. **A smoke before "take a look"** is mandatory: backend health, the same answer through the frontend/proxy, one substantive route.
10. **Clean up after yourself** for a temporary stand: your processes, the tunnel, seeded data, demo edits — and return to the baseline state.

## Topology (fill in from a live run)

| Component | Where | Note |
|---|---|---|
| stand DB | `<DSN, port>` | `<what data; how it differs from the test DB>` |
| backend | `<command, 127.0.0.1:port>` | `<--reload>` |
| frontend | `<command, 127.0.0.1:port>` | `<proxy to the backend>` |
| outside access | `<tunnel URL>` | `<Tailscale Serve / cloudflared; how to check the route>` |
| background jobs | `<worker, beat, poller>` | `<what they send outside>` |

## Bring up

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
<curl a substantive route: 200, or 401 without login = alive>
```

## Hand it to the human

Link `<URL>` → `<how to log in: stand account>` → the right screen. What exactly to look at — one list from the task's acceptance criteria.

## Stop and clean up

```bash
pkill -f '<exact pattern of your backend with its port>'
pkill -f '<exact pattern of your frontend with its port>'
<shut down your tunnel, delete seeded data, revert demo edits>
```
Check the baseline state: `<what should respond after cleanup>`.

## If something is wrong

- the backend is silent → `tail -20 /tmp/<project>_api.log` (migrations, secret, port taken)
- data is empty → the stand points at the wrong DB (rule 6)
- changes aren't visible → not in dev mode, or code from the main checkout instead of the worktree (rule 5)
- the external link does not open → the tunnel route points at the wrong port
- `<project-specific cases>`

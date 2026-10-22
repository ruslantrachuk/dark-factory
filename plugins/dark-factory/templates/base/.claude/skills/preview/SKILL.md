---
name: preview
description: Start, check and shut down the preview environment of <project> so a human can see the changes live. Use for "show me a preview", "start the preview", "run the app", "can I take a look", "shut the preview down", and before accepting a feature with a UI.
---

# Skill `preview` — the preview environment in one procedure

> A skeleton from the dark-factory canon: the rules and their order are generic (drawn from the
> preview skills of several projects). The project fills in the `<…>` sections
> **from a live run**, not from memory. Once a run works, write it down here as commands, not prose.

## Preview rules (generic, do not change)

1. **Detached, so it outlives the session:** `setsid nohup … >/tmp/<project>_<component>.log 2>&1 </dev/null & disown`. Not as a Bash-tool background job: that would die with the session. `setsid` keeps a `pkill` of the old process from killing your shell.
2. **Do not kill someone else's preview.** Before starting, check what is already running and whose it is: `ss -ltn` and `pgrep -af "<stack processes>"`. Kill only your own processes, with an exact pattern (put the port in the `pkill -f` pattern).
3. **Bind the database, Redis and service ports to `127.0.0.1` only.** Outside access goes only through an authenticated tunnel (Tailscale Serve, cloudflared). An open `0.0.0.0:5432` with a default password is how a database gets taken over by a ransomware bot.
4. **Do not read secrets:** load the environment with `set -a; . .env; set +a` inside the same command; log external API calls without tokens.
5. **The preview serves the working tree** (dev mode: `--reload`, vite), not a built image; otherwise "the changes aren't visible". From a worktree, set the code path explicitly (`PYTHONPATH=<wt>/src` or equivalent), or the main checkout's code starts instead.
6. **An explicit database.** Pass the preview's connection string explicitly in the start command; tests and the preview never point at production.
7. **Background jobs** (scheduler, queues, mailings) that have been idle can send everything that piled up to real people at once. Before starting them, check what is overdue (`<project query>`) and decide with the owner.
8. **Restart a preview that a person or a live bot is using only on the owner's explicit "yes".**
9. **Smoke-test before saying "take a look":** backend health, the same answer through the frontend/proxy, one real route.
10. **Clean up after a temporary preview:** your processes, the tunnel, seeded data, demo edits. Leave things as you found them.

## Topology (fill in from a live run)

| Component | Where | Note |
|---|---|---|
| preview DB | `<DSN, port>` | `<what data; how it differs from the test DB>` |
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

## Hand it to the human

Link `<URL>` → `<how to log in: preview account>` → the right screen. Say exactly what to look at, as one list taken from the task's acceptance criteria.

## Stop and clean up

```bash
pkill -f '<exact pattern of your backend with its port>'
pkill -f '<exact pattern of your frontend with its port>'
<shut down your tunnel, delete seeded data, revert demo edits>
```
Check that things are back to normal: `<what should respond after cleanup>`.

## If something is wrong

- the backend is silent → `tail -20 /tmp/<project>_api.log` (migrations, secret, port taken)
- no data → the preview points at the wrong database (rule 6)
- changes aren't visible → not in dev mode, or code from the main checkout instead of the worktree (rule 5)
- the external link does not open → the tunnel route points at the wrong port
- `<project-specific cases>`

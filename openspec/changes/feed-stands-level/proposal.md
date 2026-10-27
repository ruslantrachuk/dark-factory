# The status feed shows dev stands, the level, On-call's link and quota resets

## Why

The owner's menu bar app and phone widget get a second layer per project: the details opened from the project's row.
The feed has nothing to put there. A project may run several dev stands — the main one on main, a fast one from a
worktree — and the owner wants to see whether each is up, how current it is and to open it. The project's level on
the ladder (`/dark-factory:level`) and which modules it has are known only to the CLI. The On-call is a session too,
and the owner wants to open it from the app. The quota shows percentages but not when the windows reset.

## What changes

- **`.claude/factory/stands.json`** (a new, optional file in the main checkout on the server, not in git — ports,
  tunnels and addresses describe the server, not the project): `[{name, port, health?, checkout?, url? | tunnel?}]`.
  No file means no stands. Every feed carries `projects[].stands[]`:
  `{name, state: running|stopped, url, ref, sha, behind, ahead, at}`.
  - `state`: `http://127.0.0.1:<port><health>` answers below 500. It is probed in the live feed, at most every
    30 s.
  - `url`: `url` (https only), or the address of a cloudflared quick tunnel read from the log of its container
    `tunnel` (a marked seam).
  - `ref`, `behind`, `ahead`, `at`: the checkout (the project's own or one of its worktrees, never outside it) against
    origin's default branch. `ref` is the branch, or `main` for a detached checkout on main, else the short sha.
- **`projects[].level`**: `{level, name, fence, modules: [{name, installed}], next}`, from `level.detect`; `null` for
  a project that has not opted in.
- **`projects[].oncall.session_url`**: the live session named like the feedback-desk's `DESK_NAME`.
- **`quota.resets`**: `{five_hour, seven_day}` as ISO times, always; `resets_at` (the limiting window when blocked)
  stays.

Schema version stays 2: every field is additive, and an app without them shows nothing for that part.

## Not in this change

- The Mac app's and the phone widget's views (separate changes).
- Starting or stopping a stand from the app.
- A fixed name for the main stand: each project names its stands.

## Acceptance scenarios

- WHEN a project has no `.claude/factory/stands.json` THEN its `stands` is `[]`.
- WHEN a declared stand's health answers THEN `state` is `running` within about 30 s; WHEN the process dies THEN
  `stopped` within about 30 s, without waiting for the next full feed.
- WHEN `.claude/factory/stands.json` is written or edited THEN the next full feed shows it, with no commit or PR.
- WHEN the main checkout is detached on origin/main THEN `ref` is `main`, `behind` 0, `ahead` 0; WHEN main moved on
  THEN `behind` counts the new commits; WHEN a worktree stand is on a branch THEN `ref` is the branch, `ahead` its
  commits.
- WHEN a stand declares `tunnel` THEN `url` is the newest quick-tunnel address in that container's log.
- WHEN the project has the On-call and its session is live THEN `oncall.session_url` is its claude.ai link.

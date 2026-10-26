# The server keeps the dev stand on main

## Why

The dev stand serves a project's main checkout and must follow main after every merge: that is where a human
accepts a feature. The `dev-stand` skill had the session move that checkout (`git -C <main checkout> pull` or
`switch --detach origin/main`) and restart the stand. Since the development session runs in its own worktree
(`-w dev-session`, so that its name survives `/clear`), Claude Code isolates it there and refuses every git command on
the main checkout; the sessions spawned from claude.ai run in worktrees too. No session can update the stand, so after
a merge it stays on the old commit and the feature cannot be accepted.

## What changes

- **A per-project updater on the server.** A project with `scripts/stand-update.sh` gets `df-<slug>-stand.timer`
  (+ `.service`) from `fleet.py provision`. Every minute `fleet.py stand <checkout>` fetches origin; on a new commit of
  its default branch it moves the main checkout there (fast-forward when on `main`, detached otherwise) and runs the
  script (rebuild, migrate, restart, smoke) with `STAND_SHA` set. Without the script there are no units, and stale
  ones are removed.
- **Safe by default.** A checkout with uncommitted changes or on another branch is left alone. The first run on a
  checkout that is already on main only records it, so it does not restart a stand someone may be using. A commit
  whose update failed is not tried every minute: the next commit (or `--retry`) tries again. A fetch failure keeps the
  last state.
- **Visible.** The outcome is a state file; `fleet.py status` shows a `dev stand` line, and the fleet watch tells the
  owner when it starts or stops failing. The unit's exit code stays 0 for a failing project script, so OnFailure
  does not page every minute.
- **The skill follows.** The `dev-stand` template says the server updates the stand, gives a skeleton of
  `scripts/stand-update.sh`, and turns "update the stand" into "check `fleet.py status`, then the smoke".

## Not in this change

- Background jobs (workers, mailings): rule 7 of the skill keeps them a decision; the script starts them only when
  the project decided they may run unattended.
- Per-branch previews.
- Writing any project's script: each project writes its own from a run that works by hand.

## Acceptance scenarios

- WHEN a PR is merged into main of a project with `scripts/stand-update.sh` THEN within about a minute the main
  checkout is on the merge commit and the script ran once.
- WHEN nothing new is on main THEN nothing runs.
- WHEN the script fails THEN `fleet.py status` shows `○ dev stand — update to <sha> failed: <last line>`, the owner
  is told once, and the same commit is not retried every minute; WHEN a new commit lands THEN it is tried.
- WHEN the main checkout has uncommitted changes or is on another branch THEN it is not touched and status says why.
- WHEN the updater is first enabled on a checkout already on main THEN the stand is not restarted.

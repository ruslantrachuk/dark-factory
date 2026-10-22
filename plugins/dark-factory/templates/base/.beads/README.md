# Beads — <project> execution queue (a local store)

The project's execution queue is **beads (`bd`)**: the tasks a feature is built from (created from an
OpenSpec change's `tasks.md`), claimed, noted and closed by the sessions working on them. The board
stays the human-facing facade.

The store is **local to this checkout and outside git**: `.beads/` is gitignored except this file.
Nothing about the queue is committed, exported or merged; git carries code and the record of work
(PR descriptions, merge commits, ADRs), the queue carries the work in progress.

## Set up (once per checkout)

```bash
brew install beads                     # or the release binary; any 1.x
bd init --non-interactive --skip-agents --skip-hooks --role maintainer -p <prefix>
bd ready                               # what is free
```

`--skip-hooks` keeps `core.hooksPath` on `.githooks` (the project hooks), `--skip-agents` keeps bd
from writing its own AGENTS.md/CLAUDE.md. `<prefix>` is the task id prefix only; branch names do not carry
the task id.

## Worktrees share the main checkout's store

Every worktree of the checkout works on the same store, the one in the main checkout's `.beads/`:

- `bd` finds it by itself from a worktree (it resolves the main checkout through git);
- the SessionStart hook `.claude/hooks/env-context.sh` also exports `BEADS_DIR` (the main checkout's
  `.beads`, from `git rev-parse --git-common-dir`) for the session, so every `bd` call of the session
  and of the agents it launches names the store explicitly.

There is one queue per project checkout: no per-worktree copies, no import after a checkout.

## Working cycle

```bash
bd ready                                         # what is free
bd create --title="…" --description="…" --type=task --priority=2
bd update <id> --claim                           # take it
bd update <id> --append-notes="where I stopped"  # the state another session needs
bd close <id> --reason="…"
```

`scripts/merge-feature.sh` closes the branch's task after the merge, finding it by the branch's change key
(`<type>/<ID>-<slug>` with a tracker, `<type>/<slug>` without): a tracker ID matches the task whose
`external_ref` equals it; a slug matches the epic labelled `change:<slug>` and, for `<slug>-p<K>`, its child
labelled `phase:<K>`. Give tasks that `external_ref` or those labels when creating them. When no single task is found,
the script says why and the task is closed by hand. A follow-up found during the work becomes a new task here, not a line in a file.

## Another machine or person

The store is per checkout. A second machine sets up its own store; work that must be visible to other
people goes on the board (the facade), not through a shared queue file. Moving tasks between stores
on purpose: `bd export > tasks.jsonl` on one side, `bd import tasks.jsonl` on the other.

## Settings of this store

- **No Dolt remote** (`bd dolt remote list` → empty) and `sync.remote` unset: bd never pushes on its own.
- A backup is a copy of `.beads/` (or `bd export`), taken by the owner, not by git.

## Links

- Development and tracking cycle — [`../openspec/README.md`](../openspec/README.md)
- The function this store implements — "Feature execution queue" in the dark-factory canon (`docs/functions.md`)
- Beads upstream — [github.com/steveyegge/beads](https://github.com/steveyegge/beads)

# Beads — <project> task tracker (hybrid mode: Dolt engine + JSONL in git)

The project uses **beads (`bd`)** as the main task queue (model A: bd = the queue,
the board/Issues = the facade). Here — how to bring up
the tracker after `git clone`/checkout and how to sync between machines.

## TL;DR for onboarding (after `git clone`)

```bash
# 1. Install beads via Homebrew (the version is not critical, see below)
brew install beads

# 2. Pull tasks from git into the local Dolt store
bd import          # reads .beads/issues.jsonl → local DB

# 3. Check
bd ready           # what is free
```

If `bd import` complains about a missing/empty store, run once
`bd init --non-interactive --skip-agents --skip-hooks --role maintainer`,
then `bd import`.

## Why this way (and not `bd dolt push/pull`)

We deliberately do **NOT** use Dolt federation (`bd dolt push/pull`) to sync between
machines. Reasons:

- **Version fragility.** The Dolt schema is tied to the `bd` version; the Homebrew formula
  gets updated, and different people end up with different versions. This is exactly what broke onboarding.
- **The 1.0.5 bug.** beads release `1.0.5` contains migration `0043`, which "silently and
  irreversibly breaks multi-machine `bd dolt` sync". The authors recommend not using 1.0.5
  for multi-machine setups.
- **Data outside git.** The Dolt store (`embeddeddolt/`) is not committed to git — after a clone
  a colleague would not see any tasks at all.

**Solution (hybrid):** Dolt stays the local engine (the only backend in 1.0.x),
but **the exchange source between machines is `.beads/issues.jsonl`, committed to git**.

| Before (Dolt federation) | Now (git JSONL) |
|---|---|
| `bd dolt push` / `bd dolt pull` | a regular `git push` / `git pull` (together with the code) |
| `bd` version is critical | `bd` version is not critical (JSONL is stable and human-readable) |
| data outside git, a Dolt remote is needed | tasks travel in the repository and are visible immediately |

## Working cycle

**Locally (creating/changing tasks):**
```bash
bd ready                       # what is free
bd create --title="…" --description="…" --type=task --priority=2
bd update <id> --claim
bd close <id> --reason="…"
```
`bd` writes to the local Dolt and auto-exports `.beads/issues.jsonl` (throttle ~60 s).
If the file lags behind — run `scripts/bd-export.sh` by hand.

**Sharing tasks (with the owner's approval — the global no-push rule applies):**
```bash
scripts/bd-export.sh     # make sure the file is up to date
git add .beads/issues.jsonl
git commit -m "chore(beads): update task queue"
git push                              # only on an explicit "push it"
```

Before committing, look at `git diff --stat -- .beads/issues.jsonl`. If the export rewrote
hundreds of lines while you edited a couple of tasks, the `bd` versions on the machines have diverged (the old one
does not write `_type`, and `bd import` rewrites edge authors and comment ids). Do not commit such
a file: restore it (`git restore`) and carry over only your own lines.

**Closing a task on merge:** `scripts/merge-feature.sh` closes the branch's task and
commits a single line into the branch — that task (`scripts/beads-queue-line.sh`).
It does not do a full export: new tasks and edits to other tasks
arrive only via the step above.

**Taking in a colleague's tasks:**
```bash
git pull        # the post-merge hook runs bd import itself if issues.jsonl changed
bd ready
```
> Auto-`bd import` is attached by the `post-merge`/`post-checkout` git hooks (`.githooks/_bd-autoimport.sh`) —
> no manual `bd import` is needed after `git pull`/switching branches. Requires running
> `./scripts/install-git-hooks.sh` once (sets `core.hooksPath=.githooks`). If the hook is not installed,
> import by hand: `bd import`.

## Git worktree: each tree has its own store

Each worktree has its own embedded Dolt store under the same `project_id`. Two recurring
incidents follow from this: the first `bd` in a fresh worktree wipes
`.beads/issues.jsonl`; `bd export` from a worktree silently drops tasks that are not in its store
(a queue missing dozens of tasks can land in the main branch this way).

- Fresh worktree: `bd import .beads/issues.jsonl`, then `bd stats` — the number of tasks must
  match `wc -l .beads/issues.jsonl`.
- Leaking this outward is blocked by the `.githooks/pre-commit` hook: `scripts/bd-queue-guard.sh` restores
  missing records from HEAD, `scripts/bd-export.sh --normalize` keeps a stable order.
  Deliberate task deletion — `BD_QUEUE_ALLOW_DROP=1 git commit …`.
- Export before committing explicitly (`scripts/bd-export.sh`): a claim made after
  the auto-export otherwise does not get into the commit.

## Conflict in `issues.jsonl` on merge/pull

`issues.jsonl` is a **full snapshot** (not append-only), so a line-based git merge
(let alone `merge=union`) corrupts the data: duplicates by `id` or lost tasks.
Resolve **through the store, not as text**:

```bash
git checkout --theirs .beads/issues.jsonl && bd import   # merge the other side's tasks into the store (upsert by id)
scripts/bd-export.sh                                      # rebuild the file deterministically (yours + theirs)
git add .beads/issues.jsonl                               # and continue the merge
```

> ⚠️ **`--theirs` is correct only for `git merge`.** Under `git pull --rebase` the sides
> are inverted: `--theirs` is your commit being replayed, and `--ours` is the incoming
> side. Copying this recipe into a rebase context is **forbidden** — it silently takes your
> version of the file and wipes the other side's tasks. In a rebase, take the other side by explicit ref:
> `git checkout origin/<main> -- .beads/issues.jsonl`.

The local store already contains your tasks; step 1 adds the other side's (upsert by `id`).
Conflict prevention: always export via `scripts/bd-export.sh` (stable
line order) + **one bd task per branch** (minimum concurrent edits of the same task).

## Important settings of this store

- **The Dolt remote is removed** (`bd dolt remote list` → empty) — so that `bd` does not push to git
  behind our back on every write (it violated the "do not push without approval" rule).
- **`sync.remote`** in `config.yaml` is commented out for the same reason.
- **`issues.jsonl` is NOT in `.gitignore`** — this is intentional, see the comment there.

## Links

- Development and tracking cycle — [`../openspec/README.md`](../openspec/README.md)
- Tracking model: bd = the queue, the board/Issues = the facade (model A)
- Beads upstream — [github.com/steveyegge/beads](https://github.com/steveyegge/beads)

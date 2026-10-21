---
name: night-dev
description: Operator loop of the <project> autonomous night — status, queue preflight, starting the night in tmux (night-guard), watching, stopping. Use for "start the night", "what did the night do", "is the queue ready for the night", "night run".
---

# Skill `night-dev` — the night in one command (local night)

> Dark factory `night-local` module, deployed for <project>. Topology: the night runs on the machine where
> the repo lives (a server over ssh or a laptop); there is no relay between machines, git uses an ordinary origin.
> Engine rules — `.claude/workflows/README.md`, protection model — `docs/night-dev-runbook.md` §4.

## Commands (`.claude/skills/night-dev/bin/night-dev`)

| Command | What it does |
|---|---|
| `status` | night tmux session, `*/feat-night-*` branches, in_progress / `night-done` tasks, tail of the last log |
| `preflight` | tools (claude, bd, tmux, timeout, .venv), clean tree, release line, ready tasks (`scale:lite` + "SPEC:") |
| `arm [features] [hours]` | preflight → `tmux new-session night` → `scripts/night-guard.sh` (dead-man switch = hours) |
| `watch` | `tail -f` of the night log (`.night/runs/<stamp>.log`) |
| `stop` | kill the tmux session (the agent dies; the branch stays as is) |

## Iron rules

1. **The night does not merge and does not push.** The boundary is a local commit on branch `r{N}/feat-night-<stamp>-<bd-id>`; the task stays open with the `night-done` label. In the morning a human: review → push → "accepted" → the `ship` skill (`scripts/merge-feature.sh`).
2. **The tier and the spec are set by a human.** `scale:lite` + "SPEC: <path>" in the bd task description. Without them the night honestly returns "nothing to do". Tasks unfit for the night — `night-skip`.
3. **Pilot:** `night-dev arm 1 6` with `PROJ_NIGHT_TOKEN_BUDGET=0` (spending measured outside), under observation (`watch`). The auto/core tiers are off (`pilotLiteOnly`) until lite is green.
4. **No database or external services at night:** the gate is the fast pytest suite (no db/e2e/live) + ruff. The full matrix runs on CI in the morning.
5. Release line — `openspec/CURRENT_TRAIN` or `PROJ_NIGHT_REL`; guessing is forbidden (CLAUDE.md, GATE Step 1).

## Morning (ritual)

`night-dev status` → read the night's devlog entry (assumptions — "what the machine decided for you") → `git diff origin/main...<branch>` → push → "accepted" → ship. Remove the `night-done` label after the merge.

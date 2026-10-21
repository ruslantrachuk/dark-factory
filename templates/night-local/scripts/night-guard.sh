#!/usr/bin/env bash
# night-guard.sh — launcher of the autonomous night for <project> with a guaranteed end (runbook §4).
# Topology: local night on one machine (code and harness on the same machine), started from tmux over ssh.
#
# Wall-clock = dead-man switch: "after N hours the run WILL end", whatever happens.
# On a systemd host the unit (scripts/night-dev.service) provides wall-clock + cgroup kill → timeout is optional there.
#
# NOT started automatically. Before the first run, agree the limits (tasks/budget) with the owner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAX_HOURS="${PROJ_NIGHT_MAX_HOURS:-6}"          # dead-man switch
STAMP="${PROJ_NIGHT_STAMP:-$(date +%Y%m%d-%H%M)}"
MAX_FEATURES="${PROJ_NIGHT_MAX_FEATURES:-1}"    # night volume; pilot = 1
LITE_ONLY="${PROJ_NIGHT_LITE_ONLY:-1}"          # 1 = scale:lite only (auto/core stay off until a green lite)
# Release line: openspec/CURRENT_TRAIN (if present), otherwise PROJ_NIGHT_REL (e.g. r12). Guessing is forbidden (CLAUDE.md, GATE Step 1).
REL="${PROJ_NIGHT_REL:-}"
if [ -z "$REL" ] && [ -f "$ROOT/openspec/CURRENT_TRAIN" ]; then REL="r$(head -1 "$ROOT/openspec/CURRENT_TRAIN" | tr -d 'r[:space:]')"; fi
[ -n "$REL" ] || { echo "night-guard: release line unknown — no openspec/CURRENT_TRAIN and no PROJ_NIGHT_REL. Set PROJ_NIGHT_REL=rNN." >&2; exit 1; }
# Soft token ceiling of the night. Default ~2M per run. PILOT CALIBRATION (runbook §4.7): PROJ_NIGHT_TOKEN_BUDGET=0 →
#   tokenBudget is NOT passed, spending is measured outside (transcript JSONL / console).
TOKEN_BUDGET="${PROJ_NIGHT_TOKEN_BUDGET:-$(( MAX_FEATURES * 2000000 ))}"
if [ "$TOKEN_BUDGET" = "0" ]; then
  BUDGET_ARG=""; TOKEN_BUDGET="null (pilot measurement)"
else
  BUDGET_ARG=",\"tokenBudget\":${TOKEN_BUDGET}"
fi
LITE_ARG=$([ "$LITE_ONLY" = "1" ] && echo ',"pilotLiteOnly":true' || echo ',"pilotLiteOnly":false')

# Non-interactive environment.
export GIT_TERMINAL_PROMPT=0 GIT_EDITOR=true GIT_PAGER=cat CI=1
# Lift the 10-minute wait ceiling for background subagents/workflows in headless `claude -p` (otherwise a long run is cut off mid-Build).
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS="${CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS:-0}"

# Toolchain on PATH (tmux new-session 'bash …' is not a login shell). Everything is guarded.
export PATH="$HOME/.local/bin:$PATH"                                   # claude CLI
command -v bd >/dev/null 2>&1 || export PATH="/usr/local/bin:$HOME/go/bin:$PATH"
[ -x "$ROOT/app/.venv/bin/python" ] || echo "night-guard: ⚠ no $ROOT/app/.venv — the test gate will fail (python -m venv .venv && .venv/bin/pip install -e '.[dev]')" >&2

command -v claude >/dev/null 2>&1 || { echo "night-guard: claude is not on PATH (looked in ~/.local/bin). Check the installation/login." >&2; exit 1; }
command -v bd >/dev/null 2>&1 || { echo "night-guard: bd is not on PATH." >&2; exit 1; }

TIMEOUT_BIN="timeout"; command -v timeout >/dev/null 2>&1 || TIMEOUT_BIN="gtimeout"
command -v "$TIMEOUT_BIN" >/dev/null 2>&1 || { echo "night-guard: no timeout/gtimeout (macOS: brew install coreutils)" >&2; exit 1; }

mkdir -p "$ROOT/.night/runs"
LOG="$ROOT/.night/runs/${STAMP}.log"
echo "night-guard: night start stamp=$STAMP, rel=$REL, dead-man=${MAX_HOURS}h, maxFeaturesPerNight=$MAX_FEATURES, liteOnly=$LITE_ONLY, tokenBudget=$TOKEN_BUDGET, log $LOG"

# --permission-mode auto removes the "Review dynamic workflow before running" gate and auto-approves bash/agent spawning
# without --dangerously-skip-permissions (under root that flag would be refused; the agent never runs as root).
# CRITICAL: run the workflow SYNCHRONOUSLY and WAIT for it — in headless mode the process exits after end_turn and background work dies.
PROMPT="Run the workflow by scriptPath ${ROOT}/.claude/workflows/night-dispatch.ts with args {\"stamp\":\"${STAMP}\",\"maxFeaturesPerNight\":${MAX_FEATURES},\"releaseLine\":\"${REL}\"${BUDGET_ARG}${LITE_ARG},\"stopBeforePR\":true}, SYNCHRONOUSLY (run_in_background: false) — do NOT background it, WAIT for the workflow to finish completely and do NOT end your answer before that, otherwise the run dies together with the headless session. Return the final result. This is an autonomous night run: do NOT call ship or merge-feature.sh, do NOT push."

set +e
( cd "$ROOT" && "$TIMEOUT_BIN" -k 30s "${MAX_HOURS}h" claude -p --permission-mode auto "$PROMPT" ) 2>&1 | tee "$LOG"
code=${PIPESTATUS[0]}
set -e

[ "$code" -eq 124 ] && echo "night-guard: ⚠ dead-man switch fired (${MAX_HOURS}h) — the night was killed by timeout." | tee -a "$LOG"
echo "night-guard: night finished (code $code). In the morning: night-dev status → review branches → \"accepted\" → scripts/merge-feature.sh." | tee -a "$LOG"
exit 0

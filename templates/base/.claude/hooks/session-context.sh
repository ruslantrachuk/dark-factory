#!/usr/bin/env bash
# SessionStart hook "session header": deterministic injection of the opening context
# instead of reading devlog.md by hand — see CLAUDE.md § SESSION LOOP.
# Prints: the branch, the latest devlog entry, the latest merge commits of main.
# No network (local git refs only); works from a clone and from a worktree.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT"

echo "=== Session header (injected by .claude/hooks/session-context.sh) ==="
branch="$(git branch --show-current 2>/dev/null || true)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "Branch: ${branch:-detached} · uncommitted files: ${dirty}"
echo

echo "--- Latest devlog.md entry ---"
if [ -f devlog.md ]; then
  # The devlog is in reverse chronological order: the latest entry is the first ^## after the
  # "Rules" section (if present). Print it up to the next heading.
  entry="$(awk '/^## /{ if (on) exit; if ($0 !~ /^## Rules/) on=1 } on{print}' devlog.md)"
  if [ -n "$entry" ]; then
    printf '%s\n' "$entry" | head -80
    lines="$(printf '%s\n' "$entry" | wc -l | tr -d ' ')"
    if [ "$lines" -gt 80 ]; then
      echo "⚠ the entry is longer than 80 lines (${lines}) — the rest is in devlog.md; the template asks for ≤60"
    fi
  else
    echo "(no entries)"
  fi
else
  echo "(devlog.md not found)"
fi
echo

echo "--- Latest merge commits of main (reconcile with the board) ---"
git log --oneline --merges -5 origin/main 2>/dev/null \
  || git log --oneline --merges -5 main 2>/dev/null \
  || echo "(no data)"
echo "=== End of header; open questions and the next session are in the entry above ==="

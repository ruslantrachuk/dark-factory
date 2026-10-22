#!/usr/bin/env bash
# SessionStart hook "session header": the opening context, injected deterministically
# (CLAUDE.md § SESSION LOOP). The state of work lives in git, in the PR and in the execution queue;
# this hook reads them, nothing else:
#   - the branch and the number of uncommitted files;
#   - the branch's open PR: number, title, description (## Done / ## Decisions / ## Open questions);
#   - the tasks in progress in the execution queue, with their notes;
#   - the latest merges of the main branch (their messages carry the PR descriptions);
#   - on the main branch: the active OpenSpec changes (no SHIPPED.md), most recently touched first;
#   - a pointer to the size-task skill for new work.
# Network (gh) is optional and bounded: offline, no gh, or no login — the header says so and goes on.
# Works from a clone and from a worktree. Always exit 0.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" || exit 0

PR_BODY_LINES=40
NET_TIMEOUT=6

# A bounded run: coreutils `timeout`, else perl's alarm (stock macOS has perl, not timeout).
bounded() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
  else
    "$@"
  fi
}

# The main branch: MAIN_BRANCH from scripts/merge-feature.sh (unless still the <main> placeholder),
# else origin/HEAD, else main — the same source as pre-push and the guard.
main_branch="$(sed -n "s/^MAIN_BRANCH=['\"]\{0,1\}\([^'\"[:space:]]*\).*/\1/p" scripts/merge-feature.sh 2>/dev/null | head -n 1)"
case "$main_branch" in
  ""|*"<"*) main_branch="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"; main_branch="${main_branch#*/}" ;;
esac
main_branch="${main_branch:-main}"

echo "=== Session header (injected by .claude/hooks/session-context.sh) ==="
branch="$(git branch --show-current 2>/dev/null || true)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "Branch: ${branch:-detached} · uncommitted files: ${dirty}"
echo

# --- the branch's PR: the record of this work ---
if [ -n "$branch" ] && [ "$branch" != "$main_branch" ]; then
  echo "--- PR of ${branch} ---"
  if ! command -v gh >/dev/null 2>&1; then
    echo "(gh not installed — PR not read)"
  else
    pr_rc=0
    pr_out="$(bounded "$NET_TIMEOUT" gh pr view "$branch" --json number,title,state,isDraft,body \
      -q '"#\(.number) \(.title) [\(.state | ascii_downcase)\(if .isDraft then ", draft" else "" end)]\n\(.body)"' 2>&1)" || pr_rc=$?
    if [ "$pr_rc" = 0 ]; then
      # Drop HTML comments (the skeleton's hints) and runs of blank lines; keep the first lines.
      shown="$(printf '%s\n' "$pr_out" | tr -d '\r' | awk '
        { line = $0; out = ""
          while (length(line) > 0) {
            if (inc) { i = index(line, "-->"); if (i == 0) { line = ""; break }; line = substr(line, i + 3); inc = 0 }
            else { i = index(line, "<!--"); if (i == 0) { out = out line; break }; out = out substr(line, 1, i - 1); line = substr(line, i + 4); inc = 1 }
          }
          if (out ~ /[^[:space:]]/ || prev ~ /[^[:space:]]/) print out
          prev = out }')"
      printf '%s\n' "$shown" | head -n "$PR_BODY_LINES"
      total="$(printf '%s\n' "$shown" | wc -l | tr -d ' ')"
      [ "$total" -le "$PR_BODY_LINES" ] || echo "… (the rest: gh pr view ${branch} --json body -q .body)"
    elif printf '%s' "$pr_out" | grep -qi 'no pull requests found'; then
      echo "No PR yet. Open a draft PR now (gh pr create --draft) — its description is where this work is recorded."
    else
      echo "(PR not read: gh failed or timed out — offline or not logged in)"
    fi
  fi
  echo
fi

# --- the execution queue: tasks in progress (seam: docs/functions.md "Feature execution queue") ---
if command -v bd >/dev/null 2>&1 && bounded 10 bd where >/dev/null 2>&1; then
  echo "--- Tasks in progress (bd) ---"
  tasks="$(bounded 10 bd list --status in_progress --json 2>/dev/null || true)"
  if [ -n "$tasks" ] && command -v python3 >/dev/null 2>&1; then
    printf '%s' "$tasks" | python3 -c '
import json, sys
try:
    items = json.load(sys.stdin) or []
except ValueError:
    items = None
if items is None:
    print("(could not read the queue)")
elif not items:
    print("(none)")
for t in (items or [])[:10]:
    tid, title, who = t.get("id"), t.get("title"), t.get("assignee")
    print(f"{tid} {title}" + (f" · {who}" if who else ""))
    for line in (t.get("notes") or "").strip().splitlines()[-6:]:
        print("    " + line)
'
  else
    bounded 10 bd list --status in_progress 2>/dev/null | head -n 20 || echo "(could not read the queue)"
  fi
  echo
fi

# --- the history: merges of the main branch ---
echo "--- Latest merges of ${main_branch} (subject = PR title, body = its description) ---"
merges="$(git log --oneline --merges -5 "origin/${main_branch}" 2>/dev/null \
  || git log --oneline --merges -5 "${main_branch}" 2>/dev/null)"
printf '%s\n' "${merges:-(none)}"

# --- on the main branch: what is in flight ---
if [ "$branch" = "$main_branch" ] && [ -d openspec/changes ]; then
  echo
  echo "--- Active OpenSpec changes (no SHIPPED.md; most recently touched first) ---"
  active=""
  now="$(date +%s)"
  for dir in openspec/changes/*/; do
    [ -d "$dir" ] || continue
    [ -f "${dir}SHIPPED.md" ] && continue
    ts="$(git log -1 --format=%ct -- "$dir" 2>/dev/null)"
    active+="${ts:-${now}} ${ts:-new} ${dir%/}"$'\n'
  done
  if [ -n "$active" ]; then
    printf '%s' "$active" | sort -rn | head -n 5 | while read -r _ ts dir; do
      when="not committed yet"
      [ "$ts" = new ] || when="$(git log -1 --format=%cs -- "$dir" 2>/dev/null)"
      echo "${dir#openspec/changes/} (${when})"
    done
  else
    echo "(none)"
  fi
fi
echo
echo "New work (a request: add, fix, make, a new ask): start with the size-task skill — verdict, branch name, spec size — before any code."
echo "=== End of header; continue from the PR's Open questions and the task notes ==="
exit 0

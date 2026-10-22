#!/usr/bin/env bash
# The merge transaction (decision of the "Acceptance" layer).
# Accompanying changes (ROADMAP/SHIPPED, an ADR) travel in the feature branch in the same PR as the
# code — not as a separate commit to main after the merge. In projects where main = auto-deploy,
# every such "tail" commit is an extra prod rebuild.
#
# The record of the work is the PR description, with three sections: `## Done`, `## Decisions`,
# `## Open questions` (a decision that shapes the architecture also gets an ADR; a follow-up is a task
# in the execution queue). The script refuses to merge while a section is missing or empty (HTML
# comments do not count; "none" does) and writes the description into the merge commit message, so
# `git log --merges` of the main branch is the project's history.
#
# The script runs the mechanics, not an LLM: at solo/standard the agent merges itself once CI is
# green and its own review is done; at FENCE_LEVEL=team the PR also needs a GitHub approval. The real
# human gate is the release, a later stage. The guard (guard.py of the dark-factory plugin) denies a
# bare `gh pr merge`, so this script is the one way to merge.
#
# The execution queue is optional: a project without one (the solo kit of /dark-factory:init, or
# no bd on this machine) merges the same way, only the task-closing step is skipped.
#
# For one work branch it does: push → PR (find, or create with an empty description skeleton)
# → PR description check → draft → ready → [team: approval check] → wait for green CI
# → merge (merge commit: subject = the PR title, body = the PR description + trailers)
# → delete the branch on origin → update the main branch → close the branch's task in the
# execution queue (local, nothing is committed).
#
# Usage: scripts/merge-feature.sh <branch> [PR title] [--skip-ci "<reason>"]
#   The PR title (human-readable, no fluff) is required when creating a new PR.
#   --skip-ci "<reason>" — CI cannot run (Actions disabled: billing, limits, a platform incident):
#   the script does not wait for checks, runs the local gate (the pre-push test command) instead,
#   writes a loud "Merged WITHOUT CI" PR comment and a `CI-skipped:` trailer. Refused at FENCE_LEVEL=team.
# No CI at all (no .github/workflows/*.yml|*.yaml at the PR head — e.g. a fresh solo project): at
#   solo/standard the same local gate runs without a reason, with a `CI: none (local gate)` trailer and
#   a PR comment; at team the merge is refused. Workflows present but no checks — the usual wait.
# Red CI / conflict — an honest fail with exit ≠0: the script does NOT fix anything, report to the human.
#
# Fence level (.claude/fences.env, FENCE_LEVEL=solo|standard|team, default standard): at `team`
# a GitHub approval is required (reviewDecision APPROVED); --skip-ci and merging without CI are refused.
#
# Transactionality = idempotency + resumability, not atomicity:
# a merge on GitHub cannot be rolled back. So the contract is: the script is safe
# to RE-RUN — an already merged PR is recognized, completed tail steps are
# skipped, unfinished ones are finished. Any tail failure is accumulated and at the end
# yields a non-zero exit code with a list — no "⚠️ … do it by hand" with exit 0 (principle #7).
#
# The task is closed only AFTER the merge, in the tail: the queue is a local store outside git
# (docs/functions.md "Feature execution queue"), so nothing about it has to ride in the PR.
# The branch is the change key: <type>/<ID>-<slug> with a tracker, <type>/<slug> without one
# (a phase of a spec without sub-cards: <type>/<slug>-p<K>). The task to close is found by it:
#   - tracker ID in the branch → the task whose external_ref equals the ID;
#   - otherwise the epic labelled change:<slug> and, for -p<K>, its child labelled phase:<K>
#     (no phase → the epic itself).
# Exactly one task must match; none or several — close the task by hand (the merge does not fail).
#
# Fill in on deployment: MAIN_BRANCH, MERGE_FLAG; REQUIRE_REVIEW and LOCAL_GATE_CMD if needed.

set -euo pipefail

# Paths below (.claude/fences.env, .githooks/pre-push) are relative: running from a subdirectory
# broke the transaction tail after the merge had already happened.
cd "$(git rev-parse --show-toplevel)"

# The environment may only switch the review requirement ON (team mode for one run), never off.
env_require_review="${MERGE_REQUIRE_REVIEW:-}"

MAIN_BRANCH='<main>'
MERGE_FLAG='<--merge|--squash|--rebase>'   # the project's merge strategy. Recommended: --merge — squash breaks ancestry, git branch --merged and branch cleanup
# Team mode: 1 = refuse to merge unless the PR's reviewDecision is APPROVED. Also on with
# FENCE_LEVEL=team in .claude/fences.env or MERGE_REQUIRE_REVIEW=1 in the environment.
# Off by default: a solo owner cannot approve their own PR (the agent uses the owner's gh login).
REQUIRE_REVIEW=0
# Local gate for --skip-ci and for a repository with no CI. Empty = .githooks/pre-push over the branch range (the same test
# command a push runs). Or a command, e.g. 'cd app && .venv/bin/python -m pytest -q'.
LOCAL_GATE_CMD=''

# How long to wait for checks to APPEAR after a push. All this time `gh pr checks`
# answers "no checks reported" with a non-zero code — i.e. indistinguishable from
# red CI unless you wait for it explicitly.
#
# In practice more than six minutes can pass between the push and the creation of
# a check run, and runs may appear out of order.
# Hence ten minutes: better to wait quietly than to get a false failure
# and run the merge a second time.
CHECKS_APPEAR_TIMEOUT=600
POLL_INTERVAL=10
CI_WATCH_RETRIES=3

usage='Usage: scripts/merge-feature.sh <branch> [PR title] [--skip-ci "<reason>"]'
skip_ci=""
skip_ci_set=""
no_ci=""   # set below when the PR head has no workflow files
print_bd_id=""
positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-ci)
      [ $# -ge 2 ] || { echo "✗ $1 needs a value. ${usage}" >&2; exit 2; }
      skip_ci="$2"; skip_ci_set=1
      shift 2 ;;
    --skip-ci=*) skip_ci="${1#*=}"; skip_ci_set=1; shift ;;
    --print-bd-id) print_bd_id=1; shift ;;   # prints the id of the task found for <branch> and exits
    --) shift; positional+=("$@"); break ;;
    --*) echo "✗ unknown option $1. ${usage}" >&2; exit 2 ;;
    *) positional+=("$1"); shift ;;
  esac
done
branch="${positional[0]:-}"
title="${positional[1]:-}"
[ -n "${branch}" ] || { echo "${usage}" >&2; exit 2; }

# One line, no surrounding blanks: the value goes into a trailer and a comment.
one_line() { printf '%s' "$1" | tr -s '[:space:]' ' ' | sed 's/^ //; s/ $//'; }
skip_ci="$(one_line "${skip_ci}")"

# KEY from .claude/fences.env (KEY=value lines, # comments) — the fence level chosen at deployment.
fence_value() {
  [ -f .claude/fences.env ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*[\"']\{0,1\}\([^\"'#[:space:]]*\).*/\1/p" .claude/fences.env | tail -n 1
}
FENCE_LEVEL="$(fence_value FENCE_LEVEL)"
FENCE_LEVEL="${FENCE_LEVEL:-standard}"
case "${FENCE_LEVEL}" in
  solo|standard|team) ;;
  *) echo "✗ .claude/fences.env: unknown FENCE_LEVEL='${FENCE_LEVEL}' (solo|standard|team) — nothing done" >&2; exit 1 ;;
esac
require_review=0
if [ "${REQUIRE_REVIEW}" = "1" ] || [ "${env_require_review}" = "1" ] || [ "${FENCE_LEVEL}" = "team" ]; then
  require_review=1
fi

# Unfinished tail steps accumulate here; the summary is at the bottom, as one list and an exit code.
tail_fails=()
tail_fail() { tail_fails+=("$1"); echo "  ⚠️ $1"; }

# ── The execution queue (seam: docs/functions.md "Feature execution queue"; implementation —
# the project's local bd store, shared by all worktrees of the checkout) ──
# bd can hang on a database lock: a bounded wait where `timeout` exists (not on stock macOS).
bd_run() {
  if command -v timeout >/dev/null 2>&1; then timeout 60 bd "$@"; else bd "$@"; fi
}
queue_present() { command -v bd >/dev/null 2>&1 && bd_run where >/dev/null 2>&1; }
# ── The change key: work branch <type>/<ID>-<slug> (tracker) or <type>/<slug> ──
WORK_TYPES='feat|fix|ui|refactor|chore|docs'
# The tracker seam: one pattern for a tracker ID in a branch name. To swap the tracker, change this pattern.
TRACKER_ID_RE='[A-Z][A-Z0-9]+-[0-9]+'

tracker_id=""   # the tracker ID in the branch, if any
slug=""         # the spec slug (openspec/changes/<slug>/)
phase=""        # K of a trailing -p<K> (a phase of a spec without sub-cards)
if [[ "${branch}" =~ ^(${WORK_TYPES})/(.+)$ ]]; then
  rest="${BASH_REMATCH[2]}"
  if [[ "${rest}" =~ ^(${TRACKER_ID_RE})-(.+)$ ]]; then
    tracker_id="${BASH_REMATCH[1]}"
  else
    slug="${rest}"
    if [[ "${slug}" =~ ^(.+)-p([0-9]+)$ ]]; then
      slug="${BASH_REMATCH[1]}"
      phase="${BASH_REMATCH[2]}"
    fi
  fi
fi

# The task to close: sets bd_id (exactly one match) or bd_why (what to tell the human).
# bd lists hide closed tasks without --all and stop at 50 without -n 0; external_ref is not
# queryable directly, so it is matched with jq; labels are case-sensitive.
bd_id=""
bd_why=""
find_task() {
  local ids epics epic n what
  if ! queue_present; then
    bd_why="no execution queue here (bd) — no task to close"; return
  fi
  if [ -z "${tracker_id}" ] && [ -z "${slug}" ]; then
    bd_why="no change key in the branch name (<type>/<ID>-<slug> or <type>/<slug>) — close the task by hand"; return
  fi
  if ! command -v jq >/dev/null 2>&1; then
    bd_why="jq is missing — close the task by hand"; return
  fi
  if [ -n "${tracker_id}" ]; then
    ids="$(bd_run list --all -n 0 --json 2>/dev/null | jq -r --arg r "${tracker_id}" '.[] | select(.external_ref == $r) | .id' 2>/dev/null || true)"
    what="the task with external_ref ${tracker_id}"
  else
    epics="$(bd_run list --all -t epic -l "change:${slug}" -n 0 --json 2>/dev/null | jq -r '.[].id' 2>/dev/null || true)"
    n="$(printf '%s' "${epics}" | grep -c . || true)"
    if [ "${n}" != "1" ]; then
      bd_why="found ${n} epics labelled change:${slug} (need exactly 1) — close the task by hand"; return
    fi
    epic="${epics}"
    if [ -n "${phase}" ]; then
      ids="$(bd_run list --all --parent "${epic}" -l "phase:${phase}" -n 0 --json 2>/dev/null | jq -r '.[].id' 2>/dev/null || true)"
      what="the task labelled phase:${phase} under ${epic}"
    else
      ids="${epic}"
      what="the epic ${epic}"
    fi
  fi
  n="$(printf '%s' "${ids}" | grep -c . || true)"
  if [ "${n}" = "1" ]; then
    bd_id="${ids}"
  else
    bd_why="found ${n} candidates for ${what} (need exactly 1) — close the task by hand"
  fi
}
find_task
if [ -n "${print_bd_id}" ]; then
  echo "${bd_id}"
  [ -n "${bd_id}" ] || echo "${bd_why}" >&2
  exit 0
fi

if [ -n "${skip_ci_set}" ]; then
  if [ -z "${skip_ci}" ]; then
    echo "✗ --skip-ci needs a reason (why CI cannot run: billing, limits, a platform incident) — nothing done" >&2
    exit 2
  fi
  if [ "${FENCE_LEVEL}" = "team" ]; then
    echo "✗ --skip-ci is refused at FENCE_LEVEL=team: the team merges on CI only — nothing done" >&2
    exit 1
  fi
fi

# Closes the branch's task in the local queue — after the merge, idempotent (closing a closed task
# is not an error). Nothing is committed: the queue lives outside git.
close_task() {
  if [ -z "${bd_id}" ]; then
    echo "ℹ️ ${bd_why:-no task found}"
    return
  fi
  echo "→ bd close ${bd_id}"
  if bd_run close "${bd_id}" --reason "merged into ${MAIN_BRANCH} (merge-feature.sh)" >/dev/null 2>&1 \
     || bd_run show "${bd_id}" --json 2>/dev/null | grep -qE '"status": *"closed"'; then
    echo "  closed"
  else
    tail_fail "bd close ${bd_id} failed — close it by hand: bd close ${bd_id}"
  fi
}

# ── The PR description: the record of the work ──
PR_SECTIONS=("Done" "Decisions" "Open questions")
PR_SKELETON='## Done
<!-- what this change does, for a reader of `git log --merges` -->

## Decisions
<!-- the choices made and why; one that shapes the architecture also gets an ADR -->

## Open questions
<!-- what is left; each follow-up is a task in the execution queue — or "none" -->'

# The text without HTML comments (also multi-line ones) and carriage returns.
strip_comments() {
  tr -d '\r' | awk '{
    line = $0; out = ""
    while (length(line) > 0) {
      if (inc) { i = index(line, "-->"); if (i == 0) { line = ""; break }; line = substr(line, i + 3); inc = 0 }
      else { i = index(line, "<!--"); if (i == 0) { out = out line; break }; out = out substr(line, 1, i - 1); line = substr(line, i + 4); inc = 1 }
    }
    print out
  }'
}

# Prints the sections that are missing or have no text under their heading.
missing_sections() {
  local text="$1" section
  for section in "${PR_SECTIONS[@]}"; do
    if ! printf '%s\n' "${text}" | awk -v h="## ${section}" '
        /^##? / { sub(/[[:space:]]+$/, ""); on = ($0 == h); next }   # ### and deeper are content
        on && /[^[:space:]]/ { found = 1; exit }
        END { exit !found }'; then
      printf '%s\n' "## ${section}"
    fi
  done
}

# Reads the PR description into pr_body (comments stripped, trailing blank lines dropped);
# refuses when a section is missing or empty.
read_pr_body() {
  local raw missing
  if ! raw="$(gh pr view "${branch}" --json body -q .body 2>&1)"; then
    echo "✗ the PR description could not be read: ${raw}" >&2
    exit 1
  fi
  pr_body="$(printf '%s\n' "${raw}" | strip_comments | awk '{ a[NR] = $0 } /[^[:space:]]/ { last = NR } END { for (i = 1; i <= last; i++) print a[i] }')"
  missing="$(missing_sections "${pr_body}")"
  if [ -n "${missing}" ]; then
    cat >&2 <<EOF
✗ The PR description is the record of this work, and it is incomplete — merge cancelled.
  Missing or empty: $(printf '%s' "${missing}" | tr '\n' ',' | sed 's/,$//; s/,/, /g')
  Fill in ## Done, ## Decisions, ## Open questions (the /save skill does it; "none" is an answer):
    gh pr edit ${branch} --body-file - < <file>
  (an old gh fails there with "Projects (classic)": gh api -X PATCH repos/<owner>/<repo>/pulls/<number> -F body=@<file>)
  then re-run.
EOF
    exit 1
  fi
}

# Team mode: the PR must carry an approving review. Read again right before the merge.
check_review() {
  [ "${require_review}" = "1" ] || return 0
  local decision
  if ! decision="$(gh pr view "${branch}" --json reviewDecision -q .reviewDecision 2>&1)"; then
    echo "✗ review required (team mode), but the review decision could not be read: ${decision}" >&2
    exit 1
  fi
  if [ "${decision}" != "APPROVED" ]; then
    echo "✗ review required (team mode): the PR's review decision is '${decision:-none}', not APPROVED — merge cancelled. A teammate approves the PR on GitHub, then re-run." >&2
    exit 1
  fi
  echo "→ review: APPROVED"
}

# The local gate for --skip-ci and for a repository with no CI: the pre-push test command over the branch range, or LOCAL_GATE_CMD.
run_local_gate() {
  if [ -n "${LOCAL_GATE_CMD}" ]; then
    bash -c "${LOCAL_GATE_CMD}"
    return
  fi
  if [ ! -x .githooks/pre-push ]; then
    echo "✗ no local gate: .githooks/pre-push is missing and LOCAL_GATE_CMD is empty" >&2
    return 1
  fi
  local base
  git fetch -q origin "${MAIN_BRANCH}" || return 1
  base="$(git merge-base "origin/${MAIN_BRANCH}" HEAD)" || return 1
  printf 'refs/heads/%s %s refs/heads/%s %s\n' "${branch}" "$(git rev-parse HEAD)" "${branch}" "${base}" \
    | .githooks/pre-push origin
}

# Resumability: the PR is already merged (a previous run failed in the tail) →
# skip push/CI/merge and finish only the tail.
# "No PR" and "gh failed" (network, auth) are different answers: treating a failure
# as "no PR" would open a duplicate PR.
if pr_view_out="$(gh pr view "${branch}" --json state -q .state 2>&1)"; then
  pr_state="${pr_view_out}"
elif echo "${pr_view_out}" | grep -qi 'no pull requests found'; then
  pr_state='NONE'
else
  echo "✗ gh pr view failed — not the same as \"no PR\": ${pr_view_out}" >&2
  exit 1
fi

if [ "${pr_state}" = "CLOSED" ]; then
  echo "✗ PR of branch '${branch}' is closed without merge — reopen it or start a new branch; nothing done" >&2
  exit 1
fi

if [ "${pr_state}" = "MERGED" ]; then
  echo "→ PR of branch '${branch}' already merged — finishing the transaction tail"
else
  git rev-parse --verify "refs/heads/${branch}" >/dev/null 2>&1 \
    || { echo "✗ branch '${branch}' does not exist locally"; exit 1; }

  # No workflow files at the PR head — no checks will ever appear, waiting for them only ends in
  # "Checks did not appear". A fresh solo project has no CI yet: the local gate stands in for it.
  # Into a variable, not piped into grep -q: with pipefail an early grep exit can fail git (SIGPIPE).
  workflows="$(git ls-tree --name-only "refs/heads/${branch}" -- .github/workflows/)"
  if [ -z "${skip_ci_set}" ] && ! grep -qE '\.ya?ml$' <<< "${workflows}"; then
    if [ "${FENCE_LEVEL}" = "team" ]; then
      echo "✗ the branch has no CI (.github/workflows/*.yml) and FENCE_LEVEL=team merges on CI only — add a workflow; nothing done" >&2
      exit 1
    fi
    no_ci=1
  fi

  [ -z "$(git status --porcelain)" ] || { echo "✗ working tree is dirty — commit/clean up first"; exit 1; }

  # The local gate (no CI, --skip-ci) runs on the working tree — HEAD must be the branch.
  if [ "$(git symbolic-ref -q --short HEAD || true)" != "${branch}" ]; then
    git switch -q "${branch}" \
      || { echo "✗ cannot switch to '${branch}' (checked out in another worktree?) — run from there"; exit 1; }
    echo "→ switched to ${branch}"
  fi

  echo "→ push ${branch}"
  git push -u origin "${branch}"

  # PR: find an existing one (the draft opened at the start of work) or create it with the
  # description skeleton — the check below then asks for its sections to be filled in.
  if [ "${pr_state}" = "NONE" ]; then
    [ -n "${title}" ] || { echo "✗ no PR yet — a human-readable title is needed as the second argument"; exit 1; }
    echo "→ creating PR: ${title}"
    gh pr create --head "${branch}" --base "${MAIN_BRANCH}" --title "${title}" --body "${PR_SKELETON}"
  fi

  echo "→ PR description: ${PR_SECTIONS[*]}"
  read_pr_body

  # A draft cannot be merged: the script marks it ready.
  if [ "$(gh pr view "${branch}" --json isDraft -q .isDraft 2>/dev/null || true)" = "true" ]; then
    echo "→ draft → ready for review"
    gh pr ready "${branch}" || { echo "✗ could not mark the draft PR ready — merge cancelled" >&2; exit 1; }
  fi

  check_review

  ci_note=""
  if [ -n "${skip_ci_set}" ]; then
    # gh pr checks: 0 — green, 8 — pending; "no checks reported" — Actions did not start.
    ci_rc=0
    ci_out="$(gh pr checks "${branch}" 2>&1)" || ci_rc=$?
    if [ "${ci_rc}" = "0" ]; then
      echo "ℹ️ CI is green — --skip-ci is not needed, merging the usual way"
      skip_ci_set=""
    elif echo "${ci_out}" | grep -q 'no checks reported'; then
      ci_note="no checks reported"
    elif [ "${ci_rc}" = "8" ]; then
      ci_note="checks pending"
    else
      ci_note="checks failing or unreadable"
    fi
  fi
fi

if [ "${pr_state}" != "MERGED" ] && [ -n "${no_ci}" ]; then
  echo "→ no CI in this repository (.github/workflows is empty) — local gate instead of CI"
  if ! run_local_gate; then
    echo "✗ the local gate failed — merge cancelled. Without CI the local gate is the only check." >&2
    exit 1
  fi
  echo "  local gate passed"
  echo "ℹ️ consider adding CI: .github/workflows/ci.yml (the template's tiered ci.yml) — then merges wait for green checks"
elif [ "${pr_state}" != "MERGED" ] && [ -n "${skip_ci_set}" ]; then
  echo "⚠️ --skip-ci: CI is NOT awaited (${ci_note}). Reason: ${skip_ci}"
  echo "→ local gate instead of CI"
  if ! run_local_gate; then
    echo "✗ the local gate failed — merge cancelled. Without CI the local gate is the only check." >&2
    exit 1
  fi
  echo "  local gate passed"
elif [ "${pr_state}" != "MERGED" ]; then
  # First wait until the checks are CREATED at all. Without this step the script
  # declared red a CI that had not started yet: the push went through, check runs on
  # GitHub were not created, gh answers "no checks reported" with a non-zero code.
  # The failure looked like "CI is red", and the merge had to be re-run a second
  # and third time by hand.
  echo "→ waiting for checks to appear (up to ${CHECKS_APPEAR_TIMEOUT}s; GitHub does not create them instantly)"
  appear_started=$(date +%s)
  appear_deadline=$(( appear_started + CHECKS_APPEAR_TIMEOUT ))
  # Capture output into a variable, not via a pipeline: with `set -o pipefail`
  # the non-zero code of `gh` becomes the code of the whole pipeline, and a
  # successful grep does not save it — the wait loop silently never ran.
  checks_out="$(gh pr checks "${branch}" 2>&1 || true)"
  while echo "${checks_out}" | grep -q 'no checks reported'; do
    echo "   no checks yet, waiting... ($(( $(date +%s) - appear_started ))s)"
    if [ "$(date +%s)" -ge "${appear_deadline}" ]; then
      cat >&2 <<EOF
✗ Checks did not appear within ${CHECKS_APPEAR_TIMEOUT}s. This is NOT red CI.
  Likely causes: the workflow did not trigger on this push (its on: filters) or
  Actions are disabled. Merge cancelled — a human must investigate.
EOF
      exit 1
    fi
    sleep "${POLL_INTERVAL}"
    checks_out="$(gh pr checks "${branch}" 2>&1 || true)"
  done

  # A network failure is not red CI. `gh pr checks --watch` on a dropped connection exits
  # with the same non-zero code as on a failed check: a TLS handshake timeout was once
  # taken for red CI and the merge of a green branch was cancelled.
  # So on a non-zero code we re-read the status without --watch and tell the network
  # apart from a real failure by the response text.
  echo "→ waiting for CI (the full matrix runs in CI)"
  ci_green=""
  for ci_attempt in $(seq 1 "${CI_WATCH_RETRIES}"); do
    if gh pr checks "${branch}" --watch --fail-fast; then
      ci_green=1
      break
    fi
    ci_out="$(gh pr checks "${branch}" 2>&1 || true)"
    if echo "${ci_out}" | grep -qiE 'timeout|connection|TLS|network|dial tcp|EOF'; then
      echo "   attempt ${ci_attempt}/${CI_WATCH_RETRIES}: network failure while reading CI, not red CI — waiting ${POLL_INTERVAL}s and retrying"
      sleep "${POLL_INTERVAL}"
      continue
    fi
    echo "${ci_out}"
    echo "✗ CI is red — merge cancelled. Honest fail: for a human/agent to investigate."
    exit 1
  done
  [ -n "${ci_green}" ] || {
    echo "✗ CI status not read in ${CI_WATCH_RETRIES} attempts (network). This is NOT red CI — merge cancelled, re-run the script." >&2
    exit 1
  }
fi

if [ "${pr_state}" != "MERGED" ]; then
  check_review

  # The description may have been edited while CI ran: read it again, it goes into the merge commit.
  read_pr_body
  # A merge without CI goes on record before the merge: a loud PR comment and a trailer.
  trailers=""
  if [ -n "${skip_ci_set}" ]; then
    comment="⚠️ Merged WITHOUT CI: ${skip_ci}. CI state at merge: ${ci_note}; the local gate passed — merging via merge-feature.sh"
    trailers="CI-skipped: ${skip_ci}"
  elif [ -n "${no_ci}" ]; then
    comment="No CI in this repository — the local gate passed instead — merging via merge-feature.sh"
    trailers="CI: none (local gate)"
  fi
  if [ -n "${trailers}" ]; then
    echo "→ recording the merge without CI on the PR"
    gh pr comment "${branch}" --body "${comment}" \
      || { echo "✗ the record could not be written on the PR — merge cancelled (the record is part of the merge)" >&2; exit 1; }
    merge_msg="${pr_body}"$'\n\n'"${trailers}"
  else
    merge_msg="${pr_body}"
  fi
  merge_body=()
  case "${MERGE_FLAG}" in
    --merge)
      # Subject = the PR title and number, so `git log --oneline --merges` reads as the history.
      pr_title="$(gh pr view "${branch}" --json title -q .title 2>/dev/null || true)"
      pr_number="$(gh pr view "${branch}" --json number -q .number 2>/dev/null || true)"
      if [ -n "${pr_title}" ]; then
        merge_body=(--subject "${pr_title}${pr_number:+ (#${pr_number})}" --body "${merge_msg}")
      else
        merge_body=(--body "${merge_msg}")
      fi ;;
    --squash)
      merge_body=(--body "${merge_msg}") ;;
    *)
      echo "ℹ️ ${MERGE_FLAG} makes no merge commit — the PR description is not copied anywhere" ;;
  esac

  # We do not use --delete-branch: after the merge gh switches to the base branch
  # locally and fails if main is checked out in another worktree — and it does so AFTER the merge,
  # leaving the transaction half done. The branch is deleted as a separate step.
  echo "→ merge (${MERGE_FLAG})"
  gh pr merge "${branch}" ${MERGE_FLAG} ${merge_body[@]+"${merge_body[@]}"}
fi

# ── Transaction tail: every step is idempotent, failures accumulate in tail_fails ──

echo "→ deleting the branch on origin"
if git ls-remote --exit-code origin "refs/heads/${branch}" >/dev/null 2>&1; then
  git push origin --delete "${branch}" || tail_fail "branch '${branch}' on origin was not deleted"
else
  echo "  already deleted"
fi

echo "→ updating ${MAIN_BRANCH}"
git fetch -q origin
if git rev-parse -q --verify "refs/heads/${MAIN_BRANCH}" >/dev/null \
   && ! git merge-base --is-ancestor "${MAIN_BRANCH}" "origin/${MAIN_BRANCH}"; then
  # Never reset over local commits that are not on origin.
  tail_fail "local ${MAIN_BRANCH} has commits not on origin — not moved; reconcile it by hand"
elif git branch -f "${MAIN_BRANCH}" "origin/${MAIN_BRANCH}" 2>/dev/null; then
  echo "  local ${MAIN_BRANCH} fast-forwarded"
else
  echo "  ℹ️ ${MAIN_BRANCH} is checked out in another worktree — update it there (git pull)"
fi

close_task

# Do not leave the worktree on the merged feature branch.
# Do not check out MAIN_BRANCH itself — it may be checked out in another worktree;
# a detached HEAD conflicts with nobody.
git switch -q --detach "origin/${MAIN_BRANCH}" 2>/dev/null \
  && echo "→ worktree on origin/${MAIN_BRANCH} (detached)" \
  || echo "ℹ️ worktree left as is (switching to origin/${MAIN_BRANCH} failed)"

if [ "${#tail_fails[@]}" -gt 0 ]; then
  echo
  echo "✗ merge went through, but the transaction tail is unfinished:"
  for f in "${tail_fails[@]}"; do echo "   - ${f}"; done
  echo "  Re-run: scripts/merge-feature.sh ${branch} — it will finish only what is missing."
  exit 1
fi

echo "✓ ${branch} merged, transaction fully complete."
if [ -d .claude/skills/ship ]; then
  echo "  Next per the ship skill: board card → Merged + a comment linking the PR."
fi

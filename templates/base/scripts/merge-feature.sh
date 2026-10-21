#!/usr/bin/env bash
# Merge transaction residue (decision of the "Acceptance" layer).
# Accompanying changes (devlog, ROADMAP/SHIPPED, closing the bd task + queue
# export) travel in the feature branch in the same PR as the code — not as a
# separate commit to main after the merge. In projects where main = auto-deploy,
# every such "tail" commit is an extra prod rebuild.
#
# After the human's explicit "accepted", all the mechanics run as a script, not an LLM.
#
# For one feature branch it does: devlog check → bd close + commit of the closed
# task's line to the queue IN THE BRANCH → push → PR (find/create) → wait for green CI → merge (merge commit:
# code and accompanying changes enter main in one merge) → delete the branch on origin →
# update the main branch.
#
# Usage: scripts/merge-feature.sh <branch> [PR title]
#   The PR title (human-readable, no fluff) is required when creating a new PR.
# Red CI / conflict — an honest fail with exit ≠0: the script does NOT fix anything, report to the human.
#
# Transactionality = idempotency + resumability, not atomicity:
# a merge on GitHub cannot be rolled back. So the contract is: the script is safe
# to RE-RUN — an already merged PR is recognized, completed tail steps are
# skipped, unfinished ones are finished. Any tail failure is accumulated and at the end
# yields a non-zero exit code with a list — no "⚠️ … do it by hand" with exit 0 (principle #7).
#
# The bd task is closed BEFORE the merge (so the queue export goes into the PR, not
# as a tail). Compensation: until the merge is confirmed, a trap EXIT is set — if the
# script fails while waiting for CI/on a timeout, the task is returned to work
# (`bd reopen`), and the closing commit stays in the branch; a re-run closes it
# again without a diff. The trap is removed right after a successful `gh pr merge`.
#
# ONE line goes into the branch's queue — the closed task. A full export does not
# fit here: on machines with different bd versions it diverges from the committed
# file in almost every line (no `_type`, `bd import` rewrites edge authors and
# comment ids, stale defer dates) — two consecutive exports can rewrite nearly every
# line. Edits to OTHER tasks and new tasks therefore do not travel this way — they are
# shared separately (.beads/README.md). The file is assembled by scripts/beads-queue-line.sh.
#
# Fill in on deployment: MAIN_BRANCH, MERGE_FLAG.

set -euo pipefail

# All paths below (scripts/beads-queue-line.sh, .beads/issues.jsonl) are relative: running
# from a subdirectory broke the transaction tail after the merge had already happened.
cd "$(git rev-parse --show-toplevel)"

MAIN_BRANCH='<main>'
MERGE_FLAG='<--merge|--squash|--rebase>'   # the project's merge strategy. Recommended: --merge — squash breaks ancestry, git branch --merged and branch cleanup

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

branch="${1:?Usage: merge-feature.sh <branch> [PR title]}"
title="${2:-}"

# Unfinished tail steps accumulate here; the summary is at the bottom, as one list and an exit code.
tail_fails=()
tail_fail() { tail_fails+=("$1"); echo "  ⚠️ $1"; }

# bd task from the tail of the branch name: r{N}/<type>-<slug>-<bd-id>.
# Take everything after the last hyphen — bd understands the short id. Only for
# release-train branches: docs/* and fix/* carry no id.
bd_id=""
if echo "${branch}" | grep -qE '^r[0-9]+/'; then
  bd_id="$(echo "${branch}" | sed 's/.*-//')"
fi

QUEUE_FILE='.beads/issues.jsonl'

# Closes the bd task and commits its line to the queue. commit_to_branch=1 —
# the commit stays in the feature branch (goes to main together with the code on merge);
# commit_to_branch=0 — the PR was already merged by a previous run, there is nowhere
# to commit to any more, we do not push to main — only reconciliation and a hint.
close_bd_task() {
  local commit_to_branch="$1"
  if [ -z "${bd_id}" ] || ! command -v bd >/dev/null 2>&1; then
    echo "ℹ️ bd id not extracted from the branch name — close the task by hand"
    return
  fi
  echo "→ bd close ${bd_id}"
  if bd close "${bd_id}" --reason "merged into ${MAIN_BRANCH} (merge-feature.sh)" 2>/dev/null; then
    :
  elif bd show "${bd_id}" 2>/dev/null | grep -qi 'closed'; then
    # Build the line here too: a previous run may have closed the task but failed
    # before committing the queue.
    echo "  already closed (re-run)"
  else
    tail_fail "bd close ${bd_id} failed"
    return
  fi
  sync_bd_line "${commit_to_branch}"
}

# The closed task's line goes into the queue from the branch HEAD; all other lines
# byte for byte (scripts/beads-queue-line.sh). Changes nothing if the line is already
# the same or the task is already closed in the file.
sync_bd_line() {
  local commit_to_branch="$1" dir status
  if ! command -v jq >/dev/null 2>&1; then
    tail_fail "jq is required (brew install jq · apt install jq) — the line of closed ${bd_id} was not added to the beads queue"
    return
  fi
  dir="$(mktemp -d "${TMPDIR:-/tmp}/merge-feature-queue.XXXXXX")"
  # bd understands the short id; the file holds the full one (<prefix>-<id>).
  bd export 2>/dev/null \
    | jq -c --arg id "${bd_id}" 'select((.id // "") | endswith("-" + $id))' > "${dir}/task.jsonl" \
    || true
  # On any command bd may overwrite (and stage) the queue in the working tree with
  # its full export. The needed line is already taken — restore the file to HEAD,
  # otherwise the full export would go out with the next commit. post-checkout does
  # not fire on a file checkout, so bd import will not interfere.
  git checkout -q HEAD -- "${QUEUE_FILE}" 2>/dev/null || true
  if [ "$(wc -l < "${dir}/task.jsonl" | tr -d ' ')" != "1" ]; then
    tail_fail "line of task ${bd_id} not obtained from bd export — beads queue left untouched"
    rm -rf "${dir}"; return
  fi
  # "Already closed" above is detected by the word closed in `bd show` output — it
  # can also appear in the text of an open task. Never pass off an open line as closed.
  status="$(jq -r '.status // ""' "${dir}/task.jsonl")"
  if [ "${status}" != "closed" ]; then
    tail_fail "bd close ${bd_id} failed (store has status=${status}) — beads queue left untouched"
    rm -rf "${dir}"; return
  fi
  if git cat-file -e "HEAD:${QUEUE_FILE}" 2>/dev/null; then
    git show "HEAD:${QUEUE_FILE}" > "${dir}/base.jsonl"
  else
    : > "${dir}/base.jsonl"
  fi
  if ! scripts/beads-queue-line.sh "${dir}/base.jsonl" "${dir}/task.jsonl" > "${dir}/patched.jsonl"; then
    tail_fail "could not build the beads queue with the line of ${bd_id} (scripts/beads-queue-line.sh)"
  elif cmp -s "${dir}/base.jsonl" "${dir}/patched.jsonl"; then
    echo "  queue already up to date"
  elif [ "${commit_to_branch}" = "1" ]; then
    cp "${dir}/patched.jsonl" "${QUEUE_FILE}"
    git add "${QUEUE_FILE}"
    git commit -q -m "chore(beads): close ${bd_id}"
  else
    echo "ℹ️ PR already merged — closing ${bd_id} did not reach ${MAIN_BRANCH}; carry the line in the next feature branch (scripts/beads-queue-line.sh), not in ${MAIN_BRANCH}"
  fi
  rm -rf "${dir}"
}

# Resumability: the PR is already merged (a previous run failed in the tail) →
# skip push/CI/merge and finish only the tail.
pr_state="$(gh pr view "${branch}" --json state -q .state 2>/dev/null || echo 'NONE')"

if [ "${pr_state}" = "MERGED" ]; then
  echo "→ PR of branch '${branch}' already merged — finishing the transaction tail"
  close_bd_task 0
else
  git rev-parse --verify "refs/heads/${branch}" >/dev/null 2>&1 \
    || { echo "✗ branch '${branch}' does not exist locally"; exit 1; }

  [ -z "$(git status --porcelain)" ] || { echo "✗ working tree is dirty — commit/clean up first"; exit 1; }

  # Accompanying changes must travel in the branch, not as a tail after the merge.
  if echo "${branch}" | grep -qE '^r[0-9]+/'; then
    git fetch -q origin "${MAIN_BRANCH}"
    if git diff --quiet "origin/${MAIN_BRANCH}" HEAD -- devlog.md 2>/dev/null; then
      echo "✗ devlog.md is unchanged relative to origin/${MAIN_BRANCH} — add the devlog entry (and ROADMAP/SHIPPED, if this PR ships the release) to the branch" >&2
      exit 1
    fi
  fi

  close_bd_task 1

  # Until the merge is confirmed, the task must not hang closed for nothing.
  # shellcheck disable=SC2064
  trap "if [ -n \"${bd_id}\" ] && command -v bd >/dev/null 2>&1; then bd reopen \"${bd_id}\" 2>/dev/null && echo '↩ bd ${bd_id} reopened — merge did not happen'; fi" EXIT

  echo "→ push ${branch}"
  git push -u origin "${branch}"

  # PR: find an existing one or create it (body from commits, title passed in from outside)
  if [ "${pr_state}" = "NONE" ]; then
    [ -n "${title}" ] || { echo "✗ no PR yet — a human-readable title is needed as the second argument"; exit 1; }
    echo "→ creating PR: ${title}"
    gh pr create --head "${branch}" --base "${MAIN_BRANCH}" --title "${title}" --fill-verbose
  fi

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
  Likely causes: the workflow did not trigger on this push, Actions are disabled,
  or the branch has no .github/workflows. Merge cancelled — a human must investigate.
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
  echo "→ waiting for CI (full matrix runs in CI, an acceptance decision)"
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

  # We do not use --delete-branch: after the merge gh switches to the base branch
  # locally and fails if main is checked out in another worktree — and it does so AFTER the merge,
  # leaving the transaction half done. The branch is deleted as a separate step.
  echo "→ merge (${MERGE_FLAG})"
  gh pr merge "${branch}" ${MERGE_FLAG}
  trap - EXIT
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
if git branch -f "${MAIN_BRANCH}" "origin/${MAIN_BRANCH}" 2>/dev/null; then
  echo "  local ${MAIN_BRANCH} fast-forwarded"
else
  echo "  ℹ️ ${MAIN_BRANCH} is checked out in another worktree — update it there (git pull)"
fi

# The bd task and its queue line were already closed/committed to the feature branch before
# the push (close_bd_task above) — the merge carried them into main together with the code.
# Nothing to add here.

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

echo "✓ ${branch} merged, transaction fully complete. Next per the ship skill: board card → In Master + a comment linking the PR."

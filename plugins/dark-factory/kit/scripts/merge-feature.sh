#!/usr/bin/env bash
# Merge transaction residue (decision of the "Acceptance" layer).
# Accompanying changes (devlog, ROADMAP/SHIPPED, closing the bd task + queue
# export) travel in the feature branch in the same PR as the code — not as a
# separate commit to main after the merge. In projects where main = auto-deploy,
# every such "tail" commit is an extra prod rebuild.
#
# After the human's explicit "accepted", all the mechanics run as a script, not an LLM.
# The "yes" itself is recorded: --accepted-by "<name>" is required — the name of the person who
# said "accepted". The agent passes what the human said; nobody said it — the agent asks and does
# not merge. The script writes it to the PR as a comment and to the merge commit as an
# `Accepted-by:` trailer. The name is free text the agent types: below team nothing verifies it, so
# the record says "acceptance named by <name> (not verified)"; at team the PR's GitHub approval is
# checked, and the record says so. The guard (guard.py of the dark-factory plugin) denies a bare
# `gh pr merge`, so this script is the one way to merge.
#
# beads is optional: a project without .beads/ (the solo kit of /dark-factory:init) merges the same
# way, only the task-closing steps are skipped.
#
# For one feature branch it does: devlog check → bd close + commit of the closed
# task's line to the queue IN THE BRANCH → push → PR (find/create) → [team: approval check] →
# wait for green CI → acceptance comment → merge (merge commit:
# code and accompanying changes enter main in one merge) → delete the branch on origin →
# update the main branch.
#
# Usage: scripts/merge-feature.sh <branch> [PR title] --accepted-by "<name>" [--skip-ci "<reason>"]
#   The PR title (human-readable, no fluff) is required when creating a new PR.
#   --skip-ci "<reason>" — CI cannot run (Actions disabled: billing, limits, a platform incident):
#   the script does not wait for checks, runs the local gate (the pre-push test command) instead,
#   writes a loud "Merged WITHOUT CI" comment and a `CI-skipped:` trailer. Refused at FENCE_LEVEL=team.
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
# The bd task is taken from the branch name only when it ends in the full bd id:
# r{N}/<type>-<slug>-<prefix>-<id> (children too: <prefix>-<id>.3). Anything else — no id,
# close the task by hand. The prefix comes from the queue file (.beads/issues.jsonl).
#
# Fill in on deployment: MAIN_BRANCH, MERGE_FLAG; REQUIRE_REVIEW and LOCAL_GATE_CMD if needed.

set -euo pipefail

# All paths below (scripts/beads-queue-line.sh, .beads/issues.jsonl) are relative: running
# from a subdirectory broke the transaction tail after the merge had already happened.
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

usage='Usage: scripts/merge-feature.sh <branch> [PR title] --accepted-by "<name>" [--skip-ci "<reason>"]'
accepted_by=""
skip_ci=""
skip_ci_set=""
no_ci=""   # set below when the PR head has no workflow files
print_bd_id=""
positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    --accepted-by|--skip-ci)
      [ $# -ge 2 ] || { echo "✗ $1 needs a value. ${usage}" >&2; exit 2; }
      if [ "$1" = "--accepted-by" ]; then accepted_by="$2"; else skip_ci="$2"; skip_ci_set=1; fi
      shift 2 ;;
    --accepted-by=*) accepted_by="${1#*=}"; shift ;;
    --skip-ci=*) skip_ci="${1#*=}"; skip_ci_set=1; shift ;;
    --print-bd-id) print_bd_id=1; shift ;;   # prints the bd id taken from <branch> and exits
    --) shift; positional+=("$@"); break ;;
    --*) echo "✗ unknown option $1. ${usage}" >&2; exit 2 ;;
    *) positional+=("$1"); shift ;;
  esac
done
branch="${positional[0]:-}"
title="${positional[1]:-}"
[ -n "${branch}" ] || { echo "${usage}" >&2; exit 2; }

# One line, no surrounding blanks: the values go into a trailer and a comment.
one_line() { printf '%s' "$1" | tr -s '[:space:]' ' ' | sed 's/^ //; s/ $//'; }
accepted_by="$(one_line "${accepted_by}")"
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

QUEUE_FILE='.beads/issues.jsonl'

# The project's bd issue prefix — read without running bd (any bd command may rewrite and
# stage the queue file): the ids in the queue file, then .beads/config.yaml.
bd_prefix() {
  local id
  # The task's own top-level "id" (before any nested object: comments carry ids too).
  id="$(sed -n 's/^{[^{]*"id":"\([^"]*\)".*/\1/p' "${QUEUE_FILE}" 2>/dev/null | head -n 1)"
  if [ -n "${id}" ]; then
    echo "${id%-*}"
    return
  fi
  sed -n 's/^[[:space:]]*issue[-_]prefix:[[:space:]]*["'"'"']\{0,1\}\([^"'"'"'[:space:]]*\).*/\1/p' .beads/config.yaml 2>/dev/null | head -n 1
}

# bd task from the tail of the branch name: r{N}/<type>-<slug>-<prefix>-<id>[.<child>].
# Only the full id counts — "everything after the last hyphen" took a date or a version
# (r12/feat-lite-20261021-p3 → "p3") for a task. Only for release-train branches:
# docs/* and fix/* carry no id.
bd_id=""
if [[ "${branch}" =~ ^r[0-9]+/ ]]; then
  prefix="$(bd_prefix)"
  if [ -n "${prefix}" ]; then
    prefix_re="$(printf '%s' "${prefix}" | sed 's/[][\.*^$+?(){}|/]/\\&/g')"
    if [[ "${branch}" =~ -(${prefix_re}-[[:alnum:]]+(\.[0-9]+)*)$ ]]; then
      bd_id="${BASH_REMATCH[1]}"
    fi
  fi
fi
if [ -n "${print_bd_id}" ]; then
  echo "${bd_id}"
  exit 0
fi

# The human's "yes" — without it nothing is done.
if [ -z "${accepted_by}" ]; then
  cat >&2 <<EOF
✗ No human acceptance given — nothing done.
  merge-feature.sh merges only after a person's explicit "accepted". Pass their name:
    ${usage}
  An agent passes the name of the person who said "accepted". Nobody said it — ask; do not merge.
  Below FENCE_LEVEL=team the name is recorded as named, not verified; at team the PR's
  approval is verified on GitHub.
EOF
  exit 2
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

# Closes the bd task and commits its line to the queue. commit_to_branch=1 —
# the commit stays in the feature branch (goes to main together with the code on merge);
# commit_to_branch=0 — the PR was already merged by a previous run, there is nowhere
# to commit to any more, we do not push to main — only reconciliation and a hint.
close_bd_task() {
  local commit_to_branch="$1"
  if [ ! -d .beads ]; then
    echo "ℹ️ no beads queue in this project (.beads/) — no task to close"
    return
  fi
  if [ -z "${bd_id}" ]; then
    echo "ℹ️ no bd id in the branch name (r{N}/<type>-<slug>-<prefix>-<id>) — close the task by hand"
    return
  fi
  if ! command -v bd >/dev/null 2>&1; then
    echo "ℹ️ bd is not installed — close ${bd_id} by hand"
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
  # The branch carries the full id (<prefix>-<id>); a short one is matched by its tail.
  bd export 2>/dev/null \
    | jq -c --arg id "${bd_id}" 'select((.id // "") as $x | $x == $id or ($x | endswith("-" + $id)))' > "${dir}/task.jsonl" \
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

# How the acceptance is described on record: only team mode checks anything on GitHub.
acceptance_note() {
  if [ "${require_review}" = "1" ]; then
    echo "Acceptance named by ${accepted_by}; approval verified on GitHub"
  else
    echo "Acceptance named by ${accepted_by} (not verified)"
  fi
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
  close_bd_task 0
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

  # The devlog check and the queue commit below work on HEAD — it must be the branch.
  if [ "$(git symbolic-ref -q --short HEAD || true)" != "${branch}" ]; then
    git switch -q "${branch}" \
      || { echo "✗ cannot switch to '${branch}' (checked out in another worktree?) — run from there"; exit 1; }
    echo "→ switched to ${branch}"
  fi

  # Accompanying changes must travel in the branch, not as a tail after the merge.
  if echo "${branch}" | grep -qE '^r[0-9]+/'; then
    git fetch -q origin "${MAIN_BRANCH}"
    if git diff --quiet "origin/${MAIN_BRANCH}...HEAD" -- devlog.md 2>/dev/null; then
      echo "✗ devlog.md is unchanged relative to origin/${MAIN_BRANCH} — add the devlog entry (and ROADMAP/SHIPPED, if this PR ships the release) to the branch" >&2
      exit 1
    fi
  fi

  # Until the merge is confirmed, the task must not hang closed for nothing — the trap
  # is set before closing, so a failure inside close_bd_task (a hook, a commit) reopens it too.
  # shellcheck disable=SC2064
  trap "if [ -n \"${bd_id}\" ] && command -v bd >/dev/null 2>&1; then bd reopen \"${bd_id}\" 2>/dev/null && echo '↩ bd ${bd_id} reopened — merge did not happen'; fi" EXIT

  close_bd_task 1

  echo "→ push ${branch}"
  git push -u origin "${branch}"

  # PR: find an existing one or create it (body from commits, title passed in from outside)
  if [ "${pr_state}" = "NONE" ]; then
    [ -n "${title}" ] || { echo "✗ no PR yet — a human-readable title is needed as the second argument"; exit 1; }
    echo "→ creating PR: ${title}"
    gh pr create --head "${branch}" --base "${MAIN_BRANCH}" --title "${title}" --fill-verbose
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
fi

if [ "${pr_state}" != "MERGED" ]; then
  check_review

  # The acceptance goes on record before the merge: a PR comment and a trailer in the merge commit.
  acceptance="$(acceptance_note)"
  if [ -n "${skip_ci_set}" ]; then
    comment="⚠️ Merged WITHOUT CI by ${accepted_by}: ${skip_ci}. CI state at merge: ${ci_note}; the local gate passed. ${acceptance} — merging via merge-feature.sh"
  elif [ -n "${no_ci}" ]; then
    comment="No CI in this repository — the local gate passed instead. ${acceptance} — merging via merge-feature.sh"
  else
    comment="${acceptance} — merging via merge-feature.sh"
  fi
  echo "→ recording the acceptance on the PR"
  gh pr comment "${branch}" --body "${comment}" \
    || { echo "✗ the acceptance could not be recorded on the PR — merge cancelled (the record is part of the merge)" >&2; exit 1; }

  trailers="Accepted-by: ${accepted_by}"
  if [ -n "${skip_ci_set}" ]; then
    trailers="${trailers}"$'\n'"CI-skipped: ${skip_ci}"
  elif [ -n "${no_ci}" ]; then
    trailers="${trailers}"$'\n'"CI: none (local gate)"
  fi
  merge_body=()
  case "${MERGE_FLAG}" in
    --merge)
      # GitHub's default merge-commit body is the PR title — keep it above the trailers.
      pr_title="$(gh pr view "${branch}" --json title -q .title 2>/dev/null || true)"
      if [ -n "${pr_title}" ]; then
        merge_body=(--body "${pr_title}"$'\n\n'"${trailers}")
      else
        merge_body=(--body "${trailers}")
      fi ;;
    --squash)
      merge_body=(--body "${trailers}") ;;
    *)
      echo "ℹ️ ${MERGE_FLAG} makes no merge commit — the acceptance is recorded in the PR comment only" ;;
  esac

  # We do not use --delete-branch: after the merge gh switches to the base branch
  # locally and fails if main is checked out in another worktree — and it does so AFTER the merge,
  # leaving the transaction half done. The branch is deleted as a separate step.
  echo "→ merge (${MERGE_FLAG})"
  gh pr merge "${branch}" ${MERGE_FLAG} ${merge_body[@]+"${merge_body[@]}"}
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
if git rev-parse -q --verify "refs/heads/${MAIN_BRANCH}" >/dev/null \
   && ! git merge-base --is-ancestor "${MAIN_BRANCH}" "origin/${MAIN_BRANCH}"; then
  # Never reset over local commits that are not on origin.
  tail_fail "local ${MAIN_BRANCH} has commits not on origin — not moved; reconcile it by hand"
elif git branch -f "${MAIN_BRANCH}" "origin/${MAIN_BRANCH}" 2>/dev/null; then
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
  echo "  Re-run: scripts/merge-feature.sh ${branch} --accepted-by \"${accepted_by}\" — it will finish only what is missing."
  exit 1
fi

echo "✓ ${branch} merged, transaction fully complete."
if [ -d .claude/skills/ship ]; then
  echo "  Next per the ship skill: board card → Merged + a comment linking the PR."
fi

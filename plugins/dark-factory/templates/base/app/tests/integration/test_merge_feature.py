"""merge-feature.sh end to end on a temporary repository, with `gh` and `bd` replaced by stubs.

Covered: the PR description as the record (## Done / ## Decisions / ## Open questions — refused
when missing or empty, written into the merge commit), a draft PR made ready, closing the branch's
task in the local execution queue after the merge (nothing committed), team mode
(reviewDecision), the no-CI paths (--skip-ci, a repository without workflows) and finding the task
to close from the branch name (tracker ID → external_ref; slug [+ phase] → labels).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # app/tests/integration/ → repo root
MERGE_FEATURE = REPO_ROOT / "scripts" / "merge-feature.sh"
WORKFLOW = ".github/workflows/ci.yml"
TASK_ID = "proj-t4sk"
BRANCH = "fix/PROJ-12-something"   # <type>/<tracker ID>-<slug>
# What `bd list --all -n 0 --json` answers: one task carries the tracker ID PROJ-12 as its external_ref.
BD_ALL_TASKS = '[{"id": "proj-t4sk", "external_ref": "PROJ-12"}, {"id": "proj-other"}]'
PR_BODY = """## Done
Fixed something.

## Decisions
<!-- a comment does not count -->
Kept the old API.

## Open questions
none
"""


def _isolated_env(**extra: str) -> dict[str, str]:
    # The pre-push hook runs pytest with GIT_DIR/GIT_INDEX_FILE of the real repo:
    # if inherited, they lead git out of the temporary repo into the real one.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "BEADS_"))}
    return {**env, "BD_ALL": BD_ALL_TASKS, **extra}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=_isolated_env(), check=True, capture_output=True, text=True
    ).stdout.strip()


# ── stubs and the feature clone ──

GH_STUB = """#!/usr/bin/env bash
echo "$*" >> "$(dirname "$0")/../gh-calls"
case "$1 $2" in
  "pr view")
    if [ -n "${GH_VIEW_ERROR:-}" ]; then echo "$GH_VIEW_ERROR" >&2; exit 1; fi
    case "$*" in
      *"--json reviewDecision"*) echo "${GH_REVIEW_DECISION:-}" ;;
      *"--json title"*) echo "Fix something" ;;
      *"--json number"*) echo "7" ;;
      *"--json headRefOid"*) echo "${GH_HEAD_OID:-}" ;;
      *"--json isDraft"*) echo "${GH_DRAFT:-false}" ;;
      *"--json body"*) cat "$(dirname "$0")/../pr-body" ;;
      *) if [ -n "${GH_NO_PR:-}" ]; then echo "no pull requests found for branch" >&2; exit 1; fi
         echo "${GH_PR_STATE:-OPEN}" ;;
    esac ;;
  "pr checks")
    if [ -n "${GH_NO_CHECKS:-}" ]; then echo "no checks reported on the '$3' branch"; exit 1; fi
    echo "all checks passed" ;;
  "pr comment")
    if [ -n "${GH_COMMENT_ERROR:-}" ]; then echo "$GH_COMMENT_ERROR" >&2; exit 1; fi ;;
  *) : ;;
esac
"""

# The local queue: every call is logged; the store answers `where` and the three `list` queries of
# merge-feature.sh (all tasks → BD_ALL, epics of a slug → BD_EPICS, children of an epic → BD_CHILDREN,
# any task of a slug → BD_LABELLED).
BD_STUB = """#!/usr/bin/env bash
echo "$*" >> "$(dirname "$0")/../bd-calls"
case "$1" in
  where) echo "/main/.beads" ;;
  list)
    case "$*" in
      *"-t epic"*) echo "${BD_EPICS:-[]}" ;;
      *"--parent"*) echo "${BD_CHILDREN:-[]}" ;;
      *"-l change:"*) echo "${BD_LABELLED:-[]}" ;;
      *) echo "${BD_ALL:-[]}" ;;
    esac ;;
  close) [ -z "${BD_CLOSE_FAILS:-}" ] || exit 1 ;;
  show) echo '{"status": "in_progress"}' ;;
esac
"""


def _stub(tmp_path: Path, name: str, body: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(body)
    stub.chmod(0o755)


def _set_pr_body(clone: Path, body: str) -> None:
    (clone.parent / "pr-body").write_text(body, encoding="utf-8")


def _deploy_script(work: Path) -> None:
    # Template placeholders are filled in on deployment — here we substitute them ourselves.
    (work / "scripts").mkdir()
    script = MERGE_FEATURE.read_text(encoding="utf-8")
    script = script.replace("MAIN_BRANCH='<main>'", "MAIN_BRANCH='main'")
    script = script.replace("MERGE_FLAG='<--merge|--squash|--rebase>'", "MERGE_FLAG='--merge'")
    # The local gate of --skip-ci: the test decides (TEST_LOCAL_GATE=false — a red gate).
    script = script.replace("LOCAL_GATE_CMD=''", 'LOCAL_GATE_CMD="${TEST_LOCAL_GATE:-true}"')
    (work / "scripts" / "merge-feature.sh").write_text(script, encoding="utf-8")


@pytest.fixture
def feature_clone(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "dev@example.com")
    _git(work, "config", "user.name", "Dev")
    _deploy_script(work)
    # A project with CI: merges wait for checks (the no-workflow path has its own tests).
    (work / WORKFLOW).parent.mkdir(parents=True)
    (work / WORKFLOW).write_text("name: ci\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "HEAD:main")
    _git(work, "checkout", "-b", BRANCH)
    (work / "fix.txt").write_text("fixed\n", encoding="utf-8")
    _git(work, "add", "fix.txt")
    _git(work, "commit", "-m", "fix: something")
    _set_pr_body(work, PR_BODY)
    _stub(tmp_path, "gh", GH_STUB)
    _stub(tmp_path, "bd", BD_STUB)
    return work


def _run_merge(
    clone: Path, *args: str, branch: str = BRANCH, **env_extra: str
) -> subprocess.CompletedProcess[str]:
    env = _isolated_env(PATH=f"{clone.parent / 'bin'}{os.pathsep}{os.environ['PATH']}", **env_extra)
    return subprocess.run(
        ["bash", "scripts/merge-feature.sh", branch, *args],
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _gh_calls(clone: Path) -> str:
    calls = clone.parent / "gh-calls"
    return calls.read_text() if calls.exists() else ""


def _bd_calls(clone: Path) -> str:
    calls = clone.parent / "bd-calls"
    return calls.read_text() if calls.exists() else ""


def _task_closed(clone: Path) -> bool:
    return any(line.startswith("close ") for line in _bd_calls(clone).splitlines())


def _merge_call(clone: Path) -> str:
    calls = _gh_calls(clone)
    assert "pr merge" in calls, calls
    return calls[calls.index("pr merge"):]


def _commit_on_branch(clone: Path, path: str, text: str) -> None:
    (clone / path).parent.mkdir(parents=True, exist_ok=True)
    (clone / path).write_text(text, encoding="utf-8")
    _git(clone, "add", path)
    _git(clone, "commit", "-qm", f"chore: {path}")


# ── the execution queue: the task is closed locally after the merge, nothing is committed ──


def test_task_closed_after_merge_and_nothing_committed(feature_clone: Path) -> None:
    head_before = _git(feature_clone, "rev-parse", BRANCH)

    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"close {TASK_ID} --reason merged into main (merge-feature.sh)" in _bd_calls(feature_clone)
    assert _git(feature_clone, "rev-parse", BRANCH) == head_before
    assert _git(feature_clone, "status", "--porcelain") == ""
    assert result.stdout.index("→ merge") < result.stdout.index(f"→ bd close {TASK_ID}")


def test_failed_close_is_an_unfinished_tail(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, BD_CLOSE_FAILS="1")

    assert result.returncode != 0
    assert "pr merge" in _gh_calls(feature_clone)
    assert f"bd close {TASK_ID} failed" in result.stdout


def test_already_merged_pr_finishes_the_tail_and_closes_the_task(feature_clone: Path) -> None:
    _git(feature_clone, "push", "origin", f"{BRANCH}:main")   # the work really landed

    result = _run_merge(feature_clone, GH_PR_STATE="MERGED")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)
    assert f"close {TASK_ID}" in _bd_calls(feature_clone)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file")
def test_unreadable_gitmodules_gives_no_fetch_warnings(feature_clone: Path) -> None:
    # The Claude Code sandbox hides .gitmodules behind an unreadable stub; fetch must not try to read it.
    _git(feature_clone, "push", "origin", f"{BRANCH}:main")
    stub = feature_clone / ".gitmodules"
    stub.touch()
    stub.chmod(0)

    result = _run_merge(feature_clone, GH_PR_STATE="MERGED")

    assert result.returncode == 0, result.stdout + result.stderr
    assert ".gitmodules" not in result.stdout + result.stderr


def test_squash_merged_pr_is_recognised_by_its_head_commit(feature_clone: Path) -> None:
    tip = _git(feature_clone, "rev-parse", BRANCH)

    result = _run_merge(feature_clone, GH_PR_STATE="MERGED", GH_HEAD_OID=tip)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"close {TASK_ID}" in _bd_calls(feature_clone)


def test_reused_branch_name_does_not_pass_for_the_old_merged_pr(feature_clone: Path) -> None:
    # `gh pr view <branch>` finds an older merged PR; the new commit never reached the main branch.
    result = _run_merge(feature_clone, GH_PR_STATE="MERGED", GH_HEAD_OID="1" * 40)

    assert result.returncode != 0
    assert "branch name reused" in result.stderr
    assert "start a new branch" in result.stderr
    assert not _task_closed(feature_clone)
    assert "pr merge" not in _gh_calls(feature_clone)


def test_run_from_another_branch_merges_the_named_branch(feature_clone: Path) -> None:
    _git(feature_clone, "checkout", "-q", "main")
    main_before = _git(feature_clone, "rev-parse", "main")

    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "→ switched to " + BRANCH in result.stdout
    assert _git(feature_clone, "rev-parse", "main") == main_before


def test_closed_pr_is_refused_and_task_stays_open(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_PR_STATE="CLOSED")

    assert result.returncode != 0
    assert "closed" in (result.stdout + result.stderr).lower()
    assert not _task_closed(feature_clone)
    assert "pr merge" not in _gh_calls(feature_clone)


def test_gh_error_is_not_taken_for_missing_pr(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "Title", GH_VIEW_ERROR="error connecting to api.github.com")

    assert result.returncode != 0
    assert "pr create" not in _gh_calls(feature_clone)
    assert not _task_closed(feature_clone)


# ── the PR description is the record ──


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ("", "## Done, ## Decisions, ## Open questions"),
        ("## Done\nx\n\n## Decisions\ny\n", "## Open questions"),
        ("## Done\nx\n## Decisions\n<!-- to do -->\n## Open questions\nnone\n", "## Decisions"),
        ("## Done\n<!-- a\nmulti-line comment -->\n## Decisions\ny\n## Open questions\nnone\n", "## Done"),
    ],
)
def test_refuses_without_the_three_sections(feature_clone: Path, body: str, missing: str) -> None:
    _set_pr_body(feature_clone, body)

    result = _run_merge(feature_clone)

    assert result.returncode != 0
    assert f"Missing or empty: {missing}" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)
    assert not _task_closed(feature_clone)


def test_sub_headings_count_as_content(feature_clone: Path) -> None:
    _set_pr_body(feature_clone, "## Done\n### API\nadded x\n\n## Decisions\n### Storage\nkept\n\n## Open questions\nnone\n")

    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pr merge" in _gh_calls(feature_clone)


def test_new_pr_gets_the_skeleton_and_is_refused_until_filled(feature_clone: Path) -> None:
    _set_pr_body(feature_clone, "")

    result = _run_merge(feature_clone, "Fix something", GH_NO_PR="1")

    assert result.returncode != 0
    calls = _gh_calls(feature_clone)
    assert "pr create" in calls
    assert "## Done\n<!--" in calls
    assert "gh pr edit" in result.stderr


def test_description_goes_into_the_merge_commit(feature_clone: Path) -> None:
    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    merge = _merge_call(feature_clone)
    assert "--subject Fix something (#7)" in merge
    assert "## Done\nFixed something.\n\n## Decisions\n\nKept the old API." in merge
    assert "comment does not count" not in merge
    assert "## Open questions\nnone" in merge
    assert "Accepted-by" not in merge


def test_draft_pr_is_made_ready_before_merge(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_DRAFT="true")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _gh_calls(feature_clone)
    assert calls.index("pr ready") < calls.index("pr merge")


# ── the human's acceptance, team mode, merging without CI ──


def test_ordinary_merge_leaves_no_acceptance_record(feature_clone: Path) -> None:
    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pr comment" not in _gh_calls(feature_clone)
    merge = _merge_call(feature_clone)
    assert "--merge --subject Fix something (#7) --body ## Done" in merge
    assert "Accepted-by" not in merge
    assert "CI-skipped" not in merge


def test_accepted_by_is_no_longer_an_option(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--accepted-by", "Ann Owner")

    assert result.returncode != 0
    assert "unknown option" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_failed_ci_skip_comment_cancels_merge(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--skip-ci", "billing", GH_NO_CHECKS="1", GH_COMMENT_ERROR="HTTP 502")

    assert result.returncode != 0
    assert "pr merge" not in _gh_calls(feature_clone)


@pytest.mark.parametrize("how", ["env", "fences"])
def test_team_mode_refuses_without_approval(feature_clone: Path, how: str) -> None:
    if how == "fences":
        _commit_on_branch(feature_clone, ".claude/fences.env", "FENCE_LEVEL=team\n")
        env = {"MERGE_REQUIRE_REVIEW": "0"}  # the environment cannot switch team mode off
    else:
        env = {"MERGE_REQUIRE_REVIEW": "1"}

    result = _run_merge(feature_clone, GH_REVIEW_DECISION="REVIEW_REQUIRED", **env)

    assert result.returncode != 0
    assert "REVIEW_REQUIRED" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_team_mode_merges_when_approved(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, MERGE_REQUIRE_REVIEW="1", GH_REVIEW_DECISION="APPROVED")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _gh_calls(feature_clone)
    assert "reviewDecision" in calls
    assert "pr merge" in calls


def test_solo_owner_needs_no_approval(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_REVIEW_DECISION="REVIEW_REQUIRED")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "reviewDecision" not in _gh_calls(feature_clone)


def test_skip_ci_merges_on_local_gate_with_loud_record(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--skip-ci", "Actions disabled: billing", GH_NO_CHECKS="1")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _gh_calls(feature_clone)
    assert "--watch" not in calls
    assert "Merged WITHOUT CI: Actions disabled: billing" in calls
    assert "no checks reported" in calls
    merge = _merge_call(feature_clone)
    assert "\n\nCI-skipped: Actions disabled: billing" in merge


def test_skip_ci_refuses_on_red_local_gate(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--skip-ci", "billing", GH_NO_CHECKS="1", TEST_LOCAL_GATE="false")

    assert result.returncode != 0
    assert "local gate failed" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_skip_ci_needs_a_reason(feature_clone: Path) -> None:
    no_reason = _run_merge(feature_clone, "--skip-ci", " ")

    assert no_reason.returncode != 0
    assert "reason" in no_reason.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_skip_ci_refused_at_team_level(feature_clone: Path) -> None:
    _commit_on_branch(feature_clone, ".claude/fences.env", "FENCE_LEVEL=team\n")

    result = _run_merge(feature_clone, "--skip-ci", "billing", GH_NO_CHECKS="1", GH_REVIEW_DECISION="APPROVED")

    assert result.returncode != 0
    assert "team" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


# ── a repository without CI (no workflow files at the PR head, e.g. a fresh solo project) ──


def _drop_workflows(clone: Path) -> None:
    _git(clone, "rm", "-q", WORKFLOW)
    _git(clone, "commit", "-qm", "chore: no CI yet")


@pytest.mark.parametrize("level", ["solo", "standard"])
def test_no_workflows_merges_on_local_gate(feature_clone: Path, level: str) -> None:
    _drop_workflows(feature_clone)
    _commit_on_branch(feature_clone, ".claude/fences.env", f"FENCE_LEVEL={level}\n")

    result = _run_merge(feature_clone, GH_NO_CHECKS="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "local gate passed" in result.stdout
    assert "consider adding CI" in result.stdout
    calls = _gh_calls(feature_clone)
    assert "pr checks" not in calls  # nothing to wait for
    assert "No CI in this repository" in calls
    merge = _merge_call(feature_clone)
    assert "\n\nCI: none (local gate)" in merge
    assert "CI-skipped" not in merge


def test_no_workflows_refuses_on_red_local_gate(feature_clone: Path) -> None:
    _drop_workflows(feature_clone)

    result = _run_merge(feature_clone, TEST_LOCAL_GATE="false")

    assert result.returncode != 0
    assert "local gate failed" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)
    assert not _task_closed(feature_clone)


def test_no_workflows_refused_at_team_level(feature_clone: Path) -> None:
    _drop_workflows(feature_clone)
    _commit_on_branch(feature_clone, ".claude/fences.env", "FENCE_LEVEL=team\n")

    result = _run_merge(feature_clone, GH_REVIEW_DECISION="APPROVED")

    assert result.returncode != 0
    assert "team" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)
    assert not _task_closed(feature_clone)


def test_workflows_without_checks_still_wait(feature_clone: Path) -> None:
    # Workflows exist but checks never appear — the usual wait, then an honest cancel.
    script = feature_clone / "scripts" / "merge-feature.sh"
    script.write_text(
        script.read_text(encoding="utf-8").replace("CHECKS_APPEAR_TIMEOUT=600", "CHECKS_APPEAR_TIMEOUT=0"),
        encoding="utf-8",
    )
    _git(feature_clone, "commit", "-qam", "test: do not wait for checks")

    result = _run_merge(feature_clone, GH_NO_CHECKS="1")

    assert result.returncode != 0
    assert "Checks did not appear" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def _rename_branch(clone: Path, new: str) -> str:
    _git(clone, "branch", "-m", BRANCH, new)
    return new


def _find_task(clone: Path, branch: str, **env: str) -> str:
    result = subprocess.run(
        ["bash", "scripts/merge-feature.sh", branch, "--print-bd-id"],
        cwd=clone,
        env=_isolated_env(PATH=f"{clone.parent / 'bin'}{os.pathsep}{os.environ['PATH']}", **env),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _json(*ids: str) -> str:
    return "[" + ",".join(f'{{"id": "{i}"}}' for i in ids) + "]"


@pytest.mark.parametrize(
    ("branch", "bd_id"),
    [
        ("feat/PROJ-12-voice-input", "proj-t4sk"),  # tracker ID → the task whose external_ref equals it
        ("feat/PROJ-99-voice-input", ""),  # no task carries that external_ref
        ("fix/12-voice-input", ""),  # GitHub-style numeric ID, none in the queue
        ("voice-input", ""),  # not a work branch: no type prefix
        ("release/PROJ-12-x", ""),  # not a work type
    ],
)
def test_task_found_by_tracker_id(feature_clone: Path, branch: str, bd_id: str) -> None:
    assert _find_task(feature_clone, branch) == bd_id


def test_task_found_by_slug_epic_itself(feature_clone: Path) -> None:
    env = {"BD_EPICS": _json("proj-ep1")}
    assert _find_task(feature_clone, "feat/voice-input", **env) == "proj-ep1"
    calls = _bd_calls(feature_clone)
    assert 'list --all -t epic -l change:voice-input -n 0 --json' in calls


def test_task_found_by_slug_without_an_epic(feature_clone: Path) -> None:
    # a small change: one task of type feature labelled change:<slug> (wrap skill, feature-lite)
    env = {"BD_LABELLED": _json("proj-f1")}
    assert _find_task(feature_clone, "feat/voice-input", **env) == "proj-f1"


def test_task_found_by_slug_and_phase(feature_clone: Path) -> None:
    env = {"BD_EPICS": _json("proj-ep1"), "BD_CHILDREN": _json("proj-ep1.2")}
    assert _find_task(feature_clone, "feat/voice-input-p2", **env) == "proj-ep1.2"
    calls = _bd_calls(feature_clone)
    assert "list --all --parent proj-ep1 -l phase:2 -n 0 --json" in calls


@pytest.mark.parametrize(
    "env",
    [
        {},  # no epic for the slug
        {"BD_EPICS": _json("proj-ep1", "proj-ep2")},  # two epics: ambiguous
        {"BD_EPICS": _json("proj-ep1"), "BD_CHILDREN": _json("a", "b")},  # two tasks for the phase
        {"BD_EPICS": _json("proj-ep1")},  # one epic, but the phase has no task
    ],
)
def test_ambiguous_or_missing_task_is_closed_by_hand(feature_clone: Path, env: dict[str, str]) -> None:
    assert _find_task(feature_clone, "feat/voice-input-p2", **env) == ""


def test_merge_with_no_task_found_still_succeeds(feature_clone: Path) -> None:
    branch = _rename_branch(feature_clone, "feat/voice-input")

    result = _run_merge(feature_clone, branch=branch)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "close the task by hand" in result.stdout
    assert not _task_closed(feature_clone)


def test_slug_path_closes_the_phase_task_after_merge(feature_clone: Path) -> None:
    branch = _rename_branch(feature_clone, "feat/voice-input-p2")

    result = _run_merge(feature_clone, branch=branch, BD_EPICS=_json("proj-ep1"), BD_CHILDREN=_json("proj-ep1.2"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "close proj-ep1.2 --reason merged into main" in _bd_calls(feature_clone)


# ── a project without an execution queue (the solo kit of the dark-factory plugin's /dark-factory:init) ──


def test_merges_without_a_queue_or_bd(tmp_path: Path) -> None:
    """No bd on PATH: the merge goes through, nothing to close."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "dev@example.com")
    _git(work, "config", "user.name", "Dev")
    _deploy_script(work)
    (work / ".claude").mkdir()
    (work / ".claude" / "fences.env").write_text("FENCE_LEVEL=solo\n", encoding="utf-8")
    (work / WORKFLOW).parent.mkdir(parents=True)
    (work / WORKFLOW).write_text("name: ci\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "HEAD:main")
    _git(work, "checkout", "-b", "feat/no-queue")
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    _git(work, "add", "README.md")
    _git(work, "commit", "-m", "docs: readme")
    _set_pr_body(work, PR_BODY)
    _stub(tmp_path, "gh", GH_STUB)
    # PATH: the gh stub plus the system tools, but no bd (a real bd may live elsewhere on PATH).
    bin_dirs = [str(tmp_path / "bin")] + [
        d for d in os.environ["PATH"].split(os.pathsep) if d and not (Path(d) / "bd").exists()
    ]

    result = subprocess.run(
        ["bash", "scripts/merge-feature.sh", "feat/no-queue", "Readme"],
        cwd=work,
        env=_isolated_env(PATH=os.pathsep.join(bin_dirs)),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no execution queue here" in result.stdout
    assert "pr merge" in _merge_call(work)

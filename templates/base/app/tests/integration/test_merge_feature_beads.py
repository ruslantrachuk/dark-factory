"""merge-feature.sh commits a single line to the branch's beads queue — the closed task.

A full `bd export` after `bd close`, committed to the feature branch, differs from the
committed file in almost every line (a local bd does not write `_type`, `bd import`
rewrites edge authors and comment ids, the database keeps stale defer dates) — two
exports in a row can rewrite nearly the whole file.

The file is assembled by `scripts/beads-queue-line.sh` — these tests run it directly.
The tests at the end run the whole merge-feature.sh on a temporary repository: `gh` and `bd`
are replaced by stubs; the `bd` stub behaves like the real one — a lossy export on
every line, and every command rewrites and stages `.beads/issues.jsonl`. They also cover
the recorded human acceptance (--accepted-by: PR comment + `Accepted-by:` trailer), team
mode (reviewDecision), the no-CI path (--skip-ci) and taking the bd id from the branch name.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # app/tests/integration/ → repo root
QUEUE_LINE = REPO_ROOT / "scripts" / "beads-queue-line.sh"
MERGE_FEATURE = REPO_ROOT / "scripts" / "merge-feature.sh"
QUEUE = ".beads/issues.jsonl"
TASK_ID = "proj-t4sk"
BRANCH = "r1/fix-something-proj-t4sk"

Issue = dict[str, Any]


def _isolated_env(**extra: str) -> dict[str, str]:
    # The pre-push hook runs pytest with GIT_DIR/GIT_INDEX_FILE of the real repo:
    # if inherited, they lead git out of the temporary repo into the real one.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, **extra}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=_isolated_env(), check=True, capture_output=True, text=True
    ).stdout.strip()


def _edge(issue_id: str, depends_on: str, author: str) -> dict[str, str]:
    return {
        "issue_id": issue_id,
        "depends_on_id": depends_on,
        "type": "blocks",
        "created_at": "2026-09-01T10:00:00Z",
        "created_by": author,
        "metadata": "{}",
    }


def _committed_issues() -> list[Issue]:
    """The queue as it lies in git (written by another machine)."""
    return [
        {
            "_type": "issue",
            "id": "proj-a1aa",
            "title": "Closed task with dependencies",
            "status": "closed",
            "updated_at": "2026-09-02T10:00:00Z",
            "dependencies": [
                _edge("proj-a1aa", "proj-x9zz", "example-dev"),
                _edge("proj-a1aa", "proj-b2bb", "example-dev"),
            ],
        },
        {
            "_type": "issue",
            "id": "proj-b2bb",
            "title": "Deferred task with a comment",
            "status": "deferred",
            "updated_at": "2026-08-27T19:16:09Z",
            "comments": [{"id": "0198-committed", "author": "example-dev", "text": "see the spec"}],
        },
        {
            "_type": "issue",
            "id": TASK_ID,
            "title": "Feature branch task",
            "status": "in_progress",
            "updated_at": "2026-10-10T08:00:00Z",
            "dependencies": [_edge(TASK_ID, "proj-a1aa", "example-dev")],
        },
        {
            "_type": "issue",
            "id": "proj-x9zz",
            "title": "Task with angle brackets",
            "description": "branch r1/feat-<id>",
            "status": "open",
            "updated_at": "2026-09-03T10:00:00Z",
        },
    ]


def _line(issue: Issue) -> str:
    return json.dumps(issue, ensure_ascii=False, separators=(",", ":"))


def _committed_line(issue: Issue) -> str:
    # Raw `bd export` escapes angle brackets, jq does not: git has seen both.
    # A line with < catches an implementation that rebuilds other lines through jq.
    return _line(issue).replace("<", "\\u003c")


def _local_export_line(issue: Issue, *, closed: bool) -> str:
    """The same task as `bd export` returns it on a machine with another bd version after `bd import`."""
    local = {k: v for k, v in issue.items() if k != "_type"}
    if "dependencies" in local:
        local["dependencies"] = [
            {**e, "created_by": "Other Dev"} for e in reversed(issue["dependencies"])
        ]
    if "comments" in local:
        local["comments"] = [{**c, "id": "0199-reimported"} for c in issue["comments"]]
    if local["status"] == "deferred":
        local["defer_until"] = "2026-10-01T00:00:00Z"
    if closed and local["id"] == TASK_ID:
        local |= {
            "status": "closed",
            "updated_at": "2026-10-10T12:00:00Z",
            "closed_at": "2026-10-10T12:00:00Z",
            "close_reason": "merged into main (merge-feature.sh)",
        }
    return _line(local)


def _closed_task_line() -> str:
    task = next(issue for issue in _committed_issues() if issue["id"] == TASK_ID)
    return _local_export_line(task, closed=True)


def _queue_text(issues: list[Issue]) -> str:
    return "".join(_committed_line(issue) + "\n" for issue in issues)


def _build(tmp_path: Path, queue: str, task_line: str) -> tuple[str, str]:
    """Run beads-queue-line.sh; returns (input, output) as bytes decoded to text."""
    queue_file = tmp_path / "queue.jsonl"
    task_file = tmp_path / "task.jsonl"
    queue_file.write_bytes(queue.encode("utf-8"))
    task_file.write_bytes((task_line + "\n").encode("utf-8"))
    result = subprocess.run(
        ["bash", str(QUEUE_LINE), str(queue_file), str(task_file)],
        env=_isolated_env(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return queue, result.stdout.decode("utf-8")


def _ids(lines: list[str]) -> list[str]:
    return [json.loads(line)["id"] for line in lines]


def _changed_ids(before: list[str], after: list[str]) -> list[str]:
    return [json.loads(new)["id"] for old, new in zip(before, after, strict=True) if old != new]


# ── scripts/beads-queue-line.sh ──


def test_replaces_only_the_task_line(tmp_path: Path) -> None:
    before, after = _build(tmp_path, _queue_text(_committed_issues()), _closed_task_line())

    old, new = before.splitlines(), after.splitlines()
    assert _changed_ids(old, new) == [TASK_ID]
    assert new[_ids(new).index(TASK_ID)] == _closed_task_line()


def test_missing_task_is_inserted_in_id_order(tmp_path: Path) -> None:
    # The task was created locally; its line never reached git.
    committed = [issue for issue in _committed_issues() if issue["id"] != TASK_ID]

    before, after = _build(tmp_path, _queue_text(committed), _closed_task_line())

    new = after.splitlines()
    assert _ids(new) == ["proj-a1aa", "proj-b2bb", TASK_ID, "proj-x9zz"]
    assert [line for line in new if json.loads(line)["id"] != TASK_ID] == before.splitlines()


def test_task_sorting_after_all_lines_is_appended(tmp_path: Path) -> None:
    committed = [issue for issue in _committed_issues() if issue["id"] < TASK_ID]
    line = _closed_task_line()

    before, after = _build(tmp_path, _queue_text(committed), line)

    assert after == before + line + "\n"


def test_empty_queue_gets_the_task_line(tmp_path: Path) -> None:
    _, after = _build(tmp_path, "", _closed_task_line())

    assert after == _closed_task_line() + "\n"


def test_task_already_closed_in_queue_is_left_untouched(tmp_path: Path) -> None:
    # The closure is already in the queue in a foreign form (with `_type`) — do not overwrite it with the local line.
    committed = _committed_issues()
    for issue in committed:
        if issue["id"] == TASK_ID:
            issue |= {"status": "closed", "close_reason": "closed on another machine"}

    before, after = _build(tmp_path, _queue_text(committed), _closed_task_line())

    assert after == before


def test_identical_line_gives_identical_queue(tmp_path: Path) -> None:
    committed = _committed_issues()
    queue = "".join(
        (_closed_task_line() if issue["id"] == TASK_ID else _committed_line(issue)) + "\n"
        for issue in committed
    )

    before, after = _build(tmp_path, queue, _closed_task_line())

    assert after == before


def test_other_lines_stay_byte_identical_in_large_cyrillic_queue(tmp_path: Path) -> None:
    # A real queue can be megabytes of non-ASCII text. jq in raw-string mode (-R) corrupts
    # multibyte characters at its read-buffer boundaries, damaging other tasks' lines.
    # Four short lines do not show it. The filler below is deliberately non-ASCII
    # (2-byte Cyrillic code points, generated so the source stays ASCII) to exercise
    # multibyte UTF-8 handling.
    two_byte = "".join(chr(0x0430 + i) for i in range(32))
    filler = [
        {
            "_type": "issue",
            "id": f"proj-c{n:03d}",
            "title": "Filler task",
            "description": chr(0x044F) * n + f" {two_byte} " * 60,
            "status": "open",
            "updated_at": "2026-09-01T10:00:00Z",
        }
        for n in range(400)
    ]
    issues = sorted(_committed_issues() + filler, key=lambda issue: issue["id"])

    before, after = _build(tmp_path, _queue_text(issues), _closed_task_line())

    assert _changed_ids(before.splitlines(), after.splitlines()) == [TASK_ID]


def test_queue_with_blank_line_is_refused(tmp_path: Path) -> None:
    # A blank line would shift the number of the replaced line — refusing beats corrupting.
    queue_file = tmp_path / "queue.jsonl"
    task_file = tmp_path / "task.jsonl"
    queue_file.write_text(_queue_text(_committed_issues()) + "\n", encoding="utf-8")
    task_file.write_text(_closed_task_line() + "\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(QUEUE_LINE), str(queue_file), str(task_file)],
        env=_isolated_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0


# ── scripts/merge-feature.sh end to end: close before merge, commit to the branch ──

GH_STUB = """#!/usr/bin/env bash
echo "$*" >> "$(dirname "$0")/../gh-calls"
case "$1 $2" in
  "pr view")
    if [ -n "${GH_VIEW_ERROR:-}" ]; then echo "$GH_VIEW_ERROR" >&2; exit 1; fi
    case "$*" in
      *reviewDecision*) echo "${GH_REVIEW_DECISION:-}" ;;
      *title*) echo "Fix something" ;;
      *) echo "${GH_PR_STATE:-OPEN}" ;;
    esac ;;
  "pr checks")
    if [ -n "${GH_NO_CHECKS:-}" ]; then echo "no checks reported on the '$3' branch"; exit 1; fi
    echo "all checks passed" ;;
  "pr comment")
    if [ -n "${GH_COMMENT_ERROR:-}" ]; then echo "$GH_COMMENT_ERROR" >&2; exit 1; fi ;;
  *) : ;;
esac
"""

BD_STUB = """#!/usr/bin/env bash
state="$(dirname "$0")/../bd-state"
store() {
  if [ -e "$state/closed" ]; then cat "$state/store_closed.jsonl"; else cat "$state/store_open.jsonl"; fi
}
auto_export() {
  top="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
  store > "$top/.beads/issues.jsonl"
  git -C "$top" add .beads/issues.jsonl
}
case "$1" in
  show)
    auto_export
    if [ -e "$state/closed" ]; then echo "Status: closed"; else echo "Status: in_progress"; fi ;;
  close)
    if [ -e "$state/closed" ]; then echo "refused" >&2; exit 1; fi
    touch "$state/closed"
    auto_export ;;
  export)
    auto_export
    store ;;
  *)
    auto_export ;;
esac
"""


def _stub(tmp_path: Path, name: str, body: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(body)
    stub.chmod(0o755)


def _write_store(tmp_path: Path, issues: list[Issue]) -> None:
    state = tmp_path / "bd-state"
    state.mkdir(exist_ok=True)
    for name, closed in (("store_open.jsonl", False), ("store_closed.jsonl", True)):
        # `bd export` line order is unstable — return them reversed.
        lines = [_local_export_line(issue, closed=closed) for issue in reversed(issues)]
        (state / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def feature_clone(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "dev@example.com")
    _git(work, "config", "user.name", "Dev")
    # Template placeholders are filled in on deployment — here we substitute them ourselves.
    (work / "scripts").mkdir()
    script = MERGE_FEATURE.read_text(encoding="utf-8")
    script = script.replace("MAIN_BRANCH='<main>'", "MAIN_BRANCH='main'")
    script = script.replace("MERGE_FLAG='<--merge|--squash|--rebase>'", "MERGE_FLAG='--merge'")
    # The local gate of --skip-ci: the test decides (TEST_LOCAL_GATE=false — a red gate).
    script = script.replace("LOCAL_GATE_CMD=''", 'LOCAL_GATE_CMD="${TEST_LOCAL_GATE:-true}"')
    (work / "scripts" / "merge-feature.sh").write_text(script, encoding="utf-8")
    shutil.copy(QUEUE_LINE, work / "scripts" / "beads-queue-line.sh")
    (work / ".beads").mkdir()
    (work / QUEUE).write_text(_queue_text(_committed_issues()), encoding="utf-8")
    (work / "devlog.md").write_text("# devlog\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "HEAD:main")
    _git(work, "checkout", "-b", BRANCH)
    (work / "devlog.md").write_text("# devlog\n\nsession entry\n", encoding="utf-8")
    _git(work, "commit", "-am", "docs: devlog")
    _write_store(tmp_path, _committed_issues())
    _stub(tmp_path, "gh", GH_STUB)
    _stub(tmp_path, "bd", BD_STUB)
    return work


def _run_merge(
    clone: Path, *args: str, accepted_by: str | None = "Ann Owner", **env_extra: str
) -> subprocess.CompletedProcess[str]:
    env = _isolated_env(PATH=f"{clone.parent / 'bin'}{os.pathsep}{os.environ['PATH']}", **env_extra)
    accept = ["--accepted-by", accepted_by] if accepted_by is not None else []
    return subprocess.run(
        ["bash", "scripts/merge-feature.sh", BRANCH, *args, *accept],
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_merge_feature_commits_only_closed_task_line_to_branch(feature_clone: Path) -> None:
    before = _git(feature_clone, "show", f"main:{QUEUE}").splitlines()

    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(feature_clone, "log", "-1", "--format=%s", BRANCH) == f"chore(beads): close {TASK_ID}"
    after = _git(feature_clone, "show", f"{BRANCH}:{QUEUE}").splitlines()
    assert _changed_ids(before, after) == [TASK_ID]
    assert json.loads(after[_ids(after).index(TASK_ID)])["status"] == "closed"
    # The full bd export that overwrote the file in the working tree neither reached the branch nor stayed behind.
    assert _git(feature_clone, "status", "--porcelain") == ""


def _gh_calls(clone: Path) -> str:
    calls = clone.parent / "gh-calls"
    return calls.read_text() if calls.exists() else ""


def test_run_from_another_branch_commits_queue_line_to_the_feature_branch(feature_clone: Path) -> None:
    _git(feature_clone, "checkout", "-q", "main")
    main_before = _git(feature_clone, "rev-parse", "main")

    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(feature_clone, "log", "-1", "--format=%s", BRANCH) == f"chore(beads): close {TASK_ID}"
    assert _git(feature_clone, "rev-parse", "main") == main_before


def test_closed_pr_is_refused_and_task_stays_open(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_PR_STATE="CLOSED")

    assert result.returncode != 0
    assert "closed" in (result.stdout + result.stderr).lower()
    assert not (feature_clone.parent / "bd-state" / "closed").exists()
    assert "pr merge" not in _gh_calls(feature_clone)


def test_gh_error_is_not_taken_for_missing_pr(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "Title", GH_VIEW_ERROR="error connecting to api.github.com")

    assert result.returncode != 0
    assert "pr create" not in _gh_calls(feature_clone)
    assert not (feature_clone.parent / "bd-state" / "closed").exists()


def test_devlog_changed_only_on_main_does_not_pass_the_gate(feature_clone: Path) -> None:
    # The branch never touched devlog.md; main moved its own devlog after the branch was cut.
    _git(feature_clone, "checkout", "-q", "main")
    _git(feature_clone, "checkout", "-q", "-B", BRANCH)
    _git(feature_clone, "checkout", "-q", "main")
    (feature_clone / "devlog.md").write_text("# devlog\n\nmain-only entry\n", encoding="utf-8")
    _git(feature_clone, "commit", "-qam", "docs: devlog on main")
    _git(feature_clone, "push", "-q", "origin", "main")
    _git(feature_clone, "checkout", "-q", BRANCH)

    result = _run_merge(feature_clone)

    assert result.returncode != 0
    assert "devlog.md" in result.stdout + result.stderr


# ── the human's acceptance, team mode, merging without CI ──


def _merge_call(clone: Path) -> str:
    calls = _gh_calls(clone)
    assert "pr merge" in calls, calls
    return calls[calls.index("pr merge"):]


def _commit_on_branch(clone: Path, path: str, text: str) -> None:
    (clone / path).parent.mkdir(parents=True, exist_ok=True)
    (clone / path).write_text(text, encoding="utf-8")
    _git(clone, "add", path)
    _git(clone, "commit", "-qm", f"chore: {path}")


@pytest.mark.parametrize("accepted_by", [None, "", "   "])
def test_refuses_without_human_acceptance(feature_clone: Path, accepted_by: str | None) -> None:
    result = _run_merge(feature_clone, accepted_by=accepted_by)

    assert result.returncode != 0
    assert "--accepted-by" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)
    assert not (feature_clone.parent / "bd-state" / "closed").exists()


def test_acceptance_recorded_as_comment_and_trailer(feature_clone: Path) -> None:
    result = _run_merge(feature_clone)

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _gh_calls(feature_clone)
    assert "pr comment" in calls
    assert calls.index("pr comment") < calls.index("pr merge")
    assert "Accepted by Ann Owner — merging via merge-feature.sh" in calls
    merge = _merge_call(feature_clone)
    assert "--merge --body Fix something\n\nAccepted-by: Ann Owner" in merge
    assert "CI-skipped" not in merge


def test_failed_acceptance_comment_cancels_merge(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_COMMENT_ERROR="HTTP 502")

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
    assert "reviewDecision" in _gh_calls(feature_clone)
    assert "Accepted-by: Ann Owner" in _merge_call(feature_clone)


def test_solo_owner_needs_no_approval(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, GH_REVIEW_DECISION="REVIEW_REQUIRED")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "reviewDecision" not in _gh_calls(feature_clone)


def test_skip_ci_merges_on_local_gate_with_loud_record(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--skip-ci", "Actions disabled: billing", GH_NO_CHECKS="1")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = _gh_calls(feature_clone)
    assert "--watch" not in calls
    assert "Merged WITHOUT CI by Ann Owner: Actions disabled: billing" in calls
    assert "no checks reported" in calls
    merge = _merge_call(feature_clone)
    assert "Accepted-by: Ann Owner\nCI-skipped: Actions disabled: billing" in merge


def test_skip_ci_refuses_on_red_local_gate(feature_clone: Path) -> None:
    result = _run_merge(feature_clone, "--skip-ci", "billing", GH_NO_CHECKS="1", TEST_LOCAL_GATE="false")

    assert result.returncode != 0
    assert "local gate failed" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_skip_ci_needs_reason_and_acceptance(feature_clone: Path) -> None:
    no_reason = _run_merge(feature_clone, "--skip-ci", " ")
    no_accept = _run_merge(feature_clone, "--skip-ci", "billing", accepted_by=None)

    for result in (no_reason, no_accept):
        assert result.returncode != 0
    assert "reason" in no_reason.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


def test_skip_ci_refused_at_team_level(feature_clone: Path) -> None:
    _commit_on_branch(feature_clone, ".claude/fences.env", "FENCE_LEVEL=team\n")

    result = _run_merge(feature_clone, "--skip-ci", "billing", GH_NO_CHECKS="1", GH_REVIEW_DECISION="APPROVED")

    assert result.returncode != 0
    assert "team" in result.stderr
    assert "pr merge" not in _gh_calls(feature_clone)


@pytest.mark.parametrize(
    ("branch", "bd_id"),
    [
        ("r12/feat-x-proj-t4sk", "proj-t4sk"),
        ("r12/feat-x-proj-t4sk.3", "proj-t4sk.3"),
        ("r12/feat-lite-20261021-p3", ""),  # a date and a version are not a task
        ("r12/feat-lite-20261021-", ""),
        ("r12/fix-something-t4sk", ""),  # a short id without the prefix is not taken
        ("docs/readme-proj-t4sk", ""),  # only release-train branches carry an id
    ],
)
def test_bd_id_only_from_full_id_at_branch_end(feature_clone: Path, branch: str, bd_id: str) -> None:
    result = subprocess.run(
        ["bash", "scripts/merge-feature.sh", branch, "--print-bd-id"],
        cwd=feature_clone,
        env=_isolated_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == bd_id

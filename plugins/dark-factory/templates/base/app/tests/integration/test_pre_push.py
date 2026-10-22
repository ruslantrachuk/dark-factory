"""The pre-push test gate: patterns that match no tracked file are a gate that never fires — it says so."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / ".githooks" / "pre-push"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    (work / ".githooks").mkdir()
    shutil.copy(HOOK, work / ".githooks" / "pre-push")
    _git(work, "config", "core.hooksPath", ".githooks")
    _git(work, "remote", "add", "origin", str(origin))
    for name, text in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text)
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "init")
    return work


def test_patterns_matching_no_file_are_said_out_loud(tmp_path: Path) -> None:
    work = _repo(tmp_path, {"src/index.ts": "export {}\n", "package.json": "{}\n"})

    result = _git(work, "push", "-q", "origin", "main")

    assert "CODE_PATTERNS match no tracked file" in result.stderr


def test_patterns_matching_the_layout_stay_quiet(tmp_path: Path) -> None:
    work = _repo(tmp_path, {"app/src/x.txt": "x\n", "README.md": "r\n"})
    _git(work, "push", "-q", "--no-verify", "origin", "main")  # the code itself is not under test here
    (work / "README.md").write_text("r2\n")
    _git(work, "commit", "-qam", "docs")

    result = _git(work, "push", "-q", "origin", "main")

    assert "match no tracked file" not in result.stderr

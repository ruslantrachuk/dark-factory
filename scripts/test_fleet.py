#!/usr/bin/env python3
"""Tests for fleet.py: python3 scripts/test_fleet.py"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet  # noqa: E402

REGISTRY = """# Registry

| Project | Tracker id | Repository | Client |
|---|---|---|---|
| _Example (delete this row):_ Panel | `proj-a1b` | `~/panel` (github.com/o/panel) | Example Ltd |
| Shop | `shop-1` | `~/code/shop` (github.com/o/shop) | Shop Ltd |
| Audit hub | `hub` | — | Client |
| **Billing** | `bill` | `/srv/billing` | Client |

| Other table | Repository |
|---|---|
| Notes | `~/notes` |
"""


class ParseTest(unittest.TestCase):
    def test_registry_rows_with_paths_only(self):
        rows = fleet.parse_registry(REGISTRY)
        self.assertEqual(rows, [("Shop", "~/code/shop"), ("Billing", "/srv/billing"), ("Notes", "~/notes")])

    def test_projects_file(self):
        rows = fleet.parse_projects_file("# server A\n/srv/shop\n\n/srv/billing  # second\n")
        self.assertEqual(rows, [("shop", "/srv/shop"), ("billing", "/srv/billing")])

    def test_env_file_takes_shell_default(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "config.env"
            f.write_text('# c\nDESK_TMUX="${DESK_TMUX:-shop-feedback}"\nSESSION_NAME="Shop server"\nX=1 # n\n')
            self.assertEqual(fleet.read_env(f),
                             {"DESK_TMUX": "shop-feedback", "SESSION_NAME": "Shop server", "X": "1"})

    def test_duplicates_and_filter(self):
        rows = [("a", "/srv/shop"), ("b", "/srv/shop"), ("c", "/srv/billing")]
        self.assertEqual([p.slug for p in fleet.load_projects(rows)], ["shop", "billing"])
        self.assertEqual([p.slug for p in fleet.load_projects(rows, "billing")], ["billing"])


class UnitsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "shop/.claude/factory").mkdir(parents=True)
        (self.root / "shop/.claude/factory/session.env").write_text(
            'SESSION_NAME="Shop server"\nSESSION_ARGS="--permission-mode auto"\n')
        self.p = fleet.load_projects([("Shop", str(self.root / "shop"))])[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_unit_runs_remote_control_in_own_tmux(self):
        text = fleet.session_unit(self.p, "/bin/claude", "/bin/tmux")
        self.assertIn("ExecStart=/bin/tmux -L df-shop new-session -d -s session", text)
        self.assertIn("remote-control --name 'Shop server' --permission-mode auto", text.replace("'\"'\"'", "'"))
        self.assertIn("ExecStop=/bin/tmux -L df-shop kill-server", text)
        self.assertIn("Restart=always", text)

    def test_desk_unit_only_with_feedback_desk(self):
        self.assertEqual(list(fleet.units_for(self.p, "c", "t")), ["df-shop-session.service"])
        (self.root / "shop/scripts").mkdir()
        (self.root / "shop/scripts/feedback-desk.sh").write_text("#!/bin/sh\n")
        units = fleet.units_for(self.p, "c", "t")
        self.assertIn("df-shop-desk.service", units)
        self.assertIn("KillMode=process", units["df-shop-desk.service"])

    def test_unit_path_drops_per_shell_entries(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = "/run/user/1/fnm/bin:/usr/bin:/bin"
        try:
            self.assertEqual(fleet.unit_path(), "/usr/bin:/bin")
        finally:
            os.environ["PATH"] = old

    def test_dry_run_writes_nothing(self):
        units = self.root / "units"
        fleet.UNIT_DIR = units
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(fleet.shutil, "which", lambda n: f"/bin/{n}"):
            fleet.provision([self.p], dry=True)
        self.assertFalse(units.exists())
        self.assertIn("would run: loginctl enable-linger", out.getvalue())


class DriftTest(unittest.TestCase):
    def test_counts_template_commits_since_base_sha(self):
        with tempfile.TemporaryDirectory() as d:
            canon, proj = Path(d) / "canon", Path(d) / "proj"
            (canon / "templates").mkdir(parents=True)
            git = ["git", "-C", str(canon), "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(["git", "init", "-q", str(canon)], check=True)

            def commit(name):
                (canon / name).write_text(name)
                subprocess.run([*git, "add", "-A"], check=True)
                subprocess.run([*git, "commit", "-qm", name], check=True)
                return subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

            base = commit("templates/a")
            commit("templates/b")
            commit("docs-only")
            (proj / ".harness").mkdir(parents=True)
            (proj / ".harness/base-sha").write_text(base + "\n")
            fleet.FACTORY = canon
            p = fleet.Project("p", proj, "p")
            self.assertEqual(fleet.check_drift(p), (False, "1 template commits behind (harness-diff.sh)"))
            (proj / ".harness/base-sha").write_text("0" * 40)
            self.assertFalse(fleet.check_drift(p)[0])


if __name__ == "__main__":
    unittest.main()

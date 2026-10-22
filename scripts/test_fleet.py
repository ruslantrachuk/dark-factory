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
        self.assertIn('ExecStart="/bin/tmux" -L df-shop new-session -d -s session', text)
        # one double-quoted word for systemd, shell quoting inside it for tmux
        self.assertIn(""""/bin/claude remote-control --name 'Shop server' --permission-mode auto --spawn worktree"\n""", text)
        self.assertIn('ExecStop="/bin/tmux" -L df-shop kill-server', text)
        self.assertIn("Restart=always", text)

    def test_session_unit_stops_restarting_when_it_cannot_start(self):
        text = fleet.session_unit(self.p, "/bin/claude", "/bin/tmux")
        unit_section = text.split("[Service]")[0]
        self.assertIn("StartLimitIntervalSec=", unit_section)
        self.assertIn("StartLimitBurst=5", unit_section)

    def test_unit_quoting_escapes_systemd_specials(self):
        self.p.settings["SESSION_NAME"] = 'Shop "50%" $HOME'
        text = fleet.session_unit(self.p, "/bin/claude", "/bin/tmux")
        self.assertIn("""--name 'Shop \\"50%%\\" $$HOME'""", text)

    def test_desk_units_only_with_feedback_desk(self):
        self.assertEqual(list(fleet.units_for(self.p, "c", "t")), ["df-shop-session.service"])
        (self.root / "shop/scripts").mkdir()
        (self.root / "shop/scripts/feedback-desk.sh").write_text("#!/bin/sh\n")
        units = fleet.units_for(self.p, "c", "t")
        self.assertEqual(sorted(units), ["df-shop-desk-watch.service", "df-shop-desk-watch.timer",
                                         "df-shop-desk.service", "df-shop-session.service"])
        self.assertIn("KillMode=process", units["df-shop-desk.service"])

    def test_desk_watch_reruns_idempotent_up_every_5_minutes(self):
        (self.root / "shop/scripts").mkdir()
        (self.root / "shop/scripts/feedback-desk.sh").write_text("#!/bin/sh\n")
        units = fleet.units_for(self.p, "c", "t")
        watch, timer = units["df-shop-desk-watch.service"], units["df-shop-desk-watch.timer"]
        self.assertIn('/shop/scripts/feedback-desk.sh" up', watch)
        self.assertIn("KillMode=process", watch)  # the tmux session it starts outlives the oneshot
        self.assertNotIn("[Install]", watch)
        self.assertIn("OnUnitActiveSec=5min", timer)
        self.assertIn("Unit=df-shop-desk-watch.service", timer)
        self.assertIn("WantedBy=timers.target", timer)

    def test_unit_path_drops_per_shell_entries(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = "/run/user/1/fnm/bin:/usr/bin:/bin"
        try:
            self.assertEqual(fleet.unit_path(), "/usr/bin:/bin")
        finally:
            os.environ["PATH"] = old

    def provision(self, projects, dry=True, linux=True):
        fleet.UNIT_DIR = self.root / "units"
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stderr", err), \
                mock.patch.object(fleet.shutil, "which", lambda n: f"/bin/{n}"), \
                mock.patch.object(fleet, "platform_ok", lambda: linux):
            code = fleet.provision(projects, dry=dry)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.provision([self.p])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "units").exists())
        self.assertIn("would run: loginctl enable-linger", out)

    def test_enables_timer_not_watch_service(self):
        (self.root / "shop/scripts").mkdir()
        (self.root / "shop/scripts/feedback-desk.sh").write_text("#!/bin/sh\n")
        _, out, _ = self.provision([self.p])
        enable = next(ln for ln in out.splitlines() if " enable --now " in ln)
        self.assertIn("df-shop-desk-watch.timer", enable)
        self.assertNotIn("df-shop-desk-watch.service", enable)

    def test_refuses_project_with_disallowed_session_args(self):
        (self.root / "bad/.claude/factory").mkdir(parents=True)
        (self.root / "bad/.claude/factory/session.env").write_text(
            'SESSION_ARGS="--permission-mode bypassPermissions"\n')
        bad = fleet.load_projects([("Bad", str(self.root / "bad"))])[0]
        code, out, err = self.provision([self.p, bad])
        self.assertEqual(code, 1)
        self.assertIn("Bad: not provisioned", err)
        self.assertIn("bypassPermissions", err)
        self.assertIn("df-shop-session.service", out)  # the other project is still provisioned
        self.assertNotIn("df-bad-", out)

    def test_refuses_off_linux(self):
        code, out, err = self.provision([self.p], linux=False)
        self.assertEqual(code, 1)
        self.assertIn("systemd user instance", err)
        self.assertEqual(out, "")


class SessionArgsTest(unittest.TestCase):
    def test_accepts_allowlisted(self):
        self.assertEqual(fleet.parse_session_args(""), ["--spawn", "worktree"])
        self.assertEqual(fleet.parse_session_args("--permission-mode auto"),
                         ["--permission-mode", "auto", "--spawn", "worktree"])
        self.assertEqual(fleet.parse_session_args("--permission-mode=acceptEdits --spawn same-dir"),
                         ["--permission-mode", "acceptEdits", "--spawn", "same-dir"])
        for mode in ("default", "plan"):
            self.assertIn(mode, fleet.parse_session_args(f"--permission-mode {mode}"))

    def test_refuses_everything_else(self):
        for raw in ("--permission-mode bypassPermissions", "--permission-mode dontAsk",
                    "--dangerously-skip-permissions", "--permission-mode", "--permission-mode auto --permission-mode plan",
                    "--model claude-opus-5-5", "--debug-file /tmp/x", "--spawn worktree; rm -rf ~", "--name x",
                    "auto", "--permission-mode 'auto", "--spawn=everywhere"):
            with self.subTest(raw=raw), self.assertRaises(fleet.SettingsError):
                fleet.parse_session_args(raw)

    def test_session_name_without_control_chars(self):
        self.assertEqual(fleet.check_session_name("Café server"), "Café server")
        for name in ("", "  ", "a\tb", "a\x1bb"):
            with self.subTest(name=name), self.assertRaises(fleet.SettingsError):
                fleet.check_session_name(name)


class SessionCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        fleet.UNIT_DIR = Path(self.tmp.name)
        (fleet.UNIT_DIR / "df-shop-session.service").write_text("")
        self.p = fleet.Project("Shop", Path("/srv/shop"), "shop")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, active: bool, screen: str):
        def sh(cmd, cwd=None, timeout=20):
            if cmd[:2] == ["systemctl", "--user"]:
                return (0, "active") if active else (3, "failed")
            self.assertEqual(cmd, ["tmux", "-L", "df-shop", "capture-pane", "-p", "-t", "session"])
            return 0, screen
        with mock.patch.object(fleet, "sh", sh):
            return fleet.check_session(self.p)

    def test_active_and_working(self):
        self.assertEqual(self.check(True, "Remote Control active\n> ")[0], True)

    def test_active_but_waiting_for_trust_or_login(self):
        for screen in ("Do you trust the files in this folder?\n❯ 1. Yes, I trust this folder", "Please run /login"):
            with self.subTest(screen=screen):
                ok, text = self.check(True, screen)
                self.assertFalse(ok)
                self.assertIn("login or folder-trust prompt", text)

    def test_failed_points_at_start_limit(self):
        ok, text = self.check(False, "")
        self.assertFalse(ok)
        self.assertIn("reset-failed df-shop-session.service", text)


class UnprovisionTest(unittest.TestCase):
    def test_removes_only_this_projects_units(self):
        with tempfile.TemporaryDirectory() as d:
            fleet.UNIT_DIR = Path(d)
            for n in ("df-shop-session.service", "df-shop-desk-watch.timer", "df-shop-x-session.service"):
                (Path(d) / n).write_text("")
            calls = []
            with redirect_stdout(io.StringIO()), mock.patch.object(fleet, "run", lambda cmd, dry: calls.append(cmd) or 0):
                fleet.unprovision([fleet.Project("Shop", Path("/srv/shop"), "shop")], dry=False)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["df-shop-x-session.service"])
            self.assertEqual(calls[0], ["systemctl", "--user", "disable", "--now",
                                        "df-shop-session.service", "df-shop-desk-watch.timer"])


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

#!/usr/bin/env python3
"""Tests for fleet.py: python3 plugins/dark-factory/scripts/test_fleet.py"""
import io
import os
import subprocess
import sys
import tempfile
import time
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


    def test_same_directory_name_in_two_places_is_refused(self):
        rows = [("Gamma", "/a/Gamma"), ("Gamma", "/b/Gamma")]
        with self.assertRaises(fleet.ProjectsError) as cm:
            fleet.load_projects(rows)
        self.assertIn("/a/Gamma", str(cm.exception))
        self.assertIn("/b/Gamma", str(cm.exception))
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch("sys.stderr", out):
            f = Path(d) / "projects"
            f.write_text("/a/Gamma\n/b/Gamma\n")
            self.assertEqual(fleet.main(["projects", "--projects", str(f)]), 2)
        self.assertIn("/b/Gamma", out.getvalue())

    def test_malformed_session_env_is_a_settings_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("good", 'SESSION_NAME="Good"\n'), ("bad", "SESSION_NAME=Bob's server\n")):
                (Path(d) / name / ".claude/factory").mkdir(parents=True)
                (Path(d) / name / ".claude/factory/session.env").write_text(text)
            projects = fleet.load_projects([("good", f"{d}/good"), ("bad", f"{d}/bad")])
            self.assertEqual([p.slug for p in projects], ["good", "bad"])
            self.assertEqual(projects[0].session_name, "Good")
            self.assertIn("session.env", projects[1].settings_error)
            with self.assertRaises(fleet.SettingsError):
                fleet.units_for(projects[1], "/usr/bin/claude", "/usr/bin/tmux")
            ok, text = fleet.check_session(projects[1])
            self.assertFalse(ok)
            self.assertIn("session.env", text)

    def test_malformed_desk_config_fails_only_that_check(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "scripts").mkdir()
            (d / "scripts/feedback-desk.sh").write_text("#!/bin/sh\necho running\n")
            (d / "scripts/feedback-desk.sh").chmod(0o755)
            (d / ".claude/feedback-desk").mkdir(parents=True)
            (d / ".claude/feedback-desk/config.env").write_text("DESK_TMUX=it's\n")
            ok, text = fleet.check_desk(fleet.Project("Shop", d, "shop"))
            self.assertFalse(ok)
            self.assertIn("config.env", text)


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
        self.assertNotIn('DF_UNATTENDED', text)  # a person drives it from claude.ai: the guard asks, not denies
        # one double-quoted word for systemd, shell quoting inside it for tmux
        self.assertIn(""""/bin/claude remote-control --name 'Shop server' --permission-mode auto --spawn worktree"""
                      """ --capacity 3"\n""", text)
        self.assertIn('ExecStop="/bin/tmux" -L df-shop kill-server', text)
        self.assertIn("Restart=always", text)

    def test_session_unit_stops_restarting_when_it_cannot_start(self):
        text = fleet.session_unit(self.p, "/bin/claude", "/bin/tmux")
        unit_section = text.split("[Service]")[0]
        self.assertIn("StartLimitIntervalSec=", unit_section)
        self.assertIn("StartLimitBurst=5", unit_section)

    def test_units_notify_on_failure_and_skip_network_online(self):
        (self.root / "shop/scripts").mkdir()
        (self.root / "shop/scripts/feedback-desk.sh").write_text("#!/bin/sh\n")
        for name, text in fleet.units_for(self.p, "c", "t").items():
            with self.subTest(unit=name):
                self.assertNotIn("network-online", text)  # a no-op in a user instance
                if name.endswith(".service"):
                    self.assertIn("OnFailure=df-notify@%n.service", text.split("[Service]")[0])

    def test_server_units_notify_and_watch(self):
        units = fleet.server_units("/usr/bin/python3", ["--projects", "/home/u/.config/dark-factory/projects"])
        self.assertEqual(sorted(units), ["df-fleet-watch.service", "df-fleet-watch.timer", "df-notify@.service"])
        notify = units["df-notify@.service"]
        self.assertIn('"/usr/bin/python3" ', notify)
        self.assertIn('/fleet.py" "notify" %i', notify)
        self.assertNotIn("OnFailure", notify)  # a failing notifier must not notify about itself
        self.assertNotIn("[Install]", notify)
        watch = units["df-fleet-watch.service"]
        self.assertIn('"--projects" "/home/u/.config/dark-factory/projects" "status" "--notify"', watch)
        self.assertIn("FACTORY_CANON=", watch)
        self.assertIn("OnUnitActiveSec=15min", units["df-fleet-watch.timer"])
        self.assertIn("Unit=df-fleet-watch.service", units["df-fleet-watch.timer"])

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
                mock.patch.object(fleet, "platform_ok", lambda: linux), \
                mock.patch.object(fleet, "run", self.fake_run):  # never the real systemctl/loginctl
            code = fleet.provision(projects, dry=dry)
        return code, out.getvalue(), err.getvalue()

    @staticmethod
    def fake_run(cmd, dry):
        print(("would run: " if dry else "$ ") + " ".join(cmd))
        return 0

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
        self.assertIn("df-fleet-watch.timer", enable)
        self.assertNotIn("df-notify@", enable)  # a template, started by OnFailure only
        self.assertIn("would write " + str(self.root / "units/df-notify@.service"), out)

    def test_writes_server_units(self):
        code, out, _ = self.provision([self.p], dry=False)
        self.assertEqual(code, 0)
        self.assertIn("$ loginctl enable-linger", out)  # printed by the fake; nothing ran
        written = sorted(p.name for p in (self.root / "units").iterdir())
        self.assertEqual(written, ["df-fleet-watch.service", "df-fleet-watch.timer", "df-notify@.service",
                                   "df-shop-session.service"])

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
        self.assertEqual(fleet.parse_session_args(""), ["--spawn", "worktree", "--capacity", "3"])
        self.assertEqual(fleet.parse_session_args("--permission-mode auto"),
                         ["--permission-mode", "auto", "--spawn", "worktree", "--capacity", "3"])
        self.assertEqual(fleet.parse_session_args("--permission-mode=acceptEdits --spawn same-dir"),
                         ["--permission-mode", "acceptEdits", "--spawn", "same-dir", "--capacity", "3"])
        for mode in ("default", "plan"):
            self.assertIn(mode, fleet.parse_session_args(f"--permission-mode {mode}"))

    def test_capacity_1_to_8_default_3(self):
        self.assertEqual(fleet.parse_session_args("--capacity 8"), ["--capacity", "8", "--spawn", "worktree"])
        self.assertEqual(fleet.parse_session_args("--capacity=1 --spawn same-dir"),
                         ["--capacity", "1", "--spawn", "same-dir"])
        self.assertEqual(fleet.parse_session_args("--spawn session"), ["--spawn", "session"])  # not used there
        for raw in ("--capacity 0", "--capacity 9", "--capacity 32", "--capacity x", "--capacity",
                    "--capacity 2 --spawn session"):
            with self.subTest(raw=raw), self.assertRaises(fleet.SettingsError):
                fleet.parse_session_args(raw)

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

    def test_server_units_go_with_the_last_project(self):
        with tempfile.TemporaryDirectory() as d:
            fleet.UNIT_DIR = Path(d)
            server = ("df-notify@.service", "df-fleet-watch.service", "df-fleet-watch.timer")
            for n in ("df-shop-session.service", "df-bill-session.service", *server):
                (Path(d) / n).write_text("")
            calls = []
            with redirect_stdout(io.StringIO()), mock.patch.object(fleet, "run", lambda cmd, dry: calls.append(cmd) or 0):
                fleet.unprovision([fleet.Project("Shop", Path("/srv/shop"), "shop")], dry=False)
                self.assertTrue(all((Path(d) / n).exists() for n in server))  # billing still runs here
                fleet.unprovision([fleet.Project("Bill", Path("/srv/bill"), "bill")], dry=False)
            self.assertEqual(list(Path(d).iterdir()), [])
            self.assertNotIn("df-notify@.service", calls[-2])  # templates are not disabled
            self.assertIn("df-fleet-watch.timer", calls[-2])


    def test_project_removed_from_the_file_is_found_by_its_units(self):
        with tempfile.TemporaryDirectory() as d:
            fleet.UNIT_DIR = Path(d)
            for n in ("df-shop-session.service", "df-shop-desk.service", "df-bill-session.service"):
                (Path(d) / n).write_text("")
            projects = Path(d) / "projects"
            projects.write_text("/srv/bill\n")  # shop's line is already gone
            calls = []
            with redirect_stdout(io.StringIO()), mock.patch.object(fleet, "run", lambda cmd, dry: calls.append(cmd) or 0):
                self.assertEqual(fleet.main(["unprovision", "--projects", str(projects), "--project", "Shop"]), 0)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["df-bill-session.service", "projects"])
            self.assertEqual(calls[0][-2:], ["df-shop-session.service", "df-shop-desk.service"])
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(fleet.main(["unprovision", "--projects", str(projects), "--project", "nosuch"]), 2)


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("FLEET_NOTIFY_CMD", None)
        self.patches = [mock.patch.object(fleet, "FLEET_ENV", self.d / "fleet.env"),
                        mock.patch.object(fleet, "FLEET_STATE", self.d / "state/fleet-watch.json")]
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_sends_through_the_configured_command_on_stdin(self):
        out = self.d / "sent.txt"
        (self.d / "fleet.env").write_text(f"FLEET_NOTIFY_CMD='cat > {out}'\n")
        self.assertEqual(fleet.notify("df-shop-session.service failed"), 0)
        self.assertEqual(out.read_text(), "df-shop-session.service failed")

    def test_without_a_command_writes_to_the_journal(self):
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(fleet.notify("x failed"), 0)
        self.assertIn("dark factory: x failed", err.getvalue())

    def test_failing_command_still_reaches_the_journal(self):
        (self.d / "fleet.env").write_text("FLEET_NOTIFY_CMD='exit 3'\n")
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(fleet.notify("x failed"), 1)
        self.assertIn("dark factory: x failed", err.getvalue())

    def test_notify_command_line(self):
        with mock.patch.object(fleet, "notify", return_value=0) as n, mock.patch.object(fleet.socket, "gethostname",
                                                                                      return_value="vps"):
            self.assertEqual(fleet.main(["notify", "df-shop-session.service"]), 0)
        self.assertEqual(n.call_args.args[0],
                         "vps: df-shop-session.service failed — journalctl --user -u df-shop-session.service")

    def test_changes_only(self):
        self.assertEqual(fleet.changes({}, {}), [])
        self.assertEqual(fleet.changes({"Shop: On-call": "a"}, {"Shop: On-call": "b"}), [])  # still failing
        self.assertEqual(fleet.changes({}, {"Shop: On-call": "asks to log in"}), ["○ Shop: On-call — asks to log in"])
        self.assertEqual(fleet.changes({"Shop: On-call": "a"}, {}), ["● Shop: On-call — fine again"])

    def run_status(self, desk):
        p = fleet.Project("Shop", self.d, "shop")
        with mock.patch.multiple(fleet, check_quota=lambda: None, check_session=lambda p: (True, "active"),
                                 check_desk=lambda p: desk, check_monitor=lambda p, now: None,
                                 check_queue=lambda p: None, check_drift=lambda p: (False, "1 behind"),
                                 check_worktrees=lambda p, now, days: None), \
                mock.patch.object(fleet, "notify", return_value=0) as n, redirect_stdout(io.StringIO()):
            fleet.status([p], notify_owner=True)
        return [c.args[0] for c in n.call_args_list]

    def test_failed_notification_is_retried_by_the_next_run(self):
        login = (False, "running but asks to log in — attach and run /login")
        p = fleet.Project("Shop", self.d, "shop")

        def run(rc):
            with mock.patch.multiple(fleet, check_quota=lambda: None, check_session=lambda p: (True, "active"),
                                     check_desk=lambda p: login, check_monitor=lambda p, now: None,
                                     check_queue=lambda p: None, check_drift=lambda p: None,
                                     check_worktrees=lambda p, now, days: None), \
                    mock.patch.object(fleet, "notify", return_value=rc) as n, redirect_stdout(io.StringIO()):
                fleet.status([p], notify_owner=True)
            return n.call_count

        self.assertEqual(run(1), 1)  # delivery failed
        self.assertFalse(fleet.FLEET_STATE.exists())
        self.assertEqual(run(0), 1)  # reported again, now delivered
        self.assertEqual(run(0), 0)  # and then silent

    def test_status_notify_on_state_changes_only(self):
        login = (False, "running but asks to log in — attach and run /login")
        self.assertEqual(self.run_status((True, "running")), [])  # template drift is not a page
        [msg] = self.run_status(login)
        self.assertIn("○ Shop: On-call — running but asks to log in", msg)
        self.assertEqual(self.run_status(login), [])  # unchanged — silent
        [msg] = self.run_status((True, "running"))
        self.assertIn("● Shop: On-call — fine again", msg)


class WorktreeTest(unittest.TestCase):
    """A real repository: origin (bare) → clone with worktrees in every state gc has to tell apart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.origin, self.repo = d / "origin.git", d / "repo"
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]

        def git(*args, cwd=None):
            subprocess.run([*g, *args], cwd=cwd or self.repo, check=True, capture_output=True)

        subprocess.run([*g, "init", "-q", "--bare", str(self.origin)], check=True)
        subprocess.run([*g, "clone", "-q", str(self.origin), str(self.repo)], check=True, capture_output=True)
        (self.repo / "a").write_text("a")
        git("add", "-A")
        git("commit", "-qm", "a")
        for name in ("merged", "dirty-merged", "open"):
            git("worktree", "add", "-q", "-b", name, str(d / name))
        (d / "open/b").write_text("b")
        git("add", "-A", cwd=d / "open")
        git("commit", "-qm", "b", cwd=d / "open")
        (d / "dirty-merged/scratch").write_text("x")
        git("push", "-q", "origin", "main")
        git("remote", "set-head", "origin", "main")
        self.d = d
        self.p = fleet.Project("Repo", self.repo, "repo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_state_of_each_worktree(self):
        trees = {t.branch: t for t in fleet.list_worktrees(self.repo, time.time(), busy=[])}
        self.assertEqual(sorted(trees), ["dirty-merged", "merged", "open"])
        self.assertTrue(trees["merged"].removable)
        self.assertFalse(trees["dirty-merged"].clean)
        self.assertFalse(trees["dirty-merged"].removable)
        self.assertFalse(trees["open"].merged)
        busy = fleet.list_worktrees(self.repo, time.time(), busy=[self.d / "merged/sub"])
        self.assertFalse(next(t for t in busy if t.branch == "merged").removable)  # a live session is inside

    def test_status_reports_stale_worktrees(self):
        with mock.patch.object(fleet, "busy_paths", return_value=[]):
            ok, text = fleet.check_worktrees(self.p, time.time(), 14)
            self.assertFalse(ok)
            self.assertIn("1 clean and merged (fleet.py gc --project repo)", text)
            ok, text = fleet.check_worktrees(self.p, time.time() + 30 * 86400, 14)
            self.assertIn("without commits for over 14 days: dirty-merged, open", text)

    def test_gc_dry_run_then_apply_removes_only_clean_merged(self):
        with mock.patch.object(fleet, "busy_paths", return_value=[]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fleet.gc([self.p], apply=False), 0)
        self.assertIn("would remove " + str(self.d / "merged"), out.getvalue())
        self.assertTrue((self.d / "merged").is_dir())
        with mock.patch.object(fleet, "busy_paths", return_value=[]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fleet.gc([self.p], apply=True), 0)
        self.assertFalse((self.d / "merged").exists())
        self.assertTrue((self.d / "dirty-merged/scratch").exists())
        self.assertTrue((self.d / "open").is_dir())
        self.assertIn("dirty", out.getvalue())
        self.assertIn("not merged", out.getvalue())


class DriftTest(unittest.TestCase):
    def test_counts_template_commits_since_base_sha(self):
        with tempfile.TemporaryDirectory() as d:
            canon, proj = Path(d) / "canon", Path(d) / "proj"
            (canon / "templates").mkdir(parents=True)
            (canon / "plugins/dark-factory/templates").mkdir(parents=True)
            git = ["git", "-C", str(canon), "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(["git", "init", "-q", str(canon)], check=True)

            def commit(name):
                (canon / name).write_text(name)
                subprocess.run([*git, "add", "-A"], check=True)
                subprocess.run([*git, "commit", "-qm", name], check=True)
                return subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

            base = commit("templates/a")
            commit("templates/b")
            commit("plugins/dark-factory/templates/c")
            commit("docs-only")
            (proj / ".harness").mkdir(parents=True)
            (proj / ".harness/base-sha").write_text(base + "\n")
            fleet.FACTORY = canon
            p = fleet.Project("p", proj, "p")
            self.assertEqual(fleet.check_drift(p), (False, "2 template commits behind (harness-diff.sh)"))
            (proj / ".harness/base-sha").write_text("0" * 40)
            self.assertFalse(fleet.check_drift(p)[0])


class ReleaseTagDriftTest(unittest.TestCase):
    def test_compares_the_deployed_release_with_the_plugin_version(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d)
            (proj / ".harness").mkdir()
            p = fleet.Project("p", proj, "p")
            with mock.patch.object(fleet, "plugin_version", return_value="v2"):
                (proj / ".harness/base-sha").write_text("v2\n")
                self.assertEqual(fleet.check_drift(p), (True, "on the plugin's template v2"))
                (proj / ".harness/base-sha").write_text("v1\n")
                ok, msg = fleet.check_drift(p)
                self.assertFalse(ok)
                self.assertIn("v1", msg)

    def test_plugin_version_reads_the_manifest(self):
        self.assertRegex(fleet.plugin_version(), r"^v\d+$")


class UnitsPathTest(unittest.TestCase):
    def test_units_call_the_script_through_the_plugin_link(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "share/plugin"
            with mock.patch.object(fleet, "PLUGIN_LINK", link):
                self.assertIn(f"{link}/scripts/fleet.py", fleet.fleet_cmd("/usr/bin/python3", "notify"))
                self.assertNotIn(str(fleet.PLUGIN), fleet.fleet_cmd("/usr/bin/python3", "notify"))

    def test_provision_creates_and_refreshes_the_link(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "share/plugin"
            with mock.patch.object(fleet, "PLUGIN_LINK", link):
                fleet.link_plugin(dry=True)
                self.assertFalse(link.is_symlink())
                link.parent.mkdir()
                link.symlink_to("/old/cache/0.2.0")
                fleet.link_plugin(dry=False)
                self.assertEqual(link.resolve(), fleet.PLUGIN)

    def test_status_checks_the_link_target(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "plugin"
            with mock.patch.object(fleet, "UNIT_DIR", Path(d)), mock.patch.object(fleet, "PLUGIN_LINK", link):
                self.assertIsNone(fleet.check_units())  # not provisioned: nothing to compare
                unit = Path(d) / f"{fleet.FLEET_WATCH}.service"
                unit.write_text(f"ExecStart=python3 {link}/scripts/fleet.py status --notify\n")
                self.assertFalse(fleet.check_units()[0])  # no link
                link.symlink_to("/old/cache/0.2.0")
                self.assertFalse(fleet.check_units()[0])  # dangling
                link.unlink()
                link.symlink_to(fleet.PLUGIN)
                self.assertTrue(fleet.check_units()[0])
                unit.write_text("ExecStart=python3 /old/cache/0.2.0/scripts/fleet.py status --notify\n")
                self.assertFalse(fleet.check_units()[0])  # an old-style unit

    def test_session_start_hook_repoints_an_existing_link_only(self):
        hook = Path(fleet.PLUGIN) / "hooks/refresh-fleet-link.sh"
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "plugin"
            env = {**os.environ, "FLEET_PLUGIN_LINK": str(link), "CLAUDE_PLUGIN_ROOT": "/new/cache/1.0.0"}
            run = lambda: subprocess.run(["bash", str(hook)], env=env, capture_output=True, text=True)
            r = run()
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
            self.assertFalse(link.is_symlink())  # never created
            link.symlink_to("/old/cache/0.2.0")
            self.assertEqual(run().returncode, 0)
            self.assertEqual(os.readlink(link), "/new/cache/1.0.0")
            self.assertEqual(run().stdout, "")


class QuotaTest(unittest.TestCase):
    def test_reads_quota_from_this_plugin_not_the_project(self):
        with tempfile.TemporaryDirectory() as d:
            plugin = Path(d)
            with mock.patch.object(fleet, "PLUGIN", plugin):
                self.assertIsNone(fleet.check_quota())  # no quota script in this plugin dir
                script = plugin / "scripts/quota.py"
                script.parent.mkdir(parents=True)
                script.write_text("")
                with mock.patch.object(fleet, "sh", return_value=(0, "5h 42% (resets 21:30 UTC) · 7d 10%")) as sh:
                    self.assertEqual(fleet.check_quota(), (True, "5h 42% (resets 21:30 UTC) · 7d 10%"))
                self.assertEqual(sh.call_args.args[0][1:], [str(script), "status"])
                with mock.patch.object(fleet, "sh", return_value=(0, "5h 85% (resets 21:30 UTC) · 7d 10%")):
                    self.assertFalse(fleet.check_quota()[0])
                with mock.patch.object(fleet, "sh", return_value=(2, "no quota data")):
                    self.assertFalse(fleet.check_quota()[0])

    def test_the_real_plugin_ships_the_quota_script(self):
        self.assertTrue((Path(__file__).resolve().parent / "quota.py").is_file())


if __name__ == "__main__":
    unittest.main()

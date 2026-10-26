#!/usr/bin/env python3
"""Tests for fleet_feed.py (the menu bar status feed): python3 tests/test_fleet_feed.py"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"))
import fleet_feed  # noqa: E402
import quota  # noqa: E402

NOW = 1_800_000_000.0


def user(text="go"):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


TEXT = {"type": "text", "text": "done"}
TOOL = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}


def write(path: Path, records, age: float = 5, raw_tail: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + raw_tail)
    os.utime(path, (NOW - age, NOW - age))
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class SessionBusyTest(Tmp):
    def test_assistant_text_only_last_is_idle(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TOOL), user(), assistant(TEXT)])
        self.assertFalse(fleet_feed.session_busy(f, NOW))

    def test_assistant_tool_use_last_is_busy(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TEXT, TOOL)])
        self.assertTrue(fleet_feed.session_busy(f, NOW))

    def test_user_record_last_is_busy(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TEXT), user("next")])
        self.assertTrue(fleet_feed.session_busy(f, NOW))

    def test_other_record_types_are_skipped(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TEXT), {"type": "system", "subtype": "x"},
                                         {"type": "summary"}, {"type": "file-history-snapshot"}])
        self.assertFalse(fleet_feed.session_busy(f, NOW))

    def test_half_written_last_line_is_busy(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TEXT)], raw_tail='{"type": "assistant", "mess')
        self.assertTrue(fleet_feed.session_busy(f, NOW))

    def test_older_than_600s_is_idle(self):
        f = write(self.tmp / "s.jsonl", [user(), assistant(TOOL)], age=601)
        self.assertFalse(fleet_feed.session_busy(f, NOW))


class ActivityTest(Tmp):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "projects"
        self.checkout = Path("/srv/shop")
        self.name = "-srv-shop"

    def test_no_transcript_dir(self):
        self.assertEqual(fleet_feed.activity(self.checkout, NOW, self.root), (False, None))

    def test_worktree_dirs_count(self):
        write(self.root / self.name / "a.jsonl", [user(), assistant(TEXT)], age=3000)
        busy = write(self.root / f"{self.name}--claude-worktrees-x" / "b.jsonl", [user()], age=20)
        self.assertEqual(fleet_feed.activity(self.checkout, NOW, self.root), (True, busy.stat().st_mtime))

    def test_subagent_files_set_last_worked_not_busy(self):
        write(self.root / self.name / "a.jsonl", [user(), assistant(TEXT)], age=3000)
        sub = write(self.root / self.name / "a" / "subagents" / "agent-1.jsonl", [user()], age=30)
        self.assertEqual(fleet_feed.activity(self.checkout, NOW, self.root), (False, sub.stat().st_mtime))

    def test_other_checkout_with_same_prefix_ignored(self):
        write(self.root / "-srv-shop-x" / "a.jsonl", [user()], age=10)
        self.assertEqual(fleet_feed.activity(self.checkout, NOW, self.root), (False, None))


class AgentsTest(Tmp):
    def test_counts_by_checkout_including_worktrees(self):
        reg = {"a": {"started": NOW - 60, "cwd": "/srv/shop/.claude/worktrees/x"},
               "b": {"started": NOW - 60, "cwd": "/srv/shop"},
               "c": {"started": NOW - quota.AGENT_TTL - 1, "cwd": "/srv/shop"},
               "d": {"started": NOW - 60, "cwd": "/srv/shopx"},
               "e": {"started": NOW - 60, "cwd": "/srv/hub/app"}}
        (self.tmp / quota.AGENTS).write_text(json.dumps(reg))
        with mock.patch.dict(os.environ, {"CLAUDE_QUOTA_DIR": str(self.tmp)}):
            got = fleet_feed.agents_by_checkout([Path("/srv/shop"), Path("/srv/hub"), Path("/srv/none")], NOW)
        self.assertEqual(got, {Path("/srv/shop"): 2, Path("/srv/hub"): 1, Path("/srv/none"): 0})


class QuotaSnapshotTest(Tmp):
    def cache(self, age, five=(28.4, 3600), seven=(91.0, 86400)):
        (self.tmp / quota.CACHE).write_text(json.dumps({"updated_at": NOW - age, "windows": {
            "five_hour": {"pct": five[0], "resets_at": int(NOW + five[1])},
            "seven_day": {"pct": seven[0], "resets_at": int(NOW + seven[1])}}}))

    def snap(self):
        env = {"CLAUDE_QUOTA_DIR": str(self.tmp), "QUOTA_5H": "80,85,90", "QUOTA_7D": "80,85,90"}
        with mock.patch.dict(os.environ, env):
            return fleet_feed.quota_snapshot(NOW)

    def test_fresh_cache(self):
        self.cache(120)
        s = self.snap()
        self.assertEqual((s["five_hour"], s["seven_day"]), (28, 91))
        self.assertTrue(s["no_new_work"])
        self.assertEqual(s["resets_at"], fleet_feed.iso(NOW + 86400))  # the limiting window
        self.assertEqual(s["as_of"], fleet_feed.iso(NOW - 120))

    def test_fine_quota_resets_at_is_none(self):
        self.cache(120, seven=(18.0, 86400))
        s = self.snap()
        self.assertFalse(s["no_new_work"])
        self.assertIsNone(s["resets_at"])

    def test_cache_older_than_1800s_is_none(self):
        self.cache(1801)
        self.assertIsNone(self.snap())

    def test_missing_cache_is_none(self):
        self.assertIsNone(self.snap())

    def test_never_probes(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
            self.snap()
            self.cache(5000)
            self.snap()
        popen.assert_not_called()
        run.assert_not_called()


import fleet  # noqa: E402


class BuildFeedTest(Tmp):
    def setUp(self):
        super().setUp()
        self.shop = fleet.Project("shop", self.tmp / "shop", "shop")
        self.hub = fleet.Project("hub", self.tmp / "hub", "hub")
        self.shop.path.mkdir()
        self.hub.path.mkdir()
        self.desk = {"shop": (True, "running"), "hub": None}
        self.monitor = {"shop": (False, "silent"), "hub": None}
        self.queue = {"shop": (True, "ready: 5"), "hub": None}
        self.acts = {}
        self.agents = {}
        self.quota = None
        self.urls = {}
        self.replies = {}

    def build(self, projects=None):
        projects = projects or [self.shop, self.hub]
        with mock.patch.object(fleet, "check_desk", lambda p: self.desk[p.name]), \
                mock.patch.object(fleet, "check_monitor", lambda p, now: self.monitor[p.name]), \
                mock.patch.object(fleet, "check_queue", lambda p: self.queue[p.name]), \
                mock.patch.object(fleet_feed, "activity", lambda c, now: self.acts.get(c, (False, None))), \
                mock.patch.object(fleet_feed, "agents_by_checkout",
                                  lambda cs, now: {c: self.agents.get(c, 0) for c in cs}), \
                mock.patch.object(fleet_feed, "quota_snapshot", lambda now: self.quota), \
                mock.patch.object(fleet_feed, "session_url", lambda p: self.urls.get(p.name)), \
                mock.patch.object(fleet_feed, "oncall_last_message", lambda c, now: self.replies.get(c)):
            return fleet_feed.build_feed(projects, NOW)

    def row(self, doc, name):
        return next(r for r in doc["projects"] if r["name"] == name)

    def test_schema(self):
        doc = self.build()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["generated_at"], fleet_feed.iso(NOW))
        self.assertIn("quota", doc)
        self.assertEqual(set(self.row(doc, "shop")), {
            "name", "working", "agents", "waiting_quota", "queue_ready", "last_worked_at", "session_url", "oncall",
            "watchdog"})
        self.assertEqual(set(self.row(doc, "shop")["oncall"]), {"installed", "running", "last_message_at"})
        self.assertEqual(set(self.row(doc, "shop")["watchdog"]), {"installed", "ok"})

    def test_working_from_agents_or_busy_session(self):
        self.agents = {self.shop.path: 3}
        self.acts = {self.hub.path: (True, NOW - 30)}
        doc = self.build()
        self.assertEqual((self.row(doc, "shop")["working"], self.row(doc, "shop")["agents"]), (True, 3))
        hub = self.row(doc, "hub")
        self.assertEqual((hub["working"], hub["agents"], hub["last_worked_at"]), (True, 0, fleet_feed.iso(NOW - 30)))

    def test_waiting_quota_needs_no_new_work_and_ready_queue(self):
        self.quota = {"no_new_work": True}
        doc = self.build()
        self.assertTrue(self.row(doc, "shop")["waiting_quota"])
        self.assertEqual(self.row(doc, "shop")["queue_ready"], 5)
        self.assertFalse(self.row(doc, "hub")["waiting_quota"])
        self.quota = None
        self.assertFalse(self.row(self.build(), "shop")["waiting_quota"])
        self.quota = {"no_new_work": True}
        self.queue["shop"] = (True, "ready: 0")
        self.assertFalse(self.row(self.build(), "shop")["waiting_quota"])

    def test_module_absent_means_not_installed(self):
        doc = self.build()
        self.assertEqual(self.row(doc, "shop")["oncall"]["installed"], True)
        self.assertEqual(self.row(doc, "shop")["oncall"]["running"], True)
        self.assertEqual(self.row(doc, "shop")["watchdog"], {"installed": True, "ok": False})
        self.assertFalse(self.row(doc, "hub")["oncall"]["installed"])
        self.assertFalse(self.row(doc, "hub")["watchdog"]["installed"])

    def test_failing_check_sets_error_and_others_continue(self):
        def boom(p):
            raise RuntimeError("bd broke")
        self.queue = {"shop": None, "hub": None}
        with mock.patch.object(fleet, "check_queue", boom):
            doc = fleet_feed.build_feed([self.shop], NOW)
        self.assertIn("bd broke", self.row(doc, "shop")["error"])
        self.assertFalse(self.row(doc, "shop")["working"])
        doc = self.build()
        self.assertNotIn("error", self.row(doc, "hub"))

    def test_settings_error_project_still_listed(self):
        self.shop.settings_error = "bad SESSION_ARGS"
        self.assertEqual([r["name"] for r in self.build()["projects"]], ["shop", "hub"])

    def test_missing_path(self):
        gone = fleet.Project("gone", self.tmp / "gone", "gone")
        self.desk["gone"] = self.monitor["gone"] = self.queue["gone"] = None
        row = self.row(self.build([gone]), "gone")
        self.assertEqual((row["working"], row["last_worked_at"]), (False, None))

    def test_session_url_and_oncall_message(self):
        self.urls = {"shop": SESSION_URL}
        self.replies = {self.shop.path: NOW - 600}
        shop, hub = self.row(self.build(), "shop"), self.row(self.build(), "hub")
        self.assertEqual(shop["session_url"], SESSION_URL)
        self.assertEqual(shop["oncall"]["last_message_at"], fleet_feed.iso(NOW - 600))
        self.assertIsNone(hub["session_url"])
        self.assertIsNone(hub["oncall"]["last_message_at"])

    def test_no_paths_leak(self):
        self.desk["shop"] = (False, f"{self.shop.path}/scripts/feedback-desk.sh: not running")
        self.assertNotIn(str(self.tmp), json.dumps(self.build()))


ENV_URL = "https://claude.ai/code?environment=env_01AbC"
SESSION_URL = "https://claude.ai/code/session_01XyZ"


class SessionUrlTest(Tmp):
    def test_pick_one(self):
        self.assertEqual(fleet_feed.pick_session_url(f"Ready.\nOpen {ENV_URL} to connect\n"), ENV_URL)

    def test_pick_none(self):
        self.assertIsNone(fleet_feed.pick_session_url("no link here\nhttps://example.com/x"))

    def test_pick_last_and_prefer_session(self):
        text = f"{ENV_URL}\n{SESSION_URL}\nhttps://claude.ai/code?environment=env_02Later"
        self.assertEqual(fleet_feed.pick_session_url(text), SESSION_URL)
        self.assertEqual(fleet_feed.pick_session_url(f"{ENV_URL}\nhttps://claude.ai/code?environment=env_02"),
                         "https://claude.ai/code?environment=env_02")

    def test_dev_session_pane_first_then_new_sessions(self):
        p = fleet.Project("shop", self.tmp, "shop")
        panes = {"df-shop": "", "df-shop.rc": f"{ENV_URL}\n"}
        with mock.patch.object(fleet, "sh", lambda cmd, **kw: (0, panes[cmd[2]])):
            self.assertEqual(fleet_feed.session_url(p), ENV_URL)
        panes["df-shop"] = f"{SESSION_URL}\n"
        with mock.patch.object(fleet, "sh", lambda cmd, **kw: (0, panes[cmd[2]])):
            self.assertEqual(fleet_feed.session_url(p), SESSION_URL)

    def test_no_tmux_is_none(self):
        p = fleet.Project("shop", self.tmp, "shop")
        with mock.patch.object(fleet, "sh", lambda cmd, **kw: (1, "no server running")):
            self.assertIsNone(fleet_feed.session_url(p))


def reply(ts):
    rec = assistant({"type": "tool_use", "id": "r", "name": "mcp__plugin_telegram_telegram__reply", "input": {}})
    rec["timestamp"] = ts
    return rec


class OncallLastMessageTest(Tmp):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "projects"
        self.checkout = Path("/srv/shop")

    def test_last_reply(self):
        write(self.root / "-srv-shop" / "desk.jsonl",
              [user(), reply("2027-01-15T08:00:00.000Z"), reply("2027-01-15T08:30:00.000Z"), assistant(TEXT)], age=60)
        write(self.root / "-srv-shop" / "dev.jsonl", [user(), assistant(TOOL)], age=10)
        got = fleet_feed.oncall_last_message(self.checkout, NOW, self.root)
        self.assertEqual(fleet_feed.iso(got), "2027-01-15T08:30:00Z")

    def test_none(self):
        write(self.root / "-srv-shop" / "dev.jsonl", [user(), assistant(TOOL)], age=10)
        self.assertIsNone(fleet_feed.oncall_last_message(self.checkout, NOW, self.root))

    def test_transcript_older_than_an_hour_not_read(self):
        write(self.root / "-srv-shop" / "desk.jsonl", [reply("2027-01-15T08:00:00.000Z")], age=3601)
        self.assertIsNone(fleet_feed.oncall_last_message(self.checkout, NOW, self.root))

    def test_unreadable_is_none(self):
        f = write(self.root / "-srv-shop" / "desk.jsonl", [reply("not a time")], age=60)
        self.assertIsNone(fleet_feed.oncall_last_message(self.checkout, NOW, self.root))
        f.chmod(0)
        try:
            self.assertIsNone(fleet_feed.oncall_last_message(self.checkout, NOW, self.root))
        finally:
            f.chmod(0o600)


class WriteFeedTest(Tmp):
    def test_atomic_replace(self):
        target = self.tmp / "state" / "status.json"
        fleet_feed.write_feed({"version": 1}, target)
        fleet_feed.write_feed({"version": 1, "x": 2}, target)
        self.assertEqual(json.loads(target.read_text()), {"version": 1, "x": 2})
        self.assertEqual([p.name for p in target.parent.iterdir()], ["status.json"])


if __name__ == "__main__":
    unittest.main()

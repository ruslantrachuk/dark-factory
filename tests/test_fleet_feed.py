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


if __name__ == "__main__":
    unittest.main()

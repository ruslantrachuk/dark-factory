#!/usr/bin/env python3
"""Tests for analytics.py and analytics_lib: python3 tests/test_analytics.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from analytics_lib import store  # noqa: E402


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class StoreTest(TempDirTest):
    def test_transcript_dirs_include_worktrees(self):
        root = self.tmp / "projects"
        for name in ("-home-u-my-proj", "-home-u-my-proj--claude-worktrees-x", "-home-u-my-proj--worktrees-dev",
                     "-home-u-my-proj-other", "-home-u-my-projx"):
            (root / name).mkdir(parents=True)
        dirs = store.transcript_dirs(Path("/home/u/my.proj"), root)
        self.assertEqual(sorted(d.name for d in dirs),
                         ["-home-u-my-proj", "-home-u-my-proj--claude-worktrees-x", "-home-u-my-proj--worktrees-dev"])

    def test_iso_week(self):
        self.assertEqual(store.iso_week("2026-10-19T00:00:01Z"), "2026-W43")
        self.assertEqual(store.iso_week("2026-10-18T23:59:59.500Z"), "2026-W42")
        self.assertEqual(store.iso_week("2027-01-01T10:00:00Z"), "2026-W53")

    def test_week_bounds(self):
        start, end = store.week_bounds("2026-W43")
        self.assertEqual(start.isoformat(), "2026-10-19T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-10-26T00:00:00+00:00")

    def test_save_load_roundtrip(self):
        with mock.patch.dict(os.environ, {"ANALYTICS_STATE": str(self.tmp / "state")}):
            store.save_week("2026-W43", {"week": "2026-W43", "projects": {}})
            store.save_week("2026-W41", {"week": "2026-W41", "projects": {}})
            self.assertEqual(store.load_week("2026-W43")["week"], "2026-W43")
            self.assertIsNone(store.load_week("2026-W40"))
            self.assertEqual(store.stored_weeks(), ["2026-W41", "2026-W43"])

    def test_settings_owner_split(self):
        env = self.tmp / "analytics.env"
        env.write_text('ANALYTICS_OWNER="peat ruslan_trachuk"\nANALYTICS_SWEAR="darn"\n')
        s = store.load_settings(env)
        self.assertEqual(s.owner, {"peat", "ruslan_trachuk"})
        self.assertEqual(s.swear, ["darn"])
        self.assertEqual(store.load_settings(self.tmp / "missing.env").owner, set())


if __name__ == "__main__":
    unittest.main()

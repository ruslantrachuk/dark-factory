"""Feature pipeline on Codex: python3 tests/test_codex_feature.py (stdlib only; a fake `codex` plays the turns)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import codex_feature as cf  # noqa: E402

# The fake answers by the stage it recognises in the prompt; a file <dir>/<stage>.json overrides the answer,
# <dir>/fail-<stage> makes that turn fail once after the thread started. Every call is logged as one JSON line.
FAKE = r'''#!/usr/bin/env python3
import json, os, sys, uuid
d = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
out = args[args.index("-o") + 1]
prompt = args[-1]
resume = args[1] == "resume"
stage = ("regate" if "full gate after you" in prompt else "fix" if "Apply the review fixes" in prompt
         else "review" if "Read-only review" in prompt else "build")
thread = args[-2] if resume else str(uuid.uuid4())
with open(os.path.join(d, "calls.jsonl"), "a") as f:
    f.write(json.dumps({"stage": stage, "resume": resume, "thread": thread, "args": args[:-1]}) + "\n")
if not resume:
    print(json.dumps({"type": "thread.started", "thread_id": thread}), flush=True)
fail = os.path.join(d, "fail-" + stage)
if os.path.exists(fail):
    os.remove(fail)
    print(json.dumps({"type": "turn.failed", "error": {"message": "stream disconnected"}}))
    sys.exit(1)
default = {"build": {"ok": True, "summary": "built", "details": "", "appDir": "", "prBody": "## Done\n- built",
                     "slices": ["1.1 x"], "assumptions": ["a"]},
           "regate": {"ok": True, "summary": "fixed", "details": "", "appDir": "", "prBody": "## Done\n- regated",
                      "slices": [], "assumptions": []},
           "review": {"findings": []},
           "fix": {"ok": True, "summary": "fixed", "details": "", "prBody": "## Done\n- fixed"}}[stage]
custom = os.path.join(d, stage + ".json")
answer = json.load(open(custom)) if os.path.exists(custom) else default
open(out, "w").write(json.dumps(answer))
print(json.dumps({"type": "turn.completed", "usage": {}}))
'''


class CodexFeatureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.fake = t / "fake"
        self.fake.mkdir()
        (self.fake / "codex").write_text(FAKE)
        (self.fake / "codex").chmod(0o755)
        self.repo = t / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q",
                        "--allow-empty", "-m", "init"], check=True)
        (self.repo / ".claude/worktrees/fab-add-x").mkdir(parents=True)  # what the builder's worktree add makes
        # the gate: green unless <fake>/red-N exists (then red N more times)
        gate = f"python3 -c \"import pathlib,sys; p=sorted(pathlib.Path('{self.fake}').glob('red-*')); " \
               f"(p[0].unlink(), sys.exit(1)) if p else None\""
        self.settings = t / "settings.json"
        self.settings.write_text(json.dumps({"testCmd": gate, "lintCmd": "true", "surfaces": "<surfaces>"}))
        self.patches = [mock.patch.object(cf, "CODEX", str(self.fake / "codex")),
                        mock.patch.object(cf, "RUNS", t / "runs"),
                        mock.patch.object(cf, "quota_stop", lambda: False)]
        for p in self.patches:
            p.start()
        self.cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.cwd)
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_cf(self, *extra, stamp="s1"):
        args = ["run", "--stamp", stamp, "--request", "add x", "--bd", "p-1", "--slug", "add-x",
                "--settings", str(self.settings), *extra]
        with open(os.devnull, "w") as null, mock.patch("sys.stdout", new=null):
            cf.main(args)
        return json.loads((cf.RUNS / f"{stamp}.json").read_text())["result"]

    def calls(self):
        f = self.fake / "calls.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    def test_happy_path_build_gate_review(self):
        res = self.run_cf()
        self.assertIsNone(res["error"])
        self.assertEqual(res["branch"], "feat/add-x")
        self.assertTrue(res["appDir"].endswith(".claude/worktrees/fab-add-x"))
        self.assertEqual([c["stage"] for c in self.calls()], ["build", "review"])
        review = self.calls()[1]
        self.assertIn("read-only", review["args"])
        self.assertEqual(res["turns"], 2)
        self.assertIn("built", res["prBody"])

    def test_red_gate_goes_back_to_the_builder_thread(self):
        (self.fake / "red-1").touch()
        res = self.run_cf()
        self.assertIsNone(res["error"])
        calls = self.calls()
        self.assertEqual([c["stage"] for c in calls], ["build", "regate", "review"])
        self.assertTrue(calls[1]["resume"])
        self.assertEqual(calls[1]["thread"], calls[0]["thread"])
        self.assertIn("regated", res["prBody"])

    def test_gate_stays_red(self):
        for i in range(5):
            (self.fake / f"red-{i}").touch()
        res = self.run_cf()
        self.assertEqual(res["error"], "incomplete: final gates red after build")
        self.assertEqual([c["stage"] for c in self.calls()], ["build", "regate", "regate"])

    def test_major_finding_is_fixed_in_the_builder_thread(self):
        (self.fake / "review.json").write_text(json.dumps({"findings": [
            {"file": "a.py", "line": 1, "summary": "bug", "severity": "major", "fix": ""},
            {"file": "b.py", "line": 0, "summary": "style", "severity": "minor", "fix": ""}]}))
        res = self.run_cf()
        self.assertIsNone(res["error"])
        calls = self.calls()
        self.assertEqual([c["stage"] for c in calls], ["build", "review", "fix"])
        self.assertEqual(calls[2]["thread"], calls[0]["thread"])
        self.assertIn("fixed", res["prBody"])

    def test_critical_finding_not_fixed_is_a_blocker(self):
        (self.fake / "review.json").write_text(json.dumps({"findings": [
            {"file": "a.py", "line": 1, "summary": "hole", "severity": "critical", "fix": ""}]}))
        (self.fake / "fix.json").write_text(json.dumps({"ok": False, "summary": "no", "details": "", "prBody": ""}))
        res = self.run_cf()
        self.assertIn("review fixes not applied", res["error"])
        self.assertIn("1 critical review blocker(s) remain", res["error"])

    def test_cut_off_turn_resumes_in_its_thread(self):
        (self.fake / "fail-build").touch()
        first = self.run_cf()
        self.assertEqual(first["error"], "codex: stream disconnected")
        second = self.run_cf()
        self.assertIsNone(second["error"])
        calls = self.calls()
        self.assertEqual([c["stage"] for c in calls], ["build", "build", "review"])
        self.assertTrue(calls[1]["resume"])
        self.assertEqual(calls[1]["thread"], calls[0]["thread"])

    def test_done_stages_are_not_repeated(self):
        self.run_cf()
        self.run_cf()
        self.assertEqual([c["stage"] for c in self.calls()], ["build", "review"])

    def test_quota_stops_before_a_turn(self):
        with mock.patch.object(cf, "quota_stop", lambda: True):
            res = self.run_cf()
        self.assertEqual(res["error"], "quota")
        self.assertEqual(self.calls(), [])

    def test_turn_cap(self):
        with mock.patch.object(cf, "MAX_TURNS", 1):
            res = self.run_cf()
        self.assertEqual(res["error"], "agent limit reached")

    def test_failed_build(self):
        (self.fake / "build.json").write_text(json.dumps({"ok": False, "summary": "migration required", "details": "",
                                                          "appDir": "", "prBody": "", "slices": [],
                                                          "assumptions": []}))
        self.assertEqual(self.run_cf()["error"], "session build failed")


class PartsTest(unittest.TestCase):
    def ns(self, **kw):
        base = dict(stamp="s", slug=None, change=None, phase=None, tracker=None, type="feat")
        base.update(kw)
        return cf.argparse.Namespace(**base)

    def test_branch_names(self):
        self.assertEqual(cf.branch_name(self.ns(slug="x")), "feat/x")
        self.assertEqual(cf.branch_name(self.ns(tracker="DMP-1", slug="x")), "feat/DMP-1-x")
        self.assertEqual(cf.branch_name(self.ns(change="openspec/changes/voice", phase="2")), "feat/voice-p2")
        self.assertEqual(cf.branch_name(self.ns()), "feat/auto-s")
        with self.assertRaises(cf.Stop):
            cf.branch_name(self.ns(slug="../x"))

    def test_gate_commands(self):
        root = Path("/r")
        self.assertEqual(cf.gate_commands({}, "/t", root),
                         ["/r/app/.venv/bin/python -m pytest /t/app/tests -q --tb=short",
                          "/r/app/.venv/bin/ruff check /t/app/src /t/app/tests && "
                          "/r/app/.venv/bin/ruff format --check /t/app/src /t/app/tests"])
        cmds = cf.gate_commands({"testCmd": "make -C {tree} test", "lintCmd": "true", "dbTests": True,
                                 "appSubdir": ""}, "/t", root)
        self.assertEqual(cmds[:2], ["make -C /t test", "true"])
        self.assertEqual(cmds[2], "/r/.venv/bin/python -m pytest /t/tests/integration/db -m db -q --tb=short")

    def test_placeholders_are_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "s.json")
            p.write_text(json.dumps({"testCmd": "<test command>", "lintCmd": "ruff"}))
            self.assertEqual(cf.load_settings(p, Path(d)), {"lintCmd": "ruff"})

    def test_bad_stamp(self):
        with self.assertRaises(cf.Stop):
            cf.Run("../x")


if __name__ == "__main__":
    unittest.main()

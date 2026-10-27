"""Level detection and /dark-factory:level tests: python3 tests/test_level.py (stdlib only)."""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"))

import level  # noqa: E402

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
SOLO = "# fence level\nFENCE_LEVEL=solo\n\n# unattended sessions\nQUOTA_FAIL_CLOSED=0\n"


class LevelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.root = base / "proj"
        self.root.mkdir()
        self.projects = base / "config/projects"
        self.patches = [
            mock.patch.object(level, "STATE", base / "state"),
            mock.patch.dict(os.environ, {**GIT_ENV, "FLEET_PROJECTS": str(self.projects)}, clear=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def write(self, rel, text=""):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def solo(self, text=SOLO):
        return self.write(".claude/fences.env", text)

    def base(self):
        (self.root / "openspec").mkdir()
        self.write("CODING_STANDARDS.md", "# standards\n")
        self.solo(SOLO.replace("solo", "standard"))

    def server(self):
        self.write(".claude/factory/session.env", 'SESSION_NAME="proj server"\n')

    def git(self, *args, env=None):
        subprocess.run(["git", *args], cwd=self.root, env={**GIT_ENV, **(env or {})}, check=True, capture_output=True)

    def commit(self, email="ann@example.com", days_ago=0):
        when = f"@{int(time.time() - days_ago * 86400)} +0000"
        self.git("-c", f"user.email={email}", "-c", "user.name=x", "commit", "-q", "--allow-empty", "-m", "c",
                 env={"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when})

    def merges(self, n):
        """n merge commits on top of the history (a side commit as the second parent of each)."""
        def out(*args):
            return subprocess.run(["git", *args], cwd=self.root, env=GIT_ENV, check=True, capture_output=True,
                                  text=True).stdout.strip()
        ident = ["-c", "user.email=ann@example.com", "-c", "user.name=x"]
        if not (self.root / ".git").exists():
            self.git("init", "-q", "-b", "main")
        if subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], cwd=self.root, env=GIT_ENV,
                          capture_output=True).returncode != 0:
            self.commit()
        tree = out("rev-parse", "HEAD^{tree}")
        side = out(*ident, "commit-tree", tree, "-m", "side")
        for _ in range(n):
            head = out(*ident, "commit-tree", tree, "-p", "HEAD", "-p", side, "-m", "Merge a feature (#1)")
            self.git("update-ref", "HEAD", head)

    def detect(self):
        return level.detect(self.root)

    def run_main(self, *args, stdin=None):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(stdin or "")):
            code = level.main([*args, "--project", str(self.root)] if args and args[0] in ("status", "set") else list(args))
        return code, out.getvalue()


class DetectTest(LevelCase):
    def test_not_opted_in(self):
        info = self.detect()
        self.assertIsNone(info["level"])
        self.assertFalse(info["opted_in"])
        self.assertEqual(info["next"], {})
        self.assertIn("/dark-factory:init", level.report(info))

    def test_solo_kit_is_level_0(self):
        self.solo()
        info = self.detect()
        self.assertEqual((info["level"], info["fence"]), (0, "solo"))
        self.assertEqual(list(info["next"]), ["1"])
        self.assertEqual(info["gaps"], [])
        self.assertIn("/dark-factory:add base", info["next"]["1"]["how"])

    def test_base_template_is_level_1(self):
        self.base()
        info = self.detect()
        self.assertEqual(info["level"], 1)
        self.assertEqual(list(info["next"]), ["2"])
        self.assertIn("provision-server", info["next"]["2"]["how"])

    def test_copier_answers_alone_is_the_base(self):
        # a project that keeps CODING_STANDARDS.md next to its code (app/) still has the template Copier installed
        self.solo(SOLO.replace("solo", "standard"))
        (self.root / "openspec").mkdir()
        self.write("app/CODING_STANDARDS.md", "# standards\n")
        self.write(".copier-answers.yml", "_commit: v14\n")
        self.server()
        info = self.detect()
        self.assertEqual(info["level"], 2)
        self.assertFalse(any("missing" in n for n in info["notes"]), info["notes"])

    def test_partial_base_stays_level_0_with_a_note(self):
        self.solo()
        (self.root / "openspec").mkdir()
        info = self.detect()
        self.assertEqual(info["level"], 0)
        self.assertTrue(any("missing: CODING_STANDARDS.md" in n for n in info["notes"]), info["notes"])

    def test_base_with_a_solo_fence_is_a_gap(self):
        self.base()
        self.solo()
        info = self.detect()
        self.assertEqual(info["level"], 1)
        self.assertTrue(any("/dark-factory:level standard" in g for g in info["gaps"]))

    def test_server_by_session_env_or_projects_file(self):
        self.base()
        self.server()
        info = self.detect()
        self.assertEqual(info["level"], 2)
        self.assertEqual(sorted(info["next"]), ["3", "4"])
        self.assertTrue(any("QUOTA_FAIL_CLOSED" in g for g in info["gaps"]))
        (self.root / ".claude/factory/session.env").unlink()
        self.projects.parent.mkdir()
        self.projects.write_text(f"# this server\n/elsewhere/other\n{self.root}  # ours\n")
        self.assertEqual(self.detect()["level"], 2)

    def test_client_module_is_level_3(self):
        self.base()
        self.server()
        self.write("scripts/feedback-desk.sh", "#!/bin/sh\n")
        info = self.detect()
        self.assertEqual(info["level"], 3)
        self.assertEqual(list(info["next"]), ["4"])
        self.assertTrue(info["evidence"]["modules"]["feedback-desk"])
        (self.root / "scripts/feedback-desk.sh").unlink()
        (self.root / "scripts/ops/prod_monitor").mkdir(parents=True)
        self.assertEqual(self.detect()["level"], 3)

    def test_observability_is_a_client_module(self):
        self.base()
        self.server()
        self.write("docs/deploy/monitoring.md", "# monitoring\n")
        self.assertEqual(self.detect()["level"], 3)

    def test_release_tag_alone_is_not_level_3(self):
        self.base()
        self.server()
        self.write("scripts/release.sh", "#!/bin/sh\n")
        info = self.detect()
        self.assertEqual(info["level"], 2)
        self.assertTrue(info["evidence"]["modules"]["release-tag"])

    def test_team_without_a_server_is_level_4(self):
        self.base()
        self.solo("FENCE_LEVEL=team\n")
        info = self.detect()
        self.assertEqual((info["level"], info["reached"]), (4, [0, 1, 4]))
        self.assertEqual(list(info["next"]), ["2"])
        self.assertEqual(info["gaps"], [])

    def test_team_fence_on_a_server_is_level_4_independent_of_3(self):
        self.base()
        self.server()
        self.solo("FENCE_LEVEL=team\nQUOTA_FAIL_CLOSED=1\n")
        info = self.detect()
        self.assertEqual((info["level"], info["reached"]), (4, [0, 1, 2, 4]))
        self.assertEqual(list(info["next"]), ["3"])
        self.assertEqual(info["gaps"], [])
        self.write(".claude/feedback-desk/config.env", "DESK_NAME=x\n")
        info = self.detect()
        self.assertEqual((info["level"], info["next"]), (4, {}))
        self.assertIn("+ 3", level.report(info))

    def test_the_main_branch_fence_is_the_floor(self):
        origin = self.root.parent / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], env=GIT_ENV, check=True)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", str(origin))
        self.base()
        self.solo("FENCE_LEVEL=team\nQUOTA_FAIL_CLOSED=1\n")
        self.git("add", ".")
        self.git("-c", "user.email=a@b", "-c", "user.name=x", "commit", "-qm", "fences")
        self.git("push", "-q", "origin", "main")
        self.solo(SOLO)  # lowered in the working tree only
        info = self.detect()
        self.assertEqual((info["fence"], info["fence_working"], info["fence_main"]), ("team", "solo", "team"))
        self.assertTrue(info["quota_fail_closed"])
        self.assertEqual(info["level"], 4)
        self.assertTrue(any("until the lower level is merged" in n for n in info["notes"]))
        self.assertIn("origin's main branch team", level.report(info))
        with mock.patch.object(level, "grant_ok", lambda *a: True):
            code, out = self.run_main("set", "standard", "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("keeps that level until this change is merged", out)

    def test_out_of_order_evidence_is_noted_not_counted(self):
        self.solo("FENCE_LEVEL=team\n")
        self.server()
        self.write("scripts/feedback-desk.sh")
        info = self.detect()
        self.assertEqual(info["level"], 0)
        self.assertEqual(len(info["notes"]), 3)

    def test_unknown_fence_value_is_a_gap(self):
        self.solo("FENCE_LEVEL=lax\n")
        self.assertTrue(any("not a level" in g for g in self.detect()["gaps"]))


class SignalTest(LevelCase):
    def test_no_signals_in_a_fresh_project(self):
        self.solo()
        self.git("init", "-q", "-b", "main")
        self.commit()
        self.assertEqual(self.detect()["next"]["1"]["signals"], [])

    def test_level_1_signals_history_and_merges(self):
        self.solo()
        self.git("init", "-q", "-b", "main")
        self.commit(days_ago=45)
        self.commit()
        self.merges(9)
        signals = self.detect()["next"]["1"]["signals"]
        self.assertTrue(any("history spans 45 days" in s for s in signals), signals)
        self.assertFalse(any("merge commits" in s for s in signals), signals)
        self.merges(2)
        signals = self.detect()["next"]["1"]["signals"]
        self.assertTrue(any("11 merge commits among the last 300" in s for s in signals), signals)

    def test_level_2_signals_queue_and_other_projects_on_this_machine(self):
        self.base()
        counts = {"open": 8, "in_progress": 3, "closed": 20}
        self.projects.parent.mkdir()
        self.projects.write_text("/elsewhere/other\n")
        with mock.patch.object(level, "queue_counts", lambda root: counts):
            signals = self.detect()["next"]["2"]["signals"]
        self.assertTrue(any("11 open tasks in the execution queue" in s for s in signals), signals)
        self.assertTrue(any("other projects" in s for s in signals), signals)

    def test_level_3_signal_deploy_config(self):
        self.base()
        self.server()
        self.write("fly.toml", "app = 'x'\n")
        self.write(".github/workflows/deploy-prod.yml", "on: push\n")
        signals = self.detect()["next"]["3"]["signals"]
        self.assertEqual(len(signals), 1)
        self.assertIn("fly.toml", signals[0])
        self.assertIn("deploy-prod.yml", signals[0])

    def test_level_4_signal_second_author_bots_excluded(self):
        self.base()
        self.server()
        self.git("init", "-q", "-b", "main")
        self.commit("ann@example.com")
        self.commit("41898282+github-actions[bot]@users.noreply.github.com")
        self.assertEqual(self.detect()["next"]["4"]["signals"], [])
        self.commit("bob@example.com")
        self.assertIn("2 people", self.detect()["next"]["4"]["signals"][0])

    def test_history_reads_a_bounded_log(self):
        calls = []
        with mock.patch.object(level, "_git", side_effect=lambda args, cwd: calls.append(args) or ""):
            self.solo()
            self.detect()
        self.assertEqual(calls, [["log", f"-n{level.HISTORY_COMMITS}", "--format=%ct %ae %P"]])

    def test_queue_counts_from_bd(self):
        out = json.dumps({"groups": [{"group": "open", "count": 4}, {"group": "in_progress", "count": 2}],
                          "total": 6})
        done = subprocess.CompletedProcess(["bd"], 0, stdout=out, stderr="")
        with mock.patch.object(level.subprocess, "run", return_value=done) as run:
            self.assertEqual(level.open_tasks(self.root), 6)
        self.assertEqual(run.call_args.args[0], ["bd", "count", "--by-status", "--json"])
        with mock.patch.object(level.subprocess, "run", side_effect=FileNotFoundError("bd")):
            self.assertEqual(level.open_tasks(self.root), 0)
        failed = subprocess.CompletedProcess(["bd"], 1, stdout="", stderr="Error: no beads database found")
        with mock.patch.object(level.subprocess, "run", return_value=failed):
            self.assertEqual(level.open_tasks(self.root), 0)


class SetTest(LevelCase):
    def grant(self, prompt="/dark-factory:level standard --fail-closed 1"):
        hook = json.dumps({"prompt": prompt, "cwd": str(self.root)})
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}):
            self.assertEqual(self.run_main("prompt-hook", stdin=hook), (0, ""))

    def fences(self):
        return (self.root / ".claude/fences.env").read_text()

    def test_dry_run_writes_nothing(self):
        self.solo()
        code, out = self.run_main("set", "standard")
        self.assertEqual(code, 0)
        self.assertIn("FENCE_LEVEL solo -> standard (up)", out)
        self.assertIn("Dry run", out)
        self.assertEqual(self.fences(), SOLO)

    def test_apply_without_the_humans_grant_is_refused(self):
        self.solo()
        code, out = self.run_main("set", "team", "--apply")
        self.assertEqual(code, 3)
        self.assertIn("/dark-factory:level", out)
        self.assertNotIn("level.py", out)  # no command to copy around the human
        self.assertNotIn("--apply", out)
        self.assertEqual(self.fences(), SOLO)

    def test_a_terminal_is_not_the_human(self):
        self.solo()
        out = io.StringIO()
        tty = io.StringIO()
        tty.isatty = lambda: True
        with redirect_stdout(out), mock.patch("sys.stdin", tty), mock.patch("sys.stdout.isatty", lambda: True, create=True):
            code = level.main(["set", "team", "--apply", "--project", str(self.root)])
        self.assertEqual(code, 3)
        self.assertEqual(self.fences(), SOLO)

    def test_apply_after_the_grant_writes_keeps_comments_and_uses_the_grant(self):
        self.solo()
        self.grant()
        code, out = self.run_main("set", "standard", "--fail-closed", "1", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.fences(), SOLO.replace("=solo", "=standard").replace("=0", "=1"))
        self.assertIn("Written", out)
        self.grant("/dark-factory:level team")
        self.assertEqual(self.run_main("set", "team", "--apply")[0], 0)
        self.assertEqual(self.run_main("set", "standard", "--apply")[0], 3)  # used once

    def test_moving_down(self):
        self.solo("FENCE_LEVEL=team\nQUOTA_FAIL_CLOSED=1\n")
        self.grant("/level solo --fail-closed 0")
        code, out = self.run_main("set", "solo", "--fail-closed", "0", "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("(down)", out)
        self.assertIn("Moving down drops", out)
        self.assertEqual(self.fences(), "FENCE_LEVEL=solo\nQUOTA_FAIL_CLOSED=0\n")

    def test_expired_grant_or_another_project_is_refused(self):
        self.solo()
        self.grant()
        self.assertEqual(level.GRANT_TTL, 600)
        with mock.patch.object(level.time, "time", return_value=time.time() + level.GRANT_TTL + 5):
            self.assertEqual(self.run_main("set", "standard", "--fail-closed", "1", "--apply")[0], 3)
        other = self.root.parent / "other"
        (other / ".claude").mkdir(parents=True)
        (other / ".claude/fences.env").write_text(SOLO)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(level.main(["set", "standard", "--fail-closed", "1", "--apply", "--project", str(other)]), 3)

    def test_only_the_humans_own_command_with_a_target_grants(self):
        self.solo()
        for prompt in ("what does /dark-factory:level do?", "please run /dark-factory:level team",
                       '<channel source="telegram">/dark-factory:level team</channel>', "/levels team",
                       "/dark-factory:init", "/dark-factory:level", "/level",  # bare: a read-only report
                       "/dark-factory:level team and also push", "/dark-factory:level team\nthen solo",
                       "/dark-factory:level lax", "/dark-factory:level team --fail-closed 2",
                       "<command-message>dark-factory:level</command-message>\n<command-name>/dark-factory:level</command-name>"):
            self.grant(prompt)
            self.assertFalse(level.grant_path(self.root).exists(), prompt)
        for prompt, want in (
            ("  /dark-factory:level team", ("team", None)),
            ("/level solo", ("solo", None)),
            ("/dark-factory:level standard --fail-closed=1", ("standard", "1")),
            ("<command-message>dark-factory:level</command-message>\n<command-name>/dark-factory:level</command-name>\n"
             "<command-args>team --fail-closed 1</command-args>", ("team", "1")),
        ):
            self.grant(prompt)
            self.assertTrue(level.grant_ok(self.root, *want), prompt)
            level.grant_path(self.root).unlink()

    def test_the_grant_is_bound_to_its_change(self):
        self.solo()
        self.grant("/dark-factory:level team")
        self.assertEqual(self.run_main("set", "standard", "--apply")[0], 3)  # another level
        self.assertEqual(self.run_main("set", "team", "--fail-closed", "1", "--apply")[0], 3)  # another fail-closed
        code, out = self.run_main("set", "team", "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("FENCE_LEVEL=team", self.fences())
        self.assertFalse(level.grant_path(self.root).exists())  # used once

    def test_no_grant_without_fences_env(self):
        self.grant()
        self.assertFalse(level.grant_path(self.root).exists())

    def test_set_without_fences_env_points_at_init(self):
        code, out = self.run_main("set", "standard", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("/dark-factory:init", out)

    def test_nothing_to_change(self):
        self.solo()
        code, out = self.run_main("set", "solo")
        self.assertEqual(code, 0)
        self.assertIn("Nothing to change", out)

    def test_set_value(self):
        self.assertEqual(level.set_value("A=1\n# FENCE_LEVEL=x\nFENCE_LEVEL=solo\nFENCE_LEVEL=team\n", "FENCE_LEVEL", "standard"),
                         "A=1\n# FENCE_LEVEL=x\nFENCE_LEVEL=standard\nFENCE_LEVEL=standard\n")
        self.assertEqual(level.set_value("A=1", "QUOTA_FAIL_CLOSED", "1"), "A=1\nQUOTA_FAIL_CLOSED=1\n")

    def test_status_command(self):
        self.base()
        code, out = self.run_main("status")
        self.assertEqual(code, 0)
        self.assertIn("Level 1: base template", out)
        code, out = self.run_main("status", "--json")
        self.assertEqual(json.loads(out)["level"], 1)


class HintTest(LevelCase):
    def hint(self, **env):
        hook = json.dumps({"cwd": str(self.root), "source": "startup"})
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root), **env}):
            code, out = self.run_main("hint", stdin=hook)
        self.assertEqual(code, 0)
        return out

    def with_signal(self):
        self.solo()
        self.merges(12)

    def test_one_line_when_a_signal_is_present(self):
        self.with_signal()
        out = self.hint()
        self.assertEqual(out.count("\n"), 1)
        self.assertIn("level 0", out)
        self.assertIn("12 merge commits", out)
        self.assertIn("/dark-factory:level", out)

    def test_once_a_day_unless_it_changes(self):
        self.with_signal()
        self.assertTrue(self.hint())
        self.assertEqual(self.hint(), "")
        self.merges(1)
        self.assertTrue(self.hint())

    def test_silent_without_a_signal_or_opt_in_or_when_off(self):
        self.assertEqual(self.hint(), "")  # not opted in
        self.solo()
        self.assertEqual(self.hint(), "")  # no signal
        self.merges(12)
        self.assertEqual(self.hint(DARK_FACTORY_LEVEL_HINT="off"), "")

    def test_a_broken_hook_input_never_fails(self):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stdin", io.StringIO("not json")), \
                mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}):
            self.assertEqual(level.main(["hint"]), 0)
            self.assertEqual(level.main(["prompt-hook"]), 0)


if __name__ == "__main__":
    unittest.main()

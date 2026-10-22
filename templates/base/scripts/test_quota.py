"""Quota watchdog tests: python3 scripts/test_quota.py (stdlib only)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import quota  # noqa: E402

NOW = 1_792_600_000

STREAM = [
    '{"type":"system","subtype":"init"}',
    json.dumps(
        {
            "type": "rate_limit_event",
            "rate_limit_info": {
                "status": "allowed",
                "unifiedWindows": {
                    "five_hour": {"utilization": 0.62, "resetsAt": NOW + 3600},
                    "seven_day": {"utilization": 0.45, "resetsAt": NOW + 86400},
                },
            },
        }
    ),
    "not json",
]


class ParseTest(unittest.TestCase):
    def test_stream_json_rate_limit_event(self):
        w = quota.parse_stream(STREAM)
        self.assertEqual(w["five_hour"], {"pct": 62.0, "resets_at": NOW + 3600})
        self.assertEqual(w["seven_day"], {"pct": 45.0, "resets_at": NOW + 86400})

    def test_stream_without_event(self):
        self.assertIsNone(quota.parse_stream(['{"type":"result"}']))

    def test_statusline_input(self):
        data = {
            "rate_limits": {
                "five_hour": {"used_percentage": 23.5, "resets_at": NOW + 10},
                "seven_day": {"used_percentage": 41.2, "resets_at": NOW + 20},
            }
        }
        w = quota.parse_statusline(data)
        self.assertEqual(w["five_hour"], {"pct": 23.5, "resets_at": NOW + 10})
        self.assertEqual(w["seven_day"]["pct"], 41.2)

    def test_statusline_without_limits(self):
        self.assertIsNone(quota.parse_statusline({"model": {}}))


class PretoolTest(unittest.TestCase):
    def test_agent_is_guarded(self):
        self.assertTrue(quota.is_guarded({"tool_name": "Agent", "tool_input": {}}))
        self.assertTrue(quota.is_guarded({"tool_name": "Workflow", "tool_input": {}}))

    def test_bd_claim_is_guarded(self):
        hook = {"tool_name": "Bash", "tool_input": {"command": "bd update proj-1 --claim"}}
        self.assertTrue(quota.is_guarded(hook))

    def test_other_bash_not_guarded(self):
        hook = {"tool_name": "Bash", "tool_input": {"command": "bd ready"}}
        self.assertFalse(quota.is_guarded(hook))
        self.assertFalse(quota.is_guarded({"tool_name": "Read", "tool_input": {}}))

    def test_deny_payload(self):
        out = quota.deny("5h 85% ≥ 80%")
        spec = out["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PreToolUse")
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertIn("85%", spec["permissionDecisionReason"])


def win(p5, p7=10, r5=NOW + 100, r7=NOW + 1000):
    return {"five_hour": {"pct": p5, "resets_at": r5}, "seven_day": {"pct": p7, "resets_at": r7}}


class StageTest(unittest.TestCase):
    def test_stages_five_hour(self):
        self.assertEqual(quota.stage(win(79), NOW)[0], quota.OK)
        self.assertEqual(quota.stage(win(80), NOW)[0], quota.NO_NEW)
        self.assertEqual(quota.stage(win(85), NOW)[0], quota.WRAP)
        self.assertEqual(quota.stage(win(89), NOW)[0], quota.WRAP)
        self.assertEqual(quota.stage(win(90), NOW)[0], quota.HARD)

    def test_stages_seven_day(self):
        self.assertEqual(quota.stage(win(10, 80), NOW)[0], quota.NO_NEW)
        self.assertEqual(quota.stage(win(10, 85), NOW)[0], quota.WRAP)
        self.assertEqual(quota.stage(win(10, 90), NOW)[0], quota.HARD)

    def test_expired_window_counts_as_zero(self):
        self.assertEqual(quota.stage(win(99, r5=NOW - 1), NOW)[0], quota.OK)

    def test_worst_window_wins(self):
        st, reason = quota.stage(win(86, 90), NOW)
        self.assertEqual(st, quota.HARD)
        self.assertIn("7d", reason)

    def test_tie_names_window_that_resets_later(self):
        st, reason = quota.stage(win(92, 91, r5=NOW + 100, r7=NOW + 86400), NOW)
        self.assertEqual(st, quota.HARD)
        self.assertIn("7d", reason)

    def test_extra_thresholds_clamped_to_hard(self):
        with mock.patch.dict(os.environ, {"QUOTA_5H": "50,60,70,80"}):
            self.assertEqual(quota.stage(win(85), NOW)[0], quota.HARD)


class ResumeTest(unittest.TestCase):
    def test_reopen_is_latest_reset_among_holding_windows(self):
        self.assertEqual(quota.reopen_at(win(92, 81, r7=NOW + 86400), NOW), NOW + 86400)
        self.assertEqual(quota.reopen_at(win(92, 10, r7=NOW + 86400), NOW), NOW + 100)
        self.assertIsNone(quota.reopen_at(win(50), NOW))

    def test_hint_gives_utc_time_and_how_to_wait(self):
        hint = quota.resume_hint(win(92, r5=NOW + 2 * 3600 + 300), NOW)
        self.assertIn("= 2026-10-21T18:31:40Z,", hint)
        self.assertIn("in 2h 5min", hint)
        self.assertIn("schedule", hint)

    def test_every_main_session_message_says_when(self):
        w = win(92, r5=NOW + 3600)
        deny = quota.pretool_decision(hook("Edit", file_path="a.py"), w, NOW, 0)
        self.assertIn("Work resumes", deny["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("Work resumes", quota.posttool_message(hook("Edit"), w, NOW))
        self.assertIn("Work resumes", quota.posttool_message(hook("Edit"), win(86), NOW))
        agent = quota.pretool_decision(hook("Agent"), win(82), NOW, 0)
        self.assertIn("Work resumes", agent["hookSpecificOutput"]["permissionDecisionReason"])


def hook(tool, agent=None, **inp):
    h = {"tool_name": tool, "tool_input": inp, "session_id": "s1"}
    if agent:
        h["agent_id"] = agent
    return h


class PretoolDecisionTest(unittest.TestCase):
    def test_ok_allows_agent(self):
        self.assertIsNone(quota.pretool_decision(hook("Agent"), win(50), NOW, running=5))

    def test_no_new_denies_agent_and_claim(self):
        self.assertIsNotNone(quota.pretool_decision(hook("Agent"), win(82), NOW, running=0))
        claim = hook("Bash", command="bd update proj-1 --claim")
        self.assertIsNotNone(quota.pretool_decision(claim, win(82), NOW, running=0))
        self.assertIsNone(
            quota.pretool_decision(hook("Edit", file_path="a.py"), win(82), NOW, running=0)
        )

    def test_fan_out_ceiling(self):
        self.assertIsNone(quota.pretool_decision(hook("Agent"), win(65), NOW, running=1))
        out = quota.pretool_decision(hook("Agent"), win(65), NOW, running=2)
        self.assertIn("2", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(quota.pretool_decision(hook("Agent"), win(55), NOW, running=9))

    def test_hard_allows_only_saving(self):
        w = win(90)
        allowed = [
            hook("Bash", command="git commit -m wip"),
            hook("Bash", command="bd update proj-1 --notes x"),
            hook("Edit", file_path="/repo/devlog/2026-10-21-x.md"),
            hook("Write", file_path="devlog/x.md"),
            hook("Edit", file_path="/repo/devlog.md"),
            hook("Edit", file_path="devlog.md"),
            hook("Read", file_path="a.py"),
            hook("CronCreate"),
            hook("ScheduleWakeup"),
            hook("mcp__claude-code-remote__send_later"),
            hook("mcp__claude-code-remote__delete_trigger"),
            hook("RemoteTrigger"),
            hook("Bash", command="BEADS_DIR=/repo/.beads bd list"),
            hook("Bash", command="env -C /repo git log -3"),
            hook("Bash", command="git show HEAD:a.py | grep -n foo | head -5"),
            hook("Bash", command="wc -l devlog.md; git status 2>&1"),
            hook("Bash", command="cd /repo && git diff --stat"),
            hook("Bash", command="git commit -m \"$(cat <<'EOF'\nwip: save; resume after reset\n\nnext | step\nEOF\n)\""),
            hook("Bash", command="git commit -m 'wip; resume && go'"),
        ]
        for h in allowed:
            self.assertIsNone(quota.pretool_decision(h, w, NOW, running=0), h)
        denied = [
            hook("Edit", file_path="backend/a.py"),
            hook("Edit", file_path="docs/devlog.md.bak"),
            hook("Bash", command="make test"),
            hook("Bash", command="git status && rm -rf x"),
            hook("Bash", command="FOO=1 make test"),
            hook("Bash", command="env -C /repo pytest"),
            hook("Bash", command="python3 x.py"),
            hook("Bash", command="git log | sh"),
            hook("Bash", command="cd /repo"),
            hook("mcp__claude-code-remote__create_session"),
        ]
        for h in denied:
            self.assertIsNotNone(quota.pretool_decision(h, w, NOW, running=0), h)

    def test_hard_denies_writes_disguised_as_saving(self):
        # Reviewers' examples: each passed as "saving work" before.
        w = win(90)
        denied = [
            "cat > src/app.py <<EOF\nprint('hi')\nEOF",
            "cat <<'EOF' > src/app.py\nprint('hi')\nEOF",
            "jq . a > src/x.json",
            "sort -o src/a.py b",
            "sort --output=src/a.py b",
            "git push --force origin main",
            "git push origin feat",
            "git reset --hard HEAD~3",
            "git checkout -- src/a.py",
            "git switch main",
            "git clean -fdx",
            "git status &> src/a.py",
            "git log >> notes.txt",
            "git diff >| patch.diff",
            "git diff --output=src/a.py",
            "git branch -D old",
            "git branch -m new-name",
            "git branch r1/new-branch",
            "git stash drop",
            "git worktree add ../w feat",
            "git remote add up https://example.com/x.git",
            "uniq a.txt src/a.py",
            "rg --pre=./run.sh foo",
            "git status & rm -rf x",
            "git log $(rm -rf x)",
            "git commit -m \"$(python3 gen.py)\"",
            "bash -c 'git status'",
        ]
        for command in denied:
            self.assertIsNotNone(quota.pretool_decision(hook("Bash", command=command), w, NOW, running=0), command)

    def test_hard_allows_reading_git_and_harmless_redirections(self):
        w = win(90)
        allowed = [
            "git status >/dev/null 2>&1",
            "git log --oneline -5 2>/dev/null | head -3",
            "git diff --stat >&2",
            "git add devlog.md && git commit -m 'wip: save before reset'",
            "git stash",
            "git stash push -m wip",
            "git stash list",
            "git rev-parse HEAD",
            "git ls-files devlog",
            "git branch",
            "git branch -vv",
            "git branch --show-current",
            "git branch -a --merged main",
            "git branch --list 'r1/*'",
            "git worktree list",
            "git remote -v",
            "sort -u notes.txt | uniq -c",
            "bd ready",
            "jq -c . .beads/issues.jsonl | wc -l",
            "git commit -m 'docs: why git push --force and > src/x are denied'",
        ]
        for command in allowed:
            self.assertIsNone(quota.pretool_decision(hook("Bash", command=command), w, NOW, running=0), command)

    def test_hard_subagent_may_only_read(self):
        w = win(90)
        self.assertIsNotNone(
            quota.pretool_decision(hook("Bash", "ag1", command="git commit"), w, NOW, 0)
        )
        self.assertIsNone(quota.pretool_decision(hook("Read", "ag1", file_path="a"), w, NOW, 0))


class FailClosedTest(unittest.TestCase):
    def test_off_by_default_and_from_env(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": d}):
            os.environ.pop("QUOTA_FAIL_CLOSED", None)
            self.assertFalse(quota.fail_closed())
            with mock.patch.dict(os.environ, {"QUOTA_FAIL_CLOSED": "1"}):
                self.assertTrue(quota.fail_closed())

    def test_from_fences_file_env_wins(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": d}):
            os.environ.pop("QUOTA_FAIL_CLOSED", None)
            (Path(d) / ".claude").mkdir()
            (Path(d) / ".claude" / "fences.env").write_text("FENCE_LEVEL=standard\nQUOTA_FAIL_CLOSED=1\n")
            self.assertTrue(quota.fail_closed())
            with mock.patch.dict(os.environ, {"QUOTA_FAIL_CLOSED": "0"}):
                self.assertFalse(quota.fail_closed())

    def test_no_data_denies_only_new_work(self):
        out = quota.no_data_decision(hook("Agent"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("QUOTA_FAIL_CLOSED", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNotNone(quota.no_data_decision(hook("Bash", command="bd update proj-1 --claim")))
        self.assertIsNone(quota.no_data_decision(hook("Edit", file_path="a.py")))


class PosttoolTest(unittest.TestCase):
    def test_silent_below_wrap(self):
        self.assertIsNone(quota.posttool_message(hook("Edit"), win(82), NOW))

    def test_wrap_main_vs_subagent(self):
        main = quota.posttool_message(hook("Edit"), win(86), NOW)
        sub = quota.posttool_message(hook("Edit", "ag1"), win(86), NOW)
        self.assertIn("devlog", main)
        self.assertIn("report", sub)
        self.assertNotIn("commit", sub)

    def test_notice_key_once_per_window(self):
        k1 = quota.notice_key(hook("Edit"), win(86), NOW)
        k2 = quota.notice_key(hook("Edit"), win(87), NOW)
        k3 = quota.notice_key(hook("Edit", "ag1"), win(86), NOW)
        k4 = quota.notice_key(hook("Edit"), win(90), NOW)
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertNotEqual(k1, k4)


class AgentsRegistryTest(unittest.TestCase):
    def test_add_remove_prune(self):
        reg = quota.agents_add({}, "ag1", "/p/example", NOW)
        reg = quota.agents_add(reg, "ag2", "/p/other", NOW - 3 * 3600)
        self.assertEqual(set(quota.agents_live(reg, NOW)), {"ag1"})
        reg = quota.agents_remove(reg, "ag1")
        self.assertEqual(quota.agents_live(reg, NOW), {})


class ProbeIsolationTest(unittest.TestCase):
    def test_probe_loads_no_user_plugins_or_mcp(self):
        cmd = quota.PROBE_CMD
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "local")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(json.loads(cmd[cmd.index("--mcp-config") + 1]), {"mcpServers": {}})


class ProbeBackoffTest(unittest.TestCase):
    def test_failed_probe_not_repeated_within_ttl(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch.dict(os.environ, {"CLAUDE_QUOTA_DIR": d}),
        ):
            with mock.patch.object(quota, "probe", return_value=None) as probe:
                self.assertIsNone(quota.current())
                self.assertIsNone(quota.current())
                self.assertEqual(probe.call_count, 1)
                quota.current(force=True)
                self.assertEqual(probe.call_count, 2)


if __name__ == "__main__":
    unittest.main()

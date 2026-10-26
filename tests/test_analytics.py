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
from analytics_lib import store, transcripts  # noqa: E402


def prompt(ts, text, origin=None, entrypoint="sdk-cli", branch="main"):
    r = {"type": "user", "timestamp": ts, "entrypoint": entrypoint, "gitBranch": branch,
         "message": {"role": "user", "content": text}}
    if origin:
        r["origin"] = origin
    return r


def tool_result(ts, text="ok"):
    return {"type": "user", "timestamp": ts, "entrypoint": "sdk-cli",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": text}]}}


def asst(ts, mid, out=10, cache_read=100, command=None, branch="main"):
    content = [{"type": "text", "text": "x"}]
    if command:
        content.append({"type": "tool_use", "name": "Bash", "id": "t", "input": {"command": command}})
    return {"type": "assistant", "timestamp": ts, "entrypoint": "sdk-cli", "gitBranch": branch,
            "message": {"id": mid, "role": "assistant", "model": "m", "content": content,
                        "usage": {"input_tokens": 1, "cache_creation_input_tokens": 5,
                                  "cache_read_input_tokens": cache_read, "output_tokens": out}}}


def write_jsonl(path, records, extra_lines=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records] + list(extra_lines)
    path.write_text("\n".join(lines) + "\n")


def T(h, m=0):
    return f"2026-10-20T{h:02d}:{m:02d}:00.000Z"


OWNER = store.Settings(owner={"peat", "ruslan_trachuk"})


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


class TranscriptTest(TempDirTest):
    def read(self, settings=OWNER):
        return transcripts.read_project([self.tmp / "proj"], settings)

    def session(self, records, sid="s1", extra_lines=()):
        write_jsonl(self.tmp / "proj" / f"{sid}.jsonl", records, extra_lines)

    def subagent(self, records, agent_type=None, sid="s1", name="agent-a1"):
        path = self.tmp / "proj" / sid / "subagents" / f"{name}.jsonl"
        write_jsonl(path, records)
        if agent_type:
            path.with_suffix(".meta.json").write_text(json.dumps({"agentType": agent_type}))

    def test_bad_lines_skipped(self):
        self.session([prompt(T(1), "hi", {"kind": "human"}), {"type": "assistant", "timestamp": T(1, 1)},
                      asst(T(1, 2), "m1")], extra_lines=['{"type": "user", "trunc'])
        turns, _ = self.read()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].tokens["direct"]["output"], 10)

    def test_dedup_by_message_id(self):
        self.session([prompt(T(1), "hi", {"kind": "human"})] + [asst(T(1, i), "m1", out=26) for i in range(3)])
        turns, _ = self.read()
        self.assertEqual(turns[0].tokens["direct"],
                         {"input": 1, "cache_write": 5, "cache_read": 100, "output": 26})

    def test_symlinked_file_counted_once(self):
        self.session([prompt(T(1), "hi", {"kind": "human"}), asst(T(1, 1), "m1")])
        (self.tmp / "proj" / "s1-link.jsonl").symlink_to(self.tmp / "proj" / "s1.jsonl")
        turns, _ = self.read()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].tokens["direct"]["output"], 10)

    def test_copied_history_counted_once(self):
        first = dict(prompt(T(1), "hi", {"kind": "human"}), uuid="u1")
        self.session([first, asst(T(1, 1), "m1")])
        self.session([first, asst(T(1, 1), "m1"), dict(prompt(T(2), "next", {"kind": "human"}), uuid="u2"),
                      asst(T(2, 1), "m2")], sid="s2")
        turns, _ = self.read()
        self.assertEqual([(t.session, t.start) for t in turns], [("s1", T(1)), ("s2", T(2))])
        self.assertEqual(sum(t.total()["output"] for t in turns), 20)

    def test_turn_kinds(self):
        cases = [
            (prompt(T(1), "do it", {"kind": "human"}), "owner"),
            (prompt(T(2), "plain old prompt"), "owner"),
            (prompt(T(3), '<channel source="plugin:telegram:telegram" user="pavel" ts="x">\nis it down?\n</channel>',
                    {"kind": "channel"}), "on_call"),
            (prompt(T(4), '<channel source="plugin:telegram:telegram" user="ruslan_trachuk">\nok\n</channel>',
                    {"kind": "channel"}), "owner"),
            (prompt(T(5), 'Another Claude session sent a message:\n<cross-session-message from="bridge:session_1">'
                          '\nsend it\n</cross-session-message>', {"kind": "peer", "from": "bridge:session_1"}), "owner"),
            (prompt(T(6), "<task-notification>done</task-notification>", {"kind": "task-notification"}), "unattended"),
            (prompt(T(7), '<cross-session-message from="uds:/x">hi</cross-session-message>',
                    {"kind": "peer", "from": "uds:/x"}), "unattended"),
            (prompt(T(8), "Check production now.", entrypoint="sdk-py"), "monitor"),
        ]
        records = []
        for i, (r, _) in enumerate(cases):
            records += [r, asst(r["timestamp"].replace(":00.000Z", ":30.000Z"), f"m{i}")]
        records.append(tool_result(T(9)))
        self.session(records)
        turns, _ = self.read()
        self.assertEqual([t.kind for t in turns], [k for _, k in cases])
        self.assertEqual([t.typed for t in turns], [k == "owner" for _, k in cases])

    def test_subagent_tokens_go_to_launching_turn(self):
        self.session([prompt(T(1), "a", {"kind": "human"}), asst(T(1, 1), "m1"),
                      prompt(T(2), "b", {"kind": "human"}), asst(T(2, 1), "m2")])
        self.subagent([asst(T(2, 5), "w1", out=7)], "workflow-subagent", name="agent-w")
        self.subagent([asst(T(2, 6), "r1", out=3)], "dark-factory:reviewer", name="agent-r")
        self.subagent([asst(T(1, 30), "e1", out=2)], "Explore", name="agent-e")
        no_meta = asst(T(1, 31), "g1", out=4)
        no_meta["attributionAgent"] = "general-purpose"
        self.subagent([no_meta], name="agent-g")
        turns, _ = self.read()
        self.assertEqual(turns[0].tokens["helpers"]["output"], 6)
        self.assertEqual(turns[0].tokens["pipeline"]["output"], 0)
        self.assertEqual(turns[1].tokens["pipeline"]["output"], 10)
        self.assertEqual(turns[1].tokens["direct"]["output"], 10)

    def test_channel_record_marked_meta_still_starts_a_turn(self):
        r = prompt(T(1), '<channel source="plugin:telegram:telegram" user="pavel">\nhello\n</channel>', {"kind": "channel"})
        r["isMeta"] = True
        self.session([r, asst(T(1, 1), "m1"), dict(prompt(T(2), "skill text"), isMeta=True), asst(T(2, 1), "m2")])
        turns, _ = self.read()
        self.assertEqual([t.kind for t in turns], ["on_call"])
        self.assertEqual(turns[0].tokens["direct"]["output"], 20)

    def test_workflow_agents_nested_under_subagents(self):
        self.session([prompt(T(1), "a", {"kind": "human"}), asst(T(1, 1), "m1")])
        path = self.tmp / "proj" / "s1" / "subagents" / "workflows" / "wf_1" / "agent-x.jsonl"
        write_jsonl(path, [asst(T(1, 5), "w1", out=9)])
        turns, _ = self.read()
        self.assertEqual(turns[0].tokens["pipeline"]["output"], 9)

    def test_friction_counts_owner_only(self):
        self.session([
            # deliberate non-ASCII test data: a Russian swear word, the owner's language
            prompt(T(1), "ну пиздец", {"kind": "human"}), asst(T(1, 1), "m1"),
            {"type": "user", "timestamp": T(1, 2), "message": {"role": "user", "content": [
                {"type": "text", "text": "[Request interrupted by user]"}]}},
            tool_result(T(1, 3), "The user doesn't want to proceed with this tool use. The tool use was rejected"),
            prompt(T(2), '<channel source="plugin:telegram:telegram" user="pavel">\nну пиздец\n</channel>',
                   {"kind": "channel"}), asst(T(2, 1), "m2"),
            prompt(T(3), "workshop is fine", {"kind": "human"}), asst(T(3, 1), "m3"),
        ])
        turns, _ = self.read()
        self.assertEqual([t.swear for t in turns], [True, False, False])
        self.assertEqual((turns[0].interrupts, turns[0].rejected), (1, 1))
        self.assertEqual(len(turns), 3)  # the interrupt and the tool result start no turn

    def test_test_calls(self):
        self.session([prompt(T(1), "run", {"kind": "human"}), asst(T(1, 1), "m1", out=8, command="cd app && pytest -q"),
                      tool_result(T(1, 2)), asst(T(1, 3), "m2", command="ls")])
        turns, _ = self.read()
        self.assertEqual(turns[0].test_calls, 1)
        self.assertEqual(turns[0].test_tokens["output"], 8)

    def test_pr_links_read(self):
        self.session([prompt(T(1), "go", {"kind": "human"}), asst(T(1, 1), "m1"),
                      {"type": "pr-link", "sessionId": "s1", "prNumber": 5, "prRepository": "o/r",
                       "timestamp": T(1, 5)}])
        _, links = self.read()
        self.assertEqual([(l.session, l.repo, l.number) for l in links], [("s1", "o/r", 5)])


if __name__ == "__main__":
    unittest.main()

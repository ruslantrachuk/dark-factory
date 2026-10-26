#!/usr/bin/env python3
"""Tests for analytics.py and analytics_lib: python3 tests/test_analytics.py"""
import json
import re
import subprocess
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from analytics_lib import codehost, collect, parts, render, store, transcripts  # noqa: E402


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

    def test_branch_mentions_read(self):
        self.session([prompt(T(1), "go", {"kind": "human"}),
                      asst(T(1, 1), "m1", command="git checkout -b fix/DEV-3-login origin/main && git push -u origin fix/DEV-3-login"),
                      asst(T(1, 2), "m2", command="scripts/merge-feature.sh feat/new-thing 'x'")])
        turns, _ = self.read()
        self.assertEqual(turns[0].mentions, {"fix/DEV-3-login", "feat/new-thing"})

    def test_pr_links_read(self):
        self.session([prompt(T(1), "go", {"kind": "human"}), asst(T(1, 1), "m1"),
                      {"type": "pr-link", "sessionId": "s1", "prNumber": 5, "prRepository": "o/r",
                       "timestamp": T(1, 5)}])
        _, links = self.read()
        self.assertEqual([(l.session, l.repo, l.number) for l in links], [("s1", "o/r", 5)])


class AttributionTest(unittest.TestCase):
    def turn(self, sid, ts, out=10, kind="owner", pipeline=0, branch=None):
        t = transcripts.Turn(sid, ts, kind)
        t.tokens["direct"]["output"] = out
        t.tokens["pipeline"]["output"] = pipeline
        if branch:
            t.branches[branch] += 1
        return t

    def test_tokens_up_to_pr_link(self):
        turns = [self.turn("s", T(1)), self.turn("s", T(2)), self.turn("s", T(3))]
        links = [transcripts.PrLink("s", T(2, 30), "o/r", 5)]
        costs, rest = transcripts.attribute(turns, links, {})
        self.assertEqual(costs[("o/r", 5)].tokens["output"], 20)
        self.assertEqual(rest["output"], 10)

    def test_second_link_takes_from_previous(self):
        turns = [self.turn("s", T(1)), self.turn("s", T(2), out=7)]
        links = [transcripts.PrLink("s", T(1, 30), "o/r", 5), transcripts.PrLink("s", T(2, 30), "o/r", 6)]
        costs, rest = transcripts.attribute(turns, links, {})
        self.assertEqual((costs[("o/r", 5)].tokens["output"], costs[("o/r", 6)].tokens["output"]), (10, 7))
        self.assertEqual(rest["output"], 0)

    def test_branch_fallback(self):
        turns = [self.turn("s", T(1), branch="feat/x"), self.turn("s", T(2), branch="main")]
        costs, rest = transcripts.attribute(turns, [], {("o/r", 7): "feat/x"})
        self.assertEqual(costs[("o/r", 7)].tokens["output"], 10)
        self.assertEqual(rest["output"], 10)

    def test_branch_named_in_a_command(self):
        t = self.turn("s", T(1))
        t.mentions.add("feat/DEV-9-x")
        costs, rest = transcripts.attribute([t, self.turn("s", T(2))], [], {("o/r", 9): "feat/DEV-9-x"})
        self.assertEqual(costs[("o/r", 9)].tokens["output"], 10)
        self.assertEqual(rest["output"], 10)

    def test_pipeline_flag_and_kind(self):
        turns = [self.turn("s", T(1), out=3, kind="owner"), self.turn("s", T(2), out=50, kind="unattended", pipeline=4)]
        costs, _ = transcripts.attribute(turns, [transcripts.PrLink("s", T(3), "o/r", 1)], {})
        self.assertTrue(costs[("o/r", 1)].pipeline)
        self.assertEqual(costs[("o/r", 1)].kind, "unattended")


def gh_pr(number, head, base="main", files=(("app/x.py", 10),)):
    return {"number": number, "headRefName": head, "baseRefName": base, "mergedAt": "2026-10-20T10:00:00Z",
            "files": [{"path": p, "additions": n, "deletions": 0} for p, n in files]}


class CodeHostTest(TempDirTest):
    def test_classify_defaults(self):
        rules = codehost.Rules()
        self.assertEqual(codehost.classify("web/src/App.tsx", rules), "frontend")
        self.assertEqual(codehost.classify("src/components/Button.vue", rules), "frontend")
        self.assertEqual(codehost.classify("app/api/x.py", rules), "backend")
        self.assertEqual(codehost.classify("tests/test_x.py", rules), "tests")
        self.assertEqual(codehost.classify("src/a.spec.ts", rules), "tests")
        self.assertEqual(codehost.classify("README.md", rules), "other")
        self.assertEqual(codehost.classify(".github/workflows/ci.yml", rules), "other")

    def test_project_override(self):
        env = self.tmp / ".claude" / "factory" / "analytics.env"
        env.parent.mkdir(parents=True)
        env.write_text('ANALYTICS_FRONTEND="miniapp/*"\nANALYTICS_BACKEND="web/server/*"\n')
        rules = codehost.Rules.for_project(self.tmp)
        self.assertEqual(codehost.classify("miniapp/main.py", rules), "frontend")
        self.assertEqual(codehost.classify("web/server/app.ts", rules), "backend")

    def test_pr_class_by_lines(self):
        rules = codehost.Rules()
        self.assertEqual(codehost.pr_class({"frontend": 70, "backend": 30}), "frontend")
        self.assertEqual(codehost.pr_class({"frontend": 69, "backend": 31}), "mixed")
        self.assertEqual(codehost.pr_class({"backend": 5, "tests": 100}), "backend")
        self.assertEqual(codehost.pr_class({"tests": 3, "other": 9}), "other")
        self.assertIsNotNone(rules)

    def test_promotion_prs_excluded(self):
        data = [gh_pr(1, "feat/a", base="develop"), gh_pr(2, "develop"), gh_pr(3, "main", base="release"),
                gh_pr(4, "fix/b")]
        with mock.patch.object(codehost, "gh_json", side_effect=[{"defaultBranchRef": {"name": "main"}}, data]):
            prs = codehost.merged_prs("o/r", "2026-W43", codehost.Rules())
        self.assertEqual([p.number for p in prs], [1, 4])
        self.assertEqual(prs[0].lines["backend"], 10)
        self.assertEqual(prs[0].cls, "backend")
        self.assertEqual(prs[0].head, "feat/a")

    def test_ci_minutes(self):
        runs = [{"startedAt": "2026-10-20T10:00:00Z", "updatedAt": "2026-10-20T10:05:30Z", "status": "completed"},
                {"startedAt": "2026-10-20T11:00:00Z", "updatedAt": "2026-10-20T11:01:00Z", "status": "completed"}]
        with mock.patch.object(codehost, "gh_json", return_value=runs):
            self.assertEqual(codehost.ci_runs("o/r", "2026-W43"), {"runs": 2, "minutes": 6.5})

    def test_gh_failure_returns_none(self):
        with mock.patch.object(codehost, "gh_json", return_value=None):
            self.assertIsNone(codehost.merged_prs("o/r", "2026-W43", codehost.Rules()))
            self.assertIsNone(codehost.ci_runs("o/r", "2026-W43"))

    def test_repo_of_parses_origin(self):
        for url in ("https://github.com/o/r.git", "git@github.com:o/r.git", "https://github.com/o/r"):
            with mock.patch.object(codehost, "git_origin", return_value=url):
                self.assertEqual(codehost.repo_of(self.tmp), "o/r")
        with mock.patch.object(codehost, "git_origin", return_value=None):
            self.assertIsNone(codehost.repo_of(self.tmp))


class PartsTest(TempDirTest):
    def git(self, *args, date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        if date:
            env.update(GIT_AUTHOR_DATE=f"{date}T12:00:00Z", GIT_COMMITTER_DATE=f"{date}T12:00:00Z")
        subprocess.run(["git", "-C", str(self.tmp), *args], check=True, capture_output=True, env=env)

    def commit(self, date, files):
        for rel, text in files.items():
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-qm", "c", date=date)

    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.commit("2026-09-01", {"README.md": "x"})

    def test_first_add_date(self):
        self.commit("2026-10-07", {"scripts/feedback-desk.sh": "x"})
        self.commit("2026-10-09", {"scripts/feedback-desk.sh": "y", "CODING_STANDARDS.md": "x"})
        got = parts.project_parts(self.tmp)
        self.assertEqual(got["on_call"], "2026-10-07")
        self.assertEqual(got["base"], "2026-10-09")

    def test_part_absent(self):
        self.assertEqual(parts.project_parts(self.tmp), {})
        self.assertEqual(parts.project_parts(self.tmp / "not-a-repo"), {})

    def test_plugin_pin_changes(self):
        pin = lambda ref: json.dumps({"extraKnownMarketplaces": {"dark-factory": {"source": {"ref": ref}}}})
        self.commit("2026-10-10", {".claude/settings.json": pin("v4")})
        self.commit("2026-10-11", {".claude/settings.json": pin("v4") + "\n"})
        self.commit("2026-10-15", {".claude/settings.json": pin("v8")})
        self.assertEqual(parts.plugin_pins(self.tmp), [["2026-10-10", "v4"], ["2026-10-15", "v8"]])

    def test_factory_releases_from_tags(self):
        self.git("tag", "v1")
        self.commit("2026-10-02", {"a": "1"})
        self.git("tag", "v2")
        self.git("tag", "not-a-release")
        self.assertEqual(parts.factory_parts(self.tmp, self.tmp / "units")["releases"],
                         {"v1": "2026-09-01", "v2": "2026-10-02"})


class CollectTest(TempDirTest):
    """One checkout `shop` (repo o/shop) with transcripts in W42 and W43."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "projects"
        self.checkout = self.tmp / "shop"
        self.checkout.mkdir()
        tdir = self.root / re.sub(r"[^A-Za-z0-9]", "-", str(self.checkout))
        write_jsonl(tdir / "s1.jsonl", [
            prompt("2026-10-14T10:00:00Z", "old work", {"kind": "human"}), asst("2026-10-14T10:01:00Z", "m0", out=4),
            prompt("2026-10-20T10:00:00Z", "fix it", {"kind": "human"}), asst("2026-10-20T10:01:00Z", "m1", out=10),
            {"type": "pr-link", "sessionId": "s1", "prNumber": 5, "prRepository": "o/shop",
             "timestamp": "2026-10-20T10:02:00Z"},
            prompt("2026-10-20T11:00:00Z", '<channel source="plugin:telegram:telegram" user="pavel">\nhi\n</channel>',
                   {"kind": "channel"}), asst("2026-10-20T11:01:00Z", "m2", out=3),
            {"type": "pr-link", "sessionId": "s1", "prNumber": 2, "prRepository": "o/canon",
             "timestamp": "2026-10-20T11:02:00Z"},
        ])
        env = mock.patch.dict(os.environ, {"ANALYTICS_STATE": str(self.tmp / "state")})
        env.start()
        self.addCleanup(env.stop)
        patches = [mock.patch.object(codehost, "repo_of", return_value="o/shop"),
                   mock.patch.object(parts, "project_parts", return_value={"on_call": "2026-10-07"}),
                   mock.patch.object(parts, "plugin_pins", return_value=[["2026-10-23", "v8"]]),
                   mock.patch.object(parts, "factory_parts", return_value={"releases": {"v9": "2026-10-23"},
                                                                           "server": {}}),
                   mock.patch.object(codehost, "gh_json", side_effect=self.fake_gh)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.gh_ok = True

    def fake_gh(self, args):
        if not self.gh_ok:
            return None
        if args[:2] == ["repo", "view"]:
            return {"defaultBranchRef": {"name": "main"}}
        if args[:2] == ["pr", "list"]:
            week = args[args.index("--search") + 1]
            if args[2:4] == ["-R", "o/shop"] and "2026-10-19" in week:
                return [gh_pr(5, "fix/a", files=(("app/x.py", 8), ("web/a.tsx", 2)))]
            return []
        if args[:2] == ["run", "list"]:
            return [{"startedAt": "2026-10-20T10:00:00Z", "updatedAt": "2026-10-20T10:03:00Z", "status": "completed"}]
        return None

    def run_collect(self, weeks, now="2026-10-27T06:00:00Z"):
        return collect.collect(weeks, [self.checkout], OWNER, canon=None, now=store.parse_ts(now), root=self.root)

    def test_collect_week_shape(self):
        data = self.run_collect(["2026-W43"])["2026-W43"]
        shop = data["projects"]["o/shop"]
        self.assertEqual(shop["first_week"], "2026-W42")
        self.assertEqual(shop["turns"], {"owner": 1, "on_call": 1})  # the canon is not one of this run's repositories
        self.assertEqual(shop["tokens"]["owner"]["output"], 10)
        self.assertEqual(shop["prs"], [{"number": 5, "head": "fix/a", "cls": "backend", "lines": {"frontend": 2, "backend": 8,
                                        "tests": 0, "other": 0}, "tokens": shop["prs"][0]["tokens"],
                                        "pipeline": False, "kind": "owner"}])
        self.assertEqual(shop["prs"][0]["tokens"]["output"], 14)  # the W42 turn led up to the PR too
        self.assertEqual(shop["ci"], {"runs": 1, "minutes": 3.0})
        self.assertEqual(shop["friction"], {"prompts": 1, "swear": 0, "interrupts": 0, "rejected": 0})
        self.assertEqual(shop["parts"], {"on_call": "2026-10-07"})
        self.assertTrue(data["final"])
        self.assertEqual(data["factory"]["releases"], {"v9": "2026-10-23"})
        self.assertEqual(store.load_week("2026-W43"), data)

    def test_outside_repository_work_stays_home(self):
        projects = self.run_collect(["2026-W43"])["2026-W43"]["projects"]
        self.assertEqual(list(projects), ["o/shop"])
        self.assertEqual(projects["o/shop"]["turns"], {"owner": 1, "on_call": 1})

    def test_turns_for_another_repo_go_there(self):
        with mock.patch.object(codehost, "repo_of", side_effect=lambda c: "o/canon" if c.name == "canon" else "o/shop"):
            data = collect.collect(["2026-W43"], [self.checkout], OWNER, canon=self.tmp / "canon",
                                   now=store.parse_ts("2026-10-27T06:00:00Z"), root=self.root)
        canon = data["2026-W43"]["projects"]["o/canon"]
        self.assertEqual(canon["turns"], {"on_call": 1})
        self.assertEqual(canon["tokens"]["on_call"]["output"], 3)
        self.assertEqual(canon["parts"], {})

    def test_gh_unavailable_still_collects(self):
        self.gh_ok = False
        shop = self.run_collect(["2026-W43"])["2026-W43"]["projects"]["o/shop"]
        self.assertIsNone(shop["prs"])
        self.assertIsNone(shop["ci"])
        self.assertEqual(shop["turns"], {"owner": 1, "on_call": 1})

    def test_recollect_overwrites_and_final_flag(self):
        self.assertFalse(self.run_collect(["2026-W43"], now="2026-10-22T00:00:00Z")["2026-W43"]["final"])
        self.run_collect(["2026-W43"])
        self.assertTrue(store.load_week("2026-W43")["final"])

    def test_weeks_to_collect(self):
        self.assertEqual(collect.weeks_to_collect("since-last", "2026-W38", "2026-W43", ["2026-W40"]),
                         ["2026-W40", "2026-W41", "2026-W42", "2026-W43"])
        self.assertEqual(collect.weeks_to_collect("since-last", "2026-W41", "2026-W43", []),
                         ["2026-W41", "2026-W42", "2026-W43"])
        self.assertEqual(collect.weeks_to_collect("all", "2026-W41", "2026-W42", ["2026-W42"]),
                         ["2026-W41", "2026-W42"])

    def test_oldest_week(self):
        self.assertEqual(collect.oldest_week([self.checkout], root=self.root), "2026-W42")


def tok(out, rest=0):
    return {"input": 0, "cache_write": 0, "cache_read": rest, "output": out}


def week_data(week="2026-W43", repos=("o/shop",), first=None, parts_=None):
    projects = {}
    for r in repos:
        projects[r] = {
            "first_week": (first or {}).get(r, "2026-W40"), "turns": {"owner": 3, "on_call": 1},
            "tokens": {"owner": tok(300, 9000), "on_call": tok(10, 90)},
            "split": {"direct": tok(200), "helpers": tok(60), "pipeline": tok(50)},
            "prs": [{"number": 5, "head": "feat/shop-cart", "cls": "backend", "lines": {"backend": 8, "frontend": 2,
                     "tests": 1, "other": 0}, "tokens": tok(120), "pipeline": True, "kind": "owner"}],
            "unattributed": tok(190), "ci": {"runs": 4, "minutes": 12.5},
            "tests": {"calls": 6, "tokens": tok(30)},
            "friction": {"prompts": 3, "swear": 1, "interrupts": 2, "rejected": 0},
            "parts": (parts_ or {}).get(r, {"base": "2026-10-01", "on_call": "2026-10-20"}), "pins": [["2026-10-23", "v8"]]}
    return {"week": week, "collected_at": "2026-10-27T05:20:00Z", "final": True, "projects": projects,
            "factory": {"releases": {"v9": "2026-10-23"}, "server": {"fleet_watch": "2026-10-23"}}}


class RenderTest(TempDirTest):
    def test_aliases_stable_and_new_project_next_letter(self):
        path = self.tmp / "aliases.json"
        self.assertEqual(render.aliases(["o/b", "o/a"], path, None), {"o/a": "A", "o/b": "B"})
        self.assertEqual(render.aliases(["o/c", "o/a", "o/canon"], path, "o/canon"),
                         {"o/a": "A", "o/b": "B", "o/c": "C", "o/canon": "canon"})

    def test_render_has_reading_notes(self):
        md, _ = render.render_week(week_data(), {"o/shop": "A"})
        head = md.split("\n## ")[0]
        self.assertIn("2026-W43", head)
        self.assertIn("How to read", head)
        self.assertIn("cache", head.lower())
        self.assertIn("approximate", head.lower())

    def test_render_has_no_real_names(self):
        md, data = render.render_week(week_data(), {"o/shop": "A"})
        blob = md + json.dumps(data)
        for term in ("o/shop", "shop", "feat/shop-cart"):
            self.assertNotIn(term, blob)
        self.assertIn("A", data["projects"])
        self.assertNotIn("number", json.dumps(data))
        self.assertNotIn("head", json.dumps(data["projects"]))

    def test_render_week_numbers(self):
        md, _ = render.render_week(week_data(), {"o/shop": "A"})
        self.assertIn("| A |", md)
        self.assertRegex(md, r"(?i)on-call")
        self.assertIn("12.5", md)  # CI minutes
        self.assertIn("new this week", render.render_week(week_data(first={"o/shop": "2026-W43"}),
                                                          {"o/shop": "A"})[0])

    def test_summary_marks_first_week_and_parts(self):
        weeks = [week_data("2026-W42", parts_={"o/shop": {"base": "2026-10-01"}}),
                 week_data("2026-W43", parts_={"o/shop": {"base": "2026-10-01", "on_call": "2026-10-20"}})]
        md = render.render_summary(weeks, {"o/shop": "A"})
        self.assertIn("2026-W42", md)
        self.assertIn("2026-W43", md)
        self.assertIn("A: on_call", md)  # the part's first week is marked
        self.assertIn("v9", md)
        self.assertNotIn("shop", md)

    def test_leak_check_whole_word(self):
        terms = render.clean_terms({"shop", "main", "ab", "Kids-CRM"})
        self.assertEqual(terms, {"shop", "kids-crm"})
        files = {"a.md": "Shop is here", "b.md": "a workshop", "c.md": "about kids-crm today"}
        self.assertEqual(render.leak_check(files, terms), [("a.md", "shop"), ("c.md", "kids-crm")])

    def test_leak_terms_from_sources(self):
        with mock.patch.object(codehost, "repo_of", return_value="acme/kids-crm"), \
                mock.patch.object(render.socket, "gethostname", return_value="vps-123"):
            terms = render.leak_terms([Path("/opt/clients/kids-crm")], [week_data(repos=("acme/kids-crm",))],
                                      store.Settings(owner={"ruslan_trachuk"}), canon_repo="acme/dark-factory")
        for t in ("kids-crm", "acme/kids-crm", "acme", "clients", "vps-123", "ruslan_trachuk", "shop-cart"):
            self.assertIn(t, terms)
        self.assertNotIn("dark-factory", terms)
        self.assertNotIn("main", terms)


if __name__ == "__main__":
    unittest.main()

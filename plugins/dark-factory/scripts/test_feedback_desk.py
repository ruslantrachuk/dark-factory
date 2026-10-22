#!/usr/bin/env python3
"""Tests of templates/feedback-desk/scripts/feedback-desk.sh: the permission rules and the On-call's two Bash
subcommands (accept, release). gh and release.sh are stubs; stdlib only."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "feedback-desk"
LINK = "https://t.me/c/123/45"

GH_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
echo "$*" >> "$dir/gh.log"
if [ "$1 $2" = "pr view" ]; then cat "$dir/pr-$3.json" 2>/dev/null || exit 1; fi
exit 0
"""

RELEASE_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")/.."
if [ "$1" = "--list-unaccepted" ]; then cat "$dir/unaccepted.tsv" 2>/dev/null; exit 0; fi
echo "DF_ROLE=${DF_ROLE:-} $*" >> "$dir/release.log"
"""


class DeskCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / ".claude/feedback-desk").mkdir(parents=True)
        shutil.copy(TEMPLATE / "scripts/feedback-desk.sh", self.root / "scripts/feedback-desk.sh")
        shutil.copy(TEMPLATE / ".claude/feedback-desk/config.env", self.root / ".claude/feedback-desk/config.env")
        (self.root / ".claude/feedback-desk/ROLE.md").write_text("role\n")
        for path, text in ((self.root / "gh", GH_STUB), (self.root / "scripts/release.sh", RELEASE_STUB)):
            path.write_text(text)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith(("DESK_", "DF_"))},
            "DESK_WORKDIR": str(self.root), "DESK_GH": str(self.root / "gh"),
            "DESK_STATE_DIR": str(self.root / "state"), "DESK_OWNER_IDS": "1, 2",
            "DESK_PLUGIN": "telegram@claude-plugins-official",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def desk(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(self.root / "scripts/feedback-desk.sh"), *args],
                              env={**self.env, **env}, capture_output=True, text=True, cwd=self.root)

    def pr(self, number: int, *, state: str = "MERGED", labels: tuple[str, ...] = (), requested: str | None = None) -> None:
        body = "## Done\nx\n"
        if requested is not None:
            body += f"\n## Requested by\n{requested}\n\n## Open questions\nnone\n"
        (self.root / f"pr-{number}.json").write_text(
            json.dumps({"state": state, "labels": [{"name": n} for n in labels], "body": body}))

    def gh_calls(self) -> list[str]:
        log = self.root / "gh.log"
        return log.read_text().splitlines() if log.exists() else []

    def release_calls(self) -> list[str]:
        log = self.root / "release.log"
        return log.read_text().splitlines() if log.exists() else []

    def unaccepted(self, *rows: str) -> None:
        (self.root / "unaccepted.tsv").write_text("".join(r + "\n" for r in rows))


class RulesTest(DeskCase):
    def allow(self, **env: str) -> list[str]:
        out = self.desk("rules", **env)
        self.assertEqual(out.returncode, 0, out.stderr)
        line = next(x for x in out.stdout.splitlines() if x.startswith("allow: "))
        return line[len("allow: "):].split(",")

    def test_telegram_tools_are_allowed_by_name_next_to_the_server_rule(self) -> None:
        rules = self.allow()
        server = "mcp__plugin_telegram_telegram"
        self.assertIn(server, rules)
        for tool in ("reply", "react", "edit_message", "download_attachment"):
            self.assertIn(f"{server}__{tool}", rules)

    def test_bash_is_allowed_only_for_accept_and_release(self) -> None:
        bash = [r for r in self.allow() if r.startswith("Bash")]
        self.assertEqual(bash, ["Bash(scripts/feedback-desk.sh accept *)", "Bash(scripts/feedback-desk.sh release)",
                                "Bash(scripts/feedback-desk.sh release *)"])

    def test_board_tools_come_from_the_config(self) -> None:
        self.assertFalse([r for r in self.allow() if "Linear" in r])
        rules = self.allow(DESK_BOARD_TOOLS="mcp__claude_ai_Linear__save_issue,mcp__claude_ai_Linear__save_comment")
        self.assertIn("mcp__claude_ai_Linear__save_issue", rules)
        self.assertIn("mcp__claude_ai_Linear__save_comment", rules)

    def test_session_gets_the_on_call_role_in_both_environments(self) -> None:
        text = (TEMPLATE / "scripts/feedback-desk.sh").read_text()
        self.assertIn("DF_UNATTENDED=1 DF_ROLE=on-call", text)  # the env prefix
        self.assertIn('\\"DF_ROLE\\":\\"on-call\\"', text)  # --settings env


class AcceptTest(DeskCase):
    def test_requester_accepts_a_merged_pr(self) -> None:
        self.pr(12, requested="Vlad (tg 42), https://t.me/c/123/40")

        out = self.desk("accept", "12", "42", LINK)

        self.assertEqual(out.returncode, 0, out.stderr)
        calls = self.gh_calls()
        self.assertIn("pr edit 12 --add-label accepted", calls)
        self.assertIn(f"pr comment 12 --body accepted by Vlad (tg 42), {LINK}", calls)

    def test_owner_accepts_anything(self) -> None:
        self.pr(12, requested="Vlad (tg 42)")
        self.pr(13)

        for number in ("12", "13"):
            self.assertEqual(self.desk("accept", number, "2", LINK).returncode, 0)

        self.assertIn(f"pr comment 13 --body accepted by the owner (tg 2), {LINK}", self.gh_calls())

    def test_someone_else_is_refused_and_nothing_is_marked(self) -> None:
        self.pr(12, requested="Vlad (tg 42)")

        out = self.desk("accept", "12", "99", LINK)

        self.assertEqual(out.returncode, 1)
        self.assertIn("neither the requester", out.stdout)
        self.assertFalse([c for c in self.gh_calls() if c.startswith(("pr edit", "pr comment"))])

    def test_pr_without_requester_only_owners_accept(self) -> None:
        self.pr(12)
        self.assertEqual(self.desk("accept", "12", "42", LINK).returncode, 1)
        self.assertEqual(self.desk("accept", "12", "1", LINK).returncode, 0)

    def test_unmerged_or_unreadable_pr_is_refused(self) -> None:
        self.pr(12, state="OPEN", requested="Vlad (tg 42)")
        self.assertEqual(self.desk("accept", "12", "42", LINK).returncode, 1)
        self.assertEqual(self.desk("accept", "77", "1", LINK).returncode, 1)
        self.assertFalse([c for c in self.gh_calls() if c.startswith(("pr edit", "pr comment"))])

    def test_already_accepted_is_a_noop(self) -> None:
        self.pr(12, labels=("accepted",), requested="Vlad (tg 42)")

        out = self.desk("accept", "12", "42", LINK)

        self.assertEqual(out.returncode, 0)
        self.assertIn("already accepted", out.stdout)
        self.assertFalse([c for c in self.gh_calls() if c.startswith(("pr edit", "pr comment"))])

    def test_malformed_arguments_are_refused(self) -> None:
        self.pr(12, requested="Vlad (tg 42)")
        for args in (("12", "42"), ("x", "42", LINK), ("12", "4 2", LINK), ("12", "42", "not a link"),
                     ("12", "42", "https://t.me/x; rm -rf /"), ("12", "42", "http://t.me/c/1/2")):
            self.assertNotEqual(self.desk("accept", *args).returncode, 0, args)
        self.assertFalse([c for c in self.gh_calls() if c.startswith(("pr edit", "pr comment"))])


class ReleaseTest(DeskCase):
    def test_plain_release_runs_the_script_as_the_on_call(self) -> None:
        out = self.desk("release")

        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.release_calls(), ["DF_ROLE=on-call "])

    def test_requester_of_every_unaccepted_feature_may_include_them(self) -> None:
        self.unaccepted("12\tDark theme\tVlad (tg 42), https://t.me/c/123/40",
                        "14\tExport\tVlad (tg 42), https://t.me/c/123/41")

        out = self.desk("release", "--include-unaccepted", "42", LINK)

        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.release_calls(), [f"DF_ROLE=on-call --include-unaccepted Vlad (tg 42), {LINK}"])

    def test_requester_of_only_one_feature_is_refused(self) -> None:
        self.unaccepted("12\tDark theme\tVlad (tg 42)", "14\tExport\tPasha (tg 7)")

        out = self.desk("release", "--include-unaccepted", "42", LINK)

        self.assertEqual(out.returncode, 1)
        self.assertIn("Export", out.stdout)
        self.assertEqual(self.release_calls(), [])

    def test_owner_may_include_anything_even_a_non_pr_merge(self) -> None:
        self.unaccepted("12\tDark theme\tPasha (tg 7)", "-\tMerge branch hotfix\tnot a pull request (abc12345)")

        out = self.desk("release", "--include-unaccepted", "1", LINK)

        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.release_calls(), [f"DF_ROLE=on-call --include-unaccepted the owner (tg 1), {LINK}"])

    def test_a_non_pr_merge_is_not_for_a_requester(self) -> None:
        self.unaccepted("-\tMerge branch hotfix\tnot a pull request (abc12345)")

        self.assertEqual(self.desk("release", "--include-unaccepted", "42", LINK).returncode, 1)
        self.assertEqual(self.release_calls(), [])

    def test_nothing_unaccepted_means_a_plain_release(self) -> None:
        self.unaccepted()

        out = self.desk("release", "--include-unaccepted", "42", LINK)

        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.release_calls(), ["DF_ROLE=on-call "])

    def test_other_options_are_refused(self) -> None:
        for args in (("--owner-accepts",), ("--manual",), ("--include-unaccepted", "42"),
                     ("--include-unaccepted", "x", LINK), ("--include-unaccepted", "42", "nope")):
            self.assertNotEqual(self.desk("release", *args).returncode, 0, args)
        self.assertEqual(self.release_calls(), [])


if __name__ == "__main__":
    unittest.main()

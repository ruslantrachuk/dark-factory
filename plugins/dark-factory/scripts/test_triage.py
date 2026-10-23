#!/usr/bin/env python3
"""Tests of triage.py, the daily queue review: python3 plugins/dark-factory/scripts/test_triage.py
bd and claude are stubs on PATH (claude answers the review, or the delivery run when it is given --tools),
git is a real temporary repository."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import triage  # noqa: E402

NOW = datetime.now(timezone.utc)

BD_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
case "$*" in
  "list --status open "*) cat "$dir/open.json" ;;
  "list --status in_progress "*) cat "$dir/wip.json" ;;
  *) echo "unexpected: $*" >&2; exit 1 ;;
esac
"""

CLAUDE_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
if printf '%s\\n' "$@" | grep -qx -- --tools; then
  printf '%s\\n' "$@" > "$dir/deliver.args"
  cat "$dir/sent.json" 2>/dev/null || echo '{"structured_output": {"sent": false}}'
  exit 0
fi
printf '%s\\n' "$@" > "$dir/claude.args"
echo "DF_UNATTENDED=${DF_UNATTENDED:-}" > "$dir/claude.env"
cat "$dir/verdicts.json"
"""


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def task(i: str, status: str, quiet: float, title: str = "a task") -> dict:
    return {"id": i, "title": title, "status": status, "priority": 2, "issue_type": "task",
            "created_at": ago(quiet + 5), "updated_at": ago(quiet)}


class TriageCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "shop"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, text in (("bd", BD_STUB), ("claude", CLAUDE_STUB)):
            path = self.bin / name
            path.write_text(text)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@x", "-c", "init.defaultBranch=main"]
        subprocess.run([*git, "init", "-q", str(self.project)], check=True)
        g = [*git, "-C", str(self.project)]
        subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run([*g, "checkout", "-q", "-b", "feat/x"], check=True)
        subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "work"], check=True)
        subprocess.run([*g, "checkout", "-q", "main"], check=True)
        subprocess.run([*g, "merge", "-q", "--no-ff", "feat/x", "-m", "Merge pull request #7\n\nCloses p-9"],
                       check=True)
        self.path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}:{self.path}"
        self.queue(open_=[task("p-1", "open", 20), task("p-2", "open", 2), task("p-9", "open", 1)],
                   wip=[task("p-5", "in_progress", 4), task("p-6", "in_progress", 1)])
        self.saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("TRIAGE_", "DESK_"))}

    def tearDown(self) -> None:
        os.environ["PATH"] = self.path
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def queue(self, open_: list[dict], wip: list[dict]) -> None:
        (self.bin / "open.json").write_text(json.dumps(open_))
        (self.bin / "wip.json").write_text(json.dumps(wip))

    def verdicts(self, items: list[dict]) -> None:
        (self.bin / "verdicts.json").write_text(json.dumps({"result": "", "structured_output": {"items": items}}))


class FactsTest(TriageCase):
    def test_candidates_are_stale_or_named_by_a_merge(self) -> None:
        f = triage.facts(self.project, NOW)
        self.assertEqual((f["open"], f["wip"], f["old"]), (3, 2, 1))
        signals = {c["id"]: c["signal"] for c in f["candidates"]}
        self.assertEqual(sorted(signals), ["p-1", "p-5", "p-9"])  # fresh p-2 and p-6 are left alone
        self.assertIn("open, no change for 20 days", signals["p-1"])
        self.assertIn("in progress, no change for 4 days", signals["p-5"])
        self.assertIn("named by merge", signals["p-9"])

    def test_an_id_inside_a_longer_id_is_not_a_mention(self) -> None:
        self.queue(open_=[task("p-9", "open", 1), task("p-90", "open", 1)], wip=[])
        ids = [c["id"] for c in triage.facts(self.project, NOW)["candidates"]]
        self.assertEqual(ids, ["p-9"])


class ReviewTest(TriageCase):
    def test_the_review_is_read_only_and_unattended(self) -> None:
        cands = triage.facts(self.project, NOW)["candidates"]
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "done"}])
        triage.review(self.project, cands, {})
        args = (self.bin / "claude.args").read_text().splitlines()
        self.assertIn("product owner", args[args.index("--append-system-prompt") + 1].lower())
        self.assertNotIn("--agent", args)  # --agent drops --json-schema
        self.assertIn("dontAsk", args)
        self.assertEqual(args[args.index("--setting-sources") + 1], "project,local")  # never plugin:telegram
        self.assertIn("--max-budget-usd", args)
        self.assertEqual(Path(args[args.index("--plugin-dir") + 1]), HERE.parent)
        for tool in ("Edit", "Write"):
            self.assertIn(tool, args[args.index("--disallowedTools"):])
        self.assertEqual((self.bin / "claude.env").read_text().strip(), "DF_UNATTENDED=1")

    def test_unknown_ids_and_bad_verdicts_are_dropped_and_reasons_capped(self) -> None:
        cands = triage.facts(self.project, NOW)["candidates"]
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "x\n" * 200},
                       {"id": "p-1", "verdict": "keep", "why": "a second verdict for the same id"},
                       {"id": "other", "verdict": "close", "why": "not a candidate"},
                       {"id": "p-5", "verdict": "burn", "why": "no such verdict"}])
        items = triage.review(self.project, cands, {})
        self.assertEqual([(i["id"], i["verdict"]) for i in items], [("p-1", "close")])
        self.assertLessEqual(len(items[0]["why"]), triage.WHY_MAX)
        self.assertNotIn("\n", items[0]["why"])


class RunTest(TriageCase):
    def run_main(self, *args: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return triage.main([str(self.project), *args])

    def test_report_numbers_close_then_defer_and_is_kept_for_the_answer(self) -> None:
        self.verdicts([{"id": "p-5", "verdict": "defer", "why": "later"},
                       {"id": "p-1", "verdict": "close", "why": "obsolete"},
                       {"id": "p-9", "verdict": "keep", "why": "client asked"}])
        self.assertEqual(self.run_main(), 1)  # no owner, no bot token: not sent, but written
        report = json.loads((self.project / ".claude/state/triage/latest.json").read_text())
        self.assertEqual([(i["id"], i.get("n")) for i in report["items"]], [("p-5", 2), ("p-1", 1), ("p-9", None)])
        history = (self.project / ".claude/state/triage/history.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(history[-1])["open"], 3)

    def test_the_report_goes_into_the_on_call_session_and_nowhere_else(self) -> None:
        os.environ["DESK_NAME"] = "On-call shop"
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "obsolete"}])
        (self.bin / "sent.json").write_text('{"structured_output": {"sent": true}}')
        self.assertEqual(self.run_main(), 0)
        prompt = (self.bin / "deliver.args").read_text()  # one argument per line; the prompt spans many
        args = prompt.splitlines()
        self.assertEqual(args[args.index("--tools") + 1], "SendMessage,ListAgents")  # no other tool
        self.assertIn("'On-call shop'", prompt)
        self.assertIn("never in the group", prompt)
        self.assertIn("1. p-1", prompt)
        (self.bin / "sent.json").write_text('{"structured_output": {"sent": false}}')
        self.assertEqual(self.run_main(), 1)  # not delivered: the report stays in latest.json

    def test_render_leads_with_the_distance_to_clean(self) -> None:
        f = {"open": 30, "wip": 2, "old": 20}
        items = [{"id": "p-1", "verdict": "close", "why": "done", "n": 1},
                 {"id": "p-2", "verdict": "ask", "why": "still needed?"}]
        text = triage.render("shop", f, items, {"p-1": "Fix it"}, {"TRIAGE_LANG": "ru", "TRIAGE_LIMIT": "15"}, 31, 4)
        head = text.splitlines()[0]
        self.assertIn("открыто 30 (лимит 15)", head)
        self.assertIn("вчера 31", head)
        self.assertIn("1. p-1 — Fix it — done", text)
        self.assertIn("? p-2", text)
        self.assertIn("ещё 4", text)
        self.assertIn("«кроме 3 7»", text)

    def test_a_quiet_day_sends_nothing(self) -> None:
        self.queue(open_=[task("p-2", "open", 2)], wip=[])
        self.assertEqual(self.run_main(), 0)
        self.assertFalse((self.bin / "claude.args").exists())  # no candidates — no model

    def test_dry_run_writes_nothing(self) -> None:
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "obsolete"}])
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertFalse((self.project / ".claude/state/triage").exists())


if __name__ == "__main__":
    unittest.main()

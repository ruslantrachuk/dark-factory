#!/usr/bin/env python3
"""Tests of triage.py, the daily queue review: python3 tests/test_triage.py
bd, claude and tmux are stubs on PATH, git is a real temporary repository."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"
sys.path.insert(0, str(HERE))
import triage  # noqa: E402

NOW = datetime.now(timezone.utc)

BD_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
case "$*" in
  "list --status open "*) cat "$dir/open.json" ;;
  "list --status in_progress "*) cat "$dir/wip.json" ;;
  close*|defer*) echo "$*" >> "$dir/bd.log" ;;
  *) echo "unexpected: $*" >&2; exit 1 ;;
esac
"""

CLAUDE_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
printf '%s\\n' "$@" > "$dir/claude.args"
echo "DF_UNATTENDED=${DF_UNATTENDED:-}" > "$dir/claude.env"
cat "$dir/verdicts.json"
"""

TMUX_STUB = """#!/usr/bin/env bash
dir="$(dirname "$0")"
printf '%s\\n' "$@" >> "$dir/tmux.log"
echo "--" >> "$dir/tmux.log"
"""


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def task(i: str, status: str, quiet: float, title: str = "a task") -> dict:
    return {"id": i, "title": title, "status": status, "priority": 2, "issue_type": "task",
            "created_at": ago(quiet + 5), "updated_at": ago(quiet)}


def silent(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class TriageCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "shop"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, text in (("bd", BD_STUB), ("claude", CLAUDE_STUB), ("tmux", TMUX_STUB)):
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
        self.saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("TRIAGE_", "SESSION_"))}

    def tearDown(self) -> None:
        os.environ["PATH"] = self.path
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def queue(self, open_: list[dict], wip: list[dict]) -> None:
        (self.bin / "open.json").write_text(json.dumps(open_))
        (self.bin / "wip.json").write_text(json.dumps(wip))

    def verdicts(self, items: list[dict]) -> None:
        (self.bin / "verdicts.json").write_text(json.dumps({"result": "", "structured_output": {"items": items}}))

    def log(self, name: str) -> list[str]:
        path = self.bin / name
        return path.read_text().splitlines() if path.exists() else []


class FactsTest(TriageCase):
    def test_candidates_are_stale_or_named_by_a_merge(self) -> None:
        f = triage.facts(self.project, NOW)
        self.assertEqual((f["open"], f["wip"], f["old"]), (3, 2, 1))
        signals = {c["id"]: c["signal"] for c in f["candidates"]}
        self.assertEqual(sorted(signals), ["p-1", "p-5", "p-9"])  # fresh p-2 and p-6 are left alone
        self.assertIn("open, no change for 20 days", signals["p-1"])
        self.assertIn("in progress, no change for 4 days", signals["p-5"])
        self.assertIn("named by merge", signals["p-9"])
        self.assertEqual([(t["id"], t["status"]) for t in f["fresh"]], [("p-2", "open"), ("p-6", "in_progress")])

    def test_an_id_inside_a_longer_id_is_not_a_mention(self) -> None:
        self.queue(open_=[task("p-9", "open", 1), task("p-90", "open", 1)], wip=[])
        ids = [c["id"] for c in triage.facts(self.project, NOW)["candidates"]]
        self.assertEqual(ids, ["p-9"])


class ReviewTest(TriageCase):
    def test_the_review_is_read_only_and_unattended(self) -> None:
        cands = triage.facts(self.project, NOW)["candidates"]
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "done"}])
        triage.review(self.project, cands, {})
        args = self.log("claude.args")
        self.assertIn("product owner", args[args.index("--append-system-prompt") + 1].lower())
        self.assertNotIn("--agent", args)  # --agent drops --json-schema
        self.assertIn("dontAsk", args)
        self.assertEqual(args[args.index("--setting-sources") + 1], "project,local")  # never plugin:telegram
        self.assertEqual(Path(args[args.index("--plugin-dir") + 1]), HERE.parent)
        self.assertIn("--max-budget-usd", args)
        for tool in ("Edit", "Write"):
            self.assertIn(tool, args[args.index("--disallowedTools"):])
        self.assertEqual(self.log("claude.env"), ["DF_UNATTENDED=1"])

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
        return silent(triage.main, [str(self.project), *args])

    def test_the_report_opens_a_review_session_and_is_kept_for_the_answer(self) -> None:
        self.verdicts([{"id": "p-5", "verdict": "defer", "why": "later"},
                       {"id": "p-1", "verdict": "close", "why": "obsolete"},
                       {"id": "p-9", "verdict": "keep", "why": "client asked"}])
        self.assertEqual(self.run_main(), 0)
        report = json.loads((self.project / ".claude/state/triage/latest.json").read_text())
        self.assertEqual([(i["id"], i.get("n")) for i in report["items"]], [("p-5", 2), ("p-1", 1), ("p-9", None)])
        history = (self.project / ".claude/state/triage/history.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(history[-1])["open"], 3)
        calls = "\n".join(self.log("tmux.log")).split("\n--\n")
        self.assertIn("kill-session", calls[0])  # yesterday's unanswered review is replaced
        new = calls[1].splitlines()
        self.assertEqual(new[:4], ["-L", "df-shop", "-f", "/dev/null"])
        self.assertEqual(new[new.index("-s") + 1], "triage")
        command = "\n".join(new[new.index(str(self.project)) + 1:])
        self.assertIn("--remote-control 'Queue review · shop · ", command)
        self.assertIn("dontAsk", command)
        self.assertIn("triage.py apply *)", command)  # the answer goes through apply, nothing else writes
        self.assertNotIn("Bash(bd close", command)
        self.assertIn("1. p-1", command)

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

    def test_render_accounts_for_what_it_did_not_review(self) -> None:
        wip = [{"id": f"w-{k}", "title": f"step {k}", "status": "in_progress"} for k in range(32)]
        f = {"open": 1, "wip": 32, "old": 0, "fresh": [{"id": "o-1", "title": "new", "status": "open"}, *wip]}
        text = triage.render("shop", f, [], {}, {"TRIAGE_LANG": "ru"}, None, 0)
        self.assertIn("Не разбирались, менялись недавно: в работе 32 (моложе 3 дн.), открыто 1 (моложе 14 дн.):", text)
        self.assertIn("· w-0 — step 0", text)
        self.assertIn("· w-29 — step 29", text)
        self.assertNotIn("w-30", text)
        self.assertIn("· +2", text)
        self.assertNotIn("o-1", text)  # fresh open tasks are counted, not listed

    def test_a_quiet_day_opens_nothing(self) -> None:
        self.queue(open_=[task("p-2", "open", 2)], wip=[])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.log("claude.args"), [])  # no candidates — no model
        self.assertEqual(self.log("tmux.log"), [])

    def test_dry_run_writes_nothing(self) -> None:
        self.verdicts([{"id": "p-1", "verdict": "close", "why": "obsolete"}])
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertFalse((self.project / ".claude/state/triage").exists())
        self.assertEqual(self.log("tmux.log"), [])


class ApplyTest(TriageCase):
    """The owner's answer closes or defers exactly the numbered items of the latest report, each once."""

    def report(self, hours_ago: float = 1) -> Path:
        stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - hours_ago * 3600))
        items = [{"id": "p-1", "verdict": "close", "why": "done in #12", "n": 1},
                 {"id": "p-2", "verdict": "close", "why": "nobody asked", "n": 2},
                 {"id": "p-3", "verdict": "defer", "why": "later", "n": 3},
                 {"id": "p-4", "verdict": "keep", "why": "client asked"},
                 {"id": "p-5", "verdict": "ask", "why": "still needed?"}]
        path = self.project / ".claude/state/triage/latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stamp": stamp, "items": items}))
        return path

    def apply(self, answer: str) -> int:
        return silent(triage.main, ["apply", answer, "--project", str(self.project)])

    def touched(self) -> list[str]:
        return [c.split()[1] for c in self.log("bd.log")]

    def test_yes_applies_every_numbered_item(self) -> None:
        self.report()
        self.assertEqual(self.apply("да"), 0)
        calls = self.log("bd.log")
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0].startswith("close p-1 --reason done in #12 — queue review "), calls)
        self.assertEqual(calls[2], "defer p-3")

    def test_except_and_only(self) -> None:
        self.report()
        self.assertEqual(self.apply("кроме 2"), 0)
        self.assertEqual(self.touched(), ["p-1", "p-3"])
        (self.bin / "bd.log").unlink()
        self.report()
        self.assertEqual(self.apply("only 2"), 0)
        self.assertEqual(self.touched(), ["p-2"])

    def test_each_item_is_applied_once(self) -> None:
        path = self.report()
        self.apply("1")
        self.apply("yes")
        self.assertEqual(self.touched(), ["p-1", "p-2", "p-3"])
        self.assertEqual(json.loads(path.read_text())["applied"], [1, 2, 3])

    def test_refusals_touch_nothing(self) -> None:
        self.report()
        for answer in ("4", "close everything you like", "", "keep 1"):
            with self.subTest(answer=answer):
                self.assertNotEqual(self.apply(answer), 0)
        self.assertEqual(self.touched(), [])

    def test_a_stale_or_missing_report_is_refused(self) -> None:
        self.assertNotEqual(self.apply("yes"), 0)
        self.report(hours_ago=80)
        self.assertNotEqual(self.apply("yes"), 0)
        self.assertEqual(self.touched(), [])


if __name__ == "__main__":
    unittest.main()

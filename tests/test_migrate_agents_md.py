"""v23 -> v24 rules layout migration: python3 tests/test_migrate_agents_md.py (stdlib only)."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"))

import canon_block  # noqa: E402
import migrate_agents_md as mig  # noqa: E402

TITLE = "# acme — CLAUDE.md\n\n"
SECTIONS = ("## Overview\n\n**acme** — invoices for plumbers.\n\n## Project settings\n\n- **Main branch:** `main`\n\n"
            "## Project constraints\n\n- ⛔ no PII in logs\n")
V23_CLAUDE = TITLE + mig.OLD_INTRO + "\n\n" + mig.OLD_IMPORT + "\n\n" + SECTIONS
ENV_CONTEXT = "#!/usr/bin/env bash\necho '🖥️ ENV=vps — acme may deploy the stand'\n"
V23_SETTINGS = {
    "permissions": {"deny": ["Read(./.env*)"]},
    "hooks": {"SessionStart": [{"matcher": "", "hooks": [
        {"command": "command -v bd >/dev/null 2>&1 && bd prime || true", "type": "command"},
        {"command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/env-context.sh\"", "type": "command"},
        {"command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/session-context.sh\"", "type": "command"},
        {"command": "bash scripts/acme-warmup.sh", "type": "command"},
    ]}]},
}


class MigrateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        files = {
            "CLAUDE.md": V23_CLAUDE,
            ".claude/canon/CLAUDE.md": "# Operating canon\n\nold v23 text\n",
            ".claude/skills/ship/SKILL.md": "---\nname: ship\n---\nacme ship\n",
            ".claude/skills/feedback-desk/SKILL.md": "---\nname: feedback-desk\n---\n",
            ".claude/skills/acme-release/SKILL.md": "---\nname: acme-release\n---\nour own\n",
            ".claude/hooks/env-context.sh": ENV_CONTEXT,
            ".claude/hooks/session-context.sh": "#!/usr/bin/env bash\necho header\n",
            ".claude/hooks/acme-extra.sh": "#!/usr/bin/env bash\n",
            ".claude/settings.json": json.dumps(V23_SETTINGS, indent=2) + "\n",
        }
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mig.main(["--project", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        return sorted((str(p.relative_to(self.root)), p.is_symlink() or p.read_bytes())
                      for p in self.root.rglob("*") if p.is_file() or p.is_symlink())


class DryRunTest(MigrateCase):
    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        before = self.snapshot()
        code, out, _ = self.run_main()
        self.assertEqual(code, mig.EXIT_OWNER)  # the settings edit is left for the owner
        self.assertIn("dry run", out)
        self.assertIn("WRITE AGENTS.md", out)
        self.assertIn("MOVE .claude/skills/ship -> .agents/skills/ship", out)
        self.assertIn("LINK .claude/skills -> ../.agents/skills", out)
        self.assertEqual(self.snapshot(), before)


class ApplyTest(MigrateCase):
    def setUp(self):
        super().setUp()
        self.code, self.out, _ = self.run_main("--apply")
        self.agents = (self.root / "AGENTS.md").read_text()

    def test_agents_md_keeps_the_sections_and_takes_the_canon_where_the_import_was(self):
        self.assertTrue(self.agents.startswith("# acme — AGENTS.md\n\n" + mig.NEW_INTRO + "\n\n"))
        self.assertTrue(self.agents.endswith("<!-- dark-factory:canon:end -->\n\n" + SECTIONS))
        self.assertNotIn(mig.OLD_IMPORT, self.agents)
        self.assertEqual(canon_block.main(["check", str(self.root / "AGENTS.md")]), canon_block.EXIT_OK)

    def test_claude_md_imports_agents_md(self):
        self.assertEqual((self.root / "CLAUDE.md").read_text().splitlines()[0], "@AGENTS.md")

    def test_old_canon_file_is_gone(self):
        self.assertFalse((self.root / ".claude/canon").exists())

    def test_skills_move_behind_the_link(self):
        link = self.root / ".claude/skills"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../.agents/skills")
        for name in ("ship", "feedback-desk", "acme-release"):
            self.assertTrue((self.root / ".agents/skills" / name / "SKILL.md").is_file(), name)
        self.assertIn("our own", (link / "acme-release/SKILL.md").read_text())

    def test_header_scripts_move_with_their_project_text(self):
        self.assertEqual((self.root / "scripts/agent/env-context.sh").read_text(), ENV_CONTEXT)
        self.assertTrue((self.root / "scripts/agent/session-context.sh").is_file())
        start = self.root / "scripts/agent/session-start.sh"
        self.assertTrue(os.access(start, os.X_OK))
        self.assertTrue((self.root / ".claude/hooks/acme-extra.sh").is_file())
        self.assertFalse((self.root / ".claude/hooks/env-context.sh").exists())
        self.assertIn("KEEP .claude/hooks/: acme-extra.sh", self.out)

    def test_settings_are_printed_not_written(self):
        self.assertEqual(json.loads((self.root / ".claude/settings.json").read_text()), V23_SETTINGS)
        self.assertEqual(self.code, mig.EXIT_OWNER)
        self.assertIn("fence file", self.out)
        _, out, _ = self.run_main("--json")
        groups = json.loads(out)["session_start"]
        commands = [h["command"] for g in groups for h in g["hooks"]]
        self.assertEqual(commands, [mig.NEW_START, "bash scripts/acme-warmup.sh"])

    def test_second_run_has_nothing_to_move(self):
        before = self.snapshot()
        code, out, _ = self.run_main("--apply")
        self.assertIn("nothing to do", out)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(code, mig.EXIT_OWNER)  # settings still point at the old scripts until the owner edits them

    def test_after_the_settings_edit_nothing_is_left(self):
        path = self.root / ".claude/settings.json"
        data = json.loads(path.read_text())
        _, out, _ = self.run_main("--json")
        data["hooks"]["SessionStart"] = json.loads(out)["session_start"]
        path.write_text(json.dumps(data, indent=2))
        code, out, _ = self.run_main()
        self.assertEqual(code, mig.EXIT_DONE)
        self.assertIn("nothing to do", out)


class EdgeTest(MigrateCase):
    def test_agents_md_with_text_of_its_own_stops_before_any_change(self):
        (self.root / "AGENTS.md").write_text("# acme agents\n\nUse pnpm.\n")
        before = self.snapshot()
        code, _, err = self.run_main("--apply")
        self.assertEqual(code, mig.EXIT_STOP)
        self.assertIn("text of its own", err)
        self.assertEqual(self.snapshot(), before)

    def test_agents_md_pointer_is_replaced(self):
        (self.root / "AGENTS.md").write_text("@CLAUDE.md\n")
        code, out, _ = self.run_main("--apply")
        self.assertIn("REPLACE AGENTS.md", out)
        self.assertIn("<!-- dark-factory:canon:begin", (self.root / "AGENTS.md").read_text())

    def test_skill_name_taken_in_agents_skills_keeps_both_and_no_link(self):
        (self.root / ".agents/skills/ship").mkdir(parents=True)
        (self.root / ".agents/skills/ship/SKILL.md").write_text("newer\n")
        code, out, _ = self.run_main("--apply")
        self.assertEqual(code, mig.EXIT_OWNER)
        self.assertIn("KEEP .claude/skills/ship", out)
        self.assertTrue((self.root / ".claude/skills/ship/SKILL.md").is_file())
        self.assertFalse((self.root / ".claude/skills").is_symlink())
        self.assertTrue((self.root / ".agents/skills/acme-release/SKILL.md").is_file())

    def test_claude_md_without_the_import_gets_the_block_before_its_sections(self):
        (self.root / "CLAUDE.md").write_text(TITLE + SECTIONS)
        code, out, _ = self.run_main("--apply")
        text = (self.root / "AGENTS.md").read_text()
        self.assertLess(text.index("dark-factory:canon:begin"), text.index("## Overview"))
        self.assertIn("did not import the canon", out)

    def test_v24_project_has_nothing_to_do(self):
        target = Path(self.tmp.name) / "fresh"
        target.mkdir()
        for rel in ("AGENTS.md", "CLAUDE.md"):
            (target / rel).write_bytes((mig.TEMPLATE / rel).read_bytes())
        out = io.StringIO()
        with redirect_stdout(out):
            code = mig.main(["--project", str(target)])
        self.assertEqual(code, mig.EXIT_DONE)
        self.assertIn("nothing to do", out.getvalue())


if __name__ == "__main__":
    unittest.main()

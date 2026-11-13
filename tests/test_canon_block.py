"""Canon block in AGENTS.md: python3 tests/test_canon_block.py (stdlib only)."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"))

import canon_block as cb  # noqa: E402

CANON = "# Operating canon\n\n## Contract\n\n1. Code goes out only through the standard procedure.\n"
CANON_V2 = CANON + "2. The work queue is beads.\n"
PROJECT_HEAD = "# proj — AGENTS.md\n\n> Single entry point for agents and humans.\n\n"
PROJECT_TAIL = "## Overview\n\n**proj** — does things.\n\n## Project constraints\n\n- ⛔ no PII in logs\n"


class CanonBlockCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.canon = self.dir / "canon.md"
        self.canon.write_text(CANON)
        self.agents = self.dir / "AGENTS.md"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv, version=24):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cb.main(["--canon", str(self.canon), "--version", str(version), *argv])
        return code, out.getvalue(), err.getvalue()

    def project_with_block(self, canon=CANON, version=24, nl="\n"):
        text = PROJECT_HEAD + cb.render(canon, version) + "\n" + PROJECT_TAIL
        self.agents.write_bytes(text.replace("\n", nl).encode())
        return text.replace("\n", nl)


class RenderTest(CanonBlockCase):
    def test_render_wraps_canon_in_markers_with_version(self):
        block = cb.render(CANON, 24)
        self.assertTrue(block.startswith("<!-- dark-factory:canon:begin v24 -->\n# Operating canon\n"))
        self.assertTrue(block.endswith("only through the standard procedure.\n<!-- dark-factory:canon:end -->\n"))

    def test_render_command_prints_block(self):
        code, out, _ = self.run_main("render")
        self.assertEqual(code, 0)
        self.assertEqual(out, cb.render(CANON, 24))


class CheckTest(CanonBlockCase):
    def test_current_block(self):
        self.project_with_block()
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_OK)
        self.assertIn("current: v24", out)

    def test_edited_block_differs(self):
        text = self.project_with_block().replace("1. Code goes out", "1. Code may go out")
        self.agents.write_text(text)
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_DIFFERS)
        self.assertIn("differs", out)

    def test_older_version_marker_differs(self):
        self.project_with_block(version=23)
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_DIFFERS)
        self.assertIn("v23", out)

    def test_no_block_is_broken(self):
        self.agents.write_text(PROJECT_HEAD + PROJECT_TAIL)
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertIn("no canon block", out)

    def test_duplicate_block_is_broken(self):
        block = cb.render(CANON, 24)
        self.agents.write_text(PROJECT_HEAD + block + block + PROJECT_TAIL)
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertIn("2 and 2", out)

    def test_unpaired_marker_is_broken(self):
        self.agents.write_text(PROJECT_HEAD + "<!-- dark-factory:canon:begin v24 -->\n" + CANON + PROJECT_TAIL)
        code, _, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_BROKEN)

    def test_end_before_begin_is_broken(self):
        self.agents.write_text("<!-- dark-factory:canon:end -->\n" + CANON + "<!-- dark-factory:canon:begin v24 -->\n")
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertIn("before", out)

    def test_too_large(self):
        self.project_with_block()
        code, out, _ = self.run_main("--max-bytes", "100", "check", str(self.agents))
        self.assertEqual(code, cb.EXIT_TOO_LARGE)
        self.assertIn("too large", out)

    def test_near_the_limit_is_current_with_a_note(self):
        self.agents.write_text(PROJECT_HEAD + cb.render(CANON, 24) + "x" * (cb.NEAR_BYTES + 10))
        code, out, _ = self.run_main("check", str(self.agents))
        self.assertEqual(code, cb.EXIT_OK)
        self.assertIn("near the size limit", out)

    def test_json_output(self):
        self.project_with_block()
        code, out, _ = self.run_main("check", str(self.agents), "--json")
        data = json.loads(out)
        self.assertEqual((code, data["status"], data["version"]), (0, "current", 24))

    def test_missing_file(self):
        code, _, err = self.run_main("check", str(self.dir / "nope.md"))
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertIn("no such file", err)


class ApplyTest(CanonBlockCase):
    def test_replace_keeps_outside_text_byte_for_byte(self):
        self.project_with_block()
        self.canon.write_text(CANON_V2)
        code, _, _ = self.run_main("apply", str(self.agents), version=25)
        self.assertEqual(code, 0)
        text = self.agents.read_text()
        self.assertTrue(text.startswith(PROJECT_HEAD))
        self.assertTrue(text.endswith("\n" + PROJECT_TAIL))
        self.assertIn("2. The work queue is beads.", text)
        self.assertIn("begin v25", text)
        self.assertEqual(self.run_main("check", str(self.agents), version=25)[0], cb.EXIT_OK)

    def test_replace_overwrites_hand_edits_inside_block(self):
        text = self.project_with_block().replace("1. Code goes out", "1. Code may go out")
        self.agents.write_text(text)
        self.run_main("apply", str(self.agents))
        self.assertNotIn("may go out", self.agents.read_text())

    def test_crlf_file_keeps_crlf(self):
        self.project_with_block(nl="\r\n")
        self.canon.write_text(CANON_V2)
        self.run_main("apply", str(self.agents))
        raw = self.agents.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(b"2. The work queue is beads.\r\n", raw)

    def test_current_file_is_untouched(self):
        self.project_with_block()
        before = self.agents.stat().st_mtime_ns
        code, out, _ = self.run_main("apply", str(self.agents))
        self.assertEqual(code, 0)
        self.assertIn("nothing to do", out)
        self.assertEqual(self.agents.stat().st_mtime_ns, before)

    def test_dry_run_prints_diff_and_writes_nothing(self):
        original = self.project_with_block()
        self.canon.write_text(CANON_V2)
        code, out, _ = self.run_main("apply", str(self.agents), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("+2. The work queue is beads.", out)
        self.assertEqual(self.agents.read_text(), original)

    def test_no_block_without_insert_stops(self):
        self.agents.write_text(PROJECT_HEAD + PROJECT_TAIL)
        code, _, err = self.run_main("apply", str(self.agents))
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertIn("--insert", err)
        self.assertEqual(self.agents.read_text(), PROJECT_HEAD + PROJECT_TAIL)

    def test_insert_goes_before_first_section(self):
        self.agents.write_text(PROJECT_HEAD + PROJECT_TAIL)
        code, _, _ = self.run_main("apply", str(self.agents), "--insert")
        self.assertEqual(code, 0)
        text = self.agents.read_text()
        self.assertTrue(text.startswith(PROJECT_HEAD + "<!-- dark-factory:canon:begin v24 -->"))
        self.assertTrue(text.endswith("<!-- dark-factory:canon:end -->\n\n" + PROJECT_TAIL))

    def test_insert_into_file_without_sections_appends(self):
        self.agents.write_text("# proj")
        self.run_main("apply", str(self.agents), "--insert")
        self.assertEqual(self.agents.read_text(), "# proj\n\n" + cb.render(CANON, 24))

    def test_broken_file_is_not_changed(self):
        broken = PROJECT_HEAD + "<!-- dark-factory:canon:begin v24 -->\n" + PROJECT_TAIL
        self.agents.write_text(broken)
        code, _, _ = self.run_main("apply", str(self.agents), "--insert")
        self.assertEqual(code, cb.EXIT_BROKEN)
        self.assertEqual(self.agents.read_text(), broken)

    def test_too_large_result_is_not_written(self):
        original = self.project_with_block()
        self.canon.write_text(CANON_V2)
        code, _, err = self.run_main("--max-bytes", "100", "apply", str(self.agents))
        self.assertEqual(code, cb.EXIT_TOO_LARGE)
        self.assertIn("limit", err)
        self.assertEqual(self.agents.read_text(), original)


class CanonSourceTest(CanonBlockCase):
    def test_canon_source_with_a_block_gives_the_block_text(self):
        self.canon.write_text("# tpl — AGENTS.md\n\nintro\n\n" + cb.render(CANON_V2, 24) + "\n## Overview\n")
        self.agents.write_text(PROJECT_HEAD + PROJECT_TAIL)
        self.run_main("apply", str(self.agents), "--insert")
        text = self.agents.read_text()
        self.assertIn("2. The work queue is beads.", text)
        self.assertNotIn("# tpl", text)
        self.assertNotIn("intro", text)

    def test_broken_canon_source_stops(self):
        self.canon.write_text("<!-- dark-factory:canon:begin v24 -->\n" + CANON)
        self.agents.write_text(PROJECT_HEAD + PROJECT_TAIL)
        with self.assertRaises(SystemExit):
            self.run_main("apply", str(self.agents), "--insert")


class PluginDefaultsTest(unittest.TestCase):
    def test_version_is_plugin_major(self):
        manifest = json.loads(cb.MANIFEST.read_text())
        self.assertEqual(cb.plugin_version(), int(manifest["version"].split(".")[0]))

    def test_real_canon_fits_with_room_for_the_project(self):
        size = len(cb.render(cb.load_canon(cb.DEFAULT_CANON), cb.plugin_version()).encode())
        self.assertLess(size, cb.MAX_BYTES - 4096, "the canon leaves under 4 KiB for the project's own sections")

    def test_template_agents_md_is_current_and_fits(self):
        self.assertEqual(cb.main(["check", str(cb.DEFAULT_CANON)]), cb.EXIT_OK)


if __name__ == "__main__":
    unittest.main()

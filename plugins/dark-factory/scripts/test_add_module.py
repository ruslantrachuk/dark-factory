"""add-module.sh and deploy-base.sh find their files in the plugin: python3 plugins/dark-factory/scripts/test_add_module.py"""

import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent


def add(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(HERE / "add-module.sh"), *args, "--project", str(project)],
                          capture_output=True, text=True)


class AddModuleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_lists_and_writes_nothing(self):
        proc = add(self.project, "on-call", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("COPY: scripts/feedback-desk.sh", proc.stdout)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_aliases_copy_the_module_without_its_manifest(self):
        for alias, expected in (("on-call", "scripts/feedback-desk.sh"),
                                ("monitor", "scripts/ops/prod_monitor/prod-monitor.sh"),
                                ("release", "scripts/release.sh")):
            with tempfile.TemporaryDirectory() as d:
                proc = add(Path(d), alias)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue((Path(d) / expected).is_file(), alias)
                self.assertFalse((Path(d) / "MANIFEST.md").exists(), alias)
                self.assertTrue((Path(d) / expected).stat().st_mode & 0o111, alias)

    def test_release_installs_the_workflow_and_the_tests(self):
        add(self.project, "release")
        self.assertTrue((self.project / ".github/workflows/release.yml").is_file())
        self.assertTrue((self.project / "app/tests/integration/test_release_script.py").is_file())

    def test_project_without_a_value_is_refused(self):
        for args in (["release", "--project"], ["release", "--project", ""]):
            proc = subprocess.run(["bash", str(HERE / "add-module.sh"), *args], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("✗ --project needs a directory", proc.stderr)

    def test_never_overwrites(self):
        (self.project / "scripts").mkdir()
        (self.project / "scripts/feedback-desk.sh").write_text("mine\n")
        proc = add(self.project, "feedback-desk")
        self.assertIn("SKIP (exists): scripts/feedback-desk.sh", proc.stdout)
        self.assertEqual((self.project / "scripts/feedback-desk.sh").read_text(), "mine\n")

    def test_every_module_has_a_directory_and_a_setup_section(self):
        for module in ("feedback-desk", "prod-monitor", "release-tag", "observability", "code-audit", "feature-pipeline"):
            manifest = (PLUGIN / "templates" / module / "MANIFEST.md").read_text()
            self.assertIn("## Setup by /dark-factory:add", manifest, module)
        proc = add(self.project, "no-such-module")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(add(self.project, "base").returncode, 2)


class FindsFilesInThePluginTest(unittest.TestCase):
    """From a project directory with no checkout of the repository anywhere near, both scripts resolve the plugin."""

    def test_deploy_base_dry_run_uses_the_plugin_templates(self):
        with tempfile.TemporaryDirectory() as d:
            proc = subprocess.run(["bash", str(HERE / "deploy-base.sh"), str(Path(d) / "app"), "--dry-run"],
                                  capture_output=True, text=True, cwd=d)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("COPY: .claude/canon/CLAUDE.md", proc.stdout)
            self.assertIn("Template: dark-factory plugin templates/base @", proc.stdout)

    def test_harness_diff_reads_the_canon_from_the_plugin_directory(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "app"
            subprocess.run(["bash", str(HERE / "deploy-base.sh"), str(project)], check=True, capture_output=True)
            self.assertRegex((project / ".harness/base-sha").read_text().strip(), r"^(v\d+|[0-9a-f]{40})$")
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            proc = subprocess.run(["bash", str(project / "scripts/harness-diff.sh"), str(PLUGIN)],
                                  capture_output=True, text=True, cwd=project)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("identical", proc.stdout)
            self.assertNotIn("missing", proc.stdout)


if __name__ == "__main__":
    unittest.main()

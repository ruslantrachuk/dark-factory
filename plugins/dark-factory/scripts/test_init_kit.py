"""Solo kit scaffolding tests: python3 plugins/dark-factory/scripts/test_init_kit.py (stdlib only)."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import init_kit  # noqa: E402

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run(project: Path, *args: str, config: Path | None = None) -> str:
    out = io.StringIO()
    env = {**GIT_ENV, "CLAUDE_CONFIG_DIR": str(config or project / "no-config")}
    env.pop("CLAUDE_PROJECT_DIR", None)
    with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out):
        assert init_kit.main(["--project", str(project), *args]) == 0
    return out.getvalue()


def git(project: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=project, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


class InitKitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "app"
        self.project.mkdir()
        git(self.project, "init", "-q", "-b", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return sorted(str(p.relative_to(self.project)) for p in self.project.rglob("*")
                      if p.is_file() and p.relative_to(self.project).parts[0] != ".git")

    def test_dry_run_writes_nothing(self):
        out = run(self.project)
        self.assertIn("CREATE: scripts/merge-feature.sh", out)
        self.assertIn("Dry run", out)
        self.assertEqual(self.files(), [])
        hooks_path = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=self.project, env=GIT_ENV,
                                    capture_output=True, text=True)
        self.assertEqual(hooks_path.stdout, "")

    def test_apply_creates_the_kit_with_placeholders_filled(self):
        run(self.project, "--apply", "--main-branch", "trunk", "--test-cmd", "python3 -m pytest -q")
        self.assertEqual(self.files(), [".claude/fences.env", ".claude/settings.json", ".githooks/pre-push",
                                        "CLAUDE.md", "scripts/merge-feature.sh"])
        merge = (self.project / "scripts/merge-feature.sh").read_text()
        self.assertIn("MAIN_BRANCH='trunk'", merge)
        self.assertIn("MERGE_FLAG='--merge'", merge)
        self.assertNotIn("<main>", merge)
        self.assertTrue(os.access(self.project / "scripts/merge-feature.sh", os.X_OK))
        self.assertIn("TEST_CMD='python3 -m pytest -q'", (self.project / ".githooks/pre-push").read_text())
        self.assertIn("FENCE_LEVEL=solo", (self.project / ".claude/fences.env").read_text())
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertEqual(settings["enabledPlugins"], {"dark-factory@dark-factory": True})
        self.assertIn("dark-factory", settings["extraKnownMarketplaces"])
        self.assertEqual(git(self.project, "config", "--get", "core.hooksPath"), ".githooks")

    def test_never_overwrites_and_appends_the_block_once(self):
        (self.project / "CLAUDE.md").write_text("# Mine\n\nmy rules\n")
        (self.project / "scripts").mkdir()
        (self.project / "scripts/merge-feature.sh").write_text("my own\n")
        (self.project / ".claude").mkdir()
        (self.project / ".claude/settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ls:*)"]}, "enabledPlugins": {"dark-factory@dark-factory": False}}))
        out = run(self.project, "--apply")
        self.assertIn("SKIP (exists): scripts/merge-feature.sh", out)
        self.assertIn("APPEND kit block: CLAUDE.md", out)
        self.assertIn("MERGE extraKnownMarketplaces.dark-factory", out)
        self.assertEqual((self.project / "scripts/merge-feature.sh").read_text(), "my own\n")
        claude = (self.project / "CLAUDE.md").read_text()
        self.assertTrue(claude.startswith("# Mine\n\nmy rules\n"))
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertIs(settings["enabledPlugins"]["dark-factory@dark-factory"], False)  # the owner's choice stays
        again = run(self.project, "--apply")
        self.assertIn("SKIP (kit block present): CLAUDE.md", again)
        self.assertEqual((self.project / "CLAUDE.md").read_text(), claude)
        self.assertNotIn("CREATE", again)

    def test_other_hooks_path_is_kept(self):
        git(self.project, "config", "core.hooksPath", ".husky")
        out = run(self.project, "--apply")
        self.assertIn("SKIP (set to '.husky'", out)
        self.assertEqual(git(self.project, "config", "--get", "core.hooksPath"), ".husky")

    def test_marketplace_source_from_this_machine(self):
        config = Path(self.tmp.name) / "config"
        (config / "plugins").mkdir(parents=True)
        source = {"source": "github", "repo": "acme/dark-factory"}
        (config / "plugins/known_marketplaces.json").write_text(json.dumps({"dark-factory": {"source": source}}))
        run(self.project, "--apply", config=config)
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertEqual(settings["extraKnownMarketplaces"]["dark-factory"]["source"], source)
        override = init_kit.marketplace_source("me/fork")
        self.assertEqual(override, {"source": "github", "repo": "me/fork"})

    def test_marketplace_source_never_a_local_folder(self):
        config = Path(self.tmp.name) / "config"
        (config / "plugins").mkdir(parents=True)
        known = config / "plugins/known_marketplaces.json"
        known.write_text(json.dumps({"dark-factory": {"source": {"source": "directory", "path": "/home/me/df"}}}))
        run(self.project, "--apply", config=config)
        source = json.loads((self.project / ".claude/settings.json").read_text())["extraKnownMarketplaces"]
        self.assertEqual(source["dark-factory"]["source"]["repo"], "ruslantrachuk/dark-factory")
        known.write_text(json.dumps({"dark-factory": {"source": {"source": "git",
                                                                  "url": "git@github.com:acme/dark-factory.git"}}}))
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config)}):
            self.assertEqual(init_kit.marketplace_source(None), {"source": "github", "repo": "acme/dark-factory"})

    def test_solo_settings_name_the_published_repository(self):
        kit = json.loads((init_kit.SOLO / ".claude/settings.json").read_text())
        self.assertEqual(kit["extraKnownMarketplaces"]["dark-factory"]["source"]["repo"], "ruslantrachuk/dark-factory")

    def test_apply_says_to_commit_the_fence_files(self):
        out = run(self.project, "--apply")
        for name in (".claude/fences.env", ".claude/settings.json", ".githooks/", "scripts/merge-feature.sh",
                     "git clean"):
            self.assertIn(name, out)

    def test_main_branch_from_origin_head(self):
        origin = Path(self.tmp.name) / "origin.git"
        git(Path(self.tmp.name), "init", "-q", "--bare", "-b", "trunk", str(origin))
        git(self.project, "remote", "add", "origin", str(origin))
        git(self.project, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertEqual(init_kit.detect_main_branch(self.project), "trunk")

    def test_kit_pre_push_is_a_no_op_without_a_test_command(self):
        run(self.project, "--apply")
        hook = self.project / ".githooks/pre-push"
        proc = subprocess.run([str(hook), "origin"], cwd=self.project, input="", env=GIT_ENV,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no test command configured", proc.stderr)
        hook.write_text(hook.read_text().replace("TEST_CMD=''", "TEST_CMD='false'"))
        proc = subprocess.run([str(hook), "origin"], cwd=self.project, input="", env=GIT_ENV,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("BLOCKED", proc.stderr)

    def test_merge_flag_takes_a_bare_word_or_the_equals_form(self):
        for given in (["--merge-flag", "squash"], ["--merge-flag=--squash"], ["--merge-flag=squash"]):
            shutil.rmtree(self.project / "scripts", ignore_errors=True)
            run(self.project, "--apply", *given)
            self.assertIn("MERGE_FLAG='--squash'", (self.project / "scripts/merge-feature.sh").read_text())

    def test_main_branch_without_origin_head_follows_the_repository(self):
        git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        git(self.project, "branch", "-m", "master")
        self.assertEqual(init_kit.detect_main_branch(self.project), "master")
        out = run(self.project)
        self.assertIn("main branch: master", out)
        self.assertNotIn("AMBIGUOUS", out)

    def test_ambiguous_main_branch_is_said_in_the_dry_run(self):
        git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        git(self.project, "branch", "master")
        out = run(self.project)
        self.assertIn("AMBIGUOUS", out)

    def test_other_hooks_path_warns_that_the_test_gate_is_not_active(self):
        git(self.project, "config", "core.hooksPath", ".husky")
        out = run(self.project)
        self.assertIn("WARNING", out)
        self.assertIn("NOT active", out)
        self.assertIn(".githooks/pre-push", out)

    def test_kit_pre_push_skips_branch_deletes(self):
        run(self.project, "--apply")
        hook = self.project / ".githooks/pre-push"
        hook.write_text(hook.read_text().replace("TEST_CMD=''", "TEST_CMD='false'"))
        zero = "0" * 40
        proc = subprocess.run([str(hook), "origin"], cwd=self.project, env=GIT_ENV, capture_output=True, text=True,
                              input=f"(delete) {zero} refs/heads/x {'a' * 40}\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = subprocess.run([str(hook), "origin"], cwd=self.project, env=GIT_ENV, capture_output=True, text=True,
                              input=f"refs/heads/x {'b' * 40} refs/heads/x {'a' * 40}\n")
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()

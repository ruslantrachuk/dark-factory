#!/usr/bin/env python3
"""Repository-level checks: python3 scripts/test_repo.py (stdlib only).

The dark-factory plugin is the single source of the always-on hooks; templates/base relies on it.
These tests hold that wiring: the kit copy of merge-feature.sh matches the canon, the plugin's
hooks point at files that exist, and base neither ships nor registers what moved into the plugin.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/dark-factory"
BASE = ROOT / "templates/base"


class PluginKitSyncTest(unittest.TestCase):
    def test_kit_matches_the_canon(self):
        proc = subprocess.run(["bash", str(ROOT / "scripts/sync-plugin-kit.sh"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class PluginWiringTest(unittest.TestCase):
    def test_manifests_agree(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        entry = next(p for p in market["plugins"] if p["name"] == "dark-factory")
        self.assertEqual(market["name"], "dark-factory")
        self.assertEqual((ROOT / entry["source"]).resolve(), PLUGIN)
        self.assertEqual(plugin["name"], "dark-factory")

    def test_hook_commands_point_at_plugin_files(self):
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        commands = [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]
        self.assertTrue(commands)
        for command in commands:
            paths = re.findall(r'"\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)"', command)
            self.assertEqual(len(paths), 1, command)
            self.assertTrue((PLUGIN / paths[0]).is_file(), command)
        for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop"):
            self.assertIn(event, hooks)


class PluginWorkflowsTest(unittest.TestCase):
    """The plugin registers workflows/*.js as dark-factory:<meta.name>; meta must be a plain literal."""

    WF = PLUGIN / "workflows"

    def test_workflows_are_js_with_literal_meta_named_after_the_file(self):
        names = sorted(p.stem for p in self.WF.glob("*.js"))
        self.assertEqual(names, ["feature-auto", "feature-core", "feature-lite"])
        for name in names:
            text = (self.WF / f"{name}.js").read_text()
            meta = text[text.index("export const meta = {"):text.index("\n}\n")]
            self.assertIn(f"name: '{name}'", meta)
            self.assertNotIn("`", meta, f"{name}: template literal in meta")
            self.assertNotIn("<project>", text, name)
        auto = (self.WF / "feature-auto.js").read_text()
        self.assertIn("'dark-factory:feature-core'", auto)
        self.assertIn("'dark-factory:feature-lite'", auto)

    def test_no_model_ids_in_the_scripts(self):
        """Models are a setting (args.models); a call without one inherits the session's model."""
        for path in self.WF.glob("*.js"):
            self.assertNotRegex(path.read_text(), r"model:\s*['\"]", path.name)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_dry_runs(self):
        runs = {
            "feature-auto.js": '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true}',
            "feature-lite.js": '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x"}',
            "feature-core.js": '{"appDir":"/r/.claude/worktrees/fab-x","root":"/r","parentId":"proj-x"}',
        }
        for script, args in runs.items():
            proc = subprocess.run(["node", str(self.WF / "dryrun.mjs"), script, args], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('"error": null', proc.stdout, script)
        auto = subprocess.run(["node", str(self.WF / "dryrun.mjs"), "feature-auto.js", runs["feature-auto.js"]],
                              capture_output=True, text=True).stdout
        self.assertIn("workflow feature-core.js", auto)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_dry_runs_stop_on_the_cost_caps(self):
        """A spent token target and the agent cap both stop the run cleanly; the cap holds across children."""
        auto = '{"request":"x","stamp":"s1","releaseLine":"r12","bdId":"proj-x","path":"full","allowMigrations":true'
        cases = [
            ("feature-auto.js", auto + "}", {"DRYRUN_BUDGET": "3000"}, "budget exhausted"),
            ("feature-auto.js", auto + ',"maxAgents":8}', {}, "agent limit reached"),
            ("feature-auto.js", auto + ',"maxAgents":12}', {}, "agent limit reached"),
            ("feature-core.js", '{"appDir":"/r/x","root":"/r","parentId":"proj-x","maxAgents":5}', {}, "agent limit reached"),
            ("feature-lite.js", '{"request":"x","stamp":"s1","releaseLine":"r12","maxAgents":1}', {}, "agent limit reached"),
        ]
        for script, args, env, expected in cases:
            proc = subprocess.run(["node", str(self.WF / "dryrun.mjs"), script, args], capture_output=True, text=True,
                                  env={**os.environ, **env, "DRYRUN_EXPECT_ERROR": expected})
            self.assertEqual(proc.returncode, 0, script + args + proc.stdout + proc.stderr)


class BaseReliesOnPluginTest(unittest.TestCase):
    def test_base_does_not_ship_or_register_plugin_files(self):
        for rel in ("scripts/quota.py", "scripts/guard.py", ".claude/hooks/ensure-git-hooks.sh", "docs/quota-guard.md"):
            self.assertFalse((BASE / rel).exists(), rel)
        settings = (BASE / ".claude/settings.json").read_text()
        for name in ("quota.py", "guard.py", "ensure-git-hooks.sh"):
            self.assertNotIn(name, settings)
        data = json.loads(settings)
        self.assertIs(data["enabledPlugins"]["dark-factory@dark-factory"], True)
        self.assertIn("dark-factory", data["extraKnownMarketplaces"])


class DeployBaseTest(unittest.TestCase):
    """deploy-base.sh writes the starting fence level into the fences.env it copies, and only into that one."""

    def deploy(self, target, *args):
        proc = subprocess.run(["bash", str(ROOT / "scripts/deploy-base.sh"), str(target), *args],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout

    def test_fence_level_set_in_a_fresh_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "app"
            out = self.deploy(target, "--dry-run", "--fence-level", "team", "--fail-closed", "1")
            self.assertIn("would set FENCE_LEVEL=team, QUOTA_FAIL_CLOSED=1", out)
            self.assertFalse(target.exists())
            self.deploy(target, "--fence-level", "team", "--fail-closed", "1")
            text = (target / ".claude/fences.env").read_text()
            self.assertIn("\nFENCE_LEVEL=team\n", text)
            self.assertIn("\nQUOTA_FAIL_CLOSED=1\n", text)
            self.assertFalse((target / ".claude/fences.env.bak").exists())
            out = self.deploy(target, "--fence-level", "solo")
            self.assertIn("exists and is left as it is; wanted FENCE_LEVEL=solo", out)
            self.assertIn("\nFENCE_LEVEL=team\n", (target / ".claude/fences.env").read_text())

    def test_bad_options_refused(self):
        for args in (["--fence-level", "lax"], ["--fail-closed", "2"], ["--force"]):
            proc = subprocess.run(["bash", str(ROOT / "scripts/deploy-base.sh"), "/nonexistent/x", *args],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, args)


class PublishedNamesTest(unittest.TestCase):
    """The repository is published as ruslantrachuk/dark-factory; its own address is never a placeholder."""

    SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache"}

    def test_no_owner_placeholder_for_this_repository(self):
        needle = "<owner>" + "/dark-factory"
        found = []
        for path in ROOT.rglob("*"):
            if path.is_dir() or self.SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
                continue
            try:
                if needle in path.read_text(encoding="utf-8"):
                    found.append(str(path.relative_to(ROOT)))
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(found, [], f"replace {needle} with ruslantrachuk/dark-factory")

    def test_release_pin_matches_the_plugin_version(self):
        version = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        source = json.loads((BASE / ".claude/settings.json").read_text())["extraKnownMarketplaces"]["dark-factory"]["source"]
        self.assertEqual(source["repo"], "ruslantrachuk/dark-factory")
        self.assertEqual(source.get("ref"), f"v{version}", "base pins the marketplace to this release's tag")
        self.assertIn(f"## [{version}]", (ROOT / "CHANGELOG.md").read_text(), "CHANGELOG entry for the version")


class PluginSkillsTest(unittest.TestCase):
    def test_human_invoked_skills(self):
        for name in ("init", "level"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
            self.assertIn(f"\nname: {name}\n", text)
            self.assertIn("\ndisable-model-invocation: true\n", text)
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/", text)

    def test_feature_command_launches_the_pipeline_with_the_settings_file(self):
        text = (PLUGIN / "skills/feature/SKILL.md").read_text()
        self.assertIn("\nname: feature\n", text)
        self.assertIn("\ndisable-model-invocation: true\n", text)
        self.assertIn(".claude/feature-pipeline.json", text)
        self.assertIn("dark-factory:feature-auto", text)
        self.assertIn("dark-factory:feature-lite", text)


if __name__ == "__main__":
    unittest.main()

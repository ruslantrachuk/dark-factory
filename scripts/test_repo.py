#!/usr/bin/env python3
"""Repository-level checks: python3 scripts/test_repo.py (stdlib only).

The dark-factory plugin is the single source of the always-on hooks; templates/base relies on it.
These tests hold that wiring: the kit copy of merge-feature.sh matches the canon, the plugin's
hooks point at files that exist, and base neither ships nor registers what moved into the plugin.
"""
import json
import re
import shutil
import subprocess
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


if __name__ == "__main__":
    unittest.main()

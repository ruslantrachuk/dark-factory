#!/usr/bin/env python3
"""Repository-level checks: python3 scripts/test_repo.py (stdlib only).

The dark-factory plugin is the single source of the always-on hooks, and it carries everything a user installs
(commands, scripts, templates, workflows): nothing outside plugins/dark-factory/ is needed on the user's machine.
These tests hold that wiring: the plugin's hooks and commands point at files that exist inside it, and base neither
ships nor registers what moved into the plugin.
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
BASE = PLUGIN / "templates/base"
DEPLOY_BASE = PLUGIN / "scripts/deploy-base.sh"


class PluginIsSelfContainedTest(unittest.TestCase):
    """An installed plugin is only its own directory: every ${CLAUDE_PLUGIN_ROOT} path the commands use exists in it,
    and nothing it ships reaches back to the repository root."""

    def test_plugin_root_paths_in_the_skills_exist(self):
        found = 0
        for path in (PLUGIN / "skills").rglob("*.md"):
            for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)", path.read_text()):
                rel = rel.rstrip(".")
                found += 1
                self.assertTrue((PLUGIN / rel).exists(), f"{path.relative_to(ROOT)}: ${{CLAUDE_PLUGIN_ROOT}}/{rel}")
        self.assertGreater(found, 10)

    def test_no_script_reads_the_repository_root(self):
        for path in (PLUGIN / "scripts").glob("*"):
            if path.suffix not in (".py", ".sh") or path.name.startswith("test_"):
                continue
            text = path.read_text()
            self.assertNotIn("parent.parent.parent", text, path.name)

    def test_nothing_of_the_plugin_stayed_at_the_root(self):
        for rel in ("templates", "kit", ".claude/skills", "scripts/fleet.py", "scripts/deploy-base.sh",
                    "scripts/sync-plugin-kit.sh"):
            self.assertFalse((ROOT / rel).exists(), rel)
        for rel in ("templates/base", "templates/solo", "templates/feedback-desk", "templates/prod-monitor",
                    "templates/release-tag", "templates/observability", "templates/code-audit",
                    "templates/feature-pipeline", "scripts/fleet.py", "scripts/deploy-base.sh",
                    "scripts/add-module.sh", "scripts/init_kit.py"):
            self.assertTrue((PLUGIN / rel).exists(), rel)


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
            "feature-auto.js": '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true}',
            "feature-lite.js": '{"request":"x","stamp":"s1","bdId":"proj-x"}',
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
        auto = '{"request":"x","stamp":"s1","bdId":"proj-x","path":"full","allowMigrations":true'
        cases = [
            ("feature-auto.js", auto + "}", {"DRYRUN_BUDGET": "3000"}, "budget exhausted"),
            ("feature-auto.js", auto + ',"maxAgents":8}', {}, "agent limit reached"),
            ("feature-auto.js", auto + ',"maxAgents":12}', {}, "agent limit reached"),
            ("feature-core.js", '{"appDir":"/r/x","root":"/r","parentId":"proj-x","maxAgents":5}', {}, "agent limit reached"),
            ("feature-lite.js", '{"request":"x","stamp":"s1","maxAgents":1}', {}, "agent limit reached"),
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
        proc = subprocess.run(["bash", str(DEPLOY_BASE), str(target), *args],
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
            proc = subprocess.run(["bash", str(DEPLOY_BASE), "/nonexistent/x", *args],
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
        for name in ("init", "level", "add", "provision-server"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
            self.assertIn(f"\nname: {name}\n", text)
            self.assertIn("\ndisable-model-invocation: true\n", text)
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/", text)

    def test_factory_commands_are_plugin_skills_that_run_from_any_directory(self):
        for name in ("provision-server", "factory-status"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
            self.assertIn(f"\nname: {name}\n", text)
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/fleet.py", text)
            self.assertNotIn("../../../scripts", text)

    def test_add_covers_every_module_and_each_manifest_has_its_setup_section(self):
        add = (PLUGIN / "skills/add/SKILL.md").read_text()
        modules = {p.name for p in (PLUGIN / "templates").iterdir() if (p / "MANIFEST.md").is_file()}
        self.assertEqual(modules, {"base", "feedback-desk", "prod-monitor", "release-tag", "observability",
                                   "code-audit", "feature-pipeline"})
        for alias in ("base", "on-call", "monitor", "release", "observability", "code-audit", "feature-pipeline"):
            self.assertIn(f"| `{alias}` |", add)
        for module in modules:
            manifest = (PLUGIN / "templates" / module / "MANIFEST.md").read_text()
            self.assertRegex(manifest, r"\n## Setup by /dark-factory:add \S+\n", module)
        self.assertTrue((PLUGIN / "skills/add/base.md").is_file())

    def test_feature_command_launches_the_pipeline_with_the_settings_file(self):
        text = (PLUGIN / "skills/feature/SKILL.md").read_text()
        self.assertIn("\nname: feature\n", text)
        self.assertIn("\ndisable-model-invocation: true\n", text)
        self.assertIn(".claude/feature-pipeline.json", text)
        self.assertIn("dark-factory:feature-auto", text)
        self.assertIn("dark-factory:feature-lite", text)


class CanonSplitTest(unittest.TestCase):
    """The project's CLAUDE.md holds project sections only and imports the canon part, replaced whole on upgrade."""

    def test_project_file_imports_the_canon_part(self):
        project = (BASE / "CLAUDE.md").read_text()
        canon = (BASE / ".claude/canon/CLAUDE.md").read_text()
        self.assertIn("\n@.claude/canon/CLAUDE.md\n", project)
        for heading in ("## ⚡ Operating contract", "## GATE", "## SESSION LOOP"):
            self.assertIn(heading, canon)
            self.assertNotIn(heading, project)
        for heading in ("## Overview", "## Project settings", "## Project principles", "## Project constraints"):
            self.assertIn(heading, project)

    def test_canon_part_has_no_project_placeholders(self):
        canon = (BASE / ".claude/canon/CLAUDE.md").read_text()
        self.assertEqual(re.findall(r"<(?:project|main|owner|language)[^>]*>", canon), [])

    def test_harness_diff_skips_the_project_file_but_not_the_canon_part(self):
        script = (BASE / "scripts/harness-diff.sh").read_text()
        exclude = script[script.index("EXCLUDE=("):script.index("\n)\n", script.index("EXCLUDE=("))]
        entries = re.findall(r"^\s*'([^']+)'", exclude, re.M)
        self.assertIn("CLAUDE.md", entries)
        self.assertNotIn(".claude/canon/CLAUDE.md", entries)

    def test_deploy_replaces_the_canon_part_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / ".claude/canon").mkdir(parents=True)
            (target / ".claude/canon/CLAUDE.md").write_text("stale\n")
            proc = subprocess.run(["bash", str(DEPLOY_BASE), str(target), "--fence-level", "solo"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual((target / ".claude/canon/CLAUDE.md").read_bytes(),
                             (BASE / ".claude/canon/CLAUDE.md").read_bytes())


class ChangeKeyTest(unittest.TestCase):
    """Branch = change key (<type>/<ID>-<slug>); no release train anywhere."""

    TRAIN = re.compile(r"releaseLine|CURRENT_TRAIN|INTEGRATION_BRANCH|fetch-openspec-docs|r\{N\}|rN-|--accepted-by|Accepted-by")

    def test_no_train_or_acceptance_flag_is_left(self):
        found = []
        for path in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split():
            if path in ("CHANGELOG.md", "scripts/test_repo.py", "plugins/dark-factory/templates/base/app/tests/integration/test_merge_feature.py") or not (ROOT / path).is_file():
                continue
            try:
                text = (ROOT / path).read_text()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if self.TRAIN.search(line) and "accepted-by is no longer" not in line:
                    found.append(f"{path}:{n}")
        self.assertEqual(found, [])

    def test_tracker_pattern_is_one_seam_in_the_script_and_the_skill(self):
        pattern = "[A-Z][A-Z0-9]+-[0-9]+"
        script = (BASE / "scripts/merge-feature.sh").read_text()
        skill = (BASE / ".claude/skills/size-task/SKILL.md").read_text()
        self.assertIn(f"TRACKER_ID_RE='{pattern}'", script)
        self.assertIn(pattern, skill)
        self.assertIn("To swap the tracker, change this pattern", script)
        self.assertIn("To swap the tracker, change this pattern", skill)

    def test_session_header_points_at_size_task(self):
        self.assertIn("size-task", (BASE / ".claude/hooks/session-context.sh").read_text())

    def test_nothing_vendored_from_openspec_remains(self):
        self.assertFalse((BASE / ".claude/skills/openspec/schemas").exists())
        self.assertFalse((BASE / "scripts/fetch-openspec-docs.sh").exists())
        self.assertFalse((BASE / "openspec/CURRENT_TRAIN").exists())


if __name__ == "__main__":
    unittest.main()

"""codex_project.py against a fake `codex app-server`: python3 tests/test_codex_project.py

The fake speaks the same newline-delimited JSON-RPC as Codex 0.169 for the three methods the script uses
(config/read, config/batchWrite, hooks/list) and keeps its state in a JSON file: the trusted projects, the hooks with
their hashes, and the approvals written by batchWrite.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins/dark-factory/scripts/codex_project.py"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FAKE_CODEX_STATE"]
if sys.argv[1:] != ["app-server"]:
    sys.exit(2)

def load():
    return json.load(open(state_path))

def save(s):
    json.dump(s, open(state_path, "w"))

def status(s, h):
    approved = s.get("approved", {}).get(h["key"])
    if approved is None:
        return "untrusted"
    return "trusted" if approved == h["hash"] else "modified"

for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    s, method, params = load(), msg["method"], msg.get("params", {})
    if method == "initialize":
        result = {}
    elif method == "config/read":
        result = {"config": {"projects": {p: {"trust_level": "trusted"} for p in s.get("trusted", [])},
                             "plugins": s.get("plugins", {}),
                             **({"default_permissions": s["profile"]} if s.get("profile") and
                                params.get("cwd") in s.get("trusted", []) else {})}}
    elif method == "hooks/list":
        trusted = params["cwds"][0] in s.get("trusted", [])
        hooks = [h for h in s["hooks"] if trusted or not h.get("project")]
        result = {"data": [{"cwd": params["cwds"][0], "warnings": [],
                            "hooks": [{"key": h["key"], "eventName": h["event"], "currentHash": h["hash"],
                                       "trustStatus": status(s, h)} for h in hooks]}]}
    elif method == "config/batchWrite":
        for edit in params["edits"]:
            if edit["keyPath"] == "projects":
                s.setdefault("trusted", []).extend(p for p, v in edit["value"].items() if v["trust_level"] == "trusted")
            elif edit["keyPath"] == "hooks.state":
                s.setdefault("approved", {}).update({k: v["trusted_hash"] for k, v in edit["value"].items()})
            else:
                s.setdefault("written", {})[edit["keyPath"]] = [edit["value"], edit["mergeStrategy"]]
        save(s)
        result = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"message": "unknown " + method}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


class CodexProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.bin, self.home, self.project = t / "bin", t / "codex-home", t / "proj"
        self.bin.mkdir()
        (self.bin / "codex").write_text(FAKE)
        (self.bin / "codex").chmod(0o755)
        (self.home / "plugins/cache/dark-factory/dark-factory/23.0.0").mkdir(parents=True)
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, env=self.git_env())
        (self.project / ".codex").mkdir()
        (self.project / ".codex/hooks.json").write_text("{}")
        self.root = str(self.project.resolve())
        self.state = t / "state.json"
        self.write_state({
            "plugins": {"dark-factory@dark-factory": {"enabled": True}},
            "profile": "dark-factory",
            "hooks": [{"key": f"{self.root}/.codex/hooks.json:session_start:0:0", "event": "sessionStart",
                       "hash": "p1", "project": True},
                      {"key": "dark-factory@dark-factory:hooks/hooks.json:pre_tool_use:0:0", "event": "preToolUse",
                       "hash": "g1"}],
        })

    def tearDown(self):
        self.tmp.cleanup()

    def git_env(self):
        return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def write_state(self, s):
        self.state.write_text(json.dumps(s))

    def read_state(self):
        return json.loads(self.state.read_text())

    def run_script(self, *args, cwd=None):
        env = {**self.git_env(), "PATH": f"{self.bin}:{os.environ['PATH']}", "CODEX_HOME": str(self.home),
               "FAKE_CODEX_STATE": str(self.state)}
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--project", str(cwd or self.project)],
                              capture_output=True, text=True, env=env, timeout=30)

    def test_check_before_setup_names_every_missing_piece(self):
        proc = self.run_script("check")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("✗ trusted", proc.stdout)
        self.assertIn("✗ permission profile", proc.stdout)
        self.assertIn("untrusted", proc.stdout)
        self.assertIn("skipped silently until approved", proc.stdout)

    def test_setup_trusts_the_project_and_approves_the_project_and_plugin_hooks(self):
        proc = self.run_script("setup")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = self.read_state()
        self.assertEqual(state["trusted"], [self.root])
        # the project's hook is listed only once the project is trusted, and setup approves it in the same run
        self.assertEqual(state["approved"], {f"{self.root}/.codex/hooks.json:session_start:0:0": "p1",
                                             "dark-factory@dark-factory:hooks/hooks.json:pre_tool_use:0:0": "g1"})
        self.assertIn("approved 2 hook(s)", proc.stdout)
        self.assertEqual(self.run_script("check").returncode, 0)

    def test_a_changed_hook_shows_modified_until_setup_runs_again(self):
        self.run_script("setup")
        state = self.read_state()
        state["hooks"][0]["hash"] = "p2"
        self.write_state(state)
        proc = self.run_script("check", "--json")
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual([h["status"] for h in report["hooks"]], ["modified", "trusted"])
        self.assertEqual(self.run_script("setup").returncode, 0)
        self.assertEqual(self.read_state()["approved"][f"{self.root}/.codex/hooks.json:session_start:0:0"], "p2")

    def test_a_worktree_is_set_up_on_the_main_checkout(self):
        env = self.git_env()
        for args in (["commit", "-q", "--allow-empty", "-m", "x"], ["worktree", "add", "-q", "wt"]):
            subprocess.run(["git", "-C", str(self.project), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                           check=True, env=env)
        proc = self.run_script("setup", cwd=self.project / "wt")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["trusted"], [self.root])

    def test_plugin_missing_or_disabled_fails_the_check(self):
        self.run_script("setup")
        state = self.read_state()
        state["plugins"] = {"dark-factory@dark-factory": {"enabled": False}}
        self.write_state(state)
        self.assertIn("plugin dark-factory@dark-factory: disabled", self.run_script("check").stdout)
        for p in sorted((self.home / "plugins/cache").rglob("*"), reverse=True):
            p.rmdir()
        out = self.run_script("check")
        self.assertEqual(out.returncode, 1)
        self.assertIn("plugin dark-factory@dark-factory: missing", out.stdout)

    def test_without_the_module_the_check_says_how_to_add_it(self):
        (self.project / ".codex/hooks.json").unlink()
        out = self.run_script("check").stdout
        self.assertIn("✗ module agent-codex", out)
        self.assertIn("/dark-factory:add agent-codex", out)

    def test_domains_go_to_the_user_config_and_replace_the_list(self):
        env = {**self.git_env(), "PATH": f"{self.bin}:{os.environ['PATH']}", "CODEX_HOME": str(self.home),
               "FAKE_CODEX_STATE": str(self.state)}
        proc = subprocess.run([sys.executable, str(SCRIPT), "domains", "github.com, pypi.org"], capture_output=True,
                              text=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        written = self.read_state()["written"]
        self.assertEqual(written["features.network_proxy"], [True, "replace"])
        self.assertEqual(written["permissions.dark-factory.network.domains"],
                         [{"github.com": "allow", "pypi.org": "allow"}, "replace"])
        empty = subprocess.run([sys.executable, str(SCRIPT), "domains", " , "], capture_output=True, text=True,
                               env=env, timeout=30)
        self.assertEqual(empty.returncode, 2)

    def test_not_a_repository_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            proc = self.run_script("check", cwd=Path(d))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not in a git repository", proc.stderr)


if __name__ == "__main__":
    unittest.main()

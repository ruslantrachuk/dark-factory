#!/usr/bin/env python3
"""Codex in a dark-factory project: trust it, approve its hooks, check that the canon is in force.

Codex reads a project's layer (.codex/config.toml, .codex/hooks.json) only when the project is trusted, and runs a
hook — the project's or a plugin's — only after it was approved by its hash. A hook that was never approved, or was
changed since, is skipped without a word: the session header, the guard and the quota guard would be gone and nothing
would say so. This script does what the Codex TUI does when the owner approves them, through `codex app-server`
(stdio JSON-RPC, the same protocol the TUI uses), and checks the result.

  codex_project.py setup [--project DIR] [--json]   trust the project, approve its and the plugin's hooks
  codex_project.py check [--project DIR] [--json]   report; exit 0 when everything is in force, 1 otherwise
  codex_project.py domains <domain,domain,…>        the network allowlist of the permission profile, in the user's
                                                    config (a project layer cannot narrow the network by domain)

The project is the main checkout of the git repository at DIR (default: the current directory): a git worktree
inherits the main checkout's trust and approvals. Writes go to the user's config.toml of $CODEX_HOME (~/.codex).

Seam: agent = Codex CLI ≥ 0.169 (app-server methods config/read, config/batchWrite, hooks/list). Another agent has
its own canon; this script is the agent-codex module's install step, not a general one.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = "dark-factory@dark-factory"
PROFILE = "dark-factory"  # the permission profile the module's .codex/config.toml defines
APPROVE = ("untrusted", "modified")  # hooks/list trustStatus values that need the owner's approval
TIMEOUT = 60


class CodexError(Exception):
    pass


class AppServer:
    """One `codex app-server` over stdio: newline-delimited JSON-RPC."""

    def __init__(self, codex: str) -> None:
        self.proc = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.next_id = 0
        self.call("initialize", {"clientInfo": {"name": "dark-factory-codex-project", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "initialized"})

    def send(self, msg: dict) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def call(self, method: str, params: dict) -> dict:
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        assert self.proc.stdout
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == self.next_id:
                if "error" in msg:
                    raise CodexError(f"{method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result") or {}
        raise CodexError(f"{method}: codex app-server closed")

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()

    def __enter__(self) -> "AppServer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def main_checkout(directory: Path) -> Path:
    """The main checkout of the repository at directory: trust and approvals live on its path."""
    r = subprocess.run(["git", "-C", str(directory), "worktree", "list", "--porcelain"], capture_output=True, text=True)
    if r.returncode != 0:
        raise CodexError(f"{directory} is not in a git repository")
    first = r.stdout.splitlines()[0] if r.stdout else ""
    if not first.startswith("worktree "):
        raise CodexError(f"cannot read the worktrees of {directory}")
    return Path(first[len("worktree "):]).resolve()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def hooks(server: AppServer, root: Path) -> tuple[list[dict], list[str]]:
    listed = server.call("hooks/list", {"cwds": [str(root)]})
    found, warnings = [], []
    for entry in listed.get("data", []):
        warnings += [str(w) for w in entry.get("warnings", [])]
        found += entry.get("hooks", [])
    return found, warnings


def trust_level(config: dict, root: Path) -> str:
    projects = config.get("projects") or {}
    for path, conf in projects.items():
        if Path(path).resolve() == root and isinstance(conf, dict):
            return str(conf.get("trust_level") or "")
    return ""


def plugin_state(config: dict) -> str:
    """installed (cache present and enabled) | disabled | missing — Codex's own install records."""
    entry = (config.get("plugins") or {}).get(PLUGIN_ID)
    cache = codex_home() / "plugins/cache" / PLUGIN_ID.split("@")[1] / PLUGIN_ID.split("@")[0]
    if not cache.is_dir() or not any(cache.iterdir()):
        return "missing"
    if not isinstance(entry, dict) or entry.get("enabled") is not True:
        return "disabled"
    return "installed"


def read_config(server: AppServer, root: Path) -> dict:
    return server.call("config/read", {"cwd": str(root)}).get("config") or {}


def report(server: AppServer, root: Path) -> dict:
    config = read_config(server, root)
    found, warnings = hooks(server, root)
    module = (root / ".codex/hooks.json").is_file()
    return {
        "project": str(root),
        "trusted": trust_level(config, root) == "trusted",
        "plugin": plugin_state(config),
        "profile": config.get("default_permissions") == PROFILE,
        "module": module,
        "hooks": [{"key": h.get("key"), "event": h.get("eventName"), "status": h.get("trustStatus")} for h in found],
        "warnings": warnings,
    }


def healthy(r: dict) -> bool:
    return (r["trusted"] and r["plugin"] == "installed" and r["profile"] and r["module"] and bool(r["hooks"])
            and all(h["status"] not in APPROVE for h in r["hooks"]))


def trust(server: AppServer, root: Path) -> None:
    # The same record `codex exec --trust` and the TUI's trust prompt write: projects."<root>".trust_level.
    server.call("config/batchWrite", {"edits": [{"keyPath": "projects", "value": {str(root): {"trust_level": "trusted"}},
                                                 "mergeStrategy": "upsert"}], "reloadUserConfig": True})


def approve(server: AppServer, root: Path) -> list[str]:
    # As the TUI does (codex-rs/tui/src/hooks_rpc.rs): hooks.state.<key>.trusted_hash = the hook's current hash.
    found, _ = hooks(server, root)
    pending = {h["key"]: {"trusted_hash": h["currentHash"]} for h in found
               if h.get("trustStatus") in APPROVE and h.get("key") and h.get("currentHash")}
    if pending:
        server.call("config/batchWrite", {"edits": [{"keyPath": "hooks.state", "value": pending, "mergeStrategy": "upsert"}],
                                          "reloadUserConfig": True})
    return sorted(pending)


def set_domains(server: AppServer, domains: list[str]) -> None:
    """The profile's allowlist in the user's config.toml: Codex reads [permissions.<name>.network.domains] and the
    network proxy only from there. The whole list is replaced: a domain dropped from the setting is closed again."""
    server.call("config/batchWrite", {"edits": [
        {"keyPath": "features.network_proxy", "value": True, "mergeStrategy": "replace"},
        {"keyPath": f"permissions.{PROFILE}.network.domains", "value": {d: "allow" for d in domains},
         "mergeStrategy": "replace"},
    ], "reloadUserConfig": True})


def print_report(r: dict, approved: list[str] | None = None) -> None:
    def mark(ok: bool) -> str:
        return "✓" if ok else "✗"

    print(f"Codex project: {r['project']}")
    print(f"  {mark(r['trusted'])} trusted" + ("" if r["trusted"] else " — codex_project.py setup"))
    print(f"  {mark(r['module'])} module agent-codex (.codex/hooks.json)" +
          ("" if r["module"] else " — /dark-factory:add agent-codex"))
    print(f"  {mark(r['profile'])} permission profile {PROFILE}" +
          ("" if r["profile"] else " — not in force (the project is not trusted, or .codex/config.toml lost it)"))
    plugin_fix = {"missing": f" — the owner: codex plugin marketplace add <canon> && codex plugin add {PLUGIN_ID}",
                  "disabled": f" — enable it: [plugins.\"{PLUGIN_ID}\"] enabled = true"}
    print(f"  {mark(r['plugin'] == 'installed')} plugin {PLUGIN_ID}: {r['plugin']}{plugin_fix.get(r['plugin'], '')}")
    if not r["hooks"]:
        print("  ✗ hooks: none found — Codex does not see the project's or the plugin's hooks")
    for h in r["hooks"]:
        bad = h["status"] in APPROVE
        hint = " — skipped silently until approved: codex_project.py setup" if bad else ""
        print(f"  {mark(not bad)} hook {h['event']}: {h['status']} ({h['key']}){hint}")
    for w in r["warnings"]:
        print(f"  ! {w}")
    if approved:
        print(f"approved {len(approved)} hook(s)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("setup", "check", "domains"))
    ap.add_argument("domains", nargs="?", default="")
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    codex = shutil.which("codex")
    if not codex:
        print("✗ codex not found on PATH", file=sys.stderr)
        return 2
    if a.command == "domains":
        domains = [d.strip() for d in a.domains.split(",") if d.strip()]
        if not domains:
            print("✗ domains: give a comma-separated list", file=sys.stderr)
            return 2
        try:
            with AppServer(codex) as server:
                set_domains(server, domains)
        except CodexError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        print(f"Codex network allowlist ({PROFILE}): {', '.join(domains)}")
        return 0
    try:
        root = main_checkout(Path(a.project).resolve())
        with AppServer(codex) as server:
            approved: list[str] | None = None
            if a.command == "setup":
                trust(server, root)
                approved = approve(server, root)
            r = report(server, root)
    except CodexError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({**r, "ok": healthy(r), **({"approved": approved} if approved is not None else {})},
                         ensure_ascii=False, indent=1))
    else:
        print_report(r, approved)
    return 0 if healthy(r) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

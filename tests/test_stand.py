#!/usr/bin/env python3
"""Tests for stand.py (a project's stands): python3 tests/test_stand.py

Real processes on 127.0.0.1: a fake project whose scripts/stand.sh serves a directory with python's http.server."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "scripts"
sys.path.insert(0, str(SCRIPTS))

TEMP_PORTS = (18310, 18312)
PREVIEW_PORT = 18320

STAND_SH = """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  build) mkdir -p "$STAND_DIR"; echo "$STAND_KIND $(git -C "$STAND_CHECKOUT" rev-parse --abbrev-ref HEAD)" > "$STAND_DIR/index.html" ;;
  run) exec python3 -m http.server "$STAND_PORT" --bind 127.0.0.1 --directory "$STAND_DIR" ;;
  prepare) echo "$STAND_CHECKOUT" >> "$STAND_STATE_LOG" ;;
  smoke) python3 -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1], timeout=2)" "http://127.0.0.1:$STAND_PORT/" ;;
  db) if [ "$STAND_KIND" = preview ]; then echo "${PREVIEW_DB:-shop_preview}"; else echo shop; fi ;;
esac
"""


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def body(port: int) -> str:
    return urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode().strip()


class StandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"
        self.env = {**os.environ, "DF_STAND_STATE": str(self.state),
                    "STAND_TEMP_PORTS": f"{TEMP_PORTS[0]}-{TEMP_PORTS[1]}", "STAND_WAIT": "15",
                    "STAND_STATE_LOG": str(self.tmp / "prepared.log"),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t"}
        self.project = self.tmp / "shop"
        self.git(self.tmp, "init", "-q", "-b", "main", str(self.project))
        sh = self.project / "scripts/stand.sh"
        sh.parent.mkdir()
        sh.write_text(STAND_SH)
        sh.chmod(0o755)
        self.git(self.project, "add", "-A")
        self.git(self.project, "commit", "-q", "-m", "one")
        self.strangers = []

    def tearDown(self):
        self.stand("stop", "temp", "--from", str(self.project))
        for wt in self.project.parent.glob("wt-*"):
            self.stand("stop", "temp", "--from", str(wt))
        self.stand("stop", "preview", "--from", str(self.project))
        for s in self.strangers:
            s.shutdown()
            s.server_close()
        self._tmp.cleanup()

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=getattr(self, "env", os.environ), check=True,
                              capture_output=True, text=True).stdout

    def stand(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPTS / "stand.py"), *args], cwd=self.project,
                              env={**self.env, **(env or {})}, capture_output=True, text=True, timeout=60)

    def worktree(self, name):
        wt = self.tmp / f"wt-{name}"
        self.git(self.project, "worktree", "add", "-q", "-b", name, str(wt))
        return wt

    def stranger(self, port):
        from http.server import HTTPServer, BaseHTTPRequestHandler
        s = HTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.strangers.append(s)

    def port_of(self, out):
        return int(out.split("http://127.0.0.1:")[1].split()[0])

    def declare_preview(self):
        f = self.project / ".claude/factory/stands.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps([{"name": "main", "port": 18300}, {"name": "preview", "port": PREVIEW_PORT}]))

    # ---------- temp ----------

    def test_no_script_gives_a_hint(self):
        (self.project / "scripts/stand.sh").unlink()
        r = self.stand("start", "temp")
        self.assertEqual(r.returncode, 1)
        self.assertIn("scripts/stand.sh", r.stderr)

    def test_parallel_temp_stands_get_their_own_ports_and_stop_alone(self):
        a, b = self.worktree("ui-a"), self.worktree("ui-b")
        procs = [subprocess.Popen([sys.executable, str(SCRIPTS / "stand.py"), "start", "temp", "--from", str(w)],
                                  env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for w in (a, b)]
        outs = [p.communicate(timeout=60) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0], outs)
        pa, pb = (self.port_of(o[0]) for o in outs)
        self.assertNotEqual(pa, pb)
        self.assertEqual((body(pa), body(pb)), ("temp ui-a", "temp ui-b"))
        self.assertEqual(self.stand("stop", "temp", "--from", str(a)).returncode, 0)
        self.assertTrue(free(pa))
        self.assertEqual(body(pb), "temp ui-b")

    def test_a_port_held_outside_the_tool_is_skipped(self):
        self.stranger(TEMP_PORTS[0])
        r = self.stand("start", "temp")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.port_of(r.stdout), TEMP_PORTS[0] + 1)

    def test_no_free_port_has_its_own_code(self):
        self.stranger(TEMP_PORTS[0])
        r = self.stand("start", "temp", env={"STAND_TEMP_PORTS": str(TEMP_PORTS[0])})
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("stand.py ls", r.stderr)

    def test_start_again_restarts_its_own_stand(self):
        first = self.port_of(self.stand("start", "temp").stdout)
        second = self.port_of(self.stand("start", "temp").stdout)
        self.assertEqual(first, second)
        self.assertEqual(len(list((self.state / "temp").glob("*.json"))), 1)

    def test_a_stand_whose_worktree_is_gone_is_removed(self):
        wt = self.worktree("gone")
        port = self.port_of(self.stand("start", "temp", "--from", str(wt)).stdout)
        shutil.rmtree(wt)
        self.assertNotIn("gone", self.stand("ls").stdout)
        self.assertTrue(free(port))
        self.assertEqual(list((self.state / "temp").glob("*.json")), [])

    def test_a_reused_pid_is_not_the_stand(self):
        import stand
        rec = {"pid": os.getpid(), "start": stand.proc_start(os.getpid())}
        self.assertTrue(stand.alive(rec))
        self.assertFalse(stand.alive({**rec, "start": "0"}))

    def test_main_is_the_servers(self):
        r = self.stand("restart", "main")
        self.assertEqual(r.returncode, 4)
        self.assertIn("df-<slug>-stand", r.stderr)

    # ---------- preview ----------

    def test_preview_needs_its_declaration(self):
        r = self.stand("start", "preview", "--from", str(self.project))
        self.assertEqual(r.returncode, 1)
        self.assertIn("stands.json", r.stderr)

    def test_preview_serves_a_branch_and_switches_only_with_take(self):
        self.declare_preview()
        a, b = self.worktree("feat-a"), self.worktree("feat-b")
        r = self.stand("start", "preview", "--from", str(a))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(body(PREVIEW_PORT), "preview feat-a")
        r = self.stand("start", "preview", "--from", str(b))
        self.assertEqual(r.returncode, 4)
        self.assertIn("feat-a", r.stderr)
        self.assertEqual(body(PREVIEW_PORT), "preview feat-a")
        r = self.stand("start", "preview", "--from", str(b), "--take")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(body(PREVIEW_PORT), "preview feat-b")
        self.assertEqual((self.tmp / "prepared.log").read_text().split(), [str(a), str(b)])
        self.assertIn("feat-b", self.stand("ls").stdout)

    def test_preview_refuses_the_main_stands_database(self):
        self.declare_preview()
        r = self.stand("start", "preview", "--from", str(self.project), env={"PREVIEW_DB": "shop"})
        self.assertEqual(r.returncode, 4)
        self.assertTrue(free(PREVIEW_PORT))

    def test_feed_shows_the_branch_the_preview_serves(self):
        self.declare_preview()
        wt = self.worktree("feat-c")
        self.assertEqual(self.stand("start", "preview", "--from", str(wt)).returncode, 0)
        os.environ["DF_STAND_STATE"] = str(self.state)
        try:
            import importlib
            import stand
            importlib.reload(stand)
            import fleet
            import fleet_feed
            p = fleet.Project("shop", self.project, "shop")
            self.assertEqual(fleet_feed.served(p, {"name": "preview", "port": PREVIEW_PORT})["checkout"], str(wt))
            self.assertNotIn("checkout", fleet_feed.served(p, {"name": "main", "port": 18300}))
        finally:
            del os.environ["DF_STAND_STATE"]


if __name__ == "__main__":
    unittest.main()

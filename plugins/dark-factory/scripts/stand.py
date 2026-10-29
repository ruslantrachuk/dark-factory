#!/usr/bin/env python3
"""A project's stands, with the same commands everywhere; the project extends it with scripts/stand.sh.

  stand.py start temp [--from <worktree>]            an agent's own frontend stand of the worktree on a free port of
                                                     the server's range; prints its URL
  stand.py start preview --from <worktree> [--take]  the project's preview serves that worktree's branch, on its own
                                                     database; --take switches a preview that serves another branch
  stand.py stop|restart|logs temp|preview [--from <worktree>]
  stand.py ls                                        every stand of this server: port, branch, link, log
  stand.py start|stop|restart main                   refused: the main stand is the server's (df-<slug>-stand)

The tool does the mechanics: an atomic port claim, a detached start in its own session, a record of the process,
stop by that record only (never a pattern), logs, the wait until it listens, removal of temp stands whose worktree is
gone or that are older than STAND_TEMP_HOURS. Its state is one place per user, outside every worktree:
~/.local/state/dark-factory/stands/. Exit codes: 0 done; 3 no free port; 4 refused (another branch on the preview,
the main stand's database, a main-stand command); 1 anything else.

scripts/stand.sh <step> (the project's, from the worktree being served) holds the stack. Steps, all with
STAND_KIND (temp|preview|main), STAND_CHECKOUT, STAND_PORT, STAND_DIR (a build directory of the tool's), STAND_URL:
  build    build into STAND_DIR (temp, preview)
  run      serve on 127.0.0.1:STAND_PORT in the foreground; the tool detaches it (temp, preview)
  prepare  dependencies; for the preview its own database, recreated and migrated from zero (preview)
  smoke    exit non-zero when the served stand is wrong (preview)
  db       print the database name, without credentials, for STAND_KIND (preview, main) — the preview refuses to
           start on the main stand's
A temp stand is frontend-only, its API proxied to the main stand, and writes nothing there.
"""
import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(os.environ.get("DF_STAND_STATE", Path.home() / ".local/state/dark-factory/stands"))  # tests move it
STANDS_FILE = ".claude/factory/stands.json"
SCRIPT = "scripts/stand.sh"


def temp_ports() -> list[int]:
    lo, _, hi = os.environ.get("STAND_TEMP_PORTS", "8210-8219").partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


TEMP_HOURS = float(os.environ.get("STAND_TEMP_HOURS", "24"))
WAIT = float(os.environ.get("STAND_WAIT", "60"))
NO_PORT, REFUSED = 3, 4


class Stop(Exception):
    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if r.returncode:
        raise Stop(f"{cwd}: not a git checkout — {r.stderr.strip()}")
    return r.stdout.strip()


def worktree(path: str | None) -> Path:
    return Path(git(Path(path or "."), "rev-parse", "--show-toplevel"))


def main_checkout(wt: Path) -> Path:
    return Path(git(wt, "worktree", "list", "--porcelain").splitlines()[0].removeprefix("worktree "))


def branch(wt: Path) -> str:
    try:
        return git(wt, "symbolic-ref", "--short", "-q", "HEAD")
    except Stop:
        return git(wt, "rev-parse", "--short", "HEAD")


def key(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:12]


def decl(project: Path, name: str) -> dict:
    try:
        stands = json.loads((project / STANDS_FILE).read_text())
    except (OSError, ValueError):
        stands = []
    return next((d for d in stands if isinstance(d, dict) and d.get("name") == name), {})


# ---------- records: <kind>/<id>.json → {pid, start, port, worktree, project, log, dir, at} ----------

def record_path(kind: str, ident: str) -> Path:
    return STATE / kind / f"{ident}.json"


def read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def proc_start(pid: int) -> str | None:
    """The process's start time (/proc/<pid>/stat field 22): with the pid it names one process, not a reused pid."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def alive(rec: dict) -> bool:
    return bool(rec.get("pid")) and proc_start(rec["pid"]) == rec.get("start")


def kill(rec: dict) -> None:
    """Stop the recorded process and everything it started: it leads its own session, so its group is its own."""
    if not alive(rec):
        return
    try:
        os.killpg(rec["pid"], signal.SIGTERM)
    except OSError:
        return
    for _ in range(40):
        if not alive(rec):
            return
        time.sleep(0.25)
    try:
        os.killpg(rec["pid"], signal.SIGKILL)
    except OSError:
        pass


def drop(path: Path, rec: dict | None) -> None:
    if rec:
        kill(rec)
        if rec.get("dir"):
            shutil.rmtree(rec["dir"], ignore_errors=True)
        if rec.get("log"):
            Path(rec["log"]).unlink(missing_ok=True)
    path.unlink(missing_ok=True)


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def sweep_temp() -> None:
    """Temp stands whose worktree is gone, whose process died, or that are older than STAND_TEMP_HOURS go."""
    for path in sorted((STATE / "temp").glob("*.json")):
        rec = read(path)  # None also for a claim another start has created and not yet written
        if rec is None or rec.get("pid") is None:
            try:
                stale = time.time() - path.stat().st_mtime > WAIT * 4  # a claim whose start never finished
            except OSError:
                continue
            if stale:
                drop(path, rec)
            continue
        if not Path(rec["worktree"]).is_dir() or not alive(rec) or time.time() - rec["at"] > TEMP_HOURS * 3600:
            drop(path, rec)


# ---------- the project's script ----------

def script(wt: Path) -> Path:
    s = wt / SCRIPT
    if not os.access(s, os.X_OK):
        raise Stop(f"no {SCRIPT} in {wt}: write it from the skeleton in the dev-stand skill "
                   "(steps build, run; for the preview also prepare, smoke, db)")
    return s


def env(kind: str, wt: Path, port: int, dirpath: Path, url: str) -> dict:
    return {**os.environ, "STAND_KIND": kind, "STAND_CHECKOUT": str(wt), "STAND_PORT": str(port),
            "STAND_DIR": str(dirpath), "STAND_URL": url}


def step(wt: Path, name: str, e: dict, log: Path | None = None) -> str:
    r = subprocess.run([str(script(wt)), name], cwd=wt, env=e, capture_output=True, text=True)
    if log:
        with log.open("a") as f:
            f.write(f"--- {name}\n{r.stdout}{r.stderr}")
    if r.returncode:
        tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
        raise Stop(f"{SCRIPT} {name} failed ({r.returncode}):\n" + "\n".join(tail))
    return r.stdout.strip()


def launch(path: Path, rec: dict, wt: Path, e: dict) -> dict:
    """run, detached in its own session, the record written with its pid; wait until the port listens."""
    log = Path(rec["log"])
    with log.open("a") as f:
        f.write("--- run\n")
        f.flush()
        p = subprocess.Popen([str(script(wt)), "run"], cwd=wt, env=e, stdin=subprocess.DEVNULL, stdout=f,
                             stderr=subprocess.STDOUT, start_new_session=True)
    rec = {**rec, "pid": p.pid, "start": proc_start(p.pid)}
    path.write_text(json.dumps(rec))
    deadline = time.time() + WAIT
    while time.time() < deadline:
        if listening(rec["port"]):
            return rec
        if p.poll() is not None:
            break
        time.sleep(0.25)
    tail = "\n".join(log.read_text(errors="replace").splitlines()[-5:])
    raise Stop(f"the stand did not listen on :{rec['port']} (log {log}):\n{tail}")


# ---------- temp ----------

def start_temp(wt: Path) -> int:
    script(wt)
    sweep_temp()
    stop_temp(wt, quiet=True)
    (STATE / "temp").mkdir(parents=True, exist_ok=True)
    dirpath = STATE / "build" / f"temp-{key(wt)}"
    for port in temp_ports():
        path = record_path("temp", str(port))
        try:  # the claim: whoever creates the record owns the port
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        rec = {"pid": None, "port": port, "worktree": str(wt), "project": str(main_checkout(wt)), "branch": branch(wt),
               "log": str(STATE / "temp" / f"{port}.log"), "dir": str(dirpath), "at": time.time()}
        os.write(fd, json.dumps(rec).encode())
        os.close(fd)
        if listening(port):  # someone outside the tool holds it
            path.unlink()
            continue
        url = f"http://127.0.0.1:{port}"
        e = env("temp", wt, port, dirpath, url)
        try:
            Path(rec["log"]).write_text("")
            step(wt, "build", e, Path(rec["log"]))
            launch(path, rec, wt, e)
        except Stop:
            drop(path, read(path))
            raise
        print(f"{url}  ({wt}, {branch(wt)})")
        return 0
    raise Stop(f"every temp port {temp_ports()[0]}-{temp_ports()[-1]} is taken: stand.py ls", NO_PORT)


def stop_temp(wt: Path, quiet: bool = False) -> int:
    found = False
    for path in (STATE / "temp").glob("*.json"):
        rec = read(path)
        if rec and rec.get("worktree") == str(wt):
            drop(path, rec)
            found = True
            if not quiet:
                print(f"temp stand of {wt} on :{rec['port']} stopped")
    if not found and not quiet:
        print(f"no temp stand of {wt}")
    return 0


# ---------- preview ----------

def preview_record(project: Path) -> tuple[Path, dict | None]:
    path = record_path("preview", key(project))
    return path, read(path)


def preview_url(d: dict) -> str:
    import fleet_feed
    return fleet_feed.stand_url(d) or f"http://127.0.0.1:{d['port']}"


def start_preview(wt: Path, take: bool) -> int:
    project = main_checkout(wt)
    d = decl(project, "preview")
    if not isinstance(d.get("port"), int):
        raise Stop(f"no preview in {project / STANDS_FILE}: add "
                   '{"name": "preview", "port": <port>, "health": "<route>", "tunnel" or "url": …}')
    path, rec = preview_record(project)
    if rec and alive(rec) and rec["worktree"] != str(wt) and not take:
        raise Stop(f"the preview serves {rec['branch']} ({rec['worktree']}); someone may be looking at it — "
                   "--take switches it", REFUSED)
    port, dirpath = d["port"], STATE / "build" / f"preview-{key(project)}"
    url = preview_url(d)
    e = env("preview", wt, port, dirpath, url)
    mine = step(wt, "db", e)
    theirs = step(wt, "db", env("main", project, decl(project, "main").get("port", 0), dirpath, url))
    if not mine or mine == theirs:
        raise Stop(f"the preview's database {mine or '(none printed)'} is not its own: "
                   f"{SCRIPT} db must print a database other than the main stand's", REFUSED)
    if rec:
        drop(path, rec)
    if listening(port):
        raise Stop(f"port {port} of the preview is taken by a process the tool did not start: ss -ltnp")
    path.parent.mkdir(parents=True, exist_ok=True)
    log = STATE / "preview" / f"{key(project)}.log"
    log.write_text("")
    rec = {"pid": None, "port": port, "worktree": str(wt), "project": str(project), "branch": branch(wt),
           "log": str(log), "dir": str(dirpath), "at": time.time(), "url": url}
    path.write_text(json.dumps(rec))
    try:
        for name in ("prepare", "build"):
            step(wt, name, e, log)
        rec = launch(path, rec, wt, e)
        step(wt, "smoke", e, log)
    except Stop:
        kill(read(path) or rec)
        raise
    print(f"{url}  ({rec['branch']}, {wt})")
    return 0


def stop_preview(wt: Path) -> int:
    project = main_checkout(wt)
    path, rec = preview_record(project)
    if not rec:
        print(f"no preview of {project}")
        return 0
    drop(path, {**rec, "log": None})
    print(f"preview of {project} ({rec['branch']}) stopped")
    return 0


# ---------- ls, logs ----------

def ls() -> int:
    sweep_temp()
    rows = []
    for kind in ("preview", "temp"):
        for path in sorted((STATE / kind).glob("*.json")):
            rec = read(path) or {}
            state = "up" if alive(rec) else ("starting" if rec.get("pid") is None else "down")
            rows.append(f"{kind:<8} :{rec.get('port')}  {state:<8} {rec.get('branch') or ''}  "
                        f"{rec.get('worktree')}  {rec.get('url') or ''}  log {rec.get('log')}")
    print("\n".join(rows) or "no stands started by the tool (the main stand is the server's: fleet.py status)")
    return 0


def logs(kind: str, wt: Path) -> int:
    if kind == "preview":
        rec = preview_record(main_checkout(wt))[1]
    else:
        rec = next((r for p in (STATE / "temp").glob("*.json") if (r := read(p)) and r["worktree"] == str(wt)), None)
    if not rec:
        raise Stop(f"no {kind} stand of {wt}")
    print(Path(rec["log"]).read_text(errors="replace")[-8000:], end="")
    return 0


def preview_worktree(project: Path) -> Path | None:
    """The worktree the project's preview serves, for the status feed; None when the tool runs none."""
    rec = read(record_path("preview", key(project)))
    return Path(rec["worktree"]) if rec and alive(rec) else None


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="stand.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["start", "stop", "restart", "logs", "ls"])
    ap.add_argument("stand", nargs="?", choices=["temp", "preview", "main"])
    ap.add_argument("--from", dest="src")
    ap.add_argument("--take", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "ls":
        return ls()
    if not a.stand:
        ap.error("name the stand: temp, preview or main")
    if a.stand == "main":
        raise Stop("the main stand is the server's: df-<slug>-stand updates it on every new commit of main "
                   "(fleet.py status)", REFUSED)
    wt = worktree(a.src)
    if a.cmd == "logs":
        return logs(a.stand, wt)
    if a.stand == "temp":
        return stop_temp(wt) if a.cmd == "stop" else start_temp(wt)
    if a.cmd == "stop":
        return stop_preview(wt)
    if a.cmd == "restart" and not a.src:
        rec = preview_record(main_checkout(wt))[1]
        if not rec:
            raise Stop("no preview to restart: start preview --from <worktree>")
        return start_preview(Path(rec["worktree"]), take=True)
    if a.cmd == "start" and not a.src:
        raise Stop("start preview --from <worktree>: name the branch's worktree")
    return start_preview(wt, a.take or a.cmd == "restart")


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1:]))
    except Stop as err:
        print(f"stand: {err}", file=sys.stderr)
        sys.exit(err.code)

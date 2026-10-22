"""Starting the preview environment for end-to-end scenarios and the screenshot generator.

One piece of code for both: conftest.py (the `preview` fixture) and make_screenshots.py.
If they diverged, the user guide would be shot from a different preview than the
one the tests check.

The same stack that goes into the image is started. The preview never reaches
outside: tokens of external systems from the shell are not passed into the
process environment (otherwise an exported monitoring token could reach the preview).
"""

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
# <Replace with the project launch: uvicorn/app factory/built SPA.>
# Seed — a temporary database with data relative to "today", not calendar dates.
PREVIEW_COMMAND = ["<python>", "-m", "<package>", "--port", "{port}"]
# <Environment variables holding the project's external-system tokens — fill in>
UNSET_ENV: tuple[str, ...] = ()
READY_TIMEOUT_SECONDS = 10


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(url: str, process: subprocess.Popen) -> None:
    """GET the root until it answers; a crashed process fails at once instead of waiting."""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"preview exited during startup (code {process.returncode})")
        try:
            with urllib.request.urlopen(f"{url}/", timeout=1):  # noqa: S310 — own localhost
                return
        except urllib.error.HTTPError:
            return  # the server answered — even with an error: it is up
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError(f"preview did not answer at {url}/ within {READY_TIMEOUT_SECONDS} s")


@contextmanager
def running_preview() -> Iterator[str]:
    """URL of the running preview; the process is stopped on exit."""
    port = free_port()
    command = [part.format(port=port) for part in PREVIEW_COMMAND]
    env = {k: v for k, v in os.environ.items() if k not in UNSET_ENV}
    process = subprocess.Popen(command, cwd=APP_DIR, env=env)  # noqa: S603 — own command
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(url, process)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

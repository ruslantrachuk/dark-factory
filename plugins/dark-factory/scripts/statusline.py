#!/usr/bin/env python3
"""Install the status-line feed of the quota watchdog into the user's Claude Code settings.

Claude Code hands the status-line command a JSON with rate_limits.*.used_percentage after every
model reply; `quota.py statusline` writes it to the watchdog's cache — fresh quota data with no
`claude -p` probe. The installed plugin lives under a versioned path
(~/.claude/plugins/cache/<marketplace>/dark-factory/<version>/), so settings.json does not point
at it: it points at a stable wrapper, ~/.claude/dark-factory/statusline.sh, which finds the newest
installed version at run time, feeds it, and then runs the status line the user had before (saved
by the installer), so that output stays as it was.

  statusline.py              dry run: what would change
  statusline.py --apply      write the wrapper and the statusLine of ~/.claude/settings.json
  statusline.py --uninstall  (with --apply) restore the previous statusLine, remove the wrapper
  --feed-only                the wrapper feeds the cache but adds no quota line of its own

The settings directory is $CLAUDE_CONFIG_DIR, else ~/.claude. Run by a human (the
/dark-factory:statusline skill): it edits a user file.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

WRAPPER_DIR = "dark-factory"
WRAPPER = "statusline.sh"
PREVIOUS = "statusline-previous.json"

WRAPPER_TEXT = """#!/bin/sh
# dark-factory status line: feeds the quota watchdog (scripts/quota.py statusline) and keeps the
# status line you had before. Written by /dark-factory:statusline: rerun it to change, --uninstall to remove.
input=$(cat)
cfg="${{CLAUDE_CONFIG_DIR:-$HOME/.claude}}"
# the newest installed version of the plugin: the path in settings.json survives plugin updates
quota=$(for f in "$cfg"/plugins/cache/*/dark-factory/*/scripts/quota.py; do
  [ -f "$f" ] && printf '%s\\t%s\\n' "$(basename "$(dirname "$(dirname "$f")")")" "$f"
done | sort -V | tail -n 1 | cut -f 2)
[ -n "$quota" ] || quota={fallback}
line=$(printf '%s' "$input" | python3 "$quota" statusline 2>/dev/null)
previous={previous}
show={show}
if [ -n "$previous" ]; then
  shell=sh; command -v bash >/dev/null 2>&1 && shell=bash
  out=$(printf '%s' "$input" | "$shell" -c "$previous")
  printf '%s' "$out"
  [ "$show" = 1 ] && [ -n "$line" ] && printf '\\n%s' "$line"
elif [ "$show" = 1 ]; then
  printf '%s' "$line"
fi
exit 0
"""


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def _write_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_settings(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    return data


def wrapper_text(previous: dict | None, feed_only: bool) -> str:
    command = (previous or {}).get("command", "") if (previous or {}).get("type", "command") == "command" else ""
    fallback = Path(__file__).resolve().parent / "quota.py"
    return WRAPPER_TEXT.format(
        fallback=shlex.quote(str(fallback)),
        previous=shlex.quote(command),
        show=0 if feed_only else 1,
    )


def is_ours(status_line, wrapper: Path) -> bool:
    return isinstance(status_line, dict) and str(wrapper) in str(status_line.get("command", ""))


def install(apply: bool, feed_only: bool) -> int:
    cfg = config_dir()
    settings_path, wrapper = cfg / "settings.json", cfg / WRAPPER_DIR / WRAPPER
    saved = cfg / WRAPPER_DIR / PREVIOUS
    settings = read_settings(settings_path)
    current = settings.get("statusLine")
    if is_ours(current, wrapper):
        # reinstall: the status line from before the first install stays the one to chain
        previous = json.loads(saved.read_text(encoding="utf-8")).get("statusLine") if saved.is_file() else None
    else:
        previous = current
    if isinstance(previous, dict) and "quota.py" in str(previous.get("command", "")) \
            and "statusline" in str(previous.get("command", "")):
        print(f"replacing a hand-wired feed: {previous.get('command')}")
        previous = None  # the old hand-wired feed (a versioned path): the wrapper does its job
    new = {"type": "command", "command": f"sh {shlex.quote(str(wrapper))}"}
    if isinstance(previous, dict) and "padding" in previous:
        new["padding"] = previous["padding"]
    print(f"settings:  {settings_path}")
    print(f"wrapper:   {wrapper} (finds the newest installed dark-factory, feeds quota.py statusline)")
    print(f"previous:  {json.dumps(previous) if previous else 'none'}"
          + (" — kept: its output is shown first" if previous else ""))
    print(f"statusLine: {json.dumps(current)} -> {json.dumps(new)}")
    if previous and previous.get("type", "command") != "command":
        print(f"note: the previous statusLine is not a command ({previous.get('type')}); it is not chained")
    if not apply:
        print("dry run: nothing written; add --apply to install")
        return 0
    _write_atomic(saved, json.dumps({"statusLine": previous}, indent=2) + "\n")
    _write_atomic(wrapper, wrapper_text(previous, feed_only), 0o755)
    settings["statusLine"] = new
    _write_atomic(settings_path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print("installed: the status line feeds the quota watchdog after every model reply")
    return 0


def uninstall(apply: bool) -> int:
    cfg = config_dir()
    settings_path, wrapper = cfg / "settings.json", cfg / WRAPPER_DIR / WRAPPER
    saved = cfg / WRAPPER_DIR / PREVIOUS
    settings = read_settings(settings_path)
    current = settings.get("statusLine")
    previous = json.loads(saved.read_text(encoding="utf-8")).get("statusLine") if saved.is_file() else None
    ours = is_ours(current, wrapper)
    if ours:
        print(f"statusLine: {json.dumps(current)} -> {json.dumps(previous) if previous else '(removed)'}")
    else:
        print(f"statusLine is not the dark-factory wrapper ({json.dumps(current)}): left as it is")
    print(f"remove:    {wrapper}, {saved}")
    if not apply:
        print("dry run: nothing written; add --apply to uninstall")
        return 0
    if ours:
        if previous:
            settings["statusLine"] = previous
        else:
            settings.pop("statusLine", None)
        _write_atomic(settings_path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    for f in (wrapper, saved):
        f.unlink(missing_ok=True)
    try:
        wrapper.parent.rmdir()
    except OSError:
        pass  # not empty: something else lives there
    print("uninstalled")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--uninstall", action="store_true", help="restore the previous statusLine")
    ap.add_argument("--feed-only", action="store_true", help="no quota line in the status line")
    args = ap.parse_args(argv[1:])
    try:
        return uninstall(args.apply) if args.uninstall else install(args.apply, args.feed_only)
    except (OSError, ValueError) as exc:
        print(f"statusline: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

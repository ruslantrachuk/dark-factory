#!/usr/bin/env python3
"""The canon block in a project's AGENTS.md: render it, check it, replace it.

A project's rules file (AGENTS.md) holds the project's own sections and the factory canon between two markers:

  <!-- dark-factory:canon:begin v<N> -->
  ...the canon, verbatim from the template...
  <!-- dark-factory:canon:end -->

Upgrade replaces the block whole; text outside it is the project's and is kept byte for byte. Codex reads
AGENTS.md without imports and caps the chain at 32 KiB, so the result is checked against that size.

  canon_block.py render [--canon PATH]                print the block for the current canon
  canon_block.py check FILE [--canon PATH] [--json]   is the block present once and equal to the canon?
  canon_block.py apply FILE [--canon PATH] [--insert] [--dry-run]
                                                      replace the block (or, with --insert, add it before the
                                                      file's first "## " heading when there is none)

Exit codes: 0 ok (check: current; apply: written or already current), 1 check: the block differs from the canon
or is from another version, 2 the file is broken (no block, an unpaired or repeated marker, a nested block), 3 the
result would exceed the size limit (--max-bytes, default 32768).

The canon: --canon, else the block of this plugin's templates/base/AGENTS.md — the template's AGENTS.md is the one
copy of the canon in the repository. A --canon file with a block gives its block's text; a file without one is the
canon as a whole. The version in the begin marker is the plugin's major version. stdlib only, Python 3.11+.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
DEFAULT_CANON = PLUGIN / "templates" / "base" / "AGENTS.md"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
MAX_BYTES = 32 * 1024  # Codex project_doc_max_bytes default: the whole AGENTS.md chain

BEGIN_RE = re.compile(r"^<!-- dark-factory:canon:begin(?: v(\d+))? -->[ \t]*\r?$", re.MULTILINE)
END_RE = re.compile(r"^<!-- dark-factory:canon:end -->[ \t]*\r?$", re.MULTILINE)

EXIT_OK, EXIT_DIFFERS, EXIT_BROKEN, EXIT_TOO_LARGE = 0, 1, 2, 3


class BrokenFile(Exception):
    """The file's markers do not make exactly one well-formed block."""


@dataclass
class Block:
    start: int  # offset of the begin marker
    end: int  # offset just past the end marker line (its newline included when present)
    version: int | None
    body: str  # the text between the marker lines


def plugin_version() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return int(str(data["version"]).split(".")[0])


def read(path: Path) -> str:
    # bytes -> str without newline translation, so the project's text survives exactly
    return path.read_bytes().decode("utf-8")


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def render(canon: str, version: int, nl: str = "\n") -> str:
    body = canon.replace("\r\n", "\n").strip("\n").replace("\n", nl)
    return f"<!-- dark-factory:canon:begin v{version} -->{nl}{body}{nl}<!-- dark-factory:canon:end -->{nl}"


def find_block(text: str) -> Block | None:
    begins = list(BEGIN_RE.finditer(text))
    ends = list(END_RE.finditer(text))
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise BrokenFile(f"expected one begin and one end marker, found {len(begins)} and {len(ends)}")
    b, e = begins[0], ends[0]
    if e.start() < b.end():
        raise BrokenFile("the end marker comes before the begin marker")
    body_start = text.find("\n", b.end())
    body_start = len(text) if body_start < 0 else body_start + 1
    end = e.end()
    if text.startswith("\r\n", end):
        end += 2
    elif text.startswith("\n", end):
        end += 1
    body = text[body_start:e.start()]
    return Block(b.start(), end, int(b.group(1)) if b.group(1) else None, body)


def normalize(s: str) -> str:
    return s.replace("\r\n", "\n").strip("\n")


def status(text: str, canon: str, version: int) -> tuple[int, str]:
    try:
        block = find_block(text)
    except BrokenFile as exc:
        return EXIT_BROKEN, f"broken: {exc}"
    if block is None:
        return EXIT_BROKEN, "broken: no canon block"
    if normalize(block.body) != normalize(canon):
        return EXIT_DIFFERS, "differs: the block is not the current canon (edited by hand or from another release)"
    if block.version != version:
        return EXIT_DIFFERS, f"differs: the block is marked v{block.version}, the canon is v{version}"
    return EXIT_OK, f"current: v{version}"


def replaced(text: str, canon: str, version: int, insert: bool) -> str:
    nl = newline_of(text)
    new_block = render(canon, version, nl)
    block = find_block(text)  # BrokenFile propagates
    if block is not None:
        return text[: block.start] + new_block + text[block.end :]
    if not insert:
        raise BrokenFile("no canon block (use --insert to add one)")
    heading = re.search(r"^## ", text, re.MULTILINE)
    if heading is None:
        sep = "" if not text or text.endswith(("\n", "\r\n")) else nl
        return text + sep + nl + new_block
    return text[: heading.start()] + new_block + nl + text[heading.start() :]


def load_canon(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"canon_block: no canon file at {path}")
    text = read(path)
    try:
        block = find_block(text)
    except BrokenFile as exc:
        raise SystemExit(f"canon_block: the canon source {path} is broken: {exc}")
    return text if block is None else block.body


def cmd_render(args) -> int:
    sys.stdout.write(render(load_canon(args.canon), args.version))
    return EXIT_OK


def cmd_check(args) -> int:
    code, msg = status(read(args.file), load_canon(args.canon), args.version)
    size = args.file.stat().st_size
    if code == EXIT_OK and size > args.max_bytes:
        code, msg = EXIT_TOO_LARGE, f"too large: {size} bytes, the limit is {args.max_bytes}"
    if args.json:
        print(json.dumps({"file": str(args.file), "code": code, "status": msg.split(":")[0], "detail": msg,
                          "bytes": size, "version": args.version}))
    else:
        print(f"{args.file}: {msg}")
    return code


def cmd_apply(args) -> int:
    old = read(args.file)
    try:
        new = replaced(old, load_canon(args.canon), args.version, args.insert)
    except BrokenFile as exc:
        print(f"{args.file}: broken: {exc}; nothing changed", file=sys.stderr)
        return EXIT_BROKEN
    size = len(new.encode("utf-8"))
    if size > args.max_bytes:
        print(f"{args.file}: would be {size} bytes, the limit is {args.max_bytes}; nothing changed", file=sys.stderr)
        return EXIT_TOO_LARGE
    if new == old:
        print(f"{args.file}: current (v{args.version}), nothing to do")
        return EXIT_OK
    if args.dry_run:
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                   str(args.file), f"{args.file} (canon v{args.version})"))
        return EXIT_OK
    args.file.write_bytes(new.encode("utf-8"))
    print(f"{args.file}: canon block set to v{args.version}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="The canon block in a project's AGENTS.md.")
    p.add_argument("--canon", type=Path, default=DEFAULT_CANON, help="canon source (default: the plugin's)")
    p.add_argument("--version", type=int, default=None, help="version in the begin marker (default: plugin major)")
    p.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    c = sub.add_parser("check")
    c.add_argument("file", type=Path)
    c.add_argument("--json", action="store_true")
    a = sub.add_parser("apply")
    a.add_argument("file", type=Path)
    a.add_argument("--insert", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if args.version is None:
        args.version = plugin_version()
    if args.cmd != "render" and not args.file.is_file():
        print(f"{args.file}: no such file", file=sys.stderr)
        return EXIT_BROKEN
    return {"render": cmd_render, "check": cmd_check, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

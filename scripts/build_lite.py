#!/usr/bin/env python3
"""Build plugins/dark-factory-lite from the dark-factory plugin: python3 scripts/build_lite.py [--check]

The light edition is the factory's method without anything that runs on its own: chosen skills and roles, as text,
for the plugin directory, which accepts hooks, scripts and workflows only from verified organizations. The skills live
once, in plugins/dark-factory; this script copies them and adapts what the directory refuses or what has no meaning
without the full plugin:

- roles lose the `skills:` preload (a frontmatter key outside the directory's allowed list) and name the skills in
  their text instead; every frontmatter value is quoted;
- `dark-factory:<skill>` becomes `dark-factory-lite:<skill>`;
- the skill-check cases are not shipped: their scaffold scripts are shell files, which the directory accepts only from
  verified organizations. `--with-cases` adds the cases of the chosen skills to the build for a check run (CI does it
  in the job, never committed).

--check builds into a temporary folder and exits 1 when the committed copy differs: the test suite runs it, so a skill
changed in plugins/dark-factory without a rebuild fails CI.
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "plugins" / "dark-factory"
LITE = ROOT / "plugins" / "dark-factory-lite"
SOURCES = ROOT / "scripts" / "lite"

SKILLS = ["size-task", "wsjf", "plan", "build-tdd", "integrate", "wrap"]
AGENTS = ["tech-lead", "product-owner", "reviewer", "builder"]
CASES_DIR = "evals"  # the CLI's default folder for skill-check cases

# Role text that speaks of preloaded skills: the light roles name the skills to use instead.
ROLE_TEXT = [
    ("The preloaded skills are your procedure:", "These skills of this plugin are your procedure, used at each step:"),
    ("the preloaded `", "the `"),
    ("by the preloaded `", "by the `"),
]


def rename(text: str) -> str:
    text = text.replace("Part of the dark-factory plugin", "Part of dark-factory-lite, the light edition of dark-factory")
    return re.sub(r"\bdark-factory:(?=[a-z])", "dark-factory-lite:", text)


def split_frontmatter(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.index("\n---\n", 4)
    return text[4:end].split("\n"), text[end + 5:]


def role(text: str) -> str:
    lines, body = split_frontmatter(text)
    out: list[str] = []
    skip_list = False
    for line in lines:
        if skip_list:
            if line.startswith("  - ") or line.startswith("- "):
                continue
            skip_list = False
        key, sep, value = line.partition(":")
        if not sep or line.startswith(" "):
            out.append(line)
            continue
        if key == "skills":
            skip_list = True
            continue
        value = value.strip()
        if value and not (value.startswith('"') or value.startswith("'")):
            value = json.dumps(value, ensure_ascii=False)
        out.append(f"{key}: {value}" if value else f"{key}:")
    for old, new in ROLE_TEXT:
        body = body.replace(old, new)
    return "---\n" + "\n".join(out) + "\n---\n" + rename(body)


def build(dest: Path, with_cases: bool = False) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / ".claude-plugin").mkdir(parents=True)
    version = json.loads((FULL / ".claude-plugin" / "plugin.json").read_text())["version"]
    manifest = (SOURCES / "plugin.json").read_text().replace("{version}", version)
    (dest / ".claude-plugin" / "plugin.json").write_text(manifest)
    shutil.copy2(FULL / ".claude-plugin" / "icon.png", dest / ".claude-plugin" / "icon.png")
    shutil.copy2(SOURCES / "README.md", dest / "README.md")
    for name in SKILLS:
        src = FULL / "skills" / name
        files = sorted(p for p in src.rglob("*") if p.is_file())
        for f in files:
            target = dest / "skills" / name / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rename(f.read_text()))
    (dest / "agents").mkdir()
    for name in AGENTS:
        (dest / "agents" / f"{name}.md").write_text(role((FULL / "agents" / f"{name}.md").read_text()))
    if with_cases:
        for case in sorted((FULL / CASES_DIR).iterdir()):
            if case.is_dir() and any(case.name.startswith(s + "-") for s in SKILLS):
                shutil.copytree(case, dest / CASES_DIR / case.name)


def same(a: Path, b: Path) -> list[str]:
    diffs: list[str] = []
    cmp = filecmp.dircmp(a, b)
    diffs += [f"only in the build: {n}" for n in cmp.left_only] + [f"only committed: {n}" for n in cmp.right_only]
    for n in cmp.common_files:
        if (a / n).read_bytes() != (b / n).read_bytes():
            diffs.append(f"differs: {(b / n).relative_to(LITE)}")
    for n in cmp.common_dirs:
        diffs += same(a / n, b / n)
    return diffs


def main() -> int:
    if "--check" in sys.argv[1:]:
        with tempfile.TemporaryDirectory() as tmp:
            built = Path(tmp) / "lite"
            build(built)
            diffs = same(built, LITE) if LITE.exists() else ["plugins/dark-factory-lite is missing"]
        if diffs:
            print("dark-factory-lite is out of date — run python3 scripts/build_lite.py and commit:")
            print("\n".join("  " + d for d in diffs))
            return 1
        print("dark-factory-lite matches its sources")
        return 0
    with_cases = "--with-cases" in sys.argv[1:]
    build(LITE, with_cases)
    print(f"built {LITE.relative_to(ROOT)}" + (" with the skill-check cases (do not commit them)" if with_cases else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

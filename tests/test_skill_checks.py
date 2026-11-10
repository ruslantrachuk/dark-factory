#!/usr/bin/env python3
"""Shape of the skill-check cases in plugins/dark-factory/evals/: python3 tests/test_skill_checks.py
No model is called. `claude plugin eval` refuses a scaffold script outside its case directory, so each case carries
copies of the shared scripts in `_fixtures/`; these tests keep the copies equal to the source and every case runnable."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

CASES = Path(__file__).resolve().parents[1] / "plugins" / "dark-factory" / "evals"
FIXTURES = CASES / "_fixtures"


def case_dirs() -> list[Path]:
    return sorted(d for d in CASES.iterdir() if d.is_dir() and ((d / "prompt.md").exists() or (d / "case.yaml").exists()))


class SkillCheckCases(unittest.TestCase):
    def test_there_are_cases(self) -> None:
        self.assertGreater(len(case_dirs()), 0)

    def test_every_case_has_a_grader(self) -> None:
        for d in case_dirs():
            with self.subTest(case=d.name):
                self.assertTrue(list((d / "graders").glob("*.md")), "a case without graders fails to load")

    def test_scaffold_script_is_inside_the_case(self) -> None:
        for d in case_dirs():
            yaml = d / "case.yaml"
            if not yaml.exists():
                continue
            m = re.search(r"scaffold_script:\s*(\S+)", yaml.read_text())
            if not m:
                continue
            with self.subTest(case=d.name):
                self.assertNotIn("..", m.group(1))
                self.assertFalse(m.group(1).startswith("/"))
                self.assertTrue((d / m.group(1)).is_file())

    def test_copies_of_shared_scripts_match_the_source(self) -> None:
        shared = {p.name: p.read_bytes() for p in FIXTURES.glob("*.sh")}
        for d in case_dirs():
            for script in d.glob("*.sh"):
                if script.name in shared:
                    with self.subTest(case=d.name, script=script.name):
                        self.assertEqual(script.read_bytes(), shared[script.name],
                                         f"copy {d.name}/{script.name} differs from _fixtures/: copy it again")


if __name__ == "__main__":
    unittest.main()

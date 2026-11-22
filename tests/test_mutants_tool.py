"""How the mutant tool reads a run of the suite (tests/mutants.py: `read`, `passed`).

The tool is not run here, and nothing here looks at a mutant or at where it is anchored: a test of that kind would be
changed by the mutants themselves. Only the reading of unittest's last lines is held — found wanting on 2026-11-21,
when a skipped test made the line "OK (skipped=1)" and the tool took the unmutated tree for one with no result.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tool():
    keep = sys.argv
    sys.argv = ["mutants.py"]
    try:
        spec = importlib.util.spec_from_file_location("mutants_tool", ROOT / "tests" / "mutants.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    finally:
        sys.argv = keep
    return m


BAR = "-" * 70


class WhatTheToolReads(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = tool()

    def test_a_suite_that_passed_with_or_without_a_skipped_test(self) -> None:
        for last in ("OK", "OK (skipped=1)", "OK (skipped=2, expected failures=1)"):
            with self.subTest(last):
                killed, summary = self.m.read(f"....s...\n{BAR}\nRan 811 tests in 180.1s\n\n{last}\n")
                self.assertEqual((killed, summary), (False, f"Ran 811 {last}; 0 test(s): "))
                self.assertTrue(self.m.passed(summary))

    def test_a_suite_that_failed(self) -> None:
        out = f"FAIL: test_one_thing (tests.x.Y.test_one_thing)\n{BAR}\nERROR: test_another (tests.x.Y.test_another)\n{BAR}\nRan 811 tests in 3.0s\n\nFAILED (failures=1, errors=1, skipped=1)\n"
        killed, summary = self.m.read(out)
        self.assertEqual((killed, summary), (True, "Ran 811 FAILED (failures=1, errors=1, skipped=1); 2 test(s): another, one_thing"))
        self.assertFalse(self.m.passed(summary))

    def test_a_run_that_said_nothing_is_neither_killed_nor_passed(self) -> None:
        for out in ("", "Traceback (most recent call last):\n  ...\nImportError: no\n", f"{BAR}\nRan 0 tests in 0.0s\n\nOK\n", f"{BAR}\nRan 811 tests in 3.0s\n"):
            with self.subTest(out[-24:]):
                killed, summary = self.m.read(out)
                self.assertEqual((killed, self.m.passed(summary)), (False, False), summary)

    def test_a_word_in_the_middle_of_a_line_is_not_the_result(self) -> None:
        killed, summary = self.m.read(f"it said OK and then FAILED somewhere\n{BAR}\nRan 5 tests in 0.1s\n\nOK\n")
        self.assertEqual((killed, summary), (False, "Ran 5 OK; 0 test(s): "))


class WhereAStoppedRunGoesOn(unittest.TestCase):
    """A run that was stopped (2026-11-22: by the session, the machine short of memory) goes on from where its record
    ends: the record's lines are in the list's order, so the count of them is the place."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = tool()

    def test_the_first_of_the_list_are_passed_by_and_the_rest_are_taken_in_order(self) -> None:
        every = self.m.MUTANTS
        self.assertEqual(self.m.taken("", 0), every)
        self.assertEqual(self.m.taken("", 7), every[7:])
        self.assertEqual(self.m.taken("", len(every)), [])
        name = every[9][1]
        self.assertEqual([m[1] for m in self.m.taken(name, 9)][:1], [name])
        self.assertNotIn(every[9], self.m.taken(name, 10))

    def test_a_place_that_is_not_in_the_list_is_refused(self) -> None:
        for start in (-1, len(self.m.MUTANTS) + 1):
            with self.subTest(start), self.assertRaises(ValueError):
                self.m.taken("", start)


if __name__ == "__main__":
    unittest.main()

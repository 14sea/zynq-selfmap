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


class ASuiteThatShowsAnotherSuite(unittest.TestCase):
    """2026-11-23: tests/test_prober_dirty.py runs the twin tests of the older stages once more and, when they fail,
    shows what they said. That has a "Ran 38 tests" of its own before the suite's; the tool took the first, found it
    was not the count of the unmutated tree, and called eight mutants that tests had killed BROKEN."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = tool()

    def test_the_count_is_the_suite_s_own_which_is_the_last(self) -> None:
        out = (f"F..\n======\nFAIL: test_inner (tests.test_x.X.test_inner)\n{BAR}\nAssertionError: 1 != 0 : ...\n{BAR}\nRan 38 tests in 0.4s\n\nFAILED (failures=6)\n"
               f"\n{BAR}\nRan 987 tests in 300.2s\n\nFAILED (failures=1, skipped=1)\n")
        self.assertEqual(self.m.read(out), (True, "Ran 987 FAILED (failures=1, skipped=1); 1 test(s): inner"))
        inner_only = f"{BAR}\nRan 38 tests in 0.4s\n\nFAILED (failures=6)\n"
        self.assertEqual(self.m.read(inner_only)[1][:7], "Ran 38 ")

    def test_that_test_sets_in_what_it_shows(self) -> None:
        text = (ROOT / "tests" / "test_prober_dirty.py").read_text()
        self.assertIn('"  | " + line for line in r.stderr[-1200:].splitlines()', text)
        self.assertEqual(text.count("r.stderr[-"), 1, "nothing of the other suite's words is shown as it came")


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


class NoSuiteOfTheToolReachesABoard(unittest.TestCase):
    """Section 33 of the S2 plan. A mutant can take away the check that keeps a test from the board's runner (the
    chains' tests of the command hold it back by that check alone), and the board's adapter may be attached while the
    tool runs. Every suite the tool starts is given SELFMAP_NO_BOARD, and where that is set no console is opened."""

    def test_the_tool_gives_it_to_every_suite(self) -> None:
        import subprocess
        from unittest import mock
        m = tool()
        self.assertEqual(m.NO_BOARD, {"SELFMAP_NO_BOARD": "1"})
        seen: list[dict] = []

        def run(cmd, **kw):
            seen.append(kw["env"])
            return subprocess.CompletedProcess(cmd, 0, "", f"{BAR}\nRan 3 tests in 0.1s\n\nOK\n")
        sys.path.insert(0, str(ROOT / "tests"))
        import scratch_dirs
        tree = Path(scratch_dirs.mkdtemp(prefix="smtool_")) / "tree"; tree.mkdir()
        with mock.patch.object(m.subprocess, "run", run), mock.patch.dict("os.environ", {"SELFMAP_NO_BOARD": ""}):
            self.assertEqual(m.suite(tree), (False, "Ran 3 OK; 0 test(s): "))
        self.assertEqual([env["SELFMAP_NO_BOARD"] for env in seen], ["1"], "whatever the tool's own environment says of it")

    def test_where_it_is_set_the_console_is_not_opened(self) -> None:
        from unittest import mock
        sys.path.insert(0, str(ROOT / "host"))
        import serial
        import uboot_console

        def opened(*a, **kw):
            raise AssertionError("the port was opened")
        with mock.patch.object(uboot_console.serial, "Serial", opened), mock.patch.object(uboot_console, "open", opened, create=True):
            with mock.patch.dict("os.environ", {"SELFMAP_NO_BOARD": "1"}):
                self.assertRaisesRegex(serial.SerialException, "SELFMAP_NO_BOARD is set", uboot_console.UB)
            with mock.patch.dict("os.environ"):
                import os
                os.environ.pop("SELFMAP_NO_BOARD", None)
                self.assertRaisesRegex(AssertionError, "the port was opened", uboot_console.UB)   # without it the port is what is asked for

    def test_every_session_with_the_board_begins_with_that_console(self) -> None:
        """What the lock rests on: no file under host/ opens the port by another way before a console of that class
        is made (the run script opens it again after a transfer, with a console in hand)."""
        import re
        for f in sorted((ROOT / "host").glob("*.py")):
            text = f.read_text()
            if f.name == "uboot_console.py":
                self.assertEqual(text.count("serial.Serial("), 1)
                self.assertLess(text.index("SELFMAP_NO_BOARD"), text.index("serial.Serial("))
            elif f.name == "s1a_run.py":
                self.assertEqual(len(re.findall(r"serial\.Serial\(|open\(DEV", text)), 2, "the two of the transfer, after the console was made")
                self.assertIn("    con.s = serial.Serial(DEV, 115200, timeout=0.1)", text)
            else:
                self.assertFalse(re.search(r"serial\.Serial\(|open\(DEV|/dev/", text), f.name)


if __name__ == "__main__":
    unittest.main()

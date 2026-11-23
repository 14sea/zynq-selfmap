"""Every stage on memory that holds something — docs/s2_plan.md, section 32 (review of 5936a8e).

Stage 9 answered a refused block with a result that took in words it had not written. The twin can be started with
memory that is not zero (SM_DIRTY=1, prober/twin_hal.c); it then writes no result out of which a word was never
written, and ends with a code instead. Here the tests of the other stages are run once more in that way: each of
these files starts the twin with the environment it is run in, so nothing of them needs to change. (The tests of
stage 9 are made on such memory always: tests/test_prober_s2_3.py.)"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("test_prober_twin", "test_prober_s1b0", "test_prober_s1b0b", "test_prober_s1b1", "test_prober_s2", "test_prober_s2_2")


class OnMemoryThatHoldsSomething(unittest.TestCase):
    def test_the_twin_tests_of_the_other_stages_pass_on_it(self) -> None:
        for name in FILES:
            with self.subTest(name):
                r = subprocess.run([sys.executable, "-B", "-m", "unittest", f"tests.{name}"], cwd=ROOT, capture_output=True, text=True,
                                   env=dict(os.environ, SM_DIRTY="1"))
                ran = re.search(r"^Ran (\d+) tests?", r.stderr, re.M)
                self.assertTrue(ran and int(ran.group(1)) > 0, r.stderr[-400:])
                self.assertEqual((r.returncode, r.stderr.strip().splitlines()[-1]), (0, "OK"), r.stderr[-1200:])

    def test_these_files_do_start_the_twin_with_the_environment_they_are_run_in(self) -> None:
        """What the test above rests on: none of them takes SM_DIRTY away before it starts the twin."""
        for name in FILES:
            text = (ROOT / "tests" / f"{name}.py").read_text()
            self.assertNotIn("SM_DIRTY", text, name)
            self.assertTrue("env = dict(os.environ)" in text or re.search(r"from test_prober_\w+ import .*\bRun\b", text), name)

    def test_the_twin_does_end_with_a_code_for_a_result_of_which_a_word_was_never_written(self) -> None:
        """The check itself, asked of the twin: its stale-word count is made over the whole result, with the pattern
        the memory was filled with."""
        text = (ROOT / "prober" / "twin_hal.c").read_text()
        self.assertEqual(text.count("ddr[i] = DIRTY(i);"), 1)
        self.assertEqual(text.count("for (i = 0; i < total; i++) if (ddr[i] == DIRTY(i)) stale++;"), 1)
        self.assertIn("if (stale) {", text)


if __name__ == "__main__":
    unittest.main()

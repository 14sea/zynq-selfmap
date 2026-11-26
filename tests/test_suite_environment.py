"""The shell the suite is run in (review of S2, finding F5; docs/s2_plan.md, section 31).

The twin reads its switches from the environment (`SM_LIST`, `SM_FAULT` and the rest: `prober/twin_hal.c`). Most of
the tests that start it take away the ones they do not set, but not all of them take away all: a shell left with such
a variable from a diagnosis once gave 955 errors that were none. Clearing them for the whole suite is not the answer —
`tests/test_prober_dirty.py` runs the twin's tests on purpose with `SM_DIRTY` set and rests on its reaching the twin —
so the suite says it instead, once, by name. That test runs single files, not this one."""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def the_twin_s_variables() -> set[str]:
    return set(re.findall(r'getenv\("(SM_[A-Z0-9_]+)"\)', (ROOT / "prober" / "twin_hal.c").read_text()))


class TheShellTheSuiteIsRunIn(unittest.TestCase):
    def test_the_twin_s_variables_are_found_where_it_reads_them(self) -> None:
        names = the_twin_s_variables()
        self.assertTrue({"SM_LIST", "SM_FAULT", "SM_DIRTY", "SM_ACC"} <= names, names)

    def test_no_variable_of_the_twin_is_set(self) -> None:
        left = sorted(n for n in the_twin_s_variables() if n in os.environ)
        self.assertEqual(left, [], "the shell has the twin's variables set; tests that start the twin would read them. "
                                   "Run the suite without them (e.g. env -u NAME ...)")


if __name__ == "__main__":
    unittest.main()

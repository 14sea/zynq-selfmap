"""The after-the-fact comparison with an outside description. The database here is made up by the test:
the comparison has to say "agrees" and "differs" correctly whatever the database holds."""
from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import grade_s1b1  # noqa: E402
import s1b1_judge  # noqa: E402
from test_prober_s1b1 import Run, column, frames_for  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())


def database(counts: dict[int, int]) -> dict:
    return {"global_clock_regions": {"top": {"rows": {"0": {"configuration_buses": {"CLB_IO_CLK": {"configuration_columns": {
        str(c): {"frame_count": n} for c, n in counts.items()}}}}}}}}


def verdict(**kw) -> dict:
    r = Run(**kw)
    return s1b1_judge.judge(r.words, KNOWN, r.params)


class Grade(unittest.TestCase):
    def test_the_address_fields(self) -> None:
        self.assertEqual(grade_s1b1.fields(0xB98), {"block_type": 0, "half": "top", "row": 0, "column": 0x17, "minor": 0x18})
        self.assertEqual(grade_s1b1.address(0, "top", 0, 0x18, 0), 0xC00)
        self.assertEqual(grade_s1b1.fields(0x00C20080), {"block_type": 1, "half": "bottom", "row": 1, "column": 1, "minor": 0})

    def test_agreement_and_each_kind_of_disagreement(self) -> None:
        v = verdict()
        g = grade_s1b1.grade(v, database({23: 36, 24: 36}))
        self.assertEqual((len(g["agrees"]), g["differs"], g["not_compared"], g["database_frame_count"]), (3, [], [], 36))
        g = grade_s1b1.grade(v, database({23: 28, 24: 36}))
        self.assertEqual(g["differs"], ["frames in the column: the walk found 36, the database says 28"])
        g = grade_s1b1.grade(v, database({23: 36}))
        self.assertEqual((g["differs"], len(g["not_compared"])), ([], 1), "the last column of a row: nothing to compare the named address with")
        g = grade_s1b1.grade(v, database({22: 36}))
        self.assertEqual((g["differs"], len(g["not_compared"])), ([], 1), "a column the database does not have")
        v = verdict(succ=column(36, after=0xC80))                   # the device names minor 0 of the column after the next
        self.assertTrue(any("0x00000c80" in d and "0x00000c00" in d for d in grade_s1b1.grade(v, database({23: 36, 24: 36}))["differs"]))

    def test_a_walk_that_stopped_at_its_limit_or_left_the_column(self) -> None:
        v = verdict(limit=5)
        g = grade_s1b1.grade(v, database({23: 36, 24: 36}))
        self.assertEqual((g["differs"], any("stopped at its limit after 5 frames" in a for a in g["agrees"])), ([], True))
        self.assertEqual(g["not_compared"], ["the walk stopped at its limit: neither the length of the column nor what follows it was compared"])
        self.assertTrue(grade_s1b1.grade(v, database({23: 4, 24: 36}))["differs"], "more frames walked than the database has")
        v = verdict(succ={0xB83: 0xBF0, 0xBF1: 0x1000}, frames=frames_for([0xB80, 0xB81, 0xB82, 0xB83, 0xBF0, 0xBF1, 0xB99]))
        self.assertTrue(any("not minors 0.. of one column" in d for d in grade_s1b1.grade(v, database({23: 36, 24: 36}))["differs"]))

    def test_a_walk_that_did_not_finish_is_not_taken_for_the_column(self) -> None:
        """Found in review: a walk stopped by an anomaly after six frames was reported as "the column has 6 frames, the
        database says 36", and the address it had just been told was held against the start of the next column."""
        for kw in ({"fault": "padnz@14"}, {"succ": {0xB85: 0xB85}}, {"fault": "err@70", "poll_limit": 30}):
            with self.subTest(str(kw)):
                v = verdict(**kw)
                self.assertEqual((v["verdict"], v["passes"][0]["ended"]), ("FAIL", "not ended"))
                g = grade_s1b1.grade(v, database({23: 36, 24: 36}))
                self.assertEqual(g["differs"], [])
                self.assertEqual(g["judge_verdict"], "FAIL")
                self.assertTrue(any("did not finish after" in a for a in g["agrees"]))
                self.assertFalse(any("frames in the column" in x or "next column" in x for x in g["agrees"] + g["differs"]))
                self.assertEqual(len(g["not_compared"]), 2, "the verdict was not PASS; and the walk did not finish")
        v = verdict(fault="padnz@14")
        self.assertTrue(grade_s1b1.grade(v, database({23: 4, 24: 36}))["differs"], "already more frames than the database has is still a difference")
        g = grade_s1b1.grade(verdict(), database({23: 36, 24: 36}))
        self.assertEqual((g["judge_verdict"], g["walk_ended"], g["not_compared"]), ("PASS", "the device named an address outside the envelope", []))

    def test_the_prober_and_the_judges_never_see_the_database(self) -> None:
        """The closed-book rule, as far as a test can hold it: nothing but this one program names the database, and
        no judge, run script or prober source imports it or carries a frame count for a column."""
        for path in list((ROOT / "host").glob("*.py")) + list((ROOT / "prober").glob("*.[ch]")):
            text = path.read_text()
            if path.name in ("grade_s1b1.py", "grade_s1b2.py"):     # the two graders (the second is held the same way in test_s1b2)
                continue
            self.assertNotIn("prjxray", text.lower(), path.name)
            self.assertNotIn("grade_s1b1", text, path.name)
            self.assertNotIn("frame_count", text, path.name)
        tree = ast.parse((ROOT / "host" / "grade_s1b1.py").read_text())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib"}, set(), "and it uses nothing of the judge's but the verdict file")


if __name__ == "__main__":
    unittest.main()

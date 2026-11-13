"""The host side of S1a: the judge, on results produced by the twin (the run script is in test_s1a_run.py)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1a_judge  # noqa: E402
from test_prober_twin import Run  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())


HDR, REC, DATA_AT = 64, 266, 16 + 43 + 5
# the only things the judge may say about a run whose records are consistent with the prober's own account
HONEST = ("the run did not complete", "anomalous read(s)", "the run stopped at", "differs from the known frame")


def at(record: int, field: int) -> int:
    return HDR + record * REC + field


class Judge(unittest.TestCase):
    def test_a_clean_run_passes(self) -> None:
        v = s1a_judge.judge(Run().words, KNOWN)
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(len(v["records"]), 11)
        self.assertTrue(all(r["matches_known"] and r["pad_all_zero"] for r in v["records"]))

    def test_for_every_fault_the_judge_rederives_exactly_what_the_prober_reported(self) -> None:
        """The judge rebuilds codes, status, anomaly count and stop record from the raw words. On every fault
        the twin can inject, that reconstruction must agree with the prober: the verdict is FAIL, and the only
        complaints are that the run stopped or had anomalies — never an inconsistency."""
        faults = ["ctrl", "lpbk", "nodone", "dcache", "stale", "err@1", "err@2", "err@3", "err@4", "err@5", "err@6", "timeout@4",
                  "timeout@5", "timeout@6", "drop@4", "drop@5", "drop@6", "dropafter@3", "dropafter@4", "dropafter@6", "short@2",
                  "padnz@3", "flip@5", "short@2,flip@3", "short@2,short@3", "flip@11", "short@2,padnz@6", "short@1", "padnz@1"]
        for fault in faults:
            with self.subTest(fault):
                v = s1a_judge.judge(Run(fault, poll_limit=40).words, KNOWN)
                self.assertEqual(v["verdict"], "FAIL")
                odd = [p for p in v["problems"] if not any(h in p for h in HONEST)]
                self.assertEqual(odd, [])
        for name, over in (("budget", {"budget": 0}), ("bad parameters", {"repeats": 9})):
            with self.subTest(name):
                v = s1a_judge.judge(Run("short@2", **over).words, KNOWN)
                self.assertEqual((v["verdict"], [p for p in v["problems"] if not any(h in p for h in HONEST + ("bad parameters",))]), ("FAIL", []))

    def test_a_frame_that_differs_from_the_known_one_fails_even_if_the_board_saw_nothing_wrong(self) -> None:
        words = list(Run().words)
        for i in (0, 2, 5, 8, 10):                           # every reading of 0xb99, as if the device returned this consistently
            words[at(i, DATA_AT + 101 + 9)] ^= 1
        v = s1a_judge.judge(words, KNOWN)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(all("differs from the known frame" in p for p in v["problems"]), v["problems"])

    # ---- the three results an earlier judge let through
    def test_a_nonzero_pad_under_a_clean_code_fails(self) -> None:
        words = list(Run().words); words[at(2, DATA_AT + 7)] = 0x100
        v = s1a_judge.judge(words, KNOWN)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("record 2: code 0x0, but its raw words say 0x11" in p for p in v["problems"]), v["problems"])

    def test_eleven_copies_of_the_baseline_fail(self) -> None:
        words = list(Run().words); base = words[HDR:HDR + REC]
        for i in range(1, 11):
            words[HDR + i * REC:HDR + (i + 1) * REC] = base
        v = s1a_judge.judge(words, KNOWN)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("expected the target read of 0x00000b98" in p for p in v["problems"]), v["problems"])

    def test_a_header_that_counts_an_anomaly_no_record_shows_fails(self) -> None:
        words = list(Run().words); words[4] = 1
        v = s1a_judge.judge(words, KNOWN)
        self.assertTrue(any("the header counts 1 anomalies; the records show 0" in p for p in v["problems"]), v["problems"])
        self.assertEqual(v["verdict"], "FAIL")

    # ---- other ways a buffer can disagree with itself
    def test_tampered_buffers_fail(self) -> None:
        clean = Run().words
        cases = {
            "two records swapped": lambda w: w.__setitem__(slice(at(1, 0), at(3, 0)), w[at(2, 0):at(3, 0)] + w[at(1, 0):at(2, 0)]),
            "a target read relabelled as another frame": lambda w: w.__setitem__(at(1, 0), 0xB9A),
            "a wrong repeat number": lambda w: w.__setitem__(at(4, 12), 0),
            "a wrong kind": lambda w: w.__setitem__(at(5, 1), 1),
            "a status that is not done": lambda w: w.__setitem__(2, 0x300),
            "a stop record on a completed run": lambda w: w.__setitem__(18, 3),
            "a sentinel word under a clean code": lambda w: w.__setitem__(at(3, DATA_AT + 150), 0xA5A55A5A),
            "a wrong survivor count": lambda w: w.__setitem__(at(3, 9), 5),
            "an error bit under a clean code": lambda w: w.__setitem__(at(6, 5), w[at(6, 5)] | 0x00040000),
            "a transfer that never finished under a clean code": lambda w: w.__setitem__(at(6, 3), 0x4),
            "a repeat that differs under a clean code": lambda w: w.__setitem__(at(7, DATA_AT + 101 + 50), w[at(7, DATA_AT + 101 + 50)] ^ 4),
            "a health flag on a target read": lambda w: w.__setitem__(at(4, 10), 1),
            "the final flag cleared": lambda w: w.__setitem__(at(10, 10), 0),
            "a stream claiming CMD = WCFG": lambda w: w.__setitem__(at(3, 16 + 5), 1),
            "a stream addressing a frame outside the envelope": lambda w: w.__setitem__(at(2, 16 + 8), 0x00400A20),
            "a stream addressing another frame than the record says": lambda w: w.__setitem__(at(1, 16 + 8), 0xB9A),
            "a cleanup without DESYNC": lambda w: w.__setitem__(at(2, 16 + 43 + 2), 0),
            "a nonzero guard word": lambda w: w.__setitem__(at(2, 13), 0x101),
            "a record address outside the envelope": lambda w: (w.__setitem__(at(1, 0), 0xB97), w.__setitem__(at(1, 16 + 8), 0xB97)),
        }
        for name, change in cases.items():
            with self.subTest(name):
                words = list(clean); change(words)
                self.assertEqual(s1a_judge.judge(words, KNOWN)["verdict"], "FAIL")

    def test_a_dropped_record_fails_even_with_the_sizes_repaired(self) -> None:
        words = list(Run().words)
        del words[at(4, 0):at(5, 0)]
        words[3] -= 1; words[5] -= REC
        v = s1a_judge.judge(words, KNOWN)
        self.assertEqual(v["verdict"], "FAIL")

    def test_a_run_cut_short_before_its_last_reads_fails_even_with_the_sizes_repaired(self) -> None:
        for cut in (1, 2, 5):                                # the final reference read; that and the last target read; more
            with self.subTest(cut=cut):
                words = list(Run().words)
                del words[at(11 - cut, 0):]
                words[3] -= cut; words[5] -= cut * REC
                v = s1a_judge.judge(words, KNOWN)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any("is missing" in p for p in v["problems"]), v["problems"])

    def test_a_stopped_run_relabelled_as_done_fails(self) -> None:
        """A run that stopped at its very first read has no anomaly count to give it away: only the walk does."""
        for fault in ("stale", "err@1", "timeout@2"):
            with self.subTest(fault):
                words = list(Run(fault, poll_limit=40).words)
                self.assertNotEqual(words[2], 1)
                words[2] = 1
                v = s1a_judge.judge(words, KNOWN)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any("the records imply" in p for p in v["problems"]), v["problems"])

    def test_truncated_padded_or_foreign_data_is_invalid(self) -> None:
        clean = Run().words
        self.assertEqual(s1a_judge.judge(clean[:500], KNOWN)["verdict"], "INVALID")
        self.assertEqual(s1a_judge.judge(clean + [0], KNOWN)["verdict"], "INVALID")
        self.assertEqual(s1a_judge.judge([0] * 3000, KNOWN)["verdict"], "INVALID")
        words = list(clean); words[32 + 7] = 9               # the echoed repeat count out of range
        self.assertEqual(s1a_judge.judge(words, KNOWN)["verdict"], "INVALID")

    def test_the_console_line_and_return_code_the_judge_predicts_are_the_prober_s(self) -> None:
        for fault in ("", "short@2", "err@5", "dcache", "short@2,flip@3"):
            with self.subTest(fault or "clean"):
                r = Run(fault)
                v = s1a_judge.judge(r.words, KNOWN)
                self.assertEqual("\r\n".join(v["expected_console"]) + "\r\n", r.uart)
                self.assertEqual(int(v["expected_return_code"], 16), r.rc)


if __name__ == "__main__":
    unittest.main()

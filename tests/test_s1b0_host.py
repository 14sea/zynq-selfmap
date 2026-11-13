"""The host side of stage 2 (S1b.0): its judge, and the run script driving it through the pretend U-Boot."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1b0_judge  # noqa: E402
from test_prober_s1b0 import Run, params  # noqa: E402
import test_s1a_run as fake  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
PLANNED = params()
HDR, REC, FARBLK, DATA = 64, 480, 68, 76
HONEST = ("the run did not complete", "anomalous read(s)", "the run stopped at", "differs from the known frame",
          "do not follow one rule")                          # the last: a flipped FAR value on a reference read is a real observation


def judge(words, planned=None):
    return s1b0_judge.judge(words, KNOWN, PLANNED if planned is None else planned)


def at(record: int, field: int) -> int:
    return HDR + record * REC + field


class Judge(unittest.TestCase):
    def test_a_clean_run_passes_and_names_the_rule_the_register_followed(self) -> None:
        for rule, name in (("next", "next:"), ("skip", "next but one:")):
            with self.subTest(rule):
                v = judge(Run(rule=rule).words)
                self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
                self.assertTrue(v["far_rule"].startswith(name))
                self.assertEqual(len(v["records"]), 11)

    def test_for_every_fault_the_judge_rederives_what_the_prober_reported(self) -> None:
        faults = ["ctrl", "lpbk", "nodone", "dcache", "stale", "err@1", "err@3", "err@4", "err@6", "err@7", "err@8", "err@9", "err@10",
                  "timeout@7", "timeout@8", "timeout@9", "drop@6", "drop@8", "drop@9", "dropafter@7", "dropafter@10", "short@2", "padnz@3",
                  "flip@5", "flip3@7", "flip3@4", "farflip@5", "farshort@3", "short@2,flip@3", "short@2,farflip@3", "farflip@11", "flip@11", "farshort@1", "short@1"]
        for rule in ("next", "skip"):
            for fault in faults:
                with self.subTest(rule=rule, fault=fault):
                    run = Run(fault, rule=rule, poll_limit=40)
                    v = judge(run.words, run.params)
                    self.assertEqual(v["verdict"], "FAIL")
                    self.assertEqual([p for p in v["problems"] if not any(h in p for h in HONEST)], [])
        for name, over in (("budget", {"budget": 0}), ("bad parameters", {"repeats": 9})):
            with self.subTest(name):
                run = Run("short@2", **over)
                v = judge(run.words, run.params)
                self.assertEqual((v["verdict"], [p for p in v["problems"] if not any(h in p for h in HONEST + ("bad parameters",))]), ("FAIL", []))

    def test_the_far_register_must_follow_one_rule(self) -> None:
        words = list(Run().words)
        for i in (1, 4, 7):                                  # every run of operation 0 says "next but one"; the others say "next"
            words[at(i, FARBLK + 4)] += 1
        v = judge(words)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("do not follow one rule" in p for p in v["problems"]), v["problems"])
        self.assertNotIn("far_rule", v)
        words = list(Run().words)
        for i in range(11):                                  # consistent, but two beyond: neither rule
            words[at(i, FARBLK + 4)] += 2
        self.assertTrue(any("do not follow one rule" in p for p in judge(words)["problems"]))

    def test_every_frame_of_a_multi_frame_read_is_compared_with_its_known_frame(self) -> None:
        for frame in (0, 1, 2):
            with self.subTest(frame=frame):
                words = list(Run().words)
                for i in (3, 6, 9):                          # the three runs of the three-frame read
                    words[at(i, DATA + 101 * (frame + 1) + 40)] ^= 8
                v = judge(words)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any(f"frame {frame} (FAR {0xB98 + frame:#010x}) read cleanly but differs" in p for p in v["problems"]), v["problems"])

    def test_a_run_that_was_not_the_planned_one_fails(self) -> None:
        for name, over in (("one operation", {"ops": [(0xB98, 1)]}), ("one frame instead of three", {"ops": [(0xB98, 1), (0xB99, 1), (0xB98, 1)]}),
                           ("fewer repeats", {"repeats": 1}), ("another envelope", {"lo": 0xB97}), ("another reference", {"ref": 0xB98})):
            with self.subTest(name):
                run = Run(**over)
                self.assertEqual(judge(run.words, run.params)["verdict"], "PASS", "sanity: consistent with its own parameters")
                v = judge(run.words)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any("not the planned ones" in p for p in v["problems"]))

    def test_tampered_buffers_fail(self) -> None:
        clean = Run().words
        cases = {
            "two operations swapped": lambda w: w.__setitem__(slice(at(1, 0), at(3, 0)), w[at(2, 0):at(3, 0)] + w[at(1, 0):at(2, 0)]),
            "a wrong operation index": lambda w: w.__setitem__(at(4, 15), 1),
            "a wrong frame count": lambda w: w.__setitem__(at(1, 14), 2),
            "a nonzero tail after a one-frame read": lambda w: w.__setitem__(at(1, DATA + 300), 1),
            "a FAR value changed on one repeat": lambda w: w.__setitem__(at(4, FARBLK + 4), w[at(4, FARBLK + 4)] ^ 4),
            "an unread flag under a clean code": lambda w: w.__setitem__(at(2, FARBLK + 5), 1),
            "a sentinel as the FAR value under a clean code": lambda w: w.__setitem__(at(2, FARBLK + 4), 0xA5A55A5A),
            "an error bit on the FAR read under a clean code": lambda w: w.__setitem__(at(5, FARBLK + 2), w[at(5, FARBLK + 2)] | 0x00040000),
            "a FAR command that never finished under a clean code": lambda w: w.__setitem__(at(5, FARBLK + 0), 0x4),
            "a FAR read stream reading another register": lambda w: w.__setitem__(at(3, 16 + 43 + 1), 0x2800E001),
            "a FAR read stream with no read in it": lambda w: w.__setitem__(at(3, 16 + 43 + 1), 0x20000000),
            "a frame stream with another length": lambda w: w.__setitem__(at(3, 16 + 10), 0x48000000 | 303),
            "a cleanup without DESYNC": lambda w: w.__setitem__(at(2, 16 + 43 + 4 + 2), 0),
            "a nonzero pad under a clean code": lambda w: w.__setitem__(at(2, DATA + 7), 0x100),
            "a sentinel word in the third frame under a clean code": lambda w: w.__setitem__(at(3, DATA + 350), 0xA5A55A5A),
            "a differing third frame on a repeat under a clean code": lambda w: w.__setitem__(at(6, DATA + 380), w[at(6, DATA + 380)] ^ 2),
            "the header says one anomaly": lambda w: w.__setitem__(4, 1),
            "a gate reading that fails": lambda w: w.__setitem__(12, 0x08C5187D),
            "the final flag cleared": lambda w: w.__setitem__(at(10, 10), 0),
            "a reserved word of the FAR block": lambda w: w.__setitem__(at(6, FARBLK + 7), 1),
            "the baseline FAR value changed alone": lambda w: w.__setitem__(at(0, FARBLK + 4), w[at(0, FARBLK + 4)] + 1),
        }
        for name, change in cases.items():
            with self.subTest(name):
                words = list(clean); change(words)
                self.assertEqual(judge(words)["verdict"], "FAIL")

    def test_cut_short_relabelled_or_foreign_buffers(self) -> None:
        words = list(Run().words); del words[at(10, 0):]; words[3] -= 1; words[5] -= REC
        self.assertTrue(any("is missing" in p for p in judge(words)["problems"]))
        words = list(Run("stale").words); words[2] = 1
        self.assertTrue(any("the records imply" in p for p in judge(words)["problems"]))
        self.assertEqual(judge(Run().words + [0])["verdict"], "INVALID")
        sys.path.insert(0, str(ROOT / "tests"))
        from test_prober_twin import Run as Run1
        self.assertEqual(judge(Run1().words)["verdict"], "INVALID", "a stage-1 result is not a stage-2 result")

    def test_the_console_line_and_return_code_the_judge_predicts_are_the_prober_s(self) -> None:
        for fault in ("", "short@2", "err@7", "dcache", "farflip@5"):
            with self.subTest(fault or "clean"):
                r = Run(fault)
                v = judge(r.words, r.params)
                self.assertEqual("\r\n".join(v["expected_console"]) + "\r\n", r.uart)
                self.assertEqual(int(v["expected_return_code"], 16), r.rc)


class ThroughTheRunScript(unittest.TestCase):
    def test_a_clean_run_passes_under_either_rule_and_everything_is_saved(self) -> None:
        for rule in ("next", "skip"):
            with self.subTest(rule):
                rec, u, out = fake.run(stage="s1b0", far_rule=rule)
                self.assertEqual((rec["verdict"], rec["problems"], rec["stage"]), ("PASS", [], "s1b0"))
                self.assertEqual(rec["result_words"], 64 + 11 * 480)
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertTrue(rec["card_verified"])
                self.assertIn("far_rule", json.loads((out / "verdict.json").read_text()))

    def test_anomalies_and_stops_are_saved_whole_and_fail(self) -> None:
        for fault, records in (("short@2", 12), ("farflip@5", 12), ("farshort@3", 12), ("err@8", 2), ("stale", 1)):
            with self.subTest(fault):
                rec, u, out = fake.run(fault, stage="s1b0")
                self.assertEqual((rec["result_words"], rec["verdict"], rec.get("stop")), (64 + records * 480, "FAIL", None))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_a_valid_result_of_the_other_stage_is_saved_whole_and_fails(self) -> None:
        """The parameter block is replaced after its crc32 check, so the prober runs the other stage, cleanly. Whatever
        was asked for, a result that is consistent in itself is archived complete; that it is the wrong one is the verdict."""
        exp1 = json.loads(fake.s1a_run.EXPECTED.read_text())
        exp2 = json.loads(fake.s1a_run.STAGES["s1b0"]["expected"].read_text())
        for asked, got, exp_other, words in (("s1b0", "s1a", exp1, 64 + 11 * 266), ("s1a", "s1b0", exp2, 64 + 11 * 480)):
            with self.subTest(asked=asked, got=got):
                rec, u, out = fake.run(stage=asked, params_swapped_before_go={i: int(w, 16) for i, w in enumerate(exp_other["params"])})
                self.assertEqual((rec["result_words"], rec["result_layout"], rec.get("stop")), (words, got, None))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertEqual(u.card["s0000001.bin"], u.twin_result)
                self.assertTrue(rec["card_verified"])
                self.assertEqual((rec["verdict"], rec["judge"]), ("FAIL", "INVALID"))
                self.assertTrue(any(f"layout of stage {got}" in p for p in rec["problems"]))

    def test_a_header_that_fits_no_layout_gets_everything_a_result_could_occupy_saved(self) -> None:
        rec, u, out = fake.run(stage="s1b0", header_words_after_go={6: 300})
        self.assertEqual((rec["result_layout"], rec["result_words"]), (None, fake.s1a_run.MAX_RESULT_WORDS))
        saved = (out / "result.bin").read_bytes()
        self.assertEqual(len(saved), 4 * fake.s1a_run.MAX_RESULT_WORDS)
        self.assertEqual(saved[28:len(u.twin_result)], u.twin_result[28:], "everything the prober wrote is in it")
        self.assertEqual((rec["verdict"], rec.get("stop")), ("FAIL", None))
        self.assertTrue(any("fit no known layout" in p for p in rec["problems"]))

    def test_the_dry_run_of_stage_two_differs_from_stage_one_only_in_parameters_and_sizes(self) -> None:
        import subprocess
        def plan(stage):
            out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--dry-run"], capture_output=True, text=True, check=True).stdout
            return [line.split("#")[0].split(".", 1)[1].strip() for line in out.splitlines() if "#" in line and line.strip()[0].isdigit()]
        a, b = plan("s1a"), plan("s1b0")
        strip = lambda cmds: [c for c in cmds if not c.startswith(("mw.l 101000", "crc32 10100000"))]
        self.assertEqual([c.replace("266", "480") for c in strip(a)], strip(b))


if __name__ == "__main__":
    unittest.main()

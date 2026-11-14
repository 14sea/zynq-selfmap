"""The host side of stage 3 (S1b.0b): its judge, and the run script driving it through the pretend U-Boot."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1b0_judge  # noqa: E402
import s1b0b_judge  # noqa: E402
from test_prober_s1b0 import Run as Run2  # noqa: E402
from test_prober_s1b0b import N_RECORDS, NONE, OPS, Run  # noqa: E402
import test_s1a_run as fake  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
PLANNED = Run().params
HDR, REC, FARBLK, DATA = 64, 480, 68, 76
HONEST = ("the run did not complete", "anomalous read(s)", "the run stopped at", "differs from the known frame",
          "is not the same every time")                      # the last: a flipped FAR value on a reference read is a real observation
STEPS = {"next": {"0": [0], "101": [0], "202": [1], "303": [2]},
         "skip": {"0": [0], "101": [1], "202": [2], "303": [3]},
         "skipdata": {"0": [0], "101": [0], "202": [2], "303": [3]}}


def _pad_only_reads() -> list[int]:
    """The frame-read numbers of the pad-only reads when each of them is anomalous (a health read follows each)."""
    reads, k = [], 1
    for _ in range(3):
        for _far, n in OPS:
            if n == NONE:
                continue
            k += 1
            if n == 0:
                reads.append(k); k += 1
    return reads


PAD_FAULT = ",".join(f"padnz@{x}" for x in _pad_only_reads())      # every pad-only read has a nonzero pad word


def judge(words, planned=None):
    return s1b0b_judge.judge(words, KNOWN, PLANNED if planned is None else planned)


def at(record: int, field: int) -> int:
    return HDR + record * REC + field


def target(op: int, repeat: int) -> int:
    """The record of operation `op` in repeat `repeat` of a clean run."""
    return 1 + len(OPS) * repeat + op


class Judge(unittest.TestCase):
    def test_a_clean_run_passes_whatever_the_register_did_and_says_what_it_did(self) -> None:
        for rule, steps in STEPS.items():
            with self.subTest(rule):
                v = judge(Run(rule=rule).words)
                self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
                self.assertEqual(v["steps_by_words"], steps)
                self.assertEqual(v["one_step_per_frame_of_words"], rule == "skip")
                self.assertEqual(len(v["records"]), N_RECORDS)
                self.assertNotIn("far_rule", v)
                table = {(row["far"], row["read"]): row for row in v["far_after"]}
                self.assertEqual(len(table), 8, "eight distinct reads: the reference read, and seven of the eight operations (one is made twice)")
                self.assertEqual(table[("0x00000b98", "the pad alone")]["records"], sorted(target(op, r) for op in (1, 7) for r in range(3)),
                                 "the same read made at two places in the sequence is one row")
                self.assertEqual(table[("0x00000b99", "no read")]["step"], 0)

    def test_for_every_fault_the_judge_rederives_what_the_prober_reported(self) -> None:
        faults = ["ctrl", "lpbk", "nodone", "dcache", "stale", "err@1", "err@4", "err@6", "err@11", "err@12", "err@13", "err@14", "err@15",
                  "err@16", "err@17", "err@18", "err@19", "timeout@12", "timeout@17", "timeout@18", "drop@16", "drop@18", "dropafter@16", "dropafter@19",
                  "short@2", "short@3", "padnz@3", "flip@2", "farflip@12", "farflip@10", "farshort@3", "farshort@4", "short@3,flip@4", "short@3,farflip@4",
                  "farflip@26", "flip@20", "farshort@1", "short@1"]   # 26 FAR reads and 20 frame reads in a clean run: the last of each is the final reference read
        for rule in STEPS:
            for fault in faults:
                with self.subTest(rule=rule, fault=fault):
                    run = Run(fault, rule=rule, poll_limit=40)
                    v = judge(run.words, run.params)
                    self.assertEqual(v["verdict"], "FAIL")
                    self.assertEqual([p for p in v["problems"] if not any(h in p for h in HONEST)], [])
        for name, over in (("budget", {"budget": 0}), ("bad parameters", {"repeats": 9})):
            with self.subTest(name):
                run = Run("short@3", **over)
                v = judge(run.words, run.params)
                self.assertEqual((v["verdict"], [p for p in v["problems"] if not any(h in p for h in HONEST + ("bad parameters",))]), ("FAIL", []))

    def test_the_same_read_at_the_same_address_must_always_leave_the_same_value(self) -> None:
        """Operations 1 and 7 are both the pad alone at 0xb98, at different places in the sequence. The prober compares
        an operation only with its own repeats; that the two agree with each other is for the judge."""
        words = list(Run(rule="skip").words)
        for r in range(3):
            words[at(target(7, r), FARBLK + 4)] += 1
        v = judge(words)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("the FAR value after the pad alone at 0x00000b98 is not the same every time" in p for p in v["problems"]), v["problems"])
        self.assertEqual(sorted(row["far_read_back"] for row in v["far_after"] if (row["far"], row["read"]) == ("0x00000b98", "the pad alone")),
                         ["0x00000b99", "0x00000b9a"], "both values are in the table")
        words = list(Run(rule="skip").words)                 # the reference read against a target read of the same kind: op 0 is not at REF, so change REF's twin
        words[at(0, FARBLK + 4)] += 1; words[at(N_RECORDS - 1, FARBLK + 4)] += 1
        self.assertEqual(judge(words)["verdict"], "PASS", "baseline and final agree with each other and no target read is one frame at the reference address")

    def test_how_the_value_depends_on_the_length_is_reported_not_required(self) -> None:
        words = list(Run(rule="skip").words)
        for r in range(3):                                   # the two-frame read leaves the register somewhere unexpected, every time
            words[at(target(4, r), FARBLK + 4)] += 5
        v = judge(words)
        self.assertEqual((v["verdict"], v["one_step_per_frame_of_words"], v["steps_by_words"]["303"]), ("PASS", False, [8]))

    def test_a_far_value_is_a_measurement_even_in_a_record_that_is_anomalous_for_another_reason(self) -> None:
        """Found in review: with every pad-only read anomalous (a pad that is not zero) under the rule where the pad
        does not move the register, all twelve FAR reads succeeded and none had moved — and the table had no 101-word
        row at all, with the length rule reported as holding. The finding has to be drawn from every value read."""
        v = judge(Run(PAD_FAULT, rule="skipdata").words)
        self.assertEqual((v["verdict"], v["steps_by_words"]["101"], v["one_step_per_frame_of_words"]), ("FAIL", [0], False))
        rows = [row for row in v["far_after"] if row["words"] == 101]
        self.assertEqual([(row["far"], row["far_read_back"]) for row in rows],
                         [("0x00000b98", "0x00000b98"), ("0x00000b99", "0x00000b99"), ("0x00000b9a", "0x00000b9a")])
        self.assertEqual(sum(len(row["records"]) for row in rows), 12)
        for row in rows:
            self.assertEqual(set(row["records_with_another_anomaly"].values()), {"0x11"}, "and the table says what else was wrong with them")
            self.assertEqual(sorted(int(k) for k in row["records_with_another_anomaly"]), row["records"])
        clean = judge(Run(rule="skipdata").words)
        self.assertEqual([row["records_with_another_anomaly"] for row in clean["far_after"]], [{}] * 8)

    def test_the_length_rule_has_three_answers(self) -> None:
        """Holds / does not hold / undetermined. One value that does not fit is enough for "does not hold", wherever it
        came from; "holds" needs, for every read the plan asked for, a value from a record with nothing else wrong."""
        v = judge(Run(rule="skip").words)
        self.assertEqual((v["one_step_per_frame_of_words"], v["reads_without_a_clean_far_value"]), (True, []))
        v = judge(Run(PAD_FAULT, rule="skip").words)         # every value fits, but the pad-only ones all come from anomalous records
        self.assertEqual((v["verdict"], v["steps_by_words"]["101"]), ("FAIL", [1]))
        self.assertIsNone(v["one_step_per_frame_of_words"])
        self.assertEqual(v["reads_without_a_clean_far_value"], [[f"{far:#010x}", "the pad alone"] for far in (0xB98, 0xB99, 0xB9A)])
        v = judge(Run("padnz@3", rule="skip").words)         # one anomalous pad-only read; its two repeats are clean
        self.assertEqual((v["verdict"], v["one_step_per_frame_of_words"], v["reads_without_a_clean_far_value"]), ("FAIL", True, []))
        v = judge(Run(PAD_FAULT, rule="next").words)
        self.assertIs(v["one_step_per_frame_of_words"], False, "a contradiction is not softened to undetermined by missing clean values")
        cut = Run("err@12", rule="skip", poll_limit=30)      # stops in the first pad-only read: most planned reads were never made
        v = judge(cut.words, cut.params)
        self.assertIsNone(v["one_step_per_frame_of_words"])
        self.assertEqual(len(v["reads_without_a_clean_far_value"]), 6)

    def test_a_far_value_that_differs_in_an_anomalous_record_is_in_the_table(self) -> None:
        v = judge(Run("farflip@12", rule="skip").words)      # the second run of "no read at 0xb98": the prober's code is 0x13
        self.assertEqual(v["records"][11]["code"], "0x13")
        rows = [row for row in v["far_after"] if (row["far"], row["read"]) == ("0x00000b98", "no read")]
        self.assertEqual([(row["far_read_back"], row["records"], row["records_with_another_anomaly"]) for row in rows],
                         [("0x00000b98", [3, 20], {}), ("0x00000b9c", [11], {"11": "0x13"})])   # 20, not 19: a health read follows record 11
        self.assertTrue(any("after no read at 0x00000b98 is not the same every time" in p for p in v["problems"]))
        self.assertIs(v["one_step_per_frame_of_words"], False)

    def test_a_far_read_that_failed_measures_nothing(self) -> None:
        v = judge(Run("farshort@4", rule="skip").words)      # record 3, "no read at 0xb98": the FAR read delivered nothing
        self.assertEqual(v["records"][3]["code"], "0x14")
        self.assertFalse([row for row in v["far_after"] if 3 in row["records"] or row["far_read_back"] == "0xa5a55a5a"])
        self.assertEqual((v["verdict"], v["one_step_per_frame_of_words"]), ("FAIL", True), "its two repeats are clean and cover the read")
        for fault in ("err@17", "err@18", "timeout@18"):     # the FAR command or the FAR read of record 3 fails: an interface stop
            with self.subTest(fault):
                run = Run(fault, rule="skip", poll_limit=30)
                v = judge(run.words, run.params)
                self.assertFalse([row for row in v["far_after"] if 3 in row["records"]])

    def test_every_frame_of_the_two_frame_read_is_compared_with_its_known_frame(self) -> None:
        for frame in (0, 1):
            with self.subTest(frame=frame):
                words = list(Run().words)
                for r in range(3):
                    words[at(target(4, r), DATA + 101 * (frame + 1) + 40)] ^= 8
                v = judge(words)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any(f"frame {frame} (FAR {0xB98 + frame:#010x}) read cleanly but differs" in p for p in v["problems"]), v["problems"])

    def test_a_run_that_was_not_the_planned_one_fails(self) -> None:
        for name, over in (("one operation", {"ops": [(0xB98, 0)]}), ("a frame where the pad alone was planned", {"ops": [(far, 1 if k == 1 else n) for k, (far, n) in enumerate(OPS)]}),
                           ("the pad where no read was planned", {"ops": [(far, 0 if k == 2 else n) for k, (far, n) in enumerate(OPS)]}),
                           ("fewer repeats", {"repeats": 1}), ("another budget", {"budget": 4}), ("another reference", {"ref": 0xB98})):
            with self.subTest(name):
                run = Run(**over)
                self.assertEqual(judge(run.words, run.params)["verdict"], "PASS", "sanity: consistent with its own parameters")
                v = judge(run.words)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any("not the planned ones" in p for p in v["problems"]))

    def test_tampered_buffers_fail(self) -> None:
        clean = Run(rule="skip").words
        none, pad, two = target(2, 0), target(1, 0), target(4, 0)
        cases = {
            "a read status in an operation that reads nothing": lambda w: w.__setitem__(at(none, 5), 0x50033004),
            "read polls in an operation that reads nothing": lambda w: w.__setitem__(at(none, 6), 2),
            "a data word in an operation that reads nothing": lambda w: w.__setitem__(at(none, DATA + 3), 1),
            "a word after the pad of a pad-only read": lambda w: w.__setitem__(at(pad, DATA + 101), 1),
            "a nonzero pad word under a clean code": lambda w: w.__setitem__(at(pad, DATA + 7), 0x100),
            "a sentinel in the pad under a clean code": lambda w: w.__setitem__(at(pad, DATA + 50), 0xA5A55A5A),
            "no read relabelled as the pad alone": lambda w: w.__setitem__(at(none, 14), 0),
            "the pad alone relabelled as no read": lambda w: w.__setitem__(at(pad, 14), NONE),
            "a count the stage does not have": lambda w: w.__setitem__(at(pad, 14), 7),
            "a read in the stream of an operation that reads nothing": lambda w: w.__setitem__(slice(at(none, 16 + 9), at(none, 16 + 11)), [0x28006000, 0x48000065]),
            "no read in the stream of a pad-only operation": lambda w: w.__setitem__(slice(at(pad, 16 + 9), at(pad, 16 + 11)), [0x20000000, 0x20000000]),
            "a pad-only stream asking for a frame as well": lambda w: w.__setitem__(at(pad, 16 + 10), 0x48000000 | 202),
            "a FAR value changed on one repeat": lambda w: w.__setitem__(at(target(2, 1), FARBLK + 4), w[at(target(2, 1), FARBLK + 4)] ^ 4),
            "an unread flag under a clean code": lambda w: w.__setitem__(at(none, FARBLK + 5), 1),
            "a FAR command that never finished under a clean code": lambda w: w.__setitem__(at(none, FARBLK + 0), 0x4),
            "a differing second frame on a repeat under a clean code": lambda w: w.__setitem__(at(target(4, 1), DATA + 250), w[at(target(4, 1), DATA + 250)] ^ 2),
            "a word after the two frames": lambda w: w.__setitem__(at(two, DATA + 303), 1),
            "two operations swapped": lambda w: w.__setitem__(slice(at(1, 0), at(3, 0)), w[at(2, 0):at(3, 0)] + w[at(1, 0):at(2, 0)]),
            "the header says one anomaly": lambda w: w.__setitem__(4, 1),
            "the stage in the echoed parameters": lambda w: w.__setitem__(32 + 2, 2),
        }
        for name, change in cases.items():
            with self.subTest(name):
                words = list(clean); change(words)
                self.assertNotEqual(judge(words)["verdict"], "PASS")

    def test_a_result_of_the_other_stage_is_not_this_stage_s(self) -> None:
        two = Run2()
        self.assertEqual(judge(two.words, two.params)["verdict"], "INVALID", "a stage-2 result, even with its own parameters as the plan")
        three = Run()
        self.assertEqual(s1b0_judge.judge(three.words, KNOWN, three.params)["verdict"], "INVALID", "and the reverse")
        self.assertEqual(judge(three.words + [0])["verdict"], "INVALID")
        # relabelled: a stage-3 result whose echoed parameters, and the plan, say stage 2. Stage 2 has no read of the pad
        # alone and none of nothing, so this is not a stage-2 parameter block, whoever agrees that it is
        words, planned = list(three.words), list(three.params)
        words[32 + 2] = planned[2] = 2
        v = s1b0_judge.judge(words, KNOWN, planned)
        self.assertEqual(v["verdict"], "INVALID")
        self.assertTrue(any("not a valid stage-2 parameter block" in p for p in v["problems"]), v["problems"])

    def test_the_console_line_and_return_code_the_judge_predicts_are_the_prober_s(self) -> None:
        for fault in ("", "short@3", "err@17", "dcache", "farflip@12"):
            with self.subTest(fault or "clean"):
                r = Run(fault)
                v = judge(r.words, r.params)
                self.assertEqual("\r\n".join(v["expected_console"]) + "\r\n", r.uart)
                self.assertEqual(int(v["expected_return_code"], 16), r.rc)


class ThroughTheRunScript(unittest.TestCase):
    def test_the_board_parameters_are_the_ones_these_tests_run(self) -> None:
        exp = json.loads(fake.s1a_run.STAGES["s1b0b"]["expected"].read_text())
        board = [int(w, 16) for w in exp["params"]]
        self.assertEqual(board[:9] + board[10:], PLANNED[:9] + PLANNED[10:], "all but the poll limit, which the twin does not need so high")
        self.assertEqual((exp["records"], exp["result_words"]), (N_RECORDS, 64 + N_RECORDS * 480))

    def test_a_clean_run_passes_under_every_rule_and_everything_is_saved(self) -> None:
        for rule in STEPS:
            with self.subTest(rule):
                rec, u, out = fake.run(stage="s1b0b", far_rule=rule)
                self.assertEqual((rec["verdict"], rec["problems"], rec["stage"], rec["result_layout"]), ("PASS", [], "s1b0b", "s1b0b"))
                self.assertEqual(rec["result_words"], 64 + N_RECORDS * 480)
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertTrue(rec["card_verified"])
                self.assertEqual(json.loads((out / "verdict.json").read_text())["steps_by_words"], STEPS[rule])

    def test_anomalies_and_stops_are_saved_whole_and_fail(self) -> None:
        for fault, records in (("padnz@3", N_RECORDS + 1), ("farshort@4", N_RECORDS + 1), ("err@17", 4), ("stale", 1)):
            with self.subTest(fault):
                rec, u, out = fake.run(fault, stage="s1b0b")
                self.assertEqual((rec["result_words"], rec["verdict"], rec.get("stop")), (64 + records * 480, "FAIL", None))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_a_stage_two_result_under_stage_three_is_saved_whole_and_fails_and_the_reverse(self) -> None:
        """The two stages share a record layout, so the size says nothing; the echoed parameters and the console do."""
        e2 = json.loads(fake.s1a_run.STAGES["s1b0"]["expected"].read_text())
        e3 = json.loads(fake.s1a_run.STAGES["s1b0b"]["expected"].read_text())
        for asked, other, records, line in (("s1b0b", e2, 11, "SM2 start"), ("s1b0", e3, N_RECORDS, "SM3 start")):
            with self.subTest(asked=asked):
                rec, u, out = fake.run(stage=asked, params_swapped_before_go={i: int(w, 16) for i, w in enumerate(other["params"])})
                self.assertEqual((rec["result_words"], rec.get("stop")), (64 + records * 480, None))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertTrue(rec["card_verified"])
                self.assertEqual((rec["verdict"], rec["judge"]), ("FAIL", "INVALID"))
                self.assertEqual(rec["console"][0], line, "the console lines of the stage that really ran are in the record")
                self.assertTrue(any("the console showed" in p for p in rec["problems"]))

    def test_the_counting_run_of_the_walk_s_pair_of_reads(self) -> None:
        """64 times the pad alone and then the frame at the same address, on the known frames: stage 3, unchanged."""
        rec, u, out = fake.run(stage="ratep", far_rule="skip")
        self.assertEqual((rec["verdict"], rec["problems"], rec["result_words"]), ("PASS", [], 64 + 130 * 480))
        v = json.loads((out / "verdict.json").read_text())
        target = [(r["far"], r["words"]) for r in v["records"][1:-1]]
        self.assertEqual(target[:6], [("0x00000b98", 101), ("0x00000b98", 202), ("0x00000b99", 101), ("0x00000b99", 202), ("0x00000b9a", 101), ("0x00000b9a", 202)])
        self.assertEqual(sum(1 for a, b in zip(target[::2], target[1::2]) if a[0] == b[0] and (a[1], b[1]) == (101, 202)), 64)
        self.assertIs(v["one_step_per_frame_of_words"], True)
        rec, u, out = fake.run("err@52", stage="ratep", far_rule="skip")
        self.assertEqual((rec["verdict"], rec["result_words"], rec.get("stop")), ("FAIL", 64 + 11 * 480, None))

    def test_the_same_pairs_at_the_walk_s_first_addresses_run_through_and_are_failed_only_for_having_no_known_answer(self) -> None:
        rec, u, out = fake.run(stage="ratew", far_rule="skip")
        v = json.loads((out / "verdict.json").read_text())
        self.assertEqual((v["header"]["status"], len(v["records"]), rec["result_words"]), ("0x1", 130, 64 + 130 * 480))
        self.assertEqual({r["far"] for r in v["records"][1:-1]}, {f"{a:#010x}" for a in range(0xB80, 0xB88)})
        self.assertEqual((rec["verdict"], [p for p in v["problems"] if "no known answer" not in p]), ("FAIL", []))

    def test_the_dry_run_differs_from_stage_two_s_only_in_the_parameters(self) -> None:
        def plan(stage):
            out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--dry-run"], capture_output=True, text=True, check=True).stdout
            return [line.split("#")[0].split(".", 1)[1].strip() for line in out.splitlines() if "#" in line and line.strip()[0].isdigit()]
        a, b = plan("s1b0"), plan("s1b0b")
        strip = lambda cmds: [c for c in cmds if not c.startswith(("mw.l 101000", "crc32 10100000"))]  # noqa: E731
        self.assertEqual(strip(a), strip(b))
        self.assertIn("mw.l 10100008 00000003 1", b)
        self.assertIn("mw.l 10100028 0f020f01 1", b, "the eight frame counts: 1, pad, none, pad, 2, pad, none, pad")


if __name__ == "__main__":
    unittest.main()

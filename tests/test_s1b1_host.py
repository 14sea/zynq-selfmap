"""The host side of stage 4 (S1b.1): its judge, and the run script driving it through the pretend U-Boot."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1b0b_judge  # noqa: E402
import s1b1_judge  # noqa: E402
from test_prober_s1b0b import Run as Run3  # noqa: E402
from test_prober_s1b1 import COLUMN, H_WALK, Run, column, frames_for, schedule  # noqa: E402
import test_s1a_run as fake  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
PLANNED = Run().params
HDR, REC, FARBLK, DATA = 64, 480, 68, 76
HONEST = ("the run did not complete", "anomalous read(s)", "the run stopped at", "differs from the known frame", "but the device names")
SCHEDULE = schedule(COLUMN)


def judge(words, planned=None):
    return s1b1_judge.judge(words, KNOWN, PLANNED if planned is None else planned)


def at(record: int, field: int) -> int:
    return HDR + record * REC + field


def record_of(op: int, far: int, p: int) -> int:
    """The record of this read at this address in this pass of a clean run of the default column."""
    return next(i for i, (_k, f, _m, o, q) in enumerate(SCHEDULE) if (f, o, q) == (far, op, p))


class Judge(unittest.TestCase):
    def test_a_clean_run_passes_and_says_what_the_walk_found(self) -> None:
        v = judge(Run().words)
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(v["frames_walked"], 36)
        self.assertEqual(v["passes"], [{"frames": 36, "ended": "the device named an address outside the envelope", "last_address_named": "0x00000c00"}] * 2)
        self.assertEqual([(s["far"], s["next"]) for s in v["walk"]], [(f"{a:#010x}", f"{b:#010x}") for a, b in zip(COLUMN, COLUMN[1:] + [0xC00])])
        self.assertEqual((v["known_frames_not_reached"], v["reads_at_addresses_without_a_known_answer"], v["register_cross_checks"]), ([], 33, 70))
        self.assertEqual(len(v["records"]), 162)

    def test_the_judge_has_no_frame_count_of_its_own(self) -> None:
        for n in (1, 2, 3, 4, 17, 48):
            with self.subTest(n=n):
                r = Run(succ=column(n), frames=frames_for(range(0xB80, 0xB80 + n)), ref=0xB80)
                v = judge(r.words, r.params)
                self.assertEqual(v["frames_walked"], n)
                # a column too short to hold the known frames fails for that reason and for no other
                self.assertEqual([p for p in v["problems"] if "without passing the known frame" not in p], [])
                self.assertEqual(v["verdict"], "PASS" if n > 0x1A else "FAIL")

    def test_a_walk_that_ends_at_the_limit_is_a_sound_measurement_and_says_so(self) -> None:
        r = Run(succ={}, frames=frames_for(range(0xB80, 0xC00)))
        v = judge(r.words)
        self.assertEqual((v["verdict"], v["frames_walked"], v["passes"][0]["ended"], v["passes"][0]["last_address_named"]),
                         ("PASS", 64, "the limit of frames was reached", "0x00000bc0"))
        r = Run(limit=5)
        v = judge(r.words, r.params)
        self.assertEqual((v["verdict"], v["known_frames_not_reached"]), ("PASS", ["0x00000b98", "0x00000b99", "0x00000b9a"]), "not reached, and not expected to be")

    def test_a_walk_that_leaves_the_envelope_without_passing_the_known_frames_fails(self) -> None:
        r = Run(start=0xB9B)
        v = judge(r.words, r.params)
        self.assertEqual((v["verdict"], v["frames_walked"]), ("FAIL", 9))
        self.assertTrue(any("without passing the known frame(s) 0x00000b98, 0x00000b99, 0x00000b9a" in p for p in v["problems"]))

    def test_a_column_end_inside_the_envelope_is_reported_as_walked(self) -> None:
        addresses = [0xB80, 0xB81, 0xB82, 0xB83, 0xBF0, 0xBF1]
        r = Run(succ={0xB83: 0xBF0, 0xBF1: 0x1000}, frames=frames_for(addresses + [0xB99]))
        v = judge(r.words)
        self.assertEqual([s["far"] for s in v["walk"]], [f"{a:#010x}" for a in addresses])
        self.assertEqual([p for p in v["problems"] if "without passing the known frame" not in p], [])

    def test_for_every_fault_and_shape_the_judge_rederives_what_the_prober_reported(self) -> None:
        faults = ["ctrl", "lpbk", "nodone", "dcache", "stale", "err@1", "err@4", "short@1", "farshort@1", "err@6", "err@9", "timeout@12", "drop@14", "dropafter@10",
                  "padnz@2", "short@3", "farshort@2", "farshort@7", "flip@77", "farflip@77", "farflip@76", "flip3@150", "flip@155", "err@381", "err@747",
                  "flip@34", "padnz@2,flip@3", "flip@162", "farflip@162", "short@150", "farshort@151", "padnz@40"]
        for fault in faults:
            with self.subTest(fault=fault):
                run = Run(fault, poll_limit=40)
                v = judge(run.words, run.params)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertEqual([p for p in v["problems"] if not any(h in p for h in HONEST)], [])
        for name, kw in (("names itself", {"succ": {0xB85: 0xB85}}), ("a step back", {"succ": {0xB85: 0xB82}}), ("rule next", {"rule": "next"}),
                         ("rule skipdata", {"rule": "skipdata"}), ("bad parameters", {"passes": 3})):
            with self.subTest(name):
                run = Run(**kw)
                v = judge(run.words, run.params)
                self.assertEqual((v["verdict"], [p for p in v["problems"] if not any(h in p for h in HONEST + ("bad parameters",))]), ("FAIL", []))

    def test_a_run_that_was_not_the_planned_one_fails(self) -> None:
        for name, over in (("one pass", {"passes": 1}), ("another limit", {"limit": 40}), ("another start", {"start": 0xB81}),
                           ("the reference less often", {"every": 32}), ("another envelope", {"hi": 0xBFE})):
            with self.subTest(name):
                run = Run(**over)
                self.assertEqual(judge(run.words, run.params)["verdict"], "PASS", "sanity: consistent with its own parameters")
                v = judge(run.words)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(any("not the planned ones" in p for p in v["problems"]))

    def test_tampered_buffers_fail(self) -> None:
        clean = Run().words
        s0, c0 = record_of(0, 0xB85, 0), record_of(1, 0xB85, 0)
        s1, c1 = record_of(0, 0xB85, 1), record_of(1, 0xB85, 1)
        t1 = record_of(2, 0xB83, 2)

        def both(field: int, change):
            def apply(w):
                for rec in (c0, c1):
                    w[at(rec, field)] = change(w[at(rec, field)])
            return apply
        cases = {
            "the address named in pass 1 alone": lambda w: w.__setitem__(at(s1, FARBLK + 4), w[at(s1, FARBLK + 4)] + 1),
            "a frame word in pass 1 alone": lambda w: w.__setitem__(at(c1, DATA + 140), w[at(c1, DATA + 140)] ^ 1),
            "the register after the frame, in pass 1 alone": lambda w: w.__setitem__(at(c1, FARBLK + 4), w[at(c1, FARBLK + 4)] + 1),
            "the register after the frame, in both passes": both(FARBLK + 4, lambda x: x + 1),
            "a frame word in both passes, the three-frame read left as it was": both(DATA + 140, lambda x: x ^ 1),
            "a frame word of the three-frame read": lambda w: w.__setitem__(at(t1, DATA + 101 * 3 + 9), w[at(t1, DATA + 101 * 3 + 9)] ^ 1),
            "a successor read relabelled as a content read": lambda w: w.__setitem__(at(s0, 15), 1),
            "a record of pass 0 relabelled as pass 1": lambda w: w.__setitem__(at(s0, 12), 1),
            "two frames' records swapped": lambda w: w.__setitem__(slice(at(1, 0), at(5, 0)), w[at(3, 0):at(5, 0)] + w[at(1, 0):at(3, 0)]),
            "a nonzero tail after a successor read": lambda w: w.__setitem__(at(s0, DATA + 101), 1),
            "a nonzero pad word under a clean code": lambda w: w.__setitem__(at(s0, DATA + 7), 0x100),
            "an unread flag under a clean code": lambda w: w.__setitem__(at(s0, FARBLK + 5), 1),
            "an error bit on a FAR read under a clean code": lambda w: w.__setitem__(at(s0, FARBLK + 2), w[at(s0, FARBLK + 2)] | 0x00040000),
            "a successor stream that reads a frame": lambda w: w.__setitem__(at(s0, 16 + 10), 0x48000000 | 202),
            "a stream addressed elsewhere than the record says": lambda w: w.__setitem__(at(c0, 16 + 8), 0xB86),
            "a cleanup without DESYNC": lambda w: w.__setitem__(at(c0, 16 + 43 + 4 + 2), 0),
            "the count of frames in the header": lambda w: w.__setitem__(H_WALK, 35),
            "how pass 1 ended, in the header": lambda w: w.__setitem__(H_WALK + 4, 2),
            "the last address named, in the header": lambda w: w.__setitem__(H_WALK + 2, 0xBA4),
            "a reserved header word": lambda w: w.__setitem__(H_WALK + 6, 1),
            "the header says one anomaly": lambda w: w.__setitem__(4, 1),
            "a gate reading that fails": lambda w: w.__setitem__(12, 0x08C5187D),
            "the final reference flag cleared": lambda w: w.__setitem__(at(161, 10), 0),
            "a reference flag on a walk record": lambda w: w.__setitem__(at(s0, 10), 1),
            "the stage in the echoed parameters": lambda w: w.__setitem__(32 + 2, 3),
            "an unused parameter word": lambda w: w.__setitem__(32 + 20, 5),
        }
        for name, change in cases.items():
            with self.subTest(name):
                words = list(clean); change(words)
                self.assertNotEqual(judge(words)["verdict"], "PASS")

    def test_what_differs_between_the_passes_or_the_paths_is_named_as_such(self) -> None:
        """The same three changes as above, but held to the reason: a judge that fails them only because the schedule
        no longer fits would also fail them when the comparison itself is missing."""
        clean = Run().words
        s1, c1, t1 = record_of(0, 0xB85, 1), record_of(1, 0xB85, 1), record_of(2, 0xB83, 2)
        words = list(clean); words[at(s1, FARBLK + 4)] += 1
        self.assertIn(f"record {s1}: code 0x0, but its raw words say 0x13", judge(words)["problems"])
        words = list(clean); words[at(c1, DATA + 140)] ^= 1
        self.assertIn(f"record {c1}: code 0x0, but its raw words say 0x12", judge(words)["problems"])
        for frame in (0, 1, 2):
            words = list(clean); words[at(t1, DATA + 101 * (frame + 1) + 9)] ^= 1
            self.assertEqual(judge(words)["problems"], [f"record {t1}: code 0x0, but its raw words say 0x12"], f"frame {frame} of the three")

    def test_a_relabelled_result_is_invalid_even_when_the_plan_agrees_with_it(self) -> None:
        for name, index, value in (("another stage", 2, 3), ("a frame count word, which this stage does not have", 10, 1),
                                   ("a second address", 17, 0xB81), ("a word beyond the ones this stage reads", 31, 1)):
            with self.subTest(name):
                words, planned = list(Run().words), list(PLANNED)
                words[32 + index] = planned[index] = value
                v = judge(words, planned)
                self.assertEqual(v["verdict"], "INVALID")
                self.assertIn("the echoed parameters are not a valid stage-4 parameter block", v["problems"])

    def test_a_known_frame_that_differs_is_named(self) -> None:
        frames = frames_for(COLUMN); frames[0xB99] = list(frames[0xB99]); frames[0xB99][40] ^= 8      # consistently wrong, by every path
        v = judge(Run(frames=frames).words)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("the frame at 0x00000b99 read cleanly but differs from the known frame in 1 word(s), first at 40" in p for p in v["problems"]))

    def test_the_register_after_a_frame_must_be_the_address_named_after_the_next_frame(self) -> None:
        words = list(Run().words)
        for p in (0, 1):
            words[at(record_of(1, 0xB85, p), FARBLK + 4)] += 3
        v = judge(words)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("after the frame at 0x00000b85 the register held 0x00000b8a, but the device names 0x00000b87 after 0x00000b86" in p for p in v["problems"]), v["problems"])

    def test_cut_short_relabelled_or_foreign_buffers(self) -> None:
        words = list(Run().words); del words[at(161, 0):]; words[3] -= 1; words[5] -= REC
        self.assertTrue(any("is missing" in p for p in judge(words)["problems"]))
        words = list(Run("padnz@2").words); words[2] = 1
        self.assertTrue(any("the records imply" in p for p in judge(words)["problems"]))
        self.assertEqual(judge(Run().words + [0])["verdict"], "INVALID")
        three = Run3()
        self.assertEqual(judge(three.words, three.params)["verdict"], "INVALID", "a stage-3 result is not a stage-4 result")
        four = Run()
        self.assertEqual(s1b0b_judge.judge(four.words, KNOWN, four.params)["verdict"], "INVALID", "and the reverse")

    def test_the_console_line_and_return_code_the_judge_predicts_are_the_prober_s(self) -> None:
        for kw in ({}, {"fault": "padnz@2"}, {"fault": "err@9"}, {"fault": "dcache"}, {"succ": {0xB85: 0xB85}}, {"passes": 3}):
            with self.subTest(str(kw)):
                r = Run(**kw)
                v = judge(r.words, r.params)
                self.assertEqual("\r\n".join(v["expected_console"]) + "\r\n", r.uart)
                self.assertEqual(int(v["expected_return_code"], 16), r.rc)


MODEL = {"far_rule": "skip", "succ": column(), "frames": frames_for(COLUMN)}


class ThroughTheRunScript(unittest.TestCase):
    def test_the_board_parameters_are_the_ones_these_tests_run(self) -> None:
        exp = json.loads(fake.s1a_run.STAGES["s1b1"]["expected"].read_text())
        board = [int(w, 16) for w in exp["params"]]
        self.assertEqual(board[:9] + board[10:], PLANNED[:9] + PLANNED[10:], "all but the poll limit, which the twin does not need so high")
        self.assertNotIn("records", exp, "how many records there will be is not known before the run")

    def test_a_clean_run_passes_and_everything_is_saved(self) -> None:
        rec, u, out = fake.run(stage="s1b1", **MODEL)
        self.assertEqual((rec["verdict"], rec["problems"], rec["stage"], rec["result_layout"]), ("PASS", [], "s1b1", "s1b1"))
        self.assertEqual(rec["result_words"], 64 + 162 * 480)
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertTrue(rec["card_verified"])
        self.assertEqual(json.loads((out / "verdict.json").read_text())["frames_walked"], 36)

    def test_a_longer_walk_is_saved_whole_whatever_its_size(self) -> None:
        rec, u, out = fake.run(stage="s1b1", far_rule="skip", succ={}, frames=frames_for(range(0xB80, 0xC00)))
        self.assertEqual((rec["verdict"], rec["result_words"]), ("PASS", 64 + 285 * 480))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_stops_are_saved_whole_and_fail(self) -> None:
        for kw, records in (({"fault": "padnz@2"}, 3), ({"fault": "err@9"}, 2), ({"fault": "flip@77"}, 78), ({"succ": {0xB85: 0xB85}}, 13), ({"far_rule": "next"}, 3)):
            with self.subTest(str(kw)):
                rec, u, out = fake.run(kw.get("fault", ""), stage="s1b1", **{**MODEL, **{k: v for k, v in kw.items() if k != "fault"}})
                self.assertEqual((rec["result_words"], rec["verdict"], rec.get("stop")), (64 + records * 480, "FAIL", None))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_a_result_of_another_stage_is_saved_whole_and_fails(self) -> None:
        e3 = json.loads(fake.s1a_run.STAGES["s1b0b"]["expected"].read_text())
        rec, u, out = fake.run(stage="s1b1", params_swapped_before_go={i: int(w, 16) for i, w in enumerate(e3["params"])}, **MODEL)
        self.assertEqual((rec["verdict"], rec["judge"], rec.get("stop"), rec["console"][0]), ("FAIL", "INVALID", None, "SM3 start"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_the_dry_run_differs_from_stage_three_s_only_in_the_parameters(self) -> None:
        def plan(stage):
            out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--dry-run"], capture_output=True, text=True, check=True).stdout
            return [line.split("#")[0].split(".", 1)[1].strip() for line in out.splitlines() if "#" in line and line.strip()[0].isdigit()]
        a, b = plan("s1b0b"), plan("s1b1")
        strip = lambda cmds: [c for c in cmds if not c.startswith(("mw.l 101000", "crc32 10100000"))]  # noqa: E731
        self.assertEqual(strip(a), strip(b))
        for line in ("mw.l 10100008 00000004 1", "mw.l 1010000c 00000b80 1", "mw.l 10100010 00000bff 1", "mw.l 10100030 00000040 1", "mw.l 10100040 00000b80 1"):
            self.assertIn(line, b)


if __name__ == "__main__":
    unittest.main()

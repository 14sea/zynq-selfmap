"""Diagnostics added on 2026-11-14, when the walk overflowed the receive FIFO and stages 2 and 3 did not:
stage 5 (stage 3 with a generated sequence and with more stack beneath each target read), the same extra stack in
stage 4, the address of the polling loop's status word in every record — and the status of a run that a reference
read stopped on the interface."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import dx_judge  # noqa: E402
import s1b0_judge  # noqa: E402
import s1b0b_judge  # noqa: E402
import s1b1_judge  # noqa: E402
from test_prober_s1b0 import Run as Run2  # noqa: E402
from test_prober_s1b0b import Run as Run3  # noqa: E402
from test_prober_s1b1 import COLUMN, Run as Run4, frames_for, schedule  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
HDR, REC, FARBLK = 64, 480, 68
NONE = 15
FRAMES = frames_for(range(0xB80, 0xBA0))


class Run5(Run2):
    """Stage 5 on the twin, over the frames the walk read: by default the generated sequence of the 26 addresses."""
    def __init__(self, fault: str = "", rule: str = "skip", **over) -> None:
        import test_prober_s1b0 as base
        saved = base.FRAMES
        base.FRAMES = FRAMES
        try:
            super().__init__(fault, rule, **{"stage": 5, "lo": 0xB80, "hi": 0xB99, "ref": 0xB99, "ops": [(0xB80, 0)], "seq": 26,
                                              "repeats": 1, "budget": 24, **over})
        finally:
            base.FRAMES = saved

    def rec(self, i: int) -> dict:
        r = self.words[HDR + i * REC: HDR + (i + 1) * REC]
        return {"far": r[0], "kind": r[1], "code": r[2], "n": r[14], "op": r[15], "repeat": r[12], "poll_var": r[FARBLK + 6], "reserved": r[FARBLK + 7]}

    def recs(self) -> list[dict]:
        return [self.rec(i) for i in range(self.n_records)]


def judge5(run) -> dict:
    return dx_judge.judge(run.words, KNOWN, run.params)


class StageFive(unittest.TestCase):
    def test_the_generated_sequence_is_the_pad_alone_then_the_frame_at_each_address(self) -> None:
        r = Run5()
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations, r.n_records), (0, 1, 0, [], 1 + 52 + 1))
        self.assertEqual(r.uart, "SM5 start\r\nSM5 end status=00000001 records=00000036 anomalies=00000000 words=%08x\r\n" % r.total)
        self.assertEqual([(x["kind"], x["far"], x["n"], x["op"]) for x in r.recs()],
                         [(2, 0xB99, 1, 0xFFFFFFFF)] + [(0, 0xB80 + k // 2, k % 2, k) for k in range(52)] + [(3, 0xB99, 1, 0xFFFFFFFF)])
        self.assertEqual({(x["far"], x["n"]) for x in r.recs() if x["kind"] == 0},
                         {(far, n) for _k, far, n, op, p in schedule(COLUMN[:26], passes=1, every=100) if op in (0, 1)}, "the reads of the walk's first pass")
        two = Run5(repeats=2)
        self.assertEqual((two.status, two.n_records), (1, 1 + 104 + 1))

    def test_without_a_sequence_it_is_stage_three(self) -> None:
        ops = [(0xB98, 1), (0xB98, 0), (0xB98, NONE), (0xB99, 0)]
        five = Run5(lo=0xB98, hi=0xB9A, ops=ops, seq=0, repeats=3)
        three = Run3(ops=ops)
        self.assertEqual([(x["kind"], x["far"], x["n"], x["op"], x["repeat"]) for x in five.recs()],
                         [(x["kind"], x["far"], x["n"], x["op"], x["repeat"]) for x in (three.rec(i) for i in range(three.n_records))])
        self.assertEqual(five.status, 1)

    def test_more_stack_moves_the_polling_variable_under_the_target_reads_and_under_nothing_else(self) -> None:
        plain = Run5()
        self.assertEqual(len({x["poll_var"] for x in plain.recs()}), 1, "without it every read is made at one depth")
        for extra in (1, 8, 64):
            with self.subTest(extra=extra):
                r = Run5(extra=extra)
                self.assertEqual((r.status, r.violations, r.n_records), (1, [], 54))
                target = {x["poll_var"] for x in r.recs() if x["kind"] == 0}
                reference = {x["poll_var"] for x in r.recs() if x["kind"] != 0}
                self.assertEqual((len(target), len(reference)), (1, 1))
                shift = (reference.pop() - target.pop()) & 0xFFFFFFFF
                self.assertGreaterEqual(shift, 4 * extra)
                self.assertLess(shift, 4 * extra + 64, "the target reads lie lower by the extra words, give or take a frame")
                self.assertEqual({x["reserved"] for x in r.recs()}, {0})
        self.assertEqual([(x["far"], x["n"], x["code"]) for x in Run5(extra=8).recs()], [(x["far"], x["n"], x["code"]) for x in plain.recs()])

    def test_the_same_in_the_walk(self) -> None:
        plain = Run4()
        deep = Run4(extra=8)
        self.assertEqual((deep.status, deep.walk, deep.n_records), (plain.status, plain.walk, plain.n_records))
        self.assertEqual([(x["kind"], x["far"], x["n"], x["op"], x["repeat"], x["far_value"]) for x in deep.recs()],
                         [(x["kind"], x["far"], x["n"], x["op"], x["repeat"], x["far_value"]) for x in plain.recs()])

        def spots(run):
            out = {}
            for i in range(run.n_records):
                w = run.words[HDR + i * REC: HDR + (i + 1) * REC]
                out.setdefault(w[1] == 0, set()).add(w[FARBLK + 6])
            return out
        # addresses of two runs of the twin cannot be compared (the host places each run's stack afresh); what can
        # be is, within a run, how far the walk's own reads lie beneath its reference reads
        def gap(run):
            s = spots(run)
            self.assertEqual(len(s[True]), 1, "the walk's own reads all lie at one depth")
            baseline = run.words[HDR + FARBLK + 6]           # record 0; the reference reads come by several ways and lie at several
            return (baseline - next(iter(s[True]))) & 0xFFFFFFFF
        self.assertGreaterEqual(gap(deep) - gap(plain), 32, "the walk's own reads moved down by the eight words; its baseline read did not")
        self.assertLess(gap(deep) - gap(plain), 96)
        v = s1b1_judge.judge(deep.words, KNOWN, deep.params)
        self.assertEqual((v["verdict"], v["problems"], v["params"]["extra_stack_words"]), ("PASS", [], 8))

    def test_bad_diagnostic_parameters_touch_no_register(self) -> None:
        for name, over in (("a sequence longer than 32", {"seq": 33, "hi": 0xBFF}), ("more than 64 words of stack", {"extra": 65}),
                           ("a sequence running past the envelope", {"seq": 27}), ("a sequence from outside", {"ops": [(0xB7F, 0)], "seq": 4}),
                           ("a sequence with a table beside it", {"ops": [(0xB80, 0), (0xB81, 0)]}), ("a sequence three times", {"repeats": 3})):
            with self.subTest(name):
                r = Run5(**over)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(r.uart, "SM5 start\r\nSM5 end status=00000500\r\n")
        self.assertEqual(Run4(extra=65).status, 0x500)

    def test_a_sequence_that_would_run_past_the_top_of_the_address_space_is_refused_not_wrapped(self) -> None:
        """Review, 2026-11-15: the addresses are 32-bit sums. With the envelope open to 0xffffffff, three addresses from
        0xfffffffe came out as 0xfffffffe, 0xffffffff, 0 — each inside the envelope — and the run completed."""
        top = {"lo": 0, "hi": 0xFFFFFFFF, "ref": 0xB99, "ops": [(0xFFFFFFFE, 0)]}
        for seq in (3, 4, 32):
            with self.subTest(seq=seq):
                r = Run5(**top, seq=seq)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(dx_judge.judge(r.words, KNOWN, r.params)["verdict"], "FAIL")
        r = Run5(**top, seq=2)                               # ending exactly at the top is inside
        self.assertEqual((r.status, [(x["far"], x["n"]) for x in r.recs() if x["kind"] == 0]),
                         (1, [(0xFFFFFFFE, 0), (0xFFFFFFFE, 1), (0xFFFFFFFF, 0), (0xFFFFFFFF, 1)]))
        self.assertEqual(Run5(lo=0, hi=0xFFFFFFFF, ops=[(0xFFFFFFFF, 0)], seq=2).status, 0x500)
        self.assertEqual(Run5(ops=[(0xB9A, 0)], seq=1).status, 0x500, "a first address above the top")
        for stage, run in ((2, Run2(extra=8)), (3, Run3(extra=8)), (3, Run3(seq=4))):       # the other stages ignore both words...
            with self.subTest(stage=stage):
                self.assertEqual(run.status, 1)
                self.assertEqual(len({run.words[HDR + i * REC + FARBLK + 6] for i in range(run.n_records)}), 1, "...and read at one depth")
                judge = s1b0_judge.judge if stage == 2 else s1b0b_judge.judge
                self.assertEqual(judge(run.words, KNOWN, run.params)["verdict"], "INVALID", "but a plan that sets them for these stages is not a valid one")

    def test_the_judge_follows_stage_five_and_reports_where_the_polling_variable_lay(self) -> None:
        for extra in (0, 8):
            with self.subTest(extra=extra):
                r = Run5(extra=extra)
                v = judge5(r)
                self.assertEqual([p for p in v["problems"] if "no known answer" not in p], [], "failed for the frames without a known answer, and for nothing else")
                self.assertEqual((v["header"]["status"], len(v["records"]), v["params"]["diagnostic"]),
                                 ("0x1", 54, {"generated_sequence_of_addresses": 26, "extra_stack_words": extra, "polling_loop": s1b0_judge.POLLING[0]}))
                self.assertEqual(v["expected_console"][0], "SM5 start")
                spots = v["polling_variable"]
                self.assertEqual(len(spots), 1, "the target reads lie at one place")
                (address, s), = spots.items()
                self.assertEqual((s["frame_reads"], s["pad_only_reads"], s["operations_without_a_read"], s["interface_failures"], s["address_mod_32"]),
                                 (26, 26, 0, [], int(address, 16) % 32))
        # review, 2026-11-15: an operation that sends no read command is not a read of the pad alone
        mixed = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 1), (0xB98, 0), (0xB98, NONE), (0xB99, 0)], seq=0, repeats=3)
        v = judge5(mixed)
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        (s,) = v["polling_variable"].values()
        self.assertEqual((s["frame_reads"], s["pad_only_reads"], s["operations_without_a_read"]), (3, 6, 3))
        alone = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, NONE)], seq=0)
        (s,) = judge5(alone)["polling_variable"].values()
        self.assertEqual((s["frame_reads"], s["pad_only_reads"], s["operations_without_a_read"]), (0, 0, 1))
        known_only = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 0)], seq=3, repeats=2)
        self.assertEqual((judge5(known_only)["verdict"], judge5(known_only)["problems"]), ("PASS", []))
        r = Run5("err@27", poll_limit=30)                    # an error bit in the frame read at the third address
        v = judge5(r)
        self.assertEqual((r.status, v["header"]["status"]), (0x221, "0x221"))
        failed = [s for s in v["polling_variable"].values() if s["interface_failures"]]
        self.assertEqual([s["interface_failures"] for s in failed], [[5]])
        self.assertEqual([p for p in v["problems"] if not any(h in p for h in ("no known answer", "did not complete", "anomalous read"))], [])
        self.assertEqual(s1b0b_judge.judge(r.words, KNOWN, r.params)["verdict"], "INVALID", "a stage-5 result is not a stage-3 result")

    def test_stage_three_and_stage_five_results_are_not_each_other_s(self) -> None:
        three = Run3()
        self.assertEqual(dx_judge.judge(three.words, KNOWN, three.params)["verdict"], "INVALID", "a stage-3 result, its own parameters as the plan")
        plain = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 1), (0xB98, 0)], seq=0, repeats=2)     # stage 5 with neither option: stage 3's reads
        self.assertEqual(judge5(plain)["verdict"], "PASS")
        self.assertEqual(s1b0b_judge.judge(plain.words, KNOWN, plain.params)["verdict"], "INVALID", "and still not a stage-3 result")

    def test_diagnostic_parameters_the_prober_would_refuse_are_invalid_even_when_the_plan_agrees(self) -> None:
        clean = Run5(hi=0xBFF)                               # an envelope with room for more than 32 addresses: only the limit can refuse 33
        for name, index, value in (("a sequence longer than 32", 14, 33), ("more than 64 words of stack", 15, 65)):
            with self.subTest(name):
                words, planned = list(clean.words), list(clean.params)
                words[32 + index] = planned[index] = value
                v = dx_judge.judge(words, KNOWN, planned)
                self.assertEqual(v["verdict"], "INVALID")
                self.assertIn("the echoed parameters are not a valid stage-5 parameter block", v["problems"])
        walk = Run4(extra=8)
        words, planned = list(walk.words), list(walk.params)
        words[32 + 15] = planned[15] = 65
        v = s1b1_judge.judge(words, KNOWN, planned)
        self.assertEqual((v["verdict"], "the echoed parameters are not a valid stage-4 parameter block" in v["problems"]), ("INVALID", True))

    def test_tampered_stage_five_buffers_fail(self) -> None:
        clean = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 0)], seq=3, repeats=2)
        self.assertEqual(judge5(clean)["verdict"], "PASS")
        at = lambda rec, field: HDR + rec * REC + field  # noqa: E731
        for name, change in (("an address out of sequence", lambda w: w.__setitem__(at(3, 0), 0xB98)), ("a frame where the pad alone belongs", lambda w: w.__setitem__(at(1, 14), 1)),
                             ("the reserved word beside the polling variable", lambda w: w.__setitem__(at(2, FARBLK + 7), 1)),
                             ("the length of the sequence in the echoed parameters", lambda w: w.__setitem__(32 + 14, 2))):
            with self.subTest(name):
                words = list(clean.words); change(words)
                self.assertNotEqual(dx_judge.judge(words, KNOWN, clean.params)["verdict"], "PASS")
        words = list(clean.words); words[at(2, FARBLK + 6)] ^= 0x40          # the recorded address is reported, not judged
        self.assertEqual(dx_judge.judge(words, KNOWN, clean.params)["verdict"], "PASS")


def watched(run) -> list[tuple[int, int]]:
    """What the twin saw of the prober's count of polls, each time a queued transfer was polled: (transfer, count)."""
    return [(int(e[1]), int(e[2])) for e in run.lines if e[0] == "WATCH"]


def but_where(run) -> list[int]:
    """The result without the three things that may differ between two runs that did the same: the echoed parameter
    word that chose the loop, and in each record the address of the polling variable (the twin's stack moves between
    processes)."""
    w = list(run.words)
    w[32 + 15] = 0
    for i in range(run.n_records):
        w[HDR + i * REC + FARBLK + 6] = 0
    return w


class TheWaitThatStoresNothing(unittest.TestCase):
    """Section 20: stages 4 and 5 can wait for a transfer without storing anything while it runs (bits 8 and up of
    parameter word 15). No result can tell the loops apart — that is the point — so the twin watches the count of
    polls on the prober's stack while it is being polled, and the machine code is read in test_prober_image."""
    FAULTS = ("", "err@7", "err@8", "timeout@7", "timeout@8", "drop@8", "dropafter@8", "stale", "short@2", "farshort@3")

    def test_the_three_loops_bring_back_the_same_result_whatever_happens(self) -> None:
        for fault in self.FAULTS:
            for make, name in ((lambda **k: Run5(fault, poll_limit=30, **k), "stage 5"), (lambda **k: Run4(fault, poll_limit=30, frames=FRAMES, hi=0xB99, **k), "the walk")):
                with self.subTest(fault=fault, stage=name):
                    as_before = make()
                    for poll in (1, 2):
                        quiet = make(poll=poll)
                        self.assertEqual(quiet.words[32 + 15], poll << 8)
                        self.assertEqual((quiet.rc, quiet.status, quiet.uart, quiet.violations), (as_before.rc, as_before.status, as_before.uart, as_before.violations))
                        self.assertEqual(but_where(quiet), but_where(as_before), "every word of the result")
                        self.assertEqual((quiet.accesses, quiet.dmas), (as_before.accesses, as_before.dmas), "every register access, in order")
        self.assertEqual({Run5(f, poll_limit=30).status for f in self.FAULTS}, {0x1, 0x221, 0x222, 0x223, 0x620},
                         "and the faults are the ones meant: done, an error bit, the limit, PCFG_DONE gone, a stale status before the command")

    def test_the_count_on_the_stack_while_a_transfer_is_polled(self) -> None:
        for make, name in ((lambda **k: Run5("timeout@8", poll_limit=30, **k), "stage 5"), (lambda **k: Run4("timeout@8", poll_limit=30, frames=FRAMES, hi=0xB99, **k), "the walk")):
            with self.subTest(stage=name):
                before = watched(make())
                per = {}
                for t, count in before:
                    per.setdefault(t, []).append(count)
                self.assertTrue(all(v == list(range(len(v))) for v in per.values()), "as before: at the k-th poll the stack holds k-1")
                # the transfer that never ends: 30 polls, and then the status read that closes the run finds the count stored
                self.assertEqual(per[8], list(range(31)))
                self.assertGreater(len([v for v in per.values() if len(v) == 2]), 5, "a transfer of the twin takes two polls")
                for poll in (1, 2):
                    quiet = watched(make(poll=poll))
                    self.assertEqual([t for t, _ in quiet], [t for t, _ in before], "the same polls of the same transfers")
                    self.assertEqual([count for t, count in quiet if t == 8], [0] * 30 + [30], "nothing stored while it was waited for; the count once the wait was over")
                    self.assertEqual({count for t, count in quiet if t != 8}, {0})

    def test_the_other_stages_wait_as_they_always_did(self) -> None:
        for run in (Run2(poll=1), Run3(poll=2)):
            self.assertEqual(run.status, 1)
            self.assertEqual({count for _, count in watched(run)}, {0, 1})
            self.assertEqual(run.words[32 + 15], run.params[15])

    def test_a_loop_that_does_not_exist_is_refused_before_anything_is_touched(self) -> None:
        for run in (Run5(poll=3), Run5(poll=4, extra=8), Run4(poll=3), Run4(poll=0x10000)):
            self.assertEqual((run.status, run.n_records, run.accesses, run.dmas), (0x500, 0, [], []))

    def test_the_judges_say_which_loop_and_refuse_one_that_does_not_exist(self) -> None:
        for poll, text in ((0, "as before"), (1, "no stores until"), (2, "no stores and no loads")):
            with self.subTest(poll=poll):
                five = Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 0)], seq=3, repeats=2, poll=poll, extra=10)
                v = judge5(five)
                self.assertEqual((v["verdict"], v["problems"], v["params"]["diagnostic"]["extra_stack_words"]), ("PASS", [], 10))
                self.assertTrue(v["params"]["diagnostic"]["polling_loop"].startswith(text))
                walk = Run4(poll=poll, extra=6)
                v = s1b1_judge.judge(walk.words, KNOWN, walk.params)
                self.assertEqual((v["verdict"], v["problems"], v["params"]["extra_stack_words"]), ("PASS", [], 6))
                self.assertTrue(v["params"]["polling_loop"].startswith(text))
        for run, judge, stage in ((Run5(lo=0xB98, hi=0xB9A, ops=[(0xB98, 0)], seq=3, repeats=2, poll=2), dx_judge.judge, 5), (Run4(poll=2), s1b1_judge.judge, 4)):
            words, planned = list(run.words), list(run.params)
            words[32 + 15] = planned[15] = 3 << 8
            v = judge(words, KNOWN, planned)
            self.assertEqual((v["verdict"], f"the echoed parameters are not a valid stage-{stage} parameter block" in v["problems"]), ("INVALID", True))
            words[32 + 15] = planned[15] = 2 << 8 | 65
            self.assertEqual(judge(words, KNOWN, planned)["verdict"], "INVALID", "and the limit on the extra stack is on its own byte")


class AReferenceReadThatFailsOnTheInterface(unittest.TestCase):
    """Found on the board, 2026-11-14: an overflow fell on a read of the reference frame, and the prober reported
    status 0x300, "the reference frame changed", for what its own record called an interface failure."""

    def test_stage_two_and_three(self) -> None:
        r = Run2("err@52", poll_limit=30)                    # the final reference read (record 10): an error bit in its frame read
        self.assertEqual((r.status, r.rc, r.n_records, r.stop_record, r.record(10)["code"]), (0x221, 0x221, 11, 10, 0x21))
        v = s1b0_judge.judge(r.words, KNOWN, r.params)
        self.assertEqual([p for p in v["problems"] if "did not complete" not in p], [])
        r = Run2("short@2,timeout@13", poll_limit=30)        # the reference read after an anomaly (record 2)
        self.assertEqual((r.status, r.n_records, r.stop_record, r.n_anomalies), (0x222, 3, 2, 1))
        v = s1b0_judge.judge(r.words, KNOWN, r.params)
        self.assertEqual([p for p in v["problems"] if not any(h in p for h in ("did not complete", "anomalous read"))], [])
        r = Run2("flip@11")                                  # a reference frame that really differs is still that
        self.assertEqual((r.status, r.record(10)["code"]), (0x300, 0))
        r = Run3("short@3,err@17", poll_limit=30)
        self.assertEqual((r.status, r.stop_record), (0x221, 3))
        self.assertEqual([p for p in s1b0b_judge.judge(r.words, KNOWN, r.params)["problems"] if not any(h in p for h in ("did not complete", "anomalous read"))], [])

    def test_the_walk(self) -> None:
        plan = schedule(COLUMN)
        first = next(i for i, s in enumerate(plan) if s[0] == 1)          # the first reference read during the walk
        last = len(plan) - 1
        for what, fault, record, status in (("during the walk", f"err@{5 * first + 2}", first, 0x221), ("the final one", f"timeout@{5 * last + 2}", last, 0x222),
                                            ("after an anomaly", "padnz@2,err@12", 2, 0x221)):
            with self.subTest(what):
                r = Run4(fault, poll_limit=30)
                self.assertEqual((r.status, r.rc, r.stop_record, r.n_records), (status, status, record, record + 1))
                self.assertEqual(r.rec(record)["kind"] in (1, 3), True)
                v = s1b1_judge.judge(r.words, KNOWN, r.params)
                self.assertEqual([p for p in v["problems"] if not any(h in p for h in ("did not complete", "anomalous read"))], [])
        r = Run4(f"flip@{first + 1}")                        # a reference frame that really differs is still that
        self.assertEqual((r.status, r.rec(first)["code"]), (0x300, 0))

    def test_a_result_that_still_says_the_reference_frame_changed_is_no_longer_what_the_records_imply(self) -> None:
        r = Run4(f"err@{5 * 34 + 2}", poll_limit=30)
        words = list(r.words); words[2] = 0x300              # as the image of 2026-11-14 reported it
        v = s1b1_judge.judge(words, KNOWN, r.params)
        self.assertIn("the header's status is 0x300; the records imply 0x221", v["problems"])


class ThroughTheRunScript(unittest.TestCase):
    """The parameter sets of the diagnostic series (docs/s1b_plan.md, section 17), as the board will get them."""
    MODEL = {"far_rule": "skip", "frames": FRAMES}

    def setUp(self) -> None:                               # the parameter sets are written with the image: have them before reading one
        import subprocess
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)

    def test_the_walk_kept_to_the_addresses_already_read(self) -> None:
        import test_s1a_run as fake
        for name, extra, poll in (("dxw0", 0, 0), ("dxw6", 6, 0), ("dxw8", 8, 0), ("dxw0n", 0, 1), ("dxw0r", 0, 2)):
            with self.subTest(name):
                exp = json.loads(fake.s1a_run.STAGES[name]["expected"].read_text())
                par = [int(w, 16) for w in exp["params"]]
                self.assertEqual((par[2], par[3], par[4], par[15], par[16]), (4, 0xB80, 0xB99, extra | poll << 8, 0xB80))
                self.assertEqual([k for k in range(32) if par[k] != [int(w, 16) for w in json.loads(fake.s1a_run.STAGES["dxw0"]["expected"].read_text())["params"]][k]],
                                 [15] if extra or poll else [], "nothing else differs from the walk as it was")
                rec, u, out = fake.run(stage=name, **self.MODEL)
                v = json.loads((out / "verdict.json").read_text())
                self.assertEqual((rec["verdict"], rec["problems"], v["frames_walked"], v["passes"][0]["last_address_named"]), ("PASS", [], 26, "0x00000b9a"))
                self.assertEqual((v["params"]["extra_stack_words"], v["params"]["polling_loop"]), (extra, s1b1_judge.POLLING[poll]))
                self.assertNotIn("0x00000b9a", {r["far"] for r in v["records"]}, "the address named at the end is not read")

    def test_the_first_pass_s_reads_made_by_the_stage_three_loop(self) -> None:
        import test_s1a_run as fake
        for name, extra, poll in (("dxs0", 0, 0), ("dxs10", 10, 0), ("dxs18", 18, 0), ("dxs10n", 10, 1), ("dxs10r", 10, 2)):
            with self.subTest(name):
                par = [int(w, 16) for w in json.loads(fake.s1a_run.STAGES[name]["expected"].read_text())["params"]]
                self.assertEqual([k for k in range(32) if par[k] != [int(w, 16) for w in json.loads(fake.s1a_run.STAGES["dxs10"]["expected"].read_text())["params"]][k]],
                                 [] if name == "dxs10" else [15], "one word apart")
                rec, u, out = fake.run(stage=name, **self.MODEL)
                v = json.loads((out / "verdict.json").read_text())
                self.assertEqual((v["header"]["status"], len(v["records"]), v["params"]["diagnostic"]),
                                 ("0x1", 54, {"generated_sequence_of_addresses": 26, "extra_stack_words": extra, "polling_loop": s1b0_judge.POLLING[poll]}))
                self.assertEqual((rec["verdict"], [p for p in v["problems"] if "no known answer" not in p]), ("FAIL", []))
                self.assertEqual({r["far"] for r in v["records"]}, {f"{a:#010x}" for a in range(0xB80, 0xB9A)})
                self.assertEqual(rec["console"][0], "SM5 start")


if __name__ == "__main__":
    unittest.main()

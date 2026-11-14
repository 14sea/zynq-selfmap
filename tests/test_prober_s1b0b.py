"""Stage 3 (S1b.0b) on the host twin: what the FAR register holds after the pad alone, after no read at all,
and after two frames — next to the one-frame read S1b.0 already made on the board.
The model's FAR register follows one of three rules; the board has not said which fits the new reads, so all are run."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import packets  # noqa: E402
from test_prober_s1b0 import CMD_BUF, CTRL, DLEN, DST, DST_BUF, FRAMES, INT_STS, MCTRL, PCAP, SLEN, SRC, STATUS, Run as Run2  # noqa: E402

HDR, REC, FARBLK, DATA = 64, 480, 68, 76
LO, HI, REF, NONE = 0xB98, 0xB9A, 0xB99, 15
OPS = [(0xB98, 1), (0xB98, 0), (0xB98, NONE), (0xB99, 0), (0xB98, 2), (0xB9A, 0), (0xB99, NONE), (0xB98, 0)]   # as the board run
N_RECORDS = 1 + len(OPS) * 3 + 1
# what each model rule leaves in the register after a read of `n` (frames delivered) starting at `far`
RULES = {"next": lambda far, n: far + (0 if n == NONE else n),
         "skip": lambda far, n: far if n == NONE else far + n + 1,
         "skipdata": lambda far, n: far if n in (NONE, 0) else far + n + 1}


def words_of(n: int) -> int:
    return 0 if n == NONE else 101 * (n + 1)


class Run(Run2):
    def __init__(self, fault: str = "", rule: str = "next", **over) -> None:
        super().__init__(fault, rule, **{"stage": 3, "ops": OPS, "budget": 24, **over})

    def rec(self, i: int) -> dict:
        r = self.words[HDR + i * REC: HDR + (i + 1) * REC]
        n = r[14]; nw = words_of(n)
        return {"far": r[0], "kind": r[1], "code": r[2], "sts": (r[3], r[5], r[7]), "polls": (r[4], r[6], r[8]), "survivors": r[9],
                "ref_equal": r[10], "repeat": r[12], "guard": r[13], "n": n, "op": r[15],
                "stream": r[16:59], "farrd": r[59:63], "cleanup": r[63:68],
                "far_polls": (r[FARBLK + 1], r[FARBLK + 3]), "far_value": r[FARBLK + 4], "far_unread": r[FARBLK + 5],
                "pad": r[DATA:DATA + min(nw, 101)], "frames": [r[DATA + 101 * (j + 1):DATA + 101 * (j + 2)] for j in range(0 if n == NONE else n)],
                "tail": r[DATA + nw:]}


class Normal(unittest.TestCase):
    def test_it_completes_under_every_rule_and_reports_what_the_register_said(self) -> None:
        for rule, value in RULES.items():
            with self.subTest(rule):
                r = Run(rule=rule)
                self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
                self.assertEqual((r.n_records, r.total, len(r.words)), (N_RECORDS, HDR + N_RECORDS * REC, HDR + N_RECORDS * REC))
                self.assertEqual(r.uart, "SM3 start\r\nSM3 end status=00000001 records=%08x anomalies=00000000 words=%08x\r\n" % (N_RECORDS, r.total))
                for i in range(r.n_records):
                    rec = r.rec(i)
                    self.assertEqual(rec["far_value"], value(rec["far"], rec["n"]), f"record {i}")
                    self.assertEqual((rec["code"], rec["survivors"], rec["guard"], rec["far_unread"]), (0, 0, 0, 0))

    def test_the_schedule_and_the_data(self) -> None:
        r = Run()
        self.assertEqual([r.rec(i)["kind"] for i in range(N_RECORDS)], [2] + [0] * 24 + [3])
        self.assertEqual([(r.rec(i)["far"], r.rec(i)["n"]) for i in range(N_RECORDS)], [(REF, 1)] + OPS * 3 + [(REF, 1)])
        self.assertEqual([r.rec(i)["op"] for i in range(N_RECORDS)], [0xFFFFFFFF] + list(range(8)) * 3 + [0xFFFFFFFF])
        for i in range(N_RECORDS):
            rec = r.rec(i)
            self.assertEqual(rec["pad"], [0] * (0 if rec["n"] == NONE else 101))
            for j, frame in enumerate(rec["frames"]):
                self.assertEqual(frame, FRAMES[rec["far"] + j], f"record {i}, frame {j}")
            self.assertFalse(any(rec["tail"]), "words that were not read must stay zero in the record")
        self.assertEqual(r.rec(N_RECORDS - 1)["ref_equal"], 1)

    def test_the_only_registers_touched(self) -> None:
        r = Run()
        self.assertEqual({a for k, a, _ in r.accesses if k == "W"}, {INT_STS, SRC, DST, SLEN, DLEN})
        self.assertEqual({a for k, a, _ in r.accesses if k == "R"}, {CTRL, MCTRL, INT_STS, STATUS})
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})

    def test_an_operation_that_reads_nothing_sends_no_read_command(self) -> None:
        r = Run()
        at = 0
        for i in range(r.n_records):
            rec = r.rec(i)
            want = [(CMD_BUF | 1, PCAP, 43, 0)]
            if rec["n"] != NONE:
                want.append((PCAP, DST_BUF | 1, 0, words_of(rec["n"])))
            want += [(CMD_BUF | 1, PCAP, 4, 0), (PCAP, DST_BUF | 1, 0, 1), (CMD_BUF | 1, PCAP, 5, 0)]
            self.assertEqual(r.dmas[at:at + len(want)], want, f"record {i}")
            at += len(want)
            self.assertEqual((rec["sts"][1], rec["polls"][1]) == (0, 0), rec["n"] == NONE, "no status for a read that was not made")
            self.assertEqual((rec["polls"][0], rec["polls"][2]) + rec["far_polls"], (2, 2, 2, 2))
        self.assertEqual(at, len(r.dmas))
        self.assertEqual(len(r.dmas), 5 * N_RECORDS - 6)       # two of the eight operations read nothing, three repeats

    def test_everything_sent_is_read_only_inside_the_envelope_and_is_what_the_record_says(self) -> None:
        r = Run()
        self.assertEqual(len(r.streams), 3 * r.n_records)
        for i in range(r.n_records):
            rec = r.rec(i)
            self.assertEqual(r.streams[3 * i:3 * i + 3], [rec["stream"], rec["farrd"], rec["cleanup"]])
            for s in (rec["stream"], rec["farrd"], rec["cleanup"]):
                self.assertEqual(packets.readonly_problems(s, LO, HI, 404), [])
            self.assertEqual(rec["stream"][8], rec["far"])
            if rec["n"] == NONE:
                self.assertEqual(rec["stream"][9:11], [0x20000000, 0x20000000])
            else:
                self.assertEqual(rec["stream"][9:11], [0x28006000, 0x48000000 | words_of(rec["n"])])


class Parameters(unittest.TestCase):
    def test_stage_two_still_refuses_the_new_operations(self) -> None:
        for n in (0, NONE):
            with self.subTest(n=n):
                r = Run(stage=2, ops=[(0xB98, n)])
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(r.uart, "SM2 start\r\nSM2 end status=00000500\r\n")

    def test_stage_two_parameters_still_run_stage_two(self) -> None:
        r = Run2()
        self.assertTrue(r.uart.startswith("SM2 start"))
        self.assertEqual((r.status, r.n_records), (1, 11))

    def test_bad_parameters_touch_no_register(self) -> None:
        for name, over in (("the pad alone outside the envelope", {"ops": [(0xB9B, 0)]}), ("no read, outside the envelope", {"ops": [(0xB97, NONE)]}),
                           ("a count that is neither", {"ops": [(0xB98, 4)], "hi": 0xBA0}), ("fourteen", {"ops": [(0xB98, 14)], "hi": 0xBB0}),
                           ("two frames running past the envelope", {"ops": [(0xB9A, 2)]}),
                           ("an end that wraps", {"lo": 0xFFFFFFFE, "hi": 0xFFFFFFFF, "ref": 0xFFFFFFFF, "ops": [(0xFFFFFFFF, 3)]}),
                           ("version", {"version": 2}), ("no operations", {"ops": [], "n_ops": 0}), ("too many repeats", {"repeats": 9})):
            with self.subTest(name):
                r = Run(**over)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(r.uart, "SM3 start\r\nSM3 end status=00000500\r\n")

    def test_the_pad_alone_and_no_read_are_allowed_anywhere_inside_even_at_the_top_of_the_address_space(self) -> None:
        top = 0xFFFFFFFF
        r = Run(lo=top - 1, hi=top, ref=top - 1, ops=[(top, 0), (top, NONE), (top - 1, 0)], repeats=1)
        self.assertEqual((r.status, r.n_records, r.violations), (1, 5, []))


class Faults(unittest.TestCase):
    """DMA commands: 1..5 the baseline, 6..10 the one-frame read, 11..15 the pad alone, 16..19 the operation that reads nothing."""

    def test_an_interface_failure_in_an_operation_that_reads_nothing_stops_at_that_command(self) -> None:
        for fault, code, count in (("err@16", 0x21, 16), ("err@17", 0x21, 17), ("err@18", 0x21, 18), ("err@19", 0x21, 19),
                                   ("timeout@17", 0x22, 17), ("drop@18", 0x23, 18), ("err@12", 0x21, 12), ("timeout@12", 0x22, 12)):
            with self.subTest(fault):
                r = Run(fault, poll_limit=30)
                record = 3 if count >= 16 else 2
                self.assertEqual((r.status, r.n_records, r.stop_record, len(r.dmas)), (0x200 | code, record + 1, record, count))
                self.assertEqual(r.rec(record)["code"], code)

    def test_data_anomalies_in_the_new_operations_are_recorded_and_skipped_while_the_reference_holds(self) -> None:
        """Frame reads: 1 the baseline, 2 the one-frame read, 3 the pad alone. FAR reads: one per record, record 3 reads nothing."""
        for fault, at, code in (("padnz@3", 2, 0x11), ("short@3", 2, 0x10), ("farshort@3", 2, 0x14), ("farshort@4", 3, 0x14),
                                ("farflip@12", 11, 0x13), ("farflip@10", 9, 0x13)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.status, r.rc, r.n_anomalies, r.n_records), (1, 0, 1, N_RECORDS + 1))
                self.assertEqual(r.rec(at)["code"], code)
                health = r.rec(at + 1)
                self.assertEqual((health["kind"], health["far"], health["n"], health["code"], health["ref_equal"]), (1, REF, 1, 0, 1))

    def test_every_pad_only_read_may_be_anomalous_and_the_run_still_measures_everything(self) -> None:
        """If on the board the pad alone is not all zero, every such read is an anomaly. The budget of the board run
        (24, one per target read) must let the run go through all its operations anyway, a health read after each."""
        reads, k = [], 1                                     # frame-read commands: 1 is the baseline
        for _ in range(3):
            for far, n in OPS:
                if n == NONE:
                    continue
                k += 1
                if n == 0:
                    reads.append(k); k += 1                  # this one is anomalous; the health read after it takes the next number
        r = Run(",".join(f"padnz@{x}" for x in reads))
        self.assertEqual((r.status, r.rc, r.n_anomalies, r.n_records, r.violations), (1, 0, 12, N_RECORDS + 12, []))
        self.assertEqual([r.rec(i)["code"] for i in range(r.n_records) if r.rec(i)["kind"] == 0 and r.rec(i)["n"] == 0], [0x11] * 12)
        self.assertEqual({r.rec(i)["code"] for i in range(r.n_records) if r.rec(i)["n"] != 0}, {0})
        r = Run(",".join(f"padnz@{x}" for x in reads), budget=4)
        self.assertEqual((r.status, r.n_anomalies), (0x400, 5), "with the budget of S1b.0 the same run would have stopped early")

    def test_no_fault_makes_the_model_see_a_forbidden_operation(self) -> None:
        for fault in ("stale", "err@16", "err@18", "timeout@17", "drop@18", "padnz@3", "short@3", "farshort@4", "farflip@12"):
            with self.subTest(fault):
                self.assertEqual(Run(fault, poll_limit=30).violations, [])


if __name__ == "__main__":
    unittest.main()

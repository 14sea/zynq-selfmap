"""Stages 6 (S2.0) and 7 (S2.1) on the host twin — docs/s2_plan.md, sections 6 and 7.

Stage 6: one word of IDCODE, CTL0 and STAT read through PCAP, beside the address register. Stage 7: the same after
the first accesses to user logic — the four SLCR words as gates, then the probe design's registers through the two
helpers and through nothing else. The device and the design here are models (prober/twin_hal.c); these tests are
about the prober: what it sends, what it touches, where it stops."""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import packets  # noqa: E402
import s2_judge  # noqa: E402
from test_prober_s1b0 import CMD_BUF, CTRL, DLEN, DST, DST_BUF, FRAMES, INT_STS, MCTRL, PCAP, SLEN, SRC, STATUS, TWIN  # noqa: E402,F401

REC, FARBLK, DATA = 480, 68, 76
LO, HI, REF, NONE = 0xB98, 0xB9A, 0xB99, 15
FAR, IDCODE, CTL0, STAT = 0, 1, 2, 3
HEADER = {FAR: 0x28002001, IDCODE: 0x28018001, CTL0: 0x2800A001, STAT: 0x2800E001}
SLCR = (0xF8000900, 0xF8000240, 0xF8000170, 0xF800010C)
SLCR_WORDS = (0x0000000F, 0x00000000, 0x00400800, 0x0000003F)
PL = 0x40000000
PL_ID, PL_SCRATCH, PL_COUNT, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR, PL_SRL_DATA, PL_WRITES = (PL + off for off in range(0, 0x20, 4))
ID_WORD = 0x53324131
PLB = 16 + 2 * 1280
OPS6 = [(REF, 1, FAR), (REF, NONE, IDCODE), (REF, NONE, CTL0), (REF, NONE, STAT)]       # as the board run of S2.0
OPS7 = [(REF, NONE, IDCODE), (REF, NONE, CTL0), (REF, NONE, STAT)]                       # as the board run of S2.1


def params(stage: int, ops=None, **over) -> list[int]:
    ops = (OPS6 if stage == 6 else OPS7) if ops is None else ops
    w = [0] * 32
    w[0:10] = [0x31504D53, 1, stage, LO, HI, REF, len(ops), 3, 0, 1000]
    for k, (far, n, reg) in enumerate(ops):
        w[16 + k] = far
        w[10] |= n << (4 * k)
        w[12] |= reg << (4 * k)
    w[15] = 2 << 8                                    # the wait that touches no memory
    if stage == 7:
        w[24], w[25], w[26] = PL, PL + 0x1F, ID_WORD
        w[28:32] = SLCR_WORDS
    for k, v in over.items():
        w[int(k[1:])] = v                             # w7=..., w12=...: a word of the block by its number
    return w


class Run:
    def __init__(self, stage: int, fault: str = "", creg: str = "", rule: str = "skip", ops=None, **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(scratch_dirs.mkdtemp(prefix="smtwin6_"))
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in FRAMES.items()) + "\n")
        self.stage, self.params = stage, params(stage, ops, **over)
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in self.params) + "\n")
        env = dict(os.environ)
        for name in ("SM_FAULT", "SM_CREG", "SM_SUCC", "SM_SHOWS"):
            env.pop(name, None)
        env["SM_FAR_RULE"] = rule                     # "skip" is what the board does: one step for the pad as well
        if fault:
            env["SM_FAULT"] = fault
        if creg:
            env["SM_CREG"] = creg
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "result.bin")],
                             check=True, capture_output=True, text=True, env=env).stdout
        self.lines = [line.split() for line in out.splitlines()]
        raw = (tmp / "result.bin").read_bytes()
        self.words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        self.rc = int([e for e in self.lines if e[0] == "RC"][0][1], 16)
        self.uart = bytes(int(x, 16) for x in [e for e in self.lines if e[0] == "UART"][0][1:]).decode()
        self.violations = [" ".join(e) for e in self.lines if e[0] == "VIOLATION"]
        self.accesses = [(e[0], int(e[1], 16), int(e[2], 16)) for e in self.lines if e[0] in ("R", "W")]
        self.events = [e[0] for e in self.lines if e[0] in ("R", "W", "DMA")]
        self.dmas = [e for e in self.lines if e[0] == "DMA"]
        self.streams = [[int(x, 16) for x in e[1:]] for e in self.lines if e[0] == "STREAM"]
        h = self.words
        self.status, self.n_records, self.n_anomalies, self.total, self.hdr_words, self.stop_record = h[2], h[3], h[4], h[5], h[7], h[18]
        self.hb = 64 + (PLB if stage == 7 else 0)
        self.plb = self.words[64:64 + PLB] if stage == 7 and len(self.words) >= 64 + PLB else []

    def rec(self, i: int) -> dict:
        r = self.words[self.hb + i * REC: self.hb + (i + 1) * REC]
        return {"far": r[0], "kind": r[1], "code": r[2], "n": r[14], "op": r[15], "repeat": r[12], "guard": r[13], "ref_equal": r[10],
                "stream": r[16:59], "regrd": r[59:63], "cleanup": r[63:68], "value": r[FARBLK + 4], "unread": r[FARBLK + 5]}

    def pl_log(self) -> list[tuple[int, bool, int]]:
        return [(self.plb[16 + 2 * i] & ~3, bool(self.plb[16 + 2 * i] & 1), self.plb[17 + 2 * i]) for i in range(self.plb[1])]

    def pl_accesses(self) -> list[tuple[int, bool, int]]:
        """What the twin saw at the design's registers, in order: the same form as the log."""
        return [(a, k == "W", v) for k, a, v in self.accesses if PL <= a < PL + 0x1000]


N6, N7 = 1 + len(OPS6) * 3 + 1, 1 + len(OPS7) * 3 + 1


class StageSix(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run(6)

    def test_it_completes_and_says_so(self) -> None:
        r = self.r
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
        self.assertEqual((r.n_records, r.hdr_words, r.total, len(r.words)), (N6, 64, 64 + N6 * REC, 64 + N6 * REC))
        self.assertEqual(r.uart, "SM6 start\r\nSM6 end status=00000001 records=%08x anomalies=00000000 words=%08x\r\n" % (N6, r.total))

    def test_each_operation_reads_the_register_its_table_names_and_the_reference_reads_read_far(self) -> None:
        r = self.r
        want = [(REF, 1, FAR)] + OPS6 * 3 + [(REF, 1, FAR)]
        for i, (far, n, reg) in enumerate(want):
            rec = r.rec(i)
            self.assertEqual((rec["far"], rec["n"], rec["code"], rec["guard"], rec["unread"]), (far, n, 0, 0, 0), f"record {i}")
            self.assertEqual(rec["regrd"], [0x20000000, HEADER[reg], 0x20000000, 0x20000000], f"record {i}")
        self.assertEqual([r.rec(i)["kind"] for i in range(N6)], [2] + [0] * 12 + [3])
        self.assertEqual([r.rec(i)["op"] for i in range(N6)], [0xFFFFFFFF] + [0, 1, 2, 3] * 3 + [0xFFFFFFFF])

    def test_the_values_are_what_the_device_holds(self) -> None:
        r = Run(6, creg="idcode:13722093,ctl0:00000401,stat:5a5a0001")
        got = {(rec["op"], rec["value"]) for rec in (r.rec(i) for i in range(1, N6 - 1))}
        self.assertEqual(got, {(0, REF + 2), (1, 0x13722093), (2, 0x00000401), (3, 0x5A5A0001)})
        self.assertEqual({r.rec(0)["value"], r.rec(N6 - 1)["value"]}, {REF + 2}, "the reference reads read the address register")

    def test_the_only_registers_touched_are_those_of_every_stage_before(self) -> None:
        r = self.r
        self.assertEqual({a for k, a, _ in r.accesses if k == "W"}, {INT_STS, SRC, DST, SLEN, DLEN})
        self.assertEqual({a for k, a, _ in r.accesses if k == "R"}, {CTRL, MCTRL, INT_STS, STATUS})
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})

    def test_everything_sent_is_read_only_and_nothing_is_read_but_the_four_registers(self) -> None:
        r = self.r
        self.assertEqual(len(r.streams), 3 * N6)
        heads = set()
        for s in r.streams:
            self.assertEqual(packets.readonly_problems(s, LO, HI, 404), [], s)
            for p in packets.decode(s):
                if p["kind"].startswith("type") and p["op"] == "read" and p["reg_name"] != "FDRO":
                    heads.add((p["reg_name"], p["count"]))
                self.assertFalse(p["kind"].startswith("type") and p["op"] == "write" and p["reg_name"] not in ("CMD", "FAR"), p)
        self.assertEqual(heads, {("FAR", 1), ("IDCODE", 1), ("CTL0", 1), ("STAT", 1)})

    def test_an_operation_without_a_frame_read_sends_no_read_command_for_one(self) -> None:
        r = self.r
        for i in range(1, N6 - 1):
            rec = r.rec(i)
            self.assertEqual(rec["stream"][9:11], [0x28006000, 0x480000CA] if rec["n"] == 1 else [0x20000000, 0x20000000], f"record {i}")

    def test_the_wait_is_the_one_asked_for_and_another_is_refused(self) -> None:
        self.assertEqual(Run(6, w15=1 << 8).status, 1)
        self.assertEqual(Run(6, w15=0).status, 1)
        self.assertEqual(Run(6, w15=3 << 8).status, 0x500)


class TheStatusRegisterBetweenTransfers(unittest.TestCase):
    def test_stages_6_and_7_read_it_as_often_as_they_always_did(self) -> None:
        """Stage 8 reads the status register once more, before every clearing (docs/s2_plan.md, section 23). No other
        stage does: between the write that queues a transfer and the next clearing of the register there are that
        transfer's polls — two on the twin — and, after the last transfer of a read, the one look at PCFG_DONE."""
        int_sts, dlen, clear = 0xF800700C, 0xF8007024, 0x00F4F840
        for stage in (6, 7):
            with self.subTest(stage=stage):
                r = Run(stage)
                queued = [i for i, (k, a, v) in enumerate(r.accesses) if k == "W" and a == dlen]
                cleared = [i for i, (k, a, v) in enumerate(r.accesses) if k == "W" and a == int_sts]
                self.assertTrue(all(r.accesses[i][2] == clear for i in cleared))
                self.assertEqual(len(queued), len(cleared))
                reads = [sum(1 for k, a, v in r.accesses[i + 1:j] if k == "R" and a == int_sts) for i, j in zip(queued, cleared[1:])]
                self.assertEqual(sorted(set(reads)), [2, 3])
                self.assertEqual(reads.count(3), r.n_records - 1, "once more where a read ends and another begins")


class StageSixGates(unittest.TestCase):
    def test_seu_en_set_stops_the_run_before_anything_is_sent(self) -> None:
        r = Run(6, "seu")
        self.assertEqual((r.status, r.rc, r.n_records, r.dmas), (0x105, 0x105, 0, []))
        self.assertEqual([(k, a) for k, a, _ in r.accesses], [("R", CTRL), ("R", INT_STS), ("R", STATUS)],
                         "the control register is read and found so; the two status words for the header; nothing is written")
        self.assertTrue(r.words[8] & 0x100)

    def test_the_gates_of_every_stage_still_stop_it(self) -> None:
        for fault, status in (("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104)):
            with self.subTest(fault):
                r = Run(6, fault)
                self.assertEqual((r.status, r.n_records, r.dmas, r.violations), (status, 0, [], []))

    def test_the_order_of_the_gates(self) -> None:
        self.assertEqual(Run(6, "ctrl,seu").status, 0x101)
        self.assertEqual(Run(6, "seu,lpbk").status, 0x105)

    def test_the_older_stages_have_no_such_gate(self) -> None:
        """The gate is in stages 6 and 7 only: stages 1 to 5 and their judges are as they were on the board."""
        from test_prober_s1b0b import Run as Run3
        self.assertEqual(Run3("seu").status, 1)


class StageSixParameters(unittest.TestCase):
    def refused(self, **kw) -> None:
        r = Run(6, **kw)
        self.assertEqual((r.status, r.rc, r.n_records, r.total), (0x500, 0x500, 0, 64), kw)
        self.assertEqual(r.accesses, [], "refused on form alone: no device register is even read")
        self.assertEqual(r.uart, "SM6 start\r\nSM6 end status=00000500\r\n")

    def test_a_block_that_is_not_of_this_form_is_refused(self) -> None:
        for name, kw in (("nine operations", {"ops": [(REF, NONE, IDCODE)] * 8, "w6": 9}),
                         # with the envelope beginning at 0 a ninth operation would have an address in it (word 24, zero in
                         # this stage) and nothing but the count would stop it: the pad read at an address nobody named
                         ("nine operations and an envelope from 0", {"ops": [(REF, NONE, IDCODE)] * 8, "w6": 9, "w3": 0}),
                         ("no operation", {"w6": 0}),
                         ("a register that is not on the list", {"ops": [(REF, NONE, 4)]}),
                         ("another that is not", {"ops": [(REF, NONE, 15)]}),
                         ("a register named beyond the last operation", {"w12": 0x13210}),
                         ("a frame count beyond the last operation", {"w10": 0xFFFFF1}),
                         ("an address beyond the last operation", {"w20": REF}),
                         ("the upper half of the table of counts", {"w11": 1}),
                         ("word 13", {"w13": 16}), ("word 14", {"w14": 1}), ("more stack beneath the reads", {"w15": 2 << 8 | 4}),
                         ("a word of the second envelope", {"w24": 0x40000000}), ("the identification word", {"w26": ID_WORD}),
                         ("an SLCR word", {"w31": 0x3F}), ("word 27", {"w27": 1}),
                         ("an address outside the envelope", {"ops": [(0xB97, NONE, CTL0)]}),
                         ("four frames", {"ops": [(REF, 4, FAR)]}),
                         ("a read that runs past the envelope", {"ops": [(0xB9A, 2, FAR)]})):
            with self.subTest(name):
                self.refused(**kw)

    def test_eight_operations_are_taken(self) -> None:
        ops = [(REF, NONE, IDCODE), (REF, 0, CTL0), (0xB98, 3, STAT), (REF, 1, FAR)] * 2
        r = Run(6, ops=ops, w7=1)
        self.assertEqual((r.status, r.n_records, r.violations), (1, 10, []))
        self.assertEqual([r.rec(i)["regrd"][1] for i in range(1, 9)], [HEADER[reg] for _, _, reg in ops])


class StageSixWhenTheDeviceDoesNotAnswerAsHoped(unittest.TestCase):
    def test_a_register_that_reads_differently_a_second_time_ends_the_run(self) -> None:
        r = Run(6, "statmoves")
        self.assertEqual((r.status, r.n_anomalies), (0x400, 1), "no anomaly is budgeted for")
        stat = [i for i in range(r.n_records) if r.rec(i)["op"] == 3]
        self.assertEqual([r.rec(i)["code"] for i in stat], [0, 0x13])
        self.assertEqual(r.rec(r.n_records - 1)["kind"], 1, "one read of the reference frame, and then nothing")
        self.assertEqual(r.stop_record, r.n_records - 2)

    def test_one_changed_value_in_one_read(self) -> None:
        for k, op in ((7, 1), (8, 2), (9, 3)):                    # register reads 7, 8, 9 are the second IDCODE, CTL0, STAT
            with self.subTest(op=op):
                r = Run(6, f"farflip@{k}")
                bad = [i for i in range(r.n_records) if r.rec(i)["code"]]
                self.assertEqual([(r.rec(i)["op"], r.rec(i)["code"]) for i in bad], [(op, 0x13)])
                self.assertEqual(r.status, 0x400)

    def test_a_register_read_that_delivers_nothing(self) -> None:
        r = Run(6, "farshort@3")                                  # the third register read: IDCODE, first time
        rec = r.rec(2)
        self.assertEqual((rec["op"], rec["code"], rec["unread"], rec["value"]), (1, 0x14, 1, 0xA5A55A5A))
        self.assertEqual(r.status, 0x400)

    def test_reading_a_register_that_disturbs_the_frames_is_seen_at_the_next_frame_read(self) -> None:
        r = Run(6, "regdisturbs")
        self.assertEqual(r.status, 0x300, "the reference frame is no longer what it was")
        self.assertEqual([r.rec(i)["code"] for i in range(r.n_records)], [0, 0, 0, 0, 0, 0x12, 0])
        self.assertEqual((r.rec(r.n_records - 1)["kind"], r.rec(r.n_records - 1)["ref_equal"]), (1, 0))

    def test_a_failure_of_the_interface_during_a_register_read_stops_at_once(self) -> None:
        # commands 1 to 5 are the reference frame's first reading, 6 to 10 the frame and the address register; 11 opens
        # the session of the IDCODE read, 12 sends its header, 13 is the read of its one word
        for fault, code in (("err@13", 0x21), ("timeout@13", 0x22), ("drop@13", 0x23)):
            with self.subTest(fault):
                r = Run(6, fault)
                self.assertEqual((r.status, r.n_records, r.stop_record), (0x200 | code, 3, 2))
                self.assertEqual((r.rec(2)["op"], r.rec(2)["code"]), (1, code))
                self.assertEqual(len(r.dmas), 13, "no command follows the failing one")


class StageSeven(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run(7)

    def test_it_completes_and_says_so(self) -> None:
        r = self.r
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
        self.assertEqual((r.n_records, r.hdr_words, r.total, len(r.words)), (N7, 64 + PLB, 64 + PLB + N7 * REC, 64 + PLB + N7 * REC))
        self.assertEqual(r.uart, "SM7 start\r\nSM7 end status=00000001 records=%08x anomalies=00000000 words=%08x\r\n" % (N7, r.total))

    def test_the_pl_block_is_the_log_of_what_was_done(self) -> None:
        r = self.r
        self.assertEqual(r.plb[0:4], [0x4C504D53, 1164, 0, 0xFFFFFFFF])
        self.assertEqual(r.plb[4:8], list(SLCR_WORDS))
        self.assertFalse(any(r.plb[8:16]))
        self.assertFalse(any(r.plb[16 + 2 * 1164:]))
        self.assertEqual(r.pl_log(), r.pl_accesses(), "every access made is logged, in order, and nothing is logged that was not made")

    def test_the_sequence_is_the_one_the_judge_expects(self) -> None:
        steps = s2_judge.pl_schedule(ID_WORD)
        log = self.r.pl_log()
        self.assertEqual(len(log), len(steps))
        for i, ((addr, write, value), st) in enumerate(zip(log, steps)):
            self.assertEqual((addr - PL, write), (st["off"], st["write"]), f"access {i}")
            if write:
                self.assertEqual(value, st["value"], f"access {i}")

    def test_what_is_touched_in_the_pl_and_in_the_slcr(self) -> None:
        r = self.r
        reads = {a for k, a, _ in r.accesses if k == "R"}
        writes = {a for k, a, _ in r.accesses if k == "W"}
        self.assertEqual(reads, {CTRL, MCTRL, INT_STS, STATUS, *SLCR, PL_ID, PL_SCRATCH, PL_COUNT, PL_RAM_DATA, PL_SRL_DATA, PL_WRITES})
        self.assertEqual(writes, {INT_STS, SRC, DST, SLEN, DLEN, PL_SCRATCH, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR})
        self.assertEqual([a for k, a, _ in r.accesses if a in SLCR], list(SLCR), "each SLCR word read once, in order, and none written")
        self.assertNotIn(PL_SRL_DATA, writes, "a write there shifts: this prober never asks for it")
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})

    def test_the_order_gates_then_the_reference_frame_then_user_logic_then_the_registers(self) -> None:
        r = self.r
        where = [i for i, (k, a, _) in enumerate(r.accesses) if PL <= a < PL + 0x1000]
        slcr = [i for i, (k, a, _) in enumerate(r.accesses) if a in SLCR]
        dlen = [i for i, (k, a, _) in enumerate(r.accesses) if k == "W" and a == DLEN]
        self.assertLess(max(slcr), dlen[0], "the SLCR is looked at before anything is sent")
        self.assertLess(dlen[4], where[0], "the reference frame's first reading (five commands) comes before user logic")
        self.assertEqual(where, list(range(where[0], where[0] + len(where))), "the accesses to the design are one stretch")
        self.assertLess(where[-1], dlen[5], "and everything read through PCAP afterwards comes after it")
        self.assertEqual([r.rec(i)["regrd"][1] for i in range(1, N7 - 1)], [HEADER[IDCODE], HEADER[CTL0], HEADER[STAT]] * 3)

    def test_what_the_design_answered(self) -> None:
        log = self.r.pl_log()
        self.assertEqual(log[0], (PL_ID, False, ID_WORD))
        self.assertEqual([(a, w, v) for a, w, v in log[1:9]],
                         [x for word in (0, 0xFFFFFFFF, 0xA5A55A5A, 0x5A5AA5A5) for x in ((PL_SCRATCH, True, word), (PL_SCRATCH, False, word))])
        ram_reads = [v for a, w, v in log if a == PL_RAM_DATA and not w]
        self.assertEqual(ram_reads, [0] * 64 + [0xF] * 64 + [a & 0xF for a in range(64)] + [~a & 0xF for a in range(64)])
        srl = [v for a, w, v in log if a == PL_SRL_DATA]
        self.assertEqual(srl[:32], srl[32:])
        self.assertEqual(log[-1], (PL_WRITES, False, 256))


class StageSevenGates(unittest.TestCase):
    def test_an_slcr_word_that_is_not_the_board_s_stops_the_run_before_the_pl_is_touched(self) -> None:
        for k, fault in enumerate(("lvl", "fpgarst", "fclk", "pll")):
            with self.subTest(fault):
                r = Run(7, fault)
                self.assertEqual((r.status, r.rc, r.n_records, r.dmas, r.pl_accesses()), (0x110 | k, 0x110 | k, 0, [], []))
                self.assertEqual([a for _, a, _ in r.accesses if a in SLCR], list(SLCR), "all four are read and recorded")
                self.assertNotEqual(r.plb[4 + k], SLCR_WORDS[k])
                self.assertEqual((r.plb[0], r.plb[1], r.plb[2], r.plb[3]), (0x4C504D53, 0, 0, 0xFFFFFFFF))
                self.assertEqual(r.total, 64 + PLB)

    def test_the_first_word_that_differs_is_the_one_named(self) -> None:
        self.assertEqual(Run(7, "fclk,pll").status, 0x112)

    def test_the_host_says_what_the_words_must_be(self) -> None:
        r = Run(7, w30=0x00200A00)                                # the host expects another clock word than the board has
        self.assertEqual((r.status, r.pl_accesses()), (0x112, []))

    def test_the_gates_before_them_stop_the_run_with_the_slcr_unread(self) -> None:
        for fault, status in (("seu", 0x105), ("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104)):
            with self.subTest(fault):
                r = Run(7, fault)
                self.assertEqual((r.status, r.n_records, r.dmas, r.pl_accesses()), (status, 0, [], []))
                self.assertFalse([a for _, a, _ in r.accesses if a in SLCR])
                self.assertFalse(any(r.plb[4:8]))


class StageSevenWhenTheDesignDoesNotAnswerAsItMust(unittest.TestCase):
    def stopped(self, fault: str, code: int, accesses: int, **kw) -> Run:
        r = Run(7, fault, **kw)
        self.assertEqual((r.status, r.rc), (0xA00 | code, 0xA00 | code), fault)
        self.assertEqual((r.n_records, r.n_anomalies, r.stop_record), (1, 0, 0xFFFFFFFF), "the reference frame's first reading, and nothing after")
        self.assertEqual((r.plb[1], r.plb[2], r.plb[3]), (accesses, code, accesses), fault)
        self.assertEqual(r.pl_log(), r.pl_accesses(), "nothing is accessed after the answer that is not right")
        self.assertEqual(len(r.dmas), 5, "and nothing more is sent through PCAP: the five commands of the reference frame's first reading are all")
        self.assertEqual(r.violations, [])
        return r

    def test_the_identification_register(self) -> None:
        r = self.stopped("plid", 2, 1)
        self.assertFalse([1 for a, w, v in r.pl_accesses() if w], "nothing was written to the design")

    def test_the_scratch_register(self) -> None:
        r = self.stopped("scratchstuck", 3, 5)
        self.assertEqual({a for a, w, v in r.pl_accesses() if w}, {PL_SCRATCH}, "nothing written but the scratch register")

    def test_the_counter(self) -> None:
        self.stopped("countstuck", 4, 11)

    def test_the_ram(self) -> None:
        self.stopped("ramstuck", 5, 11 + 256 + 128 + 12)          # state 1, address 5: one bit does not set
        self.stopped("ramwild", 5, 11 + 2 * 256 + 128 + 2)        # state 2, address 0: the write at 63 reached it too

    def test_the_shift_registers(self) -> None:
        self.stopped("srlmoves", 6, 11 + 4 * 256 + 64 + 8)        # second pass, address 3

    def test_the_design_s_count_of_writes(self) -> None:
        self.stopped("plcount", 7, 1164)

    def test_an_address_outside_the_envelope_is_not_touched(self) -> None:
        r = self.stopped("", 1, 11 + 1, w25=PL + 0x0F)            # the RAM's data register lies above the envelope
        self.assertTrue(all(a <= PL + 0x0F for a, w, v in r.pl_accesses()))
        r = self.stopped("", 1, 0, w24=PL + 4)                    # the identification register lies below it
        self.assertEqual(r.pl_accesses(), [])


class StageSevenParameters(unittest.TestCase):
    def test_an_envelope_that_is_not_inside_the_design_is_refused(self) -> None:
        for name, kw in (("below the PL", {"w24": 0x3FFFFFFC}), ("beyond the design's registers", {"w25": PL + 0x20}),
                         ("the wrong way round", {"w24": PL + 8, "w25": PL + 4}), ("word 27", {"w27": 1}), ("none given", {"w24": 0, "w25": 0})):
            with self.subTest(name):
                r = Run(7, **kw)
                self.assertEqual((r.status, r.n_records, r.total, r.accesses), (0x500, 0, 64 + PLB, []))
                self.assertEqual((r.plb[0], r.plb[1], r.plb[2], r.plb[3]), (0x4C504D53, 0, 0, 0xFFFFFFFF))
                self.assertEqual(r.uart, "SM7 start\r\nSM7 end status=00000500\r\n")

    def test_the_older_stages_results_begin_where_they_always_did(self) -> None:
        from test_prober_s1b0b import Run as Run3, N_RECORDS
        r = Run3()
        self.assertEqual((r.words[7], r.total), (64, 64 + N_RECORDS * REC))


if __name__ == "__main__":
    unittest.main()

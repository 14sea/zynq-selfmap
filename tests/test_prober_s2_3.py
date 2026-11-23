"""Stage 9 (S2.3) on the host twin — docs/s2_plan.md, section 29.

The prober is given two lists: the reads, as in stage 8, and the accesses to the probe design — what to write, what to
read, what a reading must be, and where between them the frames are read. It makes them in order and knows no state.
The device, the design and where the RAM's cells show in configuration memory are models here (prober/twin_hal.c, and
a layout made up below); these tests are about the prober: what it refuses, what it touches, in which order, what it
writes down, and where it stops."""
from __future__ import annotations

import json
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
import s2_2_shares  # noqa: E402
import s2_3_states as st  # noqa: E402
from test_prober_s1b0 import DLEN, FRAMES, INT_STS, TWIN  # noqa: E402
from test_prober_s2_2 import (CTL0_HEAD, FAR_HEAD, HI, ID_WORD, LAY, LO, NO_OP, NONE, OP_CTL0, PL, PL_COUNT, PL_ID, PL_RAM_ADDR,  # noqa: E402
                              PL_RAM_DATA, PL_SCRATCH, PL_SRL_ADDR, PL_SRL_DATA, PL_WRITES, REF, SEU_ERR, SLCR, SLCR_WORDS, census, successors)

REC, FARBLK, DATA, FRAME = 480, 68, 76, 101
FIXED = 16                                             # the PL block before its log
DESIGN = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
ACC_ADDR, LIST_ADDR = 0x10190000, 0x10180000
MAY_WRITE = 1 << 0x0C | 1 << 0x10 | 1 << 0x14          # the two address registers and the RAM's data: what S2.3's lists write
BOUND = MAY_WRITE | 1 << 0x04 | 1 << 0x18              # the image's own bound: those, the scratch register, the shift registers' data

# ---- the made-up device of the stage-8 tests (block type 0 of two rows, six columns). The cells of the RAM are put,
# each at a place of its own, into one column: the first of the top row, seven frames, read in three reads.
COLUMN = [0xA00 + m for m in range(7)]
COLUMN_READS = s2_2_shares.reads_of(COLUMN)            # (0xa00, 3), (0xa03, 3), (0xa06, 1)


def ram_map(seed: int = 1, frames: tuple = (0xA03, 0xA04, 0xA05), inverted: int = 0) -> list[tuple[int, int, int, int, int, int]]:
    """Where the 256 cells show: (RAM address, memory, frame address, word, bit, inverted) — every cell at one place,
    all of them in the given frames of the column, made up differently for every seed."""
    x = seed * 2654435761 % 2 ** 32
    used: set[tuple[int, int, int]] = set()
    out = []
    for n in range(st.CELLS):
        while True:
            x = (x * 1103515245 + 12345) % 2 ** 31
            p = (frames[x % len(frames)], (x >> 8) % FRAME, (x >> 16) % 32)
            if p not in used:
                used.add(p)
                break
        out.append((n % st.DEPTH, n // st.DEPTH, *p, 1 if n < inverted else 0))
    return out


def few(states: list[dict], k: int) -> list[dict]:
    """The first k states of a run: enough for most of what is asked of the prober here."""
    return states[:k]


def params(n_list: int, n_states: int, n_acc: int, **over) -> list[int]:
    w = [0] * 32
    w[0:10] = [0x31504D53, 1, 9, LO, HI, REF, 0, n_states, 0, 1000]
    w[15] = 2 << 8                                    # the wait that touches no memory
    w[16] = n_list
    w[18], w[19] = n_acc, MAY_WRITE
    w[24], w[25], w[26] = PL, PL + 0x1F, ID_WORD
    w[28:32] = SLCR_WORDS
    for k, v in over.items():
        w[int(k[1:])] = v                             # w7=..., w19=...: a word of the block by its number
    return w


class Run:
    def __init__(self, states=None, fault: str = "", reads=None, cells=None, entries=None, n_states=None, shifts: bool = False, list_words=None,
                 clean: bool = False, **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(scratch_dirs.mkdtemp(prefix="smtwin9_"))
        self.states = few(st.code_run(), 4) if states is None else states
        self.reads = COLUMN_READS if reads is None else reads
        self.cells = ram_map() if cells is None else cells
        self.entries = st.accesses(self.states, DESIGN) if entries is None else entries
        self.list = s2_2_shares.list_words(self.reads) if list_words is None else list_words
        self.acc = st.acc_words(self.entries, DESIGN)
        self.n_states = len(self.states) if n_states is None else n_states
        self.params = params(len(self.list), self.n_states, len(self.entries), **over)
        self.list_sent = self.list
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in FRAMES.items()) + "\n")
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in self.params) + "\n")
        (tmp / "list.txt").write_text("\n".join(f"{x:x}" for x in self.list) + "\n")
        (tmp / "acc.txt").write_text("\n".join(f"{x:x}" for x in self.acc) + "\n")
        (tmp / "rammap.txt").write_text("".join("%d %d %x %d %d %d\n" % c for c in self.cells))
        env = dict(os.environ)
        for name in ("SM_FAULT", "SM_CREG", "SM_SHIFTS", "SM_DIRTY"):
            env.pop(name, None)
        if not clean:                                   # memory that holds something, as on a board: the twin writes out no result of which
            env["SM_DIRTY"] = "1"                       # a word was never written (review of 5936a8e). Every run here is made so.
        env["SM_FAR_RULE"] = "skip"
        env["SM_SUCC"], env["SM_SHOWS"] = successors()
        env["SM_LIST"], env["SM_ACC"], env["SM_RAMMAP"] = str(tmp / "list.txt"), str(tmp / "acc.txt"), str(tmp / "rammap.txt")
        if fault:
            env["SM_FAULT"] = fault
        if shifts:
            env["SM_SHIFTS"] = "allowed"
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "result.bin")],
                             check=True, capture_output=True, text=True, env=env, timeout=120).stdout   # a twin that does not end is an error, not a wait
        self.lines = [line.split() for line in out.splitlines()]
        raw = (tmp / "result.bin").read_bytes()
        self.words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        self.rc = int([e for e in self.lines if e[0] == "RC"][0][1], 16)
        self.uart = bytes(int(x, 16) for x in [e for e in self.lines if e[0] == "UART"][0][1:]).decode()
        self.violations = [" ".join(e) for e in self.lines if e[0] == "VIOLATION"]
        self.accesses = [(e[0], int(e[1], 16), int(e[2], 16)) for e in self.lines if e[0] in ("R", "W")]
        self.dmas = [e for e in self.lines if e[0] == "DMA"]
        h = self.words
        self.status, self.n_records, self.n_anomalies, self.total, self.hdr_words, self.stop_record = h[2], h[3], h[4], h[5], h[7], h[18]
        self.n_log = len(st.planned_log(self.entries, DESIGN))
        self.hb = 64 + FIXED + 2 * self.n_log         # where the records begin, if the block is one the prober takes
        self.plb = self.words[64:self.hb] if len(self.words) >= self.hb else self.words[64:]

    def raw(self, i: int) -> list[int]:
        return self.words[self.hb + i * REC: self.hb + (i + 1) * REC]

    def rec(self, i: int) -> dict:
        r = self.raw(i)
        return {"far": r[0], "kind": r[1], "code": r[2], "n": r[14], "op": r[15], "state": r[12], "guard": r[13], "cleared": r[10],
                "regrd": r[59:63], "value": r[FARBLK + 4], "unread": r[FARBLK + 5], "after": r[FARBLK + 7],
                "frames": [r[DATA + FRAME * (j + 1): DATA + FRAME * (j + 2)] for j in range(min(r[14], REC // FRAME) if r[14] != NONE else 0)]}

    def pl_log(self) -> list[tuple[int, bool, int]]:
        n = min(self.plb[1], (len(self.plb) - FIXED) // 2)
        return [(self.plb[FIXED + 2 * i] & ~3, bool(self.plb[FIXED + 2 * i] & 1), self.plb[FIXED + 1 + 2 * i]) for i in range(n)]

    def pl_accesses(self) -> list[tuple[int, bool, int]]:
        return [(a, k == "W", v) for k, a, v in self.accesses if PL <= a < PL + 0x1000]

    def touched(self) -> bool:
        """Was anything of the device looked at: a register read or written, a transfer made."""
        return bool(self.accesses or self.dmas)


def n_records(r: Run) -> int:
    return 4 + r.n_states * len(r.reads)                # the reference frame, CTL0, the reads of every state, CTL0, the reference frame


class StageNine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run()

    def test_it_completes_and_says_so(self) -> None:
        r, n = self.r, n_records(self.r)
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
        self.assertEqual((r.n_records, r.hdr_words, r.total, len(r.words)), (n, r.hb, r.hb + n * REC, r.hb + n * REC))
        self.assertEqual(r.uart, "SM9 start\r\nSM9 end status=00000001 records=%08x anomalies=00000000 words=%08x\r\n" % (n, r.total))
        self.assertEqual(r.stop_record, 0xFFFFFFFF)

    def test_the_records_are_the_reference_frame_ctl0_the_list_in_every_state_ctl0_and_the_reference_frame(self) -> None:
        r, n = self.r, n_records(self.r)
        want = [(2, REF, 1, 0, NO_OP), (0, REF, NONE, 0, OP_CTL0)]
        want += [(0, far, k, s, i) for s in range(r.n_states) for i, (far, k) in enumerate(r.reads)]
        want += [(0, REF, NONE, r.n_states, OP_CTL0), (3, REF, 1, r.n_states, NO_OP)]
        self.assertEqual([(x["kind"], x["far"], x["n"], x["state"], x["op"]) for x in (r.rec(i) for i in range(n))], want)
        for i in range(n):
            rec = r.rec(i)
            self.assertEqual((rec["code"], rec["guard"], rec["unread"]), (0, 0, 0), f"record {i}")
            self.assertEqual(rec["regrd"], [0x20000000, CTL0_HEAD if rec["op"] == OP_CTL0 else FAR_HEAD, 0x20000000, 0x20000000], f"record {i}")
            if rec["op"] != OP_CTL0:
                self.assertEqual(rec["value"], s2_2_shares.register_after(LAY, rec["far"], rec["n"]), f"record {i}")

    def test_the_log_is_the_identification_and_then_the_list_entry_by_entry(self) -> None:
        r = self.r
        log, plan = r.pl_log(), st.planned_log(r.entries, DESIGN)
        self.assertEqual((r.plb[0], r.plb[1], r.plb[2], r.plb[3]), (0x4C504D53, len(plan), 0, 0xFFFFFFFF))
        self.assertEqual(len(log), len(plan))
        for i, ((addr, write, value), (p_addr, p_write, p_value)) in enumerate(zip(log, plan)):
            self.assertEqual((addr, write), (p_addr, p_write), f"access {i}")
            if p_value is not None:
                self.assertEqual(value, p_value, f"access {i}")
        self.assertEqual(log[0], (PL_ID, False, ID_WORD))

    def test_what_the_twin_saw_of_the_design_is_the_log_and_nothing_else(self) -> None:
        r = self.r
        self.assertEqual(r.pl_accesses(), r.pl_log())
        self.assertEqual({a for a, w, _ in r.pl_accesses() if w}, {PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR})
        self.assertNotIn(PL_SRL_DATA, {a for a, w, _ in r.pl_accesses() if w}, "nothing shifts")
        self.assertNotIn(PL_SCRATCH, {a for a, _, _ in r.pl_accesses()})

    def test_the_frames_of_a_state_are_read_where_its_mark_is(self) -> None:
        """In the order the twin saw things: the reference frame; the identification; then for every state the
        entries before its mark, exactly the reads of the list, the entries after the mark; the reference frame. (A
        read of CTL0 delivers one word and no frame, and is not counted here.)"""
        r = self.r
        got = []
        for e in r.lines:
            if e[0] in ("R", "W") and PL <= int(e[1], 16) < PL + 0x1000:
                got.append("pl")
            elif e[0] == "DMA" and int(e[5].split("=")[1]) > 1:   # a transfer that delivers frames (a register read delivers one word)
                got.append("frames")
        want = ["frames", "pl"]
        for kind, _, value in r.entries:
            want += ["pl"] if kind != st.A_MARK else ["frames"] * len(r.reads) if value == st.MARK_FRAMES else []
        self.assertEqual(got, want + ["frames"])
        self.assertEqual(got.count("frames"), 2 + r.n_states * len(r.reads))

    def test_the_frames_delivered_show_the_cells_as_the_state_has_them(self) -> None:
        r = self.r
        where = {(far, word, bit): (mem * st.DEPTH + addr, inv) for addr, mem, far, word, bit, inv in r.cells}
        seen = 0
        for i in range(2, 2 + r.n_states * len(r.reads)):
            rec = r.rec(i)
            ram = r.states[rec["state"]]["ram"]
            for j, frame in enumerate(rec["frames"]):
                for (far, word, bit), (n, inv) in where.items():
                    if far == rec["far"] + j:
                        self.assertEqual((frame[word] >> bit) & 1, st.cell(ram, n) ^ inv, (i, hex(far), word, bit))
                        seen += 1
        self.assertEqual(seen, st.CELLS * r.n_states)

    def test_nothing_is_written_but_the_transfers_own_words_the_list_and_bit_5(self) -> None:
        r = self.r
        writes = [(a, v) for k, a, v in r.accesses if k == "W" and not PL <= a < PL + 0x1000]
        self.assertEqual({v for a, v in writes if a == INT_STS}, {0x00003000}, "the two done bits when a transfer begins; no error bit, ever")
        self.assertEqual({a for a, _ in writes} - {INT_STS}, {0xF8007018, 0xF800701C, 0xF8007020, DLEN})

    def test_the_whole_code_run_goes_through_and_its_result_is_as_large_as_planned(self) -> None:
        states = st.code_run()
        r = Run(states=states)
        self.assertEqual((r.rc, r.status, r.violations, r.n_records), (0, 1, [], 4 + 18 * 3))
        self.assertEqual(len(r.words), st.result_words(18, 3, r.n_log))
        self.assertEqual(r.pl_accesses(), r.pl_log())

    def test_a_run_of_singles_goes_through(self) -> None:
        states = st.single_run(2)
        r = Run(states=states, reads=COLUMN_READS[1:2])
        self.assertEqual((r.rc, r.status, r.violations, r.n_records), (0, 1, [], 4 + 66))
        self.assertEqual(len(r.words), st.result_words(66, 1, r.n_log))
        where = {(mem * st.DEPTH + addr): (far, word, bit) for addr, mem, far, word, bit, _ in r.cells}
        for s in range(1, 65):                        # the single of cell n: its place reads one in the frames of that state, if they were read
            n = states[s]["cell"]
            far, word, bit = where[n]
            rec = r.rec(2 + s)
            if rec["far"] <= far < rec["far"] + rec["n"]:
                self.assertEqual((rec["frames"][far - rec["far"]][word] >> bit) & 1, 1, n)


class WhatItRefuses(unittest.TestCase):
    """A block or a list that is not as the stage takes it is refused on its form: nothing of the device is read, and
    the twin has no violation of its own to report — the refusal is the prober's."""

    def refused(self, r: Run, why: str) -> None:
        self.assertEqual((r.rc, r.status, r.violations), (0x500, 0x500, []), why)
        self.assertFalse(r.touched(), why)
        self.assertEqual(r.uart, "SM9 start\r\nSM9 end status=00000500\r\n", why)
        self.assertEqual(r.total, len(r.words), why)
        n, s = r.params[18], r.params[7]                # what is left of a refused block: the header and the PL block, as long as the counts make it —
        room = 0 if (s == 0 or s > 80 or n > 32768 or n < 2 * s) else 1 + n - 2 * s   # and with no log at all where the counts cannot be
        self.assertEqual((r.hdr_words, r.total), (64 + FIXED + 2 * room,) * 2, why)

    def setUp(self) -> None:
        self.states = few(st.code_run(), 2)
        self.entries = st.accesses(self.states, DESIGN)

    def test_the_form_of_the_list(self) -> None:
        e = self.entries
        marks = [i for i, (kind, _, _) in enumerate(e) if kind == st.A_MARK]
        cases = {
            "the last mark is missing": e[:-1],
            "an entry after the last state's end": e + [(st.A_READ, PL_COUNT, 0)],
            "a state too many": e + e[marks[0] + 1: marks[1] + 1][-1:] * 0 + [(st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)],
            "the end before the frames": e[:marks[0]] + [(st.A_MARK, 0, st.MARK_END)] + e[marks[0] + 1:],
            "the frames twice in a state": e[:marks[1]] + [(st.A_MARK, 0, st.MARK_FRAMES)] + e[marks[1] + 1:],
            "a mark that is neither": e[:marks[0]] + [(st.A_MARK, 0, 2)] + e[marks[0] + 1:],
            "a mark with an address": e[:marks[0]] + [(st.A_MARK, PL_COUNT, st.MARK_FRAMES)] + e[marks[0] + 1:],
            "a reading that is only recorded, with a value": [(st.A_READ, PL_COUNT, 1)] + e,
        }
        for why, entries in cases.items():
            with self.subTest(why=why):
                self.refused(Run(states=self.states, entries=entries), why)

    def test_fewer_states_in_the_list_than_the_block_says_and_more(self) -> None:
        self.refused(Run(states=self.states, n_states=3), "the block says three states, the list has two")
        self.refused(Run(states=self.states, n_states=1), "the block says one state, the list has two")

    def test_the_count_of_entries_is_the_blocks(self) -> None:
        self.refused(Run(states=self.states, w18=len(self.entries) - 1), "one entry fewer than the list has: the last mark is not looked at")
        self.refused(Run(states=self.states, w18=0), "no entry at all")
        self.refused(Run(states=self.states, w18=3), "fewer entries than two states have marks")
        self.refused(Run(states=self.states, w18=32769), "more than a list holds")

    def test_a_list_longer_than_a_list_may_be_is_refused_before_a_word_beyond_its_room_is_read(self) -> None:
        """One state of 32,768 readings and its two marks: 32,770 entries, well formed, and the result would fit.
        It is refused for its length alone, and no word of memory beyond the list's room is looked at (the twin would
        call that a violation)."""
        long = [(st.A_READ, PL_COUNT, 0)] * 32768 + [(st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)]
        r = Run(states=[], entries=long, n_states=1)
        self.refused(r, "32,770 entries")
        fits = [(st.A_READ, PL_COUNT, 0)] * 32766 + long[-2:]
        ok = Run(states=[], entries=fits, n_states=1)
        self.assertEqual((ok.rc, ok.status, ok.violations, ok.plb[1]), (0, 1, [], 32767), "32,768 entries is a list: 32,766 readings, and the identification before them")

    def test_no_state_at_all_is_no_run(self) -> None:
        r = Run(states=[], entries=[], n_states=0)
        self.refused(r, "a block of no state, with a list of no entry")

    def test_a_pl_envelope_the_wrong_way_round_is_refused_even_where_no_entry_names_a_register(self) -> None:
        empty = [(st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)]
        self.refused(Run(states=[], entries=empty, n_states=1, w24=PL + 0x1C, w25=PL), "the envelope ends before it begins")
        self.assertEqual(Run(states=[], entries=empty, n_states=1).status, 1)

    def test_an_address_that_is_no_register_of_the_design(self) -> None:
        for why, addr in (("below the design", PL - 4), ("beyond its last register", PL + 0x20), ("far away", 0xF8007000), ("the result area", 0x10000000)):
            with self.subTest(why=why):
                self.refused(Run(states=self.states, entries=[(st.A_READ, addr, 0)] + self.entries), why)
                self.refused(Run(states=self.states, entries=[(st.A_WRITE, addr, 0)] + self.entries), why)

    def test_an_address_outside_the_envelope_the_block_gives(self) -> None:
        self.refused(Run(states=self.states, w25=PL + 0x0F), "the list reads the RAM's data, the envelope ends before it")
        self.refused(Run(states=self.states, w24=PL + 0x10), "the list writes the RAM's address, the envelope begins after it")

    def test_a_write_to_a_register_the_run_may_not_write(self) -> None:
        for why, addr in (("the identification", PL_ID), ("the counter", PL_COUNT), ("the count of writes", PL_WRITES),
                          ("the scratch register, which this run's word does not name", PL_SCRATCH),
                          ("the shift registers' data: a shift", PL_SRL_DATA)):
            with self.subTest(why=why):
                self.refused(Run(states=self.states, entries=[(st.A_WRITE, addr, 1)] + self.entries), why)
        self.refused(Run(states=self.states, w19=MAY_WRITE & ~(1 << 0x10)), "the list writes the RAM's data and the run's word does not allow it")

    def test_the_runs_word_cannot_go_beyond_the_images_bound(self) -> None:
        for bit in (0x00, 0x08, 0x1C, 1, 31):
            with self.subTest(bit=bit):
                self.refused(Run(states=self.states, w19=MAY_WRITE | 1 << bit), f"bit {bit} is no register this image may ever write")

    def test_inside_the_bound_the_runs_word_decides(self) -> None:
        """The image's bound has the scratch register and the shift registers' data. A run whose word names them may
        write them — S2.3's sets do not, and the test above holds that their lists are then refused."""
        e = [(st.A_WRITE, PL_SCRATCH, 0x12345678), (st.A_EXPECT, PL_SCRATCH, 0x12345678)] + self.entries
        r = Run(states=self.states, entries=e, w19=MAY_WRITE | 1 << 0x04)
        self.assertEqual((r.rc, r.status, r.violations), (0, 1, []))
        e = [(st.A_WRITE, PL_SRL_DATA, 0xF)] + [x for x in self.entries if x[1] not in (PL_SRL_ADDR, PL_SRL_DATA) and x[1] != PL_WRITES]
        r = Run(states=self.states, entries=e, w19=BOUND, shifts=True)
        self.assertEqual((r.rc, r.status, r.violations), (0, 1, []))
        self.assertIn((PL_SRL_DATA, True, 0xF), r.pl_log())
        r = Run(states=self.states, entries=e, w19=BOUND)
        self.assertEqual(r.violations, ["VIOLATION shift 0000000f"], "the twin's own word for a shift nobody announced")

    def test_the_words_the_stage_has_no_use_for_must_be_zero(self) -> None:
        used = 0xF70D82BF
        for k in range(32):
            if not (used >> k) & 1:
                with self.subTest(word=k):
                    self.refused(Run(states=self.states, **{f"w{k}": 1}), f"word {k}")
        self.assertEqual([k for k in range(32) if (used >> k) & 1], [0, 1, 2, 3, 4, 5, 7, 9, 15, 16, 18, 19, 24, 25, 26, 28, 29, 30, 31])

    def test_a_list_of_reads_that_is_not_one(self) -> None:
        self.refused(Run(states=self.states, w16=0), "no read")
        self.refused(Run(states=self.states, w16=179), "more reads than a list holds")
        self.refused(Run(states=self.states, w4=0xA04), "a read beyond the envelope")
        self.refused(Run(states=self.states, w3=0xA01, w5=0xA01), "a read below the envelope")
        two = [3 << 28 | 0xA00, 3 << 28 | 0xA03]
        self.refused(Run(states=self.states, list_words=two, w4=0xA04, w5=0xA02), "the second read begins inside the envelope and runs past its end")
        self.assertEqual(Run(states=self.states, list_words=two, w4=0xA05, w5=0xA02).status, 1, "and with the envelope one address longer it does not")
        for why, word in (("four frames", 4 << 28 | 0xA00), ("no frame", 0xA00), ("an address above the envelope", 1 << 28 | 0x400A83), ("an address below it", 1 << 28 | 0x9FF)):
            with self.subTest(why=why):
                r = Run(states=self.states, list_words=[word, 3 << 28 | 0xA03, 1 << 28 | 0xA06])
                self.refused(r, why)
        self.refused(Run(states=self.states, list_words=[3 << 28 | 0xA00, 3 << 28 | 0xA03, 4 << 28 | 0xA06]), "the last word of the list is looked at as well")
        ok = Run(states=self.states, list_words=[3 << 28 | 0xA00, 3 << 28 | 0xA03, 1 << 28 | 0xA06, 4 << 28 | 0xA00], w16=3)
        self.assertEqual((ok.rc, ok.status, ok.n_records), (0, 1, 4 + 2 * 3), "and no word beyond the count the block gives: what lies after the list is not the list")

    def test_the_block_s_other_words(self) -> None:
        for why, over in (("another version", {"w1": 2}), ("an envelope the wrong way round", {"w3": HI, "w4": LO}), ("a reference frame below the envelope", {"w3": REF + 1}),
                          ("a reference frame above it", {"w4": REF - 1}), ("no poll limit", {"w9": 0}), ("a poll limit beyond any", {"w9": 0x10000001}),
                          ("more stack beneath the reads", {"w15": 2 << 8 | 1}), ("a wait that is none", {"w15": 3 << 8}),
                          ("a PL envelope that begins below the design", {"w24": PL - 4}), ("a PL envelope the wrong way round", {"w24": PL + 0x1C, "w25": PL}),
                          ("a PL envelope that ends above the design", {"w25": PL + 0x20})):
            with self.subTest(why=why):
                self.refused(Run(states=self.states, **over), why)
        self.assertEqual(Run(states=self.states, w9=0x10000000).status, 1, "the largest poll limit there is, is one")
        self.assertEqual(Run(states=self.states, w15=0).status, 1, "and the wait as it was before is a wait")

    def test_a_result_that_would_not_lie_in_its_area(self) -> None:
        """80 states of 178 reads would be 14,244 records. The block is refused before anything is written beyond
        the header: the twin would call a write outside the area a violation."""
        reads = (COLUMN_READS * 60)[:178]
        empty = [(st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)]          # a state of no entry: the frames, and its end
        r = Run(states=[], entries=empty * 80, n_states=80, reads=reads)
        self.refused(r, "6.8 million words")
        self.assertEqual(len(r.words), 64 + FIXED + 2 * r.n_log)
        ok = Run(states=[], entries=empty * 3, n_states=3, reads=reads)   # 538 records, as stage 8's largest: it fits
        self.assertEqual((ok.rc, ok.status, ok.n_records, ok.pl_log()), (0, 1, 538, [(PL_ID, False, ID_WORD)]))
        self.refused(Run(states=[], entries=empty * 81, n_states=81, reads=reads[:1]), "more states than the stage takes")
        longer = (COLUMN_READS * 60)[:179]
        r = Run(states=[], entries=empty, n_states=1, reads=longer)
        self.refused(r, "one read more than a list holds, in a run whose result would fit")
        self.assertEqual(Run(states=[], entries=empty, n_states=1, reads=longer[:178]).n_records, 4 + 178)
        fits = Run(states=[], entries=empty * 80, n_states=80, reads=reads[:1])
        self.assertEqual((fits.rc, fits.status, fits.n_records), (0, 1, 84))


class OnMemoryThatHoldsSomething(unittest.TestCase):
    """Review of 5936a8e. On a board the result of the run before lies where this run's result will. A block refused
    for its version alone was answered with a result as long as header, PL block and log — and the log was cleared
    only after the refusal: 3,482 words of whatever lay there went out as the result of a run that made no access.
    Every run of this file is made on such memory, and the twin writes no result out that holds a word nothing wrote;
    here the results are held, word for word, to those on memory that held nothing."""

    def test_a_refused_block_is_answered_the_same_whatever_lay_in_memory(self) -> None:
        for name, over in (("the version", {"w1": 2}), ("a word the stage has no use for", {"w6": 1}), ("more entries than a list may have", {"w18": 40000}),
                           ("no state", {"n_states": 0}), ("a write the run may not make", {"w19": 0})):
            with self.subTest(name):
                dirty, clean = Run(**over), Run(clean=True, **over)
                self.assertEqual((dirty.rc, dirty.status, dirty.n_records), (0x500, 0x500, 0))
                self.assertEqual(dirty.words, clean.words)
                self.assertEqual((len(dirty.words), dirty.total), (dirty.hdr_words, dirty.hdr_words), "what is reported is what was written out")
                self.assertFalse(any(dirty.words[64 + FIXED:]), "and of the log nothing: no access was made")
        r = Run(w1=2)
        self.assertEqual((r.hdr_words, r.hdr_words - 64 - FIXED), (r.hb, 2 * r.n_log), "the log of a block refused for its version is as long as the block says")
        self.assertGreater(r.n_log, 1000)

    def test_a_run_that_completes_and_runs_that_stop_are_the_same_too(self) -> None:
        def but_the_stack(r: Run) -> list[int]:        # the one word of a record that is the twin's own from process to process
            return [0 if i >= r.hb and (i - r.hb) % REC == FARBLK + 6 else w for i, w in enumerate(r.words)]
        for fault in ("", "ramstuck", "ramdisturb@9", "seu", "err@3"):
            with self.subTest(fault or "no fault"):
                dirty, clean = Run(fault=fault), Run(fault=fault, clean=True)
                self.assertEqual((dirty.rc, but_the_stack(dirty)), (clean.rc, but_the_stack(clean)))
        self.assertNotEqual(Run(clean=True).words[3562 + FARBLK + 6], 0, "that word is written, by every run")


    def test_a_frame_word_that_is_what_lay_in_its_place_is_a_word_like_any_other(self) -> None:
        """Review of ce77a49: the twin told a word nothing wrote by what it held, so a frame that holds that very
        word in that very place was called stale. It keeps now which words were written."""
        at = Run(clean=True).hb + DATA + FRAME + 5     # record 0: the reference frame after its pad frame, word 5
        keep = FRAMES[REF][5]
        self.assertEqual(Run(clean=True).words[at], keep, "that is where the word lands")
        FRAMES[REF][5] = 0xD1E70000 | (at & 0xFFFF)   # what SM_DIRTY fills that place with (prober/twin_hal.c, DIRTY)
        try:
            dirty, clean = Run(), Run(clean=True)
        finally:
            FRAMES[REF][5] = keep
        self.assertEqual((dirty.rc, dirty.status, dirty.words[at]), (0, 1, 0xD1E70000 | (at & 0xFFFF)))
        self.assertEqual((clean.rc, clean.words[at]), (0, dirty.words[at]))


class WhereItStops(unittest.TestCase):
    def test_a_reading_before_the_frames_that_is_not_what_the_list_says(self) -> None:
        """The twin's RAM has a bit that never sets (address 5, memory 2). The first state that wants it set is read
        back before its frames, and the run ends there: stop 0xa0a, nothing read through PCAP in that state."""
        states = [st.code_run()[0], {"name": "ones", "kind": "base", "ram": [0xF] * st.DEPTH}]
        r = Run(states=states, fault="ramstuck")
        self.assertEqual((r.rc, r.status, r.violations), (0xA0A, 0xA0A, []))
        log = r.pl_log()
        self.assertEqual((r.plb[2], r.plb[3]), (10, len(log)))
        self.assertEqual(log[-1], (PL_RAM_DATA, False, 0xB), "the reading that was not 0xf is the last thing in the log")
        self.assertEqual(log[-2], (PL_RAM_ADDR, True, 5))
        self.assertEqual(r.pl_accesses(), log, "and the last access made")
        self.assertEqual(r.n_records, 2 + len(r.reads), "the reference frame, CTL0, the reads of the first state; none of the second")

    def test_a_reading_after_the_frames_that_is_not_what_the_list_says(self) -> None:
        """A frame read changes a cell of the RAM. The readings after the frames meet it: stop 0xa0b — the RAM did not
        hold. Nothing is read through PCAP afterwards, and nothing more of the design."""
        r = Run(fault="ramdisturb@3")                 # the third frame read: the second read of the list in the first state
        self.assertEqual((r.rc, r.status, r.violations), (0xA0B, 0xA0B, []))
        log = r.pl_log()
        self.assertEqual((r.plb[2], r.plb[3]), (11, len(log)))
        self.assertEqual(log[-1][0:2], (PL_RAM_DATA, False))
        self.assertEqual(r.pl_accesses(), log)
        self.assertEqual(r.n_records, 2 + len(r.reads), "the first state's reads were all made; then the readings, then nothing")
        plan = st.planned_log(r.entries, DESIGN)
        self.assertNotEqual(log[-1][2], plan[len(log) - 1][2])
        for (addr, write, value), (p_addr, p_write, p_value) in zip(log[:-1], plan):
            self.assertEqual((addr, write), (p_addr, p_write))
            self.assertTrue(p_value is None or value == p_value)

    def test_the_shift_registers_and_the_count_are_readings_like_any_other(self) -> None:
        for fault, register in (("srlmoves", PL_SRL_DATA), ("plcount", PL_WRITES)):
            with self.subTest(fault=fault):
                r = Run(fault=fault)
                self.assertIn(r.status, (0xA0A, 0xA0B))
                self.assertEqual((r.rc, r.violations, r.pl_log()[-1][0]), (r.status, [], register))

    def test_the_identification_is_the_probers_own_question(self) -> None:
        r = Run(fault="plid")
        self.assertEqual((r.rc, r.status, r.violations), (0xA02, 0xA02, []))
        self.assertEqual(r.pl_accesses(), [(PL_ID, False, 0x53324132)], "one access, and no entry of the list")
        self.assertEqual(r.n_records, 1)

    def test_the_gates_are_stage_eights(self) -> None:
        for fault, status in (("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104), ("seu", 0x105),
                              ("lvl", 0x110), ("fpgarst", 0x111), ("fclk", 0x112), ("pll", 0x113)):
            with self.subTest(fault=fault):
                r = Run(fault=fault)
                self.assertEqual((r.rc, r.status, r.violations, r.n_records), (status, status, [], 0))
                self.assertEqual((r.pl_accesses(), r.dmas), ([], []), "nothing of the design touched, nothing sent")

    def test_of_two_gates_that_fail_the_first_is_the_one_the_run_stops_at(self) -> None:
        for faults, status in (("ctrl,seu", 0x101), ("seu,lpbk", 0x105), ("lpbk,nodone", 0x102), ("nodone,dcache", 0x103), ("dcache,lvl", 0x104), ("fpgarst,pll", 0x111)):
            with self.subTest(faults=faults):
                r = Run(fault=faults)
                self.assertEqual((r.rc, r.status, r.n_records, r.pl_accesses()), (status, status, 0, []))
        r = Run(fault="seu")
        self.assertEqual(r.plb[4:8], [0, 0, 0, 0], "the SLCR is not read once a gate before it has failed")
        r = Run(fault="pll")
        self.assertEqual(r.plb[4:8], [0xF, 0, 0x00400800, 0x3B], "and all four of its words are recorded when it is read")

    def test_a_read_that_fails_ends_the_run_there(self) -> None:
        r = Run(fault="err@12")                       # a transfer of the first state's reads ends with an error bit
        self.assertEqual((r.rc, r.status, r.violations), (0x221, 0x221, []))
        self.assertEqual(r.stop_record, r.n_records - 1)
        self.assertEqual(r.rec(r.n_records - 1)["code"], 0x21)
        marks = [i for i, (kind, _, _) in enumerate(r.entries) if kind == st.A_MARK]
        before_first_mark = 1 + sum(1 for kind, _, _ in r.entries[:marks[0]] if kind != st.A_MARK)
        self.assertEqual(len(r.pl_log()), before_first_mark, "no entry after the mark was made")

    def test_bit_5_is_recorded_and_cleared_alone_as_in_stage_eight(self) -> None:
        r = Run(fault="bit5@2")                       # the second frame read: the first read of the list
        self.assertEqual((r.rc, r.status, r.violations), (0, 1, []))
        rec = r.rec(2)
        self.assertEqual((rec["after"] & SEU_ERR, rec["cleared"] & SEU_ERR, rec["cleared"] != 0xFFFFFFFF), (SEU_ERR, 0, True))
        self.assertEqual([v for k, a, v in r.accesses if k == "W" and a == INT_STS and v == SEU_ERR], [SEU_ERR])
        self.assertEqual(r.rec(3)["cleared"], 0xFFFFFFFF, "where it did not show nothing was cleared")
        stays = Run(fault="bit5@2,bit5stays")
        self.assertEqual((stays.rc, stays.status), (0, 1), "a bit 5 that does not clear is recorded; it is no error of a transfer")
        self.assertEqual(stays.rec(2)["cleared"] & SEU_ERR, SEU_ERR)

    def test_the_register_is_looked_at_after_every_read_of_the_stage(self) -> None:
        """An error bit that appears once a read's last transfer was seen done: after the reference frame at first
        (command 5), CTL0 before the first state (9), a read of the list (14), CTL0 after the last state and the
        reference frame at the end — each ends the run at that read, with the read's own record saying so."""
        probe = Run()
        last = len(probe.dmas)                          # the last command of the run: the cleanup of the final reference read
        for d, status, records in ((5, 0x621, 1), (9, 0x221, 2), (14, 0x221, 3), (last - 5, 0x221, probe.n_records - 1), (last, 0x221, probe.n_records)):
            with self.subTest(command=d):
                r = Run(fault=f"lateerr@{d}")
                self.assertEqual((r.rc, r.status, r.violations, r.n_records), (status, status, [], records))
                self.assertEqual(r.rec(r.n_records - 1)["code"], 0x21)

    def test_a_reference_frame_that_cannot_be_read_or_that_changed(self) -> None:
        r = Run(fault="err@2")                        # the first reading of the reference frame
        self.assertEqual((r.rc, r.status, r.n_records, r.pl_accesses()), (0x621, 0x621, 1, []), "a baseline stop; nothing of the design touched")
        probe = Run()
        frames = sum(1 for e in probe.dmas if int(e[5].split("=")[1]) > 1)
        r = Run(fault=f"flip@{frames}")               # the last frame read of the run: the reference frame at the end, with one bit changed
        self.assertEqual((r.rc, r.status, r.violations, r.n_records, r.stop_record), (0x300, 0x300, [], probe.n_records, probe.n_records - 1))
        self.assertEqual(r.raw(r.n_records - 1)[10], 0, "its flag says it is not the frame read at first")
        self.assertEqual(probe.raw(probe.n_records - 1)[10], 1)

    def test_a_read_of_the_list_says_which_state_it_was_made_in_and_reads_what_the_list_says(self) -> None:
        r = Run(reads=[(0xA00, 1), (0xA01, 2), (0xA03, 3)])
        got = [(x["far"], x["n"], x["state"], x["op"], len(x["frames"])) for x in (r.rec(i) for i in range(2, 2 + 3 * r.n_states))]
        self.assertEqual(got, [(far, n, s, k, n) for s in range(r.n_states) for k, (far, n) in enumerate([(0xA00, 1), (0xA01, 2), (0xA03, 3)])])

    def test_an_error_bit_after_a_read_or_after_the_clearing_ends_the_run(self) -> None:
        for fault, code in (("lateerr@14", 0x21), ("bit5@2,clearerr", 0x21)):   # command 14: the last transfer of the first read of the list
            with self.subTest(fault=fault):
                r = Run(fault=fault)
                self.assertEqual((r.rc, r.status, r.violations), (0x200 | code, 0x200 | code, []))


if __name__ == "__main__":
    unittest.main()

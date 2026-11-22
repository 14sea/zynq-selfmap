"""Stage 8 (S2.2) on the host twin — docs/s2_plan.md, section 19.

For each of three states of the probe design's RAM the prober sets the RAM through the design, makes the reads of a
list the host wrote, and reads the RAM through the design again. The device, the design and where the RAM's cells show
in configuration memory are models here (prober/twin_hal.c, and a layout made up below); these tests are about the
prober: what it sends, what it touches, in which order, and where it stops."""
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
import s2_2_judge  # noqa: E402
import s2_2_shares  # noqa: E402
from test_prober_s1b0 import CTRL, DLEN, DST, FRAMES, INT_STS, MCTRL, SLEN, SRC, STATUS, TWIN  # noqa: E402

REC, FARBLK, DATA, FRAME = 480, 68, 76, 101
PLB = 16 + 2 * 1440
HB = 64 + PLB
NONE, OP_CTL0, NO_OP = 15, 0x100, 0xFFFFFFFF
FAR_HEAD, CTL0_HEAD = 0x28002001, 0x2800A001
SLCR = (0xF8000900, 0xF8000240, 0xF8000170, 0xF800010C)
SLCR_WORDS = (0x0000000F, 0x00000000, 0x00400800, 0x0000003F)
PL = 0x40000000
PL_ID, PL_SCRATCH, PL_COUNT, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR, PL_SRL_DATA, PL_WRITES = (PL + off for off in range(0, 0x20, 4))
ID_WORD = 0x53324131
CLEAR_MASK, SEU_ERR = 0x00003000, 0x20                # what stage 8 writes to INT_STS when a transfer begins: the two done bits, and no error bit (section 25)

# ---- a made-up device: block type 0 of two rows. The top row has four columns — of 7, 4, 6 and 30 frames, the last
# holding the three frames with a known content — the bottom row two, of 5 and 3. After the last frame of a row the
# address register stands still for a step, as the board's does. None of this is the part's; it is small.
COLUMNS = [("top", 0, 20, 0xA00, 7), ("top", 0, 21, 0xA80, 4), ("top", 0, 22, 0xB00, 6), ("top", 0, 23, 0xB80, 30),
           ("bottom", 0, 20, 0x400A00, 5), ("bottom", 0, 21, 0x400A80, 3)]
LO, HI, REF = 0xA00, 0x400A82, 0xB99
NAMED_AFTER = 0x00800000                               # what the register reads after the last frame of all
STILL = {0xB9D: 0xFFF0, 0x400A82: 0xFFF1}              # the last frame of each row -> a place with no address of its own


def census() -> dict:
    """The made-up device as a census has it: the entries in the order the register names them, and the rows."""
    entries = [{"far": f"{base + m:#010x}", "block_type": 0, "half": half, "row": row, "column": col, "minor": m}
               for half, row, col, base, n in COLUMNS for m in range(n)]
    entries.append({"far": f"{NAMED_AFTER:#010x}", "block_type": 1, "half": "top", "row": 0, "column": 0, "minor": 0})   # what follows block type 0
    return {"entries": entries, "rows": [{"last": f"{last:#010x}", "ended_by": "the register stood still"} for last in STILL]}


def successors() -> tuple[str, str]:
    """The same device for the twin: which address follows which where it is not the next number, and what the
    register shows at the two places that have no address."""
    order = [base + m for _, _, _, base, n in COLUMNS for m in range(n)] + [NAMED_AFTER]
    succ: list[tuple[int, int]] = []
    for a, b in zip(order, order[1:]):
        if a in STILL:
            succ += [(a, STILL[a]), (STILL[a], b)]
        elif b != a + 1:
            succ.append((a, b))
    return ",".join(f"{a:x}:{b:x}" for a, b in succ), ",".join(f"{p:x}:{a:x}" for a, p in STILL.items())


LAY = s2_2_shares.layout(census())
READS = s2_2_shares.shares(census())[0]                # the whole made-up device is one share: 20 reads, 55 frames
N_LIST = len(READS)


def ram_map(seed: int = 1, cells: int = 256, inverted: int = 0, twice: int = 0) -> list[tuple[int, int, int, int, int, int]]:
    """Where the cells of the RAM show: (RAM address, memory, frame address, word, bit, inverted). Made up, and made
    up differently for every seed: the first `cells` cells of the RAM, each at a place of its own somewhere in the
    frames the list reads — but not in the reference frame, which the run reads before the RAM is written and after;
    `inverted` of them shown inverted; `twice` of them shown at a second place as well."""
    fars = [far + j for far, n in READS for j in range(n) if far + j != REF]
    x = seed * 2654435761 % 2 ** 32
    used: set[tuple[int, int, int]] = set()
    out = []

    def place() -> tuple[int, int, int]:
        nonlocal x
        while True:
            x = (x * 1103515245 + 12345) % 2 ** 31
            p = (fars[x % len(fars)], (x >> 8) % FRAME, (x >> 16) % 32)
            if p not in used:
                used.add(p)
                return p
    for c in range(cells):
        out.append((c // 4, c % 4, *place(), 1 if c < inverted else 0))
    for c in range(twice):
        out.append((c // 4, c % 4, *place(), 0))
    return out


def params(n_list: int = N_LIST, states: tuple = (0, 1, 0), **over) -> list[int]:
    w = [0] * 32
    w[0:10] = [0x31504D53, 1, 8, LO, HI, REF, 0, len(states), 0, 1000]
    w[15] = 2 << 8                                    # the wait that touches no memory
    w[16] = n_list
    w[17] = sum(s << (4 * k) for k, s in enumerate(states))
    w[24], w[25], w[26] = PL, PL + 0x1F, ID_WORD
    w[28:32] = SLCR_WORDS
    for k, v in over.items():
        w[int(k[1:])] = v                             # w7=..., w17=...: a word of the block by its number
    return w


class Run:
    def __init__(self, fault: str = "", reads=None, cells=None, states: tuple = (0, 1, 0), list_words=None, frames=None, **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(scratch_dirs.mkdtemp(prefix="smtwin8_"))
        self.reads = READS if reads is None else reads
        self.cells = ram_map() if cells is None else cells
        self.list = s2_2_shares.list_words(self.reads) if list_words is None else list_words
        self.states = states
        self.params = params(len(self.list), states, **over)
        self.frames = dict(FRAMES if frames is None else frames)
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in self.frames.items()) + "\n")
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in self.params) + "\n")
        (tmp / "list.txt").write_text("\n".join(f"{x:x}" for x in self.list) + "\n")
        (tmp / "rammap.txt").write_text("".join("%d %d %x %d %d %d\n" % c for c in self.cells))
        env = dict(os.environ)
        for name in ("SM_FAULT", "SM_CREG"):
            env.pop(name, None)
        env["SM_FAR_RULE"] = "skip"                   # what the board does: one step for the pad as well
        env["SM_SUCC"], env["SM_SHOWS"] = successors()
        env["SM_LIST"], env["SM_RAMMAP"] = str(tmp / "list.txt"), str(tmp / "rammap.txt")
        if fault:
            env["SM_FAULT"] = fault
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "result.bin")],
                             check=True, capture_output=True, text=True, env=env).stdout
        self.lines = [line.split() for line in out.splitlines()]
        raw = (tmp / "result.bin").read_bytes()
        self.words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        self.rc = int([e for e in self.lines if e[0] == "RC"][0][1], 16)
        self.uart = bytes(int(x, 16) for x in [e for e in self.lines if e[0] == "UART"][0][1:]).decode()
        self.violations = [" ".join(e) for e in self.lines if e[0] == "VIOLATION"]
        self.accesses = [(e[0], int(e[1], 16), int(e[2], 16)) for e in self.lines if e[0] in ("R", "W")]
        self.dmas = [e for e in self.lines if e[0] == "DMA"]
        self.streams = [[int(x, 16) for x in e[1:]] for e in self.lines if e[0] == "STREAM"]
        h = self.words
        self.status, self.n_records, self.n_anomalies, self.total, self.hdr_words, self.stop_record = h[2], h[3], h[4], h[5], h[7], h[18]
        self.plb = self.words[64:HB] if len(self.words) >= HB else []

    def planned(self) -> list[int]:
        return self.params + self.list

    def raw(self, i: int) -> list[int]:
        return self.words[HB + i * REC: HB + (i + 1) * REC]

    def rec(self, i: int) -> dict:
        """One record's words by name. The count of frames is the prober's word and may be anything: no more of
        it is followed than a record has room for (a mutant put the records elsewhere, the word read four
        thousand million, and the list below took the machine's memory — twice, 2026-11-22)."""
        r = self.raw(i)
        return {"far": r[0], "kind": r[1], "code": r[2], "n": r[14], "op": r[15], "state": r[12], "guard": r[13], "cleared": r[10],
                "stream": r[16:59], "regrd": r[59:63], "cleanup": r[63:68], "value": r[FARBLK + 4], "unread": r[FARBLK + 5],
                "after": r[FARBLK + 7], "frames": [r[DATA + FRAME * (j + 1): DATA + FRAME * (j + 2)] for j in range(min(r[14], REC // FRAME) if r[14] != NONE else 0)]}

    def pl_log(self) -> list[tuple[int, bool, int]]:
        return [(self.plb[16 + 2 * i] & ~3, bool(self.plb[16 + 2 * i] & 1), self.plb[17 + 2 * i]) for i in range(self.plb[1])]

    def pl_accesses(self) -> list[tuple[int, bool, int]]:
        return [(a, k == "W", v) for k, a, v in self.accesses if PL <= a < PL + 0x1000]


N = 4 + 3 * N_LIST                                     # the reference frame, CTL0, three passes, CTL0, the reference frame


class StageEight(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run()

    def test_the_made_up_device_is_one_share_of_twenty_reads(self) -> None:
        self.assertEqual((N_LIST, sum(n for _, n in READS)), (20, 55))
        self.assertEqual(READS[:5], [(0xA00, 3), (0xA03, 3), (0xA06, 1), (0xA80, 3), (0xA83, 1)])
        self.assertEqual(s2_2_shares.list_problems(LAY, READS), [])

    def test_it_completes_and_says_so(self) -> None:
        r = self.r
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
        self.assertEqual((r.n_records, r.hdr_words, r.total, len(r.words)), (N, HB, HB + N * REC, HB + N * REC))
        self.assertEqual(r.uart, "SM8 start\r\nSM8 end status=00000001 records=%08x anomalies=00000000 words=%08x\r\n" % (N, r.total))
        self.assertEqual(r.stop_record, 0xFFFFFFFF)

    def test_the_records_are_the_reference_frame_ctl0_the_list_three_times_ctl0_and_the_reference_frame(self) -> None:
        r = self.r
        want = [(2, REF, 1, 0, NO_OP), (0, REF, NONE, 0, OP_CTL0)]
        want += [(0, far, n, s, k) for s in range(3) for k, (far, n) in enumerate(READS)]
        want += [(0, REF, NONE, 3, OP_CTL0), (3, REF, 1, 3, NO_OP)]
        got = [(x["kind"], x["far"], x["n"], x["state"], x["op"]) for x in (r.rec(i) for i in range(N))]
        self.assertEqual(got, want)
        for i in range(N):
            rec = r.rec(i)
            self.assertEqual((rec["code"], rec["guard"], rec["unread"]), (0, 0, 0), f"record {i}")
            self.assertEqual(rec["regrd"], [0x20000000, CTL0_HEAD if rec["op"] == OP_CTL0 else FAR_HEAD, 0x20000000, 0x20000000], f"record {i}")

    def test_the_address_register_after_every_read_is_what_the_layout_says(self) -> None:
        r = self.r
        for i in range(N):
            rec = r.rec(i)
            if rec["op"] != OP_CTL0:
                self.assertEqual(rec["value"], s2_2_shares.register_after(LAY, rec["far"], rec["n"]), f"record {i}")
        last_top = next(i for i in range(N) if r.rec(i)["far"] == 0xB9B)
        self.assertEqual(r.rec(last_top)["value"], 0x400A00, "past the place where the register stands still, into the next row")
        self.assertEqual(r.rec(2 + N_LIST - 1)["value"], NAMED_AFTER)

    def test_ctl0_is_read_before_the_first_state_and_after_the_last_and_reads_no_frame(self) -> None:
        r = self.r
        for i in (1, N - 2):
            rec = r.rec(i)
            self.assertEqual((rec["value"], rec["frames"]), (0x00000501, []))
            self.assertEqual(rec["stream"][9:11], [0x20000000, 0x20000000], "no read command for a frame")

    def test_what_is_touched(self) -> None:
        r = self.r
        reads = {a for k, a, _ in r.accesses if k == "R"}
        writes = {a for k, a, _ in r.accesses if k == "W"}
        self.assertEqual(reads, {CTRL, MCTRL, INT_STS, STATUS, *SLCR, PL_ID, PL_COUNT, PL_RAM_DATA, PL_SRL_DATA, PL_WRITES})
        self.assertEqual(writes, {INT_STS, SRC, DST, SLEN, DLEN, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR})
        self.assertNotIn(PL_SRL_DATA, writes, "a write there shifts: this prober never asks for it")
        self.assertNotIn(PL_SCRATCH, reads | writes)
        self.assertEqual([a for k, a, _ in r.accesses if a in SLCR], list(SLCR), "each SLCR word read once, in order, and none written")
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {CLEAR_MASK}, "bit 5 did not show: nothing but a transfer's own bits is cleared")

    def test_everything_sent_is_read_only_and_no_register_is_read_but_far_and_ctl0(self) -> None:
        r = self.r
        self.assertEqual(len(r.streams), 3 * N)
        heads = set()
        for s in r.streams:
            self.assertEqual(packets.readonly_problems(s, LO, HI, 404), [], s)
            for p in packets.decode(s):
                if p["kind"].startswith("type") and p["op"] == "read" and p["reg_name"] != "FDRO":
                    heads.add((p["reg_name"], p["count"]))
                self.assertFalse(p["kind"].startswith("type") and p["op"] == "write" and p["reg_name"] not in ("CMD", "FAR"), p)
        self.assertEqual(heads, {("FAR", 1), ("CTL0", 1)})

    def test_the_pl_block_is_the_log_of_what_was_done(self) -> None:
        r = self.r
        steps, cuts = s2_2_judge.pl_schedule(ID_WORD, [0, 1, 0])
        self.assertEqual(len(steps), 1 + 64 + 3 * 451)
        self.assertEqual(r.plb[0:4], [0x4C504D53, len(steps), 0, 0xFFFFFFFF])
        self.assertEqual(r.plb[4:8], list(SLCR_WORDS))
        self.assertFalse(any(r.plb[8:16]))
        self.assertFalse(any(r.plb[16 + 2 * len(steps):]))
        log = r.pl_log()
        self.assertEqual(log, r.pl_accesses(), "every access made is logged, in order, and nothing is logged that was not made")
        for i, ((addr, write, value), st) in enumerate(zip(log, steps)):
            self.assertEqual((addr - PL, write), (st["off"], st["write"]), f"access {i}")
            if write:
                self.assertEqual(value, st["value"], f"access {i}")

    def test_the_order_the_ram_is_set_then_the_list_is_read_then_the_ram_is_read_again(self) -> None:
        """Where the accesses to the design lie among the commands sent to PCAP: one stretch before the first state's
        reads begin, and for each state one before its reads and one after them, with nothing of the design in between."""
        r = self.r
        _, cuts = s2_2_judge.pl_schedule(ID_WORD, [0, 1, 0])
        at = [i for i, (k, a, _) in enumerate(r.accesses) if PL <= a < PL + 0x1000]
        dlen = [i for i, (k, a, _) in enumerate(r.accesses) if k == "W" and a == DLEN]
        per_read = lambda n: 5 if n != NONE else 4                # noqa: E731  commands of one read: the session, the frames, the register's two, the cleanup
        cmds = [per_read(r.rec(i)["n"]) for i in range(N)]
        first_of = lambda i: dlen[sum(cmds[:i])]                  # noqa: E731  the access that queues record i's first command
        last_of = lambda i: dlen[sum(cmds[:i + 1]) - 1]           # noqa: E731
        stretch = lambda c: (at[cuts[c][0]], at[cuts[c][1] - 1])  # noqa: E731
        self.assertTrue(last_of(0) < stretch(0)[0] and stretch(0)[1] < first_of(1), "the identification and the shift registers: after the reference frame, before CTL0")
        for s in range(3):
            first, last = 2 + s * N_LIST, 2 + (s + 1) * N_LIST - 1
            before, after = stretch(1 + 2 * s), stretch(2 + 2 * s)
            self.assertTrue(last_of(first - 1) < before[0] and before[1] < first_of(first), f"state {s}: set and read back before its first read")
            self.assertTrue(last_of(last) < after[0] and after[1] < first_of(last + 1), f"state {s}: read again after its last read")
            between = [i for i in at if first_of(first) < i < last_of(last)]
            self.assertEqual(between, [], f"state {s}: nothing of the design is touched while the list is read")

    def test_what_the_design_was_asked_and_answered(self) -> None:
        log = self.r.pl_log()
        self.assertEqual(log[0], (PL_ID, False, ID_WORD))
        ram_writes = [v for a, w, v in log if a == PL_RAM_DATA and w]
        ram_reads = [v for a, w, v in log if a == PL_RAM_DATA and not w]
        self.assertEqual(ram_writes, [0] * 64 + [0xF] * 64 + [0] * 64)
        self.assertEqual(ram_reads, [0] * 128 + [0xF] * 128 + [0] * 128, "each state read back twice: before the list is read and after")
        srl = [v for a, w, v in log if a == PL_SRL_DATA]
        self.assertEqual(len(srl), 4 * 32)
        self.assertEqual(srl[32:], srl[:32] * 3)
        self.assertEqual([v for a, w, v in log if a == PL_WRITES], [64, 128, 192])
        counts = [v for a, w, v in log if a == PL_COUNT]
        self.assertEqual(len(counts), 6)
        self.assertEqual(len(set(counts)), 6)

    def test_the_frames_delivered_show_the_cells_as_the_ram_holds_them(self) -> None:
        r = Run(cells=ram_map(seed=7, inverted=40))
        where = {(far, word, bit): inv for _, _, far, word, bit, inv in r.cells}
        seen = {}
        for s in range(3):
            for k, (far, n) in enumerate(READS):
                for j, frame in enumerate(r.rec(2 + s * N_LIST + k)["frames"]):
                    seen.setdefault(far + j, []).append(frame)
        for (far, word, bit), inv in where.items():
            got = [frame[word] >> bit & 1 for frame in seen[far]]
            self.assertEqual(got, [1, 0, 1] if inv else [0, 1, 0], (hex(far), word, bit))
        for far, frames in seen.items():
            mask = [sum(1 << b for (f, w, b) in where if f == far and w == word) for word in range(FRAME)]
            base = r.frames.get(far, [0] * FRAME)
            for frame in frames:
                self.assertEqual([x & ~m for x, m in zip(frame, mask)], [x & ~m for x, m in zip(base, mask)], hex(far))

    def test_the_status_after_every_read_is_recorded_and_nothing_is_cleared(self) -> None:
        r = self.r
        for i in range(N):
            rec = r.rec(i)
            self.assertEqual(rec["after"] & 0x00F4C864, 0x4, f"record {i}: PCFG_DONE, no error bit, no bit 5 — after every read, of the list or not")
            if rec["kind"] == 0 and rec["op"] != OP_CTL0:
                self.assertEqual(rec["cleared"], 0xFFFFFFFF, f"record {i}")
        self.assertEqual([r.rec(i)["cleared"] for i in (0, 1, N - 2)], [0xFFFFFFFF] * 3)
        self.assertEqual(r.rec(N - 1)["cleared"], 1, "the last record's word is the reference frame's health flag")

    def test_the_wait_is_the_one_asked_for_and_another_is_refused(self) -> None:
        self.assertEqual(Run(w15=1 << 8).status, 1)
        self.assertEqual(Run(w15=0).status, 1)
        self.assertEqual(Run(w15=3 << 8).status, 0x500)

    def test_one_and_two_states(self) -> None:
        for states in ((1,), (1, 0)):
            with self.subTest(states=states):
                r = Run(states=states)
                self.assertEqual((r.status, r.n_records, r.violations), (1, 4 + len(states) * N_LIST, []))
                self.assertEqual([v for a, w, v in r.pl_log() if a == PL_RAM_DATA and w], [x for s in states for x in [0xF * s] * 64])

    def test_a_list_as_long_as_a_list_may_be_fills_the_result_area_and_no_more(self) -> None:
        reads = [(0xB80 + k % 28, 1) for k in range(178)]
        r = Run(reads=reads)
        self.assertEqual((r.status, r.n_records, r.violations), (1, 4 + 3 * 178, []))
        self.assertLessEqual(r.total, 0x40000, "the result area is 1 MiB")
        self.assertGreater(r.total + 3 * REC, 0x40000, "and one read more in each state would not fit")
        self.assertLessEqual(r.plb[1], 1440)


class Bit5(unittest.TestCase):
    def test_where_bit_5_shows_it_is_cleared_alone_and_what_the_register_reads_then_is_kept(self) -> None:
        r = Run("bit5@6")                             # frame reads: 1 the reference frame, 2.. the list; the sixth is read 4 of the list
        i = 2 + 4
        rec = r.rec(i)
        self.assertTrue(rec["after"] & SEU_ERR)
        self.assertEqual(rec["cleared"], rec["after"] & ~SEU_ERR)
        self.assertEqual((r.status, r.violations), (1, []), "bit 5 is not a failure")
        others = [k for k in range(r.n_records) if k != i and r.rec(k)["kind"] == 0 and r.rec(k)["op"] != OP_CTL0]
        self.assertTrue(all(r.rec(k)["cleared"] == 0xFFFFFFFF and not r.rec(k)["after"] & SEU_ERR for k in others))
        writes = [(n, v) for n, (k, a, v) in enumerate(r.accesses) if k == "W" and a == INT_STS and v != CLEAR_MASK]
        self.assertEqual([v for _, v in writes], [SEU_ERR], "one write of that bit and of no other")
        n = writes[0][0]
        self.assertEqual(r.accesses[n - 1][:2], ("R", INT_STS), "straight after the read that showed it")
        self.assertTrue(r.accesses[n - 1][2] & SEU_ERR)
        self.assertEqual(r.accesses[n + 1][:2], ("R", INT_STS), "and the register is read again")

    def test_a_bit_5_that_does_not_clear_is_recorded_so_and_met_again_at_the_next_read(self) -> None:
        r = Run("bit5@6,bit5stays")
        shown = [k for k in range(r.n_records) if r.rec(k)["after"] & SEU_ERR]
        self.assertEqual(shown, list(range(2 + 4, N)), "from the read that raised it to the last read of the run")
        of_list = [k for k in shown if k < 2 + 3 * N_LIST]
        self.assertTrue(all(r.rec(k)["cleared"] & SEU_ERR for k in of_list))
        self.assertEqual(r.rec(N - 2)["cleared"], 0xFFFFFFFF, "after CTL0 nothing is cleared: the bit is recorded and left")
        shown = of_list
        self.assertEqual(r.status, 1)
        self.assertEqual(len([1 for k, a, v in r.accesses if k == "W" and a == INT_STS and v == SEU_ERR]), len(shown))

    def test_bit_5_after_a_read_that_is_not_of_the_list_is_recorded_and_left_for_the_next_read_of_the_list(self) -> None:
        r = Run("bit5@1")                             # the first reading of the reference frame raises it
        self.assertEqual((r.status, r.violations), (1, []))
        self.assertEqual([r.rec(k)["after"] & SEU_ERR for k in (0, 1, 2, 3)], [SEU_ERR, SEU_ERR, SEU_ERR, 0])
        self.assertEqual([r.rec(k)["cleared"] for k in (0, 1)], [0xFFFFFFFF, 0xFFFFFFFF], "nothing is cleared after the reference frame or CTL0")
        self.assertEqual(r.rec(2)["cleared"] & 0x24, 0x4, "the list's first read meets it and clears it")
        self.assertEqual(len([1 for k, a, v in r.accesses if k == "W" and a == INT_STS and v == SEU_ERR]), 1)
        r = Run(f"bit5@{1 + 3 * N_LIST + 1}")         # the last reading of the reference frame: recorded in the last record, whose word 10 is the health flag
        self.assertEqual((r.status, r.rec(N - 1)["after"] & SEU_ERR, r.rec(N - 1)["cleared"], r.words[16] & SEU_ERR), (1, SEU_ERR, 1, SEU_ERR))

    def test_bit_5_is_never_written_unless_a_status_word_showed_it(self) -> None:
        for fault in ("", "bit5@2", "bit5@30,bit5@31"):
            r = Run(fault)
            for n, (k, a, v) in enumerate(r.accesses):
                if k == "W" and a == INT_STS and v != CLEAR_MASK:
                    self.assertEqual(v, SEU_ERR)
                    self.assertTrue(r.accesses[n - 1] [0] == "R" and r.accesses[n - 1][1] == INT_STS and r.accesses[n - 1][2] & SEU_ERR, fault)


class WhenTheDesignDoesNotAnswerAsItMust(unittest.TestCase):
    def stopped(self, fault: str, code: int, records: int) -> Run:
        r = Run(fault)
        self.assertEqual((r.status, r.rc, r.n_records, r.n_anomalies, r.stop_record), (0xA00 | code, 0xA00 | code, records, 0, 0xFFFFFFFF), fault)
        self.assertEqual((r.plb[2], r.plb[3]), (code, r.plb[1]), "the block names the failure and where the log ends")
        self.assertEqual(r.pl_log(), r.pl_accesses())
        last_pl = max(i for i, (k, a, _) in enumerate(r.accesses) if PL <= a < PL + 0x1000)
        self.assertFalse([1 for k, a, _ in r.accesses[last_pl + 1:] if a in (SRC, DST, SLEN, DLEN) or PL <= a < PL + 0x1000],
                         "after the answer that was not so, nothing is sent and nothing of the design is touched")
        return r

    def test_a_ram_that_does_not_hold_its_state_after_the_frames_were_read(self) -> None:
        r = self.stopped("ramdisturb@6", 9, 2 + N_LIST)
        self.assertEqual(r.pl_log()[-1], (PL_RAM_DATA, False, 0x4), "address 9 reads 4 where the state is all zero")
        self.assertEqual(r.pl_log()[-2], (PL_RAM_ADDR, True, 9))

    def test_in_the_second_state(self) -> None:
        r = self.stopped(f"ramdisturb@{1 + N_LIST + 3}", 9, 2 + 2 * N_LIST)
        self.assertEqual(r.pl_log()[-1], (PL_RAM_DATA, False, 0xB))

    def test_in_the_last_state_where_no_state_follows_to_stop_at(self) -> None:
        r = self.stopped(f"ramdisturb@{1 + 2 * N_LIST + 3}", 9, 2 + 3 * N_LIST)
        self.assertEqual(r.pl_log()[-1], (PL_RAM_DATA, False, 0x4))
        self.assertEqual(len(r.dmas), 5 + 4 + 5 * 3 * N_LIST, "CTL0 and the reference frame are not read after it")

    def test_a_ram_that_never_took_the_state_is_another_failure(self) -> None:
        r = self.stopped("ramstuck", 5, 2 + N_LIST)   # one bit never sets: all zero holds, all one does not
        self.assertEqual(r.pl_log()[-1], (PL_RAM_DATA, False, 0xB))
        self.assertEqual(len([1 for e in r.dmas]), 5 + 4 + 5 * N_LIST, "the second state's list is never read")

    def test_the_identification_the_counter_the_shift_registers_the_count_of_writes(self) -> None:
        self.stopped("plid", 2, 1)
        self.stopped("countstuck", 4, 2 + N_LIST)
        self.stopped("srlmoves", 6, 2 + N_LIST)
        self.stopped("plcount", 7, 2 + N_LIST)

    def test_an_envelope_that_leaves_a_register_out_stops_the_helper_and_nothing_is_touched_outside_it(self) -> None:
        r = Run(w25=PL + 0x17)                        # the shift registers' data register and the count of writes lie above
        self.assertEqual((r.status, r.plb[2], r.n_records), (0xA01, 1, 1))
        self.assertTrue(all(a <= PL + 0x17 for a, _, _ in r.pl_accesses()))


class Gates(unittest.TestCase):
    def test_every_gate_stops_the_run_before_anything_is_sent_or_touched(self) -> None:
        for fault, status in (("ctrl", 0x101), ("seu", 0x105), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104),
                              ("lvl", 0x110), ("fpgarst", 0x111), ("fclk", 0x112), ("pll", 0x113)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.status, r.rc, r.n_records, r.dmas, r.pl_accesses(), r.violations), (status, status, 0, [], [], []))
                self.assertEqual((r.plb[0], r.plb[1], r.plb[2], r.plb[3]), (0x4C504D53, 0, 0, 0xFFFFFFFF))
                self.assertEqual(r.total, HB)
                self.assertFalse([1 for k, a, _ in r.accesses if k == "W"], "nothing is written anywhere")
                slcr_read = [a for _, a, _ in r.accesses if a in SLCR]
                self.assertEqual(slcr_read, list(SLCR) if status >= 0x110 else [], "the SLCR is looked at only once the gates before it hold")

    def test_the_order_of_the_gates(self) -> None:
        self.assertEqual(Run("ctrl,seu").status, 0x101)
        self.assertEqual(Run("seu,lpbk").status, 0x105)
        self.assertEqual(Run("lpbk,nodone").status, 0x102)
        self.assertEqual(Run("nodone,dcache").status, 0x103)
        self.assertEqual(Run("dcache,lvl").status, 0x104)
        self.assertEqual(Run("lvl,pll").status, 0x110)


class Parameters(unittest.TestCase):
    def refused(self, name: str, **kw) -> None:
        r = Run(**kw)
        self.assertEqual((r.status, r.rc, r.n_records, r.total), (0x500, 0x500, 0, HB), name)
        self.assertEqual(r.violations, [], f"{name}: and nothing was read that is not the prober's to read — not a word beyond the list's room")
        self.assertEqual(r.accesses, [], f"{name}: refused on form alone: no device register is even read")
        self.assertEqual(r.uart, "SM8 start\r\nSM8 end status=00000500\r\n")
        self.assertEqual((r.plb[0], r.plb[1], r.plb[3]), (0x4C504D53, 0, 0xFFFFFFFF))

    def test_a_block_that_is_not_of_this_form_is_refused(self) -> None:
        for name, kw in (("another version", {"w1": 2}), ("an envelope the wrong way round", {"w3": HI, "w4": LO}),
                         ("a reference frame above the envelope", {"w5": HI + 1}), ("one below it", {"w5": LO - 1}),
                         ("no state", {"w7": 0}), ("no state and none named", {"w7": 0, "w17": 0}), ("four states", {"w7": 4, "w17": 0x0101}),
                         ("a state that is neither all zero nor all one", {"w17": 0x210}),
                         ("a state named beyond the last", {"w17": 0x1010}),
                         ("no poll limit", {"w9": 0}), ("a poll limit beyond every bound", {"w9": 0x10000001}),
                         ("a wait that does not exist", {"w15": 3 << 8}), ("more stack beneath the reads", {"w15": 2 << 8 | 4}),
                         ("an empty list", {"w16": 0}), ("a list longer than a list may be", {"w16": 179}),
                         ("a PL envelope below the design", {"w24": PL - 4}), ("one above it", {"w25": PL + 0x20}),
                         ("one the wrong way round", {"w24": PL + 8, "w25": PL + 4})):
            with self.subTest(name):
                self.refused(name, **kw)

    def test_every_word_the_stage_has_no_use_for_must_be_zero(self) -> None:
        used = {0, 1, 2, 3, 4, 5, 7, 9, 15, 16, 17, 24, 25, 26, 28, 29, 30, 31}
        self.assertEqual(sum(1 << k for k in used), 0xF70382BF)
        for k in sorted(set(range(32)) - used):
            with self.subTest(word=k):
                self.refused(f"word {k}", **{f"w{k}": 1})

    def test_a_list_with_a_read_the_prober_may_not_make_is_refused_before_anything_is_read(self) -> None:
        good = s2_2_shares.list_words(READS)
        for name, at, word in (("no frame", 3, 0xA80), ("four frames", 3, 4 << 28 | 0xA80), ("an address below the envelope", 0, 1 << 28 | (LO - 1)),
                               ("an address above it", 19, 1 << 28 | (HI + 1)), ("a read that runs past the envelope", 19, 3 << 28 | (HI - 1)),
                               ("a count in the top bits", 7, 9 << 28 | 0xB00)):
            with self.subTest(name):
                self.refused(name, list_words=good[:at] + [word] + good[at + 1:])

    def test_a_list_one_read_longer_than_a_list_may_be_is_refused_though_every_read_in_it_is_good(self) -> None:
        self.refused("179 reads", reads=[(0xB80 + k % 28, 1) for k in range(179)])

    def test_only_the_reads_the_block_counts_are_looked_at(self) -> None:
        r = Run(list_words=s2_2_shares.list_words(READS) + [0xFFFFFFFF], w16=N_LIST)
        self.assertEqual((r.status, r.n_records), (1, N))


class TheStatusBetweenTransfers(unittest.TestCase):
    """Review of 0417966 (docs/s2_plan.md, section 22). Stage 8 reads the status register when no transfer is running:
    after every read of the list, and after it has cleared bit 5. Both words were recorded and looked at for bit 5
    alone. They are held to what a transfer's own status is held to — no error bit, PCFG_DONE set — and the run ends at
    the read whose status is not so, with that read's record saying why; nothing is written after it.

    Commands: 1 to 5 the reference frame, 6 to 9 CTL0, then five to a read of the list, the cleanup last."""

    @staticmethod
    def last(k: int, s: int = 0) -> int:
        return 14 + 5 * (s * N_LIST + k)

    def stopped(self, r: Run, i: int, code: int, commands: int, cleared: int = 0) -> dict:
        self.assertEqual((r.status, r.rc, r.n_records, r.n_anomalies, r.stop_record, r.violations), (0x200 | code, 0x200 | code, i + 1, 1, i, []))
        self.assertEqual(r.rec(i)["code"], code, "the record says what ended the run")
        self.assertEqual(len(r.dmas), commands, "no command follows")
        self.assertEqual(len([1 for k, a, v in r.accesses if k == "W" and a == INT_STS and v != CLEAR_MASK]), cleared)
        raw = r.raw(i)
        own = [raw[3], raw[5], raw[FARBLK], raw[FARBLK + 2], raw[7]]
        self.assertTrue(all(s & 0x4 and not s & 0x00F4C840 for s in own), "none of the read's own transfers shows it")
        return r.rec(i)

    def test_an_error_bit_that_appears_once_the_last_transfer_was_seen_done_ends_the_run_at_that_read(self) -> None:
        for k, s in ((0, 0), (3, 1)):
            with self.subTest(read=k, state=s):
                r = Run(f"lateerr@{self.last(k, s)}")
                rec = self.stopped(r, 2 + s * N_LIST + k, 0x21, self.last(k, s))
                self.assertEqual(rec["after"] & 0x00040004, 0x00040004)
                self.assertEqual(rec["cleared"], 0xFFFFFFFF)
                self.assertEqual(r.words[16] & 0x00040000, 0x00040000, "the register is left as it was found")
        self.assertFalse(Run(f"lateerr@{self.last(0)}").pl_accesses()[1 + 64 + 257:], "and the RAM is not read again")

    def test_pcfg_done_lost_between_the_last_transfer_and_the_status_after_the_read(self) -> None:
        r = Run(f"latedrop@{self.last(4)}")
        rec = self.stopped(r, 6, 0x23, self.last(4))
        self.assertEqual(rec["after"] & 0x00F4C844, 0, "PCFG_DONE is gone and no error bit says so")

    def test_what_the_register_reads_after_bit_5_was_cleared_is_held_to_the_same(self) -> None:
        r = Run("bit5@2,clearerr")                    # frame read 2 is the list's first read
        rec = self.stopped(r, 2, 0x21, self.last(0), cleared=1)
        self.assertEqual((rec["after"] & 0x00040024, rec["cleared"] & 0x00040024), (0x24, 0x00040004))
        r = Run(f"bit5@2,dropafter@{self.last(0)}")   # PCFG_DONE goes at the next write to the register: the clearing
        rec = self.stopped(r, 2, 0x23, self.last(0), cleared=1)
        self.assertEqual((rec["after"] & 0x24, rec["cleared"] & 0x24), (0x24, 0))

    def test_nothing_is_written_after_a_read_that_was_not_clean_bit_5_or_not(self) -> None:
        r = Run(f"bit5@2,lateerr@{self.last(0)}")
        rec = self.stopped(r, 2, 0x21, self.last(0), cleared=0)
        self.assertEqual((rec["after"] & 0x00040024, rec["cleared"]), (0x00040024, 0xFFFFFFFF))
        self.assertEqual(r.words[16] & 0x00040024, 0x00040024, "both bits are still there at the end")
        r = Run("bit5@2,short@2")                     # the read itself is short, and bit 5 shows after it
        self.assertEqual((r.status, r.n_records, r.rec(2)["code"], r.rec(2)["after"] & 0x24, r.rec(2)["cleared"]), (0x400, 3, 0x10, 0x24, 0xFFFFFFFF))
        self.assertFalse([1 for k, a, v in r.accesses if k == "W" and a == INT_STS and v != CLEAR_MASK])

    def test_after_the_reads_that_are_not_of_the_list_as_well_before_the_design_is_touched_again(self) -> None:
        """Review of 334df53: the register was looked at only after a read of the list. An error bit after the last
        transfer of the reference frame or of CTL0 was met by the next transfer — after the design had been read, or
        the RAM written for the first state; after the last read of all it was met by nothing, and the run said done."""
        r = Run("lateerr@5")                          # the reference frame at first
        self.assertEqual((r.status, r.n_records, r.rec(0)["code"], r.rec(0)["after"] & 0x00040000, len(r.dmas), r.pl_accesses()), (0x621, 1, 0x21, 0x00040000, 5, []))
        r = Run("lateerr@9")                          # CTL0 before the first state
        self.assertEqual((r.status, r.n_records, r.stop_record, r.rec(1)["code"], len(r.dmas)), (0x221, 2, 1, 0x21, 9))
        self.assertEqual(len(r.pl_accesses()), 1 + 64, "the design was read before CTL0; nothing of it is touched after")
        self.assertFalse([1 for a, w, _ in r.pl_accesses() if w and a == PL_RAM_DATA], "the RAM is not written")
        r = Run("lateerr@313")                        # CTL0 after the last state
        self.assertEqual((r.status, r.n_records, r.stop_record, r.rec(N - 2)["code"], len(r.dmas)), (0x221, N - 1, N - 2, 0x21, 313))
        r = Run("lateerr@318")                        # the reference frame at the end: the last transfer of the run
        self.assertEqual((r.status, r.n_records, r.stop_record, r.rec(N - 1)["code"], r.rec(N - 1)["cleared"]), (0x221, N, N - 1, 0x21, 0),
                         "not done: the last record has the code, and its health flag is 0")
        r = Run("latedrop@9")
        self.assertEqual((r.status, r.n_records, r.rec(1)["code"], r.rec(1)["after"] & 0x4), (0x223, 2, 0x23, 0))
        self.assertEqual(Run("latedrop@318").status, 0x223)

    def test_a_read_that_failed_by_itself_keeps_its_own_code(self) -> None:
        r = Run(f"short@2,lateerr@{self.last(0)}")
        self.assertEqual((r.status, r.n_records, r.rec(2)["code"], r.rec(2)["after"] & 0x00040000), (0x400, 3, 0x10, 0x00040000))

    def test_a_clean_run_has_a_clean_status_after_every_read_and_every_code_is_zero(self) -> None:
        for fault in ("", "bit5@6", "bit5@6,bit5stays"):
            r = Run(fault)
            self.assertEqual((r.status, [r.rec(i)["code"] for i in range(N)]), (1, [0] * N), fault)



class WhenATransferBegins(unittest.TestCase):
    """Reviews of 9fa606e and 334df53 (docs/s2_plan.md, sections 23 and 25). Every transfer begins by clearing bits of
    the status register. The stages up to 7 clear the error bits with the two done bits, so an error bit that appeared
    after the transfer before was seen done is cleared without having been read. Section 23 had stage 8 read the
    register before that write; an error bit that appeared between the read and the write was still cleared. Now
    stage 8 clears the done bits alone and never an error bit: one that shows after the clearing stood there before
    the transfer was to begin — code 0x24, the transfer not queued, the bit left where it is.

    Commands: 1 to 5 the reference frame, 6 to 9 CTL0, 10 to 14 the list's first read; a clean run makes 318."""

    def stopped(self, r: Run, status: int, i: int, made: int, transfer: int) -> None:
        self.assertEqual((r.status, r.rc, r.n_records, r.stop_record if status >> 8 == 2 else i, r.violations), (status, status, i + 1, i, []))
        raw = r.raw(i)
        own = [(raw[3], raw[4]), (raw[5], raw[6]), (raw[FARBLK], raw[FARBLK + 1]), (raw[FARBLK + 2], raw[FARBLK + 3]), (raw[7], raw[8])]
        self.assertEqual(raw[2], 0x24)
        self.assertEqual((own[transfer][0] & 0x00043004, own[transfer][1]), (0x00040004, 0), "the transfer that was to begin has the word — the done bits cleared, the error bit not — and no poll")
        self.assertTrue(all(pair == (0, 0) for pair in own[transfer + 1:]), "and none after it has anything")
        self.assertEqual(len(r.dmas), made, "it was not queued, and no command follows")
        writes = [v for k, a, v in r.accesses if k == "W" and a == INT_STS]
        self.assertEqual(writes, [CLEAR_MASK] * (made + 1), "its own clearing of the done bits is the last write to the register")
        self.assertEqual(r.words[16] & 0x00040000, 0x00040000, "and the bit is still there at the end")

    def test_an_error_bit_that_appears_after_a_transfer_was_seen_done_ends_the_run_when_the_next_is_to_begin(self) -> None:
        for d in (10, 11, 12, 13):                    # after each transfer of the list's first read but the last
            with self.subTest(after_command=d):
                r = Run(f"lateerr@{d}")
                self.stopped(r, 0x224, 2, d, d - 9)
                self.assertEqual((r.n_anomalies, r.rec(2)["cleared"]), (1, 0xFFFFFFFF))
                self.assertFalse(r.pl_accesses()[1 + 64 + 257:], "and the RAM is not read again")

    def test_an_error_bit_that_appears_just_before_the_register_is_written_is_not_cleared_with_it(self) -> None:
        """The review's case (334df53): the bit set after every status read made before the write that begins a
        transfer. With a read before the write and the error bits in the write, it was cleared and the run passed."""
        for d in (10, 11, 12, 13, 14):                # before the write that begins each transfer of the list's first read
            with self.subTest(before_command=d):
                self.stopped(Run(f"preclear@{d}"), 0x224, 2, d - 1, d - 10)
        self.stopped(Run("preclear@15"), 0x224, 3, 14, 0)             # the first transfer of the next read
        self.stopped(Run("preclear@1"), 0x624, 0, 0, 0)               # the first transfer of the run: nothing was sent at all
        self.stopped(Run("preclear@6"), 0x224, 1, 5, 0)               # CTL0
        self.stopped(Run("preclear@314"), 0x224, N - 1, 313, 0)       # the reference frame at the end

    def test_whichever_wait_is_asked_for(self) -> None:
        """The two transfer routines — the wait as it was, and the one that touches no memory — begin alike."""
        for w15 in (0, 1 << 8, 2 << 8):
            with self.subTest(w15=w15):
                self.stopped(Run("lateerr@11", w15=w15), 0x224, 2, 11, 2)
                self.stopped(Run("preclear@11", w15=w15), 0x224, 2, 10, 1)
                r = Run(w15=w15)
                self.assertEqual((r.status, {v for k, a, v in r.accesses if k == "W" and a == INT_STS}), (1, {CLEAR_MASK}))

    def test_in_a_later_state(self) -> None:
        d = 10 + 5 * (2 * N_LIST + 7) + 1             # the frame read of read 7 in the third state
        self.stopped(Run(f"lateerr@{d}"), 0x224, 2 + 2 * N_LIST + 7, d, 2)

    def test_in_the_reads_that_are_not_of_the_list(self) -> None:
        self.stopped(Run("lateerr@2"), 0x624, 0, 2, 2)              # the reference frame at first: a baseline stop
        self.stopped(Run("lateerr@7"), 0x224, 1, 7, 3)              # CTL0 before the first state (it has no frame read)
        self.stopped(Run("lateerr@311"), 0x224, N - 2, 311, 3)      # CTL0 after the last
        self.stopped(Run("lateerr@315"), 0x224, N - 1, 315, 2)      # the reference frame at the end

    def test_no_error_bit_is_ever_written_to_the_register(self) -> None:
        for fault in ("", "bit5@6", "bit5@6,bit5stays", "lateerr@11", "preclear@11", "err@11", "drop@11", "timeout@11", "short@4", "lateerr@14", "ramdisturb@6"):
            with self.subTest(fault):
                r = Run(fault)
                self.assertLessEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {CLEAR_MASK, SEU_ERR})
                self.assertEqual(CLEAR_MASK & 0x00F4C840, 0)
                self.assertEqual(r.violations, [])

    def test_a_done_bit_that_does_not_clear_is_another_code(self) -> None:
        r = Run("donestays")                          # the register has D_P_DONE from the load of the design
        self.assertEqual((r.status, r.n_records, r.raw(0)[2], r.raw(0)[3] & 0x00F4D840, r.raw(0)[4], len(r.dmas)), (0x620, 1, 0x20, 0x1000, 0, 0))

    def test_in_a_clean_run_every_transfer_begins_with_the_done_bits_cleared_and_the_register_read(self) -> None:
        r = Run()
        clears = [n for n, (k, a, v) in enumerate(r.accesses) if k == "W" and a == INT_STS]
        self.assertEqual((r.status, len(r.dmas), len(clears)), (1, 318, 318))
        for n in clears:
            self.assertEqual((r.accesses[n][2], r.accesses[n + 1][:2], r.accesses[n + 1][2] & 0x00F4F840), (CLEAR_MASK, ("R", INT_STS), 0))

    def test_how_often_the_register_is_read_between_a_transfer_and_the_next_clearing(self) -> None:
        """Within a read as in the other stages (tests/test_prober_s2.py has theirs: 2, and 3 where a read ends): the
        transfer's two polls. Where a read ends, its look at PCFG_DONE and the status after the read."""
        r = Run()
        queued = [i for i, (k, a, v) in enumerate(r.accesses) if k == "W" and a == 0xF8007024]
        cleared = [i for i, (k, a, v) in enumerate(r.accesses) if k == "W" and a == INT_STS]
        reads = [sum(1 for k, a, v in r.accesses[i + 1:j] if k == "R" and a == INT_STS) for i, j in zip(queued, cleared[1:])]
        self.assertEqual({n: reads.count(n) for n in set(reads)}, {2: 317 - (N - 1), 4: N - 1})

    def test_pcfg_done_lost_between_two_transfers_is_met_by_the_next_as_before(self) -> None:
        r = Run("latedrop@11")
        self.assertEqual((r.status, r.n_records, r.rec(2)["code"], r.raw(2)[FARBLK + 1] > 0), (0x223, 3, 0x23, True), "by the transfer after it, at its first poll")


class WhenAReadFails(unittest.TestCase):
    def test_a_failure_of_the_interface_stops_at_once(self) -> None:
        # commands 1 to 5 are the reference frame's first reading, 6 to 9 the read of CTL0; 10 opens the session of
        # the list's first read, 11 is its frames, 12 and 13 the address register, 14 the cleanup
        for fault, code in (("err@11", 0x21), ("timeout@11", 0x22), ("drop@11", 0x23)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.status, r.rc, r.n_records, r.n_anomalies, r.stop_record), (0x200 | code, 0x200 | code, 3, 1, 2))
                self.assertEqual(r.rec(2)["code"], code)
                self.assertEqual(len(r.dmas), 11, "no command follows the failing one")
                self.assertEqual(r.plb[2], 0)
                self.assertFalse([1 for a, _, _ in r.pl_accesses()[1 + 64 + 257:]], "and the RAM is not read again")

    def test_a_short_read_ends_the_run_there_no_anomaly_is_budgeted_for(self) -> None:
        r = Run("short@4")                            # the fourth frame read: read 2 of the list, in the first state
        self.assertEqual((r.status, r.n_records, r.n_anomalies, r.stop_record), (0x400, 5, 1, 4))
        self.assertEqual(r.rec(4)["code"], 0x10)
        self.assertEqual(r.rec(4)["after"] & 0x4, 0x4, "the status after the read is recorded all the same")

    def test_a_pad_that_is_not_zero_and_a_register_read_that_delivers_nothing(self) -> None:
        self.assertEqual((Run("padnz@3").status, Run("padnz@3").rec(3)["code"]), (0x400, 0x11))
        r = Run("farshort@4")                         # register reads: 1 the reference frame, 2 CTL0, 3.. the list
        self.assertEqual((r.status, r.rec(3)["code"], r.rec(3)["unread"]), (0x400, 0x14, 1))

    def test_a_failure_at_ctl0(self) -> None:
        r = Run("farshort@2")
        self.assertEqual((r.status, r.n_records, r.n_anomalies, r.stop_record), (0x400, 2, 1, 1))
        self.assertEqual(len([1 for a, w, _ in r.pl_accesses() if a == PL_RAM_DATA]), 0, "no state is set after it")

    def test_a_reference_frame_that_fails_at_first_or_has_changed_at_the_end(self) -> None:
        r = Run("short@1")
        self.assertEqual((r.status, r.n_records, r.pl_accesses()), (0x610, 1, []))
        last = 1 + 3 * sum(1 for _ in READS) + 1      # the last frame read of all
        r = Run(f"flip@{last}")
        self.assertEqual((r.status, r.n_records, r.stop_record, r.rec(N - 1)["cleared"]), (0x300, N, N - 1, 0))

    def test_a_reference_frame_that_holds_cells_of_the_ram_is_a_health_stop_if_the_last_state_is_not_the_first(self) -> None:
        """The reference frame is read before the RAM is written and after the last state. With the states of the set
        — all zero last, and a RAM that was loaded all zero — a cell in it changes nothing; with a last state unlike
        what was loaded the frame has changed, and the run says so. (On the board the frame is all zero under the
        design both before and after the RAM was written: S2.1.)"""
        cells = [(0, 0, REF, 10, 3, 0)]
        self.assertEqual(Run(cells=cells).status, 1)
        r = Run(cells=cells, states=(0, 1))
        self.assertEqual((r.status, r.n_records, r.stop_record), (0x300, 4 + 2 * N_LIST, 3 + 2 * N_LIST))

    def test_the_prober_does_not_compare_one_state_s_frames_with_another_s(self) -> None:
        """A frame that reads differently in the second state is what the stage is there to see: no code for it."""
        r = Run(f"flip@{1 + N_LIST + 2}")
        self.assertEqual((r.status, [r.rec(i)["code"] for i in range(N)]), (1, [0] * N))


class WhatTheseTestsReadOfAResult(unittest.TestCase):
    def test_a_count_of_frames_no_record_could_hold_is_not_followed(self) -> None:
        r = Run.__new__(Run)                          # no run: only the words, and a count that is not a count
        r.words = [0] * HB + [0] * 14 + [0xFFFFFFFE] + [0] * (REC - 15)
        self.assertLessEqual(len(r.rec(0)["frames"]), REC // FRAME)
        r.words[HB + 14] = 2
        self.assertEqual([len(f) for f in r.rec(0)["frames"]], [FRAME, FRAME])


if __name__ == "__main__":
    unittest.main()

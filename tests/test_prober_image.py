"""The board image of the prober: what a host run cannot show, and the values fixed before a board run."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "prober"
DEVICE_ADDRESSES = {0xF8007000, 0xF800700C, 0xF8007014, 0xF8007018, 0xF800701C, 0xF8007020, 0xF8007024, 0xF8007080,
                    0xE000102C, 0xE0001030, 0xE0001000}
# S2.1 (docs/s2_plan.md, section 7): four registers of the SLCR, read as gates and never written. Until 2026-11-20 the
# image held no address of the SLCR at all.
SLCR_READ = {0xF8000900, 0xF8000240, 0xF8000170, 0xF800010C}
# constants that are data, not addresses: status masks, configuration words, the sentinel, the two magics, the PCAP endpoint
# (0x00F4D844: the error bits with D_P_DONE and PCFG_DONE — the three tests that end the quiet wait, made in one)
CONSTANTS = {0x00F4C840, 0x00F4F840, 0x00F4D844, 0x28006000, 0x28002001, 0x30002001, 0x30008001, 0x480000CA, 0xAA995566,
             0xA5A55A5A, 0x31504D53, 0x31524D53, 0xFFFFFFFF}
# S2.0 and S2.1: the three read headers (IDCODE, CTL0, STAT); the magic of the PL block; the sentinel's complement, one
# of the four words written to the design's scratch register; and the list of the design's registers the prober may
# write, one bit an offset (0x04, 0x0c, 0x10, 0x14)
CONSTANTS_S2 = {0x28018001, 0x2800A001, 0x2800E001, 0x4C504D53, 0x5A5AA5A5, 0x00111010}
# S2.2: which words of the parameter block stage 8 has a use for, one bit a word (P8_USED)
CONSTANTS_S2_2 = {0xF70382BF}
PL_BASE = 0x40000000


class Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "all"], check=True)
        cls.dis = (BUILD / "prober.dis").read_text()
        cls.size = (BUILD / "prober.size").read_text()
        cls.bin = (BUILD / "prober.bin").read_bytes()
        rows = re.findall(r"^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+(.*)$", cls.dis, re.M)
        cls.insns = [text.strip() for _, text in rows if not text.strip().startswith(".word")]
        cls.literals = [int(word, 16) for word, text in rows if text.strip().startswith(".word")]

    def test_the_entry_is_the_first_instruction_at_the_load_address(self) -> None:
        self.assertIn("02000000 <selfmap_entry>:", self.dis)

    def test_no_section_needs_startup_code(self) -> None:
        sections = {line.split()[0] for line in self.size.splitlines() if line.startswith(".")}
        self.assertEqual(sections - {".ARM.attributes"}, {".text", ".rodata"}, "a .data or .bss section would need initialising")

    def test_r9_is_read_once_and_never_written(self) -> None:
        r9 = [i for i in self.insns if re.search(r"\b(r9|sb)\b", i.split("@")[0])]
        self.assertEqual(len(r9), 1, r9)
        self.assertRegex(r9[0], r"^mov\s+r\d+, (r9|sb)$")

    def test_no_privileged_or_coprocessor_instruction_but_the_one_sctlr_read(self) -> None:
        mnemonics = [i.split()[0] for i in self.insns]
        for forbidden in ("mcr", "msr", "cps", "cpsid", "cpsie", "svc", "smc", "wfi", "wfe", "bkpt", "ldc", "stc"):
            self.assertNotIn(forbidden, mnemonics)
        self.assertFalse([m for m in mnemonics if re.match(r"^(v|f)[a-z]", m)], "floating point: U-Boot leaves the VFP off")
        mrc = [i for i in self.insns if i.startswith("mrc")]
        self.assertEqual(len(mrc), 1, mrc)
        self.assertRegex(mrc[0].replace("\t", " "), r"^mrc\s+15, 0, r\d+, cr1, cr0, \{0\}")

    def body(self, name: str) -> list[str]:
        """The instructions of one function, in order, comments and literal words dropped."""
        text = self.dis.split(f"<{name}>:\n", 1)[1].split("\n\n", 1)[0]
        rows = [line.split("\t", 2)[2].split("@")[0].strip() for line in text.splitlines() if line.count("\t") >= 2]
        return [" ".join(r.split()) for r in rows if not r.startswith(".word")]

    def test_the_wait_that_stores_nothing_touches_no_memory_while_the_transfer_runs(self) -> None:
        """Section 20. Read from the machine code, since no result can show it: from the write that queues the command
        to the way out of the loop there is no store and nothing addressed through the stack pointer; the one load
        through a register is the limit, made only when a place to read it from was passed."""
        b = self.body("queue_and_wait_quiet")
        self.assertRegex(b[0], r"^push \{")
        queue = [i for i, x in enumerate(b) if x.startswith("bl ") and "<hal_wr>" in x]
        self.assertEqual(len(queue), 1, "one register write: the one that queues the command")
        stores = [i for i, x in enumerate(b) if re.match(r"^(str|stm|push)", x)]
        self.assertEqual(len(stores), 2, "the registers saved on entry, the count stored on the way out")
        self.assertEqual(stores[0], 0)
        self.assertRegex(b[stores[1]], r"^str r\d, \[r\d\]$")
        self.assertRegex(b[stores[1] + 1], r"^pop \{.*pc\}$")
        back = [i for i, x in enumerate(b) if re.match(r"^b(cc|ne|eq|hi|ls|cs)? ", x) and f"<queue_and_wait_quiet+" in x
                and int(x.split("+0x")[1].rstrip(">"), 16) // 4 < i]
        self.assertEqual(len(back), 1, "one loop")
        self.assertLess(queue[0], back[0]); self.assertLess(back[0], stores[1], "the store comes after the loop")
        waiting = b[queue[0]:stores[1]]
        self.assertFalse([x for x in waiting if re.search(r"\bsp\b|\bfp\b|\[r1[0-5]", x)], "nothing through the stack pointer")
        loads = [x for x in waiting if x.startswith("ld")]
        self.assertEqual(sorted(re.sub(r"#\d+", "#N", x) for x in loads), ["ldr r0, [pc, #N]", "ldrne r3, [r5]"],
                         "the address of the status register, from the code; and the limit, if a place was given")
        self.assertIn("cmp r5, #0", waiting[waiting.index("ldrne r3, [r5]") - 1])
        self.assertEqual([x for x in waiting if x.startswith("bl ")][1:], ["bl 2000020 <hal_rd>"], "and the only call polls the status register")

    def test_the_wait_as_it_was_and_the_slot_the_quiet_one_is_given(self) -> None:
        """dma(): its own loop still makes two stores through registers and one load from the caller's stack on every
        poll; the place handed to the quiet wait for the limit is that same slot, and only for the variant that asks."""
        b = self.body("dma")
        pushed = len(re.match(r"^push \{(.*)\}$", b[0]).group(1).split(","))
        slot = f"[sp, #{4 * pushed}]"                      # the first argument passed on the stack: the poll limit
        target = lambda i: int(b[i].split("+0x")[1].rstrip(">"), 16) // 4  # noqa: E731
        back = [i for i, x in enumerate(b) if x.startswith("b ") and "<dma+" in x and target(i) < i]
        last = max(back, key=target)                       # the others jump back to the common way out, which lies before the loop
        self.assertEqual([i for i in back if target(i) == target(last)], [last], "one loop")
        loop = b[target(last): last]
        self.assertLess(len(loop), 20)
        self.assertEqual(loop[1], "bl 2000020 <hal_rd>")
        self.assertEqual([re.sub(r"r\d", "rX", x) for x in loop if x.startswith("str")], ["str rX, [rX]", "str rX, [rX]"])
        self.assertEqual([x.split(", ", 1)[1] for x in loop if x.startswith("ldr") and "[pc" not in x], [slot])
        call = [i for i, x in enumerate(b) if "<queue_and_wait_quiet>" in x]
        self.assertEqual(len(call), 1)
        prev = max(i for i, x in enumerate(b[:call[0]]) if x.startswith("bl "))
        self.assertIn("<hal_wr>", b[prev], "the register write before it (the source length; the wait itself queues the command)")
        before = b[prev + 1: call[0]]
        self.assertTrue([x for x in before if re.match(r"^cmp r\d, #1$", x)], "the choice of the wait, in whichever register the compiler keeps it")
        self.assertIn(f"addeq r1, sp, #{4 * pushed}", before, "the variant that still loads the limit is given the slot dma()'s own loop reads")
        self.assertTrue([x for x in before if re.match(r"^movne r1, r\d$", x)], "the other is given none")

    def test_every_literal_in_the_image_is_accounted_for(self) -> None:
        """Each word the compiler placed in a literal pool is one of: an address inside the image, an address inside
        the prober's four DDR areas, a device register on the list, or a known data constant. Nothing else. Since
        S2.1 the list has four registers of the SLCR (read only: the next test), and the image reaches into the PL —
        through one place, which the test after that holds."""
        self.assertGreater(len(self.literals), 20)
        for value in self.literals:
            ok = (0x02000000 <= value < 0x02008000 or 0x10000000 <= value < 0x10400000
                  or value in DEVICE_ADDRESSES or value in SLCR_READ or value in CONSTANTS or value in CONSTANTS_S2 or value in CONSTANTS_S2_2)
            self.assertTrue(ok, f"{value:#010x} is not accounted for")
        pl = [f"{v:#010x}" for v in self.literals if 0x40000000 <= v < 0xC0000000 and v not in CONSTANTS | CONSTANTS_S2 | CONSTANTS_S2_2]
        self.assertFalse(pl, "no word of a literal pool is an address in the PL: the few that lie in that range are the data constants above")

    def function_of(self, address: int) -> str:
        starts = [(int(a, 16), name) for a, name in re.findall(r"^([0-9a-f]{8}) <(\w+)>:", self.dis, re.M)]
        return max((a, name) for a, name in starts if a <= address)[1]

    def test_an_address_in_the_slcr_or_the_pl_is_formed_in_one_place_each(self) -> None:
        """Read from the machine code. The base of the PL is formed by one instruction, in the function every access
        to the PL goes through; an address of the SLCR comes from one literal, in the function that makes the four gate
        reads (the compiler derives the other three from it), and that function writes none of them: every write it
        makes to a device register goes through hal_wr with an address that is not of the SLCR — which the twin's log
        holds for every run (tests/test_prober_s2.py)."""
        rows = re.findall(r"^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(.*)$", self.dis, re.M)
        pl = [(int(at, 16), text) for at, text in rows if re.search(r"#1073741824|0x40000000", text) and not text.strip().startswith(".word")]
        self.assertEqual(len(pl), 1, pl)
        self.assertEqual(self.function_of(pl[0][0]), "pl_access")
        self.assertRegex(pl[0][1].split("@")[0].strip(), r"^add\s+(r\d+|sl|fp|ip), (r\d+|sl|fp|ip), #1073741824$")   # a register by number or by its other name
        slcr = [int(at, 16) for at, text in rows if text.strip().startswith(".word") and int(text.split()[1], 16) in SLCR_READ]
        self.assertEqual(len(slcr), 1, [f"{a:#x}" for a in slcr])
        self.assertEqual(self.function_of(slcr[0]), "sm_run")
        other = [text for at, text in rows if not text.strip().startswith(".word") and re.search(r"@ 0xf8000[0-9a-f]{3}\b", text)
                 and int(re.search(r"@ (0x[0-9a-f]+)", text).group(1), 16) not in SLCR_READ | {0xF8000000}]
        self.assertFalse(other, "no other address of the SLCR is formed by an instruction")

    def test_expected_values_are_written_for_the_board_run(self) -> None:
        known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
        params = [0] * 32
        params[0:10] = [0x31504D53, 1, 1, 0xB98, 0xB9A, 0xB99, 3, 3, 4, 0x00200000]
        params[16:19] = [0xB98, 0xB99, 0xB9A]
        records = 1 + 3 * 3 + 1
        expected = {
            "stage": "S1a", "image": "prober.bin", "image_bytes": len(self.bin),
            "image_sha256": hashlib.sha256(self.bin).hexdigest(), "image_crc32": f"{zlib.crc32(self.bin) & 0xFFFFFFFF:08x}",
            "load_address": "0x02000000", "result_address": "0x10000000", "param_address": "0x10100000",
            "pl_design": known["pl_design"],
            "params": [f"{w:08x}" for w in params],
            "records": records, "result_words": 64 + records * 266,
            "console": ["SM1 start", "SM1 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (records, 64 + records * 266)],
            "return_code": 0,
            "frames": {far: v["frame_sha256"] for far, v in known["frames"].items()},
        }
        (BUILD / "expected.json").write_text(json.dumps(expected, indent=1) + "\n")
        # stage 2 (S1b.0): the same image; one frame at 0xb98, one at 0xb99, three from 0xb98, each followed by a FAR read
        p2 = [0] * 32
        p2[0:10] = [0x31504D53, 1, 2, 0xB98, 0xB9A, 0xB99, 3, 3, 4, 0x00200000]
        p2[10] = 1 | 1 << 4 | 3 << 8
        p2[16:19] = [0xB98, 0xB99, 0xB98]
        e2 = dict(expected, stage="S1b.0", params=[f"{w:08x}" for w in p2], result_words=64 + records * 480,
                  console=["SM2 start", "SM2 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (records, 64 + records * 480)])
        (BUILD / "expected_s1b0.json").write_text(json.dumps(e2, indent=1) + "\n")
        # stage 3 (S1b.0b): the same image again. Eight operations on the known frames — one frame (as in S1b.0), the pad
        # alone, no read at all, two frames — to see what the FAR register holds after each. Count 0 is the pad alone, 15 no read.
        ops3 = [(0xB98, 1), (0xB98, 0), (0xB98, 15), (0xB99, 0), (0xB98, 2), (0xB9A, 0), (0xB99, 15), (0xB98, 0)]
        p3 = [0] * 32
        p3[0:10] = [0x31504D53, 1, 3, 0xB98, 0xB9A, 0xB99, len(ops3), 3, 24, 0x00200000]      # budget: every target read may be anomalous
        for k, (far, n) in enumerate(ops3):
            p3[16 + k] = far
            p3[10 + k // 8] |= n << (4 * (k % 8))
        rec3 = 1 + len(ops3) * 3 + 1
        e3 = dict(expected, stage="S1b.0b", params=[f"{w:08x}" for w in p3], records=rec3, result_words=64 + rec3 * 480,
                  console=["SM3 start", "SM3 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (rec3, 64 + rec3 * 480)])
        (BUILD / "expected_s1b0b.json").write_text(json.dumps(e3, indent=1) + "\n")
        # stage 4 (S1b.1): the walk of the column of the known frames, from its minor 0, twice. How many records there
        # will be is what the run is to find out, so no record count, size or console line is fixed here.
        p4 = [0] * 32
        p4[0:10] = [0x31504D53, 1, 4, 0xB80, 0xBFF, 0xB99, 1, 2, 0, 0x00200000]
        p4[12], p4[13], p4[16] = 64, 16, 0xB80                      # at most 64 frames a pass; the reference every 16; the start
        e4 = {k: v for k, v in expected.items() if k not in ("records", "result_words", "console", "frames")}
        e4.update(stage="S1b.1", params=[f"{w:08x}" for w in p4])
        (BUILD / "expected_s1b1.json").write_text(json.dumps(e4, indent=1) + "\n")
        # S1b.1 with the wait that touches no memory while a transfer runs (docs/s1b_plan.md, sections 22 and 23): the
        # walk's own parameter block with that wait chosen in word 15, and nothing else changed
        p4r = list(p4); p4r[15] = 2 << 8
        # S1b.2 (docs/s1b_plan.md, section 25): the walk in a chain of runs along the row. The envelope is every address
        # whose block type, half and row fields are zero (UG470's layout of the address word); the reference frame, the
        # passes, the limit and the wait are those of s1b1r. The starting address is the one word that differs from run
        # to run: this file holds the first run's, address 0; the run script puts in each later one.
        p5 = list(p4r); p5[3], p5[4], p5[16] = 0x00000000, 0x0001FFFF, 0x00000000
        (BUILD / "expected_s1b2.json").write_text(json.dumps(dict(e4, stage="S1b.2, one run of the chain", params=[f"{w:08x}" for w in p5]), indent=1) + "\n")
        # S1b.3a (docs/s1b_plan.md, section 35): one run of the walk across the end of the row. s1b2's set with the
        # envelope widened to block type 0 whole, one standstill a pass allowed (word 10), and the start fixed at the
        # last frame of the chain's last accepted run. Nothing of it is given at run time.
        p6 = list(p5); p6[4], p6[10], p6[16] = 0x007FFFFF, 1, 0x00001B80
        (BUILD / "expected_s1b3a.json").write_text(json.dumps(dict(e4, stage="S1b.3a, one run across the end of the row", params=[f"{w:08x}" for w in p6]), indent=1) + "\n")
        # S1b.3 (docs/s1b_plan.md, section 38): the chain over block type 0. s1b3a's set with the start given at run
        # time by the chain; this file holds the first run's, address 0.
        p7 = list(p6); p7[16] = 0x00000000
        (BUILD / "expected_s1b3.json").write_text(json.dumps(dict(e4, stage="S1b.3, one run of the chain over block type 0", params=[f"{w:08x}" for w in p7]), indent=1) + "\n")
        # S1b.4a (docs/s1b_plan.md, section 46): one run of the walk into block type 1. s1b3's set with two words
        # changed: the start fixed at the address the device named after the last frame of block type 0, and the
        # envelope's upper end at the last address whose block type field is 1 (UG470's layout of the address word).
        # The envelope still begins at 0: the prober wants the reference frame inside it. Nothing is given at run time.
        p8 = list(p7); p8[4], p8[16] = 0x00FFFFFF, 0x00800000
        (BUILD / "expected_s1b4a.json").write_text(json.dumps(dict(e4, stage="S1b.4a, one run into block type 1", params=[f"{w:08x}" for w in p8]), indent=1) + "\n")
        # S1b.4 (docs/s1b_plan.md, section 49): the chain over block type 1. s1b4a's parameter block word for word; what
        # differs is that the run script takes its starting address at run time, from the chain. This file holds the
        # first run's: the address the device named after block type 0.
        p9 = list(p8)
        (BUILD / "expected_s1b4.json").write_text(json.dumps(dict(e4, stage="S1b.4, one run of the chain over block type 1", params=[f"{w:08x}" for w in p9]), indent=1) + "\n")
        # S1b.5a (docs/s1b_plan.md, section 58): one run of the walk into block type 2. s1b4a's set with two words
        # changed: the start fixed at the address the device named after the last frame of block type 1, and the
        # envelope's upper end at the last address whose block type field is 2. Nothing is given at run time.
        p10 = list(p8); p10[4], p10[16] = 0x017FFFFF, 0x01000000
        (BUILD / "expected_s1b5a.json").write_text(json.dumps(dict(e4, stage="S1b.5a, one run into block type 2", params=[f"{w:08x}" for w in p10]), indent=1) + "\n")
        # S1b.5 (docs/s1b_plan.md, section 62): the chain over block type 2. s1b5a's parameter block word for word; what
        # differs is that the run script takes its starting address at run time, from the chain. This file holds the
        # first run's: the address the device named after block type 1.
        p11 = list(p10)
        (BUILD / "expected_s1b5.json").write_text(json.dumps(dict(e4, stage="S1b.5, one run of the chain over block type 2", params=[f"{w:08x}" for w in p11]), indent=1) + "\n")
        # S1b.6a (docs/s1b_plan.md, section 65): one run of the walk at the address the device named after the last
        # frame of block type 2. s1b5a's set with two words changed: the start fixed at that address, and the
        # envelope's upper end at the last address whose block type field is 3. Nothing is given at run time.
        p12 = list(p10); p12[4], p12[16] = 0x01FFFFFF, 0x01800000
        (BUILD / "expected_s1b6a.json").write_text(json.dumps(dict(e4, stage="S1b.6a, one run at the address named after block type 2", params=[f"{w:08x}" for w in p12]), indent=1) + "\n")
        (BUILD / "expected_s1b1r.json").write_text(json.dumps(dict(e4, stage="S1b.1, quiet wait", params=[f"{w:08x}" for w in p4r]), indent=1) + "\n")
        # S1b.2b (docs/s1b_plan.md, section 29): the end of the row, by the table-driven stage in its stage-5 form with
        # the wait that touches no memory. The addresses are the last ones the device named in the row (S1b.2, run 30);
        # none above 0x1ba9 is written, and no read asks for more than three frames. Fixed tables: nothing is given at
        # run time.
        #   s1b2e: at each of 0x1ba6..0x1ba9 the pad alone, and the pad and one, two, three frames; each three times.
        #   s1b2c: column 55 again, 0x1b80..0x1ba9 in fourteen reads of three frames; each twice.
        for name, what, ops, repeats in (("s1b2e", "S1b.2b, the end of the row", [(0x1BA6 + k // 4, k % 4) for k in range(16)], 3),
                                         ("s1b2c", "S1b.2b, column 55 again", [(0x1B80 + 3 * k, 3) for k in range(14)], 2)):
            pe = [0] * 32
            pe[0:10] = [0x31504D53, 1, 5, 0x00000000, 0x0001FFFF, 0xB99, len(ops), repeats, 0, 0x00200000]   # no anomaly is budgeted for
            for k, (far, n) in enumerate(ops):
                pe[16 + k] = far
                pe[10 + k // 8] |= n << (4 * (k % 8))
            pe[15] = 2 << 8                                             # the wait that touches no memory; no extra stack
            rec_e = 1 + len(ops) * repeats + 1
            (BUILD / f"expected_{name}.json").write_text(json.dumps(dict(
                e4, stage=what, params=[f"{w:08x}" for w in pe], records=rec_e, result_words=64 + rec_e * 480,
                console=["SM5 start", "SM5 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (rec_e, 64 + rec_e * 480)]), indent=1) + "\n")
        # two parameter sets for stage 2, to count frame reads until the receive FIFO overflows (the run stops at the
        # first interface failure): sixteen operations, eight repeats — 128 reads of one frame over the three known
        # frames in turn, or 128 reads of all three in one read. How far a run gets is what it is to find out.
        for name, ops in (("rate1", [(0xB98 + k % 3, 1) for k in range(16)]), ("rate3", [(0xB98, 3)] * 16)):
            pr = [0] * 32
            pr[0:10] = [0x31504D53, 1, 2, 0xB98, 0xB9A, 0xB99, 16, 8, 4, 0x00200000]
            for k, (far, n) in enumerate(ops):
                pr[16 + k] = far
                pr[10 + k // 8] |= n << (4 * (k % 8))
            er = {k: v for k, v in expected.items() if k not in ("records", "result_words", "console")}
            er.update(stage=name, params=[f"{w:08x}" for w in pr])
            (BUILD / f"expected_{name}.json").write_text(json.dumps(er, indent=1) + "\n")
        # the same count for the pair of reads the walk makes at each frame: the pad alone, then the frame, at one address
        # (stage 3). Eight pairs over the three known frames, eight repeats: 64 pairs in a run.
        pp = [0] * 32
        pp[0:10] = [0x31504D53, 1, 3, 0xB98, 0xB9A, 0xB99, 16, 8, 24, 0x00200000]
        for k in range(16):
            pp[16 + k] = 0xB98 + (k // 2) % 3
            pp[10 + k // 8] |= (k % 2) << (4 * (k % 8))             # even places: the pad alone (0); odd places: one frame
        ep = {k: v for k, v in expected.items() if k not in ("records", "result_words", "console")}
        ep.update(stage="ratep", params=[f"{w:08x}" for w in pp])
        (BUILD / "expected_ratep.json").write_text(json.dumps(ep, indent=1) + "\n")
        # and the same pairs at 0xb80..0xb87, the first eight addresses of the walk
        pw = list(pp)
        pw[3] = 0xB80
        for k in range(16):
            pw[16 + k] = 0xB80 + k // 2
        ew = dict(ep, stage="ratew", params=[f"{w:08x}" for w in pw])
        (BUILD / "expected_ratew.json").write_text(json.dumps(ew, indent=1) + "\n")
        pf = list(pw); pf[7] = 1                                    # one repeat: each frame read once
        (BUILD / "expected_ratef.json").write_text(json.dumps(dict(ew, stage="ratef", params=[f"{w:08x}" for w in pf]), indent=1) + "\n")
        # diagnostics (docs/s1b_plan.md, section 17). dxw*: the walk, kept to the 26 addresses it has already read
        # (envelope 0xb80..0xb99), with more stack beneath its reads. dxs*: stage 5 — the reads of the walk's first pass,
        # the pad alone then the frame at each of those 26 addresses, made by the stage-3 loop — with more stack likewise.
        # A trailing n or r (section 20): the same set with the loop that waits for a transfer changed, and nothing else —
        # n: nothing stored until the transfer is over; r: nothing stored and nothing loaded. Made for the two sets whose
        # reads lay where the overflows fell: the walk as it was, and stage 5 at the depth of the walk's reference reads.
        for extra, poll, name in ((0, 0, "dxw0"), (6, 0, "dxw6"), (8, 0, "dxw8"), (0, 1, "dxw0n"), (0, 2, "dxw0r")):
            pd = list(p4); pd[4] = 0xB99; pd[15] = extra | poll << 8
            (BUILD / f"expected_{name}.json").write_text(json.dumps(dict(e4, stage=name, params=[f"{w:08x}" for w in pd]), indent=1) + "\n")
        for extra, poll, name in ((0, 0, "dxs0"), (10, 0, "dxs10"), (18, 0, "dxs18"), (10, 1, "dxs10n"), (10, 2, "dxs10r")):
            ps = [0] * 32
            ps[0:10] = [0x31504D53, 1, 5, 0xB80, 0xB99, 0xB99, 1, 1, 24, 0x00200000]
            ps[14], ps[15], ps[16] = 26, extra | poll << 8, 0xB80
            (BUILD / f"expected_{name}.json").write_text(json.dumps(dict(e4, stage=name, params=[f"{w:08x}" for w in ps]), indent=1) + "\n")
        # S2.0 (docs/s2_plan.md, section 6): the table-driven stage with the register read after each operation chosen
        # by the host. The carrier loaded, the three known frames the envelope. Four operations, each three times: the
        # reference frame and then the FAR register (the control: the rule of S1b.0); and, with no frame read at all,
        # one word of IDCODE, of CTL0 and of STAT. The wait that touches no memory. No anomaly is budgeted for.
        p20 = [0] * 32
        p20[0:10] = [0x31504D53, 1, 6, 0xB98, 0xB9A, 0xB99, 4, 3, 0, 0x00200000]
        p20[10] = 1 | 15 << 4 | 15 << 8 | 15 << 12                 # one frame; then three times no read
        p20[12] = 0 | 1 << 4 | 2 << 8 | 3 << 12                    # FAR, IDCODE, CTL0, STAT
        p20[15] = 2 << 8
        p20[16:20] = [0xB99] * 4
        rec20 = 1 + 4 * 3 + 1
        (BUILD / "expected_s2_0.json").write_text(json.dumps(dict(
            e4, stage="S2.0, three more registers read through PCAP", params=[f"{w:08x}" for w in p20], records=rec20, result_words=64 + rec20 * 480,
            frames=expected["frames"],
            console=["SM6 start", "SM6 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (rec20, 64 + rec20 * 480)]), indent=1) + "\n")
        # S2.1 (section 7): the same stage with user logic between the reference frame's first reading and the register
        # reads. The design is s2a, not the carrier: what is loaded is taken from the record its build wrote, and no
        # frame has a known content. The second envelope is the design's eight registers; the four SLCR words are the
        # ones recorded on this board on 2026-11-13 (evidence/ret2uboot_17A6_2026-11-13/RESULT.md).
        design = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
        built = json.loads((ROOT / "pl" / "s2a" / "build.json").read_text())
        p21 = [0] * 32
        p21[0:10] = [0x31504D53, 1, 7, 0xB98, 0xB9A, 0xB99, 3, 3, 0, 0x00200000]
        p21[10] = 15 | 15 << 4 | 15 << 8
        p21[12] = 1 | 2 << 4 | 3 << 8                              # IDCODE, CTL0, STAT
        p21[15] = 2 << 8
        p21[16:19] = [0xB99] * 3
        p21[24], p21[25], p21[26] = PL_BASE, PL_BASE + 0x1F, int(design["id"], 16)
        p21[28:32] = [0x0000000F, 0x00000000, 0x00400800, 0x0000003F]
        rec21, plb = 1 + 3 * 3 + 1, 16 + 2 * 1280
        e21 = {k: v for k, v in e4.items() if k != "pl_design"}
        (BUILD / "expected_s2_1.json").write_text(json.dumps(dict(
            e21, stage="S2.1, the path to user logic and the design from its own side", params=[f"{w:08x}" for w in p21],
            pl_design={"sha256": built["bitstream"]["sha256"], "bytes": built["bitstream"]["bytes"], "file": "build/pl/s2a.bit", "card_name": "s2a.bit",
                       "note": "the probe design s2a (pl/s2a), built here and loaded as an opaque file"},
            records=rec21, result_words=64 + plb + rec21 * 480,
            console=["SM7 start", "SM7 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (rec21, 64 + plb + rec21 * 480)]), indent=1) + "\n")
        # S2.2 (section 19): stage 8 — the gates and the second envelope of S2.1; block type 0 whole, as the census has
        # it, as the envelope; three states of the design's RAM: all zero, all one, all zero. The set has no list of
        # reads: a run is of one share of the census's addresses, which the run script adds (s1a_run.with_share), and
        # with it the number of records and what the console must show.
        census = json.loads((ROOT / "census" / "frame_census_17A6.json").read_text())
        block0 = [int(e["far"], 16) for e in census["entries"] if e["block_type"] == 0]
        p22 = [0] * 32
        p22[0:10] = [0x31504D53, 1, 8, min(block0), max(block0), 0xB99, 0, 3, 0, 0x00200000]
        p22[15] = 2 << 8
        p22[17] = 0x010                                             # all zero, all one, all zero
        p22[24], p22[25], p22[26] = PL_BASE, PL_BASE + 0x1F, int(design["id"], 16)
        p22[28:32] = [0x0000000F, 0x00000000, 0x00400800, 0x0000003F]
        e22 = {k: v for k, v in e21.items() if k not in ("frames", "records", "result_words", "console")}
        (BUILD / "expected_s2_2.json").write_text(json.dumps(dict(
            e22, stage="S2.2, the RAM in readback: block type 0 in three states, a share a run", params=[f"{w:08x}" for w in p22],
            pl_design={"sha256": built["bitstream"]["sha256"], "bytes": built["bitstream"]["bytes"], "file": "build/pl/s2a.bit", "card_name": "s2a.bit",
                       "note": "the probe design s2a (pl/s2a), built here and loaded as an opaque file"}), indent=1) + "\n")
        # No part of the memory map bounds the image: it is loaded at 0x02000000 and the next thing above it is the PL
        # design at 0x04000000. The bound is a guard against an image that has grown by accident; it was 16 KiB until
        # stage 8 (16,360 bytes) came within 24 bytes of it.
        self.assertLess(len(self.bin), 32768)


if __name__ == "__main__":
    unittest.main()

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
# constants that are data, not addresses: status masks, configuration words, the sentinel, the two magics, the PCAP endpoint
# (0x00F4D844: the error bits with D_P_DONE and PCFG_DONE — the three tests that end the quiet wait, made in one)
CONSTANTS = {0x00F4C840, 0x00F4F840, 0x00F4D844, 0x28006000, 0x28002001, 0x30002001, 0x30008001, 0x480000CA, 0xAA995566,
             0xA5A55A5A, 0x31504D53, 0x31524D53, 0xFFFFFFFF}


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
        self.assertIn("cmp r4, #1", before)
        self.assertIn(f"addeq r1, sp, #{4 * pushed}", before, "the variant that still loads the limit is given the slot dma()'s own loop reads")
        self.assertTrue([x for x in before if re.match(r"^movne r1, r\d$", x)], "the other is given none")

    def test_every_literal_in_the_image_is_accounted_for(self) -> None:
        """Each word the compiler placed in a literal pool is one of: an address inside the image, an address inside
        the prober's four DDR areas, a device register on the list, or a known data constant. Nothing else — in
        particular no address in the PL (0x4000_0000..0xBFFF_FFFF) and none in the SLCR (0xF800_0xxx)."""
        self.assertGreater(len(self.literals), 20)
        for value in self.literals:
            ok = (0x02000000 <= value < 0x02004000 or 0x10000000 <= value < 0x10400000
                  or value in DEVICE_ADDRESSES or value in CONSTANTS)
            self.assertTrue(ok, f"{value:#010x} is not accounted for")

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
        (BUILD / "expected_s1b1r.json").write_text(json.dumps(dict(e4, stage="S1b.1, quiet wait", params=[f"{w:08x}" for w in p4r]), indent=1) + "\n")
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
        self.assertLess(len(self.bin), 16384)


if __name__ == "__main__":
    unittest.main()

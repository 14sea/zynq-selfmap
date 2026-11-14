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
CONSTANTS = {0x00F4C840, 0x00F4F840, 0x28006000, 0x28002001, 0x30002001, 0x30008001, 0x480000CA, 0xAA995566,
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
        self.assertLess(len(self.bin), 16384)


if __name__ == "__main__":
    unittest.main()

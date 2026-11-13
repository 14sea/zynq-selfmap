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
CONSTANTS = {0x00F4C840, 0x00F4F840, 0x28006000, 0x30002001, 0x30008001, 0x480000CA, 0xAA995566,
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
        self.assertLess(len(self.bin), 16384)


if __name__ == "__main__":
    unittest.main()

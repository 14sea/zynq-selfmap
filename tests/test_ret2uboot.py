"""The pre-run check of probes/ret2uboot: nothing in it may reach the PL or write a PS register.

Two independent looks at the same source:
  * the host twin logs every device access the function makes; the log is held to an allow-list
    written here, not derived from the source under test;
  * the board image is inspected for what the twin cannot see: the register U-Boot reserves,
    privileged or coprocessor instructions, and sections that would need startup code.
It also writes build/ret2uboot/expected.json — the image hash and the values the board run must
reproduce — so a board run is compared with numbers fixed before it.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "probes" / "ret2uboot"
BUILD = ROOT / "build" / "ret2uboot"

UART1_SR, UART1_FIFO = 0xE000102C, 0xE0001030
READ_ONLY = {0xF800000C, 0xF8000100, 0xF8000104, 0xF8000108, 0xF800010C, 0xF8000170, 0xF8000240,
             0xF8000900, 0xF8007000, 0xF8007004, 0xF800700C, 0xF8007010, 0xF8007014, 0xF8007080}
CONSOLE = "SMR0 enter\r\nSMR0 exit rc=0\r\n"
BUF_ADDR, BUF_BYTES, PATTERN_AT = 0x10000000, 0x10000, 0x1000


def build() -> None:
    subprocess.run(["make", "-s", "-C", str(SRC), "all"], check=True)


class Twin(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build()
        cls.dump = BUILD / "twin_buf.bin"
        out = subprocess.run([str(BUILD / "ret2uboot_twin"), str(cls.dump)], check=True,
                             capture_output=True, text=True).stdout
        cls.log = [line.split() for line in out.splitlines()]
        cls.buf = cls.dump.read_bytes()

    def test_the_log_is_not_empty_and_the_function_returned_zero(self) -> None:
        self.assertGreater(len(self.log), 50)
        self.assertEqual(self.log[-1], ["RC", "0"])
        self.assertFalse([e for e in self.log if e[0] == "OOB"], "a store outside the buffer")

    def test_the_only_register_written_is_the_console_tx_fifo(self) -> None:
        writes = [int(e[1], 16) for e in self.log if e[0] == "W"]
        self.assertTrue(writes)
        self.assertEqual(set(writes), {UART1_FIFO})

    def test_every_read_is_on_the_allow_list_and_none_reaches_the_pl(self) -> None:
        reads = [int(e[1], 16) for e in self.log if e[0] == "R"]
        self.assertEqual(set(reads) - {UART1_SR}, READ_ONLY)
        for address in reads + [int(e[1], 16) for e in self.log if e[0] == "W"]:
            self.assertFalse(0x40000000 <= address < 0xC0000000, f"{address:#010x} is in the PL address space")

    def test_the_console_text_is_exactly_the_two_lines(self) -> None:
        text = "".join(chr(int(e[2], 16)) for e in self.log if e[0] == "W")
        self.assertEqual(text, CONSOLE)

    def test_the_buffer_header_and_pattern(self) -> None:
        self.assertEqual(len(self.buf), BUF_BYTES)
        words = struct.unpack("<%dI" % (BUF_BYTES // 4), self.buf)
        self.assertEqual(words[0], 0x30524D53)
        self.assertEqual(words[1:4], (1, len(READ_ONLY), 4))
        self.assertEqual({words[4 + 2 * i] for i in range(len(READ_ONLY))}, READ_ONLY)
        for i in (PATTERN_AT // 4, PATTERN_AT // 4 + 1, BUF_BYTES // 4 - 1):
            self.assertEqual(words[i], (0x9E3779B9 * (i + 1)) & 0xFFFFFFFF)


class Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build()
        cls.dis = (BUILD / "ret2uboot.dis").read_text()
        cls.size = (BUILD / "ret2uboot.size").read_text()
        cls.bin = (BUILD / "ret2uboot.bin").read_bytes()
        cls.insns = [m.group(1).strip() for m in re.finditer(r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.*)$", cls.dis, re.M)]

    def test_the_entry_is_the_first_instruction_at_the_load_address(self) -> None:
        self.assertIn("02000000 <selfmap_entry>:", self.dis)

    def test_no_section_needs_startup_code(self) -> None:
        sections = {line.split()[0] for line in self.size.splitlines() if line.startswith(".")}
        self.assertEqual(sections, {".text", ".rodata"}, "a .data or .bss section would need initialising")

    def test_r9_is_read_once_and_never_written(self) -> None:
        r9 = [i for i in self.insns if re.search(r"\b(r9|sb)\b", i.split("@")[0])]
        self.assertEqual(len(r9), 1, r9)
        self.assertRegex(r9[0], r"^mov\s+r\d+, (r9|sb)$")

    def test_no_privileged_or_coprocessor_instruction_but_the_one_sctlr_read(self) -> None:
        mnemonics = [i.split()[0] for i in self.insns]
        for forbidden in ("mcr", "msr", "cps", "cpsid", "cpsie", "svc", "smc", "wfi", "wfe", "bkpt", "ldc", "stc"):
            self.assertNotIn(forbidden, mnemonics)
        self.assertFalse([m for m in mnemonics if m.startswith("v") or m.startswith("f")], "floating point: U-Boot leaves the VFP off")
        mrc = [i for i in self.insns if i.startswith("mrc")]
        self.assertEqual(len(mrc), 1, mrc)
        self.assertRegex(mrc[0].replace("\t", " "), r"^mrc\s+15, 0, r\d+, cr1, cr0, \{0\}")

    def test_it_returns_through_the_link_register(self) -> None:
        self.assertTrue(any(re.match(r"^(pop\s+\{.*pc\}|bx\s+lr)", i) for i in self.insns))

    def test_expected_values_are_written_for_the_board_run(self) -> None:
        twin = (BUILD / "twin_buf.bin")
        if not twin.exists():
            subprocess.run([str(BUILD / "ret2uboot_twin"), str(twin)], check=True, capture_output=True)
        pattern = twin.read_bytes()[PATTERN_AT:]
        expected = {
            "image": "ret2uboot.bin", "image_bytes": len(self.bin), "image_sha256": hashlib.sha256(self.bin).hexdigest(),
            "image_crc32": f"{zlib.crc32(self.bin) & 0xFFFFFFFF:08x}",
            "load_address": "0x02000000", "console": CONSOLE, "return_code": 0,
            "buffer_address": f"{BUF_ADDR:#010x}",
            "pattern": {"address": f"{BUF_ADDR + PATTERN_AT:#010x}", "bytes": f"{len(pattern):#x}",
                        "crc32": f"{zlib.crc32(pattern) & 0xFFFFFFFF:08x}"},
        }
        (BUILD / "expected.json").write_text(json.dumps(expected, indent=1) + "\n")
        self.assertEqual(len(pattern), BUF_BYTES - PATTERN_AT)


if __name__ == "__main__":
    unittest.main()

"""The host side of S1a: the judge, on results produced by the twin, and the run plan."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1a_judge  # noqa: E402
from test_prober_twin import Run  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())


class Judge(unittest.TestCase):
    def test_a_clean_run_passes(self) -> None:
        v = s1a_judge.judge(Run().words, KNOWN)
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(len(v["records"]), 11)
        self.assertTrue(all(r["matches_known"] and r["pad_all_zero"] for r in v["records"]))

    def test_a_frame_that_differs_from_the_known_one_fails_even_if_the_board_saw_nothing_wrong(self) -> None:
        words = list(Run().words)
        words[64 + 266 * 0 + 16 + 43 + 5 + 101 + 9] ^= 1      # one bit of the baseline's frame, as if the device returned it
        v = s1a_judge.judge(words, KNOWN)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("differs from the known frame" in p for p in v["problems"]))

    def test_an_anomalous_or_stopped_run_fails(self) -> None:
        for fault in ("short@2", "err@5", "flip@5", "dcache"):
            with self.subTest(fault):
                self.assertEqual(s1a_judge.judge(Run(fault).words, KNOWN)["verdict"], "FAIL")

    def test_a_recorded_stream_that_is_not_read_only_fails(self) -> None:
        words = list(Run().words)
        words[64 + 266 * 3 + 16 + 5] = 1                     # record 3 claims it sent CMD = WCFG
        v = s1a_judge.judge(words, KNOWN)
        self.assertTrue(any("not read-only" in p and "WCFG" in p for p in v["problems"]))
        words = list(Run().words)
        words[64 + 266 * 2 + 16 + 8] = 0x00400A20            # record 2's stream addresses a frame outside the envelope
        self.assertTrue(any("outside the envelope" in p for p in s1a_judge.judge(words, KNOWN)["problems"]))

    def test_truncated_or_foreign_data_is_invalid(self) -> None:
        self.assertEqual(s1a_judge.judge(Run().words[:500], KNOWN)["verdict"], "INVALID")
        self.assertEqual(s1a_judge.judge([0] * 3000, KNOWN)["verdict"], "INVALID")


class Plan(unittest.TestCase):
    def test_the_dry_run_prints_the_plan_and_opens_no_port(self) -> None:
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--dry-run"], capture_output=True, text=True, check=True).stdout
        self.assertIn("Dry run: nothing was sent.", out)
        cmds = [line.split("#")[0].split(".", 1)[1].strip() for line in out.splitlines() if "#" in line and line.strip()[0].isdigit()]
        verbs = {c.split()[0] for c in cmds}
        self.assertEqual(verbs, {"version", "dcache", "md.l", "mw.l", "loady", "crc32", "fpga", "go", "fatwrite"})
        writes = [c for c in cmds if c.startswith("mw.l")]
        for c in writes:                                     # U-Boot writes: one DEVCFG status clear, the parameter block, the result header
            address = int(c.split()[1], 16)
            self.assertTrue(address == 0xF800700C or 0x10100000 <= address < 0x10100080 or address == 0x10000000, c)
        self.assertEqual([c for c in cmds if c.startswith("go")], ["go 02000000"])
        self.assertLess(cmds.index("dcache off"), cmds.index("go 02000000"))
        self.assertLess(next(i for i, c in enumerate(cmds) if c.startswith("fpga loadb")), cmds.index("go 02000000"))

    def test_the_source_never_imports_a_serial_port_before_the_refusals(self) -> None:
        src = (ROOT / "host" / "s1a_run.py").read_text()
        self.assertLess(src.index("if a.dry_run or not a.go"), src.index("import serial"))


if __name__ == "__main__":
    unittest.main()

"""The run script against a pretend U-Boot whose `go` runs the host twin. What matters here is the host's
behaviour after `go`: whatever the prober reported, the result is saved and pulled before it is judged."""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1a_run  # noqa: E402

TWIN = ROOT / "build" / "prober" / "twin"
KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
PROMPT = b"Zynq> "


class FakeUBoot:
    """Enough of U-Boot for the run script: word memory, md.l / mw.l / crc32, a PL load, `go` (the twin), fatwrite."""

    def __init__(self, fault: str = "", **quirks) -> None:
        self.mem: dict[int, int] = {}
        self.blobs: dict[int, bytes] = {}
        self.int_sts = 0xA802000B
        self.fault, self.q = fault, quirks
        self.commands: list[str] = []
        self.card: dict[str, bytes] = {}

    # ---- the console interface the run script uses
    def interrupt(self, tries: int = 3):
        return PROMPT, True

    def cmd(self, line: str, timeout: float = 10):
        self.commands.append(line)
        w = line.split()
        out = getattr(self, "c_" + w[0].replace(".", "_"))(w)
        return (line + "\r\n" + out).encode() + PROMPT, not (self.q.get("hang_at") == w[0])

    def load(self, loady: str, path: str):
        self.commands.append(loady)
        data = Path(path).read_bytes()
        if self.q.get("corrupt_image") and "02000000" in loady:
            data = data[:-1] + bytes([data[-1] ^ 1])
        self.blobs[int(loady.split()[1], 16)] = data
        return f"## Total Size      = 0x{len(data):08x} = {len(data)} Bytes\r\n".encode() + PROMPT, True

    # ---- memory
    def rd(self, a: int) -> int:
        if a == 0xF800700C:
            return self.int_sts
        return self.mem.get(a, 0)

    def bytes_at(self, a: int, n: int) -> bytes:
        if a in self.blobs and n <= len(self.blobs[a]):
            return self.blobs[a][:n]
        return b"".join(struct.pack("<I", self.rd(a + 4 * i)) for i in range((n + 3) // 4))[:n]

    # ---- commands
    def c_version(self, w): return "U-Boot 2026.04-rc5 (pretend)\r\n"
    def c_dcache(self, w): return "" if len(w) > 1 else ("Data (writethrough) Cache is " + ("ON" if self.q.get("dcache_on") else "OFF") + "\r\n")

    def c_md_l(self, w):
        a, n = int(w[1], 16), int(w[2], 16)
        vals = [self.rd(a + 4 * i) for i in range(n)]
        if self.q.get("corrupt_dump") and n > 64:
            vals[100] ^= 1
        return "".join("%08x: %s    ....\r\n" % (a + 4 * i, " ".join("%08x" % v for v in vals[i:i + 4])) for i in range(0, n, 4))

    def c_mw_l(self, w):
        a, v, n = int(w[1], 16), int(w[2], 16), int(w[3], 16) if len(w) > 3 else 1
        if a == 0xF800700C:
            self.int_sts &= ~v
        else:
            for i in range(n):
                self.mem[a + 4 * i] = v
        return ""

    def c_crc32(self, w):
        a, n = int(w[1], 16), int(w[2], 16)
        return "crc32 for %08x ... %08x ==> %08x\r\n" % (a, a + n - 1, zlib.crc32(self.bytes_at(a, n)) & 0xFFFFFFFF)

    def c_fpga(self, w):
        if not self.q.get("pl_fails"):
            self.int_sts = 0x50021004
        return "  design filename = \"pretend\"\r\n"

    def c_fatload(self, w):
        data = self.card.get(w[4])
        if data is None:
            return "Failed to load '%s'\r\n" % w[4]
        if self.q.get("card_corrupt"):
            data = data[:100] + bytes([data[100] ^ 1]) + data[101:]
        self.blobs[int(w[3], 16)] = data
        return "%d bytes read in 9 ms (1.5 MiB/s)\r\n" % len(data)

    def c_go(self, w):
        for index, value in self.q.get("params_swapped_before_go", {}).items():    # after their crc32 was checked
            self.mem[0x10100000 + 4 * index] = value
        if self.q.get("no_result"):
            return "## Starting application at 0x02000000 ...\r\n## Application terminated, rc = 0x0\r\n"
        tmp = Path(tempfile.mkdtemp(prefix="smrun_"))
        frames = {int(k, 16): [int(x, 16) for x in v["words"]] for k, v in KNOWN["frames"].items()}
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + ws) for far, ws in frames.items()) + "\n")
        (tmp / "params.txt").write_text("\n".join(f"{self.rd(0x10100000 + 4 * i):x}" for i in range(32)) + "\n")
        env = dict(os.environ); env.pop("SM_FAULT", None)
        if self.fault:
            env["SM_FAULT"] = self.fault
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "r.bin")],
                             check=True, capture_output=True, text=True, env=env).stdout.splitlines()
        raw = (tmp / "r.bin").read_bytes()
        for i, v in enumerate(struct.unpack("<%dI" % (len(raw) // 4), raw)):
            self.mem[0x10000000 + 4 * i] = v
        self.twin_result = raw
        uart = bytes(int(x, 16) for x in [e for e in out if e.startswith("UART")][0].split()[1:]).decode()
        rc = int([e for e in out if e.startswith("RC")][0].split()[1], 16) ^ self.q.get("rc_xor", 0)
        if self.q.get("image_changes_during_go"):
            blob = self.blobs[0x02000000]; self.blobs[0x02000000] = blob[:8] + bytes([blob[8] ^ 1]) + blob[9:]
        if self.q.get("done_lost_afterwards"):
            self.int_sts &= ~4
        if self.q.get("error_afterwards"):
            self.int_sts |= 0x00040000
        return "## Starting application at 0x02000000 ...\r\n" + uart + "## Application terminated, rc = 0x%X\r\n" % rc

    def c_fatwrite(self, w):
        if self.q.get("card_fails"):
            return "** Unable to write file s.bin **\r\n"
        a, n = int(w[3], 16), int(w[5], 16)
        self.card[w[4]] = self.bytes_at(a, n)
        return "%d bytes written in 12 ms (1.2 MiB/s)\r\n" % (n - self.q.get("card_short", 0))


def run(fault: str = "", **quirks):
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
    exp = json.loads(s1a_run.EXPECTED.read_text())
    pl = s1a_run.PL.read_bytes()
    out = Path(tempfile.mkdtemp(prefix="smout_"))
    u = FakeUBoot(fault, **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin")
    return rec, u, out


class AfterGo(unittest.TestCase):
    def test_a_clean_run_passes_and_everything_is_saved(self) -> None:
        rec, u, out = run()
        self.assertEqual((rec["verdict"], rec["problems"], rec["judge"]), ("PASS", [], "PASS"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertEqual(u.card["s0000001.bin"], u.twin_result)
        self.assertEqual(rec["host_crc32"], rec["board_crc32"])
        self.assertEqual(json.loads((out / "verdict.json").read_text())["verdict"], "PASS")
        self.assertEqual(u.commands[-1], "version")

    def test_a_run_with_an_anomaly_is_saved_whole_then_judged(self) -> None:
        """The board skipped the anomaly and completed: twelve records, not eleven. The host must take the size from
        the header, save and pull all of it, and only then say FAIL."""
        rec, u, out = run("short@2")
        self.assertEqual(rec["result_words"], 64 + 12 * 266)
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertEqual(len(u.card["s0000001.bin"]), 4 * (64 + 12 * 266))
        self.assertEqual((rec["verdict"], rec["judge"], rec.get("stop")), ("FAIL", "FAIL", None))
        self.assertEqual(rec["return_code"], "0x0")

    def test_an_interface_stop_is_saved_whole_then_judged(self) -> None:
        for fault, records, rc in (("err@5", 2, "0x221"), ("drop@4", 2, "0x223"), ("short@2,flip@3", 3, "0x300"), ("stale", 1, "0x620")):
            with self.subTest(fault):
                rec, u, out = run(fault)
                self.assertEqual((rec["result_words"], rec["return_code"]), (64 + records * 266, rc))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertIn("s0000001.bin", u.card)
                self.assertEqual((rec["verdict"], rec.get("stop")), ("FAIL", None))

    def test_a_gate_stop_on_the_board_is_saved_too(self) -> None:
        rec, u, out = run("lpbk")
        self.assertEqual((rec["result_words"], rec["return_code"], rec["verdict"]), (64, "0x102", "FAIL"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_an_unconfirmed_card_write_fails_the_run_but_the_result_is_still_pulled(self) -> None:
        for quirk in ({"card_fails": True}, {"card_short": 4}):
            with self.subTest(str(quirk)):
                rec, u, out = run(**quirk)
                self.assertEqual((rec["judge"], rec["verdict"], rec["card_written"]), ("PASS", "FAIL", False))
                self.assertTrue(any("card write was not confirmed" in p for p in rec["problems"]))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_the_card_copy_is_checked_by_reading_it_back(self) -> None:
        rec, u, out = run()
        self.assertTrue(rec["card_verified"])
        self.assertIn("fatload mmc 0:1 11000000 s0000001.bin", u.commands)
        rec, u, out = run(card_corrupt=True)                 # U-Boot said it wrote the file; what comes back is not the result
        self.assertEqual((rec["judge"], rec["verdict"], rec["card_written"], rec["card_verified"]), ("PASS", "FAIL", True, False))
        self.assertTrue(any("read back from the card is not the result" in p for p in rec["problems"]))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_a_run_that_did_not_do_what_was_planned_fails(self) -> None:
        """The parameter block is changed after its crc32 was checked: one frame, read once. The three records are
        clean, self-consistent and match the known frame. It is saved whole, and it is not a pass."""
        rec, u, out = run(params_swapped_before_go={6: 1, 7: 1, 16: 0xB99})
        self.assertEqual(rec["result_words"], 64 + 3 * 266)
        self.assertEqual((rec["judge"], rec["verdict"]), ("FAIL", "FAIL"))
        self.assertTrue(any("not the planned ones" in p for p in json.loads((out / "verdict.json").read_text())["problems"]))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_an_image_that_changed_in_ram_during_the_run_fails(self) -> None:
        rec, u, out = run(image_changes_during_go=True)
        self.assertEqual((rec["judge"], rec["verdict"]), ("PASS", "FAIL"))
        self.assertTrue(any("what ran may not be what was checked" in p for p in rec["problems"]))

    def test_the_live_status_afterwards_is_a_condition_not_a_note(self) -> None:
        for quirk in ({"done_lost_afterwards": True}, {"error_afterwards": True}):
            with self.subTest(str(quirk)):
                rec, u, out = run(**quirk)
                self.assertEqual((rec["judge"], rec["verdict"]), ("PASS", "FAIL"))
                self.assertTrue(any("live status after the run" in p for p in rec["problems"]))
                self.assertTrue((out / "result.bin").exists())

    def test_a_pulled_copy_that_differs_from_the_board_is_not_accepted(self) -> None:
        rec, u, out = run(corrupt_dump=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("is not the board's", rec["stop"])
        self.assertFalse((out / "result.bin").exists())
        self.assertTrue((out / "result_unverified.bin").exists())
        self.assertIn("s0000001.bin", u.card, "the card copy was written before the pull")

    def test_a_return_code_or_console_that_contradicts_the_result_fails(self) -> None:
        rec, _, _ = run(rc_xor=1)
        self.assertEqual((rec["judge"], rec["verdict"]), ("PASS", "FAIL"))
        self.assertTrue(any("return code" in p for p in rec["problems"]))

    def test_no_result_header_is_reported_as_such_and_the_header_words_are_kept(self) -> None:
        rec, _, out = run(no_result=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("no result header", rec["stop"])
        self.assertEqual(len((out / "header.bin").read_bytes()), 256)


class BeforeGo(unittest.TestCase):
    def test_any_failed_check_before_go_means_go_is_never_sent(self) -> None:
        for quirk, why in (({"dcache_on": True}, "cache"), ({"pl_fails": True}, "PCFG_DONE"), ({"corrupt_image": True}, "crc32")):
            with self.subTest(str(quirk)):
                rec, u, out = run(**quirk)
                self.assertEqual(rec["verdict"], "FAIL")
                self.assertIn(why, rec["stop"])
                self.assertFalse([c for c in u.commands if c.startswith("go")])
                self.assertFalse(rec.get("went"))

    def test_the_parameters_reach_the_prober_as_fixed(self) -> None:
        rec, u, _ = run()
        exp = json.loads(s1a_run.EXPECTED.read_text())
        self.assertEqual([f"{u.rd(0x10100000 + 4 * i):08x}" for i in range(32)], exp["params"])


class Plan(unittest.TestCase):
    def test_the_dry_run_prints_the_plan_and_cannot_open_a_port(self) -> None:
        """Run with a `serial` module that raises on import: the dry run must not notice."""
        poison = Path(tempfile.mkdtemp(prefix="smpoison_"))
        (poison / "serial.py").write_text("raise RuntimeError('the dry run imported the serial module')\n")
        env = dict(os.environ, PYTHONPATH=str(poison))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--dry-run"], capture_output=True, text=True, check=True, env=env).stdout
        self.assertIn("Dry run: nothing was sent.", out)
        cmds = [line.split("#")[0].split(".", 1)[1].strip() for line in out.splitlines() if "#" in line and line.strip()[0].isdigit()]
        self.assertEqual({c.split()[0] for c in cmds}, {"version", "dcache", "md.l", "mw.l", "loady", "crc32", "fpga", "go", "fatwrite", "fatload"})
        for c in [c for c in cmds if c.startswith("mw.l")]:  # what U-Boot is asked to write: one DEVCFG status clear, the parameter block, the result header
            address = int(c.split()[1], 16)
            self.assertTrue(address == 0xF800700C or 0x10100000 <= address < 0x10100080 or address == 0x10000000, c)
        self.assertEqual([c for c in cmds if c.startswith("go")], ["go 02000000"])
        go = cmds.index("go 02000000")
        self.assertLess(cmds.index("dcache off"), go)
        self.assertLess(next(i for i, c in enumerate(cmds) if c.startswith("fpga loadb")), go)
        self.assertGreater(next(i for i, c in enumerate(cmds) if c.startswith("fatwrite")), go)
        self.assertLess(next(i for i, c in enumerate(cmds) if c.startswith("fatwrite")),
                        max(i for i, c in enumerate(cmds) if c.startswith("md.l 10000000")), "the card copy is written before the pull")

    def test_the_fake_and_the_real_console_share_the_interface_the_script_uses(self) -> None:
        src = (ROOT / "host" / "uboot_console.py").read_text()
        for name in ("def interrupt", "def cmd", "def until_prompt", "def tx"):
            self.assertIn(name, src)


if __name__ == "__main__":
    unittest.main()

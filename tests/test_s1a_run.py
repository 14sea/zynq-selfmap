"""The run script against a pretend U-Boot whose `go` runs the host twin. What matters here is the host's
behaviour after `go`: whatever the prober reported, the result is saved and pulled before it is judged."""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402

TWIN = ROOT / "build" / "prober" / "twin"
KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
PROMPT = b"Zynq> "
# What U-Boot prints when an access raises an exception (as it is generally known; this board has shown none), and what
# this board printed when it started again on 2026-11-19 (evidence/s1b5a_17A6_2026-11-19/precheck_console.log): it
# comes to a prompt by itself, so a restart is followed by a prompt like any reply.
ABORTS = ("data abort\r\npc : [<1ff5e1a4>]\t   lr : [<1ff5e194>]\r\nreloc pc : [<0403a1a4>]\t   lr : [<0403a194>]\r\n"
          "sp : 1eb1ed28  ip : 00000000\t fp : 00000002\r\nFlags: nZCv  IRQs off  FIQs off  Mode SVC_32\r\nCode: e1a04000 e5943000 (e5933000)\r\n"
          "Resetting CPU ...\r\n\r\nresetting ...\r\n")
STARTS_AGAIN = ("U-Boot SPL 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)\r\nSilicon version:\t3\r\nTrying to boot from MMC1\r\n\r\n\r\n"
                "U-Boot 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)\r\n\r\nCPU:   Zynq 7z010\r\nSilicon: v3.1\r\nModel: Ebang EBAZ4203\r\n"
                "DRAM:  ECC disabled 512 MiB\r\nIn:    serial@e0001000\r\nOut:   serial@e0001000\r\nErr:   serial@e0001000\r\n\r\n")


class FakeUBoot:
    """Enough of U-Boot for the run script: word memory, md.l / mw.l / crc32, a PL load, `go` (the twin), fatwrite."""

    def __init__(self, fault: str = "", **quirks) -> None:
        self.mem: dict[int, int] = {}
        self.blobs: dict[int, bytes] = {}
        self.int_sts = 0xA802000B
        self.fault, self.q = fault, quirks
        self.commands: list[str] = []
        self.card: dict[str, bytes] = {}
        if quirks.get("card_has_pl"):
            self.card["carrier.bit"] = s1a_run.PL.read_bytes()
        if quirks.get("card_pl_damaged"):
            pl = s1a_run.PL.read_bytes(); self.card["carrier.bit"] = pl[:5000] + bytes([pl[5000] ^ 1]) + pl[5001:]
        if quirks.get("card_pl_short"):
            self.card["carrier.bit"] = s1a_run.PL.read_bytes()[:-7]

    # ---- the console interface the run script uses
    def interrupt(self, tries: int = 3):
        return PROMPT, True

    def cmd(self, line: str, timeout: float = 10):
        self.commands.append(line)
        w = line.split()
        if len(self.commands) in self.q.get("restarts_at", ()):                    # at the so-manieth thing sent: an exception, the
            return (line + "\r\n" + self.q.get("restart_text", ABORTS + STARTS_AGAIN)).encode() + PROMPT, True   # board starts again and
        out = getattr(self, "c_" + w[0].replace(".", "_"))(w)                      # answers everything after it as if nothing had been
        lose = self.q.get("lossy", {})                                             # replies that lose a stretch of characters, as the
        which = lose.get(line, lose.get(w[0]))                                     # console did on 2026-11-17: by the whole line or by
        if which is not None:                                                      # the command; True: every time, or the numbers of
            self.asked = getattr(self, "asked", {})                                # the times that line is sent (1 is the first)
            self.asked[line] = self.asked.get(line, 0) + 1
            if which is True or self.asked[line] in which:
                out = out[:len(out) // 3] + out[2 * len(out) // 3:]
        return (line + "\r\n" + out).encode() + PROMPT, not (self.q.get("hang_at") == w[0])

    def load(self, loady: str, path: str):
        self.commands.append(loady)
        after = self.q.get("restart_text", STARTS_AGAIN) if len(self.commands) in self.q.get("restarts_after_transfer_at", ()) else ""
        data = Path(path).read_bytes()
        if self.q.get("corrupt_image") and "02000000" in loady:
            data = data[:-1] + bytes([data[-1] ^ 1])
        self.blobs[int(loady.split()[1], 16)] = data
        return (f"## Total Size      = 0x{len(data):08x} = {len(data)} Bytes\r\n" + after).encode() + PROMPT, True   # the size, and then the board starts again

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
        if a == 0x10000000 and n == 64 and not getattr(self, "header_shown", False):  # the first dump of the result header
            self.header_shown = True
            for i, v in self.q.get("header_dump_lies", {}).items():                # a whole dump that is not what is in memory
                vals[i] = v
        # a line as U-Boot prints it, to the character: blanks up to the text column, then a character for each byte
        text = lambda ws: "".join(chr(b) if 0x20 <= b < 0x7F else "." for x in ws for b in struct.pack("<I", x))  # noqa: E731
        lines = [("%08x:%s" % (a + 4 * i, "".join(" %08x" % v for v in vals[i:i + 4]))).ljust(45) + "  " + text(vals[i:i + 4]) + "\r\n" for i in range(0, n, 4)]
        if n > 64:                                                                 # a dump of the result, not of the header
            self.dumps = getattr(self, "dumps", 0) + 1
            bad = self.q.get("corrupt_dump")                                       # True: every dump; a number: the first so many
            if bad is True or (bad and self.dumps <= bad):
                at = min(25, len(lines) - 1)
                if self.q.get("dump_loses_a_line"):
                    del lines[at]                                                  # what the console did on 2026-11-14
                else:
                    lines[at] = lines[at][:10] + ("0" if lines[at][10] != "0" else "1") + lines[at][11:]
        return "".join(lines)

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
        if a == 0x10000000:
            self.result_crcs = getattr(self, "result_crcs", 0) + 1
            if self.q.get("result_changes_before_pull") and self.result_crcs == 2:  # the first was of the whole result, before
                self.mem[0x10000000 + 4 * 70] = self.rd(0x10000000 + 4 * 70) ^ 1    # the card write; this one is of piece 0
        return "crc32 for %08x ... %08x ==> %08x\r\n" % (a, a + n - 1, zlib.crc32(self.bytes_at(a, n)) & 0xFFFFFFFF)

    def c_fpga(self, w):
        if not self.q.get("pl_fails"):
            self.int_sts = 0x50021004
        return "  design filename = \"pretend\"\r\n"

    def c_fatload(self, w):
        data = self.card.get(w[4])
        if data is None:
            return "Failed to load '%s'\r\n" % w[4]
        if self.q.get("card_corrupt") and w[4] != "carrier.bit":
            data = data[:100] + bytes([data[100] ^ 1]) + data[101:]
        self.blobs[int(w[3], 16)] = data
        return "%d bytes read in 9 ms (1.5 MiB/s)\r\n" % len(data)

    def c_go(self, w):
        for index, value in self.q.get("params_swapped_before_go", {}).items():    # after their crc32 was checked
            self.mem[0x10100000 + 4 * index] = value
        if self.q.get("no_result"):
            return "## Starting application at 0x02000000 ...\r\n## Application terminated, rc = 0x0\r\n"
        tmp = Path(scratch_dirs.mkdtemp(prefix="smrun_"))
        frames = {int(k, 16): [int(x, 16) for x in v["words"]] for k, v in KNOWN["frames"].items()}
        frames.update(self.q.get("frames", {}))                                    # stage 4: the rest of a column
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + ws) for far, ws in frames.items()) + "\n")
        (tmp / "params.txt").write_text("\n".join(f"{self.rd(0x10100000 + 4 * i):x}" for i in range(32)) + "\n")
        env = dict(os.environ); env.pop("SM_FAULT", None)
        if self.fault:
            env["SM_FAULT"] = self.fault
        env["SM_FAR_RULE"] = self.q.get("far_rule", "next")
        env.pop("SM_CREG", None)
        env.update(self.q.get("env", {}))                                          # anything else the twin is to be told (S2: SM_CREG)
        # the twin reads 96 successors and 32 such positions and drops the rest without a word (prober/twin_hal.c): a
        # device made up with more would be walked as another device (found 2026-11-19, section 63 of the plan)
        assert len(self.q.get("succ", {})) <= 96 and len(self.q.get("shows", {})) <= 32, "more than the twin's tables hold"
        if "succ" in self.q:                                                       # stage 4: which address follows which
            env["SM_SUCC"] = ",".join(f"{a:x}:{b:x}" for a, b in self.q["succ"].items())
        env.pop("SM_SHOWS", None)
        if "shows" in self.q:                                                      # positions at which the register shows another number
            env["SM_SHOWS"] = ",".join(f"{a:x}:{b:x}" for a, b in self.q["shows"].items())
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "r.bin")],
                             check=True, capture_output=True, text=True, env=env).stdout.splitlines()
        raw = (tmp / "r.bin").read_bytes()
        for i, v in enumerate(struct.unpack("<%dI" % (len(raw) // 4), raw)):
            self.mem[0x10000000 + 4 * i] = v
        self.twin_result = raw
        self.twin_lines = out                                                      # everything the twin said, for tests that look further
        uart = bytes(int(x, 16) for x in [e for e in out if e.startswith("UART")][0].split()[1:]).decode()
        rc = int([e for e in out if e.startswith("RC")][0].split()[1], 16) ^ self.q.get("rc_xor", 0)
        for index, value in self.q.get("header_words_after_go", {}).items():
            self.mem[0x10000000 + 4 * index] = value
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


def run(fault: str = "", stage: str = "s1a", **quirks):
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
    exp = json.loads(s1a_run.STAGES[stage]["expected"].read_text())
    pl = s1a_run.PL.read_bytes()
    out = Path(scratch_dirs.mkdtemp(prefix="smout_"))
    u = FakeUBoot(fault, **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", stage)
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

    def test_a_piece_that_cannot_be_pulled_whole_stops_the_run(self) -> None:
        for how in ({}, {"dump_loses_a_line": True}):
            with self.subTest(str(how)):
                rec, u, out = run(corrupt_dump=True, **how)
                self.assertEqual(rec["verdict"], "FAIL")
                self.assertIn("piece 0 of the result could not be pulled whole in 5 attempts", rec["stop"])
                self.assertIn("the card file holds the result", rec["stop"])
                self.assertFalse((out / "result.bin").exists())
                self.assertEqual([(p["piece"], p["attempt"]) for p in rec["pull"]["repeated"]], [(0, k) for k in (1, 2, 3, 4, 5)])
                self.assertEqual((u.dumps, rec["pull"]["pieces"]), (5, 0), "five attempts at the first piece and no more; nothing further asked for")
                self.assertIn("s0000001.bin", u.card, "the card copy was written before the pull")
                self.assertIsNone(rec.get("judge"), "nothing that is not the board's copy is judged")

    def test_the_result_is_pulled_in_pieces_and_a_damaged_piece_again(self) -> None:
        """2026-11-14: the console lost data in 11 of 28 whole-result pulls. Each piece is checked against the board's own
        crc32 of it and pulled again if it differs; the whole must have the board's crc32 of the result."""
        rec, u, out = run()
        self.assertEqual((rec["verdict"], rec["pull"]), ("PASS", {"piece_words": 2048, "pieces": 2, "repeated": []}))    # 2990 words: 2048 and 942
        self.assertEqual((u.dumps, (out / "result.bin").read_bytes()), (2, u.twin_result))
        for bad, how in ((1, {}), (3, {}), (1, {"dump_loses_a_line": True}), (4, {"dump_loses_a_line": True})):
            with self.subTest(bad=bad, how=str(how)):
                rec, u, out = run(corrupt_dump=bad, **how)
                self.assertEqual((rec["verdict"], rec["problems"], rec.get("stop")), ("PASS", [], None))
                self.assertEqual([(p["piece"], p["attempt"]) for p in rec["pull"]["repeated"]], [(0, k + 1) for k in range(bad)])
                self.assertEqual((u.dumps, rec["pull"]["pieces"]), (2 + bad, 2))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertEqual(rec["host_crc32"], rec["board_crc32"])

    def test_pieces_that_each_match_do_not_make_the_whole_the_board_s(self) -> None:
        """The crc32 of a piece is asked of the board piece by piece; the crc32 of the result was taken once, before the
        card write. If the result in RAM changes in between, every piece matches itself and the whole does not."""
        rec, u, out = run(result_changes_before_pull=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("although each piece matched", rec["stop"])
        self.assertFalse((out / "result.bin").exists())
        self.assertTrue((out / "result_unverified.bin").exists())

    def test_a_return_code_or_console_that_contradicts_the_result_fails(self) -> None:
        rec, _, _ = run(rc_xor=1)
        self.assertEqual((rec["judge"], rec["verdict"]), ("PASS", "FAIL"))
        self.assertTrue(any("return code" in p for p in rec["problems"]))

    def test_sizes_are_believed_only_under_a_valid_magic(self) -> None:
        rec, u, out = run(header_words_after_go={0: 0})      # everything else in the header is consistent
        self.assertEqual((rec["result_layout"], rec["result_words"], rec["verdict"]), (None, s1a_run.MAX_RESULT_WORDS, "FAIL"))
        self.assertTrue(any("no result header" in p for p in rec["problems"]))

    def test_with_no_result_header_everything_a_result_could_occupy_is_still_saved(self) -> None:
        rec, u, out = run(no_result=True)
        self.assertEqual((rec["verdict"], rec.get("stop"), rec["result_layout"]), ("FAIL", None, None))
        self.assertTrue(any("no result header" in p for p in rec["problems"]))
        self.assertEqual(len((out / "header.bin").read_bytes()), 256)
        self.assertEqual(len((out / "result.bin").read_bytes()), 4 * s1a_run.MAX_RESULT_WORDS)
        self.assertEqual(len(u.card["s0000001.bin"]), 4 * s1a_run.MAX_RESULT_WORDS)
        self.assertEqual(json.loads((out / "verdict.json").read_text())["verdict"], "INVALID")


HEADER, STATUS = "md.l 10000000 40", "md.l f800700c 1"
# what a clean run sends more than once: the checksum of the image (before go and after the run), the status word
# (before the load, after the clear, after the load, afterwards), `version` (first and last)
subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "image"], check=True)   # a tree fresh from the repository has no image yet
TWICE_ANYWAY = [f"crc32 02000000 {s1a_run.IMAGE.stat().st_size:x}", STATUS, "version"]   # the image's size as it is built now


def sent(u: FakeUBoot, word: str) -> list[str]:
    return [c for c in u.commands if c.split()[0] == word]


class RepliesNotWhole(unittest.TestCase):
    """The console loses characters. A dump of a few words and a checksum are asked for again when the reply is not
    whole; nothing else is, and a whole reply is never asked for twice whatever it says."""

    def test_what_a_whole_reply_is(self) -> None:
        u = FakeUBoot()
        for i in range(64):
            u.mem[0x10000000 + 4 * i] = 0x1000 + i
        dump = lambda a, n: u.c_md_l(["md.l", f"{a:08x}", f"{n:x}"])  # noqa: E731
        whole = s1a_run.whole
        text = "md.l 10000000 40\r\n" + dump(0x10000000, 64) + "Zynq> "
        self.assertEqual(whole(HEADER, text), [0x1000 + i for i in range(64)])
        lines = dump(0x10000000, 64).splitlines(keepends=True)
        self.assertEqual(len(lines), 16)
        for name, damaged in (("a line missing in the middle", lines[:7] + lines[8:]), ("the last line missing", lines[:15]), ("the first line missing", lines[1:]),
                              ("a word missing from a line", lines[:4] + [lines[4][:19] + lines[4][28:]] + lines[5:]),
                              ("a character missing from a word", lines[:4] + [lines[4][:12] + lines[4][13:]] + lines[5:]),
                              ("a word run together with what follows it", lines[:4] + [lines[4][:45] + "7" + lines[4][45:]] + lines[5:]),
                              ("two lines joined, every word of the join a whole word", lines[:2] + [lines[2][:19] + lines[9][19:]] + lines[10:]),
                              ("every line whole, one of them at another address", lines[:9] + ["1" + lines[9][:7].replace("9", "a") + lines[9][8:]] + lines[10:]),
                              ("a line twice", lines[:6] + [lines[5]] + lines[6:]), ("a line of another dump besides", lines + ["10000100: 00000000\r\n"]),
                              ("nothing", [])):
            with self.subTest(name):
                self.assertIsNone(whole(HEADER, "md.l 10000000 40\r\n" + "".join(damaged) + "Zynq> "))
        self.assertEqual(whole("md.l 10000000 40", dump(0x10000000, 64).replace("    ....", "  " + "." * 16)), [0x1000 + i for i in range(64)], "the characters beside the words are not the words")
        # a dump that does not end with a line of four
        self.assertEqual(whole("md.l 10000004 6", dump(0x10000004, 6)), [0x1001 + i for i in range(6)])
        self.assertIsNone(whole("md.l 10000004 6", dump(0x10000004, 5)))
        self.assertIsNone(whole("md.l 10000004 6", dump(0x10000004, 7)))
        self.assertIsNone(whole("md.l 10000004 6", dump(0x10000004, 8)))
        self.assertEqual(whole(STATUS, "md.l f800700c 1\r\nf800700c: 50033004    .0.P\r\nZynq> "), [0x50033004])
        self.assertIsNone(whole(STATUS, "md.l f800700c 1\r\nf800700c: 5003300    .0.P\r\nZynq> "))
        self.assertIsNone(whole(STATUS, "md.l f800700c 1\r\nf8007008: 50033004    .0.P\r\nZynq> "))
        # a checksum: U-Boot's line for exactly the range asked about
        line = "crc32 for 02000000 ... 02002ec1 ==> 84f107a1\r\n"
        self.assertEqual(whole("crc32 02000000 2ec2", "crc32 02000000 2ec2\r\n" + line + "Zynq> "), "84f107a1")
        for name, damaged in (("of another range", line.replace("02002ec1", "02002ec0")), ("from another address", line.replace("for 02000000", "for 02000004")),
                              ("a character of the checksum missing", line.replace("84f107a1", "84f107a")), ("the range missing", "crc32 for 020 ==> 84f107a1\r\n"),
                              ("only the echo", "")):
            with self.subTest(name):
                self.assertIsNone(whole("crc32 02000000 2ec2", "crc32 02000000 2ec2\r\n" + damaged + "Zynq> "))
        # and no other command has a reply that may be asked for twice
        for cmd in ("go 02000000", "fatwrite mmc 0:1 10000000 s.bin 100", "fatload mmc 0:1 11000000 s.bin", "mw.l 10000000 0 40", "fpga loadb 0 04000000 100",
                    "loady 02000000", "reset", "dcache off", "version", "md.l 10000000", "crc32 10000000 100 10200000", "md.b 10000000 40"):
            with self.subTest(cmd):
                with self.assertRaises(ValueError):
                    whole(cmd, "")

    def test_a_header_dump_that_lost_a_stretch_is_asked_for_again(self) -> None:
        """What stopped run 51 of the chain over block type 0 on 2026-11-17."""
        rec, u, out = run(lossy={HEADER: {1}})
        self.assertEqual((rec["verdict"], rec["problems"], rec.get("stop")), ("PASS", [], None))
        self.assertEqual(rec["replies_not_whole"], [{"cmd": HEADER, "what": "the result header", "attempt": 1}])
        self.assertEqual(u.commands.count(HEADER), 2)
        self.assertEqual((out / "header.bin").read_bytes(), u.twin_result[:256])
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        both = [s for s in rec["steps"] if s["cmd"] == HEADER]
        self.assertEqual([s["what"] for s in both], ["the result header", "the result header (attempt 2 of at most 5: the reply before was not whole)"])
        self.assertLess(len(both[0]["reply"]), len(both[1]["reply"]), "the reply that was not whole is kept among the steps as it came")
        rec, u, out = run(lossy={HEADER: {1, 2, 3, 4}})
        self.assertEqual((rec["verdict"], [r["attempt"] for r in rec["replies_not_whole"]], u.commands.count(HEADER)), ("PASS", [1, 2, 3, 4], 5))

    def test_a_header_that_never_comes_whole_stops_the_run_with_nothing_saved(self) -> None:
        rec, u, out = run(lossy={HEADER: True})
        self.assertEqual((rec["verdict"], rec["stop"], rec["went"]), ("FAIL", "the result header could not be read whole in 5 attempts", True))
        self.assertEqual(u.commands.count(HEADER), 5, "five attempts and no more")
        self.assertEqual([r["attempt"] for r in rec["replies_not_whole"]], [1, 2, 3, 4, 5])
        self.assertEqual((u.commands[-1], sent(u, "fatwrite"), sent(u, "go")), (HEADER, [], ["go 02000000"]))
        self.assertFalse((out / "header.bin").exists() or (out / "result.bin").exists())

    def test_a_clean_run_lists_no_reply_and_repeats_only_what_the_plan_repeats(self) -> None:
        rec, u, _ = run()
        self.assertEqual(rec["replies_not_whole"], [])
        self.assertEqual(sorted(c for c in set(u.commands) if u.commands.count(c) > 1), TWICE_ANYWAY)
        self.assertEqual([u.commands.count(c) for c in TWICE_ANYWAY], [2, 4, 2])

    def test_every_short_read_only_reply_after_go_is_asked_for_again(self) -> None:
        clean, base, _ = run()
        after = base.commands[base.commands.index("go 02000000") + 1:]
        short = [c for c in after if c.startswith("crc32") or c == STATUS]
        self.assertEqual(len(short), 6, "the result, the card copy, two pieces, the status, the image")
        for cmd in short:
            with self.subTest(cmd):
                # the status word is read three times before go and the image's checksum once: the reply that is lost
                # here is the one after the run
                rec, u, out = run(lossy={cmd: {base.commands.count(cmd)}})
                self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
                self.assertEqual([(r["cmd"], r["attempt"]) for r in rec["replies_not_whole"]], [(cmd, 1)])
                self.assertEqual(u.commands.count(cmd), base.commands.count(cmd) + 1)
                self.assertEqual(len(u.commands), len(base.commands) + 1, "that command once more, and nothing else")
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_a_short_reply_that_never_comes_whole_after_go(self) -> None:
        _, base, _ = run()
        crcs = [c for c in base.commands[base.commands.index("go 02000000") + 1:] if c.startswith("crc32")]
        result, card, piece0, piece1, image = crcs
        for cmd, stop, problem, pulled in ((result, "no crc32 of the result from the board", None, False),
                                           (card, None, "read back from the card is not the result", True),
                                           (piece1, "no crc32 of piece 1 of the result from the board", None, False),
                                           (image, None, "the prober image in RAM after the run has crc32 None", True)):
            with self.subTest(cmd):
                # the checksum of the result and of its first piece are the same command when the result is one piece; here it is two
                first = base.commands.count(cmd)             # the image's checksum is asked for once before go: not that one
                rec, u, out = run(lossy={cmd: set(range(first, first + 5))})
                self.assertEqual((rec["verdict"], rec.get("stop")), ("FAIL", stop))
                self.assertEqual(u.commands.count(cmd), first + 4)
                self.assertEqual([(r["cmd"], r["attempt"]) for r in rec["replies_not_whole"]], [(cmd, k) for k in (1, 2, 3, 4, 5)])
                if problem:
                    self.assertTrue(any(problem in p for p in rec["problems"]), rec["problems"])
                self.assertEqual((out / "result.bin").exists(), pulled)
                self.assertEqual(sent(u, "fatwrite") != [], cmd != result, "nothing is saved under a size whose checksum the board never gave")
        self.assertNotEqual(result, piece0)
        rec, u, out = run(lossy={STATUS: {4, 5, 6, 7, 8}})
        self.assertEqual((rec["judge"], rec["verdict"], rec["int_sts_afterwards"], u.commands.count(STATUS)), ("PASS", "FAIL", None, 8))
        self.assertTrue(any("live status after the run is None" in p for p in rec["problems"]))

    def test_before_go_a_reply_that_is_not_whole_is_asked_for_again_and_go_waits_for_it(self) -> None:
        _, base, _ = run()
        before = base.commands[:base.commands.index("go 02000000")]
        checks = [c for c in before if c.startswith("crc32")]
        self.assertEqual(len(checks), 3, "the PL design, the parameter block, the prober image")
        for cmd, times in [(c, {1}) for c in checks] + [(STATUS, {2}), (STATUS, {3})]:      # after the clear; after the load
            with self.subTest(cmd=cmd, times=times):
                rec, u, _ = run(lossy={cmd: times})
                self.assertEqual((rec["verdict"], rec["problems"], len(rec["replies_not_whole"])), ("PASS", [], 1))
                self.assertEqual((u.commands.count(cmd), len(u.commands)), (base.commands.count(cmd) + 1, len(base.commands) + 1))
        for cmd in checks:
            with self.subTest(never=cmd):
                rec, u, _ = run(lossy={cmd: True})
                self.assertEqual((rec["verdict"], rec.get("went")), ("FAIL", None))
                self.assertTrue(rec["stop"].startswith(f"{cmd!r}: crc32 None, expected "), rec["stop"])
                self.assertEqual((u.commands.count(cmd), u.commands[-1], sent(u, "go")), (5, cmd, []))
        rec, u, _ = run(lossy={STATUS: {2, 3, 4, 5, 6}})
        self.assertEqual((rec["verdict"], rec.get("went"), sent(u, "go"), sent(u, "fpga")), ("FAIL", None, [], []))
        self.assertIn("(nothing read)", rec["stop"])
        self.assertEqual(u.commands.count(STATUS), 6, "once to record it, and five attempts after the clear")

    def test_the_status_that_is_only_recorded_is_read_once_whatever_comes_back(self) -> None:
        rec, u, _ = run(lossy={STATUS: {1}})
        self.assertEqual((rec["verdict"], rec["replies_not_whole"], u.commands.count(STATUS)), ("PASS", [], 4))

    def test_a_whole_reply_with_another_value_is_never_asked_for_twice(self) -> None:
        rec, u, _ = run(corrupt_image=True)                  # the checksum of the image in RAM is whole and wrong
        self.assertEqual((rec["verdict"], rec["replies_not_whole"], len(sent(u, "crc32")), sent(u, "go")), ("FAIL", [], 3, []))
        self.assertTrue(u.commands[-1].startswith("crc32 02000000"))
        rec, u, _ = run(pl_fails=True)                       # the status after the load is whole and has the bit clear
        self.assertEqual((rec["verdict"], rec["replies_not_whole"], u.commands.count(STATUS), u.commands[-1]), ("FAIL", [], 3, STATUS))
        for quirk in ({"image_changes_during_go": True}, {"done_lost_afterwards": True}, {"card_corrupt": True}, {"result_changes_before_pull": True}):
            with self.subTest(str(quirk)):
                rec, u, _ = run(**quirk)
                clean = sorted(c for c in set(u.commands) if u.commands.count(c) > 1)
                self.assertEqual((rec["verdict"], rec["replies_not_whole"]), ("FAIL", []))
                self.assertTrue(set(clean) <= set(TWICE_ANYWAY), clean)

    def test_a_command_that_does_something_is_sent_once_whatever_comes_back(self) -> None:
        _, base, _ = run(card_has_pl=True)
        for word, verdict in (("go", "FAIL"), ("fatwrite", "FAIL"), ("fatload", "FAIL"), ("fpga", "PASS"), ("dcache", "FAIL"), ("version", "PASS")):
            with self.subTest(word):
                rec, u, _ = run(card_has_pl=True, lossy={word: True})
                self.assertEqual(rec["verdict"], verdict)
                self.assertEqual(rec["replies_not_whole"], [])
                for c in set(sent(u, word)):               # `version` is in the plan twice, and is sent twice
                    self.assertEqual(u.commands.count(c), base.commands.count(c), c)
                self.assertLessEqual(len(sent(u, word)), len(sent(base, word)))
        rec, u, _ = run(card_has_pl=True, lossy={"go": True})
        self.assertEqual((sent(u, "go"), rec["went"]), (["go 02000000"], True))
        self.assertEqual((rec["judge"], rec["console"]), ("PASS", ["SM1 start"]), "the result is saved, pulled and judged; the console line that was lost is not asked for")
        self.assertEqual(len(rec["problems"]), 1)
        self.assertTrue(rec["problems"][0].startswith("the console showed ['SM1 start'], the result implies "))
        rec, u, _ = run(card_has_pl=True, lossy={"fatwrite": True})
        self.assertEqual((len(sent(u, "fatwrite")), rec["card_written"]), (1, False))
        rec, u, _ = run(card_has_pl=True, lossy={"fatload": True})                 # the card has the design: it is sent instead, and the
        self.assertEqual((rec["pl_source"], rec["card_verified"]), ("ymodem", False))   # copy of the result read back is not confirmed

    def test_a_missing_prompt_is_not_a_reply_to_ask_for_again(self) -> None:
        rec, u, _ = run(hang_at="crc32")
        self.assertEqual((rec["verdict"], len(sent(u, "crc32")), rec["replies_not_whole"], sent(u, "go")), ("FAIL", 1, [], []))
        self.assertIn("no prompt after 'crc32", rec["stop"])

    def test_a_reply_that_shows_an_exception_or_a_restart_stops_the_run_at_whatever_command(self) -> None:
        """Review of 363ad58: such a reply has no dump in it, so it was taken for one that lost characters and asked
        for again; the board, started again, answered, and the run went on to `go`. The pretend board here answers
        everything after its restart as a board would that had lost nothing: only the reply itself can stop the run."""
        _, base, base_out = run(card_has_pl=True)
        places = {}                                               # one place for each kind of command, and each place of the two
        for i, c in enumerate(base.commands, 1):                  # that are read again when not whole
            if c.split()[0] in ("md.l", "crc32") or c.split()[0] not in [k.split()[0] for k in places.values()]:
                places[i] = c
        places = {i: c for i, c in places.items() if c.split()[0] != "loady"}       # a transfer is not a command's reply
        self.assertEqual({c.split()[0] for c in places.values()}, {"version", "dcache", "md.l", "mw.l", "fatload", "crc32", "fpga", "go", "fatwrite"})
        self.assertGreater(len(places), 15)
        for i, c in places.items():
            with self.subTest(c, at=i):
                rec, u, out = run(card_has_pl=True, restarts_at={i})
                self.assertEqual(u.commands, base.commands[:i], "nothing is sent after it, and it is not sent again")
                self.assertEqual((rec["verdict"], rec["replies_not_whole"]), ("FAIL", []))
                self.assertIn(f"U-Boot took an exception or the board started again at {c!r} (its reply has the line 'data abort')", rec["stop"])
                stored = json.loads((out / "run.json").read_text())
                self.assertEqual(stored["steps"][-1]["cmd"], c, "the reply is in the record")
                self.assertEqual(stored["restart"], {"step": len(stored["steps"]), "cmd": c, "line": "data abort"})
                if i <= base.commands.index("go 02000000") + 1:
                    self.assertEqual([p.name for p in out.iterdir()], ["run.json"], "up to and at `go`: nothing is pulled")
                self.assertNotIn("restart", json.loads((base_out / "run.json").read_text()))
                self.assertEqual("went" in rec, i > base.commands.index("go 02000000") + 1)

    def test_each_line_that_says_so_is_enough(self) -> None:
        _, base, _ = run(card_has_pl=True)
        at = base.commands.index(STATUS) + 1
        for text, line in (("data abort\r\n", "data abort"), ("f800700c:prefetch abort\r\n", "f800700c:prefetch abort"),
                           ("undefined instruction\r\n", "undefined instruction"), ("software interrupt\r\n", "software interrupt"),
                           ("Resetting CPU ...\r\n", "Resetting CPU ..."), ("resetting ...\r\n", "resetting ..."),
                           ("U-Boot SPL 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)\r\n", "U-Boot SPL 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)"),
                           ("\r\nU-Boot 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)\r\n\r\n", "U-Boot 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)"),
                           ("Hit any key to stop autoboot:  0 \r\n", "Hit any key to stop autoboot:  0")):
            with self.subTest(line):
                self.assertEqual(s1a_run.restart_seen(STATUS, STATUS + "\r\n" + text + PROMPT.decode()), line)
                rec, u, _ = run(card_has_pl=True, restarts_at={at}, restart_text=text + "f800700c: a802000a    ....\r\n")   # and the word after it, whole
                self.assertEqual((u.commands, rec["verdict"]), (base.commands[:at], "FAIL"))
                self.assertIn(repr(line), rec["stop"])

    def test_a_transfer_that_reports_its_size_and_then_shows_a_restart(self) -> None:
        """Review of 7830797: the reply to a file transfer was held to the size it reports and to nothing else. A reply
        with the right size and the board starting again after it went on to `go`."""
        for card, loady, what in ((True, "loady 02000000", "the prober"), (False, "loady 04000000", "the PL design, which the card does not have")):
            _, base, _ = run(card_has_pl=card)
            at = base.commands.index(loady) + 1
            for text, line in ((STARTS_AGAIN, STARTS_AGAIN.split("\r\n")[0]), (ABORTS + STARTS_AGAIN, "data abort"), ("resetting ...\r\n", "resetting ...")):
                with self.subTest(what, line=line):
                    rec, u, out = run(card_has_pl=card, restarts_after_transfer_at={at}, restart_text=text)
                    self.assertEqual(u.commands, base.commands[:at], "nothing is sent after it")
                    self.assertEqual((rec["verdict"], sent(u, "go"), [p.name for p in out.iterdir()]), ("FAIL", [], ["run.json"]))
                    self.assertIn(f"U-Boot took an exception or the board started again at {loady!r} (its reply has the line {line!r})", rec["stop"])
                    stored = json.loads((out / "run.json").read_text())
                    self.assertEqual(stored["restart"], {"step": len(stored["steps"]), "cmd": loady, "line": line})
                    reply = stored["steps"][-1]["reply"]
                    self.assertRegex(reply, r"^## Total Size      = 0x[0-9a-f]{8} = \d+ Bytes\r\n")
                    self.assertTrue(reply.endswith(text + PROMPT.decode()), "whole: the size it reported and everything after it")
            self.assertEqual(len(ABORTS + STARTS_AGAIN) > 400, True, "longer than the end that is kept of a transfer's reply otherwise")

    def test_a_whole_line_of_a_dump_is_data_whatever_its_text_column_spells(self) -> None:
        """Review of 7830797: the names of the exceptions were looked for anywhere in a line, and a dump's line ends
        with its bytes as text. A result is whatever the device holds; it may spell `data abort`."""
        seen, line = s1a_run.restart_seen, s1a_run.dump_line
        spells = {4: "10000000: 00000000 61746164 6f626120 00007472  ....data abort..", 3: "10000010: 61746164 6f626120 00007472           data abort..",
                  2: "1000001c: 65736552 6e697474                    Resettin", 1: "f800700c: a802000a                             ...."}
        for n, ln in spells.items():
            with self.subTest(words=n):
                self.assertEqual(len(ln), 47 + 4 * n)
                self.assertTrue(line(ln))
                self.assertIsNone(seen(f"md.l 10000000 {n}", f"md.l 10000000 {n}\r\n{ln}\r\nZynq> "))
                if n > 2:
                    self.assertEqual(seen("crc32 10000000 10", ln + "\r\n"), ln, "only in the reply to a dump is such a line a dump's")
        # a line that began as a dump and ends otherwise is not data: the access was made after the line had begun
        for ln in ("10000000:data abort", "10000000: 00000000data abort", "10000000: 00000000 61746164 data abort",
                   "10000000: 00000000 61746164 6f626120 00007472  data abort", "10000000: 00000000 61746164 6f626120 00007472  ....data abort..data abort",
                   "10000000: 00000000 61746164 6f626120 00007472 ....data abort..", "10000000: 00000000 61746164 6f626120 00007472   ....data abort..",
                   "10000010: 61746164 6f626120 00007472  data abort..", "10000010: 61746164 6f626120 00007472           data abort...",
                   "10000010: 61746164 6f626120 00007472 data abort............",          # as long as a dump's line of three words is
                   "1000001: 00000000 61746164 6f626120 00007472  ....data abort..", "10000000: 00000000 61746164 6f626120 00007472 12345678 data abort.."):
            with self.subTest(ln):
                self.assertFalse(line(ln))
                self.assertEqual(seen("md.l 10000000 4", "md.l 10000000 4\r\n" + ln + "\r\nZynq> "), ln)
        # the lines after a dump's are looked at as ever
        self.assertEqual(seen("md.l 10000000 4", spells[4] + "\r\ndata abort\r\n" + STARTS_AGAIN), "data abort")
        self.assertEqual(seen("md.l 10000000 4", spells[4] + "\r\n" + STARTS_AGAIN), STARTS_AGAIN.split("\r\n")[0])
        # and the pretend board of these tests prints its dumps in that form
        u = FakeUBoot(); u.mem.update({0x10000004: 0x61746164, 0x10000008: 0x6f626120, 0x1000000c: 0x00007472})
        self.assertEqual(u.c_md_l(["md.l", "10000000", "4"]), spells[4] + "\r\n")
        self.assertEqual(u.c_md_l(["md.l", "10000004", "7"]).split("\r\n")[1], "10000014: 00000000 00000000 00000000           ............")

    def test_the_reply_is_recorded_whole_however_long_it_is(self) -> None:
        """Owner, 2026-11-20: such a run stops, pulls nothing, and is recorded; whether it is made again is decided from
        the record. So the reply is kept whole where any other long reply is cut to its two ends."""
        _, base, _ = run(card_has_pl=True)
        at = base.commands.index("go 02000000") + 1
        long = "go 02000000\r\n## Starting application at 0x02000000 ...\r\nSM1 start\r\n" + "".join(f"a line of the prober, the {k}th\r\n" for k in range(100))
        rec, u, out = run(card_has_pl=True, restarts_at={at}, restart_text=long[len("go 02000000\r\n"):] + ABORTS + STARTS_AGAIN)
        stored = json.loads((out / "run.json").read_text())
        self.assertEqual(stored["steps"][-1]["reply"], long + ABORTS + STARTS_AGAIN + PROMPT.decode())
        self.assertGreater(len(stored["steps"][-1]["reply"]), 2000)
        self.assertEqual((stored["restart"]["cmd"], stored["restart"]["line"], stored["verdict"]), ("go 02000000", "data abort", "FAIL"))
        self.assertNotIn("went", stored)
        self.assertEqual([p.name for p in out.iterdir()], ["run.json"], "no header, no result, no verdict of a judge")
        self.assertEqual(u.commands[-1], "go 02000000")
        pull = next(s for s in json.loads((ROOT / "evidence" / "s1a_17A6_2026-11-13" / "run1" / "run.json").read_text())["steps"] if " … " in s["reply"])
        self.assertLess(len(pull["reply"]), 700, "as every other long reply is, and was")

    def test_what_is_not_such_a_line(self) -> None:
        seen = s1a_run.restart_seen
        version = "version\r\nU-Boot 2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)\r\n\r\narm-linux-gnueabihf-gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0\r\nZynq> "
        self.assertIsNone(seen("version", version), "U-Boot's own line in the reply to `version` is the answer")
        self.assertIsNotNone(seen("md.l f800700c 1", version), "in any other reply it is the board starting")
        self.assertEqual(seen("version", "version\r\n" + STARTS_AGAIN + "Zynq> "), STARTS_AGAIN.split("\r\n")[0], "and before it comes the loader's line")
        self.assertIsNone(seen(STATUS, "md.l f800700c 1\r\nf800700c: a802000a                             ....\r\nZynq> "))
        self.assertIsNone(seen("fpga", "fpga loadb 0 04000000 1fcc13\r\n  design filename = \"a;UserID=0XFFFFFFFF;Version=2025.2\"\r\nZynq> "))
        self.assertIsNone(seen("go", "go 02000000\r\n## Starting application at 0x02000000 ...\r\nSM1 start\r\nSM1 done 1 0\r\n## Application terminated, rc = 0x1\r\nZynq> "))
        self.assertIsNone(seen(STATUS, "a line that speaks of the U-Boot 2026.04 it runs under, or of resetting ... something\r\n"), "these two are held to a line's beginning")

    def test_the_rule_over_everything_the_board_has_said(self) -> None:
        """No reply kept with a run says so; and of everything in the console logs the replies to `reset` — sent
        between the runs of a chain, never by the run script — say so, every one of them, and nothing else does."""
        replies = 0
        for f in sorted((ROOT / "evidence").rglob("run.json")):
            for st in json.loads(f.read_text()).get("steps", []):
                replies += 1
                self.assertIsNone(s1a_run.restart_seen(st["cmd"], st["reply"]), (f, st["cmd"]))
        self.assertGreater(replies, 24000)
        resets = others = 0
        for f in sorted((ROOT / "evidence").rglob("*console*.log")):
            parts = re.split(r"\n<<TX b'(.*?)'>>\n", f.read_bytes().decode("utf-8", "replace"))
            for cmd, reply in zip(parts[1::2], parts[2::2]):
                cmd = cmd.replace("\\r", "").strip()
                if cmd == "reset":
                    resets += 1
                    self.assertTrue(s1a_run.restart_seen(cmd, reply).startswith("U-Boot SPL 2026.04"), f)
                else:
                    others += 1
                    self.assertIsNone(s1a_run.restart_seen(cmd, reply), (f, cmd))
        self.assertGreater(resets, 180); self.assertGreater(others, 25000)

    def test_the_form_of_a_dump_line_is_this_board_s(self) -> None:
        """The form dump_line() holds a line to is U-Boot's as it is generally known; here it is held to what this board
        printed. Nearly every line that begins as a dump has it; the few that have not are the ones the console damaged
        (a line cut short, two lines run together) — and those are looked at whole, as any line that is not a dump's."""
        whole = damaged = 0
        begins = re.compile(r"[0-9a-f]{8}:(?: [0-9a-f]{8}){1,4}")
        for f in sorted((ROOT / "evidence").rglob("*console*.log")):
            for ln in f.read_bytes().decode("utf-8", "replace").splitlines():
                if begins.match(ln):
                    if s1a_run.dump_line(ln):
                        whole += 1
                    else:
                        damaged += 1
        self.assertGreater(whole, 4_800_000)
        self.assertLess(damaged, 300)

    def test_the_header_is_held_to_the_pulled_result(self) -> None:
        """The header is accepted by its form when it is read. A dump that is whole in form and wrong in a word that
        does not size the result: the pull has the board's checksum, and the two headers are not the same."""
        rec, u, out = run(header_dump_lies={2: 0x5A5A5A5A})
        self.assertEqual((rec["judge"], rec["verdict"], rec.get("stop")), ("PASS", "FAIL", None))
        self.assertEqual(rec["problems"], ["the header as it was read before the pull is not the header of the pulled result"])
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertNotEqual((out / "header.bin").read_bytes(), u.twin_result[:256])


class PortFails:
    """A console whose serial port fails at one command, the way pyserial reports it, and stays failed."""

    def __init__(self, inner: FakeUBoot, at, error: Exception | None = None) -> None:
        import serial
        self.inner, self.at, self.failed, self.asked_after = inner, at, False, []
        self.error = error or serial.SerialException("device reports readiness to read but returned no data (device disconnected or multiple access on port?)")

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def interrupt(self):
        return self.cmd("\x03") if self.at("\x03", self.inner.commands) else self.inner.interrupt()

    def cmd(self, line: str, timeout: float = 10):
        if self.failed:
            self.asked_after.append(line)
        if self.failed or self.at(line, self.inner.commands):
            self.failed = True
            raise self.error
        return self.inner.cmd(line, timeout)

    def load(self, loady: str, path: str):               # the transfer of a file: `send_file` of the tests calls this
        if self.failed:
            self.asked_after.append(loady)
        if self.failed or self.at("transfer " + loady, self.inner.commands):
            self.failed = True
            raise self.error
        return self.inner.load(loady, path)


def run_on(at, error: Exception | None = None):
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
    exp = json.loads(s1a_run.STAGES["s1a"]["expected"].read_text())
    pl = s1a_run.PL.read_bytes()
    out = Path(scratch_dirs.mkdtemp(prefix="smout_"))
    con = PortFails(FakeUBoot(), at, error)
    rec = s1a_run.execute(con, exp, out, lambda c, cmd, path: c.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", "s1a")
    return rec, con, out


class TheSerialPortFails(unittest.TestCase):
    """Review of 7d7b11f: an exception of the serial port went straight through `execute`, and the record of the run —
    every step up to it — was never written. It is a stop like any other: recorded, and nothing sent after it."""

    def went(self, commands: list[str]) -> bool:
        return any(c.startswith("go ") for c in commands)

    def test_after_the_prober_returned_at_the_read_of_the_result_header(self) -> None:
        rec, con, out = run_on(lambda line, sent: self.went(sent) and line.startswith("md.l 10000000"))      # the reviewer's case
        self.assertEqual(rec, json.loads((out / "run.json").read_text()), "the record is written")
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertRegex(rec["stop"], r"^the console failed after \d+ step\(s\) — SerialException: device reports readiness to read .*; nothing more was sent$")
        self.assertEqual(rec["problems"], [rec["stop"]])
        self.assertEqual(con.asked_after, [], "nothing is sent to a port that failed")
        self.assertTrue(self.went(con.inner.commands))
        self.assertEqual((rec["steps"][-1]["cmd"].split()[0], int(re.search(r"after (\d+) step", rec["stop"]).group(1))), ("go", len(rec["steps"])),
                         "every step before it is in the record, the start of the prober the last")
        self.assertEqual((rec.get("went"), rec.get("judge"), (out / "result.bin").exists(), (out / "verdict.json").exists()), (True, None, False, False))

    def test_before_the_prober_is_started(self) -> None:
        rec, con, out = run_on(lambda line, sent: line.startswith("crc32 04000000"))
        self.assertIn("SerialException", rec["stop"])
        self.assertEqual((rec["verdict"], self.went(con.inner.commands), con.asked_after, (out / "run.json").exists()), ("FAIL", False, [], True))
        self.assertNotIn("went", rec)
        rec, con, out = run_on(lambda line, sent: line == "\x03")                 # at the very first thing sent
        self.assertRegex(rec["stop"], r"^the console failed after 0 step\(s\) — SerialException")
        self.assertEqual((rec["steps"], con.inner.commands, (out / "run.json").exists()), ([], [], True))

    def test_in_the_middle_of_the_pull(self) -> None:
        rec, con, out = run_on(lambda line, sent: self.went(sent) and line.startswith("crc32 10002000"))    # the checksum of the second piece
        self.assertIn("SerialException", rec["stop"])
        self.assertEqual((rec["verdict"], con.asked_after, (out / "result.bin").exists(), rec.get("judge")), ("FAIL", [], False, None))
        self.assertEqual((rec["card_written"], "s0000001.bin" in con.inner.card), (True, True), "the card copy was made before the pull: the result is not lost")
        self.assertEqual(rec["pull"]["pieces"], 1, "what was pulled up to then is in the record")

    def test_every_way_the_line_can_fail_at_every_place_it_is_used(self) -> None:
        """Second review of the same: a transfer that does not end in its time raises an exception of `subprocess`, not
        of the operating system, and went through. And the tty layer under pyserial raises one of its own when a port
        that vanished is flushed. So: every kind, at every place the script touches the line — the first prompt, a
        check, both transfers, the start, and each thing done after the prober returned."""
        import serial, termios
        kinds = [serial.SerialException("device reports readiness to read but returned no data"), OSError(5, "Input/output error"),
                 termios.error(5, "Input/output error"), subprocess.TimeoutExpired(["sb", "-k", "prober.bin"], 900)]
        places = [("the first prompt", lambda line, sent: line == "\x03", False),
                  ("the load of the design into the PL", lambda line, sent: line.startswith("fpga loadb"), False),
                  ("the transfer of the design", lambda line, sent: line.startswith("transfer loady 04000000"), False),
                  ("the checksum of the design", lambda line, sent: line.startswith("crc32 04000000"), False),
                  ("the transfer of the image", lambda line, sent: line.startswith("transfer loady 02000000"), False),
                  ("the start", lambda line, sent: line.startswith("go "), False),
                  ("the result header", lambda line, sent: self.went(sent) and line.startswith("md.l 10000000"), True),
                  ("the write to the card", lambda line, sent: line.startswith("fatwrite"), True),
                  ("the pull", lambda line, sent: self.went(sent) and line.startswith("crc32 10002000"), True),
                  ("the status afterwards", lambda line, sent: self.went(sent) and line.startswith("md.l f800700c"), True),
                  ("the last command", lambda line, sent: self.went(sent) and line == "version", True)]
        for place, at, went in places:
            for kind in kinds:
                with self.subTest(place=place, kind=type(kind).__name__):
                    rec, con, out = run_on(at, kind)
                    self.assertTrue(con.failed, "the place was reached")
                    self.assertEqual(rec, json.loads((out / "run.json").read_text()), "the record is written")
                    self.assertRegex(rec["stop"], rf"^the console failed after \d+ step\(s\) — {type(kind).__name__}: .*; nothing more was sent$")
                    self.assertEqual((rec["verdict"], rec["problems"], con.asked_after), ("FAIL", [rec["stop"]], []))
                    self.assertEqual((self.went(con.inner.commands), rec.get("went", False)), (went, went))
                    self.assertEqual(len(rec["steps"]), int(re.search(r"after (\d+) step", rec["stop"]).group(1)))

    def test_the_reviewers_case_a_transfer_that_does_not_end(self) -> None:
        rec, con, out = run_on(lambda line, sent: line.startswith("transfer loady 02000000"), subprocess.TimeoutExpired(["sb", "-k", "prober.bin"], 900))
        self.assertRegex(rec["stop"], r"— TimeoutExpired: .* timed out after 900 seconds; nothing more was sent$")
        self.assertEqual((self.went(con.inner.commands), con.asked_after, (out / "run.json").exists(), rec["verdict"]), (False, [], True, "FAIL"))
        self.assertTrue(rec["steps"], "the steps up to the transfer are in the record")

    def test_nothing_touches_the_line_but_through_the_one_place(self) -> None:
        """So that a use of the console added later cannot go round it: in `execute`, every line that names the console
        or the sending of a file does so inside `link(`."""
        import inspect
        body = inspect.getsource(s1a_run.execute).split('"""', 2)[2]
        uses = [ln.strip() for ln in body.splitlines() if re.search(r"\bcon\b|send_file\(", ln)]
        self.assertEqual(len(uses), 3, uses)                      # a command, a file transfer, the first prompt
        self.assertTrue(all("link(" in ln for ln in uses), uses)
        # and every reply goes into the record in one place, where it is looked at for an exception or a restart first
        # (review of 7830797: the two transfers recorded theirs themselves, and were not looked at)
        self.assertEqual(body.count('record["steps"].append('), 1)
        note = body[body.index("def note("):body.index("def do(")]
        self.assertLess(note.index("restart_seen(cmd, text)"), note.index('record["steps"].append('))
        self.assertEqual(len(re.findall(r"\bnote\(", body)), 3, "its definition, and the two that receive: do() and transfer()")
        self.assertEqual(s1a_run.TRANSPORT, (OSError, __import__("termios").error, subprocess.SubprocessError))

    def test_any_failure_of_the_port_is_one_and_a_fault_of_the_program_is_not(self) -> None:
        rec, con, out = run_on(lambda line, sent: self.went(sent) and line.startswith("md.l 10000000"), OSError(5, "Input/output error"))
        self.assertRegex(rec["stop"], r"^the console failed after \d+ step\(s\) — OSError: \[Errno 5\] Input/output error; nothing more was sent$")
        self.assertEqual((con.asked_after, (out / "run.json").exists()), ([], True))
        with self.assertRaises(ZeroDivisionError):         # not a failure of the port: it is not to be taken for a run that stopped
            run_on(lambda line, sent: self.went(sent) and line.startswith("md.l 10000000"), ZeroDivisionError("a bug"))


class PlDesign(unittest.TestCase):
    def test_from_the_card_when_it_is_there_and_nothing_is_sent(self) -> None:
        rec, u, _ = run(card_has_pl=True)
        self.assertEqual((rec["verdict"], rec["pl_source"]), ("PASS", "card"))
        self.assertFalse([c for c in u.commands if c.startswith("loady 04000000")])

    def test_by_ymodem_when_the_card_does_not_have_it(self) -> None:
        rec, u, _ = run()
        self.assertEqual((rec["verdict"], rec["pl_source"]), ("PASS", "ymodem"))
        self.assertIn("loady 04000000", u.commands)

    def test_a_card_copy_of_the_wrong_size_is_not_used(self) -> None:
        rec, u, _ = run(card_pl_short=True)
        self.assertEqual((rec["verdict"], rec["pl_source"]), ("PASS", "ymodem"))

    def test_a_damaged_card_copy_stops_the_run_before_the_pl_is_touched(self) -> None:
        rec, u, _ = run(card_pl_damaged=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("crc32", rec["stop"])
        self.assertFalse([c for c in u.commands if c.startswith(("fpga", "go"))])


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
        poison = Path(scratch_dirs.mkdtemp(prefix="smpoison_"))
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
        card = next(i for i, c in enumerate(cmds) if c.startswith("fatload mmc 0:1 04000000"))
        self.assertEqual(cmds[card + 1], "loady 04000000", "the YMODEM branch is listed right after the card load it replaces")
        self.assertIn("ONLY IF", out)
        self.assertIn("branches after go:", out)
        every = {c.split()[0] for c in (ROOT / "host" / "s1a_run.py").read_text().split('"') if c[:6] in ("loady ", "fatloa", "fatwri")}
        self.assertTrue(every <= {c.split()[0] for c in cmds})
        go = cmds.index("go 02000000")
        self.assertLess(cmds.index("dcache off"), go)
        self.assertLess(next(i for i, c in enumerate(cmds) if c.startswith("fpga loadb")), go)
        self.assertGreater(next(i for i, c in enumerate(cmds) if c.startswith("fatwrite")), go)
        self.assertLess(next(i for i, c in enumerate(cmds) if c.startswith("fatwrite")),
                        next(i for i, c in enumerate(cmds) if c.startswith("crc32 / md.l 10000000")), "the card copy is written before the pull")

    def test_the_fake_and_the_real_console_share_the_interface_the_script_uses(self) -> None:
        src = (ROOT / "host" / "uboot_console.py").read_text()
        for name in ("def interrupt", "def cmd", "def until_prompt", "def tx"):
            self.assertIn(name, src)


if __name__ == "__main__":
    unittest.main()

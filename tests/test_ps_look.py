#!/usr/bin/env python3
"""The look at PS registers from the U-Boot prompt and the one write it may make (docs/s1b_plan.md, section 54),
against a pretended console: what is sent, in which order, and when the write is not sent."""
from __future__ import annotations

import json, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import ps_look  # noqa: E402

PROMPT = b"Zynq> "
# Written out here, not taken from the program: every command it may send, in order, when the bit is found set.
DUMPS = ["md.l f8007000 6", "md.l f8007080 1", "md.l f8000100 3", "md.l f8000120 2", "md.l f8000168 1", "md.l f8f02100 2", "md.l f8006208 8"]
STATUS, CLEAR = "md.l f800700c 1", "mw.l f800700c 00000020"
ALL = DUMPS + [STATUS, CLEAR, STATUS, STATUS, STATUS]


class Console:
    """Word memory behind md.l and mw.l; `devcfg.INT_STS` clears the bits written as one, as the register does."""

    def __init__(self, status=0x50033024, lossy=None, no_prompt=None, hears=True, comes_back=False) -> None:
        self.status, self.lossy, self.no_prompt, self.hears, self.comes_back = status, lossy or {}, no_prompt, hears, comes_back
        self.sent: list[str] = []
        self.asked: dict[str, int] = {}

    def interrupt(self, tries: int = 3):
        return PROMPT, self.hears

    def word(self, a: int) -> int:
        return self.status if a == 0xF800700C else (a * 2654435761 >> 7) & 0xFFFFFFFF      # any value, the same every time

    def cmd(self, line: str, timeout: float = 10):
        self.sent.append(line); self.asked[line] = self.asked.get(line, 0) + 1
        w = line.split(); out = ""
        if w[0] == "md.l":
            a, n = int(w[1], 16), int(w[2], 16)
            for k in range(0, n, 4):
                out += f"{a + 4 * k:08x}:" + "".join(f" {self.word(a + 4 * (k + j)):08x}" for j in range(min(4, n - k))) + "    ....\r\n"
            if self.comes_back and a == 0xF800700C and self.asked[line] > 2:
                self.status |= 0x20
        elif w[0] == "mw.l":
            assert int(w[1], 16) == 0xF800700C, "the pretended board has nothing else to write to"
            self.status &= ~int(w[2], 16)
        else:
            raise AssertionError(f"not a command this console knows: {line}")
        which = self.lossy.get(line)
        if which is not None and (which is True or self.asked[line] in which):
            out = out[:len(out) // 3] + out[2 * len(out) // 3:]
        return (line + "\r\n" + out).encode() + PROMPT, self.no_prompt != line


def look(con: Console) -> tuple[dict, list[float]]:
    waits: list[float] = []
    return ps_look.look(con, pause=waits.append), waits


class WhatIsSent(unittest.TestCase):
    def test_the_commands_are_the_ones_written_here_and_no_others(self) -> None:
        self.assertEqual(ps_look.commands(), ALL)
        con = Console(); rec, waits = look(con)
        self.assertEqual((con.sent, rec["sent"], rec["stopped"], rec["replies_not_whole"]), (ALL, ALL, None, []))
        self.assertEqual([c for c in con.sent if not c.startswith("md.l ")], [CLEAR], "one command that is not a dump")
        self.assertEqual(waits, [1.0, 1.0, 1.0], "a pause before each of the three reads after the write")

    def test_what_is_recorded(self) -> None:
        con = Console(); rec, _ = look(con)
        self.assertEqual(len(rec["registers"]), 6 + 1 + 3 + 2 + 1 + 2 + 8)
        self.assertEqual(rec["registers"]["devcfg.INT_STS"], "50033024")
        for name, a in (("devcfg.CTRL", 0xF8007000), ("devcfg.STATUS", 0xF8007014), ("devcfg.MCTRL", 0xF8007080), ("slcr.IO_PLL_CTRL", 0xF8000108),
                        ("slcr.DDR_CLK_CTRL", 0xF8000124), ("slcr.PCAP_CLK_CTRL", 0xF8000168), ("l2cpl310.reg1_aux_control", 0xF8F02104),
                        ("ddrc.axi_priority_wr_port0", 0xF8006208), ("ddrc.axi_priority_rd_port3", 0xF8006224)):
            self.assertEqual(rec["registers"][name], f"{con.word(a):08x}", name)
        self.assertEqual((rec["status_before"], rec["clear_sent"], rec["status_after"]), ("50033024", True, ["50033004"] * 3))

    def test_a_bit_that_comes_back_is_seen_coming_back(self) -> None:
        rec, _ = look(Console(comes_back=True))
        self.assertEqual((rec["status_after"], rec["stopped"]), (["50033004", "50033004", "50033024"], None), "back at the third read")

    def test_the_write_is_not_sent_unless_the_status_has_the_bit_and_the_pl_is_configured(self) -> None:
        for status in (0x50033004, 0xA802000A, 0x50033020, 0x00000000):
            con = Console(status=status); rec, waits = look(con)
            self.assertEqual((con.sent, rec["clear_sent"], rec["status_after"], waits), (DUMPS + [STATUS], False, [], []), hex(status))
            self.assertEqual((rec["status_before"], rec["stopped"]), (f"{status:08x}", "the status has not both PCFG_DONE and bit 5 set: nothing was written"))
            self.assertEqual(con.status, status)
        con = Console(status=0x50033064); rec, _ = look(con)                    # another bit beside it is left as it is
        self.assertEqual((rec["clear_sent"], rec["status_after"], con.status), (True, ["50033044"] * 3, 0x50033044))

    def test_no_prompt_at_the_start_and_nothing_is_sent(self) -> None:
        con = Console(hears=False); rec, _ = look(con)
        self.assertEqual((con.sent, rec["stopped"], rec["registers"]), ([], "no U-Boot prompt", {}))


class RepliesNotWhole(unittest.TestCase):
    def test_a_dump_that_is_not_whole_is_asked_for_again(self) -> None:
        con = Console(lossy={"md.l f8006208 8": {1, 2}, STATUS: {3}}); rec, _ = look(con)
        self.assertEqual(con.sent, DUMPS[:-1] + [DUMPS[-1]] * 3 + [STATUS, CLEAR, STATUS, STATUS, STATUS, STATUS])
        self.assertEqual(rec["replies_not_whole"], [{"cmd": "md.l f8006208 8", "attempt": 1}, {"cmd": "md.l f8006208 8", "attempt": 2}, {"cmd": STATUS, "attempt": 1}])
        self.assertEqual((rec["stopped"], rec["status_after"], rec["registers"]["ddrc.axi_priority_rd_port3"]), (None, ["50033004"] * 3, f"{con.word(0xF8006224):08x}"))
        self.assertEqual(con.sent.count(CLEAR), 1)

    def test_five_times_and_no_more_and_then_it_stops(self) -> None:
        con = Console(lossy={"md.l f8000120 2": True}); rec, _ = look(con)
        self.assertEqual(con.sent, DUMPS[:3] + ["md.l f8000120 2"] * 5)
        self.assertEqual((rec["stopped"], rec["clear_sent"]), ("`md.l f8000120 2` could not be read whole in 5 attempts", False))
        con = Console(lossy={STATUS: True}); rec, _ = look(con)                # the status before the write: never whole, so no write
        self.assertEqual((con.sent, rec["clear_sent"], rec["status_before"]), (DUMPS + [STATUS] * 5, False, None))

    def test_the_write_is_sent_once_whatever_comes_back(self) -> None:
        con = Console(lossy={CLEAR: True}); rec, _ = look(con)                 # its reply garbled: it is not looked at and not repeated
        self.assertEqual((con.sent, rec["stopped"], rec["replies_not_whole"]), (ALL, None, []))
        con = Console(no_prompt=CLEAR); rec, waits = look(con)                 # no prompt after it: stop, nothing more
        self.assertEqual((con.sent, rec["stopped"], rec["status_after"], waits), (DUMPS + [STATUS, CLEAR], f"no prompt after `{CLEAR}`", [], []))

    def test_no_prompt_after_a_dump_stops_the_look(self) -> None:
        con = Console(no_prompt="md.l f8f02100 2"); rec, _ = look(con)
        self.assertEqual((con.sent, rec["stopped"], rec["clear_sent"]), (DUMPS[:6], "no prompt after `md.l f8f02100 2`", False))
        self.assertNotIn("l2cpl310.reg1_control", rec["registers"])


class ThroughTheCommandLine(unittest.TestCase):
    def test_a_serial_port_that_fails_stops_the_look_and_the_record_is_kept(self) -> None:
        """Review of 7d7b11f, the same gap as in the run script: an exception of the port went through `look`, and with
        it the record — of the write too, had it gone out."""
        class Fails(Console):
            def __init__(self, at: str, nth: int = 1, **kw) -> None:
                super().__init__(**kw); self.at, self.nth, self.failed = at, nth, False

            def cmd(self, line: str, timeout: float = 10):
                if self.failed or (line == self.at and self.asked.get(line, 0) + 1 == self.nth):
                    self.failed = True; self.sent.append(line)
                    raise OSError(5, "Input/output error")
                return super().cmd(line, timeout)
        c = Fails(DUMPS[2])                                  # at a dump
        r = ps_look.look(c, pause=lambda s: None)
        self.assertEqual((r["sent"], c.sent, r["clear_sent"]), (DUMPS[:3], DUMPS[:3], False))
        self.assertEqual(r["stopped"], f"the console failed at `{DUMPS[2]}` — OSError: [Errno 5] Input/output error; nothing more was sent")
        self.assertEqual(len(r["registers"]), 6 + 1, "what was read before it is kept")
        c = Fails(CLEAR)                                     # at the write: whether it went out is not known, and the record says it was sent
        r = ps_look.look(c, pause=lambda s: None)
        self.assertEqual((r["sent"], c.sent, r["clear_sent"], r["status_before"], r["status_after"]), (DUMPS + [STATUS, CLEAR], DUMPS + [STATUS, CLEAR], True, "50033024", []))
        self.assertIn(f"the console failed at `{CLEAR}`", r["stopped"])
        c = Fails(STATUS, nth=3)                             # after the write, at the second read
        r = ps_look.look(c, pause=lambda s: None)
        self.assertEqual((r["clear_sent"], r["status_after"], c.sent.count(CLEAR), c.sent[-1]), (True, ["50033004"], 1, STATUS))
        self.assertIn("the console failed", r["stopped"])
        import termios
        for error in (termios.error(5, "Input/output error"), subprocess.TimeoutExpired(["x"], 1)):      # the other kinds the line can raise
            class Other(Console):
                def cmd(self, line: str, timeout: float = 10, error=error):
                    self.sent.append(line)
                    raise error
            r = ps_look.look(Other(), pause=lambda s: None)
            self.assertEqual((r["sent"], r["clear_sent"]), (DUMPS[:1], False))
            self.assertIn(f"the console failed at `{DUMPS[0]}` — {type(error).__name__}", r["stopped"])
        class Bug(Console):
            def cmd(self, line: str, timeout: float = 10):
                raise ZeroDivisionError("a bug")
        with self.assertRaises(ZeroDivisionError):           # a fault of the program is not a failure of the port
            ps_look.look(Bug(), pause=lambda s: None)

    def test_the_dry_run_prints_the_commands_and_needs_no_board(self) -> None:
        prog = [sys.executable, "-B", str(ROOT / "host" / "ps_look.py")]
        p = subprocess.run(prog + ["--dry-run"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.splitlines()), (0, ALL + ["(dry run: nothing was sent)"]))
        p = subprocess.run(prog, capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.splitlines()[-1]), (2, "(nothing was sent: --go --out DIR sends them)"))
        for bad in (["--go"], ["--go", "--out", str(ROOT / "host")]):         # no directory named; one that is already there
            p = subprocess.run(prog + bad, capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout.strip()), (2, "--out must name a directory that does not exist yet"), bad)

    def test_the_program_sends_nothing_that_is_not_in_its_lists(self) -> None:
        src = (ROOT / "host" / "ps_look.py").read_text()
        self.assertEqual(src.count("con.cmd("), 2, "one place that sends a dump, one that sends the write")
        self.assertEqual((src.count("mw.l"), src.count("con.tx("), src.count(".load(")), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()

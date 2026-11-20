#!/usr/bin/env python3
"""A look at some PS registers from the U-Boot prompt, and one write: bit 5 of the status register cleared
(docs/s1b_plan.md, section 54).

    ps_look.py --dry-run                 prints the commands, touches nothing
    ps_look.py --go --out DIR            sends them; DIR gets console.log and look.json

Nothing is loaded, nothing is started, the PL is not addressed. The commands are the ones written out below and no
others:

- LOOK: dumps of registers that are only read. They are recorded as read; nothing is concluded from them here.
- STATUS, then CLEAR, then STATUS three times with a pause before each: `devcfg.INT_STS` is write-one-to-clear, and
  the prober writes its own clear mask to it before every read of a frame — never bit 5. CLEAR writes that one bit.
  It is sent only if the status read just before has PCFG_DONE and bit 5 set (the state a run of S1b.4 leaves), and it
  is sent once: its reply is not examined and it is never repeated.

A dump whose reply is not whole is asked for again, at most MAX_READS times (s1a_run.whole: the rule of section 43).
If a dump cannot be read whole, or the prompt does not come back, or the serial port itself fails, the look stops
there and says so: the record is written all the same, with everything that was sent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from s1a_run import MAX_READS, TRANSPORT, restart_seen, whole  # noqa: E402

LOOK = [  # (the dump, the registers its words are — names and addresses from UG585's register reference)
    ("md.l f8007000 6", ["devcfg.CTRL", "devcfg.LOCK", "devcfg.CFG", "devcfg.INT_STS", "devcfg.INT_MASK", "devcfg.STATUS"]),
    ("md.l f8007080 1", ["devcfg.MCTRL"]),
    ("md.l f8000100 3", ["slcr.ARM_PLL_CTRL", "slcr.DDR_PLL_CTRL", "slcr.IO_PLL_CTRL"]),
    ("md.l f8000120 2", ["slcr.ARM_CLK_CTRL", "slcr.DDR_CLK_CTRL"]),
    ("md.l f8000168 1", ["slcr.PCAP_CLK_CTRL"]),
    ("md.l f8f02100 2", ["l2cpl310.reg1_control", "l2cpl310.reg1_aux_control"]),
    ("md.l f8006208 8", ["ddrc.axi_priority_wr_port0", "ddrc.axi_priority_wr_port1", "ddrc.axi_priority_wr_port2", "ddrc.axi_priority_wr_port3",
                         "ddrc.axi_priority_rd_port0", "ddrc.axi_priority_rd_port1", "ddrc.axi_priority_rd_port2", "ddrc.axi_priority_rd_port3"]),
]
STATUS = "md.l f800700c 1"
CLEAR = "mw.l f800700c 00000020"
BIT, PCFG_DONE = 0x00000020, 0x00000004
READS_AFTER, PAUSE = 3, 1.0                          # status reads after the clear, and the seconds waited before each


def commands() -> list[str]:
    """Everything this program can send, in order, if the bit is found set."""
    return [c for c, _ in LOOK] + [STATUS, CLEAR] + [STATUS] * READS_AFTER


def look(con, pause=time.sleep) -> dict:
    record: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()), "sent": [], "registers": {}, "replies_not_whole": [],
                    "status_before": None, "clear_sent": False, "status_after": [], "stopped": None}
    try:
        return steps(con, pause, record)
    except TRANSPORT as e:                              # the serial line itself failed: nothing more is sent, and what was sent — the
        # write, if it had been — is in the record (a command is listed before it goes out)
        record["stopped"] = f"the console failed at `{record['sent'][-1] if record['sent'] else 'the first prompt'}` — {type(e).__name__}: {e}; nothing more was sent"
        return record


def steps(con, pause, record: dict) -> dict:

    def read(cmd: str):
        for attempt in range(1, MAX_READS + 1):
            record["sent"].append(cmd)
            reply, ok = con.cmd(cmd, 10)
            seen = restart_seen(cmd, reply.decode("utf-8", "replace"))
            if seen:                                    # not a reply that lost characters: it is not asked for again
                record["stopped"] = f"U-Boot took an exception or the board started again at `{cmd}` (its reply has the line {seen!r}); nothing more was sent"; return None
            if not ok:
                record["stopped"] = f"no prompt after `{cmd}`"; return None
            got = whole(cmd, reply.decode("utf-8", "replace"))
            if got is not None:
                return got
            record["replies_not_whole"].append({"cmd": cmd, "attempt": attempt})
        record["stopped"] = f"`{cmd}` could not be read whole in {MAX_READS} attempts"
        return None

    _, ok = con.interrupt()
    if not ok:
        record["stopped"] = "no U-Boot prompt"; return record
    for cmd, names in LOOK:
        got = read(cmd)
        if got is None:
            return record
        record["registers"].update({n: f"{w:08x}" for n, w in zip(names, got)})
    got = read(STATUS)
    if got is None:
        return record
    record["status_before"] = f"{got[0]:08x}"
    if not (got[0] & BIT and got[0] & PCFG_DONE):
        record["stopped"] = "the status has not both PCFG_DONE and bit 5 set: nothing was written"
        return record
    record["sent"].append(CLEAR); record["clear_sent"] = True
    reply, ok = con.cmd(CLEAR, 10)                      # once; never again, whatever comes back
    seen = restart_seen(CLEAR, reply.decode("utf-8", "replace"))
    if seen:
        record["stopped"] = f"U-Boot took an exception or the board started again at `{CLEAR}` (its reply has the line {seen!r}); nothing more was sent"; return record
    if not ok:
        record["stopped"] = f"no prompt after `{CLEAR}`"; return record
    for _ in range(READS_AFTER):
        pause(PAUSE)
        got = read(STATUS)
        if got is None:
            return record
        record["status_after"].append(f"{got[0]:08x}")
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.dry_run or not a.go:
        print("\n".join(commands()))
        print("(dry run: nothing was sent)" if a.dry_run else "(nothing was sent: --go --out DIR sends them)")
        return 0 if a.dry_run else 2
    if a.out is None or a.out.exists():
        print("--out must name a directory that does not exist yet"); return 2
    a.out.mkdir(parents=True)
    os.environ["SELFMAP_CONSOLE_LOG"] = str(a.out / "console.log")
    from uboot_console import UB
    record = look(UB())
    (a.out / "look.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    return 0 if record["stopped"] is None else 1


if __name__ == "__main__":
    sys.exit(main())

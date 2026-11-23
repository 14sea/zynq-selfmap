#!/usr/bin/env python3
"""A board run of one stage: exactly what the host types into U-Boot, in order.

    s1a_run.py [--stage s1a|s1b0|s1b0b|s1b1|s1b1r|s1b2|rate*|dx*|s2_0|s2_1] --dry-run          print the whole plan and exit; touches no serial port
    s1a_run.py [--stage s1a|s1b0|s1b0b|s1b1|s1b1r|s1b2|rate*|dx*|s2_0|s2_1] --go --out DIR     run it (refuses unless the image on disk is the one tests fixed)

The stages share everything but the parameter block, the judge and the size of a record; the prober
image is the same and picks the stage from the parameter block.

Before `go` every step has a check and the first failure stops the run: nothing has been started.
After `go` the rule is the opposite — whatever the prober reported, clean or not, its result is
first sized from its own header, checksummed, saved to the card, pulled to the host and compared,
and only then judged. A run with anomalies or an interface stop is still archived whole.

The overall verdict is PASS only if the judge says PASS (which includes: the parameters the
prober echoed are the planned ones, and the gate readings fit), the card copy was confirmed and
read back with the board's checksum, the pulled copy has the board's checksum, the console line
and return code are the ones the result implies, and the live status afterwards still shows the
PL configured with no error bit.

The console loses characters now and then (a stretch of a reply is missing; on 2026-11-17 that was the dump of
the result header, and the run stopped there). A reply this script depends on and whose form is known — a dump of a
few words, a checksum — is therefore asked for again, a bounded number of times, when it is not whole; every
attempt is among the recorded steps and every reply that was not whole is listed. That holds before `go` and
after it, and for those two commands only: they change nothing on the board. A whole reply is taken as it is — a
value that is not the one wanted is a finding and is never asked for twice — and no command that does anything
(`go`, a write, a load, a save) is ever sent a second time, whatever came back.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import termios
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1a_judge  # noqa: E402
import s1b0_judge  # noqa: E402
import s1b0b_judge  # noqa: E402
import s1b1_judge  # noqa: E402
import dx_judge  # noqa: E402
import s1b2_judge  # noqa: E402
import s1b2e_judge  # noqa: E402
import s2_0_judge  # noqa: E402
import s2_1_judge  # noqa: E402
import s2_2_judge  # noqa: E402
import s2_2_shares  # noqa: E402
import s2_3c_judge  # noqa: E402
import s2_3s_judge  # noqa: E402
import s2_4_states  # noqa: E402
import s2_4f_judge  # noqa: E402
import s2_3_states  # noqa: E402

EXPECTED = ROOT / "build" / "prober" / "expected.json"
STAGES = {"s1a": {"judge": s1a_judge, "expected": EXPECTED},
          "s1b0": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_s1b0.json"},
          "s1b0b": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_s1b0b.json"},
          "s1b1": {"judge": s1b1_judge, "expected": ROOT / "build" / "prober" / "expected_s1b1.json"},
          # S1b.1 as it is to be run after 2026-11-15: the same parameter block with the wait that stores nothing while
          # a transfer runs (word 15). The set above waits as before and overflows the receive FIFO; it is kept as it was.
          "s1b1r": {"judge": s1b1_judge, "expected": ROOT / "build" / "prober" / "expected_s1b1r.json"},
          # S1b.2: one run of the chain along the row (docs/s1b_plan.md, section 25). The set is s1b1r's with the row as
          # the envelope; its starting address is given at run time (--start), see with_start() below.
          "s1b2": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b2.json"},
          # S1b.2b: the end of the row (section 29). Two fixed tables for the table-driven stage in its stage-5 form
          # with the quiet wait: reads of the pad and 0..3 frames at the last four addresses of the row, and column 55
          # again in reads of three frames. Judged by the judge of that stage, which here counts frames without a known
          # answer instead of holding them against the run.
          "s1b2e": {"judge": s1b2e_judge, "expected": ROOT / "build" / "prober" / "expected_s1b2e.json"},
          "s1b2c": {"judge": s1b2e_judge, "expected": ROOT / "build" / "prober" / "expected_s1b2c.json"},
          # S1b.3a (section 35): one run of the walk across the end of the row — s1b2's set with block type 0 whole as
          # the envelope and one standstill a pass allowed; the start is fixed (the last frame of the chain's last
          # accepted run). Judged as a run of a chain: it begins beyond the known frames.
          "s1b3a": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b3a.json"},
          # S1b.3 (section 38): one run of the chain over block type 0 — s1b3a's set with the starting address given at
          # run time (--start), as for s1b2.
          "s1b3": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b3.json"},
          # S1b.4a (section 46): one run of the walk into block type 1 — s1b3's set with the start fixed at the address
          # the device named after block type 0 and the envelope's upper end at the end of block type 1. Judged as a
          # run of a chain: it begins beyond the known frames.
          "s1b4a": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b4a.json"},
          # S1b.4 (section 49): one run of the chain over block type 1 — s1b4a's set, with the starting address given
          # at run time (--start), as for s1b2 and s1b3.
          "s1b4": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b4.json"},
          # S1b.5a (section 58): one run of the walk into block type 2 — s1b4a's set with the start fixed at the address
          # the device named after block type 1 and the envelope's upper end at the end of block type 2. Judged as a
          # run of a chain: it begins beyond the known frames.
          "s1b5a": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b5a.json"},
          # S1b.5 (section 62): one run of the chain over block type 2 — s1b5a's set, with the starting address given
          # at run time (--start), as for s1b2, s1b3 and s1b4.
          "s1b5": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b5.json"},
          # S1b.6a (section 65): one run of the walk at the address the device named after block type 2 — s1b5a's set
          # with the start fixed there and the envelope's upper end at the last address whose block type field is 3.
          # Judged as a run of a chain: it begins beyond the known frames.
          "s1b6a": {"judge": s1b2_judge, "expected": ROOT / "build" / "prober" / "expected_s1b6a.json"},
          # S2.0 (docs/s2_plan.md, section 6): one word of IDCODE, CTL0 and STAT read through PCAP, the carrier loaded
          # as in every run before it; the address register and the known frames as controls.
          "s2_0": {"judge": s2_0_judge, "expected": ROOT / "build" / "prober" / "expected_s2_0.json"},
          # S2.1 (section 7): the first access to user logic. The design loaded is s2a, not the carrier — its file, its
          # name on the card and its hash come from the set (which takes them from the record of the design's build) —
          # and what the judge holds the run to is the design's own facts, not the known frames. Before `go` the host
          # reads the four SLCR words and the design's identification register at the prompt (before_go).
          "s2_1": {"judge": s2_1_judge, "expected": ROOT / "build" / "prober" / "expected_s2_1.json", "known": ROOT / "pl" / "s2a" / "design.json"},
          # S2.2 (section 19): one run of the chain that reads block type 0 in three states of the design's RAM. The set
          # has no list of reads of its own: a run is of one share of the census's addresses, given at run time
          # (--share), see with_share() below. What the judge holds the run to is the design's facts and the census.
          "s2_2": {"judge": s2_2_judge, "expected": ROOT / "build" / "prober" / "expected_s2_2.json", "known": ROOT / "pl" / "s2a" / "design.json",
                   "census": s2_2_shares.CENSUS},
          # S2.3 (section 29): which bit is which cell — stage 9, in two kinds of run. s2_3c: the code run, eighteen
          # states over the column in which S2.2 found its candidates. s2_3s: one of the four runs of the singles
          # (--share), sixty-six states over the reads that deliver the frames with candidates. Neither set has lists of
          # its own: the list of reads and the list of accesses are made at run time from the design, the census and
          # what S2.2 found (with_plan below; s2_3_states.plan). The two kinds have two layouts: the header of a
          # stage-9 result is as long as the run's list of accesses makes it.
          "s2_3c": {"judge": s2_3c_judge, "expected": ROOT / "build" / "prober" / "expected_s2_3c.json", "known": ROOT / "pl" / "s2a" / "design.json",
                    "census": s2_2_shares.CENSUS, "candidates": s2_3_states.CANDIDATES, "chain_before": s2_3_states.CHAIN_OF_S2_2},
          "s2_3s": {"judge": s2_3s_judge, "expected": ROOT / "build" / "prober" / "expected_s2_3s.json", "known": ROOT / "pl" / "s2a" / "design.json",
                    "census": s2_2_shares.CENSUS, "candidates": s2_3_states.CANDIDATES, "chain_before": s2_3_states.CHAIN_OF_S2_2},
          # S2.4 (sections 37 and 38): the shift registers — stage 9 again, with the image as it is. s2_4f: a run of
          # part 1, one share of the census's addresses of block type 0 (--share) in three states of the shift
          # registers. The lists are made at run time (with_plan below; s2_4_states.plan); the set's word of what the
          # run may write allows the shift, which no set of S2.3 does.
          "s2_4f": {"judge": s2_4f_judge, "expected": ROOT / "build" / "prober" / "expected_s2_4f.json", "known": ROOT / "pl" / "s2a" / "design.json",
                    "census": s2_2_shares.CENSUS, "chain_before": s2_3_states.CHAIN_OF_S2_2, "ram_places": s2_3_states.CANDIDATES},
          # not stages of the prober but two parameter sets for its stage 2, to count how many frame reads go by before
          # the receive FIFO overflows: 128 reads of one frame, and 128 reads of three frames, on the known frames
          "rate1": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_rate1.json"},
          "rate3": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_rate3.json"},
          # and one for its stage 3: 64 times the pair the walk makes at every frame — the pad alone, then the frame, at
          # the same address — because rate1 and rate3 ran clean where the walk overflowed
          "ratep": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratep.json"},
          # the same pairs at the first eight addresses the walk read (0xb80..0xb87), where it overflowed and the known
          # frames did not. Those frames have no known answer, so the judge will say so and fail the run: what is
          # wanted here is only how many records the prober gets through
          "ratew": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratew.json"},
          # ratew once through instead of eight times: after a fresh load every one of its frame reads is the first
          # read of that frame, as every read of the walk's first pass is
          "ratef": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratef.json"},
          # diagnostics: why does the walk overflow where stages 2 and 3 do not (docs/s1b_plan.md, section 17).
          # dxw*: the walk itself, kept to the 26 addresses already read, with 0, 6 or 8 more words of stack beneath its
          # reads. dxs*: the reads of the walk's first pass made by the stage-3 loop (stage 5), with 0, 10 or 18.
          # A trailing n or r (2026-11-15): the same set with the wait that stores nothing while a transfer runs (n: the
          # limit still loaded from the stack on every poll; r: registers only, no memory touched).
          **{name: {"judge": s1b1_judge, "expected": ROOT / "build" / "prober" / f"expected_{name}.json"} for name in ("dxw0", "dxw6", "dxw8", "dxw0n", "dxw0r")},
          **{name: {"judge": dx_judge, "expected": ROOT / "build" / "prober" / f"expected_{name}.json"} for name in ("dxs0", "dxs10", "dxs18", "dxs10n", "dxs10r")}}
IMAGE = ROOT / "build" / "prober" / "prober.bin"
PL = ROOT / "build" / "pl" / "carrier.bit"
KNOWN = ROOT / "data" / "known_frames_17A6.json"
PL_ADDR, IMG_ADDR, RES_ADDR, PAR_ADDR, SCRATCH_ADDR = 0x04000000, 0x02000000, 0x10000000, 0x10100000, 0x11000000
LIST_ADDR = 0x10180000                               # stage 8: where the prober looks for the list of reads (prober/sm.h)
ACC_ADDR = 0x10190000                                # stage 9: where it looks for the list of accesses to the design
PAR_WORDS = 32
MAX_RESULT_WORDS = max(m["judge"].HDR + m["judge"].MAX_RECORDS * m["judge"].REC for m in STAGES.values())
PL_CARD_NAME = "carrier.bit"
PIECE_WORDS = 2048                                   # the result is pulled over the console in pieces of this many words
MAX_PIECE_PULLS = 5                                  # attempts at one piece
MAX_READS = 5                                        # attempts at one short read-only reply (a dump of a few words, a checksum)


STARTS_AT_RUN_TIME = ("s1b2", "s1b3", "s1b4", "s1b5")  # the sets whose starting address is not fixed by the tests
P_FAR_LO, P_FAR_HI, P_START = 3, 4, 16               # words of the parameter block
P_STAGE, P_PL_LO, P_PL_ID, P_SLCR = 2, 24, 26, 28    # stage 7: the PL envelope's lower end, the identification word, four SLCR words
SHARES_AT_RUN_TIME = ("s2_2",)                       # the sets whose list of reads is a share of the census, given at run time
PLANS_AT_RUN_TIME = {"s2_3c": "code", "s2_3s": "singles"}   # the sets of S2.3: both lists are made at run time; a run of the singles is one of four (--share)
PLANS_AT_RUN_TIME["s2_4f"] = "find"                          # and of S2.4, part 1: a run is of one share of the census's addresses (--share)
PLANNED_BY = {"s2_4f": s2_4_states}                          # which program makes the plan of a set, where it is not S2.3's
P_ACC_N, P_PL_WRITE = 18, 19                         # stage 9: how many entries the list of accesses has; which registers the run may write
P_STATES_N, P_LIST_N = 7, 16                         # stage 8: how many states, how many reads the list has
SLCR_GATES = ((0xF8000900, "LVL_SHFTR_EN"), (0xF8000240, "FPGA_RST_CTRL"), (0xF8000170, "FPGA0_CLK_CTRL"), (0xF800010C, "PLL_STATUS"))


def pl_file(exp: dict) -> Path:
    """The PL design a set is run with: the carrier, unless the set names another (S2.1 names s2a)."""
    return ROOT / exp["pl_design"]["file"] if "file" in exp["pl_design"] else PL


def pl_card_name(exp: dict) -> str:
    return exp["pl_design"].get("card_name", PL_CARD_NAME)


def known_for(stage: str) -> dict:
    """What the judge of a set holds its result to: the known frames, unless the set has facts of its own — and with
    them the census, for a set whose reads are made from it."""
    known = json.loads(STAGES[stage].get("known", KNOWN).read_text())
    if "census" in STAGES[stage]:
        known = dict(known, census=json.loads(STAGES[stage]["census"].read_text()))
    if "candidates" in STAGES[stage]:                # S2.3: what S2.2 found, as its chain wrote it
        known = dict(known, candidates=json.loads(STAGES[stage]["candidates"].read_text()))
    if "chain_before" in STAGES[stage]:              # and what CTL0 read in the runs that found it: the chain of S2.3 holds its code run to it
        known = dict(known, ctl0_in_s2_2=s2_3_states.ctl0_in_s2_2(json.loads(STAGES[stage]["chain_before"].read_text())))
    if "ram_places" in STAGES[stage]:                # S2.4: where the RAM's cells are, which no bit of the shift registers may be
        known = dict(known, ram_places=json.loads(STAGES[stage]["ram_places"].read_text()))
    return known


def planned_words(exp: dict) -> list[int]:
    """What a judge is given as the plan: the words of the parameter block, after them the list of reads of a set
    that has one, and after that the list of accesses of a set that has one."""
    return [int(w, 16) for w in exp["params"]] + [int(w, 16) for w in exp.get("list", [])] + [int(w, 16) for w in exp.get("acc", [])]


class Stop(Exception):
    pass


# What U-Boot prints when an access raises an exception in the processor, and what this board prints when it starts
# again (its console of 2026-11-19 after `reset`: the loader's line, then U-Boot's own, then a prompt — it does not
# wait at a countdown). The exception lines are U-Boot's as they are generally known; none has been seen on this board.
# A reply with one of these is not a reply that lost characters: what was loaded and configured before it is gone or
# in doubt, and the next command would be given to a board in another state. The names of the exceptions are looked
# for anywhere in a line (a dump may have begun its line before the access was made), the rest at a line's beginning.
# Anywhere in a line but in the text column of a dump: a whole line of `md.l` ends with one character for each byte
# it shows, and the bytes of a result are whatever the device holds — they may spell anything (dump_line()).
EXCEPTION = re.compile(r"data abort|prefetch abort|undefined instruction|software interrupt|Resetting CPU")
STARTED_AGAIN = re.compile(r"resetting \.\.\.|U-Boot SPL |Hit any key to stop autoboot")
BANNER = re.compile(r"U-Boot \d{4}\.\d{2}")       # the reply to `version` has this line, and no other reply has


def dump_line(ln: str) -> bool:
    """Whether `ln` is a whole line of U-Boot's `md.l`, to the character: the address and a colon, one to four words,
    blanks up to the column where the text begins, and of text one character for each byte — 47 characters and four
    more for each word. Every dump line in this board's console logs that the console did not damage has this form
    (4.8 million of them). A line that began as a dump and ends otherwise is not one."""
    m = re.match(r"[0-9a-f]{8}:((?: [0-9a-f]{8}){1,4})", ln)
    n = len(m.group(1)) // 9 if m else 0
    return bool(m) and len(ln) == 47 + 4 * n and ln[9 + 9 * n:47] == " " * (38 - 9 * n)


def restart_seen(cmd: str, text: str) -> str | None:
    """The first line of a reply that says U-Boot took an exception or the board started again; None if no line does.
    In the reply to `md.l` the whole lines of the dump are data and say nothing."""
    dump = cmd.split()[:1] == ["md.l"]
    for ln in text.splitlines():
        if dump and dump_line(ln):
            continue
        ln = ln.strip()
        if EXCEPTION.search(ln) or STARTED_AGAIN.match(ln) or (BANNER.match(ln) and cmd.split()[:1] != ["version"]):
            return ln
    return None


# What the serial line can raise under the run script, none of it a fault of the script: pyserial's SerialException and
# whatever the operating system says of a device that went away (OSError); the tty layer beneath pyserial, which
# raises an error of its own when a port that vanished is flushed (termios.error is not an OSError); and the
# program that sends a file, when it does not end in its time or cannot be run (subprocess: TimeoutExpired).
TRANSPORT = (OSError, termios.error, subprocess.SubprocessError)


def with_start(stage: str, exp: dict, start: int, came_from: str) -> dict:
    """The expected values of a set with its starting address replaced: the one word of a parameter block that may be
    given at run time, and only for a set made for it. The address must lie in the set's own envelope (the prober
    checks the same, and the guard holds every read to it). `came_from` says where the address was taken from; it
    goes into the run's record and changes nothing that is sent."""
    if stage not in STARTS_AT_RUN_TIME:
        raise ValueError(f"the starting address of {stage} is fixed")
    lo, hi = int(exp["params"][P_FAR_LO], 16), int(exp["params"][P_FAR_HI], 16)
    if not lo <= start <= hi:
        raise ValueError(f"{start:#010x} is outside the envelope {lo:#010x}..{hi:#010x} of {stage}")
    params = list(exp["params"])
    params[P_START] = f"{start:08x}"
    return dict(exp, params=params, chain={"start": f"{start:#010x}", "from": came_from})


def with_share(stage: str, exp: dict, share: int, census: dict | None = None, limit: int = s2_2_shares.LIST_MAX) -> dict:
    """The expected values of a set for one share of the census: the list of reads, the one word of the parameter
    block that counts them, and what follows from their number. Only for a set made for it. The shares are made from
    the census by s2_2_shares and by nothing else; which share a run is of goes into its record."""
    if stage not in SHARES_AT_RUN_TIME:
        raise ValueError(f"{stage} has no shares")
    every = s2_2_shares.shares(census if census is not None else json.loads(STAGES[stage]["census"].read_text()), limit)
    if not 0 <= share < len(every):
        raise ValueError(f"there are {len(every)} shares, 0 to {len(every) - 1}; {share} is none of them")
    reads = every[share]
    params = list(exp["params"])
    params[P_LIST_N] = f"{len(reads):08x}"
    form = STAGES[stage]["judge"]                    # the layout of the stage's result
    records = 4 + int(params[P_STATES_N], 16) * len(reads)
    return dict(exp, params=params, list=[f"{w:08x}" for w in s2_2_shares.list_words(reads)], records=records, result_words=form.HDR + records * form.REC,
                console=[f"SM{form.STAGE} start", f"SM{form.STAGE} end status=00000001 records={records:08x} anomalies=00000000 words={form.HDR + records * form.REC:08x}"],
                share={"index": share, "of": len(every), "reads": len(reads), "frames": sum(n for _, n in reads),
                       "first": f"{reads[0][0]:#010x}", "last": f"{reads[-1][0] + reads[-1][1] - 1:#010x}"})


def list_bytes(exp: dict) -> bytes:
    return b"".join(struct.pack("<I", int(w, 16)) for w in exp["list"])


def with_plan(stage: str, exp: dict, share: int | None, known: dict | None = None) -> dict:
    """The expected values of a set of S2.3 for one run: both lists, the words of the parameter block that count them
    and say what the run may write, and what follows from their numbers. The plan is made by s2_3_states from the
    design, the census and what S2.2 found, and by nothing else; which run it is goes into the record."""
    if stage not in PLANS_AT_RUN_TIME:
        raise ValueError(f"{stage} has no plan made at run time")
    kind = PLANS_AT_RUN_TIME[stage]
    if (share is None) != (kind == "code"):
        raise ValueError("the code run is one run" if kind == "code" else "a run of part 1 is of one share of the census's addresses (--share)"
                         if kind == "find" else "a run of the singles is one of four (--share)")
    known = known if known is not None else known_for(stage)
    if stage in PLANNED_BY:
        plan = PLANNED_BY[stage].plan(kind, share, known, known["census"], known.get("candidates"))
    else:
        plan = s2_3_states.plan(kind, share, known, known["census"], known["candidates"])
    params = list(exp["params"])
    params[P_STATES_N] = f"{len(plan['states']):08x}"
    params[P_LIST_N] = f"{len(plan['reads']):08x}"
    params[P_ACC_N] = f"{len(plan['entries']):08x}"
    params[P_PL_WRITE] = f"{plan['may_write']:08x}"
    form = STAGES[stage]["judge"]
    records = 4 + len(plan["states"]) * len(plan["reads"])
    hdr = 64 + 16 + 2 * len(plan["log"])
    reads = plan["reads"]
    return dict(exp, params=params, list=[f"{w:08x}" for w in s2_2_shares.list_words(reads)],
                acc=[f"{w:08x}" for w in s2_3_states.acc_words(plan["entries"], known)], records=records, result_words=hdr + records * form.REC,
                console=[f"SM{form.STAGE} start", f"SM{form.STAGE} end status=00000001 records={records:08x} anomalies=00000000 words={hdr + records * form.REC:08x}"],
                plan={"kind": kind, "share": share, "states": len(plan["states"]), "entries": len(plan["entries"]), "accesses": len(plan["log"]),
                      "reads": len(reads), "frames": sum(n for _, n in reads), "first": f"{reads[0][0]:#010x}", "last": f"{reads[-1][0] + reads[-1][1] - 1:#010x}"})


def acc_bytes(exp: dict) -> bytes:
    return b"".join(struct.pack("<I", int(w, 16)) for w in exp["acc"])


def before_go(exp: dict, pl_bytes: int, pl_crc: str) -> list[dict]:
    """The fixed steps up to and including `go`."""
    p: list[dict] = []
    add = lambda what, cmd, check, **kw: p.append({"what": what, "cmd": cmd, "check": check, **kw})  # noqa: E731
    add("prompt", "version", "U-Boot answers")
    add("cache off (the verified run had it off; the prober refuses otherwise)", "dcache off", "prompt")
    add("cache state", "dcache", "says the data cache is OFF", expect=r"Data \(writethrough\) Cache is OFF")
    add("status before the PL load", "md.l f800700c 1", "recorded")
    add("clear the sticky PCFG_DONE bit so that the load is seen as an edge (as the verified run did)", "mw.l f800700c 00000004 1", "prompt")
    add("status after the clear", "md.l f800700c 1", "bit 2 clear", bit=(2, False))
    add(f"the PL design ({pl_bytes} bytes, sha256 {exp['pl_design']['sha256'][:8]}…) from the card; by YMODEM if the card does not have it",
        f"fatload mmc 0:1 {PL_ADDR:08x} {pl_card_name(exp)}", "U-Boot reports the same size", card_or_ymodem=str(pl_file(exp)), size=pl_bytes, timeout=60)
    add("the design in RAM is the file, whichever way it came", f"crc32 {PL_ADDR:08x} {pl_bytes:x}", f"crc32 {pl_crc}", crc=pl_crc)
    add("configure the PL", f"fpga loadb 0 {PL_ADDR:08x} {pl_bytes:x}", "no error", timeout=60)
    add("status after the load", "md.l f800700c 1", "bit 2 (PCFG_DONE) set", bit=(2, True))
    if int(exp["params"][P_STAGE], 16) in (7, 8, 9):
        # S2.1 and every stage after it that touches user logic: the first access to it is made here, at the prompt, where a design that does not answer costs
        # a power cycle and nothing else. Before it, the PS side of the PL as the prober itself will want it: the four
        # words the set carries. The prober runs in U-Boot's context and mapping, so this read is the read it will make.
        for k, (addr, name) in enumerate(SLCR_GATES):
            want = int(exp["params"][P_SLCR + k], 16)
            add(f"{name} is as recorded on this board", f"md.l {addr:08x} 1", f"reads {want:08x}", word=want)
        ident = int(exp["params"][P_PL_ID], 16)
        add("THE FIRST ACCESS TO USER LOGIC: the design's identification register. If no prompt comes back, the design does not answer: power cycle",
            f"md.l {int(exp['params'][P_PL_LO], 16):08x} 1", f"reads {ident:08x}", word=ident)
    add("zero the parameter block", f"mw.l {PAR_ADDR:08x} 0 {PAR_WORDS:x}", "prompt")
    for i, w in enumerate(exp["params"]):
        if int(w, 16):
            add(f"parameter word {i}", f"mw.l {PAR_ADDR + 4 * i:08x} {w} 1", "prompt")
    par_crc = f"{zlib.crc32(b''.join(struct.pack('<I', int(w, 16)) for w in exp['params'])) & 0xFFFFFFFF:08x}"
    add("the parameter block is as intended", f"crc32 {PAR_ADDR:08x} {PAR_WORDS * 4:x}", f"crc32 {par_crc}", crc=par_crc)
    if "list" in exp:
        # S2.2: the list of reads, where the prober looks for it. It goes as a file, like the prober; what is in memory
        # afterwards is held to the list by its checksum, whichever way it came.
        raw = list_bytes(exp)
        list_crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        add(f"send the list of reads ({len(exp['list'])} reads, {len(raw)} bytes) by YMODEM", f"loady {LIST_ADDR:08x}", "U-Boot reports the same size",
            ymodem=exp.get("list_file", "<the list, written beside the run's record>"), size=len(raw))
        add("the list in RAM is the list", f"crc32 {LIST_ADDR:08x} {len(raw):x}", f"crc32 {list_crc}", crc=list_crc)
    if "acc" in exp:
        # S2.3: the list of accesses to the design, where the prober looks for it — sent and held the same way.
        raw = acc_bytes(exp)
        acc_crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        add(f"send the list of accesses ({len(exp['acc']) // 2} entries, {len(raw)} bytes) by YMODEM", f"loady {ACC_ADDR:08x}", "U-Boot reports the same size",
            ymodem=exp.get("acc_file", "<the list, written beside the run's record>"), size=len(raw))
        add("the list of accesses in RAM is the list", f"crc32 {ACC_ADDR:08x} {len(raw):x}", f"crc32 {acc_crc}", crc=acc_crc)
    add("clear the result header", f"mw.l {RES_ADDR:08x} 0 40", "prompt")
    add(f"send the prober ({exp['image_bytes']} bytes) by YMODEM", f"loady {IMG_ADDR:08x}", "U-Boot reports the same size",
        ymodem=str(IMAGE), size=exp["image_bytes"])
    add("the prober in RAM is the checked image", f"crc32 {IMG_ADDR:08x} {exp['image_bytes']:x}", f"crc32 {exp['image_crc32']}", crc=exp["image_crc32"])
    add("RUN", f"go {IMG_ADDR:08x}", "a prompt afterwards; the console lines and return code are recorded, not required", go=True, timeout=60)
    return p


AFTER_GO = [
    (f"md.l {RES_ADDR:08x} 40", "the result header", "magic and version; gives the record count N and the record size (any known layout is saved whole)"),
    (f"crc32 {RES_ADDR:08x} <4*(64+266*N)>", "the result checksum on the board", "recorded"),
    (f"fatwrite mmc 0:1 {RES_ADDR:08x} <name>.bin <bytes>", "save the result to the card under a name unique to this run", "'<bytes> bytes written'"),
    (f"fatload mmc 0:1 {0x11000000:08x} <name>.bin", "read the card copy back to a scratch address", "'<bytes> bytes read'"),
    (f"crc32 {0x11000000:08x} <bytes>", "the card copy is the result", "the board's crc32 of the result"),
    (f"crc32 / md.l {RES_ADDR:08x}+… <64+266*N>", f"pull the result over the console in pieces of {PIECE_WORDS} words: the board's crc32 of a piece, then the piece",
     "each piece has the board's crc32 of it; the whole has the board's crc32 of the result"),
    ("md.l f800700c 1", "status afterwards", "bit 2 (PCFG_DONE) set and no error bit"),
    (f"crc32 {IMG_ADDR:08x} <image bytes>", "the prober image in RAM after the run", "still the checked image"),
    ("version", "U-Boot still answers", "U-Boot answers"),
]


def md_words(text: str) -> list[int]:
    words: list[int] = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{8}):((?: [0-9a-f]{8}){1,4})", line.strip())
        if m:
            words += [int(x, 16) for x in m.group(2).split()]
    return words


def whole(cmd: str, text: str):
    """What the reply to a read-only command says, if the reply is whole; None if it is not.

    `md.l A N`: the N words, if the reply has every line of that dump — each at its address, with its four words (the
    last with what is left) — and no other line of a dump. `crc32 A B`: the checksum, if the reply has U-Boot's line
    for exactly that range. A reply that lost a stretch of characters lacks a line, or a line lacks a word, or the
    line that follows is not at the next address: it is not whole. Whether a whole reply says what was hoped for is
    not asked here.

    These two are the only commands whose reply may be asked for a second time (`read` in execute()); any other is an
    error here, so that none becomes one by being passed in."""
    w = cmd.split()
    if len(w) == 3 and w[0] == "md.l":
        a, n = int(w[1], 16), int(w[2], 16)
        lines = [(int(m.group(1), 16), [int(x, 16) for x in m.group(2).split()])
                 for m in (re.match(r"^([0-9a-f]{8}):((?: [0-9a-f]{8}){1,4})(?=\s|$)", ln.strip()) for ln in text.splitlines()) if m]
        if [(at, len(ws)) for at, ws in lines] != [(a + 4 * k, min(4, n - k)) for k in range(0, n, 4)]:
            return None
        return [x for _, ws in lines for x in ws]
    if len(w) == 3 and w[0] == "crc32":
        a, n = int(w[1], 16), int(w[2], 16)
        m = re.search(r"crc32 for %08x \.\.\. %08x ==> ([0-9a-f]{8})(?=\s)" % (a, a + n - 1), text)
        return m.group(1) if m else None
    raise ValueError(f"{cmd!r} is not a command whose reply may be asked for twice")


def execute(con, exp: dict, out: Path, send_file, known: dict, pl_bytes: int, pl_crc: str, card_name: str, stage: str = "s1a") -> dict:
    """Run the plan on a console object (`cmd(line, timeout) -> (bytes, prompt_seen)`, `interrupt()`), sending files
    with `send_file(con, loady_command, path) -> (bytes, prompt_seen)`. Writes result files into `out`."""
    J = STAGES[stage]["judge"]
    record: dict = {"stage": stage, "steps": [], "problems": [], "replies_not_whole": [], "card_file": card_name, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    problems = record["problems"]
    if "chain" in exp:                               # a starting address given at run time, and where it was taken from
        record["chain"] = exp["chain"]
    if "share" in exp:                               # which share of the census the run is of
        record["share"] = exp["share"]
    if "plan" in exp:                                # S2.3: which run of the step it is
        record["plan"] = exp["plan"]

    def link(call):
        """Everything that goes over the serial line goes through here, and nothing else does. A failure of the line is
        a stop like any other: the steps so far are in the record, the record is written, nothing more is sent."""
        try:
            return call()
        except TRANSPORT as e:
            raise Stop(f"the console failed after {len(record['steps'])} step(s) — {type(e).__name__}: {e}; nothing more was sent") from e

    def note(cmd: str, what: str, text: str, short) -> None:
        """Every reply goes into the record through here — a command's and a file transfer's alike — and is looked at
        before it is taken for anything, and before it may be asked for again."""
        seen = restart_seen(cmd, text)
        record["steps"].append({"n": len(record["steps"]) + 1, "what": what, "cmd": cmd, "reply": text if seen else short(text)})
        if seen:                                      # recorded whole and by name: whether the run is made again is decided
            record["restart"] = {"step": len(record["steps"]), "cmd": cmd, "line": seen}   # by the owner from the record, not here
            raise Stop(f"U-Boot took an exception or the board started again at {cmd!r} (its reply has the line {seen!r}); nothing more was sent")

    def do(cmd: str, what: str, timeout: float = 10) -> str:
        reply, ok = link(lambda: con.cmd(cmd, timeout))
        text = reply.decode("utf-8", "replace")
        note(cmd, what, text, lambda t: t if len(t) < 2000 else t[:300] + " … " + t[-300:])
        if not ok:
            raise Stop(f"no prompt after {cmd!r}")
        return text

    def transfer(loady: str, what: str, path: str) -> tuple[str, bool]:
        reply, ok = link(lambda: send_file(con, loady, path))
        text = reply.decode("utf-8", "replace")
        note(loady, what, text, lambda t: t[-400:])     # a size reported is not enough if the reply also shows a restart
        return text, ok

    def read(cmd: str, what: str, timeout: float = 10):
        """A read-only command whose reply has a known form (nothing else gets past whole()). If the reply is not whole
        the same command is sent again, at most MAX_READS times in all; every reply that was not whole is listed.
        A whole reply is returned as it is, whatever it says. None if no reply was whole. A missing prompt is not
        a reply that is not whole, and neither is one that shows an exception or a restart: there do() stops the run,
        as for any command."""
        for attempt in range(1, MAX_READS + 1):
            got = whole(cmd, do(cmd, what if attempt == 1 else f"{what} (attempt {attempt} of at most {MAX_READS}: the reply before was not whole)", timeout))
            if got is not None:
                return got
            record["replies_not_whole"].append({"cmd": cmd, "what": what, "attempt": attempt})
        return None

    try:
        _, ok = link(con.interrupt)
        if not ok:
            raise Stop("no U-Boot prompt")
        go_text = ""
        for s in before_go(exp, pl_bytes, pl_crc):
            if "ymodem" in s:
                text, ok = transfer(s["cmd"], s["what"], s["ymodem"])
                m = re.search(r"## Total Size\s+= 0x([0-9a-fA-F]+)", text)
                if not ok or not m or int(m.group(1), 16) != s["size"]:
                    raise Stop(f"the transfer for {s['cmd']!r} did not report {s['size']} bytes")
                continue
            if "bit" in s or "crc" in s or "word" in s:   # a status word, a checksum, a word with a known value: asked again if the reply is not whole
                got = read(s["cmd"], s["what"], s.get("timeout", 10))
                if "bit" in s and (got is None or bool(got[0] >> s["bit"][0] & 1) != s["bit"][1]):
                    raise Stop(f"{s['cmd']!r}: {s['check']}" + (f" (read {got[0]:08x})" if got else " (nothing read)"))
                if "word" in s and (got is None or got[0] != s["word"]):
                    raise Stop(f"{s['cmd']!r}: {s['check']}" + (f" (read {got[0]:08x})" if got else " (nothing read)"))
                if "crc" in s and got != s["crc"]:
                    raise Stop(f"{s['cmd']!r}: crc32 {got}, expected {s['crc']}")
                continue
            text = do(s["cmd"], s["what"], s.get("timeout", 10))
            if "card_or_ymodem" in s:
                m = re.search(r"(\d+) bytes read", text)
                record["pl_source"] = "card"
                if not m or int(m.group(1)) != s["size"]:            # not on the card (or not this size): send it
                    record["pl_source"] = "ymodem"
                    text, ok = transfer(f"loady {PL_ADDR:08x}", "the PL design by YMODEM", s["card_or_ymodem"])
                    m = re.search(r"## Total Size\s+= 0x([0-9a-fA-F]+)", text)
                    if not ok or not m or int(m.group(1), 16) != s["size"]:
                        raise Stop(f"the PL design could not be loaded from the card or sent ({s['size']} bytes)")
                continue
            if "expect" in s and not re.search(s["expect"], text):
                raise Stop(f"{s['cmd']!r}: {s['check']}")
            if s.get("go"):
                go_text = text
        record["went"] = True
        m = re.search(r"## Application terminated, rc = 0x([0-9A-Fa-f]+)", go_text)
        record["return_code"] = f"0x{int(m.group(1), 16):x}" if m else None
        record["console"] = [ln.strip() for ln in go_text.splitlines() if re.match(r"SM\d ", ln.strip())]   # the prober's lines, of whichever stage ran

        # ---- from here on: save first, judge afterwards
        hdr = read(f"md.l {RES_ADDR:08x} 40", "the result header")
        if hdr is None:
            raise Stop(f"the result header could not be read whole in {MAX_READS} attempts")
        (out / "header.bin").write_bytes(b"".join(struct.pack("<I", x) for x in hdr))
        has_header = hdr[0] == 0x31524D53 and hdr[1] == 1
        n, total = hdr[3], hdr[5]
        # How much to save does not depend on the stage that was asked for: a result that is consistent in itself is
        # saved whole and left to the judge. Only if the header fits no layout at all is the size not its own to give;
        # then everything a result could occupy is saved.
        layouts: dict[tuple[int, int], list[str]] = {}       # stages may share a layout (s1b0 and s1b0b do)
        for name, m in STAGES.items():
            layouts.setdefault((m["judge"].HDR, m["judge"].REC), []).append(name)
        having = layouts.get((hdr[7], hdr[6]), [])
        fits = stage if stage in having else having[0] if having else None
        if has_header and fits and n <= STAGES[fits]["judge"].MAX_RECORDS and total == hdr[7] + n * hdr[6]:
            record["result_layout"] = fits
            if fits != stage:
                problems.append(f"the result has the layout of stage {fits}, not of the stage that was run ({stage})")
        else:
            record["result_layout"] = None
            problems.append(("the result header's sizes fit no known layout" if has_header else "there is no result header at the result address (magic or version)")
                            + f" (records {n}, words {total}, record size {hdr[6]}); the largest possible result ({MAX_RESULT_WORDS} words) is saved instead")
            total = MAX_RESULT_WORDS
        nbytes = total * 4
        record["result_words"] = total
        record["board_crc32"] = read(f"crc32 {RES_ADDR:08x} {nbytes:x}", "the result checksum on the board", 20)
        if record["board_crc32"] is None:
            raise Stop("no crc32 of the result from the board")

        text = do(f"fatwrite mmc 0:1 {RES_ADDR:08x} {card_name} {nbytes:x}", "save the result to the card", 60)
        m = re.search(r"(\d+) bytes written", text)
        record["card_written"] = bool(m) and int(m.group(1)) == nbytes
        if not record["card_written"]:
            problems.append(f"the card write was not confirmed for {nbytes} bytes: {text.strip()[-120:]!r}")
        else:                                        # by content, not by U-Boot's word: read the file back and checksum it
            text = do(f"fatload mmc 0:1 {SCRATCH_ADDR:08x} {card_name}", "read the card copy back to a scratch address", 60)   # sent once: it writes memory
            m = re.search(r"(\d+) bytes read", text)
            copy = read(f"crc32 {SCRATCH_ADDR:08x} {nbytes:x}", "the card copy is the result", 20)
            record["card_verified"] = bool(m) and int(m.group(1)) == nbytes and copy == record["board_crc32"]
            if not record["card_verified"]:
                problems.append("the file read back from the card is not the result (size or crc32 differs)")

        # The console is a lossy path (11 of 28 whole-result pulls came back damaged on 2026-11-14, and three attempts at
        # a large result were not always enough). So the result is pulled in pieces: for each the board is asked for its
        # own crc32 of that piece, and the piece is pulled again, a bounded number of times, until the host's copy has
        # it. Every repeat is recorded. In the end the whole must have the crc32 the board gave for the whole result —
        # that, and nothing a piece says, decides whether this is the board's copy.
        record["pull"] = {"piece_words": PIECE_WORDS, "pieces": 0, "repeated": []}
        words: list[int] = []
        for k, at in enumerate(range(0, total, PIECE_WORDS)):
            n_piece = min(PIECE_WORDS, total - at)
            addr = RES_ADDR + 4 * at
            piece = read(f"crc32 {addr:08x} {4 * n_piece:x}", f"the board's checksum of piece {k} of the result", 20)
            if piece is None:
                raise Stop(f"no crc32 of piece {k} of the result from the board")
            for attempt in range(1, MAX_PIECE_PULLS + 1):
                got = md_words(do(f"md.l {addr:08x} {n_piece:x}", f"pull piece {k} of the result over the console (attempt {attempt} of at most {MAX_PIECE_PULLS})", 120))
                crc = f"{zlib.crc32(b''.join(struct.pack('<I', x) for x in got)) & 0xFFFFFFFF:08x}"
                if len(got) == n_piece and crc == piece:
                    break
                record["pull"]["repeated"].append({"piece": k, "attempt": attempt, "words": len(got), "crc32": crc, "board_crc32": piece})
            else:
                raise Stop(f"piece {k} of the result could not be pulled whole in {MAX_PIECE_PULLS} attempts"
                           + ("; the card file holds the result" if record.get("card_verified") else ""))
            words += got
            record["pull"]["pieces"] = k + 1
        raw = b"".join(struct.pack("<I", x) for x in words)
        host_crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        record["host_crc32"] = host_crc
        if len(words) != total or host_crc != record["board_crc32"]:        # `total` words were asked for, whichever way it was sized
            (out / "result_unverified.bin").write_bytes(raw)
            raise Stop(f"the pulled copy ({len(words)} words, crc32 {host_crc}) is not the board's ({total} words, crc32 {record['board_crc32']}), "
                       "although each piece matched the board's crc32 of that piece")
        (out / "result.bin").write_bytes(raw)
        # The header was accepted above by its form; here it is held to the copy that has the board's checksum.
        if words[:len(hdr)] != hdr:
            problems.append("the header as it was read before the pull is not the header of the pulled result")

        verdict = J.judge(words, known, planned_words(exp))
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n")
        record["judge"] = verdict["verdict"]
        if record["return_code"] != verdict.get("expected_return_code"):
            problems.append(f"the return code was {record['return_code']}, the result implies {verdict.get('expected_return_code')}")
        if record["console"] != verdict.get("expected_console"):
            problems.append(f"the console showed {record['console']}, the result implies {verdict.get('expected_console')}")
        live = read("md.l f800700c 1", "status afterwards")
        record["int_sts_afterwards"] = f"{live[0]:08x}" if live else None
        if not live or not live[0] & J.PCFG_DONE or live[0] & J.ERR_MASK:
            problems.append(f"the live status after the run is {record['int_sts_afterwards']}: PCFG_DONE clear or an error bit set")
        after = read(f"crc32 {IMG_ADDR:08x} {exp['image_bytes']:x}", "the prober image in RAM after the run")
        if after != exp["image_crc32"]:
            problems.append(f"the prober image in RAM after the run has crc32 {after}, not {exp['image_crc32']}: what ran may not be what was checked")
        do("version", "U-Boot still answers")
    except Stop as e:
        record["stop"] = str(e)
        problems.append(str(e))
    record["verdict"] = "PASS" if record.get("judge") == "PASS" and not problems else "FAIL"
    (out / "run.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def ymodem_send(con, loady: str, path: str):
    """Send one file with `sb` over the console's serial port."""
    import serial
    from uboot_console import DEV
    con.s.reset_input_buffer(); con.tx(loady.encode() + b"\r")
    end = time.time() + 8; got = b""
    while time.time() < end and b"## Ready for binary (ymodem) download" not in got:
        d = con.s.read(4096); got += d; con.log.write(d)
    if b"## Ready for binary" not in got:
        return got, False
    time.sleep(0.5); con.s.close()
    with open(DEV, "rb+", buffering=0) as port:
        r = subprocess.run(["sb", "-k", path], stdin=port, stdout=port, stderr=subprocess.PIPE, timeout=900)
    con.s = serial.Serial(DEV, 115200, timeout=0.1)
    reply, ok = con.until_prompt(20)
    return reply, ok and r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stage", choices=sorted(STAGES), default="s1a")
    ap.add_argument("--start", type=lambda s: int(s, 16), help="hex; only for a set whose starting address is given at run time (s1b2, s1b3, s1b4, s1b5)")
    ap.add_argument("--start-from", default="given on the command line", help="where the starting address was taken from; recorded, not used")
    ap.add_argument("--share", type=int, help="which share of the census's addresses (s2_2, s2_4f), or which of the four runs of the singles (s2_3s); only for those sets")
    a = ap.parse_args()
    exp = json.loads(STAGES[a.stage]["expected"].read_text())
    if a.stage in PLANS_AT_RUN_TIME:
        try:
            exp = with_plan(a.stage, exp, a.share)
        except ValueError as e:
            print(f"REFUSED: {e}"); return 2
    elif (a.share is not None) != (a.stage in SHARES_AT_RUN_TIME):
        print(f"REFUSED: {a.stage} is run a share at a time (--share)" if a.share is None else f"REFUSED: {a.stage} has no shares"); return 2
    elif a.share is not None:
        try:
            exp = with_share(a.stage, exp, a.share)
        except ValueError as e:
            print(f"REFUSED: {e}"); return 2
    if a.start is not None:
        try:
            exp = with_start(a.stage, exp, a.start, a.start_from)
        except ValueError as e:
            print(f"REFUSED: {e}"); return 2
    if not pl_file(exp).is_file():
        print(f"REFUSED: the PL design of this set is not staged ({pl_file(exp)})"); return 2
    img, pl = IMAGE.read_bytes(), pl_file(exp).read_bytes()
    if hashlib.sha256(img).hexdigest() != exp["image_sha256"]:
        print("REFUSED: the image on disk is not the one the tests fixed in expected.json"); return 2
    if hashlib.sha256(pl).hexdigest() != exp["pl_design"]["sha256"] or len(pl) != exp["pl_design"]["bytes"]:
        print("REFUSED: the staged PL design is not the one this set was fixed with"); return 2
    pl_crc = f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}"
    if a.out and (a.out.exists() or a.out.is_symlink()):   # asked before the dry run as well: a dry run with --out says what the run itself would say of it
        print("REFUSED: --out must name a directory that does not exist yet"); return 2
    if a.dry_run or not a.go:
        print(f"stage {a.stage}" + (f", starting at {exp['chain']['start']} ({exp['chain']['from']})" if "chain" in exp else "")
              + (f", share {exp['share']['index']} of {exp['share']['of']}: {exp['share']['reads']} reads, {exp['share']['frames']} frames, "
                 f"{exp['share']['first']} .. {exp['share']['last']}" if "share" in exp else "")
              + (f", {'the code run' if exp['plan']['kind'] == 'code' else ('part 1, share %d' if exp['plan']['kind'] == 'find' else 'the singles, run %d') % exp['plan']['share']}: {exp['plan']['states']} states, "
                 f"{exp['plan']['entries']} entries in the list of accesses, {exp['plan']['reads']} reads a state, {exp['plan']['first']} .. {exp['plan']['last']}"
                 if "plan" in exp else ""))
        print(f"image {exp['image_sha256']}  ({exp['image_bytes']} bytes)")
        print(f"PL    {exp['pl_design']['sha256']}  ({len(pl)} bytes)\n")
        steps = before_go(exp, len(pl), pl_crc)
        for i, s in enumerate(steps, 1):
            print(f"{i:3d}. {s['cmd']:44s} # {s['what']}  ->  {s['check']}")
            if "card_or_ymodem" in s:                 # the branch taken when the card has no file of that size
                branch = f"loady {PL_ADDR:08x}"
                print(f"{i:3d}a. {branch:43s} # ONLY IF step {i} did not report {s['size']} bytes read: send the PL design by YMODEM  ->  U-Boot reports the same size")
        print("     --- after go, whatever it reported: save first, judge afterwards ---")
        size = f"{STAGES[a.stage]['judge'].HDR}+{STAGES[a.stage]['judge'].REC}*N"   # the header — with the PL block, where the stage has one — and N records
        for i, (cmd, what, check) in enumerate(AFTER_GO, len(steps) + 1):
            cmd = cmd.replace("64+266*N", size)
            print(f"{i:3d}. {cmd:44s} # {what}  ->  {check}")
        print("     branches after go:")
        print(f"       - if the header fits no known layout, or there is no header: <bytes> is 4*{MAX_RESULT_WORDS}, the largest result any stage can produce")
        print("       - the card read-back (fatload and its crc32) is done only if fatwrite confirmed the size; otherwise the run fails, and the pull still happens")
        print(f"       - a piece that does not have the board's crc32 of it is pulled again, at most {MAX_PIECE_PULLS} times in all, every repeat recorded; if a piece cannot be had, or the whole does not have the board's crc32, the run stops there")
        print(f"     a reply that is not whole (before go or after it): only `md.l` of a few words and `crc32` are sent again, at most {MAX_READS} times in all,")
        print("       every attempt recorded; a whole reply with another value than the one wanted stops or fails the run as before; nothing else is ever sent twice")
        print("\nDry run: nothing was sent.")
        return 0
    if not a.out:
        print("REFUSED: --out must name a directory that does not exist yet"); return 2
    a.out.mkdir(parents=True)
    if "list" in exp:                                # the list as it is sent, kept beside the run's record
        (a.out / "list.bin").write_bytes(list_bytes(exp))
        exp = dict(exp, list_file=str(a.out / "list.bin"))
    if "acc" in exp:                                 # and the list of accesses
        (a.out / "acc.bin").write_bytes(acc_bytes(exp))
        exp = dict(exp, acc_file=str(a.out / "acc.bin"))
    os.environ["SELFMAP_CONSOLE_LOG"] = str(a.out / "console.log")
    from uboot_console import UB
    card_name = "s%07x.bin" % (int(time.time()) & 0xFFFFFFF)
    record = execute(UB(), exp, a.out, ymodem_send, known_for(a.stage), len(pl), pl_crc, card_name, a.stage)
    print("stop:", record.get("stop")); print("problems:", record["problems"]); print("verdict:", record["verdict"])
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

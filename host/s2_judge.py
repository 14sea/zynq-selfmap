#!/usr/bin/env python3
"""Judge a result of stage 6 (S2.0) or stage 7 (S2.1) on the host — docs/s2_plan.md, sections 6 and 7.

The same principles as every judge here: nothing the board reports is taken on trust; codes, order, status and
counts are derived again from the raw words; the parameters the prober echoed must be the planned ones; the gate
readings are judged; and only then what the run was for.

Both stages are the table-driven stage with one thing more: the register read after each operation is chosen by the
host from five — FAR, IDCODE, CTL0, STAT, and since S3.0 COR0 (docs/s3_plan.md, section 5) — four bits an operation in
parameter word 12.

  * A value read from FAR must be the one the rule found in S1b.0 and S1b.0b gives: one step for every 101 words read,
    the pad included. That is the control: reading the other registers this way has changed nothing.
  * IDCODE has a known answer: its low 28 bits, as the JTAG scans of these boards gave them.
  * CTL0, STAT and COR0 have none. Each must read the same every time; what CTL0 holds is the finding of S2.0,
    reported with its bit 8 (GLUTMASK_B, UG470 table 5-27) said in words; what COR0 holds is the finding of S3.0,
    reported with its fields (UG470 table 5-31) and SINGLE, bit 23, said in words. Nothing is concluded from any
    other bit.

Stage 6 runs with the carrier loaded, and every frame it delivers is held to its known content. Stage 7 runs with
the probe design: no frame has a known content, and the reference frame is held to its own first reading.

Stage 7 has, between the header and the records, the PL block: the four SLCR words read as gates, and every access
the prober made to the design's registers, in order. The judge knows the sequence the prober is to make and walks
the log against it: each access must be the one that is due, each value written the one that is due, and each value
read must be what the design has to answer — the identification word, the scratch register giving back what was
written, a counter that goes on, the RAM reading back each of four states, the shift registers reading alike twice
and holding what the design's source loads into them, and the design's own count of writes. The first answer that
is not so ends the log, and the code the prober gave must be the one that answer implies.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import packets  # noqa: E402
from s1a_judge import (CLEANUP, CTRL_MASK, ERR_MASK, KIND, MCTRL_LPBK, PCFG_DONE, SCTLR_C, SENTINEL,  # noqa: E402,F401
                       _command_outcome, return_code)
from s1b0_judge import DATA, DATA_WORDS, FARBLK, FRAME, MAX_READ_FRAMES, NO_OP, NONE, NOOP, POLLING, REC, describe, frames_stream, read_words  # noqa: E402

HDR0 = 64
PL_LOG_MAX = 1280
PLB_WORDS = 16 + 2 * PL_LOG_MAX
PLB_MAGIC = 0x4C504D53
MAX_OPS, MAX_REPEATS = 8, 8
MAX_RECORDS = 1 + MAX_OPS * MAX_REPEATS * 2 + 1
REGS = {0: "FAR", 1: "IDCODE", 2: "CTL0", 3: "STAT", 4: "COR0"}
READ_HEADER = {0: 0x28002001, 1: 0x28018001, 2: 0x2800A001, 3: 0x2800E001, 4: 0x28012001}
# the low 28 bits of the device identification, as the JTAG scans of these boards gave it (0x13722093; the top four
# bits are the revision, which is the die's own)
IDCODE_LOW28 = 0x3722093
SEU_EN = 0x00000100
GATE_STATUS = {0x101: "CTRL gate", 0x102: "loopback gate", 0x103: "PCFG_DONE gate", 0x104: "data-cache gate", 0x105: "SEU_EN gate",
               0x110: "LVL_SHFTR_EN gate", 0x111: "FPGA_RST_CTRL gate", 0x112: "FPGA0_CLK_CTRL gate", 0x113: "PLL_STATUS gate"}
SLCR_NAMES = ("LVL_SHFTR_EN", "FPGA_RST_CTRL", "FPGA0_CLK_CTRL", "PLL_STATUS")
# control register 0, as UG470's table 5-27 names its bits. Reported; only bit 8 is the finding.
CTL0_BITS = {31: "EFUSE_KEY", 30: "ICAP_SELECT", 12: "OverTempPowerDown", 10: "ConfigFallback", 8: "GLUTMASK_B", 7: "FARSRC",
             6: "DEC", 5: "SBITS[1]", 4: "SBITS[0]", 3: "PERSIST", 0: "GTS_USR_B"}
# configuration options register 0, as UG470's table 5-31 names its fields: (name, lowest bit, width). Reported; SINGLE
# is the finding of S3.0 (docs/s3_plan.md, section 5): whether a capture needs RCAP before the next one.
COR0_FIELDS = (("PWRDWN_STAT", 27, 1), ("DONE_PIPE", 25, 1), ("DRIVE_DONE", 24, 1), ("SINGLE", 23, 1), ("OSCFSEL", 17, 6),
               ("SSCLKSRC", 15, 2), ("DONE_CYCLE", 12, 3), ("MATCH_CYCLE", 9, 3), ("LOCK_CYCLE", 6, 3), ("GTS_CYCLE", 3, 3),
               ("GWE_CYCLE", 0, 3))
SSCLKSRC = {0: "CCLK", 1: "UserClk", 2: "JTAGClk", 3: "JTAGClk"}

# ---- the probe design s2a, as the prober is to use it (prober/sm.h; pl/s2a/design.json)
PL_BASE, PL_SPAN = 0x40000000, 0x20
PL_ID, PL_SCRATCH, PL_COUNT, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR, PL_SRL_DATA, PL_WRITES = range(0, 0x20, 4)
PL_WRITABLE = (PL_SCRATCH, PL_RAM_ADDR, PL_RAM_DATA, PL_SRL_ADDR)
RAM_DEPTH, SRL_DEPTH, RAM_STATES = 64, 32, 4
SCRATCH_WORDS = (0x00000000, 0xFFFFFFFF, 0xA5A55A5A, 0x5A5AA5A5)
PL_CODES = {0: "nothing wrong", 1: "the prober's own helper refused an address", 2: "the identification register", 3: "the scratch register",
            4: "the counter", 5: "the LUT RAM", 6: "the shift registers", 7: "the design's count of writes", 8: "the log is full"}


def ram_pattern(state: int, a: int) -> int:
    return (0, 0xF, a & 0xF, ~a & 0xF)[state]


def pl_schedule(pl_id: int) -> list[dict]:
    """Every access the prober is to make to the design, in order. A step: the offset, whether it is a write, the
    value written, and — for a read whose answer is judged — the code a wrong answer implies and what decides it:
    a value, or `same_as`, the index of an earlier step whose value it must equal (`differs_from`: must not)."""
    s: list[dict] = []
    w = lambda off, v: s.append({"off": off, "write": True, "value": v})  # noqa: E731
    r = lambda off, **kw: s.append({"off": off, "write": False, **kw})  # noqa: E731
    r(PL_ID, code=2, value=pl_id)
    for word in SCRATCH_WORDS:
        w(PL_SCRATCH, word); r(PL_SCRATCH, code=3, value=word)
    r(PL_COUNT); r(PL_COUNT, code=4, differs_from=len(s) - 1)
    for state in range(RAM_STATES):
        for a in range(RAM_DEPTH):
            w(PL_RAM_ADDR, a); w(PL_RAM_DATA, ram_pattern(state, a))
        for a in range(RAM_DEPTH):
            w(PL_RAM_ADDR, a); r(PL_RAM_DATA, code=5, value=ram_pattern(state, a))
    first = len(s)
    for half in range(2):
        for a in range(SRL_DEPTH):
            w(PL_SRL_ADDR, a)
            if half == 0:
                r(PL_SRL_DATA)
            else:
                r(PL_SRL_DATA, code=6, same_as=first + 2 * a + 1)
    r(PL_WRITES, code=7, value=RAM_STATES * RAM_DEPTH)
    return s


def console_line(stage: int, status: int, records: int, anomalies: int) -> str:
    if status == 0x500:
        return "SM%d end status=%08x" % (stage, status)
    return "SM%d end status=%08x records=%08x anomalies=%08x words=%08x" % (stage, status, records, anomalies, header_words(stage) + records * REC)


def header_words(stage: int) -> int:
    return HDR0 + (PLB_WORDS if stage == 7 else 0)


def planned_ops(par: list[int]) -> list[tuple[int, int, int]]:
    """(address, frames, register) for each operation of the table."""
    return [(par[16 + k], (par[10] >> (4 * k)) & 0xF, (par[12] >> (4 * k)) & 0xF) for k in range(min(par[6], MAX_OPS))]


def params_valid(par: list[int], stage: int) -> bool:
    lo, hi, ref, n_ops, repeats, budget, poll_limit = par[3:10]
    if (par[0], par[1], par[2]) != (0x31504D53, 1, stage) or lo > hi or not lo <= ref <= hi:
        return False
    if not 1 <= n_ops <= MAX_OPS or not 1 <= repeats <= MAX_REPEATS or budget > 64 or not 0 < poll_limit <= 0x10000000:
        return False
    if par[11] or par[13] or par[14] or par[15] & 0xFF or par[15] >> 8 not in POLLING or par[27]:
        return False
    for k in range(MAX_OPS):
        sel, m, far = (par[12] >> (4 * k)) & 0xF, (par[10] >> (4 * k)) & 0xF, par[16 + k]
        if k >= n_ops:
            if sel or m or far:
                return False
        elif sel not in REGS or far < lo or far > hi or not (m in (0, NONE) or (1 <= m <= MAX_READ_FRAMES and far + m - 1 <= hi)):
            return False
    if stage == 7:
        return PL_BASE <= par[24] <= par[25] < PL_BASE + PL_SPAN
    return not any(par[24:32])


def judge(words: list[int], known: dict | None, planned: list[int], stage: int = 6) -> dict:
    """`known`: for stage 6 the known frames (data/known_frames_17A6.json); for stage 7 the facts of the probe
    design (pl/s2a/design.json), of which the words loaded into the shift registers are used."""
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append
    HB = header_words(stage)

    def invalid(why: str) -> dict:
        bad(why); out["verdict"] = "INVALID"; return out

    if len(words) < HDR0 or words[0] != 0x31524D53 or words[1] != 1:
        return invalid("not a result buffer (magic or version)")
    status, n, anomalies, total, rec_words, hdr_words = words[2:8]
    stop_record = words[18]
    out["header"] = {"status": f"{status:#x}", "records": n, "anomalies": anomalies, "total_words": total,
                     "ctrl": f"{words[8]:08x}", "mctrl": f"{words[9]:08x}", "int_sts_initial": f"{words[10]:08x}",
                     "status_initial": f"{words[11]:08x}", "sctlr": f"{words[12]:08x}", "cpsr": f"{words[13]:08x}",
                     "sp": f"{words[14]:08x}", "r9": f"{words[15]:08x}", "int_sts_final": f"{words[16]:08x}",
                     "status_final": f"{words[17]:08x}", "stop_record": f"{stop_record:#x}"}
    out["expected_console"] = [f"SM{stage} start", console_line(stage, status, n, anomalies)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if (rec_words, hdr_words) != (REC, HB) or n > MAX_RECORDS or total != HB + n * REC:
        return invalid(f"sizes do not add up for a stage-{stage} result: total {total}, records {n}, record size {rec_words}, header {hdr_words}")
    if status == 0x500 and n:
        return invalid("a parameter refusal with records")
    if len(words) != total:
        return invalid(f"the buffer has {len(words)} words, the header says {total}")
    if any(words[19:32]):
        bad("reserved header words are not zero")

    par = words[32:64]
    lo, hi, ref, n_ops, repeats, budget, poll_limit = par[3:10]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "operations": n_ops,
                     "repeats": repeats, "anomaly_budget": budget, "poll_limit": poll_limit}
    if list(par) != list(planned):
        differ = [k for k in range(32) if k >= len(planned) or par[k] != planned[k]]
        bad(f"the parameters the prober echoed are not the planned ones (word(s) {differ}): the run did not do what was asked")

    # ---- the PL block's own form (stage 7), before anything is read out of it
    plb: list[int] = []
    log: list[tuple[int, int]] = []
    if stage == 7:
        plb = words[HDR0:HB]
        if plb[0] != PLB_MAGIC:
            return invalid("the PL block does not begin with its magic")
        if plb[1] > PL_LOG_MAX:
            return invalid(f"the PL block counts {plb[1]} accesses, more than it has room for")
        log = [(plb[16 + 2 * i], plb[17 + 2 * i]) for i in range(plb[1])]
        if any(plb[8:16]):
            bad("reserved words of the PL block are not zero")
        if any(plb[16 + 2 * plb[1]:]):
            bad("the PL block holds words after the last access it counts")
    if status == 0x500:
        if stage == 7 and (plb[1] or plb[2] or any(plb[4:8]) or plb[3] != 0xFFFFFFFF):
            bad("a parameter refusal, yet the PL block is not empty")
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    if not params_valid(par, stage):
        return invalid(f"the echoed parameters are not a valid stage-{stage} parameter block")
    ops = planned_ops(par)
    out["params"]["polling_loop"] = POLLING[par[15] >> 8]
    out["params"]["ops"] = [[f"{far:#010x}", "none" if m == NONE else m, REGS[reg]] for far, m, reg in ops]

    # ---- the gates
    ctrl, mctrl, sts0, sctlr, sts1 = words[8], words[9], words[10], words[12], words[16]
    failing = (0x101 if (ctrl & CTRL_MASK) != CTRL_MASK else 0x105 if ctrl & SEU_EN else 0x102 if mctrl & MCTRL_LPBK
               else 0x103 if not sts0 & PCFG_DONE else 0x104 if sctlr & SCTLR_C else 0)
    slcr_read = stage == 7 and not failing            # the four SLCR words are read only once the gates before them hold
    if stage == 7:
        out["params"]["pl_envelope"] = [f"{par[24]:#010x}", f"{par[25]:#010x}"]
        out["slcr"] = {name: {"read": f"{plb[4 + k]:08x}", "wanted": f"{par[28 + k]:08x}"} for k, name in enumerate(SLCR_NAMES)}
        if slcr_read:
            failing = next((0x110 | k for k in range(4) if plb[4 + k] != par[28 + k]), 0)
        elif any(plb[4:8]):
            bad("SLCR words are recorded although a gate before them fails")
    if status in GATE_STATUS:
        if n:
            bad("a gate stop with records")
        if stage == 7 and (plb[1] or plb[2] or plb[3] != 0xFFFFFFFF):
            bad("a gate stop, yet the PL block shows an access to the design")
        if failing != status:
            bad(f"the run reports a stop at the {GATE_STATUS[status]}, but the readings in its header "
                + (f"fail the {GATE_STATUS[failing]}" if failing else "satisfy every gate"))
        bad(f"the run stopped at the {GATE_STATUS[status]}"); out["verdict"] = "FAIL"; return out
    if failing:
        bad(f"the readings in the header fail the {GATE_STATUS[failing]}, yet the run went on")
    if status == 1 and (not sts1 & PCFG_DONE or sts1 & ERR_MASK):
        bad(f"the run reports done, but its final INT_STS {sts1:08x} has PCFG_DONE clear or an error bit set")

    # ---- the records, each from its raw words
    frames_known = {int(k, 16): [int(w, 16) for w in v["words"]] for k, v in known["frames"].items()} if stage == 6 and known else {}
    recs: list[dict] = []
    first_clean: dict[int, dict] = {}
    seen: dict[int, dict[int, list[int]]] = {}        # register -> value read -> records
    for i in range(n):
        r = words[HB + i * REC: HB + (i + 1) * REC]
        fb = r[FARBLK:FARBLK + 8]
        far, kind, code, m, op = r[0], r[1], r[2], r[14], r[15]
        reg = ops[op][2] if kind == 0 and op < len(ops) else 0
        rec = {"i": i, "far": far, "kind": kind, "code": code, "n": m, "op": op, "repeat": r[12], "ref_equal": r[10],
               "value": fb[4], "reg": reg, "frames": []}
        recs.append(rec)
        if not (m in (0, NONE) or 1 <= m <= MAX_READ_FRAMES):
            bad(f"record {i}: {m} frames per read"); m = 1
        delivered = 0 if m == NONE else m
        nwords = read_words(m)
        data, tail = r[DATA:DATA + nwords], r[DATA + nwords:]
        rec["frames"] = [data[FRAME * (j + 1):FRAME * (j + 2)] for j in range(delivered)]
        if far < lo or far > hi or far + max(delivered, 1) - 1 > hi:
            bad(f"record {i}: reads {far:#010x} + {delivered} frame(s), outside the envelope")
        if r[13] != 0 or code == 0x30:
            bad(f"record {i}: the prober's guard refused its own stream (guard word {r[13]:#x})")
        if any(tail):
            bad(f"record {i}: words after the {nwords} data words are not zero")
        if fb[7]:
            bad(f"record {i}: reserved words are not zero")
        for name, got, want in (("frame read stream", r[16:59], frames_stream(far, m)),
                                (f"{REGS[reg]} read stream", r[59:63], [NOOP, READ_HEADER[reg], NOOP, NOOP]),
                                ("cleanup stream", r[63:68], CLEANUP)):
            if got != want:
                bad(f"record {i}: the {name} is not the pinned one")
            for p in packets.readonly_problems(got, lo, hi, DATA_WORDS):
                bad(f"record {i}: the {name} is not read-only: {p}")
        derived = 0
        attempted = done = False
        for name, sts, polls in (("frame command", r[3], r[4]), ("frame read", r[5], r[6]), ("register command", fb[0], fb[1]),
                                 ("register read", fb[2], fb[3]), ("cleanup", r[7], r[8])):
            if derived:
                if sts or polls:
                    bad(f"record {i}: the {name} transfer has a status although an earlier transfer failed")
                continue
            if name == "frame read" and m == NONE:
                if sts or polls:
                    bad(f"record {i}: a frame read transfer has a status in an operation that reads nothing")
                continue
            derived = _command_outcome(sts, polls, poll_limit)
            if derived < 0:
                bad(f"record {i}: the {name} transfer's status {sts:08x} after {polls} poll(s) is neither done, failed nor timed out")
                derived = 0xFF
            if polls > poll_limit:
                bad(f"record {i}: {polls} polls, above the limit {poll_limit}")
            if name == "register command" and derived == 0:
                attempted = True
            if name == "register read" and derived == 0:
                done = True
        survivors = sum(1 for w in data if w == SENTINEL)
        if survivors != r[9]:
            bad(f"record {i}: {survivors} sentinel word(s) in the data, the record says {r[9]}")
        unread = 1 if attempted and fb[4] == SENTINEL else 0
        if fb[5] != unread or (not attempted and fb[4]):
            bad(f"record {i}: the value {fb[4]:08x} / unread flag {fb[5]} do not fit a register read that was {'queued' if attempted else 'never queued'}")
        if derived == 0:
            if survivors:
                derived = 0x10
            elif any(data[:FRAME]):
                derived = 0x11
            elif unread:
                derived = 0x14
            elif kind == 0 and op in first_clean:
                if first_clean[op]["frames"] != rec["frames"]:
                    derived = 0x12
                elif first_clean[op]["value"] != fb[4]:
                    derived = 0x13
        if code != derived and not (code == 0x23 and derived in (0, 0x10, 0x11, 0x12, 0x13, 0x14)):
            bad(f"record {i}: code {code:#x}, but its raw words say {derived:#x}")
        if code == 0 and kind == 0:
            first_clean.setdefault(op, rec)
        # a value is a measurement whenever the register read itself succeeded, whatever else is wrong with the record
        rec["measured"] = done and not unread
        if rec["measured"]:
            seen.setdefault(reg, {}).setdefault(fb[4], []).append(i)
            if reg == 0 and fb[4] != far + nwords // FRAME:
                bad(f"record {i}: the address register reads {fb[4]:#010x} after {describe(m)} at {far:#010x}; one step for every 101 words read gives {far + nwords // FRAME:#010x}")
            if reg == 1 and fb[4] & 0x0FFFFFFF != IDCODE_LOW28:
                bad(f"record {i}: IDCODE reads {fb[4]:#010x}; its low 28 bits are not {IDCODE_LOW28:#09x}")
        digests = []
        for j, frame in enumerate(rec["frames"]):
            digests.append(hashlib.sha256(b"".join(struct.pack(">I", w) for w in frame)).hexdigest())
            if code == 0 and stage == 6:
                if far + j not in frames_known:
                    bad(f"record {i}: no known answer for FAR {far + j:#010x}")
                elif frame != frames_known[far + j]:
                    diff = [k for k in range(FRAME) if frame[k] != frames_known[far + j][k]]
                    bad(f"record {i}: frame {j} (FAR {far + j:#010x}) read cleanly but differs from the known frame in {len(diff)} word(s), first at {diff[0]}")
        out["records"].append({"index": i, "far": f"{far:#010x}", "frames": delivered, "words": nwords, "kind": KIND.get(kind, kind), "op": None if op == NO_OP else op,
                               "register": REGS[reg], "code": f"{code:#x}", "repeat": r[12], "value_read": f"{fb[4]:#010x}",
                               "int_sts": [f"{x:08x}" for x in (r[3], r[5], fb[0], fb[2], r[7])], "polls": [r[4], r[6], fb[1], fb[3], r[8]],
                               "survivors": survivors, "pad_all_zero": (not any(data[:FRAME])) if nwords else None, "frame_sha256": digests})

    # ---- stage 7: the log of accesses to the design, walked against the sequence the prober is to make
    pl_implied = 0
    if stage == 7:
        steps = pl_schedule(par[26])
        log_due = not failing and n >= 1 and recs[0]["code"] == 0     # user logic comes after the reference frame's first reading
        if not log_due and (log or plb[2] or plb[3] != 0xFFFFFFFF):
            bad("the PL block shows an access to the design in a run that never came to it")
        ended = None
        for i, (word, value) in enumerate(log):
            addr, write = word & ~3, bool(word & 1)
            off = addr - PL_BASE
            if word & 2 or not par[24] <= addr <= par[25] or not 0 <= off < PL_SPAN or (write and off not in PL_WRITABLE):
                bad(f"PL access {i}: {'write to' if write else 'read of'} {addr:#010x} is outside what the prober may touch")
            if ended is not None:
                continue
            if i >= len(steps):
                bad(f"PL access {i}: the sequence has only {len(steps)} accesses"); ended = i; continue
            st = steps[i]
            if (off, write) != (st["off"], st["write"]):
                bad(f"PL access {i}: {'a write to' if write else 'a read of'} offset {off:#x}, where {'a write to' if st['write'] else 'a read of'} offset {st['off']:#x} is due")
                ended = i; continue
            if write:
                if value != st["value"]:
                    bad(f"PL access {i}: {value:#010x} written to offset {off:#x}, where {st['value']:#010x} is due"); ended = i
                continue
            wrong = ("value" in st and value != st["value"]) or ("same_as" in st and value != log[st["same_as"]][1]) \
                or ("differs_from" in st and value == log[st["differs_from"]][1])
            if wrong:
                pl_implied = st["code"]; ended = i
                if len(log) != i + 1:
                    bad(f"PL access {i} is an answer the design must not give ({PL_CODES[st['code']]}), yet {len(log) - i - 1} access(es) follow it")
        if log_due and ended is None and len(log) < len(steps):
            nxt = steps[len(log)]
            if not par[24] <= PL_BASE + nxt["off"] <= par[25]:
                pl_implied = 1                           # the next access lies outside the envelope the host gave: the helper refuses it
            else:
                bad(f"the log of PL accesses ends after {len(log)} of {len(steps)}, with nothing in it that ends the sequence")
        if log_due:
            if plb[2] != pl_implied:
                bad(f"the PL block's code is {plb[2]:#x} ({PL_CODES.get(plb[2], 'unknown')}); its log implies {pl_implied:#x} ({PL_CODES[pl_implied]})")
            if plb[3] != (len(log) if plb[2] else 0xFFFFFFFF):
                bad(f"the PL block says it stopped at access {plb[3]:#x}; with {len(log)} accesses and code {plb[2]:#x} that is not so")
        # what the design said of itself, for the record — from the log, and only as far as it goes
        pl: dict = {"accesses": len(log), "code": f"{plb[2]:#x}", "says": PL_CODES.get(plb[2], "unknown")}
        reads = [(i, st) for i, st in enumerate(steps[:len(log)]) if not st["write"]]
        by_off: dict[int, list[int]] = {}
        for i, st in reads:
            by_off.setdefault(st["off"], []).append(log[i][1])
        if by_off.get(PL_ID):
            pl["id"] = f"{by_off[PL_ID][0]:#010x}"
        if len(by_off.get(PL_COUNT, [])) == 2:
            pl["counter"] = [f"{v:#010x}" for v in by_off[PL_COUNT]]
        pl["ram_states_read_back"] = len(by_off.get(PL_RAM_DATA, [])) // RAM_DEPTH if pl_implied != 5 else (len(by_off.get(PL_RAM_DATA, [])) - 1) // RAM_DEPTH
        srl = by_off.get(PL_SRL_DATA, [])
        if len(srl) >= SRL_DEPTH:
            held = [sum((srl[a] >> k & 1) << a for a in range(SRL_DEPTH)) for k in range(4)]
            pl["shift_registers_hold"] = [f"{w:#010x}" for w in held]
            if any(v >> 4 for v in srl[:SRL_DEPTH]):
                bad("a read of the shift registers' outputs has bits set above the four there are")
            loaded = [int(known["srl"]["cells"][str(k)]["init"], 16) for k in range(4)] if known and "srl" in known else None
            if loaded is None:
                bad("the words the design loads into its shift registers were not given: what they read as cannot be held to anything")
            elif held != loaded:
                bad("the shift registers do not hold what the design's source loads into them: read "
                    + ", ".join(f"{w:#010x}" for w in held) + "; loaded " + ", ".join(f"{w:#010x}" for w in loaded))
        if by_off.get(PL_WRITES):
            pl["writes_counted"] = {"ram": by_off[PL_WRITES][0] & 0xFFFF, "shifts": by_off[PL_WRITES][0] >> 16}
        out["pl"] = pl

    # ---- the schedule: which record must be which, and what that implies for the header
    def healthy(rec: dict) -> bool:
        return rec["code"] == 0 and rec["frames"][:1] == recs[0]["frames"][:1] and rec["value"] == recs[0]["value"]

    def stop_of(rec: dict) -> int:
        return 0x200 | rec["code"] if rec["code"] >= 0x20 else 0x300

    def expect(i: int, kind: int, far: int, m: int, repeat: int, op: int) -> dict | None:
        if i >= n:
            bad(f"the records end at {n}; a {KIND[kind]} read of {far:#010x} x{m} (repeat {repeat}) is missing")
            return None
        rec = recs[i]
        if (rec["kind"], rec["far"], rec["n"], rec["repeat"], rec["op"]) != (kind, far, m, repeat, op):
            bad(f"record {i}: expected the {KIND[kind]} read of {far:#010x} x{m} (repeat {repeat}), found a "
                f"{KIND.get(rec['kind'], rec['kind'])} read of {rec['far']:#010x} x{rec['n']} (repeat {rec['repeat']}, operation {rec['op']:#x})")
        return rec

    implied: tuple[int, int, int] | None = None
    i = count = 0
    rec = expect(0, 2, ref, 1, 0, NO_OP)
    if rec is None:
        implied = (-1, 0, 0)
    elif rec["code"] != 0:
        implied = (0x600 | rec["code"], 0, 0); i = 1
    elif stage == 7 and pl_implied:
        implied = (0xA00 | pl_implied, 0, 0xFFFFFFFF); i = 1          # user logic did not answer as it must: nothing follows
    else:
        i = 1
        for rep in range(repeats):
            for k, (far, m, _) in enumerate(ops):
                rec = expect(i, 0, far, m, rep, k)
                if rec is None:
                    implied = (-1, count, 0); break
                i += 1
                if rec["code"] == 0:
                    continue
                count += 1
                if rec["code"] >= 0x20:
                    implied = (0x200 | rec["code"], count, i - 1); break
                h = expect(i, 1, ref, 1, rep, NO_OP)
                if h is None:
                    implied = (-1, count, 0); break
                i += 1
                if h["ref_equal"] != (1 if healthy(h) else 0):
                    bad(f"record {h['i']}: the health flag is {h['ref_equal']:#x}, the data say {int(healthy(h))}")
                if not healthy(h):
                    implied = (stop_of(h), count, i - 1); break
                if count > budget:
                    implied = (0x400, count, i - 2); break
            if implied:
                break
        if not implied:
            f = expect(i, 3, ref, 1, repeats, NO_OP)
            if f is None:
                implied = (-1, count, 0)
            else:
                i += 1
                if f["ref_equal"] != (1 if healthy(f) else 0):
                    bad(f"record {f['i']}: the final reference flag is {f['ref_equal']:#x}, the data say {int(healthy(f))}")
                implied = (1, count, 0xFFFFFFFF) if healthy(f) else (stop_of(f), count, i - 1)
    if i != n:
        bad(f"{n - i} record(s) after the point where the schedule ends (record {i})")
    if implied[0] >= 0:
        if status != implied[0]:
            bad(f"the header's status is {status:#x}; the records imply {implied[0]:#x}")
        if anomalies != implied[1]:
            bad(f"the header counts {anomalies} anomalies; the records show {implied[1]}")
        if stop_record != implied[2]:
            bad(f"the header's stop record is {stop_record:#x}; the records imply {implied[2]:#x}")
    for rec in recs:
        if rec["kind"] not in (1, 3) and rec["ref_equal"] != 0xFFFFFFFF:
            bad(f"record {rec['i']}: a health flag on a {KIND.get(rec['kind'], rec['kind'])} read")

    # ---- the finding: what each register read as. Required: the same every time. Reported: what CTL0 holds.
    registers: dict = {}
    wanted = {0} | {reg for _, _, reg in ops}
    for reg in sorted(wanted):
        values = seen.get(reg, {})
        clean = sorted({recs[k]["value"] for v, where in values.items() for k in where if recs[k]["code"] == 0})
        entry: dict = {"values": {f"{v:#010x}": where for v, where in sorted(values.items())},
                       "read_cleanly": bool(clean)}
        if reg != 0 and len(values) > 1:
            bad(f"{REGS[reg]} does not read the same every time: " + ", ".join(f"{v:#010x} in record(s) {where}" for v, where in sorted(values.items())))
        if reg != 0 and len(values) == 1:
            entry["value"] = f"{next(iter(values)):#010x}"
        if reg == 1 and len(values) == 1:
            entry["low_28_bits_as_known"] = next(iter(values)) & 0x0FFFFFFF == IDCODE_LOW28
        if reg == 2 and len(values) == 1:
            v = next(iter(values))
            entry["bits_set"] = [f"{b} {CTL0_BITS.get(b, 'not in table 5-27')}" for b in range(31, -1, -1) if v >> b & 1]
            entry["bits_set_the_table_does_not_name"] = [b for b in range(32) if v >> b & 1 and b not in CTL0_BITS]
            entry["GLUTMASK_B"] = v >> 8 & 1
            entry["by_the_register_s_word"] = ("readback of LUT RAM and shift registers is not masked (bit 8 set)" if v >> 8 & 1
                                               else "readback of LUT RAM and shift registers is masked (bit 8 clear, the table's default)")
        if reg == 4 and len(values) == 1:
            v = next(iter(values))
            entry["fields"] = {name: v >> low & (1 << width) - 1 for name, low, width in COR0_FIELDS}
            named = sum(((1 << width) - 1) << low for _, low, width in COR0_FIELDS)
            entry["bits_set_the_table_does_not_name"] = [b for b in range(32) if v >> b & 1 and not named >> b & 1]
            entry["SINGLE"] = v >> 23 & 1
            entry["start_up_clock"] = SSCLKSRC[v >> 15 & 3]
            entry["by_the_register_s_word"] = ("readback is single-shot: RCAP must be sent between successive captures (bit 23 set)" if v >> 23 & 1
                                               else "readback is not single-shot: each capture loads new values (bit 23 clear)")
        registers[REGS[reg]] = entry
    out["registers"] = registers
    out["registers_without_a_clean_value"] = [REGS[reg] for reg in sorted(wanted) if not registers[REGS[reg]]["read_cleanly"]]

    if status != 1:
        bad(f"the run did not complete: status {status:#x}" + (f" ({PL_CODES[status & 0xFF]})" if status & 0xF00 == 0xA00 and status & 0xFF in PL_CODES else ""))
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def load(path: Path) -> list[int] | None:
    raw = path.read_bytes()
    if len(raw) % 4:
        return None
    return list(struct.unpack("<%dI" % (len(raw) // 4), raw))

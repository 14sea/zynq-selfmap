#!/usr/bin/env python3
"""Judge a result of stage 8 (S2.2) on the host — docs/s2_plan.md, section 19.

    s2_2_judge.py <result.bin> <share>        judge the result of the run of that share; prints the verdict as JSON

The run: for each of three states of the probe design's RAM — all zero, all one, all zero — the RAM is set through
the design's registers, a list of reads is made through PCAP, and the RAM is read through the design again. The
question: is the RAM seen in what is read back, where, and does reading disturb it.

The same principles as every judge here. Nothing the board reports is taken on trust: codes, order, status and counts
are derived again from the raw words; the parameters the prober echoed must be the planned ones; the gate readings
are judged; the log of accesses to the design is walked against the sequence the prober is to make. And then:

  * The list. What the prober read must be the list the host wrote, read by read, in every state; and that list must
    be one made from the census: every address in it one the device named in block type 0, every read in one column.
  * The address register after every read is what the census has: one place on for every 101 words read.
  * The status after every read is recorded and held to what a transfer's status is held to. After a read of the
    list, where bit 5 (PCFG_SEU_ERR) shows and nothing is amiss, the prober clears that bit and no other, and
    records what the register reads then; where it does not show, nothing is cleared.
  * CTL0 is read before the first state and after the last: the run's own record of the readback mask.
  * The finding. Every bit of every frame read has one reading in each state. Alike in all: *still*. As the state
    was: a *candidate* — it follows the RAM. The opposite of the state every time: a candidate, inverted. Anything
    else — and with the states 0, 1, 0 that means a bit that reads differently in the two all-zero states — is
    *restless*, and fails the run. The candidates are listed, each as an address, a word and a bit.

How many candidates there must be is not asked here: one run reads a share of the addresses. The program that closes
the step (s2_2_closed.py) counts them over all runs.
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
import s2_2_shares  # noqa: E402
from s1a_judge import CLEANUP, CTRL_MASK, ERR_MASK, KIND, MCTRL_LPBK, PCFG_DONE, SCTLR_C, SENTINEL, _command_outcome, return_code  # noqa: E402,F401
from s1b0_judge import DATA, DATA_WORDS, FARBLK, FRAME, MAX_READ_FRAMES, NO_OP, NONE, NOOP, POLLING, REC, describe, frames_stream, read_words  # noqa: E402
from s2_judge import (CTL0_BITS, GATE_STATUS, PL_BASE, PL_COUNT, PL_ID, PL_RAM_ADDR, PL_RAM_DATA, PL_SPAN, PL_SRL_ADDR,  # noqa: E402
                      PL_SRL_DATA, PL_WRITABLE, PL_WRITES, PLB_MAGIC, RAM_DEPTH, READ_HEADER, SEU_EN, SLCR_NAMES, SRL_DEPTH, ram_pattern)
from s2_judge import PL_CODES as PL_CODES_S2_1  # noqa: E402

STAGE = 8
HDR0 = 64
PL_LOG_MAX = 1440
PLB_WORDS = 16 + 2 * PL_LOG_MAX
HDR = HDR0 + PLB_WORDS                                # where the records begin: what the run script knows a layout by
LIST_MAX, MAX_STATES = s2_2_shares.LIST_MAX, 3
MAX_RECORDS = 4 + MAX_STATES * LIST_MAX
OP_CTL0 = 0x100
P_USED = 0xF70382BF                                   # the words of the parameter block the stage has a use for
SEU_ERR = 0x00000020
STATE_NAMES = {0: "all zero", 1: "all one"}
PL_CODES = {**PL_CODES_S2_1, 9: "the RAM did not hold its state after the frames were read"}
REG_FAR, REG_CTL0 = 0, 2
REG_NAME = {REG_FAR: "FAR", REG_CTL0: "CTL0"}


def pl_schedule(pl_id: int, states: list[int]) -> tuple[list[dict], list[tuple[int, int]]]:
    """Every access the prober is to make to the design, in order, and where the stretches of it end: the first
    stretch comes before anything of the list is read; then, for each state, one stretch before its reads and one
    after them. A step is as in s2_judge.pl_schedule."""
    s: list[dict] = []
    cuts: list[tuple[int, int]] = []
    w = lambda off, v: s.append({"off": off, "write": True, "value": v})  # noqa: E731
    r = lambda off, **kw: s.append({"off": off, "write": False, **kw})  # noqa: E731
    r(PL_ID, code=2, value=pl_id)
    srl0 = len(s)
    for a in range(SRL_DEPTH):
        w(PL_SRL_ADDR, a); r(PL_SRL_DATA)
    cuts.append((0, len(s)))
    for k, state in enumerate(states):
        begin = len(s)
        for a in range(RAM_DEPTH):
            w(PL_RAM_ADDR, a); w(PL_RAM_DATA, ram_pattern(state, a))
        for a in range(RAM_DEPTH):
            w(PL_RAM_ADDR, a); r(PL_RAM_DATA, code=5, value=ram_pattern(state, a))
        r(PL_COUNT)
        count = len(s) - 1
        cuts.append((begin, len(s)))
        begin = len(s)
        for a in range(RAM_DEPTH):
            w(PL_RAM_ADDR, a); r(PL_RAM_DATA, code=9, value=ram_pattern(state, a))
        r(PL_COUNT, code=4, differs_from=count)
        for a in range(SRL_DEPTH):
            w(PL_SRL_ADDR, a); r(PL_SRL_DATA, code=6, same_as=srl0 + 2 * a + 1)
        r(PL_WRITES, code=7, value=(k + 1) * RAM_DEPTH)
        cuts.append((begin, len(s)))
    return s, cuts


def idle_status(sts: int) -> int:
    """The code a status word read between transfers implies, as the prober's `s8_sts` has it: an error bit is a
    device error, a lost PCFG_DONE is that; 0 where neither."""
    return 0x21 if sts & ERR_MASK else 0x23 if not sts & PCFG_DONE else 0


def console_line(status: int, records: int, anomalies: int) -> str:
    if status == 0x500:
        return "SM%d end status=%08x" % (STAGE, status)
    return "SM%d end status=%08x records=%08x anomalies=%08x words=%08x" % (STAGE, status, records, anomalies, HDR + records * REC)


def params_valid(par: list[int]) -> bool:
    lo, hi, ref, n_states, limit, n_list = par[3], par[4], par[5], par[7], par[9], par[16]
    if (par[0], par[1], par[2]) != (0x31504D53, 1, STAGE) or lo > hi or not lo <= ref <= hi:
        return False
    if not 1 <= n_states <= MAX_STATES or not 1 <= n_list <= LIST_MAX or not 0 < limit <= 0x10000000:
        return False
    if any(par[k] for k in range(32) if not P_USED >> k & 1) or par[15] & 0xFF or par[15] >> 8 not in POLLING:
        return False
    if par[17] >> (4 * n_states) or any((par[17] >> (4 * s)) & 0xF > 1 for s in range(MAX_STATES)):
        return False
    return PL_BASE <= par[24] <= par[25] < PL_BASE + PL_SPAN


def judge(words: list[int], known: dict | None, planned: list[int]) -> dict:
    """`planned`: the 32 words of the parameter block, and after them the words of the list the host wrote.
    `known`: the facts of the probe design (pl/s2a/design.json) and, under "census", the census."""
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append
    planned_par, planned_list = list(planned[:32]), list(planned[32:])

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
    out["expected_console"] = [f"SM{STAGE} start", console_line(status, n, anomalies)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if (rec_words, hdr_words) != (REC, HDR) or n > MAX_RECORDS or total != HDR + n * REC:
        return invalid(f"sizes do not add up for a stage-{STAGE} result: total {total}, records {n}, record size {rec_words}, header {hdr_words}")
    if status == 0x500 and n:
        return invalid("a parameter refusal with records")
    if len(words) != total:
        return invalid(f"the buffer has {len(words)} words, the header says {total}")
    if any(words[19:32]):
        bad("reserved header words are not zero")

    par = words[32:64]
    lo, hi, ref, n_states, poll_limit, n_list = par[3], par[4], par[5], par[7], par[9], par[16]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "states": n_states,
                     "reads_in_the_list": n_list, "poll_limit": poll_limit}
    if list(par) != planned_par:
        differ = [k for k in range(32) if k >= len(planned_par) or par[k] != planned_par[k]]
        bad(f"the parameters the prober echoed are not the planned ones (word(s) {differ}): the run did not do what was asked")

    # ---- the PL block's own form, before anything is read out of it
    plb = words[HDR0:HDR]
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
        if plb[1] or plb[2] or any(plb[4:8]) or plb[3] != 0xFFFFFFFF:
            bad("a parameter refusal, yet the PL block is not empty")
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    if not params_valid(par):
        return invalid(f"the echoed parameters are not a valid stage-{STAGE} parameter block")
    states = [(par[17] >> (4 * s)) & 0xF for s in range(n_states)]
    out["params"]["states"] = [STATE_NAMES[s] for s in states]
    out["params"]["polling_loop"] = POLLING[par[15] >> 8]
    out["params"]["pl_envelope"] = [f"{par[24]:#010x}", f"{par[25]:#010x}"]

    # ---- the list: the one the host wrote, and one made from the census
    if len(planned_list) != n_list:
        return invalid(f"the parameter block names {n_list} reads; the list the host planned has {len(planned_list)}")
    reads = [(w & 0x0FFFFFFF, w >> 28) for w in planned_list]
    lay = s2_2_shares.layout(known["census"]) if known and "census" in known else None
    if lay is None:
        bad("the census was not given: the list and the address register cannot be held to anything")
    else:
        for p in s2_2_shares.list_problems(lay, reads):
            bad(f"the list is not one made from the census: {p}")
    for k, (far, m) in enumerate(reads):
        if not 1 <= m <= MAX_READ_FRAMES or far < lo or far + m - 1 > hi:
            bad(f"read {k} of the list ({far:#010x} x{m}) is not one the prober may make in this envelope")
    out["list"] = {"reads": n_list, "frames": sum(m for _, m in reads), "first": f"{reads[0][0]:#010x}",
                   "last": f"{reads[-1][0] + reads[-1][1] - 1:#010x}"}

    # ---- the gates
    ctrl, mctrl, sts0, sctlr, sts1 = words[8], words[9], words[10], words[12], words[16]
    failing = (0x101 if (ctrl & CTRL_MASK) != CTRL_MASK else 0x105 if ctrl & SEU_EN else 0x102 if mctrl & MCTRL_LPBK
               else 0x103 if not sts0 & PCFG_DONE else 0x104 if sctlr & SCTLR_C else 0)
    out["slcr"] = {name: {"read": f"{plb[4 + k]:08x}", "wanted": f"{par[28 + k]:08x}"} for k, name in enumerate(SLCR_NAMES)}
    if not failing:                                      # the four SLCR words are read only once the gates before them hold
        failing = next((0x110 | k for k in range(4) if plb[4 + k] != par[28 + k]), 0)
    elif any(plb[4:8]):
        bad("SLCR words are recorded although a gate before them fails")
    if status in GATE_STATUS:
        if n:
            bad("a gate stop with records")
        if plb[1] or plb[2] or plb[3] != 0xFFFFFFFF:
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
    recs: list[dict] = []
    ctl0_seen: dict[int, list[int]] = {}
    bit5: dict = {"shown_after_records": [], "cleared_after_records": [], "still_set_after_clearing": []}
    for i in range(n):
        r = words[HDR + i * REC: HDR + (i + 1) * REC]
        fb = r[FARBLK:FARBLK + 8]
        far, kind, code, m, op = r[0], r[1], r[2], r[14], r[15]
        of_list = kind == 0 and op != OP_CTL0
        reg = REG_CTL0 if kind == 0 and op == OP_CTL0 else REG_FAR
        rec = {"i": i, "far": far, "kind": kind, "code": code, "n": m, "op": op, "repeat": r[12], "ref_equal": r[10],
               "value": fb[4], "frames": []}
        recs.append(rec)
        if not (m == NONE or 1 <= m <= MAX_READ_FRAMES):
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
        for name, got, want in (("frame read stream", r[16:59], frames_stream(far, m)),
                                (f"{REG_NAME[reg]} read stream", r[59:63], [NOOP, READ_HEADER[reg], NOOP, NOOP]),
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
            # Stage 8 clears the two done bits when a transfer begins and never an error bit (reviews of 9fa606e and
            # 334df53). An error bit in the word of a transfer that was never queued therefore stood in the register
            # before the transfer was to begin: code 0x24. Without one, bits of the clear mask that are still set are
            # done bits that would not clear: 0x20, as in every stage.
            if derived == 0x20 and sts & ERR_MASK:
                derived = 0x24
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
            derived = 0x10 if survivors else 0x11 if any(data[:FRAME]) else 0x14 if unread else 0
        # The status after the read, and what was done about bit 5. The register is read after every read of the stage
        # — of the list, of CTL0, of the reference frame — and, after a read of the list, once more where bit 5 was
        # cleared. Both words are read when no transfer is running and are held to what a transfer's own status is
        # held to: an error bit or a lost PCFG_DONE in either is a failure of the interface, and the read's code must
        # say so (reviews of 0417966 and 334df53). Bit 5 is cleared only after a read of the list with nothing amiss:
        # after anything else the prober writes nothing more.
        after = fb[7]
        cleared = r[10] if of_list else 0xFFFFFFFF       # in the other reads that word is the reference frame's flag
        own = derived                                    # what the read's own transfers and data say
        if cleared != 0xFFFFFFFF:
            if not after & SEU_ERR:
                bad(f"record {i}: a clearing of bit 5 is recorded ({cleared:08x}) although the status after the read ({after:08x}) does not show it")
            elif own or idle_status(after):
                bad(f"record {i}: bit 5 was cleared ({cleared:08x}) after a read that was not clean (status after it {after:08x})")
        derived = own or idle_status(after) or (idle_status(cleared) if cleared != 0xFFFFFFFF else 0)
        # the prober also looks at PCFG_DONE in one status read that it does not record, between the last transfer and
        # the status after the read; a code of 0x23 that nothing recorded shows cannot be refuted. It writes nothing then
        if code != derived and not (code == 0x23 and own in (0, 0x10, 0x11, 0x14) and cleared == 0xFFFFFFFF):
            bad(f"record {i}: code {code:#x}, but its raw words say {derived:#x}")
        rec["measured"] = done and not unread
        if rec["measured"] and reg == REG_CTL0:
            ctl0_seen.setdefault(fb[4], []).append(i)
        if rec["measured"] and reg == REG_FAR and lay is not None:
            want_far = s2_2_shares.register_after(lay, far, nwords // FRAME - 1)
            if want_far is None:
                bad(f"record {i}: the census does not say what the address register reads after {describe(m)} at {far:#010x}")
            elif fb[4] != want_far:
                bad(f"record {i}: the address register reads {fb[4]:#010x} after {describe(m)} at {far:#010x}; by the census it is {want_far:#010x}")
        if after & SEU_ERR:
            bit5["shown_after_records"].append(i)
            if cleared != 0xFFFFFFFF:
                bit5["cleared_after_records"].append(i)
                if cleared & SEU_ERR:
                    bit5["still_set_after_clearing"].append(i)
            elif code == 0 and of_list:                  # after the other reads the bit is recorded and left: the next read of the list meets it
                bad(f"record {i}: bit 5 shows in the status after the read ({after:08x}), and nothing is recorded of its clearing")
        digests = [hashlib.sha256(b"".join(struct.pack(">I", w) for w in frame)).hexdigest() for frame in rec["frames"]]
        entry = {"index": i, "far": f"{far:#010x}", "frames": delivered, "words": nwords, "kind": KIND.get(kind, kind),
                 "op": None if op == NO_OP else "CTL0" if op == OP_CTL0 else op, "register": REG_NAME[reg], "code": f"{code:#x}",
                 "state": r[12], "value_read": f"{fb[4]:#010x}",
                 "int_sts": [f"{x:08x}" for x in (r[3], r[5], fb[0], fb[2], r[7])], "polls": [r[4], r[6], fb[1], fb[3], r[8]],
                 "survivors": survivors, "pad_all_zero": (not any(data[:FRAME])) if nwords else None, "frame_sha256": digests}
        entry["int_sts_after"] = f"{after:08x}"
        if cleared != 0xFFFFFFFF:
            entry["int_sts_after_clearing_bit_5"] = f"{cleared:08x}"
        out["records"].append(entry)
    out["bit_5"] = bit5

    # ---- the log of accesses to the design, walked against the sequence the prober is to make
    steps, cuts = pl_schedule(par[26], states)
    for i, (word, value) in enumerate(log):
        addr, write = word & ~3, bool(word & 1)
        off = addr - PL_BASE
        if word & 2 or not par[24] <= addr <= par[25] or not 0 <= off < PL_SPAN or (write and off not in PL_WRITABLE):
            bad(f"PL access {i}: {'write to' if write else 'read of'} {addr:#010x} is outside what the prober may touch")
    walked = {"at": 0, "over": False}                  # how far the log has been walked; whether the sequence has ended

    def stretch(which: int) -> int:
        """Walk the log through one stretch of the sequence. Returns the code the design's answers imply: 0 if every
        access of the stretch was made and answered as it must be."""
        begin, end = cuts[which]
        for at in range(begin, end):
            st = steps[at]
            if at >= len(log):
                walked["over"] = True
                if not par[24] <= PL_BASE + st["off"] <= par[25]:
                    return 1                             # the next access lies outside the envelope the host gave: the helper refuses it
                if len(log) == PL_LOG_MAX:
                    return 8
                bad(f"the log of PL accesses ends after {len(log)}, where access {at} of the sequence is due, with nothing in it that ends the sequence")
                return -1
            word, value = log[at]
            off, write = (word & ~3) - PL_BASE, bool(word & 1)
            walked["at"] = at + 1
            if (off, write) != (st["off"], st["write"]):
                bad(f"PL access {at}: {'a write to' if write else 'a read of'} offset {off:#x}, where {'a write to' if st['write'] else 'a read of'} offset {st['off']:#x} is due")
                walked["over"] = True; return -1
            if write:
                if value != st["value"]:
                    bad(f"PL access {at}: {value:#010x} written to offset {off:#x}, where {st['value']:#010x} is due")
                    walked["over"] = True; return -1
                continue
            wrong = ("value" in st and value != st["value"]) or ("same_as" in st and value != log[st["same_as"]][1]) \
                or ("differs_from" in st and value == log[st["differs_from"]][1])
            if wrong:
                walked["over"] = True
                return st["code"]
        return 0

    # ---- the schedule: which record must be which, what the design must have been asked in between, and what that
    #      implies for the header
    def healthy(rec: dict) -> bool:
        return rec["code"] == 0 and rec["frames"][:1] == recs[0]["frames"][:1] and rec["value"] == recs[0]["value"]

    def expect(i: int, kind: int, far: int, m: int, repeat: int, op: int) -> dict | None:
        if i >= n:
            bad(f"the records end at {n}; a {KIND[kind]} read of {far:#010x} x{m} (state {repeat}) is missing")
            return None
        rec = recs[i]
        if (rec["kind"], rec["far"], rec["n"], rec["repeat"], rec["op"]) != (kind, far, m, repeat, op):
            bad(f"record {i}: expected the {KIND[kind]} read of {far:#010x} x{m} (state {repeat}, operation {op:#x}), found a "
                f"{KIND.get(rec['kind'], rec['kind'])} read of {rec['far']:#010x} x{rec['n']} (state {rec['repeat']}, operation {rec['op']:#x})")
        return rec

    def read_stop(rec: dict, at: int) -> tuple[int, int, int]:
        return (0x200 | rec["code"] if rec["code"] >= 0x20 else 0x400, 1, at)

    implied: tuple[int, int, int] | None = None          # status, anomalies, stop record; a status of -1: the records ran out
    pl_implied = 0
    passes_made = 0
    log_due = False
    i = 0
    rec = expect(0, 2, ref, 1, 0, NO_OP)
    if rec is None:
        implied = (-1, 0, 0)
    elif rec["code"] != 0:
        implied = (0x600 | rec["code"], 0, 0); i = 1
    else:
        i = 1
        log_due = not failing
        todo: list = [("pl", 0), ("read", ref, NONE, 0, OP_CTL0)]
        for s in range(n_states):
            todo.append(("pl", 1 + 2 * s))
            todo += [("read", far, m, s, k) for k, (far, m) in enumerate(reads)]
            todo += [("pl", 2 + 2 * s), ("pass", s)]
        todo.append(("read", ref, NONE, n_states, OP_CTL0))
        for item in todo:
            if item[0] == "pl":
                pl_implied = stretch(item[1])
                if pl_implied > 0:
                    implied = (0xA00 | pl_implied, 0, 0xFFFFFFFF); break
                if pl_implied < 0:
                    pl_implied = 0; implied = (-2, 0, 0); break       # the log is not the sequence: said above, nothing more can be derived
            elif item[0] == "pass":
                passes_made = item[1] + 1
            else:
                rec = expect(i, 0, *item[1:])
                if rec is None:
                    implied = (-1, 0, 0); break
                i += 1
                if rec["code"] != 0:
                    implied = read_stop(rec, i - 1); break
        if not implied:
            f = expect(i, 3, ref, 1, n_states, NO_OP)
            if f is None:
                implied = (-1, 0, 0)
            else:
                i += 1
                if f["ref_equal"] != (1 if healthy(f) else 0):
                    bad(f"record {f['i']}: the final reference flag is {f['ref_equal']:#x}, the data say {int(healthy(f))}")
                implied = (1, 0, 0xFFFFFFFF) if healthy(f) else (0x200 | f["code"] if f["code"] >= 0x20 else 0x300, 0, i - 1)
    if i != n:
        bad(f"{n - i} record(s) after the point where the schedule ends (record {i})")
    if implied[0] >= 0:
        if status != implied[0]:
            bad(f"the header's status is {status:#x}; the records and the log imply {implied[0]:#x}")
        if anomalies != implied[1]:
            bad(f"the header counts {anomalies} anomalies; the records show {implied[1]}")
        if stop_record != implied[2]:
            bad(f"the header's stop record is {stop_record:#x}; the records imply {implied[2]:#x}")
    for rec in recs:
        if rec["kind"] == 3 or (rec["kind"] == 0 and rec["op"] != OP_CTL0):
            continue                                     # the final reference read has its flag; a read of the list has the status after the clearing there
        if rec["ref_equal"] != 0xFFFFFFFF:
            bad(f"record {rec['i']}: a health flag on a {KIND.get(rec['kind'], rec['kind'])} read")
    if not log_due and (log or plb[2] or plb[3] != 0xFFFFFFFF):
        bad("the PL block shows an access to the design in a run that never came to it")
    if log_due:
        if walked["at"] != len(log):
            bad(f"{len(log) - walked['at']} access(es) to the design after the point where the sequence ends (access {walked['at']})")
        if plb[2] != pl_implied:
            bad(f"the PL block's code is {plb[2]:#x} ({PL_CODES.get(plb[2], 'unknown')}); its log implies {pl_implied:#x} ({PL_CODES[pl_implied]})")
        if plb[3] != (len(log) if plb[2] else 0xFFFFFFFF):
            bad(f"the PL block says it stopped at access {plb[3]:#x}; with {len(log)} accesses and code {plb[2]:#x} that is not so")

    # ---- what the design said of itself, for the record — from the log, and only as far as it goes
    pl: dict = {"accesses": len(log), "code": f"{plb[2]:#x}", "says": PL_CODES.get(plb[2], "unknown"), "passes_the_ram_held_through": passes_made}
    answered = [(k, steps[k]) for k in range(min(walked["at"], len(steps))) if not steps[k]["write"]]
    if answered and answered[0][1]["off"] == PL_ID:
        pl["id"] = f"{log[answered[0][0]][1]:#010x}"
    pl["counter"] = [f"{log[k][1]:#010x}" for k, st in answered if st["off"] == PL_COUNT]
    srl = [log[k][1] for k, st in answered if st["off"] == PL_SRL_DATA][:SRL_DEPTH]
    if len(srl) == SRL_DEPTH:
        held = [sum((srl[a] >> k & 1) << a for a in range(SRL_DEPTH)) for k in range(4)]
        pl["shift_registers_hold"] = [f"{w:#010x}" for w in held]
        if any(v >> 4 for v in srl):
            bad("a read of the shift registers' outputs has bits set above the four there are")
        loaded = [int(known["srl"]["cells"][str(k)]["init"], 16) for k in range(4)] if known and "srl" in known else None
        if loaded is None:
            bad("the words the design loads into its shift registers were not given: what they read as cannot be held to anything")
        elif held != loaded:
            bad("the shift registers do not hold what the design's source loads into them: read "
                + ", ".join(f"{w:#010x}" for w in held) + "; loaded " + ", ".join(f"{w:#010x}" for w in loaded))
    counted = [log[k][1] for k, st in answered if st["off"] == PL_WRITES]
    if counted:
        pl["writes_counted"] = {"ram": counted[-1] & 0xFFFF, "shifts": counted[-1] >> 16}
    out["pl"] = pl

    # ---- CTL0: the same before and after, and what it says of the mask
    ctl0: dict = {"values": {f"{v:#010x}": where for v, where in sorted(ctl0_seen.items())}}
    if len(ctl0_seen) > 1:
        bad("CTL0 does not read the same before and after: " + ", ".join(f"{v:#010x} in record(s) {where}" for v, where in sorted(ctl0_seen.items())))
    if len(ctl0_seen) == 1:
        v = next(iter(ctl0_seen))
        ctl0["value"] = f"{v:#010x}"
        ctl0["bits_set"] = [f"{b} {CTL0_BITS.get(b, 'not in table 5-27')}" for b in range(31, -1, -1) if v >> b & 1]
        ctl0["GLUTMASK_B"] = v >> 8 & 1
        ctl0["by_the_register_s_word"] = ("readback of LUT RAM and shift registers is not masked (bit 8 set)" if v >> 8 & 1
                                          else "readback of LUT RAM and shift registers is masked (bit 8 clear, the table's default)")
    out["registers"] = {"CTL0": ctl0}

    # ---- the finding: every bit of every frame read, by its readings in the states
    finding: dict = {"states_read_whole": passes_made, "frames": 0, "bits": {"still": 0, "candidates": 0, "candidates_inverted": 0, "restless": 0},
                     "candidates": [], "restless": []}
    if status == 1 and passes_made == n_states and len(recs) == 4 + n_states * n_list and all(r["code"] == 0 for r in recs):
        readings: dict[int, list[list[int]]] = {}        # address -> one frame for each state
        for s in range(n_states):
            for k, (far, m) in enumerate(reads):
                rec = recs[2 + s * n_list + k]
                for j, frame in enumerate(rec["frames"]):
                    readings.setdefault(far + j, []).append(frame)
        full = 0xFFFFFFFF
        for far in sorted(readings):
            frames = readings[far]
            if len(frames) != n_states:
                bad(f"{far:#010x} has {len(frames)} reading(s) for {n_states} state(s)"); continue
            finding["frames"] += 1
            for w in range(FRAME):
                ws = [frame[w] for frame in frames]
                moved = 0
                for x in ws[1:]:
                    moved |= x ^ ws[0]
                finding["bits"]["still"] += 32 - bin(moved).count("1")
                if not moved:
                    continue
                follows = inverted = full
                for x, state in zip(ws, states):
                    follows &= x if state else ~x & full
                    inverted &= ~x & full if state else x
                for b in range(32):
                    if not moved >> b & 1:
                        continue
                    where = {"far": f"{far:#010x}", "word": w, "bit": b}
                    if follows >> b & 1:
                        finding["bits"]["candidates"] += 1; finding["candidates"].append(dict(where, inverted=False))
                    elif inverted >> b & 1:
                        finding["bits"]["candidates_inverted"] += 1; finding["candidates"].append(dict(where, inverted=True))
                    else:
                        finding["bits"]["restless"] += 1
                        finding["restless"].append(dict(where, readings="".join(str(x >> b & 1) for x in ws)))
        if finding["bits"]["restless"]:
            bad(f"{finding['bits']['restless']} bit(s) read differently in readings that are of the same state, or follow no state: restless")
        if len(set(states)) < 2:
            bad("the states are all the same: a bit that follows the RAM cannot be told from one that is still")
    out["finding"] = finding

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


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    import s1a_run
    exp = s1a_run.with_share("s2_2", json.loads(s1a_run.STAGES["s2_2"]["expected"].read_text()), int(argv[2]))
    words = load(Path(argv[1]))
    if words is None:
        print("the result is not a whole number of words"); return 2
    verdict = judge(words, s1a_run.known_for("s2_2"), s1a_run.planned_words(exp))
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

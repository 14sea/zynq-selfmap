#!/usr/bin/env python3
"""Judge a result of stage 9 (S2.3) on the host — docs/s2_plan.md, section 29.

    s2_3_judge.py <result.bin> code              judge the result of the code run; prints the verdict as JSON
    s2_3_judge.py <result.bin> singles <r>       judge the result of run r of the singles

The run: the host gave the prober a list of reads and a list of accesses to the probe design. For each state of the
design's RAM the prober made the accesses before the mark, every read of the list of reads, and the accesses after the
mark. The question: which bit of what was read back is which cell of the RAM.

The same principles as every judge here. Nothing the board reports is taken on trust: codes, order, status and counts
are derived again from the raw words; the parameters the prober echoed must be the planned ones; the gate readings
are judged; everything about a read is held as the judge of S2.2 holds it (the streams, the address register, the
status after the read, bit 5 and its clearing, CTL0). And then:

  * The list of accesses. It must have the form the prober takes, name only registers the run may touch, and write
    only what the run's word allows. The log of what the prober did is walked against it, access by access: the
    same register, the same value written, and — where the list says what a reading must be — that reading. The
    first reading that is not so is where the run must have ended, with the stop that says whether it was before
    the frames of a state or after them.
  * The states are taken from the log, not from a name: what the RAM read back as through the design, at all 64
    addresses, before the frames of a state were read, and again after — and the two must be alike. The counter
    must have gone on between them. The shift registers must read as the design loads them, the design's count of
    writes must be the writes the log shows, and it must have counted no shift: no access of the log is a write to
    the shift registers' data.
  * The run is one of the step's: its states are those of the code run, or of one run of the singles, and both lists
    are the ones the plan makes for that run from the design, the census and what S2.2 found (s2_3_states.plan).
  * The finding. Every cell of the RAM has a row of values over the states; so has every bit of every frame read.
    A bit whose row is constant is *still*. A bit whose row is the row of one cell — and of no other — *follows*
    that cell; the opposite of a cell's row in every state: it follows it inverted. Anything else that changed is
    *irregular*, and fails the run. The bits that follow are listed: the address, the word, the bit, and the cell.

Whether every cell has its bit, and no other, is not asked here: the program that closes the code run asks it
(s2_3_table.py), and the singles are held to its table there.
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
import s2_3_states as st  # noqa: E402
from s1a_judge import CLEANUP, CTRL_MASK, ERR_MASK, KIND, MCTRL_LPBK, PCFG_DONE, SCTLR_C, SENTINEL, _command_outcome, return_code  # noqa: E402,F401
from s1b0_judge import DATA, DATA_WORDS, FARBLK, FRAME, MAX_READ_FRAMES, NO_OP, NONE, NOOP, POLLING, REC, describe, frames_stream, read_words  # noqa: E402
from s2_judge import CTL0_BITS, GATE_STATUS, PL_BASE, PL_SPAN, PLB_MAGIC, READ_HEADER, SEU_EN, SLCR_NAMES  # noqa: E402
from s2_2_judge import OP_CTL0, REG_CTL0, REG_FAR, REG_NAME, SEU_ERR, idle_status  # noqa: E402
from s2_2_judge import PL_CODES as PL_CODES_S2_2  # noqa: E402

STAGE = 9
HDR0, FIXED = 64, 16                                  # the header; the PL block before its log
LIST_MAX, MAX_STATES, ACC_MAX = s2_2_shares.LIST_MAX, 80, st.ACC_MAX
RESULT_MAX_WORDS = st.RESULT_MAX_WORDS
P_USED = 0xF70D82BF                                   # the words of the parameter block the stage has a use for
PL_BOUND = (0x04, 0x0C, 0x10, 0x14, 0x18)             # the offsets the image may ever write: its own bound (prober/sm.h)
SRL_DATA_OFF = 0x18
PL_CODES = {**PL_CODES_S2_2, 10: "a reading before the frames of a state was not what the list says",
            11: "a reading after the frames of a state was not what the list says: the design did not hold"}


def log_room(par: list[int]) -> int:
    """How many accesses the log has room for, as the prober's `log9` has it: the identification, and every entry of
    the list that is not a mark; 0 for counts that cannot be."""
    n, s = par[18], par[7]
    return 0 if (s == 0 or s > MAX_STATES or n > ACC_MAX or n < 2 * s) else 1 + n - 2 * s


def hdr_words(par: list[int]) -> int:
    """Where the records begin in a result made with this parameter block."""
    return HDR0 + FIXED + 2 * log_room(par)


def console_line(status: int, records: int, anomalies: int, hdr: int) -> str:
    if status == 0x500:
        return "SM%d end status=%08x" % (STAGE, status)
    return "SM%d end status=%08x records=%08x anomalies=%08x words=%08x" % (STAGE, status, records, anomalies, hdr + records * REC)


def params_valid(par: list[int]) -> bool:
    lo, hi, ref, n_states, limit, n_list = par[3], par[4], par[5], par[7], par[9], par[16]
    if (par[0], par[1], par[2]) != (0x31504D53, 1, STAGE) or lo > hi or not lo <= ref <= hi or log_room(par) == 0:
        return False
    if not 1 <= n_list <= LIST_MAX or not 0 < limit <= 0x10000000:
        return False
    if any(par[k] for k in range(32) if not P_USED >> k & 1) or par[15] & 0xFF or par[15] >> 8 not in POLLING:
        return False
    if par[19] & ~sum(1 << off for off in PL_BOUND):
        return False
    if hdr_words(par) + (4 + n_states * n_list) * REC > RESULT_MAX_WORDS:
        return False
    return PL_BASE <= par[24] <= par[25] < PL_BASE + PL_SPAN


def entries_of(acc: list[int]) -> list[tuple[int, int, int]]:
    """The list of accesses from its words: (kind, offset, value)."""
    return [(acc[2 * k] & 3, acc[2 * k] & ~3, acc[2 * k + 1]) for k in range(len(acc) // 2)]


def entries_problems(entries: list[tuple[int, int, int]], par: list[int]) -> list[str]:
    """Why a list of accesses is not one the prober takes with this parameter block — the prober's own check."""
    problems: list[str] = []
    state, phase = 0, 0
    for k, (kind, off, value) in enumerate(entries):
        if state >= par[7]:
            problems.append(f"entry {k}: something after the end of the last state"); break
        if kind == st.A_MARK:
            if off or value != phase:
                problems.append(f"entry {k}: a mark that is not the one due (offset {off:#x}, value {value:#x})"); break
            state, phase = (state + 1, 0) if phase else (state, 1)
            continue
        if off >= PL_SPAN or not par[24] <= PL_BASE + off <= par[25]:
            problems.append(f"entry {k}: offset {off:#x} is no register of the design inside the envelope")
        elif kind == st.A_WRITE and not par[19] >> off & 1:
            problems.append(f"entry {k}: a write to offset {off:#x}, which the run may not write")
        elif kind == st.A_READ and value:
            problems.append(f"entry {k}: a reading that is only recorded has a value")
    if not problems and (state != par[7] or phase):
        problems.append(f"the list ends inside state {state}: it is not {par[7]} whole states")
    return problems


def stretches(entries: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    """Where in the log the accesses before and after each state's mark lie: (begin, end) for every stretch, in order
    — before the frames of state 0, after them, before those of state 1, ... The log's first access is the prober's
    own (the identification): the entries begin at 1."""
    cuts: list[tuple[int, int]] = []
    at = begin = 1
    for kind, _, _ in entries:
        if kind == st.A_MARK:
            cuts.append((begin, at)); begin = at
        else:
            at += 1
    return cuts


def judge(words: list[int], known: dict | None, planned: list[int], rest=None) -> dict:
    """`planned`: the 32 words of the parameter block, after them the words of the list of reads, after them the words
    of the list of accesses. `known`: the facts of the probe design (pl/s2a/design.json) and, under "census" and
    "candidates", the census and what S2.2 found.

    `rest`: for another step that runs the same stage (S2.4, host/s2_4_judge.py). Everything a run of the stage is held
    to whatever its states are — the header, the gates, every record from its raw words, the log against the list of
    accesses, the schedule and what it implies — is judged here as for S2.3; then `rest` is given what was found and
    says the rest: what the design's own readings show, which run it is, the finding, the verdict. Without it, this is
    the judge of S2.3 as it was, word for word."""
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append
    planned_par = list(planned[:32])

    def invalid(why: str) -> dict:
        bad(why); out["verdict"] = "INVALID"; return out

    if len(words) < HDR0 or words[0] != 0x31524D53 or words[1] != 1:
        return invalid("not a result buffer (magic or version)")
    status, n, anomalies, total, rec_words, hdr = words[2:8]
    stop_record = words[18]
    par = words[32:64]
    HDR = hdr_words(par)
    out["header"] = {"status": f"{status:#x}", "records": n, "anomalies": anomalies, "total_words": total,
                     "ctrl": f"{words[8]:08x}", "mctrl": f"{words[9]:08x}", "int_sts_initial": f"{words[10]:08x}",
                     "status_initial": f"{words[11]:08x}", "sctlr": f"{words[12]:08x}", "cpsr": f"{words[13]:08x}",
                     "sp": f"{words[14]:08x}", "r9": f"{words[15]:08x}", "int_sts_final": f"{words[16]:08x}",
                     "status_final": f"{words[17]:08x}", "stop_record": f"{stop_record:#x}"}
    out["expected_console"] = [f"SM{STAGE} start", console_line(status, n, anomalies, HDR)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if (rec_words, hdr) != (REC, HDR) or HDR + n * REC > RESULT_MAX_WORDS or total != HDR + n * REC:
        return invalid(f"sizes do not add up for a stage-{STAGE} result: total {total}, records {n}, record size {rec_words}, header {hdr} "
                       f"(the echoed parameters give a header of {HDR})")
    if status == 0x500 and n:
        return invalid("a parameter refusal with records")
    if len(words) != total:
        return invalid(f"the buffer has {len(words)} words, the header says {total}")
    if any(words[19:32]):
        bad("reserved header words are not zero")

    lo, hi, ref, n_states, poll_limit, n_list, n_acc = par[3], par[4], par[5], par[7], par[9], par[16], par[18]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "states": n_states,
                     "reads_in_the_list": n_list, "entries_in_the_list_of_accesses": n_acc, "may_write": f"{par[19]:#010x}", "poll_limit": poll_limit}
    if list(par) != planned_par:
        differ = [k for k in range(32) if k >= len(planned_par) or par[k] != planned_par[k]]
        bad(f"the parameters the prober echoed are not the planned ones (word(s) {differ}): the run did not do what was asked")

    # ---- the PL block's own form, before anything is read out of it
    plb = words[HDR0:HDR]
    room = (len(plb) - FIXED) // 2
    if plb[0] != PLB_MAGIC:
        return invalid("the PL block does not begin with its magic")
    if plb[1] > room:
        return invalid(f"the PL block counts {plb[1]} accesses, more than it has room for")
    log = [(plb[FIXED + 2 * i], plb[FIXED + 1 + 2 * i]) for i in range(plb[1])]
    if any(plb[8:FIXED]):
        bad("reserved words of the PL block are not zero")
    if any(plb[FIXED + 2 * plb[1]:]):
        bad("the PL block holds words after the last access it counts")
    if status == 0x500:
        if plb[1] or plb[2] or any(plb[4:8]) or plb[3] != 0xFFFFFFFF:
            bad("a parameter refusal, yet the PL block is not empty")
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    if not params_valid(par):
        return invalid(f"the echoed parameters are not a valid stage-{STAGE} parameter block")
    out["params"]["polling_loop"] = POLLING[par[15] >> 8]
    out["params"]["pl_envelope"] = [f"{par[24]:#010x}", f"{par[25]:#010x}"]

    # ---- the two lists the host planned: as many words as the block says, and of the form the prober takes
    if len(planned) != 32 + n_list + 2 * n_acc:
        return invalid(f"the parameter block names {n_list} reads and {n_acc} entries; the plan has {len(planned) - 32} words after the block")
    reads = [(w & 0x0FFFFFFF, w >> 28) for w in planned[32:32 + n_list]]
    entries = entries_of(planned[32 + n_list:])
    for p in entries_problems(entries, par):
        return invalid(f"the planned list of accesses is not one the prober takes: {p}")
    lay = s2_2_shares.layout(known["census"]) if known and "census" in known else None
    if lay is None:
        bad("the census was not given: the list of reads and the address register cannot be held to anything")
    else:
        for p in s2_2_shares.list_problems(lay, reads):
            bad(f"the list of reads is not one made from the census: {p}")
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

    # ---- the records, each from its raw words: as the judge of S2.2 has them
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
            if derived == 0x20 and sts & ERR_MASK:       # this stage clears no error bit when a transfer begins, as stage 8: it stood there before
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
        after = fb[7]                                    # the status after the read, and what was done about bit 5: as in stage 8
        cleared = r[10] if of_list else 0xFFFFFFFF       # in the other reads that word is the reference frame's flag
        own = derived
        if cleared != 0xFFFFFFFF:
            if not after & SEU_ERR:
                bad(f"record {i}: a clearing of bit 5 is recorded ({cleared:08x}) although the status after the read ({after:08x}) does not show it")
            elif own or idle_status(after):
                bad(f"record {i}: bit 5 was cleared ({cleared:08x}) after a read that was not clean (status after it {after:08x})")
        derived = own or idle_status(after) or (idle_status(cleared) if cleared != 0xFFFFFFFF else 0)
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
            elif code == 0 and of_list:
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

    # ---- the log of accesses to the design, walked against the list the host wrote
    steps = [(PL_BASE, False, par[26], 2)]               # (address, a write?, the value or None, the stop a wrong reading implies): the identification first
    cuts = stretches(entries)
    phase_of: list[int] = []
    for (begin, end), k in zip(cuts, range(len(cuts))):
        phase_of += [k % 2] * (end - begin)
    for (kind, off, value), phase in zip([e for e in entries if e[0] != st.A_MARK], phase_of):
        steps.append((PL_BASE + off, kind == st.A_WRITE, None if kind == st.A_READ else value, 0 if kind != st.A_EXPECT else 11 if phase else 10))
    for i, (word, value) in enumerate(log):
        addr, write = word & ~3, bool(word & 1)
        off = addr - PL_BASE
        if word & 2 or not par[24] <= addr <= par[25] or not 0 <= off < PL_SPAN or (write and not par[19] >> off & 1):
            bad(f"PL access {i}: {'write to' if write else 'read of'} {addr:#010x} is outside what the run may touch")
        if write and off == SRL_DATA_OFF:
            if rest is None:                             # no run of S2.3 shifts; a step that does holds its shifts to its own plan
                bad(f"PL access {i}: a write to the shift registers' data — a shift")
    walked = {"at": 0}

    def stretch(begin: int, end: int) -> int:
        """Walk the log through one stretch of the list. Returns the stop the design's answers imply: 0 if every
        access of the stretch was made and answered as the list says; -1 if the log is not the list."""
        for at in range(begin, end):
            addr, write, value, code = steps[at]
            if at >= len(log):
                bad(f"the log of PL accesses ends after {len(log)}, where access {at} of the list is due, with nothing in it that ends the run")
                return -1
            got_addr, got_write, got = log[at][0] & ~3, bool(log[at][0] & 1), log[at][1]
            walked["at"] = at + 1
            if (got_addr, got_write) != (addr, write):
                bad(f"PL access {at}: {'a write to' if got_write else 'a read of'} {got_addr:#010x}, where {'a write to' if write else 'a read of'} {addr:#010x} is due")
                return -1
            if write and got != value:
                bad(f"PL access {at}: {got:#010x} written to {addr:#010x}, where {value:#010x} is due")
                return -1
            if not write and value is not None and got != value:
                return code
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

    implied: tuple[int, int, int] | None = None          # status, anomalies, stop record; a negative status: nothing can be derived
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
        todo: list = [("pl", 0, 1), ("read", ref, NONE, 0, OP_CTL0)]
        for s in range(n_states):
            todo.append(("pl", *cuts[2 * s]))
            todo += [("read", far, m, s, k) for k, (far, m) in enumerate(reads)]
            todo += [("pl", *cuts[2 * s + 1]), ("pass", s)]
        todo.append(("read", ref, NONE, n_states, OP_CTL0))
        for item in todo:
            if item[0] == "pl":
                pl_implied = stretch(item[1], item[2])
                if pl_implied > 0:
                    implied = (0xA00 | pl_implied, 0, 0xFFFFFFFF); break
                if pl_implied < 0:
                    pl_implied = 0; implied = (-2, 0, 0); break
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
            bad(f"{len(log) - walked['at']} access(es) to the design after the point where the list ends or the run must have ended (access {walked['at']})")
        if plb[2] != pl_implied:
            bad(f"the PL block's code is {plb[2]:#x} ({PL_CODES.get(plb[2], 'unknown')}); its log implies {pl_implied:#x} ({PL_CODES[pl_implied]})")
        if plb[3] != (len(log) if plb[2] else 0xFFFFFFFF):
            bad(f"the PL block says it stopped at access {plb[3]:#x}; with {len(log)} accesses and code {plb[2]:#x} that is not so")

    if rest is not None:
        return rest({"out": out, "known": known, "par": par, "status": status, "anomalies": anomalies, "plb": plb, "log": log, "cuts": cuts,
                     "passes_made": passes_made, "n_states": n_states, "n_list": n_list, "reads": reads, "entries": entries, "recs": recs,
                     "ctl0_seen": ctl0_seen})

    # ---- what the design said of itself, from the log and only as far as it goes: the states, the counter, the shift
    #      registers, the count of writes
    reg = st.registers(known) if known and "registers" in known else None
    pl: dict = {"accesses": len(log), "code": f"{plb[2]:#x}", "says": PL_CODES.get(plb[2], "unknown"), "passes_the_ram_held_through": passes_made}
    if log:
        pl["id"] = f"{log[0][1]:#010x}"
    states: list[list[int]] = []                         # for every state whose two stretches were walked whole: the RAM, 64 values
    if reg is None:
        bad("the design's registers were not given: what the log says of the RAM cannot be read")
    else:
        def back(begin: int, end: int, addr_reg: int, data_reg: int, depth: int) -> list[int | None]:
            """What a memory read back as in a stretch: the last reading at each address, by the address written before it."""
            got: list[int | None] = [None] * depth
            a = None
            for word, value in log[begin:end]:
                if word & ~3 == addr_reg and word & 1:
                    a = value
                elif word & ~3 == data_reg and not word & 1 and a is not None and a < depth:
                    got[a] = value
            return got

        loaded = st.srl_words(known) if "srl" in known else None
        if loaded is None:
            bad("the words the design loads into its shift registers were not given: what they read as cannot be held to anything")
        written = 0
        counters: list[str] = []
        for s in range(min(passes_made, n_states)):
            (b0, e0), (b1, e1) = cuts[2 * s], cuts[2 * s + 1]
            before, after = back(b0, e0, reg["RAM_ADDR"], reg["RAM_DATA"], st.DEPTH), back(b1, e1, reg["RAM_ADDR"], reg["RAM_DATA"], st.DEPTH)
            if None in before or None in after:
                bad(f"state {s}: the RAM was not read back at every address before the frames and after them"); break
            if any(v >> 4 for v in before + after):
                bad(f"state {s}: a reading of the RAM has bits set above the four there are"); break
            if before != after:
                bad(f"state {s}: the RAM did not read back after the frames as before them"); break
            states.append(before)
            count = [[v for w, v in log[b:e] if w & ~3 == reg["COUNT"] and not w & 1] for b, e in ((b0, e0), (b1, e1))]
            if not count[0] or not count[1]:
                bad(f"state {s}: the counter was not read before the frames and after them")
            else:
                counters += [f"{count[0][-1]:#010x}", f"{count[1][0]:#010x}"]
                if count[0][-1] == count[1][0]:
                    bad(f"state {s}: the counter read {count[0][-1]:#010x} before the frames and after them: the design's clock did not go on")
            written += sum(1 for w, _ in log[b0:e1] if w & ~3 == reg["RAM_DATA"] and w & 1)
            counted = [v for w, v in log[b1:e1] if w & ~3 == reg["WRITES"] and not w & 1]
            if not counted:
                bad(f"state {s}: the design's count of writes was not read after the frames")
            elif counted[-1] != written:
                bad(f"state {s}: the design counted {counted[-1] & 0xFFFF} write(s) and {counted[-1] >> 16} shift(s); the log has {written} write(s) to the RAM and no shift")
            else:
                pl["writes_counted"] = {"ram": counted[-1] & 0xFFFF, "shifts": counted[-1] >> 16}
            for which, (b, e) in (("before", (b0, e0)), ("after", (b1, e1))):
                srl = back(b, e, reg["SRL_ADDR"], reg["SRL_DATA"], st.SRL_DEPTH)
                if which == "after" and None in srl:
                    bad(f"state {s}: the shift registers were not read at every address after the frames")
                elif None not in srl and loaded is not None and srl != loaded:
                    bad(f"state {s}: the shift registers do not read as the design loads them ({which} the frames)")
                elif None not in srl:
                    pl["shift_registers_hold"] = [f"{sum((srl[a] >> k & 1) << a for a in range(st.SRL_DEPTH)):#010x}" for k in range(st.MEMORIES)]
        pl["counter"] = counters
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
    out["registers"] = {"CTL0": ctl0}

    # ---- which run of the step this is: by its states, and both lists held to what the plan makes for it
    run: dict = {"kind": None, "share": None}
    whole = status == 1 and passes_made == n_states and len(states) == n_states and len(recs) == 4 + n_states * n_list and all(r["code"] == 0 for r in recs)
    if whole:
        named = None
        if states == [x["ram"] for x in st.code_run()]:
            run, named = {"kind": "code", "share": None}, st.code_run()
        for r_ in range(st.SINGLE_RUNS):
            if states == [x["ram"] for x in st.single_run(r_)]:
                run, named = {"kind": "singles", "share": r_}, st.single_run(r_)
        if named is None:
            bad("the states the RAM read back as are not those of the code run or of a run of the singles")
        elif not known or "census" not in known or "candidates" not in known:
            bad("the census and what S2.2 found were not given: the lists cannot be held to the plan of the run")
        else:
            try:
                p = st.plan(run["kind"], run["share"], known, known["census"], known["candidates"])
            except (ValueError, KeyError) as e:          # what is known does not make a plan, or lacks what a plan is made from
                p = None
                bad(f"no plan can be made for the run: {e}")
            if p is not None:
                if reads != p["reads"]:
                    bad("the list of reads is not the one the plan makes for this run")
                if entries != [(kind, addr - PL_BASE if kind != st.A_MARK else 0, value) for kind, addr, value in p["entries"]]:
                    bad("the list of accesses is not the one the plan makes for this run")
                if par[19] != p["may_write"]:
                    bad(f"the run's word of what it may write is {par[19]:#010x}; the plan's lists write {p['may_write']:#010x}")
        run["states"] = [x["name"] for x in named] if named else None
    out["run"] = run

    # ---- the finding: every bit of every frame read, by its readings over the states
    finding: dict = {"states_read_whole": passes_made, "frames": 0, "bits": {"still": 0, "follow": 0, "follow_inverted": 0, "irregular": 0},
                     "follows": [], "irregular": [], "cells_not_told_apart": []}
    if whole:
        rows: dict[tuple, list[int]] = {}                # a row of values over the states -> the cells that have it
        for cell in range(st.CELLS):
            row = tuple(st.cell(state, cell) for state in states)
            if len(set(row)) > 1:
                rows.setdefault(row, []).append(cell)
        finding["cells_not_told_apart"] = sorted(cells for cells in rows.values() if len(cells) > 1)
        if finding["cells_not_told_apart"]:
            bad(f"the states do not tell {len(finding['cells_not_told_apart'])} group(s) of cells apart: a bit could not be said to follow one of them")
        readings: dict[int, list[list[int]]] = {}        # address -> one frame for each state
        for s in range(n_states):
            for k, (far, m) in enumerate(reads):
                for j, frame in enumerate(recs[2 + s * n_list + k]["frames"]):
                    readings.setdefault(far + j, []).append(frame)
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
                for b in range(32):
                    if not moved >> b & 1:
                        continue
                    row = tuple(x >> b & 1 for x in ws)
                    where = {"far": f"{far:#010x}", "word": w, "bit": b}
                    for inverted, key in ((False, row), (True, tuple(1 - v for v in row))):
                        if len(rows.get(key, [])) == 1:
                            cell = rows[key][0]
                            finding["bits"]["follow_inverted" if inverted else "follow"] += 1
                            finding["follows"].append(dict(where, cell=cell, memory=cell // st.DEPTH, address=cell % st.DEPTH, inverted=inverted))
                            break
                    else:
                        finding["bits"]["irregular"] += 1
                        finding["irregular"].append(dict(where, readings="".join(str(v) for v in row)))
        if finding["bits"]["irregular"]:
            bad(f"{finding['bits']['irregular']} bit(s) changed and follow no cell of the RAM: irregular")
    out["finding"] = finding

    if status != 1:
        bad(f"the run did not complete: status {status:#x}" + (f" ({PL_CODES[status & 0xFF]})" if status & 0xF00 == 0xA00 and status & 0xFF in PL_CODES else ""))
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def layout_hdr(kind: str) -> int:
    """Where the records begin in the result of a run of that kind: the header, the PL block, and a log with room for
    the identification and every access of the run's list. The list's length depends on the states and the design's
    registers alone — not on what is read through PCAP — and every run of the singles has the same."""
    design = json.loads(st.DESIGN.read_text())
    states = st.code_run() if kind == "code" else st.single_run(0)
    return HDR0 + FIXED + 2 * len(st.planned_log(st.accesses(states, design), design))


def planned_words(par: list[int], reads: list[tuple[int, int]], entries: list[tuple[int, int, int]], design: dict) -> list[int]:
    """What the judge is given as the plan: the parameter block, the list of reads, the list of accesses."""
    return list(par) + s2_2_shares.list_words(reads) + st.acc_words(entries, design)


def load(path: Path) -> list[int] | None:
    raw = path.read_bytes()
    if len(raw) % 4:
        return None
    return list(struct.unpack("<%dI" % (len(raw) // 4), raw))


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4) or argv[2] not in ("code", "singles") or (argv[2] == "singles") != (len(argv) == 4):
        print(__doc__); return 2
    import s1a_run
    stage = "s2_3c" if argv[2] == "code" else "s2_3s"
    exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), int(argv[3]) if len(argv) == 4 else None)
    words = load(Path(argv[1]))
    if words is None:
        print("the result is not a whole number of words"); return 2
    verdict = judge(words, s1a_run.known_for(stage), s1a_run.planned_words(exp))
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

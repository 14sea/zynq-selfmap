#!/usr/bin/env python3
"""Judge a stage-4 (S1b.1) result buffer: the walk of one column by the addresses the device named.

Same principles as the earlier judges: nothing the board reports is taken on trust. Every record's code is
re-derived from its raw words; the schedule — which here depends on the data, because the next address is
the one the device named — is re-derived by following the records the way the prober must have; the echoed
parameters must be the planned ones; the gate readings are judged.

What this stage claims, and so what is required for PASS:
  * the run completed with no anomaly, each pass ending for a reason the prober may end it for;
  * every pass named the same addresses and delivered the same frames;
  * each read of several frames delivered what the single reads of those frames delivered. Every frame of the
    walk is in such a read, unless the walk found one frame only; frames without this second path are listed;
  * the register after the read of a frame is the address the device names after the next frame, and after a
    read of several frames the address it names after the frame that follows them, wherever both were measured
    (the pad counts, as S1b.0 and S1b.0b found);
  * every frame with a known answer equals it wherever it was delivered — in the walk, in a read of several
    frames, and in every read of the reference frame — and the walk passed the known frames;
  * the reference frame was read again before more frames than asked had been delivered since its last reading.
Reported, not required: how many frames were walked, and which address ended the walk. The judge knows no
frame count and no column layout; a comparison with an outside description is another program's business.
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
from s1a_judge import (CLEANUP, CTRL_MASK, ERR_MASK, GATE_STATUS, KIND, MCTRL_LPBK, PCFG_DONE, SCTLR_C, SENTINEL,  # noqa: E402,F401
                       _command_outcome, return_code)
from s1b0_judge import DATA, DATA_WORDS, FARBLK, FARRD, FRAME, HDR, NO_OP, POLLING, REC, diag_word, frames_stream  # noqa: E402

STAGE, H_WALK = 4, 19
MAX_WALK, MAX_PASSES = 64, 2
MAX_DIAG_STACK = 64                              # parameter word 15: more stack beneath each target read (diagnostics, 2026-11-14)
MAX_RECORDS = 1 + MAX_PASSES * (2 * MAX_WALK + MAX_WALK) + MAX_WALK + 4      # generous: a health read after every frame
SUCC, CONTENT, TRIPLE = 0, 1, 2
OP_NAME = {SUCC: "successor read", CONTENT: "content read", TRIPLE: "read of several frames", NO_OP: "reference read"}
END = {0: "not ended", 1: "the device named an address outside the envelope", 2: "the limit of frames was reached"}
STOPS = {0x300: "the reference frame changed", 0x800: "the device named an address that is not above the one it was asked about"}


def console_line(status: int, records: int, anomalies: int) -> str:
    if status == 0x500:
        return "SM4 end status=%08x" % status
    return "SM4 end status=%08x records=%08x anomalies=%08x words=%08x" % (status, records, anomalies, HDR + records * REC)


def judge(words: list[int], known: dict, planned: list[int], run_of_a_chain: bool = False) -> dict:
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append

    def invalid(why: str) -> dict:
        bad(why); out["verdict"] = "INVALID"; return out

    if len(words) < HDR or words[0] != 0x31524D53 or words[1] != 1:
        return invalid("not a result buffer (magic or version)")
    status, n, anomalies, total, rec_words, hdr_words = words[2:8]
    stop_record = words[18]
    out["header"] = {"status": f"{status:#x}", "records": n, "anomalies": anomalies, "total_words": total,
                     "ctrl": f"{words[8]:08x}", "mctrl": f"{words[9]:08x}", "int_sts_initial": f"{words[10]:08x}",
                     "status_initial": f"{words[11]:08x}", "sctlr": f"{words[12]:08x}", "cpsr": f"{words[13]:08x}",
                     "sp": f"{words[14]:08x}", "r9": f"{words[15]:08x}", "int_sts_final": f"{words[16]:08x}",
                     "status_final": f"{words[17]:08x}", "stop_record": f"{stop_record:#x}"}
    out["expected_console"] = ["SM4 start", console_line(status, n, anomalies)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if status != 0x500 and ((rec_words, hdr_words) != (REC, HDR) or n > MAX_RECORDS or total != HDR + n * REC):
        return invalid(f"sizes do not add up for a stage-4 result: total {total}, records {n}, record size {rec_words}")
    if status == 0x500 and (total != HDR or n):
        return invalid("a parameter refusal with records")
    if len(words) != total:
        return invalid(f"the buffer has {len(words)} words, the header says {total}")

    par = words[32:64]
    lo, hi, ref, n_fars, passes, budget, poll_limit = par[3:10]
    limit, every, start = par[12], par[13], par[16]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "start": f"{start:#010x}",
                     "passes": passes, "limit": limit, "reference_every": every, "poll_limit": poll_limit, "extra_stack_words": diag_word(par[15])[0],
                     "polling_loop": POLLING.get(diag_word(par[15])[1])}
    if list(par) != list(planned):
        differ = [k for k in range(32) if k >= len(planned) or par[k] != planned[k]]
        bad(f"the parameters the prober echoed are not the planned ones (word(s) {differ}): the run did not do what was asked")
    if status == 0x500:
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    if (par[0], par[1], par[2]) != (0x31504D53, 1, STAGE) or lo > hi or not lo <= ref <= hi or n_fars != 1 or not lo <= start <= hi \
            or not 1 <= passes <= MAX_PASSES or not 1 <= limit <= MAX_WALK or every < 3 or budget != 0 or poll_limit == 0 \
            or any(par[k] for k in (10, 11, 14)) or diag_word(par[15])[0] > MAX_DIAG_STACK or diag_word(par[15])[1] not in POLLING or any(par[17:]):
        return invalid("the echoed parameters are not a valid stage-4 parameter block")

    ctrl, mctrl, sts0, sctlr, sts1 = words[8], words[9], words[10], words[12], words[16]
    failing = (0x101 if (ctrl & CTRL_MASK) != CTRL_MASK else 0x102 if mctrl & MCTRL_LPBK
               else 0x103 if not sts0 & PCFG_DONE else 0x104 if sctlr & SCTLR_C else 0)
    if status in GATE_STATUS:
        if n:
            bad("a gate stop with records")
        if failing != status:
            bad(f"the run reports a stop at the {GATE_STATUS[status]}, but the readings in its header "
                + (f"fail the {GATE_STATUS[failing]}" if failing else "satisfy every gate"))
        bad(f"the run stopped at the {GATE_STATUS[status]}"); out["verdict"] = "FAIL"; return out
    if failing:
        bad(f"the readings in the header fail the {GATE_STATUS[failing]}, yet the run went on")
    if status == 1 and (not sts1 & PCFG_DONE or sts1 & ERR_MASK):
        bad(f"the run reports done, but its final INT_STS {sts1:08x} has PCFG_DONE clear or an error bit set")
    if any(words[H_WALK + 3 * MAX_PASSES:32]):
        bad("reserved header words are not zero")

    # ---- each record from its raw words: everything but the comparisons with other records
    frames_known = {int(k, 16): [int(w, 16) for w in v["words"]] for k, v in known["frames"].items()}
    recs: list[dict] = []
    for i in range(n):
        r = words[HDR + i * REC: HDR + (i + 1) * REC]
        fb = r[FARBLK:FARBLK + 8]
        far, kind, code, m, op = r[0], r[1], r[2], r[14], r[15]
        rec = {"i": i, "far": far, "kind": kind, "code": code, "n": m, "op": op, "repeat": r[12], "ref_equal": r[10], "far_value": fb[4]}
        recs.append(rec)
        if m not in (0, 1, 2, 3):
            bad(f"record {i}: {m} frames per read"); m = 1
        nwords = FRAME * (m + 1)
        data, tail = r[DATA:DATA + nwords], r[DATA + nwords:]
        rec["frames"] = [data[FRAME * (j + 1):FRAME * (j + 2)] for j in range(m)]
        if far < lo or far > hi or far + max(m, 1) - 1 > hi:
            bad(f"record {i}: reads {far:#010x} + {m} frame(s), outside the envelope")
        if r[13] != 0 or code == 0x30:
            bad(f"record {i}: the prober's guard refused its own stream (guard word {r[13]:#x})")
        if any(tail):
            bad(f"record {i}: words after the {nwords} data words are not zero")
        if fb[7]:
            bad(f"record {i}: reserved words are not zero")
        for name, got, want in (("frame read stream", r[16:59], frames_stream(far, m)), ("FAR read stream", r[59:63], FARRD),
                                ("cleanup stream", r[63:68], CLEANUP)):
            if got != want:
                bad(f"record {i}: the {name} is not the pinned one")
            for p in packets.readonly_problems(got, lo, hi, DATA_WORDS):
                bad(f"record {i}: the {name} is not read-only: {p}")
        derived = 0
        attempted = done = False
        for name, sts, polls in (("frame command", r[3], r[4]), ("frame read", r[5], r[6]), ("FAR command", fb[0], fb[1]),
                                 ("FAR read", fb[2], fb[3]), ("cleanup", r[7], r[8])):
            if derived:
                if sts or polls:
                    bad(f"record {i}: the {name} transfer has a status although an earlier transfer failed")
                continue
            derived = _command_outcome(sts, polls, poll_limit)
            if derived < 0:
                bad(f"record {i}: the {name} transfer's status {sts:08x} after {polls} poll(s) is neither done, failed nor timed out")
                derived = 0xFF
            if polls > poll_limit:
                bad(f"record {i}: {polls} polls, above the limit {poll_limit}")
            attempted = attempted or (name == "FAR command" and derived == 0)
            done = done or (name == "FAR read" and derived == 0)
        survivors = sum(1 for w in data if w == SENTINEL)
        if survivors != r[9]:
            bad(f"record {i}: {survivors} sentinel word(s) in the data, the record says {r[9]}")
        unread = 1 if attempted and fb[4] == SENTINEL else 0
        if fb[5] != unread or (not attempted and fb[4]):
            bad(f"record {i}: the FAR value {fb[4]:08x} / unread flag {fb[5]} do not fit a FAR read that was {'queued' if attempted else 'never queued'}")
        if derived == 0:
            derived = 0x10 if survivors else 0x11 if any(data[:FRAME]) else 0x14 if unread else 0
        rec["own"] = derived                        # the code its own words imply; comparisons with other records come below
        rec["far_measured"] = done and not unread
        out["records"].append({"index": i, "far": f"{far:#010x}", "read": OP_NAME.get(op, f"operation {op:#x}"), "frames": m,
                               "kind": KIND.get(kind, kind), "pass": r[12], "code": f"{code:#x}", "far_read_back": f"{fb[4]:#010x}",
                               "int_sts": [f"{x:08x}" for x in (r[3], r[5], fb[0], fb[2], r[7])], "polls": [r[4], r[6], fb[1], fb[3], r[8]],
                               "survivors": survivors, "pad_all_zero": not any(data[:FRAME]), "poll_variable_at": f"{fb[6]:#010x}",
                               "frame_sha256": [hashlib.sha256(b"".join(struct.pack(">I", w) for w in f)).hexdigest() for f in rec["frames"]]})

    # ---- the schedule, followed the way the prober must have followed it
    walked: list[list[dict]] = []                    # per pass: {"far", "next", "succ", "content"}
    ends: list[tuple[int, int, int]] = []            # per pass: frames, how it ended, the last address named
    count_anomalies = 0
    state = {"i": 0}

    def take(kind: int, far: int, m: int, repeat: int, op: int) -> dict | None:
        i = state["i"]
        if i >= n:
            bad(f"the records end at {n}; a {OP_NAME[op]} of {far:#010x} (pass {repeat}) is missing")
            return None
        rec = recs[i]; state["i"] = i + 1
        if (rec["kind"], rec["far"], rec["n"], rec["repeat"], rec["op"]) != (kind, far, m, repeat, op):
            # not the record the schedule has here: nothing after it can be followed, and nothing may be compared
            # with a record of another shape. The schedule ends; the caller sees the same as a missing record.
            bad(f"record {i}: expected the {KIND[kind]} {OP_NAME[op]} of {far:#010x} x{m} (pass {repeat}), found a {KIND.get(rec['kind'], rec['kind'])} "
                f"{OP_NAME.get(rec['op'], hex(rec['op']))} of {rec['far']:#010x} x{rec['n']} (pass {rec['repeat']})")
            return None
        return rec

    def settle(rec: dict, derived: int) -> int:
        """The record's code must be the derived one."""
        if rec["code"] != derived and not (rec["code"] == 0x23 and derived in (0, 0x10, 0x11, 0x12, 0x13, 0x14)):
            bad(f"record {rec['i']}: code {rec['code']:#x}, but its raw words say {derived:#x}")
        return rec["code"]

    def healthy(rec: dict) -> bool:
        return rec["code"] == 0 and rec["frames"][:1] == recs[0]["frames"][:1] and rec["far_value"] == recs[0]["far_value"]

    def against_known(rec: dict, addresses: list[int]) -> None:
        """Every frame a clean record delivered, against the known frame at its address, where there is one."""
        if rec["code"] != 0:
            return
        for frame, far in zip(rec["frames"], addresses):
            if far in frames_known and frame != frames_known[far]:
                diff = [k for k in range(FRAME) if frame[k] != frames_known[far][k]]
                bad(f"record {rec['i']}: the frame at {far:#010x} read cleanly but differs from the known frame in {len(diff)} word(s), first at {diff[0]}")

    since = {"frames": 0, "most": 0}                 # frames delivered since the reference frame was last read

    def reference(kind: int, repeat: int) -> bool | None:
        rec = take(kind, ref, 1, repeat, NO_OP)
        if rec is None:
            return None
        since["frames"] = 0
        settle(rec, rec["own"])
        against_known(rec, [ref])
        if rec["ref_equal"] != (1 if healthy(rec) else 0):
            bad(f"record {rec['i']}: the reference flag is {rec['ref_equal']:#x}, the data say {int(healthy(rec))}")
        return healthy(rec)

    def stop_of(rec: dict) -> int:
        """A reference read that did not hold: an interface failure is reported as one; only otherwise has the
        reference frame changed. (Until 2026-11-14 the prober said 0x300 for both.)"""
        return 0x200 | rec["code"] if rec["code"] >= 0x20 else 0x300

    def after_anomaly(rec: dict, repeat: int) -> tuple[int, int, int]:
        """What the prober does after an anomalous walk record: the status it stops with."""
        if rec["code"] >= 0x20:
            return (0x200 | rec["code"], count_anomalies, rec["i"])
        ok = reference(1, repeat)
        if ok is None:
            return (-1, count_anomalies, 0)
        return (0x700 | rec["code"], count_anomalies, rec["i"]) if ok else (stop_of(recs[state["i"] - 1]), count_anomalies, state["i"] - 1)

    def first_clean(op: int, far: int, upto: int) -> dict | None:
        for rec in recs[1:upto]:
            if (rec["kind"], rec["repeat"], rec["op"], rec["far"], rec["code"]) == (0, 0, op, far, 0):
                return rec
        return None

    def due(m: int, repeat: int) -> tuple[int, int, int] | None:
        """Before a read that delivers m frames: the reference read the prober must make first, if any.
        Returns the status the run stops with, or None to go on."""
        if since["frames"] + m > every:
            ok = reference(1, repeat)
            if ok is None:
                return (-1, count_anomalies, 0)
            if not ok:
                return (stop_of(recs[state["i"] - 1]), count_anomalies, state["i"] - 1)
        since["frames"] += m
        since["most"] = max(since["most"], since["frames"])
        return None

    implied: tuple[int, int, int] | None = None
    base = take(2, ref, 1, 0, NO_OP)
    if base is None:
        implied = (-1, 0, 0)
    elif settle(base, base["own"]) != 0:
        implied = (0x600 | base["code"], 0, 0)
    else:
        against_known(base, [ref])
    for p in range(passes if not implied else 0):
        cur, count, steps = start, 0, []
        walked.append(steps)
        ended = 0
        while not implied:
            pair = []
            for op, m in ((SUCC, 0), (CONTENT, 1)):
                if op == CONTENT:
                    implied = due(1, p)
                    if implied:
                        break
                rec = take(0, cur, m, p, op)
                if rec is None:
                    implied = (-1, count_anomalies, 0); break
                derived = rec["own"]
                if derived == 0 and p > 0:                      # a later pass: against pass 0 at this address
                    first = first_clean(op, cur, rec["i"])
                    if first is None or first["far_value"] != rec["far_value"]:
                        derived = 0x13
                    elif first["frames"] != rec["frames"]:
                        derived = 0x12
                if settle(rec, derived) != 0:
                    count_anomalies += 1
                    implied = after_anomaly(rec, p); break
                pair.append(rec)
            if implied:
                break
            nxt = pair[0]["far_value"]
            steps.append({"far": cur, "next": nxt, "succ": pair[0], "content": pair[1]})
            against_known(pair[1], [cur])
            count += 1
            if nxt <= cur:                                      # not above the address asked about, wherever it lies
                implied = (0x800, count_anomalies, pair[0]["i"]); break
            if nxt > hi:
                ended = 1; break
            if count >= limit:
                ended = 2; break
            cur = nxt
        ends.append((count, ended, steps[-1]["next"] if steps else 0))
    covered: set[int] = set()                        # places in the list of pass 0 that a clean read of several frames delivered
    if not implied:
        first_pass = walked[0] if walked else []
        n0 = len(first_pass)
        for k in range(0, n0, 3):
            m, at = 3, k
            if n0 - k < 3:                           # one or two left over: the last three again; both, if there are only two
                if n0 >= 3:
                    at = n0 - 3
                elif n0 == 2:
                    m = 2
                else:
                    break
            implied = due(m, passes)
            if implied:
                break
            rec = take(0, first_pass[at]["far"], m, passes, TRIPLE)
            if rec is None:
                implied = (-1, count_anomalies, 0); break
            derived = rec["own"]
            if derived == 0 and any(rec["frames"][j] != first_pass[at + j]["content"]["frames"][0] for j in range(m)):
                derived = 0x12
            if settle(rec, derived) != 0:
                count_anomalies += 1
                implied = after_anomaly(rec, passes); break
            against_known(rec, [first_pass[at + j]["far"] for j in range(m)])
            covered.update(range(at, at + m))
    if not implied:
        ok = reference(3, passes)
        implied = (-1, count_anomalies, 0) if ok is None else (1, count_anomalies, 0xFFFFFFFF) if ok else (stop_of(recs[state["i"] - 1]), count_anomalies, state["i"] - 1)
    if state["i"] != n:
        bad(f"{n - state['i']} record(s) after the point where the schedule ends (record {state['i']})")
    if implied[0] >= 0:
        if status != implied[0]:
            bad(f"the header's status is {status:#x}; the records imply {implied[0]:#x}")
        if anomalies != implied[1]:
            bad(f"the header counts {anomalies} anomalies; the records show {implied[1]}")
        if stop_record != implied[2]:
            bad(f"the header's stop record is {stop_record:#x}; the records imply {implied[2]:#x}")
    for p in range(MAX_PASSES):
        got = tuple(words[H_WALK + 3 * p:H_WALK + 3 * p + 3])
        want = ends[p] if p < len(ends) else (0, 0, 0)
        if got != want:
            bad(f"pass {p}: the header says {got[0]} frame(s), end {got[1]}, last address {got[2]:#010x}; the records show {want[0]}, {want[1]}, {want[2]:#010x}")
    for rec in recs:
        if rec["kind"] not in (1, 3) and rec["ref_equal"] != 0xFFFFFFFF:
            bad(f"record {rec['i']}: a reference flag on a {KIND.get(rec['kind'], rec['kind'])} read")

    # ---- what the walk found
    out["passes"] = [{"frames": c, "ended": END.get(e, e), "last_address_named": f"{a:#010x}"} for c, e, a in ends]
    first_pass = walked[0] if walked else []
    out["walk"] = [{"far": f"{s['far']:#010x}", "next": f"{s['next']:#010x}", "register_after_the_frame": f"{s['content']['far_value']:#010x}",
                    "frame_sha256": hashlib.sha256(b"".join(struct.pack(">I", w) for w in s["content"]["frames"][0])).hexdigest()} for s in first_pass]
    out["frames_walked"] = len(first_pass)
    for p, steps in enumerate(walked[1:], 1):
        if [(s["far"], s["next"]) for s in steps] != [(s["far"], s["next"]) for s in first_pass][:len(steps)] or (status == 1 and len(steps) != len(first_pass)):
            bad(f"pass {p} did not name the same addresses as pass 0")
    if status == 1 and len(set(ends)) > 1:
        bad("the passes did not end alike: " + ", ".join(f"{c} frame(s), {END.get(e, e)}, {a:#010x}" for c, e, a in ends))
    # the register after the read of a frame is the address the device names after the next frame
    named = {s["far"]: s["next"] for s in first_pass}
    crossed = 0
    for steps in walked:
        for s in steps:
            if s["next"] in named:
                crossed += 1
                if s["content"]["far_value"] != named[s["next"]]:
                    bad(f"after the frame at {s['far']:#010x} the register held {s['content']['far_value']:#010x}, but the device names "
                        f"{named[s['next']]:#010x} after {s['next']:#010x}")
    # ... and after a read of several frames, the address the device names after the frame that follows them
    for rec in recs:
        if rec["kind"] == 0 and rec["op"] == TRIPLE and rec["code"] == 0 and rec["far"] in named:
            at = [s["far"] for s in first_pass].index(rec["far"])
            if at + rec["n"] < len(first_pass):
                crossed += 1
                want = first_pass[at + rec["n"]]["next"]
                if rec["far_value"] != want:
                    bad(f"after the {rec['n']} frames from {rec['far']:#010x} the register held {rec['far_value']:#010x}, but the device names "
                        f"{want:#010x} after {first_pass[at + rec['n']]['far']:#010x}")
    out["register_cross_checks"] = crossed
    # the frames with a known answer were compared wherever they were delivered (against_known); here: were they reached
    reached = {s["far"] for s in first_pass}
    missing = sorted(f for f in frames_known if lo <= f <= hi and f not in reached)
    out["known_frames_not_reached"] = [f"{f:#010x}" for f in missing]
    # A walk that leaves the envelope without having passed the known frames in it has failed: that is S1b.1's rule,
    # and a walk that starts above them fails by it. One run of a chain (S1b.2) is judged otherwise in this one point:
    # a walk only goes upward (an address named that is not above the current one stops it), so a run that begins
    # beyond a known frame cannot pass it — the run of the chain that began below it has to. For such a run only the
    # known frames at or above its start count. The frames not reached are listed above in either case, and the
    # reference frame, read throughout every run, is held against its known answer as before.
    passed_by = [f for f in missing if f >= start or not run_of_a_chain]
    if status == 1 and passed_by and ends and ends[0][1] == 1:
        bad("the walk left the envelope without passing the known frame(s) " + ", ".join(f"{f:#010x}" for f in passed_by))
    out["reads_at_addresses_without_a_known_answer"] = sum(1 for s in first_pass if s["far"] not in frames_known)
    # the second path: which frames of the walk no clean read of several frames delivered. With one frame walked there
    # is no such read to make; otherwise a completed run covers every frame, and anything listed here is a stopped run's
    out["frames_without_a_second_path"] = [f"{s['far']:#010x}" for k, s in enumerate(first_pass) if k not in covered]
    out["most_frames_between_reference_reads"] = since["most"]
    # diagnostics: where the polling loop's status word lay during each read, and which reads failed there
    spots: dict[str, dict] = {}
    for rec, shown in zip(recs, out["records"]):
        key = shown["poll_variable_at"]
        s = spots.setdefault(key, {"address_mod_32": int(key, 16) % 32, "frame_reads": 0, "pad_only_reads": 0, "interface_failures": []})
        s["frame_reads" if rec["n"] else "pad_only_reads"] += 1
        if rec["code"] >= 0x20:
            s["interface_failures"].append(rec["i"])
    out["polling_variable"] = spots

    if status != 1:
        bad(f"the run did not complete: status {status:#x}" + (f" ({STOPS[status]})" if status in STOPS else ""))
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def main(argv: list[str]) -> int:
    raw = Path(argv[1]).read_bytes()
    if len(raw) % 4:
        print(json.dumps({"verdict": "INVALID", "problems": [f"the file is {len(raw)} bytes, not a whole number of 32-bit words"]}, indent=1))
        return 1
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
    expected = json.loads(Path(argv[2] if len(argv) > 2 else ROOT / "build" / "prober" / "expected_s1b1.json").read_text())
    result = judge(words, known, [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

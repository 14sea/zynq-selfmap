#!/usr/bin/env python3
"""Judge a stage-2 (S1b.0) result buffer on the host. Same principles as s1a_judge: nothing the board
reports is taken on trust; codes, order, status and counts are re-derived from the raw words; the echoed
parameters must be the planned ones; the gate readings are judged; only then the known frames.

What is new in this stage and judged here:
  * a read may cover one to three frames: each frame is compared with the known frame at its address,
    and the unused tail of the record must be zero;
  * after each read the FAR register is read back: the value must be the same on every repeat of an
    operation, and across the whole run it must follow ONE rule — the frame after the last one read,
    or the one after that. Which rule is the finding; a run that fits neither, or both, fails.

Stage 3 (S1b.0b, `judge(..., stage=3)`, also reached through s1b0b_judge) has the same records. Its operations
may also read the pad alone (a frame count of 0) or nothing at all (NONE), and its finding is a table, not a
rule: what the FAR register held after each kind of read at each address. The value must be the same whenever
the same read is made at the same address; how it depends on the length is reported, not required.

In both stages a FAR value counts as measured whenever the FAR read itself succeeded, also in a record that is
anomalous for another reason (a pad that is not zero, frame data that differ): the finding is drawn from every
value the register gave, never from the clean records alone.
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
from s1a_judge import (CLEANUP, CLEAR_MASK, CTRL_MASK, D_P_DONE, ERR_MASK, GATE_STATUS, KIND, MAX_FARS, MAX_REPEATS,  # noqa: E402,F401
                       MCTRL_LPBK, PCFG_DONE, SCTLR_C, SENTINEL, _command_outcome, pinned_stream, return_code)

HDR, REC, FARBLK, DATA = 64, 480, 68, 76
FRAME, MAX_READ_FRAMES, DATA_WORDS = 101, 3, 404
MAX_RECORDS = 1 + MAX_FARS * MAX_REPEATS * 2 + 1
FARRD = [0x20000000, 0x28002001, 0x20000000, 0x20000000]
NO_OP = 0xFFFFFFFF
NONE = 0xF                                           # stage 3, as a frame count: no FDRO read at all
NOOP = 0x20000000
RULES = {0: "next: the register holds the frame after the last one read", 1: "next but one: the register holds the frame after that"}


def frames_stream(far: int, n: int) -> list[int]:
    s = pinned_stream(far)
    if n == NONE:
        s[9] = s[10] = NOOP
    else:
        s[10] = 0x48000000 | FRAME * (n + 1)
    return s


def read_words(n: int) -> int:
    return 0 if n == NONE else FRAME * (n + 1)


def describe(n: int) -> str:
    return "no read" if n == NONE else "the pad alone" if n == 0 else f"the pad and {n} frame(s)"


def console_line(status: int, records: int, anomalies: int, stage: int = 2) -> str:
    if status == 0x500:
        return "SM%d end status=%08x" % (stage, status)
    return "SM%d end status=%08x records=%08x anomalies=%08x words=%08x" % (stage, status, records, anomalies, HDR + records * REC)


def planned_ops(par: list[int]) -> list[tuple[int, int]]:
    return [(par[16 + k], (par[10 + k // 8] >> (4 * (k % 8))) & 0xF) for k in range(min(par[6], MAX_FARS))]


def judge(words: list[int], known: dict, planned: list[int], stage: int = 2) -> dict:
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
    out["expected_console"] = [f"SM{stage} start", console_line(status, n, anomalies, stage)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if status != 0x500 and ((rec_words, hdr_words) != (REC, HDR) or n > MAX_RECORDS or total != HDR + n * REC):
        return invalid(f"sizes do not add up for a stage-{stage} result: total {total}, records {n}, record size {rec_words}")
    if status == 0x500 and (total != HDR or n):
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
    if status == 0x500:
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    ops = planned_ops(par)

    def count_ok(m: int) -> bool:                    # a frame count this stage may ask for
        return 1 <= m <= MAX_READ_FRAMES or (stage == 3 and m in (0, NONE))

    def delivered(m: int) -> int:                    # how many frames a read with this count delivers
        return 0 if m == NONE else m

    if (par[0], par[1], par[2]) != (0x31504D53, 1, stage) or lo > hi or not lo <= ref <= hi \
            or not 1 <= n_ops <= MAX_FARS or not 1 <= repeats <= MAX_REPEATS or poll_limit == 0 \
            or any(not count_ok(m) or far < lo or far > hi or far + max(delivered(m), 1) - 1 > hi for far, m in ops):
        return invalid(f"the echoed parameters are not a valid stage-{stage} parameter block")
    out["params"]["ops"] = [[f"{far:#010x}", "none" if m == NONE else m] for far, m in ops]

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

    frames_known = {int(k, 16): [int(w, 16) for w in v["words"]] for k, v in known["frames"].items()}
    recs: list[dict] = []
    first_clean: dict[int, dict] = {}
    deltas: dict[int, list[int]] = {}
    after: dict[tuple[int, int], dict[int, list[int]]] = {}       # stage 3: (address, count) -> value read back -> records
    for i in range(n):
        r = words[HDR + i * REC: HDR + (i + 1) * REC]
        fb = r[FARBLK:FARBLK + 8]
        far, kind, code, m, op = r[0], r[1], r[2], r[14], r[15]
        rec = {"i": i, "far": far, "kind": kind, "code": code, "n": m, "op": op, "repeat": r[12], "ref_equal": r[10],
               "far_value": fb[4], "frames": []}
        recs.append(rec)
        if not count_ok(m):
            bad(f"record {i}: {m} frames per read"); m = 1
        nwords = read_words(m)
        data, tail = r[DATA:DATA + nwords], r[DATA + nwords:]
        rec["frames"] = [data[FRAME * (j + 1):FRAME * (j + 2)] for j in range(delivered(m))]
        if far < lo or far > hi or far + max(delivered(m), 1) - 1 > hi:
            bad(f"record {i}: reads {far:#010x} + {delivered(m)} frame(s), outside the envelope")
        if r[13] != 0 or code == 0x30:
            bad(f"record {i}: the prober's guard refused its own stream (guard word {r[13]:#x})")
        if any(tail):
            bad(f"record {i}: words after the {nwords} data words are not zero")
        if fb[6] or fb[7]:
            bad(f"record {i}: reserved words are not zero")
        for name, got, want in (("frame read stream", r[16:59], frames_stream(far, m)), ("FAR read stream", r[59:63], FARRD),
                                ("cleanup stream", r[63:68], CLEANUP)):
            if got != want:
                bad(f"record {i}: the {name} is not the pinned one")
            for p in packets.readonly_problems(got, lo, hi, DATA_WORDS):
                bad(f"record {i}: the {name} is not read-only: {p}")
        # the five commands in the order they are attempted
        derived = 0
        far_read_attempted = False                   # the prober records the word it finds whenever it queued the FAR read
        far_read_done = False                        # the FAR read transfer itself completed without an interface failure
        for name, sts, polls in (("frame command", r[3], r[4]), ("frame read", r[5], r[6]), ("FAR command", fb[0], fb[1]),
                                 ("FAR read", fb[2], fb[3]), ("cleanup", r[7], r[8])):
            if derived:
                if sts or polls:
                    bad(f"record {i}: the {name} transfer has a status although an earlier transfer failed")
                continue
            if name == "frame read" and m == NONE:   # nothing to read: the prober queues no read command
                if sts or polls:
                    bad(f"record {i}: a frame read transfer has a status in an operation that reads nothing")
                continue
            derived = _command_outcome(sts, polls, poll_limit)
            if derived < 0:
                bad(f"record {i}: the {name} transfer's status {sts:08x} after {polls} poll(s) is neither done, failed nor timed out")
                derived = 0xFF
            if polls > poll_limit:
                bad(f"record {i}: {polls} polls, above the limit {poll_limit}")
            if name == "FAR command" and derived == 0:
                far_read_attempted = True
            if name == "FAR read" and derived == 0:
                far_read_done = True
        survivors = sum(1 for w in data if w == SENTINEL)
        if survivors != r[9]:
            bad(f"record {i}: {survivors} sentinel word(s) in the data, the record says {r[9]}")
        unread = 1 if far_read_attempted and fb[4] == SENTINEL else 0
        if fb[5] != unread or (not far_read_attempted and fb[4]):
            bad(f"record {i}: the FAR value {fb[4]:08x} / unread flag {fb[5]} do not fit a FAR read that was {'queued' if far_read_attempted else 'never queued'}")
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
                elif first_clean[op]["far_value"] != fb[4]:
                    derived = 0x13
        if code != derived and not (code == 0x23 and derived in (0, 0x10, 0x11, 0x12, 0x13, 0x14)):
            bad(f"record {i}: code {code:#x}, but its raw words say {derived:#x}")
        if code == 0 and kind == 0:
            first_clean.setdefault(op, rec)
        # A FAR value is a measurement whenever the FAR read itself succeeded, whatever else is wrong with the record:
        # a pad that is not zero, or frame data that differ, do not make the register's value unread. Leaving such
        # records out would let the finding be drawn from the clean records alone and miss what the others say.
        rec["far_measured"] = far_read_done and not unread
        if rec["far_measured"]:
            deltas.setdefault(fb[4] - (far + delivered(m)), []).append(i)
            after.setdefault((far, m), {}).setdefault(fb[4], []).append(i)
        digests = []
        for j, frame in enumerate(rec["frames"]):
            digests.append(hashlib.sha256(b"".join(struct.pack(">I", w) for w in frame)).hexdigest())
            if code == 0:
                if far + j not in frames_known:
                    bad(f"record {i}: no known answer for FAR {far + j:#010x}")
                elif frame != frames_known[far + j]:
                    diff = [k for k in range(FRAME) if frame[k] != frames_known[far + j][k]]
                    bad(f"record {i}: frame {j} (FAR {far + j:#010x}) read cleanly but differs from the known frame in {len(diff)} word(s), first at {diff[0]}")
        out["records"].append({"index": i, "far": f"{far:#010x}", "frames": delivered(m), "words": nwords, "kind": KIND.get(kind, kind), "op": None if op == NO_OP else op,
                               "code": f"{code:#x}", "repeat": r[12], "far_read_back": f"{fb[4]:#010x}",
                               "int_sts": [f"{x:08x}" for x in (r[3], r[5], fb[0], fb[2], r[7])], "polls": [r[4], r[6], fb[1], fb[3], r[8]],
                               "survivors": survivors, "pad_all_zero": (not any(data[:FRAME])) if nwords else None, "frame_sha256": digests})

    def healthy(rec: dict) -> bool:
        return rec["code"] == 0 and rec["frames"][:1] == recs[0]["frames"][:1] and rec["far_value"] == recs[0]["far_value"]

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
    else:
        i = 1
        for rep in range(repeats):
            for k, (far, m) in enumerate(ops):
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
                    implied = (0x300, count, i - 1); break
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
                implied = (1, count, 0xFFFFFFFF) if healthy(f) else (0x300, count, i - 1)
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

    if stage == 2:
        # ---- the finding: which rule the FAR register follows
        out["far_deltas"] = {str(d): v for d, v in sorted(deltas.items())}
        if len(deltas) == 1 and next(iter(deltas)) in RULES:
            out["far_rule"] = RULES[next(iter(deltas))]
        elif deltas:
            bad("the FAR values read back do not follow one rule: (value - (address + frames read)) is "
                + ", ".join(f"{d} in record(s) {v}" for d, v in sorted(deltas.items())))
    else:
        # ---- the finding: what the FAR register held after each kind of read at each address. Required: the same
        # read at the same address always leaves the same value. Reported, not required: how the value depends on
        # the length read. Nothing is derived from an address that was not read back.
        table = []
        steps: dict[int, set[int]] = {}
        for (far, m), values in sorted(after.items(), key=lambda kv: (read_words(kv[0][1]), kv[0][0])):
            if len(values) != 1:
                bad(f"the FAR value after {describe(m)} at {far:#010x} is not the same every time: "
                    + ", ".join(f"{v:#010x} in record(s) {where}" for v, where in sorted(values.items())))
            for value, where in sorted(values.items()):
                table.append({"far": f"{far:#010x}", "read": describe(m), "words": read_words(m), "far_read_back": f"{value:#010x}",
                              "step": value - far, "records": where,
                              "records_with_another_anomaly": {str(k): f"{recs[k]['code']:#x}" for k in where if recs[k]["code"] != 0}})
                steps.setdefault(read_words(m), set()).add(value - far)
        out["far_after"] = table
        out["steps_by_words"] = {str(w): sorted(s) for w, s in sorted(steps.items())}
        # Three answers. False: some value read back does not fit — one is enough, wherever it came from. True: every
        # value fits AND every read the plan asked for has at least one value from a record with nothing else wrong.
        # None (undetermined): nothing contradicts it, but some planned read has no such value to stand on.
        wanted = {(ref, 1)} | set(ops)
        clean = {(rec["far"], rec["n"]) for rec in recs if rec["far_measured"] and rec["code"] == 0}
        missing = sorted(wanted - clean, key=lambda fm: (read_words(fm[1]), fm[0]))
        out["reads_without_a_clean_far_value"] = [[f"{far:#010x}", describe(m)] for far, m in missing]
        if any(s != {w // FRAME} for w, s in steps.items()):
            out["one_step_per_frame_of_words"] = False
        else:
            out["one_step_per_frame_of_words"] = None if missing else True

    if status != 1:
        bad(f"the run did not complete: status {status:#x}")
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
    expected = json.loads(Path(argv[2] if len(argv) > 2 else ROOT / "build" / "prober" / "expected_s1b0.json").read_text())
    result = judge(words, known, [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

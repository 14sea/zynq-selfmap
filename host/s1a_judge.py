#!/usr/bin/env python3
"""Judge an S1a result buffer on the host.

The board's own verdict is not taken on trust. Everything the header and the record codes claim is
re-derived here from the raw words the records carry, and the two must agree:

  * the sizes, the echoed parameters and the order of the records against the prober's schedule
    (baseline, then every frame of every repeat in order, a health read after each anomaly, the
    final reference read), so that no frame can be missing or replaced;
  * each record's code against the raw data (sentinel survivors, the pad half, a repeat that
    differs) and against the status words recorded for its three DMA commands;
  * the header's status, anomaly count and stop record against what that walk implies;
  * every stream the record says was sent, against the pinned words and the read-only policy;
  * the echoed parameters against the parameters planned for this run, word for word — the
    schedule is rebuilt from what was planned, not from what the result says was asked;
  * the gate readings in the header against the gates, and against the status: a run that went
    on must show every gate satisfied, a run stopped at a gate must show that gate failing;
  * and only then the frames against the known answer, which the board does not carry.

PASS means: the run completed, no anomaly, every scheduled read present, every frame equal to
the known frame, nothing inconsistent.
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

HDR, REC, STREAM_AT, DATA_AT = 64, 266, 16, 16 + 43 + 5
FRAME, READ = 101, 202
SENTINEL = 0xA5A55A5A
ERR_MASK, CLEAR_MASK, D_P_DONE, PCFG_DONE = 0x00F4C840, 0x00F4F840, 0x00001000, 0x00000004
KIND = {0: "target", 1: "health", 2: "baseline", 3: "final"}
MAX_FARS, MAX_REPEATS = 16, 8
MAX_RECORDS = 1 + MAX_FARS * MAX_REPEATS * 2 + 1
CLEANUP = [0x20000000, 0x30008001, 0x0000000D, 0x20000000, 0x20000000]
GATE_STATUS = {0x101: "CTRL gate", 0x102: "loopback gate", 0x103: "PCFG_DONE gate", 0x104: "data-cache gate", 0x500: "bad parameters"}


def pinned_stream(far: int) -> list[int]:
    return [0xFFFFFFFF, 0xAA995566, 0x20000000, 0x20000000, 0x30008001, 0x00000004, 0x20000000,
            0x30002001, far, 0x28006000, 0x480000CA] + [0x20000000] * 32


def console_line(status: int, records: int, anomalies: int) -> str:
    if status == 0x500:
        return "SM1 end status=%08x" % status
    return "SM1 end status=%08x records=%08x anomalies=%08x words=%08x" % (status, records, anomalies, HDR + records * REC)


def return_code(status: int) -> int:
    return 0 if status == 1 else status


def _command_outcome(sts: int, polls: int, poll_limit: int) -> int:
    """What one DMA command's recorded status and poll count say happened to it."""
    if polls == 0:                                   # never queued: the stale check or the precondition
        return 0x20 if sts & CLEAR_MASK else (0x23 if not sts & PCFG_DONE else -1)
    if sts & ERR_MASK:
        return 0x21
    if not sts & PCFG_DONE:
        return 0x23
    if sts & D_P_DONE:
        return 0
    return 0x22 if polls >= poll_limit else -1


CTRL_MASK, MCTRL_LPBK, SCTLR_C = 0x0C000000, 0x00000010, 0x00000004


def judge(words: list[int], known: dict, planned: list[int]) -> dict:
    """`planned` is the 32-word parameter block this run was meant to have."""
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append

    def invalid(why: str) -> dict:
        bad(why); out["verdict"] = "INVALID"; return out

    # ---- the header and its sizes
    if len(words) < HDR or words[0] != 0x31524D53 or words[1] != 1:
        return invalid("not an S1a result (magic or version)")
    status, n, anomalies, total, rec_words, hdr_words = words[2:8]
    stop_record = words[18]
    out["header"] = {"status": f"{status:#x}", "records": n, "anomalies": anomalies, "total_words": total,
                     "ctrl": f"{words[8]:08x}", "mctrl": f"{words[9]:08x}", "int_sts_initial": f"{words[10]:08x}",
                     "status_initial": f"{words[11]:08x}", "sctlr": f"{words[12]:08x}", "cpsr": f"{words[13]:08x}",
                     "sp": f"{words[14]:08x}", "r9": f"{words[15]:08x}", "int_sts_final": f"{words[16]:08x}",
                     "status_final": f"{words[17]:08x}", "stop_record": f"{stop_record:#x}"}
    out["expected_console"] = ["SM1 start", console_line(status, n, anomalies)]
    out["expected_return_code"] = f"{return_code(status):#x}"
    if (rec_words, hdr_words) != (REC, HDR) or n > MAX_RECORDS or total != HDR + n * REC:
        return invalid(f"sizes do not add up: total {total}, records {n}")
    if len(words) != total:
        return invalid(f"the buffer has {len(words)} words, the header says {total}")
    if any(words[19:32]):
        bad("reserved header words are not zero")

    # ---- the echoed parameters
    par = words[32:64]
    lo, hi, ref, n_fars, repeats, budget, poll_limit = par[3:10]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "n_fars": n_fars,
                     "repeats": repeats, "anomaly_budget": budget, "poll_limit": poll_limit}
    if list(par) != list(planned):
        differ = [k for k in range(32) if k >= len(planned) or par[k] != planned[k]]
        bad(f"the parameters the prober echoed are not the planned ones (word(s) {differ}): the run did not do what was asked")
    if status == 0x500:
        if n:
            bad("a parameter refusal with records")
        bad("the run stopped: bad parameters"); out["verdict"] = "FAIL"; return out
    if (par[0], par[1], par[2]) != (0x31504D53, 1, 1) or lo > hi or not lo <= ref <= hi \
            or not 1 <= n_fars <= MAX_FARS or not 1 <= repeats <= MAX_REPEATS or poll_limit == 0:
        return invalid("the echoed parameters are not a valid S1a parameter block")
    fars = par[16:16 + n_fars]
    out["params"]["fars"] = [f"{x:#010x}" for x in fars]
    if any(not lo <= f <= hi for f in fars):
        return invalid("an echoed frame address lies outside the echoed envelope")
    # ---- the gate readings in the header: which gate, if any, do they fail? (the prober's own order; a reading
    #      after the failing gate was never taken and is zero, which that order never looks at)
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
        bad(f"the readings in the header fail the {GATE_STATUS[failing]} (CTRL {ctrl:08x}, MCTRL {mctrl:08x}, INT_STS {sts0:08x}, "
            f"SCTLR {sctlr:08x}), yet the run went on")
    if status == 1 and (not sts1 & PCFG_DONE or sts1 & ERR_MASK):
        bad(f"the run reports done, but its final INT_STS {sts1:08x} has PCFG_DONE clear or an error bit set")

    # ---- every record, re-derived from its own raw words
    frames_known = {int(k, 16): v for k, v in known["frames"].items()}
    recs: list[dict] = []
    first_clean: dict[int, list[int]] = {}
    for i in range(n):
        r = words[HDR + i * REC: HDR + (i + 1) * REC]
        data = r[DATA_AT:DATA_AT + READ]
        rec = {"i": i, "far": r[0], "kind": r[1], "code": r[2], "sts": (r[3], r[5], r[7]), "polls": (r[4], r[6], r[8]),
               "survivors": r[9], "ref_equal": r[10], "repeat": r[12], "guard": r[13],
               "stream": r[STREAM_AT:STREAM_AT + 43], "cleanup": r[STREAM_AT + 43:DATA_AT],
               "pad": data[:FRAME], "frame": data[FRAME:], "data": data}
        recs.append(rec)
        far, code = rec["far"], rec["code"]
        if r[14] or r[15]:
            bad(f"record {i}: reserved words are not zero")
        if not lo <= far <= hi:
            bad(f"record {i}: frame address {far:#010x} outside the envelope")
        if rec["guard"] != 0 or code == 0x30:
            bad(f"record {i}: the prober's guard refused its own stream (guard word {rec['guard']:#x})")
        if rec["stream"] != pinned_stream(far):
            bad(f"record {i}: the readback stream is not the pinned one for {far:#010x}")
        if rec["cleanup"] != CLEANUP:
            bad(f"record {i}: the cleanup stream is not the pinned one")
        for name in ("stream", "cleanup"):
            for p in packets.readonly_problems(rec[name], lo, hi, READ):
                bad(f"record {i}: the {name} is not read-only: {p}")
        # the three commands, in order; a later one is only attempted after the earlier one succeeded
        derived = 0
        for k, name in enumerate(("command", "read", "cleanup")):
            if derived:
                if rec["sts"][k] or rec["polls"][k]:
                    bad(f"record {i}: the {name} transfer has a status although an earlier transfer failed")
                continue
            derived = _command_outcome(rec["sts"][k], rec["polls"][k], poll_limit)
            if derived < 0:
                bad(f"record {i}: the {name} transfer's status {rec['sts'][k]:08x} after {rec['polls'][k]} poll(s) is neither done, failed nor timed out")
                derived = 0xFF
            if rec["polls"][k] > poll_limit:
                bad(f"record {i}: {rec['polls'][k]} polls, above the limit {poll_limit}")
        survivors = sum(1 for w in data if w == SENTINEL)
        if survivors != rec["survivors"]:
            bad(f"record {i}: {survivors} sentinel word(s) in the data, the record says {rec['survivors']}")
        if derived == 0:                             # the interface was fine: now the data
            if survivors:
                derived = 0x10
            elif any(rec["pad"]):
                derived = 0x11
            elif rec["kind"] == 0 and far in first_clean and first_clean[far] != rec["frame"]:
                derived = 0x12
        if code != derived and not (code == 0x23 and derived in (0, 0x10, 0x11, 0x12)):   # 0x23 can also come from the check after the cleanup
            bad(f"record {i}: code {code:#x}, but its raw words say {derived:#x}")
        if code == 0:
            first_clean.setdefault(far, rec["frame"])
        digest = hashlib.sha256(b"".join(struct.pack(">I", w) for w in rec["frame"])).hexdigest()
        matches = None
        if far in frames_known:
            matches = digest == frames_known[far]["frame_sha256"]
            if code == 0 and not matches:
                diff = [k for k in range(FRAME) if rec["frame"][k] != int(frames_known[far]["words"][k], 16)]
                bad(f"record {i}: FAR {far:#010x} read cleanly but differs from the known frame in {len(diff)} word(s), first at {diff[0]}")
        elif code == 0:
            bad(f"record {i}: no known answer for FAR {far:#010x}")
        out["records"].append({"index": i, "far": f"{far:#010x}", "kind": KIND.get(rec["kind"], rec["kind"]), "code": f"{code:#x}",
                               "repeat": rec["repeat"], "int_sts": [f"{x:08x}" for x in rec["sts"]], "polls": list(rec["polls"]),
                               "survivors": survivors, "pad_all_zero": not any(rec["pad"]), "frame_sha256": digest, "matches_known": matches})

    # ---- the order of the records against the prober's schedule; what status that implies
    def healthy(rec: dict) -> bool:
        return rec["code"] == 0 and rec["frame"] == recs[0]["frame"]

    def expect(i: int, kind: int, far: int, repeat: int) -> dict | None:
        if i >= n:
            bad(f"the records end at {n}; a {KIND[kind]} read of {far:#010x} (repeat {repeat}) is missing")
            return None
        rec = recs[i]
        if (rec["kind"], rec["far"], rec["repeat"]) != (kind, far, repeat):
            bad(f"record {i}: expected the {KIND[kind]} read of {far:#010x} (repeat {repeat}), found a "
                f"{KIND.get(rec['kind'], rec['kind'])} read of {rec['far']:#010x} (repeat {rec['repeat']})")
        return rec

    implied: tuple[int, int, int] | None = None      # (status, anomalies, stop_record)
    i = count = 0
    rec = expect(0, 2, ref, 0)
    if rec is None:
        implied = (-1, 0, 0)
    elif rec["code"] != 0:
        implied = (0x600 | rec["code"], 0, 0); i = 1
    else:
        i = 1
        for r in range(repeats):
            for far in fars:
                rec = expect(i, 0, far, r)
                if rec is None:
                    implied = (-1, count, 0); break
                i += 1
                if rec["code"] == 0:
                    continue
                count += 1
                if rec["code"] >= 0x20:
                    implied = (0x200 | rec["code"], count, i - 1); break
                h = expect(i, 1, ref, r)
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
            f = expect(i, 3, ref, repeats)
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

    if status != 1:
        bad(f"the run did not complete: status {status:#x}")
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def main(argv: list[str]) -> int:
    raw = Path(argv[1]).read_bytes()
    if len(raw) % 4:                                 # never round a length down: stray bytes are not part of a result
        print(json.dumps({"verdict": "INVALID", "problems": [f"the file is {len(raw)} bytes, not a whole number of 32-bit words"]}, indent=1))
        return 1
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
    expected = json.loads(Path(argv[2] if len(argv) > 2 else ROOT / "build" / "prober" / "expected.json").read_text())
    result = judge(words, known, [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

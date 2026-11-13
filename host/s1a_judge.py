#!/usr/bin/env python3
"""Judge an S1a result buffer on the host: against the known frames, and every stream it says it sent
against the read-only policy. The board does not carry the known answer; this is where it is compared."""
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
KINDS = {0: "target", 1: "health", 2: "baseline", 3: "final"}


def judge(words: list[int], known: dict) -> dict:
    out: dict = {"problems": [], "records": []}
    bad = out["problems"].append
    if len(words) < HDR or words[0] != 0x31524D53 or words[1] != 1:
        bad("not an S1a result (magic or version)"); out["verdict"] = "INVALID"; return out
    status, n, anomalies, total, rec_words, hdr_words = words[2:8]
    out["header"] = {"status": f"{status:#x}", "records": n, "anomalies": anomalies, "total_words": total,
                     "ctrl": f"{words[8]:08x}", "mctrl": f"{words[9]:08x}", "int_sts_initial": f"{words[10]:08x}",
                     "status_initial": f"{words[11]:08x}", "sctlr": f"{words[12]:08x}", "cpsr": f"{words[13]:08x}",
                     "sp": f"{words[14]:08x}", "r9": f"{words[15]:08x}", "int_sts_final": f"{words[16]:08x}",
                     "status_final": f"{words[17]:08x}", "stop_record": f"{words[18]:#x}"}
    params = words[32:64]
    lo, hi, ref = params[3], params[4], params[5]
    out["params"] = {"far_lo": f"{lo:#010x}", "far_hi": f"{hi:#010x}", "ref_far": f"{ref:#010x}", "n_fars": params[6],
                     "repeats": params[7], "anomaly_budget": params[8], "poll_limit": params[9],
                     "fars": [f"{x:#010x}" for x in params[16:16 + min(params[6], 16)]]}
    if (rec_words, hdr_words) != (REC, HDR) or total != HDR + n * REC or len(words) < total:
        bad(f"sizes do not add up: total {total}, records {n}, have {len(words)} words"); out["verdict"] = "INVALID"; return out
    frames = {int(k, 16): v for k, v in known["frames"].items()}
    for i in range(n):
        r = words[HDR + i * REC: HDR + (i + 1) * REC]
        far, kind, code = r[0], r[1], r[2]
        frame = r[DATA_AT + 101:DATA_AT + 202]
        digest = hashlib.sha256(b"".join(struct.pack(">I", w) for w in frame)).hexdigest()
        rec = {"index": i, "far": f"{far:#010x}", "kind": KINDS.get(kind, kind), "code": f"{code:#x}", "repeat": r[12],
               "int_sts": [f"{r[3]:08x}", f"{r[5]:08x}", f"{r[7]:08x}"], "polls": [r[4], r[6], r[8]], "survivors": r[9],
               "pad_all_zero": not any(r[DATA_AT:DATA_AT + 101]), "frame_sha256": digest}
        for name, stream in (("readback", r[STREAM_AT:STREAM_AT + 43]), ("cleanup", r[STREAM_AT + 43:DATA_AT])):
            for p in packets.readonly_problems(stream, lo, hi, 202):
                bad(f"record {i}: the {name} stream is not read-only: {p}")
        if r[STREAM_AT + 8] != far:
            bad(f"record {i}: the stream addresses {r[STREAM_AT + 8]:#010x}, the record says {far:#010x}")
        if far in frames:
            rec["matches_known"] = digest == frames[far]["frame_sha256"]
            if code == 0 and not rec["matches_known"]:
                diff = [k for k in range(101) if frame[k] != int(frames[far]["words"][k], 16)]
                bad(f"record {i}: FAR {far:#010x} read cleanly but differs from the known frame in {len(diff)} word(s), first at {diff[0]}")
        else:
            rec["matches_known"] = None
        if code != 0:
            bad(f"record {i}: code {code:#x} ({rec['kind']} read of {far:#010x})")
        out["records"].append(rec)
    if status != 1:
        bad(f"the run did not complete: status {status:#x}")
    expected = 1 + params[6] * params[7] + 1
    if status == 1 and anomalies == 0 and n != expected:
        bad(f"{n} records where a clean run has {expected}")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def main(argv: list[str]) -> int:
    raw = Path(argv[1]).read_bytes()
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw[:len(raw) // 4 * 4]))
    known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
    result = judge(words, known)
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Judge a run of S1b.2b, the end of the row (docs/s1b_plan.md, section 29): the judge of the table-driven stage,
see s1b0_judge, for stage 5, with the one difference these runs need. They read at the last addresses of the row,
where no frame has a known answer; the judge of that stage holds a frame without a known answer against the run,
and here such frames are counted instead. Everything else is that judge unchanged: the records are the planned
ones, the streams the pinned ones, every repeat of a read is the first again (the same words, the same address
register), the reference frame is the known one, nothing overflowed.

What the address register held after each read is reported by that judge (far_after) and required of nothing but
to be the same every time. What it means is laid out by s1b2_end.py."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b0_judge  # noqa: E402
from s1b0_judge import ERR_MASK, HDR, MAX_RECORDS, PCFG_DONE, REC  # noqa: E402,F401

STAGE = 5


def judge(words: list[int], known: dict, planned: list[int]) -> dict:
    return s1b0_judge.judge(words, known, planned, stage=STAGE, unknown_frames_allowed=True)


def main(argv: list[str]) -> int:
    raw = Path(argv[1]).read_bytes()
    if len(raw) % 4:
        print(json.dumps({"verdict": "INVALID", "problems": [f"the file is {len(raw)} bytes, not a whole number of 32-bit words"]}, indent=1))
        return 1
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
    expected = json.loads(Path(argv[2]).read_text())
    result = judge(words, known, [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

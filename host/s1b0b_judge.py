#!/usr/bin/env python3
"""Judge a stage-3 (S1b.0b) result buffer: the stage-2 judge with the stage-3 operations and finding.
See s1b0_judge. The record layout is the same as stage 2; which stage a result belongs to is in the
parameter block it echoes, and a result of the other stage is INVALID here."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b0_judge  # noqa: E402
from s1b0_judge import ERR_MASK, HDR, MAX_RECORDS, PCFG_DONE, REC  # noqa: E402,F401

STAGE = 3


def judge(words: list[int], known: dict, planned: list[int]) -> dict:
    return s1b0_judge.judge(words, known, planned, stage=STAGE)


def main(argv: list[str]) -> int:
    raw = Path(argv[1]).read_bytes()
    if len(raw) % 4:
        print(json.dumps({"verdict": "INVALID", "problems": [f"the file is {len(raw)} bytes, not a whole number of 32-bit words"]}, indent=1))
        return 1
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    known = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
    expected = json.loads(Path(argv[2] if len(argv) > 2 else ROOT / "build" / "prober" / "expected_s1b0b.json").read_text())
    result = judge(words, known, [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

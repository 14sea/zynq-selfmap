#!/usr/bin/env python3
"""Judge a stage-5 (diagnostic) result buffer: the stage-3 judge with the two diagnostic options of stage 5.
See s1b0_judge. Stage 5 exists to find out why the walk overflows the receive FIFO where stages 2 and 3 do not;
its runs read frames that have no known answer, and the judge says so for each: what such a run is for is how far
the prober gets, and where on the stack its polling loop was writing when it did or did not get there."""
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
    return s1b0_judge.judge(words, known, planned, stage=STAGE)


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

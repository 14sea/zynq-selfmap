#!/usr/bin/env python3
"""Judge one run of the chain of S1b.2 (docs/s1b_plan.md, section 25): the judge of the walk, see s1b1_judge, with
the one difference a run of a chain needs. S1b.1's judge fails a walk that leaves the envelope without having
passed the known frames; a run of the chain that begins beyond them cannot pass them, and is not failed for it —
only for a known frame at or above its own start. Everything else is the walk's judge unchanged — including
that a known frame the walk went past without reading fails the run, however the pass ended (section 27)."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b1_judge  # noqa: E402
from s1b1_judge import END, ERR_MASK, HDR, MAX_RECORDS, PCFG_DONE, REC  # noqa: E402,F401


def judge(words: list[int], known: dict, planned: list[int]) -> dict:
    return s1b1_judge.judge(words, known, planned, run_of_a_chain=True)


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

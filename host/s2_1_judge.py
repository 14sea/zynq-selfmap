#!/usr/bin/env python3
"""Judge an S2.1 result buffer: s2_judge in its stage-7 form — user logic first, then the registers, the probe design loaded.
See s2_judge. Which stage a result belongs to is in the parameter block it echoes and in the size of its header;
a result of the other stage is INVALID here."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_judge  # noqa: E402
from s2_judge import ERR_MASK, MAX_RECORDS, PCFG_DONE, REC  # noqa: E402,F401

STAGE = 7
HDR = s2_judge.header_words(STAGE)
KNOWN = ROOT / "pl/s2a/design.json"


def judge(words: list[int], known: dict, planned: list[int]) -> dict:
    return s2_judge.judge(words, known, planned, stage=STAGE)


def main(argv: list[str]) -> int:
    words = s2_judge.load(Path(argv[1]))
    if words is None:
        print(json.dumps({"verdict": "INVALID", "problems": ["the file is not a whole number of 32-bit words"]}, indent=1))
        return 1
    expected = json.loads(Path(argv[2] if len(argv) > 2 else ROOT / "build" / "prober" / "expected_s2_1.json").read_text())
    result = judge(words, json.loads(KNOWN.read_text()), [int(w, 16) for w in expected["params"]])
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

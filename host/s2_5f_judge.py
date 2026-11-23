#!/usr/bin/env python3
"""Judge the result of part 1 of S2.5: s2_5_judge, with the layout that run's result has. See s2_5_judge.

The header of a stage-9 result is as long as the run's list of accesses makes it, so each kind of run of S2.5 has a
layout of its own; the run script knows a result by its layout, and this module says the one of part 1 —
the same for all eight shares, whose lists of accesses are one list."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_5_judge  # noqa: E402
from s2_5_judge import ERR_MASK, PCFG_DONE, REC, STAGE, judge  # noqa: E402,F401

KIND = "find"
HDR = s2_5_judge.layout_hdr(KIND)
MAX_RECORDS = (s2_5_judge.RESULT_MAX_WORDS - HDR) // REC

if __name__ == "__main__":
    sys.exit(s2_5_judge.main([sys.argv[0], sys.argv[1], KIND, sys.argv[2]] if len(sys.argv) == 3 else ["", "", ""]))

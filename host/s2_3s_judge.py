#!/usr/bin/env python3
"""Judge the result of a run of the singles of S2.3: s2_3_judge, with the layout such a run's result has. See
s2_3_judge and s2_3c_judge: every run of the singles has the same number of accesses, and so the same layout."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_3_judge  # noqa: E402
from s2_3_judge import ERR_MASK, PCFG_DONE, REC, STAGE, judge  # noqa: E402,F401

KIND = "singles"
HDR = s2_3_judge.layout_hdr(KIND)
MAX_RECORDS = (s2_3_judge.RESULT_MAX_WORDS - HDR) // REC

if __name__ == "__main__":
    sys.exit(s2_3_judge.main([sys.argv[0], sys.argv[1], KIND, sys.argv[2]] if len(sys.argv) == 3 else ["", "", ""]))

#!/usr/bin/env python3
"""S1b.4a: where the addresses of one run of the walk lie (docs/s1b_plan.md, section 46).

    s1b4a_layout.py <verdict.json of the run>

One run is not a list. This program takes the verdict as the run's judge wrote it and lays the walk out with the
program that lays out the rows of a chain (s1b3_rows: the addresses cut where the register stood still; of each
piece the block type, half and row; its columns by the column field, the frames of each, the minors) — as far as
the run went, and it says how the run ended. A run counts as having reached an end only if its judge passed it and
both passes ended because the device named an address outside the envelope.

It adds what the run saw of content: how many of the frames are not all zero, and how many different contents
there are — "the same frame twice" says nothing where every frame is alike.

If the judge did not pass the run, what its records hold is laid out all the same, with a note; that is not a
finding. There is no expected value in this program. Nothing is read from a board or a database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_row  # noqa: E402
import s1b3_rows  # noqa: E402
from s1b1_judge import END  # noqa: E402
from s1b3_top import ALL_ZERO  # noqa: E402

LEFT = END[1]                                        # the judge's words for a pass that ended beyond the envelope


def layout(verdict: dict) -> dict:
    out: dict = {"run": {"verdict": verdict.get("verdict"), "status": verdict.get("header", {}).get("status"), "problems": verdict.get("problems", [])}}
    if verdict.get("verdict") != "PASS":
        out["note"] = "the judge did not pass this run: what follows is laid out from its records all the same, and is not a finding"
    walk, passes = verdict.get("walk", []), verdict.get("passes", [])
    out["passes"] = passes
    out["frames"] = len(walk)
    if not walk:
        return out
    left = verdict.get("verdict") == "PASS" and bool(passes) and all(p["ended"] == LEFT for p in passes)
    chain = {"state": "complete" if left else "go on", "runs": [{"dir": "the run", "decision": "go on", "walk": walk}]}
    if left:
        chain["named_after_the_last_frame"] = passes[0]["last_address_named"]
    s = s1b3_rows.summarize(chain, {"frames": {}})
    out.update(first=walk[0]["far"], last=walk[-1]["far"], block_types=sorted({s1b2_row.fields(int(x["far"], 16))["block_type"] for x in walk}),
               rows=s["rows"], frames_per_row=s["frames_per_row"], standstills=s["standstills"], end=s["end"], unexpected=s["unexpected"])
    not_zero = sum(1 for x in walk if x["frame_sha256"] != ALL_ZERO)
    out["content"] = {"frames_not_all_zero": not_zero, "distinct_contents": len({x["frame_sha256"] for x in walk})}
    if not_zero == 0:
        out["content"]["note"] = "every frame delivered is all zero: that two reads of an address agree says nothing about which frame either read"
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__); return 2
    out = layout(json.loads(Path(argv[1]).read_text()))
    print(json.dumps(out, indent=1))
    return 0 if out["run"]["verdict"] == "PASS" and not out.get("unexpected") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

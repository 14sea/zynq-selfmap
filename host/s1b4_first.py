#!/usr/bin/env python3
"""S1b.4: a stored run held against the chain that walked the same addresses again (docs/s1b_plan.md, section 49).

    s1b4_first.py <rows.json of the chain> <verdict.json of the stored run>

The chain over block type 1 begins where the one run of S1b.4a began, so its first run reads that run's addresses a
second time. This program takes the chain's summary and the stored run's verdict as its judge wrote it and says, for
every address the stored run walked: is it in the chain's list, with the same frame, the same address named after
it, and the register having stood still there in both or in neither; and whether the chain's list, between the first
and the last of those addresses, is that run's list — none more, none fewer, in the same order.

It also says how many of those frames are not all zero and how many contents there are among them: where every
frame is alike, that the frames agree says nothing about which frame either read.

There is no expected value in this program. A disagreement is listed and the exit code is 1; it alters neither.
Nothing is read from a board or a database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from s1b3_top import ALL_ZERO  # noqa: E402


def against(rows: dict, verdict: dict) -> dict:
    out: dict = {"chain": rows.get("chain", {}).get("state"),
                 "stored_run": {"verdict": verdict.get("verdict"), "status": verdict.get("header", {}).get("status")}, "disagreements": []}
    odd = out["disagreements"].append
    if verdict.get("verdict") != "PASS":
        odd("the stored run is not one its judge passed")
    theirs = verdict.get("walk", [])
    if not theirs:
        odd("the stored run walked nothing"); return out
    mine = rows.get("addresses", [])
    here = {s["far"]: s for s in mine}
    shared = [(here[t["far"]], t) for t in theirs if t["far"] in here]
    missing = [t["far"] for t in theirs if t["far"] not in here]
    if missing:
        odd(f"{len(missing)} address(es) of the stored run are not in the chain's list; the first is {missing[0]}")
    for s, t in shared:
        if s["frame_sha256"] != t["frame_sha256"]:
            odd(f"the frame at {t['far']}: the chain has {s['frame_sha256'][:12]}…, the stored run {t['frame_sha256'][:12]}…")
        if s["next"] != t["next"]:
            odd(f"after {t['far']} the chain was told {s['next']}, the stored run {t['next']}")
        if bool(s.get("stood_still")) != bool(t.get("stood_still")):
            odd(f"at {t['far']} the register stood still in one of the two and not in the other")
    first, last = int(theirs[0]["far"], 16), int(theirs[-1]["far"], 16)
    between = [s["far"] for s in mine if first <= int(s["far"], 16) <= last]
    if between != [t["far"] for t in theirs]:
        odd(f"between {theirs[0]['far']} and {theirs[-1]['far']} the chain lists {len(between)} address(es), the stored run {len(theirs)}, or not in the same order")
    out.update(addresses_of_the_stored_run=len(theirs), of_which_in_the_chain=len(shared),
               same_frames=sum(1 for s, t in shared if s["frame_sha256"] == t["frame_sha256"]),
               same_address_named=sum(1 for s, t in shared if s["next"] == t["next"]),
               frames_not_all_zero=sum(1 for _, t in shared if t["frame_sha256"] != ALL_ZERO),
               distinct_contents=len({t["frame_sha256"] for _, t in shared}))
    if out["distinct_contents"] <= 1 and shared:
        out["note_on_content"] = "every frame the two share is the same content: that they agree on it says nothing about which frame either read"
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    out = against(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(json.dumps(out, indent=1))
    return 1 if out["disagreements"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

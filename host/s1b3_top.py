#!/usr/bin/env python3
"""S1b.3: the first row of the chain over block type 0, held against the row stored before (section 38).

    s1b3_top.py <rows.json of the chain> <row_closed.json>

The chain of S1b.3 walks the first row again, on another day and with another image. This program takes its summary
(s1b3_rows.py) and the stored summary of that row (S1b.2's chain as closed by S1b.2b) and says: are they the same
addresses in the same order; is every frame the same; did the device name the same address after each; do the
columns have the same numbers of frames. At the last frame the two differ in form — the stored row has the address
naming itself and, beside it, the address the register showed afterwards; the chain stood still there and went on —
and have to agree in substance.

It also says how many of the frames compared are not all zero and how many contents there are among them: where
every frame is the same, their agreement says nothing about which frame was read.

No expected value. A difference is listed and the exit code is 1; it alters neither summary. No board, no database.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FRAME_WORDS = 101
ALL_ZERO = hashlib.sha256(bytes(4 * FRAME_WORDS)).hexdigest()


def against(rows: dict, stored: dict) -> dict:
    out: dict = {"chain": rows.get("chain", {}).get("state"), "disagreements": []}
    odd = out["disagreements"].append
    theirs = stored.get("addresses", [])
    end = stored.get("end", {})
    if not rows.get("rows") or not theirs:
        odd("one of the two summaries lists no row"); return out
    first = rows["rows"][0]
    mine = rows["addresses"][:first["frames"]]
    out["row"] = {k: first[k] for k in ("block_type", "half", "row", "frames", "first", "last", "walked_whole", "ended_by")}
    out["stored_frames"] = len(theirs)
    if not first["walked_whole"]:
        odd(f"the chain did not walk its first row whole: {first['frames']} frame(s), {first['ended_by']}")
    a, b = [s["far"] for s in mine], [s["far"] for s in theirs]
    if a != b:
        k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        odd(f"the addresses differ: the chain's row has {len(a)}, the stored row {len(b)}; the first place they differ is {k} "
            f"({a[k] if k < len(a) else 'none'} against {b[k] if k < len(b) else 'none'})")
    same = named = 0
    for s, t in zip(mine, theirs):
        if s["far"] != t["far"]:
            break
        if s["frame_sha256"] == t["frame_sha256"]:
            same += 1
        else:
            odd(f"the frame at {s['far']}: the chain delivered {s['frame_sha256'][:12]}…, the stored row has {t['frame_sha256'][:12]}…")
        if s["far"] == end.get("last_frame"):            # the end of the stored row: there it names itself; the chain has to have stood still and gone on
            if not s.get("stood_still"):
                odd(f"the stored row ends at {s['far']} with the register standing still; the chain did not stand still there (it names {s['next']})")
            elif s["next"] != end.get("named_after_the_last_frame"):
                odd(f"after the standstill at {s['far']} the chain went on to {s['next']}; the stored row has {end.get('named_after_the_last_frame')} named after it")
            else:
                named += 1
        elif s["next"] != t["next"]:
            odd(f"after {s['far']} the chain was told {s['next']}, the stored row has {t['next']}")
        elif s.get("stood_still"):
            odd(f"the chain stood still at {s['far']}, where the stored row has no end")
        else:
            named += 1
    shared = [t for s, t in zip(mine, theirs) if s["far"] == t["far"]]
    out.update(addresses_in_both=len(shared), same_frames=same, same_address_named=named,
               frames_not_all_zero=sum(1 for t in shared if t["frame_sha256"] != ALL_ZERO),
               distinct_contents=len({t["frame_sha256"] for t in shared}))
    if first["frames_per_column"] != stored.get("frames_per_column"):
        odd("the columns do not have the same numbers of frames in the two summaries")
    else:
        out["columns"] = len(first["frames_per_column"])
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    out = against(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(json.dumps(out, indent=1))
    return 1 if out["disagreements"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

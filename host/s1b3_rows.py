#!/usr/bin/env python3
"""S1b.3: what a chain of runs over block type 0 says about its rows (docs/s1b_plan.md, section 38).

    s1b3_rows.py <chain directory> [<set>]        prints the summary as JSON; the set is s1b3 if none is named

Every stored run of the chain is taken from its files and judged again (s1b2_chain.assess, with that set); from
the runs that passed, the addresses the device named are put in order. The list is cut into rows where the register
stood still — the device's own mark of the end of a row (sections 31 and 37) — and each row is described by the
program that described the row of S1b.2 (s1b2_row: the columns by the column field of the address word, the frames
of each, whether the minors are 0, 1, 2, ..., whether minor 0 of the next column was named after each).

Of every row it says: the block type, half and row fields of its first address; whether it was walked whole (the
register stood still after its last frame, or the chain left the envelope there); the address named after it.
Listed as unexpected, as found: a row whose addresses do not all share those fields (s1b2_row says so column by
column); a standstill after which the address named lies in the same row; two rows with the same fields.

This program knows the layout of the address word (UG470) and nothing about any part: no number of rows, columns or
frames. It reads no database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_chain  # noqa: E402
import s1b2_row  # noqa: E402

STAGE = "s1b3"


def summarize(assessment: dict, known: dict) -> dict:
    out: dict = {"chain": {"state": assessment["state"], "runs": len(assessment["runs"]),
                           "runs_that_passed": [r["dir"] for r in assessment["runs"] if r["decision"] != "halt"]}}
    if assessment["state"] == "halted":
        out["chain"]["why"] = assessment["why"]
    complete = assessment["state"] == "complete"
    seq: list[dict] = []
    for r in assessment["runs"]:
        if r["decision"] == "halt":                      # a run that did not pass adds nothing
            break
        seq += [dict(s, run=r["dir"]) for s in r["walk"][(1 if seq else 0):]]     # the seam frame once: it is the one before
    out["frames"] = len(seq)
    out["addresses"] = seq
    out["unexpected"] = []
    odd = out["unexpected"].append
    if any(int(b["far"], 16) <= int(a["far"], 16) for a, b in zip(seq, seq[1:])):
        odd("the addresses are not in rising order")
    if any(a["next"] != b["far"] for a, b in zip(seq, seq[1:])):
        odd("an address in the list is not the one named after the address before it")

    # ---- the rows: the list cut after every frame at which the register stood still
    pieces: list[tuple[list[dict], bool]] = []
    cur: list[dict] = []
    for s in seq:
        cur.append(s)
        if s.get("stood_still"):
            pieces.append((cur, True)); cur = []
    if cur:
        pieces.append((cur, False))
    rows: list[dict] = []
    seen: dict[tuple, int] = {}
    for k, (steps, stood) in enumerate(pieces):
        whole = stood or (complete and k == len(pieces) - 1)
        named = steps[-1]["next"]
        described = s1b2_row.summarize({"state": "complete" if whole else "go on", "named_after_the_last_frame": named,
                                        "runs": [{"dir": "-", "decision": "go on", "walk": steps}]}, {"frames": {}})
        first, last = int(steps[0]["far"], 16), int(steps[-1]["far"], 16)
        place = s1b2_row.place(first)[:3]
        row = {"index": k, "block_type": place[0], "half": place[1], "row": place[2], "frames": len(steps), "first": steps[0]["far"], "last": steps[-1]["far"],
               "walked_whole": whole,
               "ended_by": "the register stood still" if stood else "the device named an address beyond the envelope" if whole else "not ended",
               "named_after_the_last_frame": named if whole else None,
               "columns": described["columns"], "frames_per_column": described["frames_per_column"], "unexpected": described["unexpected"]}
        where = f"row {k} ({row['first']}..{row['last']})"
        if stood and s1b2_row.place(int(named, 16))[:3] == s1b2_row.place(last)[:3]:
            row["unexpected"].append(f"the register stood still after {row['last']}, yet the address named then, {named}, has the block type, half and row of that frame")
        if place in seen:
            row["unexpected"].append(f"the block type, half and row of this row are those of row {seen[place]}")
        seen.setdefault(place, k)
        for u in row["unexpected"]:
            odd(f"{where}: {u}")
        rows.append(row)
    out["rows"] = rows
    out["frames_per_row"] = [[r["block_type"], r["half"], r["row"], r["frames"]] for r in rows]
    out["standstills"] = [{"after": r["last"], "named": r["named_after_the_last_frame"]} for r in rows if r["ended_by"] == "the register stood still"]

    # ---- the end
    if complete:
        named = int(assessment["named_after_the_last_frame"], 16)
        out["end"] = {"reached": True, "last_frame": seq[-1]["far"], "named_after_the_last_frame": f"{named:#010x}", "that_address": s1b2_row.fields(named),
                      "after_a_standstill": bool(seq[-1].get("stood_still"))}
    else:
        out["end"] = {"reached": False, "last_frame_walked": seq[-1]["far"] if seq else None,
                      "note": "the envelope was not left: the last row listed may go on, and what follows it is not known"}

    # ---- the frames with a known answer (each read of them was held against it by the judge of its run)
    known_addresses = sorted(int(k, 16) for k in known["frames"])
    walked = {int(s["far"], 16) for s in seq}
    out["known_frames_walked"] = [f"{a:#010x}" for a in known_addresses if a in walked]
    out["known_frames_not_walked"] = [f"{a:#010x}" for a in known_addresses if a not in walked]
    return out


def main(argv: list[str]) -> int:
    import s1a_run
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] not in s1b2_chain.BOUNDS):
        print(__doc__); return 2
    root, stage = Path(argv[1]), argv[2] if len(argv) == 3 else STAGE
    stored = root / f"expected_{stage}.json"             # the set as it was when the chain was run, if it was kept with the runs
    base = [int(w, 16) for w in json.loads((stored if stored.exists() else s1a_run.STAGES[stage]["expected"]).read_text())["params"]]
    known = json.loads(s1a_run.KNOWN.read_text())
    print(json.dumps(summarize(s1b2_chain.assess(root, base, known, s1b2_chain.BOUNDS[stage], stage), known), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

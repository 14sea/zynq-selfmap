#!/usr/bin/env python3
"""After the fact: compare what the chain of S1b.3 found in block type 0 with prjxray-db's description of the part.

Like grade_s1b2.py, which it uses for every row: not part of any judge, never run before the chain's runs and its
summary are saved, judged and committed. It reads the summary over rows (s1b3_rows.py) and the database's part.json.
A disagreement is a finding, not a failure of the chain: the database is one more witness, not the answer.

    grade_s1b3.py <rows.json> [<part.json>]

Compared: each row, by the grader of a row as it is (the columns and the frames of each; the address named after the
row against the first frame of the row next in the database's order); the rows walked against the database's rows of
that block type in its own order (the top half's rows, then the bottom half's); and, if the chain left the envelope,
the frames in all and the address named after the last frame against the first frame of the next block type in the
database. The database lists frames; it does not say what a device names after a row or a block type — those
comparisons are offered as such. That the register stood still at the end of a row is listed as not compared.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import grade_s1b2  # noqa: E402

DEFAULT_DB = grade_s1b2.DEFAULT_DB


def as_row(rows: dict, r: dict) -> dict:
    """One row of the summary in the form the grader of a row takes."""
    return {"chain": rows.get("chain", {}), "columns": r["columns"], "unexpected": r["unexpected"],
            "end": {"reached": r["walked_whole"], "named_after_the_last_frame": r["named_after_the_last_frame"]}}


def grade(rows: dict, part: dict) -> dict:
    out: dict = {"chain": rows.get("chain", {}).get("state"), "agrees": [], "differs": [], "not_compared": [], "rows": []}
    walked = rows.get("rows", [])
    if not walked:
        out["not_compared"].append("the summary lists no row"); return out
    for r in walked:
        g = grade_s1b2.grade(as_row(rows, r), part)
        name = f"row {r['index']} (block type {r['block_type']}, {r['half']} half, row {r['row']})"
        out["rows"].append({"row": name, "frames": r["frames"], "walked_whole": r["walked_whole"], "agrees": g["agrees"], "differs": g["differs"],
                            "not_compared": g["not_compared"], "columns": g["columns"]})
        out["differs"] += [f"{name}: {d}" for d in g["differs"]]
    if not any(r["differs"] for r in out["rows"]):
        out["agrees"].append(f"nothing differs within any of the {len(walked)} row(s) walked")

    # ---- the rows, in the database's order: the top half's, then the bottom half's
    block = walked[0]["block_type"]
    bus = grade_s1b2.BUS.get(block)
    regions = part.get("global_clock_regions", {})
    theirs = [(block, half, int(k)) for half in ("top", "bottom")
              for k in sorted(regions.get(half, {}).get("rows", {}), key=int) if bus in regions[half]["rows"][k].get("configuration_buses", {})]
    mine = [(r["block_type"], r["half"], r["row"]) for r in walked]
    reached = bool(rows.get("end", {}).get("reached"))
    expected = theirs if reached else theirs[:len(mine)]
    (out["agrees"] if mine == expected else out["differs"]).append(
        (f"the rows walked are the database's {'rows' if reached else 'first ' + str(len(mine)) + ' row(s)'} of block type {block}, in its order" if mine == expected
         else f"the rows walked are {mine}; the database's {'rows' if reached else 'first ' + str(len(mine))} of block type {block} are {expected}"))
    stood = [s["after"] for s in rows.get("standstills", [])]
    if stood:
        out["not_compared"].append(f"the register stood still after the last frame of {len(stood)} row(s) ({', '.join(stood)}): "
                                   "the database lists frames and has nothing to hold that against")
    if not reached:
        out["not_compared"].append(f"the chain did not leave the envelope: the database's {len(theirs) - len([r for r in walked if r['walked_whole']])} "
                                   "further row(s), the frames in all and what follows the block type were not compared")
        return out
    total = sum(r["frames"] for r in walked)
    there = sum(c["frame_count"] for _, half, k in theirs for c in regions[half]["rows"][str(k)]["configuration_buses"][bus]["configuration_columns"].values())
    (out["agrees"] if total == there else out["differs"]).append(f"frames of block type {block}: the chain found {total}, the database's columns add up to {there}")

    # ---- what follows the block type
    named = int(rows["end"]["named_after_the_last_frame"], 16)
    after = grade_s1b2.BUS.get(block + 1)
    first = next(((half, int(k)) for half in ("top", "bottom") for k in sorted(regions.get(half, {}).get("rows", {}), key=int)
                  if after in regions[half]["rows"][k].get("configuration_buses", {})), None)
    if first is None:
        out["not_compared"].append(f"the address named after the last frame is {named:#010x}; the database lists no block type after this one")
        return out
    nxt = grade_s1b2.address(block + 1, first[0], first[1], 0, 0)
    (out["agrees"] if named == nxt else out["differs"]).append(
        f"the address named after the last frame of block type {block} is {named:#010x}; the first frame of block type {block + 1} "
        f"in the database's order ({first[0]} half, row {first[1]}) is {nxt:#010x}")
    return out


def main(argv: list[str]) -> int:
    rows = json.loads(Path(argv[1]).read_text())
    part = json.loads(Path(argv[2] if len(argv) > 2 else DEFAULT_DB).read_text())
    result = grade(rows, part)
    print(json.dumps(result, indent=1))
    return 0 if not result["differs"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

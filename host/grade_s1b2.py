#!/usr/bin/env python3
"""After the fact: compare what the chain of S1b.2 found along the row with prjxray-db's description of the part.

Like grade_s1b1.py: not part of any judge, never run before the runs are saved, judged and committed. It reads the
row summary (s1b2_row.py: the columns the device's own addresses fall into, and their frame counts) and the
database's part.json, and says where they agree and where they do not. A disagreement is a finding, not a failure
of the walk: the database is one more witness, not the answer.

    grade_s1b2.py <row.json> [<part.json>]

Compared: the columns of the row and the number of frames in each; and, if the chain left the row, the address the
device named after the last frame against the first frame of the row that comes next in the database's own order
(the next row of the same half; after the last row of the top half, row 0 of the bottom half). The database lists
frames; it does not say what a device names after a row — that last comparison is offered as such.

A summary closed by a later step (s1b2_closed.py, section 32) is graded like any other; the grade says that it was,
and lists what such a summary records about the end of the row that the database has nothing to say about.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_DB = Path("/home/test/prjxray-db/zynq7/xc7z010clg400-1/part.json")
BUS = {0: "CLB_IO_CLK", 1: "BLOCK_RAM"}


def address(block_type: int, half: str, row: int, column: int, minor: int) -> int:
    return block_type << 23 | (1 if half == "bottom" else 0) << 22 | row << 17 | column << 7 | minor


def grade(row: dict, part: dict) -> dict:
    out: dict = {"chain": row.get("chain", {}).get("state"), "agrees": [], "differs": [], "not_compared": [], "columns": []}
    if "closed" in row:                                  # a summary closed by a later step says so, and so does its grade
        out["summary_closed_by"] = row["closed"].get("by")
    walked = row.get("columns", [])
    if not walked:
        out["not_compared"].append("the summary lists no column"); return out
    if row.get("unexpected"):
        out["not_compared"].append(f"the summary lists {len(row['unexpected'])} thing(s) as unexpected; they are the summary's to report, and are not graded here")
    first = walked[0]
    where = {k: first[k] for k in ("block_type", "half", "row")}
    out["row_walked"] = where
    if any({k: c[k] for k in where} != where for c in walked):
        out["differs"].append("the columns walked are not all in one block type, half and row")
    try:
        rows = part["global_clock_regions"][first["half"]]["rows"]
        theirs = {int(c): v["frame_count"] for c, v in rows[str(first["row"])]["configuration_buses"][BUS[first["block_type"]]]["configuration_columns"].items()}
    except KeyError as e:
        out["not_compared"].append(f"the database has no entry for this row ({e})"); return out
    reached = bool(row.get("end", {}).get("reached"))

    # ---- column by column: only a column the device went on from (or left the row after) has a length to compare
    whole = [c for c in walked if c["walked_whole"]]
    ok = True
    for c in walked:
        entry = {"column": c["column"], "walked": c["frames"], "database": theirs.get(c["column"]), "walked_whole": c["walked_whole"]}
        out["columns"].append(entry)
        if not c["walked_whole"]:
            (out["agrees"] if entry["database"] is not None and c["frames"] <= entry["database"] else out["differs"]).append(
                f"column {c['column']}: the chain stopped in it after {c['frames']} frame(s); the database gives it {entry['database']}")
        elif entry["database"] != c["frames"]:
            ok = False
            out["differs"].append(f"column {c['column']}: the walk found {c['frames']} frame(s), the database says {entry['database']}")
    if whole and ok:
        out["agrees"].append(f"each of the {len(whole)} column(s) walked whole has the number of frames the database gives it")
    numbers = [c["column"] for c in walked]
    expected = sorted(theirs)[:len(numbers)] if not reached else sorted(theirs)
    (out["agrees"] if numbers == expected else out["differs"]).append(
        (f"the columns walked are the database's columns {numbers[0]}..{numbers[-1]} of this row, in order" if numbers == expected
         else f"the columns walked are {numbers}; the database's {'columns of this row' if reached else 'first ' + str(len(numbers))} are {expected}"))
    if not reached:
        out["not_compared"].append(f"the chain did not leave the row: the database's {len(theirs) - len(whole)} further column(s) and what follows the row were not compared")
        return out
    total = sum(c["frames"] for c in walked)
    (out["agrees"] if total == sum(theirs.values()) else out["differs"]).append(f"frames in the row: the walk found {total}, the database's columns add up to {sum(theirs.values())}")

    still = row["end"].get("the_register_stood_still")
    if still:
        out["not_compared"].append(f"the register stood still at step(s) {still.get('at_steps_beyond_the_last_frame')} beyond the last frame of the row: "
                                   "the database lists frames and has nothing to hold that against")
    beyond = row["end"].get("frames_delivered_from_beyond_the_last_frame")
    if beyond:
        out["not_compared"].append(f"{len(beyond)} frame(s) were delivered from beyond the last frame of the row: they are not graded")

    # ---- what follows the row
    named = int(row["end"]["named_after_the_last_frame"], 16)
    if str(first["row"] + 1) in rows:
        nxt, what = address(first["block_type"], first["half"], first["row"] + 1, 0, 0), f"row {first['row'] + 1} of the {first['half']} half"
    elif first["half"] == "top" and "0" in part["global_clock_regions"].get("bottom", {}).get("rows", {}):
        nxt, what = address(first["block_type"], "bottom", 0, 0, 0), "row 0 of the bottom half (this is the last row of the top half in the database)"
    else:
        out["not_compared"].append(f"the address named after the last frame is {named:#010x}; the database has no row after this one in its order")
        return out
    (out["agrees"] if named == nxt else out["differs"]).append(
        f"the address named after the last frame of the row is {named:#010x}; the first frame of the row next in the database's order, {what}, is {nxt:#010x}")
    return out


def main(argv: list[str]) -> int:
    row = json.loads(Path(argv[1]).read_text())
    part = json.loads(Path(argv[2] if len(argv) > 2 else DEFAULT_DB).read_text())
    result = grade(row, part)
    print(json.dumps(result, indent=1))
    return 0 if not result["differs"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

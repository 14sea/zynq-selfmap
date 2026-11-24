#!/usr/bin/env python3
"""After the fact: compare what a walk found with prjxray-db's description of the part.

This is not part of the judge and is never run before a result is saved and judged. The prober and the
judge know no frame count and no column layout; this program is where an outside description is first
looked at. It reads the judge's verdict (the list of addresses the device named) and the database's
part.json, and says where they agree and where they do not. A disagreement is a finding, not a failure
of the walk: the database is one more witness, not the answer.

    grade_s1b1.py <verdict.json> [<part.json>]

The address fields are those of UG470 (7-series): block type [25:23], half [22] (0 top, 1 bottom),
row [21:17], column [16:7], minor [6:0].
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# The database is no part of this repository: by default a checkout of prjxray-db beside it; another file is named as the second argument.
DEFAULT_DB = Path(__file__).resolve().parents[2] / "prjxray-db" / "zynq7" / "xc7z010clg400-1" / "part.json"
BUS = {0: "CLB_IO_CLK", 1: "BLOCK_RAM"}


def fields(far: int) -> dict:
    return {"block_type": (far >> 23) & 7, "half": "bottom" if (far >> 22) & 1 else "top", "row": (far >> 17) & 0x1F,
            "column": (far >> 7) & 0x3FF, "minor": far & 0x7F}


def address(block_type: int, half: str, row: int, column: int, minor: int) -> int:
    return block_type << 23 | (1 if half == "bottom" else 0) << 22 | row << 17 | column << 7 | minor


LEFT, LIMIT = "the device named an address outside the envelope", "the limit of frames was reached"


def grade(verdict: dict, part: dict) -> dict:
    """What can be compared depends on how far the walk got. Only a pass that the device itself ended — by naming an
    address outside the envelope — says how long the column is and what follows it. A walk that stopped at its limit,
    or was stopped by an anomaly, has walked a beginning of the column: its addresses are compared, its length is
    only held against the database as "not more than", and the last address it was told is not an end of anything."""
    out: dict = {"judge_verdict": verdict.get("verdict"), "agrees": [], "differs": [], "not_compared": []}
    if verdict.get("verdict") != "PASS":
        out["not_compared"].append(f"the judge's verdict is {verdict.get('verdict')}: what follows compares what was walked, as far as it goes, "
                                   "and is not a statement about the column")
    walk = [int(s["far"], 16) for s in verdict.get("walk", [])]
    if not walk:
        out["not_compared"].append("the verdict has no walk"); return out
    first = fields(walk[0])
    out["column_walked"] = {k: first[k] for k in ("block_type", "half", "row", "column")}
    same_column = all({k: v for k, v in fields(a).items() if k != "minor"} == {k: v for k, v in first.items() if k != "minor"} for a in walk)
    minors = [fields(a)["minor"] for a in walk]
    (out["agrees"] if same_column and minors == list(range(len(walk))) else out["differs"]).append(
        f"the {len(walk)} addresses walked are minors 0..{len(walk) - 1} of one column" if same_column and minors == list(range(len(walk)))
        else f"the addresses walked are not minors 0.. of one column (minors {minors[:6]}…, one column: {same_column})")
    try:
        columns = part["global_clock_regions"][first["half"]]["rows"][str(first["row"])]["configuration_buses"][BUS[first["block_type"]]]["configuration_columns"]
        frames = columns[str(first["column"])]["frame_count"]
    except KeyError as e:
        out["not_compared"].append(f"the database has no entry for this column ({e})"); return out
    out["database_frame_count"] = frames
    ended = verdict["passes"][0]["ended"] if verdict.get("passes") else ""
    out["walk_ended"] = ended
    if ended != LEFT:                                # the limit, or a stop: a beginning of the column, not the column
        why = "stopped at its limit" if ended == LIMIT else "did not finish"
        (out["agrees"] if len(walk) <= frames else out["differs"]).append(
            f"the walk {why} after {len(walk)} frames; the database gives the column {frames}")
        out["not_compared"].append(f"the walk {why}: neither the length of the column nor what follows it was compared")
        return out
    (out["agrees"] if len(walk) == frames else out["differs"]).append(f"frames in the column: the walk found {len(walk)}, the database says {frames}")
    named = int(verdict["passes"][0]["last_address_named"], 16)
    if str(first["column"] + 1) in columns:
        want = address(first["block_type"], first["half"], first["row"], first["column"] + 1, 0)
        (out["agrees"] if named == want else out["differs"]).append(
            f"the address named after the last frame is {named:#010x}; minor 0 of the next column in the database is {want:#010x}")
    else:
        out["not_compared"].append(f"the address named after the last frame is {named:#010x}; this is the last column of its row in the database, "
                                   "which does not say what follows a row")
    return out


def main(argv: list[str]) -> int:
    verdict = json.loads(Path(argv[1]).read_text())
    part = json.loads(Path(argv[2] if len(argv) > 2 else DEFAULT_DB).read_text())
    result = grade(verdict, part)
    print(json.dumps(result, indent=1))
    return 0 if not result["differs"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

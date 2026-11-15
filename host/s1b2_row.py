#!/usr/bin/env python3
"""S1b.2: what a chain of runs says about the row (docs/s1b_plan.md, section 25).

    s1b2_row.py <chain directory> [<verdict.json of S1b.1>]        prints the summary as JSON

Every stored run of the chain is taken from its files and judged again (s1b2_chain.assess); from the runs that
passed, the addresses the device named are put in order and described:

  - the list of addresses, each with the address named after it and the hash of its frame;
  - the addresses grouped by the column field of the address word: how many frames each column has, whether their
    minors are 0, 1, 2, ... and whether the address named after the last is minor 0 of the column numbered one higher;
  - the column S1b.1 walked, held against that walk;
  - which frames with a known answer were walked;
  - what the device named after the last frame, if the chain got that far.

This program knows the layout of the address word (UG470: block type [25:23], half [22], row [21:17], column [16:7],
minor [6:0]) and nothing about any part: no number of columns, no number of frames. A column whose shape is not the
one just described is listed under "unexpected" as it was found; it is not an error of the chain, which follows what
the device names.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_chain  # noqa: E402


def fields(far: int) -> dict:
    return {"block_type": (far >> 23) & 7, "half": "bottom" if (far >> 22) & 1 else "top", "row": (far >> 17) & 0x1F,
            "column": (far >> 7) & 0x3FF, "minor": far & 0x7F}


def place(far: int) -> tuple:
    """Everything of an address but its minor: which column of which row."""
    f = fields(far)
    return f["block_type"], f["half"], f["row"], f["column"]


def summarize(assessment: dict, known: dict, s1b1_verdict: dict | None = None) -> dict:
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

    # ---- the columns: the addresses that share everything but the minor, as they come
    columns: list[dict] = []
    for s in seq:
        far = int(s["far"], 16)
        if not columns or columns[-1]["_place"] != place(far):
            columns.append({"_place": place(far), **{k: v for k, v in fields(far).items() if k != "minor"}, "frames": 0, "first": s["far"], "minors": []})
        c = columns[-1]
        c["frames"] += 1; c["last"] = s["far"]; c["named_after_the_last"] = s["next"]; c["minors"].append(far & 0x7F)
    for i, c in enumerate(columns):
        last_of_all = i == len(columns) - 1
        c["walked_whole"] = complete or not last_of_all  # the device went on to another column, or left the row
        c["minors_are_0_to_n_minus_1"] = c["minors"] == list(range(c["frames"]))
        named = int(c["named_after_the_last"], 16)
        c["next_is_minor_0_of_the_column_numbered_one_higher"] = place(named) == (*c["_place"][:3], c["_place"][3] + 1) and named & 0x7F == 0
        where = f"column {c['column']} ({c['first']}..{c['last']})"
        if not c["minors_are_0_to_n_minus_1"]:
            odd(f"{where}: the minors walked are {c['minors'] if c['frames'] <= 8 else str(c['minors'][:8]) + '…'}, not 0..{c['frames'] - 1}")
        if c["walked_whole"] and not c["next_is_minor_0_of_the_column_numbered_one_higher"] and not (complete and last_of_all):
            odd(f"{where}: after its last frame the device named {c['named_after_the_last']}, not minor 0 of column {c['column'] + 1}")
        if i and c["_place"][:3] != columns[i - 1]["_place"][:3]:
            odd(f"{where}: not in the block type, half and row of the column before it")
    for c in columns:                                    # the working fields are not part of the summary
        del c["minors"], c["_place"]
    out["columns"] = columns
    out["frames_per_column"] = [[c["column"], c["frames"]] for c in columns]

    # ---- the end
    if complete:
        named = int(assessment["named_after_the_last_frame"], 16)
        out["end"] = {"reached": True, "last_frame": seq[-1]["far"], "named_after_the_last_frame": f"{named:#010x}", "that_address": fields(named)}
    else:
        out["end"] = {"reached": False, "last_frame_walked": seq[-1]["far"] if seq else None,
                      "note": "the row was not left: the last column listed may go on, and what follows the row is not known"}

    # ---- held against S1b.1's walk of its column
    if s1b1_verdict is not None:
        here = {s["far"]: s for s in seq}
        theirs = s1b1_verdict.get("walk", [])
        covered = [t for t in theirs if t["far"] in here]
        out["column_of_s1b1"] = {
            "frames_there": len(theirs), "of_which_walked_here": len(covered),
            "same_frames": all(here[t["far"]]["frame_sha256"] == t["frame_sha256"] for t in covered),
            "same_addresses_named": all(here[t["far"]]["next"] == t["next"] for t in covered),
            # the addresses walked here in that column are exactly the ones walked there: none more, none fewer
            "the_same_column": bool(theirs) and [s["far"] for s in seq if place(int(s["far"], 16)) == place(int(theirs[0]["far"], 16))] == [t["far"] for t in theirs]}

    # ---- the frames with a known answer (each read of them was held against it by the judge of its run)
    known_addresses = sorted(int(k, 16) for k in known["frames"])
    walked = {int(s["far"], 16) for s in seq}
    out["known_frames_walked"] = [f"{a:#010x}" for a in known_addresses if a in walked]
    out["known_frames_not_walked"] = [f"{a:#010x}" for a in known_addresses if a not in walked]
    return out


def main(argv: list[str]) -> int:
    import s1a_run
    root = Path(argv[1])
    stored = root / "expected_s1b2.json"                 # the set as it was when the chain was run, if it was kept with the runs
    base = [int(w, 16) for w in json.loads((stored if stored.exists() else s1a_run.STAGES["s1b2"]["expected"]).read_text())["params"]]
    known = json.loads(s1a_run.KNOWN.read_text())
    s1b1 = json.loads(Path(argv[2]).read_text()) if len(argv) > 2 else None
    print(json.dumps(summarize(s1b2_chain.assess(root, base, known), known, s1b1), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""The row of S1b.2 as closed by the two runs at its end (docs/s1b_plan.md, section 32).

    s1b2_closed.py <row.json> <verdict.json of the run the chain stopped on> <verdict.json of s1b2c> <verdict.json of s1b2e>

The chain of S1b.2 halted in the last column of its row: the prober stopped at an address that names itself, and the
chain accepts no run that did not complete. Its summary (s1b2_row.py) therefore ends with a column cut short and a row
not left. Two further runs were made at that place (section 29). This program writes, from those stored results and
nothing else, what the device says the whole row is, in the form of the chain's summary — or says why it does not.

The rules (fixed in section 32 before any database was opened):

  1. The walk the chain did not accept contributes its addresses only if
       a. its only fault is the stop at an address that names itself;
       b. it began at the last frame of the last accepted run — the same address, the same frame, the same address
          named after it;
       c. the second path (s1b2c) read every one of its addresses again with the same frame, and the register after
          each of those reads was what the walk's successors say wherever they reach.
  2. The last address of the row is the address at which the pad alone leaves the register where it is — in the walk
     and in s1b2e, every repeat; and s1b2e's starting addresses follow one another as the walk says they do.
  3. The address named after the row is the first value other than that address which the register shows as further
     frames of words are clocked from it, every read that ends there agreeing; it has to lie outside the row. The
     number of steps the register stood still before it is recorded.
  4. The columns the chain walked whole are taken as they are: the summary made of the longer list has to give them
     again unchanged.
  5. If any of this is not so, no closed summary is written: the output is {"refused": [...]} and the exit code 1.

The chain's state stays what it was (halted); the summary says of itself that it was closed and from what. There is
no number of frames or columns in this program, and it reads no database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_end  # noqa: E402
import s1b2_row  # noqa: E402

STOPPED = "0x800"                                    # the prober's status: the device named an address that is not above the one asked about
THE_RUN = "the run the chain stopped on"


def close(row: dict, walk: dict, again: dict, at_the_end: dict) -> dict:
    if row.get("chain", {}).get("state") != "halted" or row.get("end", {}).get("reached") or not row.get("addresses") or not row.get("columns"):
        return {"refused": ["the summary is not that of a halted chain that did not leave its row: there is nothing to close"]}
    steps = walk.get("walk", [])
    if not steps:
        return {"refused": ["the run the chain stopped on walked nothing"]}
    last = steps[-1]["far"]
    rules: dict = {}
    refused: list[str] = []

    def rule(name: str, holds: bool, why: str) -> None:
        rules[name] = bool(holds)
        if not holds:
            refused.append(f"rule {name}: {why}")

    # ---- 1a: the walk's only fault is the stop at an address that names itself
    def of_the_stop(p: str) -> bool:
        return p.startswith(f"the run did not complete: status {STOPPED}") or (
            p.startswith(f"after the frame at {last} the register held ") and p.endswith(f"but the device names {last} after {last}"))
    header = walk.get("header", {})
    rule("1a", header.get("status") == STOPPED and header.get("anomalies") == 0 and steps[-1]["next"] == last
         and all(a["next"] == b["far"] for a, b in zip(steps, steps[1:])) and all(of_the_stop(p) for p in walk.get("problems", [])),
         "the walk was not stopped at an address that names itself and for nothing else")
    # ---- 1b: it began at the last frame of the last accepted run
    seam = row["addresses"][-1]
    rule("1b", all(steps[0].get(k) == seam.get(k) for k in ("far", "next", "frame_sha256")),
         "the walk does not begin with the last frame of the last accepted run, as that run had it")
    # ---- 1c: every frame of it read again by the second path
    col = s1b2_end.column(again, walk, at_the_end)
    rule("1c", col["run"]["verdict"] == "PASS" and not col["disagreements"] and not col["addresses_of_the_walk_not_read_again"]
         and not col["frames_at_places_the_walk_did_not_reach"] and col["frames_compared"] == col["same"] == len(steps),
         "the second path did not pass, or did not read every frame of the walk again as the walk had it")
    # ---- 2: the last address of the row
    end = s1b2_end.end(at_the_end)
    walked = {s["far"]: s["next"] for s in steps}
    starts = end.get("starting_addresses", [])
    alone = [r["register_afterwards"] for r in end.get("reads", []) if r["at"] == last and r["steps"] == 1]
    rule("2", end["run"]["verdict"] == "PASS" and not end["disagreements"] and end.get("starting_addresses_one_step_apart") is True
         and end.get("beyond", {}).get("last_address_written") == last and alone == [[last]]
         and all(walked.get(a) == b for a, b in zip(starts, starts[1:])),
         "the run at the end did not pass, or does not show the walk's last address as the one at which the pad alone leaves the register standing")
    # ---- 3: the address named after the row
    stood, named = 0, None
    for k, s in enumerate(end.get("beyond", {}).get("register_step_by_step", [])):
        if s["steps_beyond"] != k + 1:
            break
        if s["register"] == last:
            stood += 1; continue
        named = s["register"] if isinstance(s["register"], str) else None
        break
    outside = named is not None and s1b2_row.place(int(named, 16))[:3] != s1b2_row.place(int(last, 16))[:3]
    rule("3", stood >= 1 and outside, "the register was not seen to stand still and then to show an address outside the row")
    if refused:
        return {"refused": refused, "rules": rules}

    # ---- the longer list, and the summary made of it by the program that made the chain's
    addresses = row["addresses"] + [{"far": s["far"], "next": s["next"], "frame_sha256": s["frame_sha256"], "run": THE_RUN} for s in steps[1:]]
    made = s1b2_row.summarize({"state": "complete", "named_after_the_last_frame": named,
                               "runs": [{"dir": THE_RUN, "decision": "go on", "walk": addresses}]}, {"frames": {}})
    before = len(row["columns"]) - 1
    cut_short = row["columns"][before]
    rule("4", made["columns"][:before] == row["columns"][:before] and len(made["columns"]) > before
         and all(made["columns"][before][k] == cut_short[k] for k in ("block_type", "half", "row", "column", "first")),
         "the columns the chain walked whole do not come out of the longer list as they were")
    if refused:
        return {"refused": refused, "rules": rules}

    out = dict(row)
    out.update(frames=len(addresses), addresses=addresses, unexpected=made["unexpected"], columns=made["columns"], frames_per_column=made["frames_per_column"])
    beyond = end["beyond"]
    out["end"] = dict(made["end"],
                      the_register_stood_still={"steps_before_that_address": stood, "at_steps_beyond_the_last_frame": beyond["steps_at_which_the_register_did_not_change"],
                                                "register_step_by_step": beyond["register_step_by_step"]},
                      frames_delivered_from_beyond_the_last_frame=[{"steps_beyond": f["steps_beyond"], "all_zero": f["all_zero"]} for f in beyond["frames_delivered_from_beyond"]],
                      note="the chain did not leave the row: this address is the first the register showed other than the last frame's own, "
                           "as further frames of words were clocked from it in the run at the end of the row")
    out["closed"] = {"by": "the two runs at the end of the row (S1b.2b); the chain itself halted and is not altered",
                     "rules": rules, "frames_added": len(steps) - 1, "added_from": THE_RUN + ", every frame of it read again by a second path",
                     "frames_read_again": col["frames_compared"], "of_which_the_same": col["same"], "distinct_contents_among_them": col["distinct_contents"],
                     "chain_summary_frames": row["frames"]}
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(__doc__); return 2
    out = close(*(json.loads(Path(a).read_text()) for a in argv[1:5]))
    print(json.dumps(out, indent=1))
    return 1 if "refused" in out else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

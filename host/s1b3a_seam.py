#!/usr/bin/env python3
"""S1b.3a: the run across the end of the row, held against what is stored of that row (docs/s1b_plan.md, section 35).

    s1b3a_seam.py <verdict.json of the run> <row_closed.json>

The run begins at an address the stored row already has and walks on beyond the row. This program takes the run's
verdict as its judge wrote it and the stored summary of the row (the chain's, as closed by S1b.2b) and says, for
every address the two share: is the frame the same, and did the device name the same address after it. At the last
frame of the stored row the two are expected to differ in form and to agree in substance: the stored row has that
address naming itself, and beside it the address the register showed one step later; the run must have stood still
there and gone on to that address. The registers of the standstill are held against the ones stored, step by step.

Addresses the run walked that the stored row does not have are counted and listed by their first and last; nothing
is known of them here and nothing is required of them.

There is no expected value in this program. A disagreement is listed and the exit code is 1; it does not alter the
run. Nothing is read from a board or a database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def against(verdict: dict, row: dict) -> dict:
    out: dict = {"run": {"verdict": verdict.get("verdict"), "status": verdict.get("header", {}).get("status"), "problems": verdict.get("problems", [])},
                 "disagreements": []}
    odd = out["disagreements"].append
    if verdict.get("verdict") != "PASS":
        out["note"] = "the judge did not pass this run: what follows is laid out from its records all the same, and is not a finding"
    stored = {s["far"]: s for s in row.get("addresses", [])}
    end = row.get("end", {})
    last, named = end.get("last_frame"), end.get("named_after_the_last_frame")
    walk = verdict.get("walk", [])
    if not walk:
        odd("the run walked nothing"); return out
    out["begins_at"] = walk[0]["far"]
    if walk[0]["far"] not in stored:
        odd(f"the run begins at {walk[0]['far']}, which the stored row does not have: there is no seam")
    shared = same = 0
    new: list[dict] = []
    for s in walk:
        t = stored.get(s["far"])
        if t is None:
            new.append(s); continue
        shared += 1
        if s["frame_sha256"] == t["frame_sha256"]:
            same += 1
        else:
            odd(f"the frame at {s['far']}: the run delivered {s['frame_sha256'][:12]}…, the stored row has {t['frame_sha256'][:12]}…")
        if s["far"] == last:                             # the end of the stored row: it names itself there; the run has to have crossed
            if not s.get("stood_still"):
                odd(f"the stored row ends at {last} with the register standing still; the run did not stand still there (it names {s['next']})")
            elif s["next"] != named:
                odd(f"after the standstill at {last} the run went on to {s['next']}; the stored row has {named} named after it")
        elif s["next"] != t["next"]:
            odd(f"after {s['far']} the run was told {s['next']}, the stored row has {t['next']}")
        elif s.get("stood_still"):
            odd(f"the run stood still at {s['far']}, where the stored row has no end")
    out.update(addresses_in_both=shared, same_frames=same, distinct_contents_among_them=len({s["frame_sha256"] for s in walk if s["far"] in stored}))
    if out["distinct_contents_among_them"] <= 1 and shared:
        out["note_on_content"] = "every frame the two share is the same content: that they agree on it says nothing about which frame either read"
    # ---- the standstill, register by register
    there = [x for x in verdict.get("standstills", []) if x["at"] == last]
    steps = {x["steps_beyond"]: x["register"] for x in end.get("the_register_stood_still", {}).get("register_step_by_step", [])}
    if last in {s["far"] for s in walk}:
        if len(there) != 1:
            odd(f"the run's judge lists {len(there)} standstill(s) at {last}")
        else:
            out["standstill"] = {"at": last, "after_the_pad_alone": there[0]["register_after_the_pad_alone"], "stored_one_step_beyond": steps.get(1),
                                 "after_the_frame": there[0]["register_after_the_frame"], "stored_two_steps_beyond": steps.get(2)}
            if there[0]["register_after_the_pad_alone"] != steps.get(1):
                odd(f"after the pad alone at {last} the register read {there[0]['register_after_the_pad_alone']}; one step beyond, the stored row has {steps.get(1)}")
            if there[0]["register_after_the_frame"] != steps.get(2):
                odd(f"after the frame at {last} the register read {there[0]['register_after_the_frame']}; two steps beyond, the stored row has {steps.get(2)}")
    else:
        out["note_on_the_end"] = "the run did not reach the last frame of the stored row"
    # ---- what the run has that the stored row has not
    out["addresses_the_stored_row_does_not_have"] = {"count": len(new), "first": new[0]["far"] if new else None, "last": new[-1]["far"] if new else None,
                                                     "standstills_among_them": [s["far"] for s in new if s.get("stood_still")]}
    if new and walk.index(new[0]) and walk[walk.index(new[0]) - 1]["far"] != last:
        odd(f"the first address the stored row does not have, {new[0]['far']}, does not follow the last frame of the stored row")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    out = against(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(json.dumps(out, indent=1))
    return 1 if out["disagreements"] or out["run"]["verdict"] != "PASS" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

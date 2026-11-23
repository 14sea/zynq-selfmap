#!/usr/bin/env python3
"""S2.4, part 2: the table — which bit of configuration memory is which output of the design's shift registers
(docs/s2_plan.md, sections 37 to 41).

    s2_4_table.py <verdict.json> <candidates.json>       close the code run whose verdict this is; prints the closing

Three things, each from verdicts the judge wrote and from nothing else.

  * `close_code`: the code run closed into a table. The judge says of every bit that changed which cell it follows,
    and which way. Here it is asked whether that is a table, by point 6 of section 38 as the owner changed it:
    **every candidate of part 1 follows exactly one cell, as it is or inverted — the way part 1 saw it follow the
    uniform states — and no other bit follows one; and every cell has at least one bit that follows it as it is.** If
    so the table is given, at confidence 1: for each cell its places and which way each shows it. A cell may have
    several places; how many of which kind the cells have is said beside the table. If not there is no table, and the
    singles are not run. What a place follows is what it follows over the states made by shifts (s2_4_judge): a
    place that reads otherwise before any shift than its cell's loaded content gives is in the table all the same,
    and is named beside it.
  * `hold_singles`: a run of the singles held to the table. In the state in which cell n alone is the other way,
    the bits that differ from the loaded content are those that follow n in the judge's words: they must be exactly
    the places the table has for n, every one of them, each shown the same way. A cell for which that is so is
    confirmed (confidence 2); one for which it is not is a contradiction.
  * `srl_map`: the description written out (schemas/srl_map_v1.schema.json), closed-book: an entry for each place
    with its cell, which way it shows it, its confidence, and the records it rests on.

A cell is output a of register k, as the design's address register chooses it (s2_4_states). Nothing here knows which
stage of a primitive that is, where a place lies, or which LUT a register is. What the build of the design said of
where it put each register is copied beside the table, marked as the build's word.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_4_states as st  # noqa: E402
from s2_3_table import CONFIDENCE, place, records_of  # noqa: E402,F401


def shape(n_as_it_is: int, n_inverted: int) -> str:
    return f"{n_as_it_is} as it is, {n_inverted} inverted"


def close_code(verdict: dict, candidates: dict) -> dict:
    """The code run's verdict closed into the table, or the reasons why there is none. `candidates`: what part 1
    found, as its chain wrote it."""
    out: dict = {"problems": [], "cells": st.CELLS, "table": None}
    bad = out["problems"].append
    if verdict.get("verdict") != "PASS":
        bad("the code run is not a passing run")
    if (verdict.get("run") or {}).get("kind") != "code":
        bad("the verdict is not of the code run")
    if out["problems"]:
        out["outcome"] = "no table: there is no passing code run to close"
        return out
    follows = verdict["finding"]["follows"]
    by_cell: dict[int, list[dict]] = {}
    for x in follows:
        by_cell.setdefault(x["cell"], []).append(x)
    found = {place(x): x["inverted"] for x in follows}
    before = {place(x): x["inverted"] for x in candidates["places"]}
    new = sorted(p for p in found if p not in before)
    lost = sorted(p for p in before if p not in found)
    turned = sorted(p for p in found if p in before and found[p] != before[p])
    none = [n for n in range(st.CELLS) if not any(not x["inverted"] for x in by_cell.get(n, []))]
    shapes: dict[str, list[int]] = {}
    for n in range(st.CELLS):
        its = by_cell.get(n, [])
        shapes.setdefault(shape(sum(1 for x in its if not x["inverted"]), sum(1 for x in its if x["inverted"])), []).append(n)
    out.update(bits_that_follow=len(follows), as_they_are=sum(1 for x in follows if not x["inverted"]), inverted=sum(1 for x in follows if x["inverted"]),
               cells_by_their_places={k: len(v) for k, v in sorted(shapes.items())},
               cells_without_a_bit_as_it_is=none, places_part_1_did_not_have=[list(p) for p in new],
               candidates_of_part_1_that_follow_no_cell=[list(p) for p in lost], places_shown_the_other_way_than_in_part_1=[list(p) for p in turned],
               candidates_of_part_1=len(before), bit_5_after_records=(verdict.get("bit_5") or {}).get("shown_after_records", []),
               places_that_read_otherwise_as_loaded=[{k: x[k] for k in ("far", "word", "bit", "cell", "inverted", "state", "reads", "the_cell_gives")}
                                                     for x in verdict["finding"].get("otherwise_as_loaded", [])])
    if len(found) != len(follows):
        bad("a place is said to follow two cells")
    if none:
        bad(f"{len(none)} cell(s) have no bit that follows them as it is")
    if new:
        bad(f"{len(new)} bit(s) follow a cell at a place part 1 did not find")
    if lost:
        bad(f"{len(lost)} candidate(s) of part 1 follow no cell")
    if turned:
        bad(f"{len(turned)} place(s) follow a cell the other way than they followed the uniform states in part 1")
    if out["problems"]:
        out["outcome"] = "11: a candidate that follows no cell, a cell without a bit as it is, or a place not as part 1 has it — no table"
        return out
    out["table"] = [{"cell": n, "register": n // st.DEPTH, "output": n % st.DEPTH,
                     "places": [{"far": x["far"], "word": x["word"], "bit": x["bit"], "inverted": x["inverted"]}
                                for x in sorted(by_cell[n], key=lambda x: (x["inverted"], place(x)))]} for n in range(st.CELLS)]
    out["shapes"] = {k: v for k, v in sorted(shapes.items())}
    out["outcome"] = ("10: every candidate of part 1 follows exactly one cell, as it is or inverted, and every cell has a bit as it is — "
                      + "; ".join(f"{len(v)} cell(s) with {k}" for k, v in sorted(shapes.items())))
    return out


def hold_singles(verdict: dict, table: list[dict]) -> dict:
    """A passing run of the singles held to the table: which of its cells are confirmed, and the contradictions."""
    out: dict = {"problems": [], "confirmed": [], "contradictions": []}
    bad = out["problems"].append
    run = verdict.get("run") or {}
    if verdict.get("verdict") != "PASS" or run.get("kind") != "singles":
        bad("not a passing run of the singles"); return out
    cells = range(st.SINGLES_A_RUN * run["share"], st.SINGLES_A_RUN * (run["share"] + 1))
    want = {row["cell"]: {(p["far"], p["word"], p["bit"]): p["inverted"] for p in row["places"]} for row in table}
    if sorted(want) != list(range(st.CELLS)):
        bad("the table is not one of every cell"); return out
    by_cell: dict[int, dict] = {}
    for x in verdict["finding"]["follows"]:
        by_cell.setdefault(x["cell"], {})[place(x)] = x["inverted"]
    for n in sorted(set(by_cell) - set(cells)):
        bad(f"a bit follows cell {n}, which is not a cell of this run")
    for n in cells:
        got = by_cell.get(n, {})
        if got == want[n]:
            out["confirmed"].append(n)
            continue
        out["contradictions"].append({"cell": n, "the_table_has": [[*p, inv] for p, inv in sorted(want[n].items())],
                                      "the_single_shows": [[*p, inv] for p, inv in sorted(got.items())]})
        bad(f"cell {n}: its single changes {len(got)} bit(s), the table has {len(want[n])} place(s) for it, and they are not the same places shown the same way")
    return out


def srl_map(design: dict, table: list[dict], code: dict, singles: list[dict], otherwise: list[dict] | None = None) -> dict:
    """The description. `code`: {"dir", "result_sha256", "reads", "states"} of the code run; `singles`: the same for
    each run of the singles that was made, with "share" and what `hold_singles` said of it ("held"); `otherwise`: the
    places that read otherwise before any shift than their cell's loaded content gives, as the closing of the code run
    has them. An entry rests on the states that were made by shifts and on no other (review of 07abf08: the state
    before any shift was named as evidence for a place that reads otherwise in it); what such a place read before any
    shift is said in the entry, beside its evidence and not as part of it."""
    confirmed = {n: s for s in singles for n in s["held"]["confirmed"]}
    refuted = {c["cell"]: s for s in singles for c in s["held"]["contradictions"]}
    apart = {(x["far"], x["word"], x["bit"]): x for x in otherwise or []}
    entries = []
    for row in table:
        n = row["cell"]
        holds_one = [i for i, state in enumerate(code["states"]) if state["shifted"] and st.cell(state["srl"], n)]   # the shifted states of the code run in which the cell held a one
        state = "contradiction" if n in refuted else "confirmed" if n in confirmed else "decoded"
        by = confirmed.get(n) or refuted.get(n)
        for p in row["places"]:
            far = int(p["far"], 16)
            single = None
            if by is not None:
                at = next(i for i, x in enumerate(by["states"]) if x.get("cell") == n)
                single = {"run": by["dir"], "state": at, "record": records_of(far, by["reads"], [at])[0]}
            entries.append({"address": f"{p['far']}/{p['word']}/{p['bit']}", "cell": n, "register": row["register"], "output": row["output"],
                            "inverted": p["inverted"], "confidence": CONFIDENCE[state], "state": state,
                            "observed_transition": {"output_0": int(p["inverted"]), "output_1": 1 - int(p["inverted"])},
                            "evidence": {"code_states": holds_one, "code_records": records_of(far, code["reads"], holds_one), "single": single}})
            x = apart.get((p["far"], p["word"], p["bit"]))
            if x is not None:
                entries[-1]["before_any_shift"] = {"state": x["state"], "record": records_of(far, code["reads"], [x["state"]])[0], "reads": x["reads"],
                                                   "the_output_as_loaded_would_give": x["the_cell_gives"]}
    doc = {"schema": "srl_map", "schema_version": 1, "label": "closed-book",
           "what": "which bit of configuration memory is which output of the probe design's shift registers, found by shifting known contents in "
                   "through user logic and reading configuration memory back (docs/s2_plan.md, sections 37 to 41). An address is the frame address "
                   "the device named, a word of the frame read there (0 the first) and a bit of that word (0 the least significant). A cell may "
                   "have several places; a place that is inverted reads the opposite of what the output holds.",
           "design": design["name"],
           "numbering": "cell = 32 x register + output. register: which bit of the design's data register shifts into it (0 to 3). output: what the "
                        "design's address register chooses (0 to 31): the bit shifted in output + 1 shifts ago. Which stage of a primitive an "
                        "output is, and which LUT of a slice a register is, is not shown by this.",
           "cells": st.CELLS,
           "confidence": {"0": "contradiction: with that cell alone the other way, the bits that changed are not the places decoded for it",
                          "1": "decoded from the code states only",
                          "2": "confirmed: with that cell alone the other way, exactly the places decoded for it read otherwise than with the loaded content"},
           "runs": {"code": {"dir": code["dir"], "result_sha256": code["result_sha256"]},
                    "singles": [{"dir": s["dir"], "share": s["share"], "result_sha256": s["result_sha256"]} for s in singles]},
           "counts": {state: sum(1 for e in entries if e["state"] == state) for state in ("confirmed", "decoded", "contradiction")},
           "places": len(entries), "places_that_read_otherwise_before_any_shift": sum(1 for e in entries if "before_any_shift" in e), "entries": entries}
    cells = design["srl"]["cells"]
    if all("bel" in cells[k] for k in cells):
        doc["as_the_build_placed_them"] = {
            "what": "the design's own record of where the build put each register (pl/s2a/design.json): what was placed, not something the device showed",
            "site": design["srl"]["site"], "registers": {k: cells[k]["bel"] for k in sorted(cells)}}
    return doc


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    closing = close_code(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(json.dumps({k: v for k, v in closing.items() if k not in ("table", "shapes")}, indent=1))
    return 0 if closing["table"] is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

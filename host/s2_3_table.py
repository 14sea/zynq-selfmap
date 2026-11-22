#!/usr/bin/env python3
"""S2.3: the table — which bit of configuration memory is which cell of the RAM (docs/s2_plan.md, section 29).

    s2_3_table.py <verdict.json> <candidates.json>       close the code run whose verdict this is; prints the closing

Three things, each from verdicts the judge wrote and from nothing else.

  * `close_code`: the code run closed into a table. The judge says of every bit that changed which cell it follows;
    here it is asked whether that is a table: **every cell of the RAM has exactly one bit, and the bits are exactly
    the places S2.2 found** — each shown the way S2.2 saw it, as written or inverted. If so the table is given, at
    confidence 1: decoded from the code states and nothing else. If not there is no table, and the singles are not
    run.
  * `hold_singles`: a run of the singles held to the table. In the state in which cell n alone is set, the bits that
    differ from the base are those that follow n in the judge's words: there must be exactly one, and it must be the
    place the table has for n, shown the same way. A cell for which that is so is confirmed (confidence 2); one for
    which it is not is a contradiction.
  * `ram_map`: the description written out (schemas/ram_map_v1.schema.json), closed-book: an entry for each cell
    with its place, its confidence, and the records it rests on.

Nothing here knows where a cell lies, what an address word means, or which LUT a memory is. What the build of the
design said of where it put each memory is copied beside the table, marked as the build's word.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_3_states as st  # noqa: E402

CONFIDENCE = {"contradiction": 0, "decoded": 1, "confirmed": 2}     # the copied schema's words for them (schemas/self_map_v2.schema.json)


def place(x: dict) -> tuple[str, int, int]:
    return (x["far"], x["word"], x["bit"])


def close_code(verdict: dict, candidates: dict) -> dict:
    """The code run's verdict closed into the table, or the reasons why there is none. `candidates`: what S2.2 found,
    as its chain wrote it."""
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
    none = [n for n in range(st.CELLS) if n not in by_cell]
    several = sorted(n for n, where in by_cell.items() if len(where) > 1)
    found = {place(x): x["inverted"] for x in follows}
    before = {place(x): x["inverted"] for x in candidates["places"]}
    new = sorted(p for p in found if p not in before)
    lost = sorted(p for p in before if p not in found)
    turned = sorted(p for p in found if p in before and found[p] != before[p])
    out.update(bits_that_follow=len(follows), cells_with_one_bit=sum(1 for where in by_cell.values() if len(where) == 1),
               cells_with_no_bit=none, cells_with_several_bits=several, inverted=sum(1 for x in follows if x["inverted"]),
               places_s2_2_did_not_have=[list(p) for p in new], places_of_s2_2_that_follow_no_cell=[list(p) for p in lost],
               places_shown_the_other_way_than_in_s2_2=[list(p) for p in turned], candidates_of_s2_2=len(before),
               bit_5_after_records=(verdict.get("bit_5") or {}).get("shown_after_records", []))
    if none:
        bad(f"{len(none)} cell(s) of the RAM have no bit that follows them")
    if several:
        bad(f"{len(several)} cell(s) of the RAM are followed by more than one bit")
    if new:
        bad(f"{len(new)} bit(s) follow a cell at a place S2.2 did not find")
    if lost:
        bad(f"{len(lost)} place(s) S2.2 found follow no cell")
    if turned:
        bad(f"{len(turned)} place(s) are shown the other way than S2.2 saw them")
    if out["problems"]:
        out["outcome"] = ("2: a cell has no bit, or more than one" if none or several else "4: what follows a cell is not what S2.2 found") + " — no table"
        return out
    out["table"] = [{"cell": n, "memory": n // st.DEPTH, "address": n % st.DEPTH, "far": x["far"], "word": x["word"], "bit": x["bit"], "inverted": x["inverted"]}
                    for n, (x,) in sorted(by_cell.items())]
    out["outcome"] = "1: every cell of the RAM has exactly one bit, and the bits are the places S2.2 found; every other bit of the column is still"
    return out


def hold_singles(verdict: dict, table: list[dict]) -> dict:
    """A passing run of the singles held to the table: which of its cells are confirmed, and the contradictions."""
    out: dict = {"problems": [], "confirmed": [], "contradictions": []}
    bad = out["problems"].append
    run = verdict.get("run") or {}
    if verdict.get("verdict") != "PASS" or run.get("kind") != "singles":
        bad("not a passing run of the singles"); return out
    cells = range(st.SINGLES_A_RUN * run["share"], st.SINGLES_A_RUN * (run["share"] + 1))
    want = {row["cell"]: row for row in table}
    if sorted(want) != list(range(st.CELLS)):
        bad("the table is not one of every cell"); return out
    by_cell: dict[int, list[dict]] = {}
    for x in verdict["finding"]["follows"]:
        by_cell.setdefault(x["cell"], []).append(x)
    for n in sorted(set(by_cell) - set(cells)):
        bad(f"a bit follows cell {n}, which is not a cell of this run")
    for n in cells:
        got = by_cell.get(n, [])
        row = want[n]
        if len(got) == 1 and place(got[0]) == place(row) and got[0]["inverted"] == row["inverted"]:
            out["confirmed"].append(n)
            continue
        out["contradictions"].append({"cell": n, "the_table_has": [row["far"], row["word"], row["bit"]],
                                      "the_single_shows": [[x["far"], x["word"], x["bit"]] for x in got]})
        bad(f"cell {n}: its single changes {len(got)} bit(s)" + ("" if not got else ", not the one the table has" if len(got) == 1 else "")
            + f"; the table has {row['far']} word {row['word']} bit {row['bit']}")
    return out


def records_of(place_far: int, reads: list[tuple[int, int]], states: list[int]) -> list[int]:
    """The records of a run in which a frame was read, for the given states: record 2 + state x reads + the read that
    delivers the frame (the reference frame and CTL0 come first)."""
    k = next(i for i, (far, n) in enumerate(reads) if far <= place_far < far + n)
    return [2 + s * len(reads) + k for s in states]


def ram_map(design: dict, table: list[dict], code: dict, singles: list[dict], build: dict | None = None) -> dict:
    """The description. `code`: {"dir", "result_sha256", "reads", "states"} of the code run; `singles`: the same for
    each run of the singles that was made, with "share" and what `hold_singles` said of it ("held")."""
    confirmed = {n: s for s in singles for n in s["held"]["confirmed"]}
    refuted = {c["cell"]: s for s in singles for c in s["held"]["contradictions"]}
    entries = []
    for row in table:
        n = row["cell"]
        far = int(row["far"], 16)
        lit = [i for i, state in enumerate(code["states"]) if st.cell(state["ram"], n)]   # the states of the code run in which the cell was set
        state = "contradiction" if n in refuted else "confirmed" if n in confirmed else "decoded"
        by = confirmed.get(n) or refuted.get(n)
        single = None
        if by is not None:
            at = next(i for i, x in enumerate(by["states"]) if x.get("cell") == n)
            single = {"run": by["dir"], "state": at, "record": records_of(far, by["reads"], [at])[0]}
        entries.append({"address": f"{row['far']}/{row['word']}/{row['bit']}", "cell": n, "memory": row["memory"], "ram_address": row["address"],
                        "inverted": row["inverted"], "confidence": CONFIDENCE[state], "state": state,
                        "observed_transition": {"base": int(row["inverted"]), "set": 1 - int(row["inverted"])},
                        "evidence": {"code_states": lit, "code_records": records_of(far, code["reads"], lit), "single": single}})
    doc = {"schema": "ram_map", "schema_version": 1, "label": "closed-book",
           "what": "which bit of configuration memory is which cell of the probe design's LUT RAM, found by setting the RAM through user "
                   "logic and reading configuration memory back (docs/s2_plan.md, section 29). An address is the frame address the device "
                   "named, a word of the frame read there (0 the first) and a bit of that word (0 the least significant).",
           "design": design["name"],
           "numbering": "cell = 64 x memory + ram_address. memory: which bit of the design's data register writes it (0 to 3). ram_address: "
                        "what the design's address register held (0 to 63). Which LUT of a slice a memory is, and which pin carries which "
                        "address bit, is not shown by this.",
           "cells": st.CELLS,
           "confidence": {"0": "contradiction: the single did not change the decoded place and no other", "1": "decoded from the code states only",
                          "2": "confirmed: with that cell alone set, the decoded place and no other bit read differs from the base"},
           "runs": {"code": {"dir": code["dir"], "result_sha256": code["result_sha256"]},
                    "singles": [{"dir": s["dir"], "share": s["share"], "result_sha256": s["result_sha256"]} for s in singles]},
           "counts": {state: sum(1 for e in entries if e["state"] == state) for state in ("confirmed", "decoded", "contradiction")},
           "entries": entries}
    if build is not None:
        cells = design["ram"]["cells"]
        doc["as_the_build_placed_them"] = {
            "what": "the build's own record of where it put each memory (pl/s2a/build.json): what was placed, not something the device showed",
            "site": design["ram"]["site"],
            "memories": {k: build["memory_primitives"][cells[k]["cell"]]["bel"] for k in sorted(cells)}}
    return doc


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    closing = close_code(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
    print(json.dumps({k: v for k, v in closing.items() if k != "table"}, indent=1))
    return 0 if closing["table"] is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

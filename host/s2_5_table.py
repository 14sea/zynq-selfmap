#!/usr/bin/env python3
"""S2.5, part 2: the tables — at every site of the design s2b, which bit of configuration memory is which cell
(docs/s2_plan.md, sections 45 and 46).

    s2_5_table.py <verdict.json> <candidates.json>       close the code run whose verdict this is; prints the closing

Three things, each from verdicts the judge wrote, from what part 1's chain wrote, and from nothing else.

  * `close_code`: the code run closed into a table for every site. Two things are known of a place, each found
    without the other. Part 1 says **whose memory it is**: the word a memory was loaded with was found in the frames
    read before anything was written, at the place the six moves give — memory k of site s, address a. The code run
    says **which cell it follows**: over states written to every site at once, a number of 256. Here they are held
    against each other, site by site: every bit that follows a cell is a candidate of part 1 and follows the way part
    1 saw; every candidate follows a cell; and at every site each of the 256 cells has exactly one bit, which is the
    place of the memory and the address that cell's number says (cell 64 k + a: memory k, address a). A site of which
    that holds has its table, at confidence 1. If it does not hold of every site, the closing says of which and why,
    and no single is run.
  * `hold_singles`: a run of the singles held to the tables. In the state in which cell n is one at every site and
    every other cell zero, the bits that differ from the base are those that follow n in the judge's words: they must
    be exactly the places the tables have for n, one at every site, each shown the same way. A cell of which that is
    so is confirmed at every site (confidence 2); otherwise it is a contradiction.
  * `ram_map`: the description written out (schemas/ram_map_v2.schema.json), closed-book: an entry for each place
    with its site, its cell, which way it shows it and its confidence. What an entry rests on is said once for each
    cell — the states of the code run in which it was one, the state of the singles in which it alone was — since
    every site was written alike; the record of a run in which a place's frame was read in a state is
    2 + state x reads + the read that delivers the frame, with the reads given.

A site here is the design's number for it; its name is the design's own record of where the build placed the
memories it loaded with the words found there. Nothing here knows where a place lies or which LUT a memory is; what
the build said of that is used by the rule (s2_5_rule), marked as the build's word."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_5_find  # noqa: E402
import s2_5_judge  # noqa: E402
import s2_5_states as st  # noqa: E402
from s2_3_table import CONFIDENCE, records_of  # noqa: E402,F401


def text(p: tuple[int, int, int]) -> str:
    return f"{p[0]:#010x}/{p[1]}/{p[2]}"


def place(s: str) -> tuple[int, int, int]:
    far, word, bit = s.split("/")
    return int(far, 16), int(word), int(bit)


def whose(candidates: dict) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """Whose memory a place is, by part 1: (frame address, word, bit) -> (site, memory, address), for the memories
    whose loaded word was found as it is."""
    the_rule = [(m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in candidates["the_six_moves"]]
    s2_5_find.check_rule(the_rule)
    out: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for hit in candidates["memories"]:
        if hit["inverted"]:
            continue
        for p, a in s2_5_find.places_of(hit, the_rule).items():
            out[p] = (hit["site"], hit["memory"], a)
    return out


def close_code(verdict: dict, candidates: dict, design: dict) -> dict:
    """The code run's verdict closed into the tables, or the reasons why a site has none."""
    names = {s["site"]: s["name"] for s in design["ram"]["sites"]}
    out: dict = {"problems": [], "sites": len(names), "cells_a_site": st.CELLS, "tables": None}
    bad = out["problems"].append
    if verdict.get("verdict") != "PASS":
        bad("the code run is not a passing run")
    if (verdict.get("run") or {}).get("kind") != "code":
        bad("the verdict is not of the code run")
    if out["problems"]:
        out["outcome"] = "no table: there is no passing code run to close"
        return out
    found = s2_5_judge.places(verdict["finding"]["follows"])     # place -> (cell, inverted)
    before = s2_5_judge.places(candidates["places"])             # place -> (what it read as loaded, inverted)
    where = whose(candidates)
    new = sorted(p for p in found if p not in before)
    lost = sorted(p for p in before if p not in found)
    turned = sorted(p for p in found if p in before and found[p][1] != before[p][1])
    of_no_site = sorted(p for p in found if p not in where)
    by_site: dict[int, dict[int, list[tuple]]] = {s: {} for s in names}
    disagree: dict[int, int] = {}
    for p, (cell, inverted) in found.items():
        if p not in where:
            continue
        s, k, a = where[p]
        by_site[s].setdefault(cell, []).append((p, inverted))
        if cell != st.number(k, a):
            disagree[s] = disagree.get(s, 0) + 1
    without: list[dict] = []
    tables: dict[int, list[tuple[tuple[int, int, int], bool]]] = {}
    for s in sorted(names):
        none = [n for n in range(st.CELLS) if n not in by_site[s]]
        several = sorted(n for n, its in by_site[s].items() if len(its) > 1)
        if none or several or disagree.get(s):
            without.append({"site": s, "name": names[s], "cells_with_no_bit": len(none), "cells_with_several_bits": len(several),
                            "places_where_the_code_and_the_loaded_word_say_another_cell": disagree.get(s, 0)})
        else:
            tables[s] = [by_site[s][n][0] for n in range(st.CELLS)]
    out.update(bits_that_follow=len(found), inverted=sum(1 for _, inv in found.values() if inv), candidates_of_part_1=len(before),
               places_part_1_did_not_have=[text(p) for p in new[:32]], places_part_1_did_not_have_n=len(new),
               candidates_of_part_1_that_follow_no_cell=[text(p) for p in lost[:32]], candidates_of_part_1_that_follow_no_cell_n=len(lost),
               places_shown_the_other_way_than_in_part_1=[text(p) for p in turned[:32]], places_shown_the_other_way_than_in_part_1_n=len(turned),
               bits_that_follow_and_are_of_no_memory_found=[text(p) for p in of_no_site[:32]], bits_that_follow_and_are_of_no_memory_found_n=len(of_no_site),
               sites_with_a_table=len(tables), sites_without_a_table=without,
               bit_5_after_records=(verdict.get("bit_5") or {}).get("shown_after_records", []))
    if new:
        bad(f"{len(new)} bit(s) follow a cell at a place part 1 did not find")
    if lost:
        bad(f"{len(lost)} candidate(s) of part 1 follow no cell")
    if turned:
        bad(f"{len(turned)} place(s) follow a cell the other way than they followed the written states in part 1")
    if of_no_site:
        bad(f"{len(of_no_site)} bit(s) follow a cell and lie in no memory whose loaded word part 1 found: whose they are is not known")
    if without:
        bad(f"{len(without)} site(s) have no table: " + ", ".join(w["name"] for w in without[:8]) + (" ..." if len(without) > 8 else ""))
    if out["problems"]:
        out["outcome"] = "8: a site where the code and the loaded word disagree, a cell with no bit or several, or a place not as part 1 has it — no single is run"
        return out
    out["tables"] = tables
    out["outcome"] = ("7: at every site every cell has exactly one bit, the bits are the candidates of part 1, and each is the cell its place in the "
                      "loaded word says")
    return out


def table_file(closing: dict, run: dict, design: dict) -> dict:
    """The tables as they are written out when the code run is closed: confidence 1, from the code states and the
    loaded words. For each site its 256 places in the order of the cells, and the cells shown inverted."""
    names = {s["site"]: s["name"] for s in design["ram"]["sites"]}
    return {"schema": "s2_5_table", "schema_version": 1, "label": "closed-book",
            "what": "at every site of the probe design s2b, which bit of configuration memory follows which cell of its four memories: the cell from "
                    "the code run, the site from the word the memory was loaded with (docs/s2_plan.md, sections 45 and 46). Not yet confirmed by "
                    "the singles. A place is frame address/word/bit; cell = 64 x memory + address.",
            "design": design.get("name"), "outcome": closing["outcome"], "sites": closing["sites"], "cells_a_site": closing["cells_a_site"],
            "code_run": {"dir": run["dir"], "result_sha256": run["result_sha256"]},
            "tables": [{"site": s, "name": names[s], "places": [text(p) for p, _ in rows], "inverted": [n for n, (_, inv) in enumerate(rows) if inv]}
                       for s, rows in sorted(closing["tables"].items())]}


def tables_of(doc: dict) -> dict[int, list[tuple[tuple[int, int, int], bool]]]:
    """The tables back from the form they are written out in."""
    return {t["site"]: [(place(p), n in t["inverted"]) for n, p in enumerate(t["places"])] for t in doc["tables"]}


def hold_singles(verdict: dict, tables: dict[int, list]) -> dict:
    """A passing run of the singles held to the tables: which of its cells are confirmed at every site, and the
    contradictions."""
    out: dict = {"problems": [], "confirmed": [], "contradictions": []}
    bad = out["problems"].append
    run = verdict.get("run") or {}
    if verdict.get("verdict") != "PASS" or run.get("kind") != "singles":
        bad("not a passing run of the singles"); return out
    cells = range(st.SINGLES_A_RUN * run["share"], st.SINGLES_A_RUN * (run["share"] + 1))
    if not tables or any(len(rows) != st.CELLS for rows in tables.values()):
        bad("the tables are not of every cell of their sites"); return out
    by_cell: dict[int, dict] = {}
    for p, (cell, inverted) in s2_5_judge.places(verdict["finding"]["follows"]).items():
        by_cell.setdefault(cell, {})[p] = inverted
    for n in sorted(set(by_cell) - set(cells)):
        bad(f"a bit follows cell {n}, which is not a cell of this run")
    for n in cells:
        want = {rows[n][0]: rows[n][1] for rows in tables.values()}
        got = by_cell.get(n, {})
        if got == want:
            out["confirmed"].append(n)
            continue
        missing = sorted(s for s, rows in tables.items() if got.get(rows[n][0]) != rows[n][1])
        other = sorted(p for p in got if p not in want)
        out["contradictions"].append({"cell": n, "sites_whose_place_did_not_change_as_the_table_has_it": missing[:16], "of_them": len(missing),
                                      "bits_that_changed_and_are_no_site_s_place_for_it": [text(p) for p in other[:16]], "of_those": len(other)})
        bad(f"cell {n}: its single changes {len(got)} bit(s); the tables have {len(want)} place(s) for it, one a site; at {len(missing)} site(s) the place "
            f"did not change as the table has it, and {len(other)} bit(s) changed that are no site's place for it")
    return out


def ram_map(design: dict, tables: dict[int, list], code: dict, singles: list[dict]) -> dict:
    """The description. `code`: {"dir", "result_sha256", "reads", "states"} of the code run; `singles`: the same for
    each run of the singles that was made, with "share" and what `hold_singles` said of it ("held")."""
    names = {s["site"]: s["name"] for s in design["ram"]["sites"]}
    confirmed = {n: s for s in singles for n in s["held"]["confirmed"]}
    refuted = {c["cell"]: s for s in singles for c in s["held"]["contradictions"]}
    of_a_cell = []
    for n in range(st.CELLS):
        state = "contradiction" if n in refuted else "confirmed" if n in confirmed else "decoded"
        by = confirmed.get(n) or refuted.get(n)
        of_a_cell.append({"cell": n, "state": state, "code_states": [i for i, x in enumerate(code["states"]) if st.cell(x["ram"], n)],
                          "single": None if by is None else {"run": by["dir"], "state": next(i for i, x in enumerate(by["states"]) if x.get("cell") == n)}})
    entries = []
    for s, rows in sorted(tables.items()):
        for n, (p, inverted) in enumerate(rows):
            state = of_a_cell[n]["state"]
            entries.append({"address": text(p), "site": s, "cell": n, "memory": n // st.DEPTH, "ram_address": n % st.DEPTH, "inverted": inverted,
                            "confidence": CONFIDENCE[state], "state": state})
    return {"schema": "ram_map", "schema_version": 2, "label": "closed-book",
            "what": "at every site of the probe design s2b, which bit of configuration memory is which cell of its LUT RAM: found by writing the RAM "
                    "at every site at once through user logic and reading configuration memory back, the site of a place from the word its memory "
                    "was loaded with (docs/s2_plan.md, sections 45 and 46). An address is the frame address the device named, a word of the frame "
                    "read there (0 the first) and a bit of that word (0 the least significant).",
            "design": design["name"],
            "numbering": "site: the design's number for a site; its name is the design's record of where the build placed the memories it loaded "
                         "with the words found there. cell = 64 x memory + ram_address. memory: which bit of the design's data register writes it (0 "
                         "to 3). ram_address: what the design's address register held (0 to 63). Which LUT of a slice a memory is, and which pin "
                         "carries which address bit, is not shown by this.",
            "sites": [{"site": s, "name": names[s]} for s in sorted(tables)], "cells_a_site": st.CELLS,
            "confidence": {"0": "contradiction: with that cell alone set at every site, the bits that changed are not the places decoded for it",
                           "1": "decoded from the code states and the loaded words only",
                           "2": "confirmed: with that cell alone set at every site, exactly the places decoded for it, one a site, read otherwise than the base"},
            "runs": {"code": {"dir": code["dir"], "result_sha256": code["result_sha256"]},
                     "singles": [{"dir": s["dir"], "share": s["share"], "result_sha256": s["result_sha256"]} for s in singles]},
            "evidence": {"what": "every site was written alike, so what an entry rests on is said once for each cell: the states of the code run in "
                                 "which the cell was one, and the run and state of the singles in which it alone was. The record of a run in which a "
                                 "place's frame was read in a state is 2 + state x (number of reads) + (the read that delivers the frame); the reads "
                                 "are the same in every run of part 2.",
                         "reads": [[f"{far:#010x}", n] for far, n in code["reads"]], "of_a_cell": of_a_cell},
            "counts": {state: sum(1 for e in entries if e["state"] == state) for state in ("confirmed", "decoded", "contradiction")},
            "entries": entries}


def dump(doc: dict) -> str:
    """A description as it is written to a file: its entries a line each."""
    head = json.dumps({k: v for k, v in doc.items() if k != "entries"}, indent=1)
    return head[:-2] + ',\n "entries": [\n' + ",\n".join("  " + json.dumps(e) for e in doc["entries"]) + "\n ]\n}\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    closing = close_code(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()), json.loads(st.DESIGN.read_text()))
    print(json.dumps({k: v for k, v in closing.items() if k != "tables"}, indent=1))
    return 0 if closing["tables"] is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

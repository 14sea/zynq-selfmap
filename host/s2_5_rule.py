#!/usr/bin/env python3
"""S2.5: the rule the probed sites obey — docs/s2_plan.md, sections 45 and 46.

From the tables of part 2 (which place is which cell, at every site probed), the census, the design's record of its
sites' names and the build's record of which LUT position each memory was put on, this says how a memory's place
depends on its site — as far as the sites probed show, and for no other site more than "the rule says":

    the six moves   within its half word and its four frames, which address of a memory lies where
    the position    which word of the site's two, and which half, a memory on a LUT position has
    the half        which half of the device (as the census names the halves) the rows 0 to 49 and 50 to 99 lie in
    the column      which column of the census's block type 0 a column of sites lies in, and which frames of it
    the word        which word of the frame a row has

Each part is read from the measurements alone and is said to be a rule only if every site measured obeys it; where
they do not, what was measured is set down instead and the part says so. The names A to D of the LUT positions and
the names of the sites are the build's and the design's words; the device showed places.

Nothing here reads a database, and nothing is graded. The prediction of part 0 is not read here."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402
import s2_5_states as st  # noqa: E402

HALF, ROWS_A_HALF = 16, 50


def one(values) -> object | None:
    """The one value they all have, or None."""
    s = {json.dumps(v, sort_keys=True) for v in values}
    return json.loads(next(iter(s))) if len(s) == 1 else None


def rule(tables: dict[int, list], design: dict, build: dict, census: dict, all_sites: list[str] | None = None) -> dict:
    """`tables`: site -> for each cell ((frame address, word, bit), inverted?), as s2_5_table has them."""
    lay = s2_2_shares.layout(census)
    cols = s2_2_shares.columns(lay)
    col_of = {far: i for i, c in enumerate(cols) for far in c}
    sites = {s["site"]: s for s in design["ram"]["sites"]}
    per: list[dict] = []
    for s, rows in sorted(tables.items()):
        x, y = (int(v) for v in re.fullmatch(r"SLICE_X(\d+)Y(\d+)", sites[s]["name"]).groups())
        fars = sorted({p[0] for p, _ in rows})
        low = fars[0]
        words = sorted({p[1] for p, _ in rows})
        memories = []
        for k in range(st.MEMORIES):
            its = [rows[st.number(k, a)][0] for a in range(st.DEPTH)]
            half = min(b for _, _, b in its) // HALF * HALF
            memories.append({"position": build["memory_primitives"][sites[s]["cells"][k]]["bel"], "word": one(w for _, w, _ in its), "half": half,
                             "moves": [[f - low, b - half] for f, _, b in its]})
        col = cols[col_of[low]] if low in col_of else []
        per.append({"site": s, "name": sites[s]["name"], "x": x, "y": y, "frames": fars, "words": words, "memories": memories,
                    "census_half": lay["column"][low][1] if low in lay["column"] else None,
                    "census_column": lay["column"][low][3] if low in lay["column"] else None,
                    "frames_of_its_column": len(col), "first_frame_in_its_column": col.index(low) if low in col else None,
                    "inverted": sum(1 for _, inv in rows if inv)})
    doc: dict = {"schema": "s2_5_rule", "schema_version": 1, "label": "closed-book",
                 "what": "how the place of a LUT RAM cell in configuration memory depends on its site, as the sites probed by the design s2b show it "
                         "(docs/s2_plan.md, sections 45 and 46). Measured at the sites listed; for every other site this is what the rule says, and "
                         "nothing here has shown it.",
                 "design": design["name"], "sites_measured": len(per), "measured_at": [p["name"] for p in per],
                 "columns_of_sites_measured": sorted({p["x"] for p in per}),
                 "rows_measured": {str(x): (lambda ys: f"{len(ys)} row(s), {ys[0]} to {ys[-1]}" if len(ys) > 1 else f"row {ys[0]}")(sorted(p["y"] for p in per if p["x"] == x))
                                   for x in sorted({p["x"] for p in per})}}
    if all_sites is not None:
        doc["sites_of_this_kind_not_measured"] = len(set(all_sites) - {p["name"] for p in per})
    obeyed: dict[str, bool] = {}

    # ---- the six moves
    moves = one(m["moves"] for p in per for m in p["memories"])
    obeyed["the_six_moves"] = moves is not None and all(m["word"] is not None for p in per for m in p["memories"]) and not any(p["inverted"] for p in per)
    doc["the_six_moves"] = ({"says": "every memory measured lies in one half of one word of four frames next to each other, shown as it is, and address a lies "
                                      "at the same frame of the four and the same bit of the half word at every one",
                             "moves": [{"address": a, "frame_above_the_lowest": f, "bit_of_the_half_word": b} for a, (f, b) in enumerate(moves)]}
                            if obeyed["the_six_moves"] else {"says": "the memories measured are not all laid out alike", "layouts": len({json.dumps(m["moves"]) for p in per for m in p["memories"]})})

    # ---- the position
    by_position: dict[str, set] = {}
    for p in per:
        for m in p["memories"]:
            if m["word"] is not None:
                by_position.setdefault(m["position"], set()).add((m["word"] - p["words"][0], m["half"]))
    obeyed["the_position"] = bool(by_position) and all(len(v) == 1 for v in by_position.values()) and all(len(p["words"]) == 2 and p["words"][1] == p["words"][0] + 1 for p in per)
    doc["the_position"] = ({"says": "a site's four memories lie in two words next to each other; which of the two and which half is the same for a LUT position at every site",
                            "positions": {k: {"word_of_the_site_s_two": next(iter(v))[0], "half": f"{next(iter(v))[1] + 15} down to {next(iter(v))[1]}"} for k, v in sorted(by_position.items())},
                            "whose_word": "the names of the positions are the build's record (pl/s2b/build.json): what was placed, not something the device showed"}
                           if obeyed["the_position"] else {"says": "a LUT position does not have one word and one half at every site",
                                                           "positions": {k: sorted(v) for k, v in sorted(by_position.items())}})

    # ---- the half
    halves: dict[int, set] = {}
    for p in per:
        halves.setdefault(p["y"] // ROWS_A_HALF, set()).add(p["census_half"])
    obeyed["the_half"] = all(len(v) == 1 and None not in v for v in halves.values()) and len({min(v) for v in halves.values()}) == len(halves)
    doc["the_half"] = {"says": "the rows 0 to 49 lie in one half of the device, as the census names the halves, and the rows 50 to 99 in the other" if obeyed["the_half"]
                       else "the rows do not part into the census's halves at row 50",
                       "rows": {f"{ROWS_A_HALF * h} to {ROWS_A_HALF * h + ROWS_A_HALF - 1}": sorted(str(x) for x in v) for h, v in sorted(halves.items())}}

    # ---- the column
    wide = one(p["frames_of_its_column"] for p in per)
    first = one(p["first_frame_in_its_column"] for p in per)
    of_that_width = sorted({lay["column"][c[0]][3] for c in cols if len(c) == wide}) if wide else []
    by_x: dict[int, set] = {}
    for p in per:
        by_x.setdefault(p["x"], set()).add(p["census_column"])
    steps = {of_that_width.index(next(iter(v))) - x // 2 for x, v in by_x.items() if len(v) == 1 and next(iter(v)) in of_that_width}
    obeyed["the_column"] = (wide is not None and first is not None and all(len(p["frames"]) == 4 and p["frames"] == list(range(p["frames"][0], p["frames"][0] + 4)) for p in per)
                            and all(len(v) == 1 for v in by_x.values()) and len(steps) == 1 and all(x % 2 == 0 for x in by_x))
    doc["the_column"] = ({"says": f"a site's memories lie in four frames next to each other, the {first}th to the {first + 3}th (counted from 0) of a column of {wide} "
                                  f"frames of block type 0; counted among the columns of {wide} frames of its half alone (from 0), the column of sites numbered X lies "
                                  f"in the ({next(iter(steps))} + X/2)-th",
                          "frames_of_the_column": wide, "first_of_the_four": first, "of_site_column_0": next(iter(steps)), "site_columns_a_column": 2,
                          "measured": {str(x): next(iter(v)) for x, v in sorted(by_x.items())},
                          "note": "only columns of sites with even numbers were measured; that two numbers share a column of frames is the rule's reading of a "
                                  "step of one column for two numbers, not something an odd-numbered column showed"}
                         if obeyed["the_column"] else {"says": "the columns of sites measured do not lie on one line among the columns of frames",
                                                       "measured": {str(x): sorted(str(c) for c in v) for x, v in sorted(by_x.items())}})

    # ---- the word
    by_row: dict[int, set] = {}                          # every word a site of the row has a cell in, not its lowest alone (review of 66e4ac4:
    for p in per:                                        # a site with the words 14 and 19 was said to have "2 r and 2 r + 1")
        by_row.setdefault(p["y"] % ROWS_A_HALF, set()).add(tuple(p["words"]))
    alike = all(len(v) == 1 for v in by_row.values())
    its = {r: min(v) for r, v in by_row.items()} if alike else {}
    fits = [f for f in range(-1, ROWS_A_HALF) if alike and all(list(w) == [2 * r + (1 if r > f else 0), 2 * r + (1 if r > f else 0) + 1] for r, w in its.items())]
    obeyed["the_word"] = bool(fits)
    if fits:
        said = (f"row r of its half (the site's row, less 50 in the upper half) has the words 2 r and 2 r + 1 up to row {fits[0]}, and 2 r + 1 and 2 r + 2 above it: "
                "one word of the frame lies between" if 0 <= fits[0] < ROWS_A_HALF - 1 and len(fits) == 1 else
                f"row r of its half has two words; where the one word more lies is not fixed by the rows measured: after row {fits[0]} to {fits[-1]}"
                if len(fits) > 1 else "row r of its half has the words 2 r and 2 r + 1" if fits[0] == ROWS_A_HALF - 1 else "row r of its half has the words 2 r + 1 and 2 r + 2")
        doc["the_word"] = {"says": said, "the_one_word_more_after_row": fits, "rows_measured": len(its),
                           "the_same_row_in_both_halves_and_in_every_column_has_the_same_words": True}
    else:
        doc["the_word"] = {"says": "the rows measured do not have their words by one such rule", "rows": {str(r): sorted(list(w) for w in v) for r, v in sorted(by_row.items())}}

    doc["obeyed_by_every_site_measured"] = obeyed
    doc["one_rule"] = all(obeyed.values())
    doc["sites"] = [{"site": p["site"], "name": p["name"], "frames": [f"{f:#010x}" for f in p["frames"]], "words": p["words"],
                     "memories": [{"position": m["position"], "word": m["word"], "bits": f"{m['half'] + 15} down to {m['half']}"} for m in p["memories"]]} for p in per]
    return doc

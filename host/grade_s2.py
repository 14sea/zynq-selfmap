#!/usr/bin/env python3
"""After the fact: hold the descriptions of S2 against prjxray-db (docs/s2_plan.md, section 57).

Not part of any judge and of no chain: it was written after every run of S2 was stored, judged and committed, and after
section 57 had said what it compares. It reads the descriptions as they are stored and changes none of them. A
disagreement is a finding, not a failure of S2: the database is one more witness, not the answer.

    grade_s2.py [<the database's directory of the family>]

Graded: the LUT RAM cells of S2.3 (one site) and of S2.5 (110 sites), the places of the shift registers of S2.4, and
the rule of S2.5 part by part — at the sites measured, and at every other site of that kind the database has.

How the database's numbers are read (section 57): a tile of `tilegrid.json` has a first frame address and a first word
within a frame; a line of the `segbits` file of the tile's type gives a frame of the tile and a bit, the bit counted
from the tile's first word, 32 to a word, bit 0 the least significant. If a comparison differs under that reading, it
is counted again under others, and those are named: none is taken as agreement.

It takes RAM address a to be bit a of a LUT's content, which S2 does not show and the simulation model says. It parses
no bitstream and reads no report of Vivado; the names of sites and of LUTs are the build's own record.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402  (the project's own reading of its census: in which column an address lies)

# The database is no part of this repository: by default a checkout of prjxray-db beside it.
DEFAULT_DB = ROOT.parent / "prjxray-db" / "zynq7"
DEVICE = "xc7z010"                                   # the directory of the family that holds the tiles of the part
BUS = "CLB_IO_CLK"                                   # the database's name for block type 0
KIND = "SLICEM"                                      # the database's name for the sites that can hold LUT RAM
FRAME_WORDS = 101                                    # UG470: words of a frame (for one of the other readings only)
EVIDENCE = ROOT / "evidence"
S2_3 = EVIDENCE / "s2_3_17A6_2026-11-23" / "ram_map.json"
S2_4 = EVIDENCE / "s2_4b_17A6_2026-11-23" / "srl_map.json"
S2_5 = EVIDENCE / "s2_5b_17A6" / "ram_map.json"
RULE = EVIDENCE / "s2_5b_17A6" / "rule.json"
CENSUS = ROOT / "census" / "frame_census_17A6.json"
SITES_LISTED = ROOT / "pl" / "s2a" / "slicem_sites.txt"
S2B = ROOT / "pl" / "s2b"
# What section 53 said of the columns, in its own words a reckoning and no finding: counted among the columns of
# frames of one width in a half (from 0), the column of sites numbered X is the (13 + X/2)-th up to X12 — measured at
# X10 and X12 — and the (19 + X/2)-th from X16 on — measured at nine columns. Of X14 it said nothing.
SECTION_53 = ((0, 12, 13), (16, None, 19))
SHOWN = 12                                           # differences listed in full before they are only counted
HALF_WORD = 16                                       # the rule speaks of the bits of a half word

READINGS = {                                         # other ways the database's numbers could be read; each is named
    "the bits of a word counted from the other end": lambda f, w, b: (f, w, 31 - b),
    "the words of a frame counted from the other end": lambda f, w, b: (f, FRAME_WORDS - 1 - w, b),
    "both: words and bits counted from the other end": lambda f, w, b: (f, FRAME_WORDS - 1 - w, 31 - b),
}


def xy(name: str) -> tuple[int, int]:
    m = re.fullmatch(r"SLICE_X(\d+)Y(\d+)", name)
    if not m:
        raise ValueError(f"not the name of a site: {name!r}")
    return int(m.group(1)), int(m.group(2))


def place(address: str) -> tuple[int, int, int]:
    """An address of a description: frame address / word of the frame / bit of the word."""
    far, word, bit = address.split("/")
    return int(far, 16), int(word), int(bit)


def said(p: tuple[int, int, int] | None) -> str:
    return "nothing" if p is None else f"{p[0]:#010x}/{p[1]}/{p[2]}"


class Database:
    """`tiles`: the database's grid of tiles. `segbits`: for a type of tile, the text of its file of lines."""

    def __init__(self, tiles: dict, segbits: dict[str, str]) -> None:
        self.tiles = tiles
        self.tile_of = {s: name for name, t in tiles.items() for s in t.get("sites", {})}
        self.lines: dict[str, list[tuple[str, list[tuple[int, int, bool]]]]] = {}
        self.not_read: list[str] = []                # words of a line that are not a frame and a bit
        self.files: dict[str, str] = {}
        for kind, text in segbits.items():
            rows = []
            for line in text.splitlines():
                parts = line.split()
                if len(parts) < 2 or "." not in parts[0]:
                    continue
                bits = []
                for p in parts[1:]:
                    m = re.fullmatch(r"(!?)(\d+)_(\d+)", p)
                    if m:
                        bits.append((int(m.group(2)), int(m.group(3)), bool(m.group(1))))
                    else:
                        self.not_read.append(f"{kind}: {line.strip()}")
                rows.append((parts[0].split(".", 1)[1], bits))
            self.lines[kind] = rows

    @classmethod
    def read(cls, root: Path, device: str = DEVICE) -> "Database":
        grid = root / device / "tilegrid.json"
        tiles = json.loads(grid.read_text())
        kinds = sorted({t["type"] for t in tiles.values() if KIND in t.get("sites", {}).values()})
        files = {k: root / f"segbits_{k.lower()}.db" for k in kinds}
        db = cls(tiles, {k: f.read_text() for k, f in files.items()})
        db.files = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in [grid, *files.values()]}
        return db

    def sites(self, kind: str = KIND) -> list[str]:
        return sorted((s for s, t in self.tile_of.items() if self.tiles[t]["sites"][s] == kind), key=xy)

    def tile(self, site: str) -> dict | None:
        return self.tiles[self.tile_of[site]] if site in self.tile_of else None

    def key(self, site: str) -> str:
        """The name a site has in the lines of its tile's type: its kind, and which of the tile's sites it is by X."""
        t = self.tile(site)
        return f"{t['sites'][site]}_X{sorted(t['sites'], key=xy).index(site)}"

    def where(self, site: str, frame: int, bit: int) -> tuple[int, int, int] | None:
        b = self.tile(site).get("bits", {}).get(BUS)
        return None if b is None else (int(b["baseaddr"], 16) + frame, b["offset"] + bit // 32, bit % 32)

    def layout(self, kind: str, key: str) -> dict[tuple[str, int], tuple[int, int, bool]]:
        """(LUT, bit of its content) -> (frame of the tile, bit of the tile, marked with the database's "!")."""
        out = {}
        for feature, bits in self.lines.get(kind, []):
            m = re.fullmatch(re.escape(key) + r"\.([A-D])LUT\.INIT\[(\d+)\]", feature)
            if m and len(bits) == 1:
                out[(m.group(1), int(m.group(2)))] = bits[0]
        return out

    def content(self, site: str) -> dict[tuple[str, int], tuple[int, int, int]]:
        """(LUT, bit of its content) -> frame address, word, bit; empty where the database has no such site or lines."""
        t = self.tile(site)
        if t is None:
            return {}
        out = {}
        for k, (frame, bit, _) in self.layout(t["type"], self.key(site)).items():
            p = self.where(site, frame, bit)
            if p is not None:
                out[k] = p
        return out

    def named(self, site: str) -> dict[tuple[int, int, int], list[str]]:
        """Every bit the lines of the site's tile name, with what they call it."""
        t = self.tile(site)
        out: dict[tuple[int, int, int], list[str]] = {}
        for feature, bits in self.lines.get(t["type"], []) if t else []:
            for frame, bit, _ in bits:
                p = self.where(site, frame, bit)
                if p is not None:
                    out.setdefault(p, []).append(feature)
        return out


# ---------------------------------------------------------------- the descriptions, as lists of cells

def cells_of_one_site(doc: dict) -> list[tuple[str, str, int, tuple[int, int, int]]]:
    """S2.3's map: (site, LUT, RAM address, place) for each entry; site and LUT as the map's own record of the build."""
    built = doc["as_the_build_placed_them"]
    return [(built["site"], built["memories"][str(e["memory"])][0], e["ram_address"], place(e["address"])) for e in doc["entries"]]


def cells_of_many_sites(doc: dict, design: dict, build: dict) -> tuple[list[tuple[str, str, int, tuple[int, int, int]]], list[str]]:
    """S2.5's map: the same, the LUT from the build's record of the memory the design names for that site."""
    names = {s["site"]: s["name"] for s in doc["sites"]}
    cells = {s["site"]: s["cells"] for s in design["ram"]["sites"]}
    out, odd = [], []
    for e in doc["entries"]:
        prim = build["memory_primitives"][cells[e["site"]][e["memory"]]]
        if prim["site"] != names[e["site"]]:
            odd.append(f"site {e['site']}: the map names {names[e['site']]}, the build placed memory {e['memory']} at {prim['site']}")
        out.append((names[e["site"]], prim["bel"][0], e["ram_address"], place(e["address"])))
    return out, sorted(set(odd))


# ---------------------------------------------------------------- comparisons 1 and 2: the cells of LUT RAM

def grade_ram(cells: list[tuple[str, str, int, tuple[int, int, int]]], db: Database) -> dict:
    out: dict = {"entries": len(cells), "sites": len({c[0] for c in cells}), "agree": 0, "differ": 0,
                 "sites_the_database_does_not_have": sorted({c[0] for c in cells if db.tile(c[0]) is None}, key=xy),
                 "cells_the_database_has_no_line_for": 0, "differences": [], "memories": {}}
    content = {s: db.content(s) for s in {c[0] for c in cells}}
    memories: dict[tuple[str, str], list] = {}
    for site, lut, a, p in cells:
        want = content[site].get((lut, a))
        memories.setdefault((site, lut), []).append((a, p, want))
        if want is None:
            out["cells_the_database_has_no_line_for"] += 1
        if want == p:
            out["agree"] += 1
        else:
            out["differ"] += 1
            if len(out["differences"]) < SHOWN:
                out["differences"].append({"site": site, "lut": lut, "ram_address": a, "the_description": said(p), "the_database": said(want)})
    kinds = {"every place agrees": 0, "the same places in another order": 0, "the places of another LUT of the site": 0, "neither": 0}
    for (site, lut), rows in memories.items():
        mine = {p for _, p, _ in rows}
        if all(p == want for _, p, want in rows):
            kinds["every place agrees"] += 1
        elif mine == {p for (l, _), p in content[site].items() if l == lut}:
            kinds["the same places in another order"] += 1
        elif any(mine == {p for (l, _), p in content[site].items() if l == other} for other in "ABCD" if other != lut):
            kinds["the places of another LUT of the site"] += 1
        else:
            kinds["neither"] += 1
    out["memories"] = {"compared": len(memories), **kinds}
    # counted whether anything differs or not: where all agree, these say how many would have agreed read otherwise
    out["entries_that_would_agree_under_another_reading_of_the_database"] = {
        name: sum(1 for site, lut, a, p in cells if (lut, a) in content[site] and move(*content[site][(lut, a)]) == p)
        for name, move in READINGS.items()}
    return out


# ---------------------------------------------------------------- comparison 3: the places of the shift registers

def grade_srl(doc: dict, db: Database) -> dict:
    built = doc["as_the_build_placed_them"]
    site = built["site"]
    out: dict = {"site": site, "places": len(doc["entries"]), "the_database_has_the_site": db.tile(site) is not None}
    if db.tile(site) is None:
        return out
    content = db.content(site)
    whose = {p: k for k, p in content.items()}
    named = db.named(site)
    own = other = 0
    elsewhere: list[dict] = []
    per: dict[int, dict[int, list]] = {}
    for e in doc["entries"]:
        lut = built["registers"][str(e["register"])][0]
        p = place(e["address"])
        if p in whose and whose[p][0] == lut:
            own += 1
            per.setdefault(e["register"], {}).setdefault(e["output"], []).append([whose[p][1], bool(e["inverted"])])
        else:
            other += 1
            elsewhere.append({"register": e["register"], "output": e["output"], "the_description": said(p),
                              "the_database_calls_it": named.get(p, ["nothing"])})
    for outputs in per.values():
        for v in outputs.values():
            v.sort()
    key = db.key(site)
    t = db.tile(site)
    out.update({
        "content_bits_of_the_lut_the_build_names": own, "not_such": other, "those_that_are_not": elsewhere[:SHOWN],
        "content_bits_of_those_luts_that_are_no_place": sum(64 for _ in per) - len({(r, a) for r, o in per.items() for v in o.values() for a, _ in v}),
        "what_the_database_says_of_such_a_lut_beside_its_content": sorted(
            f for f, _ in db.lines.get(t["type"], []) if f.startswith(key + ".") and "LUT." in f and ".INIT[" not in f),
        "alike_in_every_register": len({json.dumps(o, sort_keys=True) for o in per.values()}) == 1 and len(per) == len(built["registers"]),
        "listed_not_graded": {"what": "for a register and an output: the bits of content its places are, and whether the place reads inverted",
                              "registers": {str(r): {str(o): v for o, v in sorted(outputs.items())} for r, outputs in sorted(per.items())}},
    })
    return out


# ---------------------------------------------------------------- comparisons 4 and 5: the rule, and the sites not measured

def among(lay: dict, cols: list[list[int]], far: int) -> tuple[int, int, int] | None:
    """Of the column of frames an address lies in: its number in the census, its width in frames, and which it is among
    the columns of that width in its half and row (from 0)."""
    if far not in lay["column"]:
        return None
    block, half, row, column = lay["column"][far]
    mine = next(c for c in cols if far in c)
    same = sorted(lay["column"][c[0]][3] for c in cols if lay["column"][c[0]][:3] == (block, half, row) and len(c) == len(mine))
    return column, len(mine), same.index(column)


def section_53(x: int) -> int | None:
    for lo, hi, first in SECTION_53:
        if x >= lo and (hi is None or x <= hi):
            return first + x // 2
    return None


def tally(pairs: list[tuple[str, object, object]]) -> dict:
    """(site, what the rule says, what the database says) -> counts, and the first differences."""
    bad = [{"site": s, "the_rule": r, "the_database": d} for s, r, d in pairs if r != d]
    return {"sites": len(pairs), "agree": len(pairs) - len(bad), "differ": len(bad), "differences": bad[:SHOWN]}


def grade_rule(rule: dict, cells: list[tuple[str, str, int, tuple[int, int, int]]], db: Database, census: dict, listed: list[str] | None = None) -> dict:
    lay = s2_2_shares.layout(census)
    cols = s2_2_shares.columns(lay)
    col_at = {far: c for c in cols for far in c}
    sites = db.sites()
    measured = set(rule.get("measured_at", []))
    out: dict = {"sites_of_this_kind_in_the_database": len(sites), "measured": len(measured),
                 "measured_sites_the_database_does_not_have": sorted(measured - set(sites), key=xy),
                 "obeyed_as_the_rule_says_of_itself": rule.get("obeyed_by_every_site_measured", {})}
    if listed is not None:
        out["the_list_of_sites_the_design_was_made_from"] = {"sites": len(listed), "the_same_sites_as_the_database_s": sorted(listed) == sorted(sites)}
    if "sites_of_this_kind_not_measured" in rule:
        out["not_measured"] = {"the_rule_says": rule["sites_of_this_kind_not_measured"], "by_the_database": len(set(sites) - measured)}

    # ---- the six moves and the position: against the lines of each type of tile that holds such a site
    moves = [(m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in rule.get("the_six_moves", {}).get("moves", [])]
    positions = {k[0]: (v["word_of_the_site_s_two"], int(v["half"].split()[-1])) for k, v in rule.get("the_position", {}).get("positions", {}).items()}
    kinds: dict[str, str] = {}
    for s in sites:
        kinds.setdefault(db.tile(s)["type"], s)
    fits: dict[str, dict] = {}
    for kind, s in sorted(kinds.items()):
        lines = db.layout(kind, db.key(s))
        low = min((f for f, _, _ in lines.values()), default=0)
        frames = sorted({f for f, _, _ in lines.values()})
        fit = {"sites": sum(1 for x in sites if db.tile(x)["type"] == kind), "lines_of_content": len(lines),
               "four_frames_next_to_each_other": frames == list(range(low, low + 4)), "frames_of_the_tile": frames,
               "marked_inverted_by_the_database": sum(1 for _, _, inv in lines.values() if inv)}
        if moves:
            fit["the_six_moves"] = {"lines": len(lines), "agree": sum(1 for (l, a), (f, b, _) in lines.items() if a < len(moves) and (f - low, b % HALF_WORD) == moves[a])}
        if positions:
            fit["the_position"] = {l: {"the_rule": list(positions.get(l, ())), "the_database": sorted({(b // 32, b % 32 // HALF_WORD * HALF_WORD) for (k, _), (_, b, _) in lines.items() if k == l})}
                                   for l in "ABCD"}
            fit["the_position"]["agree"] = sum(1 for l in "ABCD" if fit["the_position"][l]["the_database"] == [positions.get(l)])
        fits[kind] = fit
    out["by_type_of_tile"] = fits

    # ---- what the rule says of a site by its row and its column
    spans = {tuple(int(n) for n in re.fullmatch(r"(\d+) to (\d+)", k).groups()): v for k, v in rule.get("the_half", {}).get("rows", {}).items()}
    rows_a_half = min((hi - lo + 1 for lo, hi in spans), default=0)
    after = rule.get("the_word", {}).get("the_one_word_more_after_row", [])
    column_of = {int(x): v for x, v in rule.get("the_column", {}).get("measured", {}).items()} if isinstance(rule.get("the_column", {}).get("measured"), dict) else {}

    def half_by_rule(y: int) -> str | None:
        v = next((v for (lo, hi), v in spans.items() if lo <= y <= hi), [])
        return v[0] if len(v) == 1 else None

    def words_by_rule(y: int) -> list[int] | None:
        if len(after) != 1 or not rows_a_half:
            return None
        r = y % rows_a_half
        first = 2 * r + (1 if r > after[0] else 0)
        return [first, first + 1]

    def column_by_rule(x: int) -> int | None:
        v = column_of.get(x)
        if isinstance(v, list):
            return int(v[0]) if len(v) == 1 else None
        return None if v is None else int(v)

    # which four frames of its column a site's memories have: the rule file does not say it where the column is no
    # one rule; the entries of the map do
    lowest: dict[str, int] = {}
    for site, _, _, p in cells:
        lowest[site] = min(lowest.get(site, p[0]), p[0])
    first_seen = sorted({col_at[f].index(f) for f in lowest.values() if f in col_at})
    first_of_four = first_seen[0] if len(first_seen) == 1 else None
    out["the_first_of_a_site_s_four_frames_within_its_column"] = {"as_the_entries_of_the_map_show_it": first_seen}

    halves, words, columns, firsts = [], [], [], []
    by_x: dict[int, dict] = {}
    part_ok: dict[str, dict[str, bool]] = {}
    for s in sites:
        x, y = xy(s)
        t = db.tile(s)
        b = t.get("bits", {}).get(BUS)
        content = db.content(s)
        low = min((p[0] for p in content.values()), default=None)
        where = among(lay, cols, low) if low is not None else None
        ok = part_ok.setdefault(s, {})
        base = int(b["baseaddr"], 16) if b else None
        its_half = lay["column"][base][1] if base in lay["column"] else None
        if half_by_rule(y) is not None:
            halves.append((s, half_by_rule(y), its_half)); ok["the_half"] = half_by_rule(y) == its_half
        if words_by_rule(y) is not None:
            theirs = list(range(b["offset"], b["offset"] + b["words"])) if b else None
            words.append((s, words_by_rule(y), theirs)); ok["the_word"] = words_by_rule(y) == theirs
        if first_of_four is not None:
            theirs = col_at[low].index(low) if low in col_at else None
            firsts.append((s, first_of_four, theirs)); ok["the_four_frames"] = first_of_four == theirs
        kind = fits.get(t["type"], {})
        ok["the_six_moves"] = bool(moves) and kind.get("the_six_moves", {}).get("agree") == kind.get("lines_of_content") == 256
        ok["the_position"] = bool(positions) and kind.get("the_position", {}).get("agree") == 4
        col = by_x.setdefault(x, {"sites": 0, "measured_here": column_by_rule(x) is not None, "the_database": set(), "among": set(), "width": set()})
        col["sites"] += 1
        if where is not None:
            col["the_database"].add(where[0]); col["width"].add(where[1]); col["among"].add(where[2])
        if column_by_rule(x) is not None:
            columns.append((s, column_by_rule(x), where[0] if where else None)); ok["the_column"] = where is not None and column_by_rule(x) == where[0]
    out["the_half"] = tally(halves)
    out["the_word"] = tally(words)
    out["the_four_frames"] = tally(firsts)
    out["the_column"] = {"where_the_rule_names_a_column": tally(columns), "columns_of_sites": {}}
    for x, col in sorted(by_x.items()):
        idx = sorted(col["among"])
        said53 = section_53(x)
        out["the_column"]["columns_of_sites"][str(x)] = {
            "sites": col["sites"], "measured": col["measured_here"], "the_rule": column_by_rule(x), "the_database": sorted(col["the_database"]),
            "frames_of_that_column": sorted(col["width"]), "which_among_the_columns_of_that_width": idx,
            "section_53": said53, "section_53_agrees": None if said53 is None else idx == [said53]}
    table = out["the_column"]["columns_of_sites"]
    out["the_column"]["section_53"] = {
        "measured_columns_it_fits": sorted(int(x) for x, c in table.items() if c["measured"] and c["section_53_agrees"]),
        "measured_columns_it_does_not_fit": sorted(int(x) for x, c in table.items() if c["measured"] and c["section_53_agrees"] is False),
        "columns_not_measured_it_fits": sorted(int(x) for x, c in table.items() if not c["measured"] and c["section_53_agrees"]),
        "columns_not_measured_it_does_not_fit": sorted(int(x) for x, c in table.items() if not c["measured"] and c["section_53_agrees"] is False),
        "columns_it_says_nothing_of": sorted(int(x) for x, c in table.items() if c["section_53"] is None)}

    # ---- comparison 5: every site of this kind that was not measured
    def frames_by_rule(x: int, y: int) -> list[int] | None:
        """The addresses of the site's four frames as the rule gives them, or None where it does not."""
        c, h = column_by_rule(x), half_by_rule(y)
        if c is None or h is None or first_of_four is None:
            return None
        its = [col for col in cols if lay["column"][col[0]][1] == h and lay["column"][col[0]][3] == c and lay["column"][col[0]][0] == 0]
        return its[0][first_of_four:first_of_four + 4] if len(its) == 1 and len(its[0]) >= first_of_four + 4 else None

    rest = [s for s in sites if s not in measured]
    with_column = [s for s in rest if column_by_rule(xy(s)[0]) is not None]
    without = [s for s in rest if column_by_rule(xy(s)[0]) is None]
    cells_agree = cells_all = sites_agree = no_place = 0
    examples: list[dict] = []
    for s in with_column:
        x, y = xy(s)
        four, two = frames_by_rule(x, y), words_by_rule(y)
        content = db.content(s)
        if four is None or two is None or not moves or not positions:
            no_place += 1
            continue
        good = 0
        for (lut, a), want in sorted(content.items()):
            mine = (four[moves[a][0]], two[positions[lut][0]], positions[lut][1] + moves[a][1])
            good += mine == want
            if mine != want and len(examples) < SHOWN:
                examples.append({"site": s, "lut": lut, "ram_address": a, "the_rule": said(mine), "the_database": said(want)})
        cells_all += len(content); cells_agree += good; sites_agree += good == len(content) == 256
    needs_no_column = ("the_six_moves", "the_position", "the_half", "the_word", "the_four_frames")
    out["sites_not_measured"] = {
        "sites": len(rest),
        "in_a_column_of_sites_that_was_measured": {
            "sites": len(with_column), "sites_at_which_the_rule_gives_no_place": no_place, "cells_compared": cells_all, "cells_agree": cells_agree,
            "cells_differ": cells_all - cells_agree, "sites_at_which_every_cell_agrees": sites_agree, "differences": examples},
        "in_a_column_of_sites_not_measured": {
            "sites": len(without), "what": "the rule names no column of frames for them; held are the parts that do not need it: " + ", ".join(needs_no_column),
            "sites_at_which_each_of_those_agrees": sum(1 for s in without if all(part_ok[s].get(k) for k in needs_no_column)),
            "by_part": {k: sum(1 for s in without if part_ok[s].get(k)) for k in needs_no_column}}}
    return out


# ---------------------------------------------------------------- the whole

def sentences(g: dict) -> tuple[list[str], list[str], list[str]]:
    agrees: list[str] = []
    differs: list[str] = []
    for name, key in (("S2.5", "s2_5"), ("S2.3", "s2_3")):
        r = g[key]
        text = f"{name}, the cells of LUT RAM: {r['agree']} of {r['entries']} entries at {r['sites']} site(s) lie where the database puts that bit of that LUT's content"
        (agrees if r["differ"] == 0 and r["entries"] else differs).append(text if r["differ"] == 0 else text + f"; {r['differ']} do not")
    r = g["s2_4"]
    if r.get("the_database_has_the_site"):
        text = f"S2.4, the shift registers: {r['content_bits_of_the_lut_the_build_names']} of {r['places']} places are content bits of the LUT the build names for their register"
        (agrees if r["not_such"] == 0 else differs).append(text if r["not_such"] == 0 else text + f"; {r['not_such']} are not")
    else:
        differs.append(f"S2.4: the database has no site {r['site']}")
    r = g["rule"]
    if "the_list_of_sites_the_design_was_made_from" in r:
        same = r["the_list_of_sites_the_design_was_made_from"]["the_same_sites_as_the_database_s"]
        (agrees if same else differs).append(f"the sites of this kind: the list the designs were made from ({r['the_list_of_sites_the_design_was_made_from']['sites']}) "
                                             f"{'is' if same else 'is not'} the database's ({r['sites_of_this_kind_in_the_database']})")
    if r["measured_sites_the_database_does_not_have"]:
        differs.append(f"the rule: the database has no site of this kind named {r['measured_sites_the_database_does_not_have']}")
    if "not_measured" in r:
        n = r["not_measured"]
        (agrees if n["the_rule_says"] == n["by_the_database"] else differs).append(
            f"sites of this kind not measured: the rule says {n['the_rule_says']}, the database leaves {n['by_the_database']}")
    for kind, fit in r["by_type_of_tile"].items():
        for part in ("the_six_moves", "the_position"):
            if part in fit:
                whole = fit[part].get("lines", 4)
                text = f"the rule, {part.replace('_', ' ')}: {fit[part]['agree']} of {whole} hold in the database's lines for tiles of type {kind} ({fit['sites']} sites)"
                (agrees if fit[part]["agree"] == whole else differs).append(text)
    for part in ("the_half", "the_word", "the_four_frames"):
        t = r[part]
        if t["sites"]:
            text = f"the rule, {part.replace('_', ' ')}: {t['agree']} of {t['sites']} sites of this kind in the database"
            (agrees if t["differ"] == 0 else differs).append(text)
    t = r["the_column"]["where_the_rule_names_a_column"]
    if t["sites"]:
        (agrees if t["differ"] == 0 else differs).append(f"the rule, the column as measured: {t['agree']} of {t['sites']} sites in the columns of sites that were measured")
    s53 = r["the_column"]["section_53"]
    if s53["columns_not_measured_it_fits"]:
        agrees.append(f"the reckoning of section 53 for columns of sites not measured: fits at X = {s53['columns_not_measured_it_fits']}")
    if s53["columns_not_measured_it_does_not_fit"] or s53["measured_columns_it_does_not_fit"]:
        differs.append(f"the reckoning of section 53: does not fit at X = {s53['columns_not_measured_it_does_not_fit'] + s53['measured_columns_it_does_not_fit']}")
    n = r["sites_not_measured"]["in_a_column_of_sites_that_was_measured"]
    if n["sites"]:
        text = f"sites not measured, in a measured column of sites: by the rule {n['cells_agree']} of {n['cells_compared']} cells at {n['sites']} sites lie where the database puts them"
        (agrees if n["cells_differ"] == 0 and n["sites_at_which_the_rule_gives_no_place"] == 0 else differs).append(text)
    n = r["sites_not_measured"]["in_a_column_of_sites_not_measured"]
    if n["sites"]:
        text = f"sites not measured, in a column of sites not measured: at {n['sites_at_which_each_of_those_agrees']} of {n['sites']} every part of the rule that needs no column holds"
        (agrees if n["sites_at_which_each_of_those_agrees"] == n["sites"] else differs).append(text)
    not_compared = [
        "whether a place reads inverted: the descriptions say what readback showed; the database's mark on a line is of the bitstream, and is counted beside it, not held against it",
        "which bit of a LUT's content is which stage of a shift register: the database has no line for it; what S2.4 found is listed, not graded",
        "control register 0, the mask of LUT RAM in readback, that reading does not disturb the RAM, bit 5 of the status, the path from PS to PL: the database describes the bitstream, not what the device does",
        "that RAM address a is bit a of the content: taken from the simulation model, shown neither by S2 nor by the database",
    ]
    return agrees, differs, not_compared


def grade(db: Database, s2_3: dict, s2_4: dict, s2_5: dict, rule: dict, design: dict, build: dict, census: dict, listed: list[str] | None = None) -> dict:
    cells, odd = cells_of_many_sites(s2_5, design, build)
    g: dict = {"what": "the descriptions of S2 held against prjxray-db after the fact (docs/s2_plan.md, section 57); nothing here is part of a description",
               "database_files": db.files, "words_of_the_database_s_lines_not_read": len(db.not_read),
               "names_that_do_not_fit_the_build": odd,
               "s2_5": grade_ram(cells, db), "s2_3": grade_ram(cells_of_one_site(s2_3), db), "s2_4": grade_srl(s2_4, db),
               "rule": grade_rule(rule, cells, db, census, listed)}
    g["agrees"], g["differs"], g["not_compared"] = sentences(g)
    if odd:
        g["differs"].append(f"the map of S2.5 names a site otherwise than the build's record at {len(odd)} place(s)")
    return g


def main(argv: list[str]) -> int:
    db = Database.read(Path(argv[1]) if len(argv) > 1 else DEFAULT_DB)
    load = lambda p: json.loads(Path(p).read_text())    # noqa: E731
    listed = [line.strip() for line in SITES_LISTED.read_text().splitlines() if line.strip() and not line.startswith("#")]
    result = grade(db, load(S2_3), load(S2_4), load(S2_5), load(RULE), load(S2B / "design.json"), load(S2B / "build.json"), load(CENSUS), listed)
    print(json.dumps(result, indent=1))
    return 0 if not result["differs"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

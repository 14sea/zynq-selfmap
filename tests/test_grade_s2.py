"""The grader of S2 (host/grade_s2.py; docs/s2_plan.md, section 57). The database here is made up by the test, and so
is the device: the comparison has to say "agrees" and "differs" correctly whatever the database holds.

The made-up device: two halves of four rows; a frame of nine words, one word more after row 1 of a half; six columns
of frames a half, four of them twelve frames wide; sites that can hold LUT RAM in three of those, numbered X0, X2 and
X6. A LUT's 64 bits lie in the last four of a column's twelve frames.
"""
from __future__ import annotations

import ast
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import grade_s2  # noqa: E402

ROWS, AFTER, WIDE, FIRST = 4, 1, 12, 8
WIDTHS = [6, WIDE, WIDE, 6, WIDE, WIDE]                # the columns of frames of a half, by their number
COLUMN = {0: 1, 2: 2, 6: 5}                            # the column of sites numbered X: its column of frames
KIND = {0: "CLBM_L", 2: "CLBM_R", 6: "CLBM_L"}
BEL = {0: "D6LUT", 1: "A6LUT", 2: "B6LUT", 3: "C6LUT"}  # which LUT a memory is, as a build places them
START = {"A": 0, "B": 16, "C": 32, "D": 48}


def far(y: int, column: int, minor: int) -> int:
    return (0 if y >= ROWS else 0x400000) | column << 7 | minor


def first_word(y: int) -> int:
    r = y % ROWS
    return 2 * r + (1 if r > AFTER else 0)


def truth(site: str, lut: str, a: int) -> tuple[int, int, int]:
    """Where the made-up device has bit a of that LUT's content: written here on its own, not taken from the grader."""
    x, y = grade_s2.xy(site)
    bit = START[lut] + 15 - a // 4
    return far(y, COLUMN[x], FIRST + a % 4), first_word(y) + bit // 32, bit % 32


def address(p: tuple[int, int, int]) -> str:
    return f"{p[0]:#010x}/{p[1]}/{p[2]}"


def sites() -> list[str]:
    return [f"SLICE_X{x}Y{y}" for x in COLUMN for y in range(2 * ROWS)]


def census() -> dict:
    entries, rows = [], []
    for half, y in (("top", ROWS), ("bottom", 0)):
        for column, wide in enumerate(WIDTHS):
            entries += [{"far": f"{far(y, column, m):#010x}", "block_type": 0, "half": half, "row": 0, "column": column} for m in range(wide)]
        rows.append({"last": entries[-1]["far"], "ended_by": "the register stood still"})
    return {"entries": entries, "rows": rows}


def lines(kind: str) -> str:
    out = [f"{kind}.SLICEM_X0.{l}LUT.INIT[{a:02d}] {FIRST + a % 4:02d}_{START[l] + 15 - a // 4:02d}" for l in "ABCD" for a in range(64)]
    out += [f"{kind}.SLICEL_X1.{l}LUT.INIT[{a:02d}] {2 + a % 4:02d}_{START[l] + 15 - a // 4:02d}" for l in "ABCD" for a in range(64)]
    out += [f"{kind}.SLICEM_X0.ALUT.SRL 07_01", f"{kind}.SLICEM_X0.AFFMUX.O6 !06_00 06_03"]
    return "\n".join(out) + "\n"


def database(without: tuple[str, ...] = ()) -> grade_s2.Database:
    tiles = {}
    for s in sites():
        if s in without:
            continue
        x, y = grade_s2.xy(s)
        tiles[f"{KIND[x]}_X{x}Y{y}"] = {"bits": {"CLB_IO_CLK": {"baseaddr": f"0x{far(y, COLUMN[x], 0):08X}", "frames": WIDE, "offset": first_word(y), "words": 2}},
                                        "sites": {s: "SLICEM", f"SLICE_X{x + 1}Y{y}": "SLICEL"}, "type": KIND[x]}
    tiles["INT_X9Y9"] = {"bits": {}, "sites": {}, "type": "INT"}
    return grade_s2.Database(tiles, {k: lines(k) for k in sorted(set(KIND.values()))})


MEASURED = [f"SLICE_X0Y{y}" for y in range(2 * ROWS)] + ["SLICE_X6Y2"]


def one_site(site: str = "SLICE_X2Y5") -> dict:
    return {"as_the_build_placed_them": {"site": site, "memories": {str(k): v for k, v in BEL.items()}},
            "entries": [{"address": address(truth(site, BEL[m][0], a)), "memory": m, "ram_address": a, "inverted": False} for m in range(4) for a in range(64)]}


def many_sites(names: list[str] = MEASURED) -> tuple[dict, dict, dict]:
    doc = {"sites": [{"site": i, "name": n} for i, n in enumerate(names)],
           "entries": [{"address": address(truth(n, BEL[m][0], a)), "site": i, "memory": m, "ram_address": a, "inverted": False}
                       for i, n in enumerate(names) for m in range(4) for a in range(64)]}
    design = {"ram": {"sites": [{"site": i, "name": n, "cells": [f"at[{i}].ram{m}" for m in range(4)]} for i, n in enumerate(names)]}}
    build = {"memory_primitives": {f"at[{i}].ram{m}": {"site": n, "bel": BEL[m]} for i, n in enumerate(names) for m in range(4)}}
    return doc, design, build


def shift_registers(site: str = "SLICE_X6Y6") -> dict:
    entries = []
    for r, lut in enumerate("ABCD"):
        for o in range(32):
            its = [(2 * o + 1, False)] + ([(2 * o + 2, True)] if o < 31 else []) + ([(0, True)] if o == 0 else [])
            entries += [{"address": address(truth(site, lut, a)), "register": r, "output": o, "inverted": inv} for a, inv in its]
    return {"as_the_build_placed_them": {"site": site, "registers": {str(r): f"{l}6LUT" for r, l in enumerate("ABCD")}}, "entries": entries}


def the_rule() -> dict:
    return {"measured_at": list(MEASURED), "sites_of_this_kind_not_measured": len(sites()) - len(MEASURED),
            "obeyed_by_every_site_measured": {"the_six_moves": True, "the_position": True, "the_half": True, "the_column": False, "the_word": True},
            "the_six_moves": {"moves": [{"address": a, "frame_above_the_lowest": a % 4, "bit_of_the_half_word": 15 - a // 4} for a in range(64)]},
            "the_position": {"positions": {f"{l}6LUT": {"word_of_the_site_s_two": START[l] // 32, "half": f"{START[l] % 32 + 15} down to {START[l] % 32}"} for l in "ABCD"}},
            "the_half": {"rows": {f"0 to {ROWS - 1}": ["bottom"], f"{ROWS} to {2 * ROWS - 1}": ["top"]}},
            "the_word": {"the_one_word_more_after_row": [AFTER]},
            "the_column": {"measured": {"0": ["1"], "6": ["5"]}}}


SAID_OF_THE_COLUMNS = ((0, 2, 0), (6, None, 0))        # among the columns twelve frames wide: X0 the 0th, X2 the 1st, X6 the 3rd


def graded(db=None, s23=None, s24=None, many=None, rule=None, listed="as the device", said=SAID_OF_THE_COLUMNS) -> dict:
    doc, design, build = many if many is not None else many_sites()
    with mock.patch.object(grade_s2, "SECTION_53", said):
        return grade_s2.grade(db or database(), s23 or one_site(), s24 or shift_registers(), doc, rule or the_rule(), design, build, census(),
                              sites() if listed == "as the device" else listed)


class WhereEverythingIsAsTheDatabaseHasIt(unittest.TestCase):
    def test_nothing_differs_and_what_was_counted_is_said(self) -> None:
        g = graded()
        self.assertEqual(g["differs"], [])
        self.assertEqual((g["s2_5"]["entries"], g["s2_5"]["agree"], g["s2_5"]["sites"]), (9 * 256, 9 * 256, 9))
        self.assertEqual(g["s2_5"]["memories"], {"compared": 36, "every place agrees": 36, "the same places in another order": 0,
                                                 "the places of another LUT of the site": 0, "neither": 0})
        self.assertEqual((g["s2_3"]["entries"], g["s2_3"]["agree"], g["s2_3"]["differ"]), (256, 256, 0))
        self.assertEqual((g["s2_4"]["places"], g["s2_4"]["content_bits_of_the_lut_the_build_names"], g["s2_4"]["not_such"]), (256, 256, 0))
        r = g["rule"]
        self.assertEqual((r["sites_of_this_kind_in_the_database"], r["measured"], r["not_measured"]), (24, 9, {"the_rule_says": 15, "by_the_database": 15}))
        self.assertEqual(r["the_first_of_a_site_s_four_frames_within_its_column"], {"as_the_entries_of_the_map_show_it": [FIRST]})
        for part in ("the_half", "the_word", "the_four_frames"):
            self.assertEqual((r[part]["sites"], r[part]["agree"]), (24, 24), part)
        self.assertEqual((r["the_column"]["where_the_rule_names_a_column"]["sites"], r["the_column"]["where_the_rule_names_a_column"]["agree"]), (16, 16))
        self.assertEqual(sorted(r["by_type_of_tile"]), ["CLBM_L", "CLBM_R"])
        for fit in r["by_type_of_tile"].values():
            self.assertEqual((fit["the_six_moves"], fit["the_position"]["agree"], fit["four_frames_next_to_each_other"]), ({"lines": 256, "agree": 256}, 4, True))
        n = r["sites_not_measured"]
        self.assertEqual((n["sites"], n["in_a_column_of_sites_that_was_measured"]["sites"], n["in_a_column_of_sites_that_was_measured"]["cells_agree"],
                          n["in_a_column_of_sites_that_was_measured"]["sites_at_which_every_cell_agrees"]), (15, 7, 7 * 256, 7))
        self.assertEqual((n["in_a_column_of_sites_not_measured"]["sites"], n["in_a_column_of_sites_not_measured"]["sites_at_which_each_of_those_agrees"]), (8, 8))
        self.assertEqual(len(g["agrees"]), 16, g["agrees"])
        self.assertEqual(len(g["not_compared"]), 4)

    def test_read_another_way_nothing_would_agree(self) -> None:
        """What makes "all agree" say something: the same entries counted under the other readings."""
        g = graded()
        self.assertEqual(set(g["s2_5"]["entries_that_would_agree_under_another_reading_of_the_database"].values()), {0})

    def test_the_columns_as_the_database_has_them(self) -> None:
        table = graded()["rule"]["the_column"]["columns_of_sites"]
        self.assertEqual({x: (c["measured"], c["the_rule"], c["the_database"], c["which_among_the_columns_of_that_width"], c["section_53_agrees"]) for x, c in table.items()},
                         {"0": (True, 1, [1], [0], True), "2": (False, None, [2], [1], True), "6": (True, 5, [5], [3], True)})


class TheCells(unittest.TestCase):
    def test_one_entry_elsewhere_is_one_difference_and_is_shown(self) -> None:
        doc, design, build = many_sites()
        was = doc["entries"][300]["address"]
        doc["entries"][300]["address"] = "0x00000081/0/0"
        g = graded(many=(doc, design, build))
        self.assertEqual((g["s2_5"]["agree"], g["s2_5"]["differ"]), (9 * 256 - 1, 1))
        self.assertEqual(g["s2_5"]["differences"], [{"site": "SLICE_X0Y1", "lut": "D", "ram_address": 44, "the_description": "0x00000081/0/0", "the_database": was}])
        self.assertEqual(g["s2_5"]["memories"]["neither"], 1)
        self.assertTrue(any(s.startswith("S2.5, the cells of LUT RAM") and s.endswith("; 1 do not") for s in g["differs"]), g["differs"])
        self.assertFalse(any(s.startswith("S2.5, the cells") for s in g["agrees"]))

    def test_two_addresses_changed_about_are_the_same_places_in_another_order(self) -> None:
        s23 = one_site()
        s23["entries"][3]["address"], s23["entries"][9]["address"] = s23["entries"][9]["address"], s23["entries"][3]["address"]
        g = graded(s23=s23)
        self.assertEqual((g["s2_3"]["differ"], g["s2_3"]["memories"]["the same places in another order"], g["s2_3"]["memories"]["neither"]), (2, 1, 0))
        self.assertTrue(any(s.startswith("S2.3") for s in g["differs"]))

    def test_a_memory_that_is_another_lut_than_the_build_says(self) -> None:
        s23 = one_site()
        s23["as_the_build_placed_them"]["memories"].update({"0": "A6LUT", "1": "D6LUT"})
        g = graded(s23=s23)
        self.assertEqual((g["s2_3"]["differ"], g["s2_3"]["memories"]["the places of another LUT of the site"], g["s2_3"]["memories"]["every place agrees"]), (128, 2, 2))

    def test_bits_counted_from_the_other_end_are_not_taken_as_agreement(self) -> None:
        """Section 57: if it differs under the reading named and agrees under another, that is reported as what it is."""
        s23 = one_site()
        for e in s23["entries"]:
            f, w, b = grade_s2.place(e["address"])
            e["address"] = address((f, w, 31 - b))
        g = graded(s23=s23)
        self.assertEqual((g["s2_3"]["agree"], g["s2_3"]["differ"]), (0, 256))
        self.assertEqual(g["s2_3"]["entries_that_would_agree_under_another_reading_of_the_database"]["the bits of a word counted from the other end"], 256)
        self.assertTrue(any(s.startswith("S2.3") for s in g["differs"]))

    def test_a_site_the_database_does_not_have(self) -> None:
        g = graded(db=database(without=("SLICE_X2Y5",)))
        self.assertEqual((g["s2_3"]["sites_the_database_does_not_have"], g["s2_3"]["cells_the_database_has_no_line_for"], g["s2_3"]["agree"]), (["SLICE_X2Y5"], 256, 0))
        self.assertEqual(g["s2_3"]["differences"][0]["the_database"], "nothing")

    def test_a_name_in_the_map_that_is_not_the_build_s(self) -> None:
        doc, design, build = many_sites()
        build["memory_primitives"]["at[8].ram2"]["site"] = "SLICE_X6Y3"
        g = graded(many=(doc, design, build))
        self.assertEqual(g["names_that_do_not_fit_the_build"], ["site 8: the map names SLICE_X6Y2, the build placed memory 2 at SLICE_X6Y3"])
        self.assertTrue(any("otherwise than the build's record" in s for s in g["differs"]))


class TheShiftRegisters(unittest.TestCase):
    def test_what_is_listed_of_an_output(self) -> None:
        g = graded()["s2_4"]
        reg = g["listed_not_graded"]["registers"]
        self.assertEqual((reg["0"]["0"], reg["3"]["31"], reg["1"]["7"]), ([[0, True], [1, False], [2, True]], [[63, False]], [[15, False], [16, True]]))
        self.assertTrue(g["alike_in_every_register"])
        self.assertEqual(g["content_bits_of_those_luts_that_are_no_place"], 0)
        self.assertEqual(g["what_the_database_says_of_such_a_lut_beside_its_content"], ["SLICEM_X0.ALUT.SRL"])

    def test_a_place_that_is_no_content_bit_of_its_lut(self) -> None:
        s24 = shift_registers()
        site = s24["as_the_build_placed_them"]["site"]
        s24["entries"][0]["address"] = address(truth(site, "C", 5))                       # of another LUT
        f, w, _ = truth(site, "A", 0)
        s24["entries"][1]["address"] = address((f - 1, grade_s2.xy(site)[1] % ROWS * 2 + 1, 1))   # the line "ALUT.SRL 07_01"
        s24["entries"][2]["address"] = "0x00000000/0/0"                                   # no line at all
        g = graded(s24=s24)
        self.assertEqual((g["s2_4"]["content_bits_of_the_lut_the_build_names"], g["s2_4"]["not_such"]), (253, 3))
        self.assertEqual([e["the_database_calls_it"] for e in g["s2_4"]["those_that_are_not"]], [["SLICEM_X0.CLUT.INIT[05]"], ["SLICEM_X0.ALUT.SRL"], ["nothing"]])
        self.assertTrue(any(s.startswith("S2.4") and s.endswith("; 3 are not") for s in g["differs"]))
        self.assertFalse(g["s2_4"]["alike_in_every_register"])

    def test_a_site_the_database_does_not_have(self) -> None:
        g = graded(db=database(without=("SLICE_X6Y6",)))
        self.assertFalse(g["s2_4"]["the_database_has_the_site"])
        self.assertIn("S2.4: the database has no site SLICE_X6Y6", g["differs"])


class TheRule(unittest.TestCase):
    def differs(self, g: dict, starts: str) -> bool:
        return any(s.startswith(starts) for s in g["differs"])

    def test_a_move_that_is_not_the_database_s(self) -> None:
        rule = the_rule()
        rule["the_six_moves"]["moves"][10]["bit_of_the_half_word"] = 0
        g = graded(rule=rule)
        self.assertEqual({k: f["the_six_moves"]["agree"] for k, f in g["rule"]["by_type_of_tile"].items()}, {"CLBM_L": 252, "CLBM_R": 252})
        self.assertTrue(self.differs(g, "the rule, the six moves: 252 of 256"))
        n = g["rule"]["sites_not_measured"]
        self.assertEqual((n["in_a_column_of_sites_that_was_measured"]["cells_differ"], n["in_a_column_of_sites_that_was_measured"]["sites_at_which_every_cell_agrees"]), (7 * 4, 0))
        self.assertEqual(n["in_a_column_of_sites_not_measured"]["by_part"]["the_six_moves"], 0)
        self.assertTrue(self.differs(g, "sites not measured, in a measured column"))
        self.assertTrue(self.differs(g, "sites not measured, in a column of sites not measured"))

    def test_two_positions_changed_about(self) -> None:
        rule = the_rule()
        p = rule["the_position"]["positions"]
        p["A6LUT"], p["B6LUT"] = p["B6LUT"], p["A6LUT"]
        g = graded(rule=rule)
        self.assertEqual({k: f["the_position"]["agree"] for k, f in g["rule"]["by_type_of_tile"].items()}, {"CLBM_L": 2, "CLBM_R": 2})
        self.assertTrue(self.differs(g, "the rule, the position: 2 of 4"))

    def test_the_halves_the_other_way_round(self) -> None:
        rule = the_rule()
        rule["the_half"]["rows"] = {f"0 to {ROWS - 1}": ["top"], f"{ROWS} to {2 * ROWS - 1}": ["bottom"]}
        g = graded(rule=rule)
        self.assertEqual((g["rule"]["the_half"]["agree"], g["rule"]["the_half"]["differ"]), (0, 24))
        self.assertEqual(g["rule"]["the_half"]["differences"][0], {"site": "SLICE_X0Y0", "the_rule": "top", "the_database": "bottom"})
        self.assertTrue(self.differs(g, "the rule, the half: 0 of 24"))

    def test_the_one_word_more_after_another_row(self) -> None:
        rule = the_rule()
        rule["the_word"]["the_one_word_more_after_row"] = [2]
        g = graded(rule=rule)
        self.assertEqual((g["rule"]["the_word"]["differ"], sorted({grade_s2.xy(d["site"])[1] % ROWS for d in g["rule"]["the_word"]["differences"]})), (6, [2]))
        self.assertTrue(self.differs(g, "the rule, the word: 18 of 24"))

    def test_a_column_that_is_not_the_database_s(self) -> None:
        rule = the_rule()
        rule["the_column"]["measured"]["6"] = ["4"]
        g = graded(rule=rule)
        t = g["rule"]["the_column"]["where_the_rule_names_a_column"]
        self.assertEqual((t["agree"], t["differ"], t["differences"][0]), (8, 8, {"site": "SLICE_X6Y0", "the_rule": 4, "the_database": 5}))
        self.assertTrue(self.differs(g, "the rule, the column as measured: 8 of 16"))
        self.assertEqual(g["rule"]["sites_not_measured"]["in_a_column_of_sites_that_was_measured"]["cells_agree"], 0)

    def test_the_four_frames_are_those_the_map_s_entries_show(self) -> None:
        doc, design, build = many_sites()
        for e in doc["entries"]:
            f, w, b = grade_s2.place(e["address"])
            e["address"] = address((f - 4, w, b))
        g = graded(many=(doc, design, build))
        self.assertEqual(g["rule"]["the_first_of_a_site_s_four_frames_within_its_column"], {"as_the_entries_of_the_map_show_it": [FIRST - 4]})
        self.assertEqual((g["rule"]["the_four_frames"]["agree"], g["rule"]["the_four_frames"]["differ"]), (0, 24))
        self.assertTrue(self.differs(g, "the rule, the four frames: 0 of 24"))

    def test_what_was_reckoned_of_the_columns_is_held_as_a_reckoning(self) -> None:
        g = graded(said=((0, 2, 1), (6, None, 0)))
        s53 = g["rule"]["the_column"]["section_53"]
        self.assertEqual((s53["measured_columns_it_fits"], s53["measured_columns_it_does_not_fit"], s53["columns_not_measured_it_does_not_fit"]), ([6], [0], [2]))
        self.assertIn("the reckoning of section 53: does not fit at X = [2, 0]", g["differs"])
        g = graded(said=((0, 0, 0), (6, None, 0)))
        self.assertEqual(g["rule"]["the_column"]["section_53"]["columns_it_says_nothing_of"], [2])
        self.assertFalse(self.differs(g, "the reckoning"))
        self.assertFalse(any(s.startswith("the reckoning") for s in g["agrees"]), "and of a column it says nothing of, nothing is said")

    def test_the_count_of_sites_and_the_list_they_were_taken_from(self) -> None:
        rule = the_rule()
        rule["sites_of_this_kind_not_measured"] = 14
        g = graded(rule=rule, listed=sites()[:-1])
        self.assertIn("sites of this kind not measured: the rule says 14, the database leaves 15", g["differs"])
        self.assertIn("the sites of this kind: the list the designs were made from (23) is not the database's (24)", g["differs"])

    def test_a_measured_site_the_database_does_not_have(self) -> None:
        g = graded(db=database(without=("SLICE_X6Y2",)))
        self.assertEqual(g["rule"]["measured_sites_the_database_does_not_have"], ["SLICE_X6Y2"])
        self.assertTrue(self.differs(g, "the rule: the database has no site of this kind named"))

    def test_a_rule_that_says_of_itself_that_a_part_does_not_hold_is_not_graded_on_it(self) -> None:
        rule = the_rule()
        rule["the_six_moves"] = {"says": "the memories measured are not all laid out alike", "layouts": 2}
        g = graded(rule=rule)
        self.assertFalse(any("the six moves" in s for s in g["agrees"] + g["differs"]))
        self.assertEqual(g["rule"]["sites_not_measured"]["in_a_column_of_sites_that_was_measured"]["sites_at_which_the_rule_gives_no_place"], 7)
        self.assertTrue(self.differs(g, "sites not measured, in a measured column"))


class TheDatabaseAsItIsRead(unittest.TestCase):
    def test_a_line_s_frame_and_bit_become_an_address_a_word_and_a_bit(self) -> None:
        db = database()
        self.assertEqual(db.key("SLICE_X2Y5"), "SLICEM_X0")
        self.assertEqual(db.key("SLICE_X3Y5"), "SLICEL_X1")
        self.assertEqual(db.where("SLICE_X2Y5", 9, 37), (far(5, 2, 9), first_word(5) + 1, 5))
        self.assertEqual(db.content("SLICE_X2Y5")[("C", 6)], truth("SLICE_X2Y5", "C", 6))
        self.assertEqual(len(db.content("SLICE_X2Y5")), 256)
        self.assertEqual(db.content("SLICE_X9Y9"), {})
        self.assertEqual(len(db.sites()), 24)
        self.assertEqual(db.not_read, [])

    def test_a_word_of_a_line_that_is_no_frame_and_bit_is_counted(self) -> None:
        db = grade_s2.Database({}, {"CLBM_L": "CLBM_L.SLICEM_X0.ALUT.INIT[00] 08_15\nCLBM_L.SLICEM_X0.ALUT.INIT[01] <const0>\n"})
        self.assertEqual(len(db.not_read), 1)
        self.assertEqual(db.layout("CLBM_L", "SLICEM_X0"), {("A", 0): (8, 15, False)})


class ClosedBook(unittest.TestCase):
    def test_the_grader_is_the_only_program_of_s2_that_names_the_database(self) -> None:
        for path in sorted((ROOT / "host").glob("s2_*.py")) + [ROOT / "host" / "s1a_run.py"] + sorted((ROOT / "prober").glob("*.[ch]")):
            text = path.read_text().lower()
            for word in ("prjxray", "segbits", "tilegrid", "grade_s2"):
                self.assertNotIn(word, text, f"{path.name}: {word}")

    def test_it_uses_nothing_of_the_judges_and_writes_nothing(self) -> None:
        text = (ROOT / "host" / "grade_s2.py").read_text()
        tree = ast.parse(text)
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "hashlib", "json", "re", "sys", "pathlib"}, {"s2_2_shares"}, "of the project's programs: its reading of the census alone")
        for word in ("write_text", "write_bytes", "open(", "subprocess", ".bit", ".rpt", ".ll\""):
            self.assertNotIn(word, text, word)

    def test_what_it_is_given_is_left_as_it_was(self) -> None:
        doc, design, build = many_sites()
        given = [one_site(), shift_registers(), doc, the_rule(), design, build]
        kept = copy.deepcopy(given)
        with mock.patch.object(grade_s2, "SECTION_53", SAID_OF_THE_COLUMNS):
            grade_s2.grade(database(), *given, census(), sites())
        self.assertEqual(given, kept)


class TheCommand(unittest.TestCase):
    def run_it(self, s23: dict) -> tuple[int, dict]:
        import contextlib
        import io
        import scratch_dirs
        d = Path(scratch_dirs.mkdtemp(prefix="smgrade_"))
        doc, design, build = many_sites()
        (d / "s2b").mkdir()
        for name, what in (("s23.json", s23), ("s24.json", shift_registers()), ("s25.json", doc), ("rule.json", the_rule()), ("census.json", census()),
                           ("s2b/design.json", design), ("s2b/build.json", build)):
            (d / name).write_text(json.dumps(what))
        (d / "sites.txt").write_text("# the sites\n" + "\n".join(sites()) + "\n")
        said = io.StringIO()
        with mock.patch.multiple(grade_s2, S2_3=d / "s23.json", S2_4=d / "s24.json", S2_5=d / "s25.json", RULE=d / "rule.json", CENSUS=d / "census.json",
                                 S2B=d / "s2b", SITES_LISTED=d / "sites.txt", SECTION_53=SAID_OF_THE_COLUMNS), \
                mock.patch.object(grade_s2.Database, "read", classmethod(lambda cls, root, device=None: database())), contextlib.redirect_stdout(said):
            rc = grade_s2.main(["grade_s2.py", str(d)])
        return rc, json.loads(said.getvalue())

    def test_it_ends_in_zero_where_nothing_differs_and_in_one_where_something_does(self) -> None:
        sys.path.insert(0, str(ROOT / "tests"))
        rc, g = self.run_it(one_site())
        self.assertEqual((rc, g["differs"], len(g["agrees"])), (0, [], 16))
        s23 = one_site()
        s23["entries"][0]["address"] = "0x00000000/0/0"
        rc, g = self.run_it(s23)
        self.assertEqual((rc, len(g["differs"])), (1, 1))


class TheGradeThatIsStored(unittest.TestCase):
    """The grade stored with the evidence is what this grader says of the stored descriptions. Held only where the
    database lies beside the repository: it is no part of it."""

    STORED = ROOT / "evidence" / "s2_grade_2026-11-26" / "grade.json"

    def test_it_is_what_the_grader_says(self) -> None:
        if not (grade_s2.DEFAULT_DB / grade_s2.DEVICE / "tilegrid.json").is_file():
            self.skipTest("no checkout of the database beside the repository")
        load = lambda p: json.loads(Path(p).read_text())    # noqa: E731
        listed = [line.strip() for line in grade_s2.SITES_LISTED.read_text().splitlines() if line.strip() and not line.startswith("#")]
        g = grade_s2.grade(grade_s2.Database.read(grade_s2.DEFAULT_DB), load(grade_s2.S2_3), load(grade_s2.S2_4), load(grade_s2.S2_5), load(grade_s2.RULE),
                           load(grade_s2.S2B / "design.json"), load(grade_s2.S2B / "build.json"), load(grade_s2.CENSUS), listed)
        self.assertEqual(json.loads(json.dumps(g)), load(self.STORED))

    def test_the_stored_grade_names_the_files_it_was_made_from(self) -> None:
        stored = json.loads(self.STORED.read_text())
        self.assertEqual(sorted(stored["database_files"]), ["segbits_clblm_l.db", "segbits_clblm_r.db", "xc7z010/tilegrid.json"])
        self.assertTrue(all(len(v) == 64 for v in stored["database_files"].values()))


if __name__ == "__main__":
    unittest.main()

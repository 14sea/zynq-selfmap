#!/usr/bin/env python3
"""S2.5, part 0: the prediction of where the memories of s2b will lie (docs/s2_plan.md, sections 45 and 46): host only."""
from __future__ import annotations

import copy, hashlib, json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s2_5_predict as P  # noqa: E402

CENSUS = json.loads(P.CENSUS.read_text())
MOVES = [(2 + (a & 1) - 2 * (a >> 3 & 1), 15 - ((a >> 1 & 1) + 2 * (a >> 2 & 1) + 4 * (a >> 4 & 1) + 8 * (a >> 5 & 1))) for a in range(64)]
# the columns of 36 frames of a half, by the number the census gives them, written out
OF_36 = [2, 3, 4, 5, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19, 20, 21, 23, 24, 26, 27, 28, 29, 30, 31, 32, 33, 35, 36, 37, 38, 40, 41, 43, 44, 45, 47, 48, 50, 51, 52, 53]


class WhatTheRulesAreReadFrom(unittest.TestCase):
    def test_the_columns_of_36_frames(self) -> None:
        cols = P.columns_of_36(CENSUS)
        self.assertEqual({h: [f & 0x3FFFFF for f in v] for h, v in cols.items()}, {"top": [c << 7 for c in OF_36], "bottom": [c << 7 for c in OF_36]})
        self.assertEqual((cols["top"][0], cols["bottom"][0], len(OF_36)), (0x00000100, 0x00400100, 41))

    def test_the_two_known_sites_as_the_descriptions_have_them(self) -> None:
        ram, srl = P.known_sites()
        self.assertEqual((ram["name"], ram["frames"]), ("SLICE_X16Y30", [0x00401220, 0x00401221, 0x00401222, 0x00401223]))
        self.assertEqual([(m["position"], m["word"], m["half"]) for m in ram["memories"]], [("D6LUT", 62, 16), ("A6LUT", 61, 0), ("B6LUT", 61, 16), ("C6LUT", 62, 0)])
        self.assertEqual((srl["name"], srl["frames"]), ("SLICE_X34Y70", [0x00001820, 0x00001821, 0x00001822, 0x00001823]))
        self.assertEqual([(m["position"], m["word"], m["half"]) for m in srl["memories"]], [("A6LUT", 40, 0), ("B6LUT", 40, 16), ("C6LUT", 41, 0), ("D6LUT", 41, 16)])

    def test_the_rules_they_give(self) -> None:
        r = P.rules(CENSUS, P.known_sites())
        self.assertEqual(r["the_column"], {"of_site_column_0": 19, "site_columns_a_column": 2})
        self.assertEqual(r["the_half"], {"rows 0 to 49": "bottom", "rows 50 to 99": "top"})
        self.assertEqual(r["the_word"], {"words_a_row": 2, "one_word_more_after_row": list(range(20, 30)), "named_first": 24})
        self.assertEqual(r["the_position"], {"A6LUT": {"word_of_the_row": 0, "half": 0}, "B6LUT": {"word_of_the_row": 0, "half": 16},
                                             "C6LUT": {"word_of_the_row": 1, "half": 0}, "D6LUT": {"word_of_the_row": 1, "half": 16}})
        self.assertEqual(r["read_from"], {"SLICE_X16Y30": {"x": 16, "row": 30, "half": "bottom", "place": 27, "word": 61},
                                          "SLICE_X34Y70": {"x": 34, "row": 20, "half": "top", "place": 36, "word": 40}})
        self.assertEqual((OF_36[27], OF_36[36], 19 + 43 // 2, len(OF_36) - 1), (36, 48, 40, 40), "the highest site column the part has, 43, lands on the last column of 36 frames")

    def test_sites_that_make_no_such_rule_predict_nothing(self) -> None:
        good = P.known_sites()
        def changed(i: int, **over) -> list:
            sites = copy.deepcopy(good); sites[i].update(over); return sites
        self.assertRaisesRegex(ValueError, "not the last four of a column of 36 frames", P.rules, CENSUS, changed(0, frames=[0x0040121F + f for f in range(4)]))
        self.assertRaisesRegex(ValueError, "do not lie in four frames next to each other", P.rules, CENSUS, changed(0, frames=[0x00401220, 0x00401221, 0x00401222, 0x00401224]))
        self.assertRaisesRegex(ValueError, "do not lie in two halves", P.rules, CENSUS, changed(1, name="SLICE_X34Y20"))
        self.assertRaisesRegex(ValueError, "two numbers of site columns to a column of frames", P.rules, CENSUS, changed(1, name="SLICE_X36Y70"))
        self.assertRaisesRegex(ValueError, "two words a row and one word more between them", P.rules, CENSUS, changed(1, name="SLICE_X34Y71"))
        swapped = copy.deepcopy(good); swapped[0]["memories"][0]["position"], swapped[0]["memories"][1]["position"] = "A6LUT", "D6LUT"
        self.assertRaisesRegex(ValueError, "not as the rule of the positions has it", P.rules, CENSUS, swapped)
        three = copy.deepcopy(good); three[1]["memories"][3]["word"] = 42
        self.assertRaisesRegex(ValueError, "not in two words next to each other", P.rules, CENSUS, three)
        self.assertRaisesRegex(ValueError, "no name of a site", P.site_xy, "SLICE_X1")
        higher = copy.deepcopy(good)                     # the rows as they are, and the words of one site two further up: no two words a row
        for m in higher[1]["memories"]:
            m["word"] += 2
        self.assertRaisesRegex(ValueError, "two words a row and one word more between them", P.rules, CENSUS, higher)

    def test_a_site_the_rule_of_the_column_has_no_column_for_is_not_predicted(self) -> None:
        import scratch_dirs
        design = json.loads((P.S2B / "design.json").read_text())
        tmp = Path(scratch_dirs.mkdtemp(prefix="smpredict5_"))
        for name, why in (("SLICE_X44Y3", "a column beyond the last of 36 frames"), ("SLICE_X17Y3", "a site column of an odd number: the rule was read from even ones")):
            made = copy.deepcopy(design); made["ram"]["sites"][0]["name"] = name
            (tmp / "design.json").write_text(json.dumps(made))
            self.assertRaisesRegex(ValueError, f"{name}: the rule of the column gives it no column of frames", P.predict, tmp / "design.json")

    def test_the_word_of_a_row_under_each_form(self) -> None:
        self.assertEqual([P.word_of(r, 24) for r in (0, 20, 24, 25, 30, 49)], [0, 40, 48, 51, 61, 99])
        self.assertEqual([P.word_of(25, f) for f in P.FORMS], [51] * 5 + [50] * 5)
        self.assertEqual({(P.word_of(20, f), P.word_of(30, f)) for f in P.FORMS}, {(40, 61)}, "every form gives the two known rows their words")
        self.assertEqual(max(P.word_of(49, f) + 1 for f in P.FORMS), 100, "the last row's upper word is the last word of a frame of 101")


class ThePredictionAsStored(unittest.TestCase):
    D = ROOT / "evidence" / "s2_5_prediction_2026-11-23"

    def test_it_is_what_the_program_says_now(self) -> None:
        self.assertEqual(json.loads(json.dumps(P.predict())), json.loads((self.D / "prediction.json").read_text()))
        self.assertEqual(hashlib.sha256((self.D / "prediction.json").read_bytes()).hexdigest(), "dcff784f0694fc7e79c37075e961fee08dea2cb97c5790def4d1ff215baa0da4")

    def test_what_it_says(self) -> None:
        p = json.loads((self.D / "prediction.json").read_text())
        self.assertEqual((p["label"], p["memories"], len(p["sites"]), len(p["sites_whose_word_depends_on_the_form"])), ("closed-book", 440, 110, 19))
        self.assertEqual([(m["address"], m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in p["the_six_moves"]], [(a, f, b) for a, (f, b) in enumerate(MOVES)])
        first = {}
        for s in p["sites"]:
            x, y = P.site_xy(s["name"])
            self.assertEqual((s["half"], s["row_of_its_half"], s["column_of_36_frames"]), ("bottom" if y < 50 else "top", y % 50, 19 + x // 2), s["name"])
            self.assertEqual(int(s["frames"][0], 16), (0x00400000 if y < 50 else 0) + (OF_36[19 + x // 2] << 7) + 32, s["name"])
            first.setdefault(x, set()).add(int(s["frames"][0], 16) & 0xFFFF)
            self.assertEqual([(m["memory"], m["position"]) for m in s["memories"]], [(0, "D6LUT"), (1, "A6LUT"), (2, "B6LUT"), (3, "C6LUT")], "as the build placed them")
            row = y % 50
            low = 2 * row + (1 if row > 24 else 0)
            self.assertEqual([(m["word"], m["bits"]) for m in s["memories"]], [(low + 1, "31 down to 16"), (low, "15 down to 0"), (low, "31 down to 16"), (low + 1, "15 down to 0")], s["name"])
            self.assertEqual(bool(s["memories"][0]["word_under_the_other_forms"]), 21 <= row <= 29, s["name"])
        self.assertEqual({x: sorted(v) for x, v in first.items()}, {10: [0x1020], 12: [0x10A0], 16: [0x1220], 20: [0x1320], 24: [0x14A0], 28: [0x1620],
                                                                  30: [0x16A0], 32: [0x17A0], 34: [0x1820], 38: [0x19A0], 42: [0x1AA0]})
        self.assertEqual(sorted(p["sites_whose_word_depends_on_the_form"]),
                         sorted([f"SLICE_X16Y{y}" for y in (*range(21, 30), *range(71, 80))] + ["SLICE_X32Y29"]))
        design = json.loads((ROOT / "pl" / "s2b" / "design.json").read_text())
        self.assertEqual([(s["name"], [m["loaded_word"] for m in s["memories"]]) for s in p["sites"]], [(s["name"], s["init"]) for s in design["ram"]["sites"]])

    def test_as_places(self) -> None:
        p = json.loads((self.D / "prediction.json").read_text())
        said = P.places(p)
        self.assertEqual((len(said), len(set(said.values()))), (28160, 28160), "every cell of every memory a place of its own")
        ram = json.loads(P.RAM_MAP.read_text())["entries"]
        self.assertEqual({k: (m, a) for k, (s, m, a) in said.items() if s == 30},
                         {tuple(int(x, 0) for x in e["address"].split("/")): (e["memory"], e["ram_address"]) for e in ram},
                         "for the one site already known it gives what S2.3 found — from which it was read: no test of it")
        other = P.places(p, form=21)
        moved = {s for k, (s, m, a) in said.items() if other.get(k) != (s, m, a)}
        self.assertEqual(moved, {s["site"] for s in p["sites"] if 22 <= s["row_of_its_half"] <= 24}, "another form moves the rows between the two forms and no other")
        x16y70 = {k for k, (s, m, a) in said.items() if s == 70}
        self.assertEqual((min(x16y70), max(x16y70)), ((0x00001220, 40, 0), (0x00001223, 41, 31)))


if __name__ == "__main__":
    unittest.main()

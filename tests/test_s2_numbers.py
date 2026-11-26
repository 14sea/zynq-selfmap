"""The closed-book rule for the programs of S2, as far as a test can hold it: no number of the part in them but those
the project measured or named itself, each held here to where its program says it comes from (review of S2,
finding F3; docs/s2_plan.md, section 9: the test of the sources for numbers of the part "is extended to the new
programs").

What "a number of the part" is, is taken from the project's own records and from nothing else: the census (the frame
count of every column, the columns of a row, the frames of a row, the rows, the totals) and the list of sites the
designs were made from (how many, how many rows). A constant of a program of S2 that equals one of those numbers, is
above 16 — below that, every bit and every small count would be one — and is not listed here with its reason, fails."""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_5_predict as P  # noqa: E402
import s2_5_rule as R  # noqa: E402

CENSUS = json.loads((ROOT / "census" / "frame_census_17A6.json").read_text())
SITES = [line.strip() for line in (ROOT / "pl" / "s2a" / "slicem_sites.txt").read_text().splitlines() if line.startswith("SLICE_")]
RAM_MAP = json.loads((ROOT / "evidence" / "s2_3_17A6_2026-11-23" / "ram_map.json").read_text())
SRL_MAP = json.loads((ROOT / "evidence" / "s2_4b_17A6_2026-11-23" / "srl_map.json").read_text())

# (program, value) -> why the constant is there. Every one is either a format of this project's own or a number held
# to its source by a test below.
LISTED = {
    ("s2_5_predict.py", 36): "COLUMN_FRAMES: the frames of the census's columns the two measured sites lie in (held below)",
    ("s2_5_predict.py", 50): "ROWS_A_HALF: the rows of the list of sites, over the census's two halves (held below)",
    ("s2_5_predict.py", 30): "FORMS = range(20, 30): the rows, within their halves, of the two measured sites (held below)",
    ("s2_5_rule.py", 50): "ROWS_A_HALF: as the prediction's (held below)",
    ("s2_2_judge.py", 36): "0x24: an outcome code of the prober's transfers, not a count",
    ("s2_3_judge.py", 36): "0x24: an outcome code of the prober's transfers, not a count",
    ("s2_2_judge.py", 28): "the address of a read in the low 28 bits of a word of the list, the prober's own format",
    ("s2_3_judge.py", 28): "the same format, and indices of the parameter block",
    ("s2_judge.py", 28): "indices of the parameter block (the SLCR words wanted)",
    ("s2_judge.py", 30): "bit 30 of CTL0 in the table of its bits' names (UG470)",
    ("s2_judge.py", 1280): "PL_LOG_MAX: how many accesses the prober's log holds (prober/sm.h), not block type 1's frames",
    ("s2_2_judge.py", 1280): "0x500: a status code of the prober's PL stage, not a count",
    ("s2_3_judge.py", 1280): "0x500: a status code of the prober's PL stage, not a count",
    ("s2_2_shares.py", 28): "the list's format: the address in the low 28 bits",
    ("s2_4_chain2.py", 28): "the list's format: the address in the low 28 bits",
}


def numbers_of_the_part() -> set[int]:
    found = {len(CENSUS["rows"])}
    for row in CENSUS["rows"]:
        found |= {row["frames"], len(row["columns"])} | {n for _, n in row["columns"]}
    found |= {n for _, n in CENSUS["totals"]["by_block_type"]} | {CENSUS["totals"]["addresses"]}
    rows = 1 + max(int(re.fullmatch(r"SLICE_X\d+Y(\d+)", s).group(1)) for s in SITES)
    found |= {len(SITES), rows, rows // 2}
    return {n for n in found if n > 16}


def column_of(far: int) -> list[int]:
    """The census's column of block type 0 that holds the frame address, as its frame addresses."""
    entry = next(e for e in CENSUS["entries"] if int(e["far"], 16) == far)
    return sorted(int(e["far"], 16) for e in CENSUS["entries"]
                  if (e["block_type"], e["half"], e["row"], e["column"]) == (entry["block_type"], entry["half"], entry["row"], entry["column"]))


def frames_of(doc: dict) -> list[int]:
    return sorted({int(e["address"].split("/")[0], 16) for e in doc["entries"]})


def row_of(site: str) -> int:
    return int(re.fullmatch(r"SLICE_X\d+Y(\d+)", site).group(1))


class TheNumbersOfThePredictionAndTheRule(unittest.TestCase):
    def test_the_frames_of_a_column_are_those_of_the_census_where_the_measured_sites_lie(self) -> None:
        for doc in (RAM_MAP, SRL_MAP):
            frames = frames_of(doc)
            column = column_of(frames[0])
            self.assertEqual(len(column), P.COLUMN_FRAMES)
            self.assertEqual(len(frames), P.GROUP, "four frames next to each other hold a site")
            self.assertEqual(frames, column[-P.GROUP:], "and they are the last four of their column")

    def test_the_rows_of_a_half_are_the_rows_of_the_list_of_sites_over_the_census_s_two_halves(self) -> None:
        rows = 1 + max(row_of(s) for s in SITES)
        halves = {r["half"] for r in CENSUS["rows"] if r["block_type"] == 0}
        self.assertEqual(halves, {"top", "bottom"})
        self.assertEqual(rows % len(halves), 0)
        self.assertEqual(P.ROWS_A_HALF, rows // len(halves))
        self.assertEqual(R.ROWS_A_HALF, P.ROWS_A_HALF)

    def test_the_forms_of_the_word_lie_between_the_rows_of_the_two_measured_sites(self) -> None:
        sites = {RAM_MAP["as_the_build_placed_them"]["site"], SRL_MAP["as_the_build_placed_them"]["site"]}
        within = sorted(row_of(s) % P.ROWS_A_HALF for s in sites)
        self.assertEqual(P.FORMS, list(range(within[0], within[1])))
        self.assertEqual(P.NAMED, (P.ROWS_A_HALF - 1) // 2, "the form named first is the middle of a half")

    def test_a_half_word_is_what_one_memory_takes_at_the_measured_site(self) -> None:
        by_memory: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
        for e in RAM_MAP["entries"]:
            far, word, bit = e["address"].split("/")
            by_memory[e["memory"]].add((int(far, 16), int(word), int(bit) // R.HALF))
        self.assertEqual(len(by_memory), 4)
        for places in by_memory.values():
            self.assertEqual(len({(w, h) for _, w, h in places}), 1, "every place of a memory lies in one half word of one word")
            self.assertEqual(len(places), P.GROUP, "in each of the four frames")
        self.assertEqual(len(RAM_MAP["entries"]) // 4, P.GROUP * R.HALF, "64 cells a memory: four frames of a half word")


class TheProgramsOfS2(unittest.TestCase):
    def test_no_number_of_the_part_but_those_listed(self) -> None:
        numbers = numbers_of_the_part()
        self.assertTrue({36, 50, 1932, 3864, 1500} <= numbers, "what the census and the list of sites give is what is looked for")
        found = set()
        for path in sorted((ROOT / "host").glob("s2_*.py")):
            for n in ast.walk(ast.parse(path.read_text())):
                if isinstance(n, ast.Constant) and type(n.value) is int and n.value in numbers:
                    found.add((path.name, n.value))
        self.assertEqual(found - set(LISTED), set(), "a number of the part in a program of S2 that nobody has said the source of")
        self.assertEqual(set(LISTED) - found, set(), "and the list names nothing that is no longer there")


if __name__ == "__main__":
    unittest.main()

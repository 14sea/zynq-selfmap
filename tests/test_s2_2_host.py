"""S2.2 on the host — docs/s2_plan.md, section 19: the shares, the rule for the address register, the judge of
stage 8, the run script with a list of reads, and the chain that closes the step.

The device the judge is tried on is the twin with a layout made up in tests/test_prober_s2_2.py; where the cells of
the RAM show in it is made up there too, differently for every seed. The shares and the rule for the address
register are held against the real census and against everything the board has said so far."""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_2_chain  # noqa: E402
import s2_2_judge  # noqa: E402
import s2_2_shares  # noqa: E402
import test_prober_s2_2 as T  # noqa: E402
from test_prober_s2_2 import DATA, FARBLK, FRAME, HB, N, N_LIST, PL, READS, REC, REF, Run  # noqa: E402
from test_s2_host import Board  # noqa: E402

CENSUS = json.loads(s2_2_shares.CENSUS.read_text())
DESIGN = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
KNOWN = dict(DESIGN, census=T.census())               # what the judge is given: the design's facts and (here) the made-up census
EVIDENCE = ROOT / "evidence"


def judged(r: Run, known: dict = KNOWN, planned=None, words=None) -> dict:
    return s2_2_judge.judge(r.words if words is None else words, known, r.planned() if planned is None else planned)


def places(cells) -> set:
    return {(f"{far:#010x}", word, bit, bool(inv)) for _, _, far, word, bit, inv in cells}


def found(v: dict) -> set:
    return {(c["far"], c["word"], c["bit"], c["inverted"]) for c in v["finding"]["candidates"]}


class Shares(unittest.TestCase):
    """Block type 0 of the real census, cut into runs."""

    def setUp(self) -> None:
        # Before every test, not once for the class: where the cutting itself refuses (a mutant of it did, 2026-11-22),
        # each test here must be a test that ran and failed. Made once for the class, none ran, the suite counted ten
        # tests fewer, and the mutant tool took the mutant for one that did not build (docs/s2_plan.md, section 27).
        self.lay = s2_2_shares.layout(CENSUS)
        self.shares = s2_2_shares.shares(CENSUS)

    def test_block_type_0_is_eight_shares(self) -> None:
        self.assertEqual(len(self.shares), 8)
        self.assertEqual([len(s) for s in self.shares], [174, 174, 174, 176, 172, 176, 172, 82])
        self.assertEqual(sum(len(s) for s in self.shares), 1300)
        self.assertTrue(all(len(s) <= s2_2_shares.LIST_MAX for s in self.shares))

    def test_every_address_of_block_type_0_is_read_once_and_nothing_else_is(self) -> None:
        read = [far + j for s in self.shares for far, n in s for j in range(n)]
        self.assertEqual(len(read), 3864)
        self.assertEqual(sorted(read), sorted(self.lay["block0"]))
        self.assertEqual(len(set(read)), len(read))
        self.assertTrue(all(self.lay["column"][f][0] == 0 for f in read))

    def test_a_share_is_whole_columns_and_every_read_lies_in_one(self) -> None:
        cols = s2_2_shares.columns(self.lay)
        self.assertEqual(len(cols), 112)
        self.assertEqual(sorted(set(len(c) for c in cols)), [28, 30, 36, 42])
        firsts, lasts = {c[0] for c in cols}, {c[-1] for c in cols}
        for k, s in enumerate(self.shares):
            self.assertIn(s[0][0], firsts, f"share {k} begins at a column's first address")
            self.assertIn(s[-1][0] + s[-1][1] - 1, lasts, f"share {k} ends at a column's last")
            self.assertEqual(s2_2_shares.list_problems(self.lay, s), [], f"share {k}")

    def test_a_column_is_read_in_threes_from_its_first_address_and_the_last_read_takes_what_is_left(self) -> None:
        self.assertEqual(s2_2_shares.reads_of(list(range(0x100, 0x100 + 28))), [(0x100 + 3 * k, 3) for k in range(9)] + [(0x11B, 1)])
        self.assertEqual(s2_2_shares.reads_of(list(range(0x100, 0x100 + 5))), [(0x100, 3), (0x103, 2)])
        self.assertEqual([n for _, n in s2_2_shares.reads_of(list(range(36)))], [3] * 12)

    def test_the_list_as_the_prober_takes_it(self) -> None:
        self.assertEqual(s2_2_shares.list_words([(0xB98, 3), (0x401BA9, 1)]), [0x30000B98, 0x10401BA9])
        for bad in ((0x10000000, 1), (0xB98, 0), (0xB98, 4)):
            with self.assertRaises(ValueError):
                s2_2_shares.list_words([bad])

    def test_a_list_that_is_not_made_from_the_census_is_named(self) -> None:
        lay = self.lay
        for name, reads, says in (("an address the device never named", [(0x2A, 1)], "does not have in block type 0"),
                                  ("a read across the end of a column", [(0x28, 3)], "does not have in block type 0"),
                                  ("an address of block type 1", [(0x00800000, 3)], "does not have in block type 0"),
                                  ("the same address twice", [(0x00, 3), (0x02, 3)], "already read"),
                                  ("four frames", [(0x00, 4)], "4 frames")):
            with self.subTest(name):
                p = s2_2_shares.list_problems(lay, reads)
                self.assertEqual(len(p), 1, p)
                self.assertIn(says, p[0])
        self.assertEqual(s2_2_shares.list_problems(lay, [(0x27, 3)]), [], "the last three frames of the first column")

    @staticmethod
    def small(*columns: tuple[int, int], ended_by: str = "the register stood still") -> dict:
        """A census of one row: columns given as (first address, frames)."""
        entries = [{"far": f"{base + m:#010x}", "block_type": 0, "half": "top", "row": 0, "column": c, "minor": m}
                   for c, (base, n) in enumerate(columns) for m in range(n)]
        return {"entries": entries, "rows": [{"last": entries[-1]["far"], "ended_by": ended_by}]}

    def test_a_read_must_lie_in_one_column_even_where_two_columns_are_neighbours_by_number(self) -> None:
        lay = s2_2_shares.layout(self.small((0x100, 2), (0x102, 4)))
        self.assertEqual(s2_2_shares.list_problems(lay, [(0x100, 2), (0x102, 3)]), [])
        p = s2_2_shares.list_problems(lay, [(0x101, 2)])
        self.assertEqual(len(p), 1)
        self.assertIn("does not lie in one column", p[0])

    def test_a_share_takes_columns_up_to_the_limit_and_not_one_read_more(self) -> None:
        census = self.small((0x100, 9), (0x200, 6), (0x300, 3))               # 3, 2 and 1 reads
        self.assertEqual([len(x) for x in s2_2_shares.shares(census, 5)], [5, 1])
        self.assertEqual([len(x) for x in s2_2_shares.shares(census, 4)], [3, 3])
        self.assertEqual([len(x) for x in s2_2_shares.shares(census, 6)], [6])

    def test_only_a_row_that_ended_with_a_standstill_has_the_place_where_the_register_stands_still(self) -> None:
        still = s2_2_shares.layout(self.small((0x100, 3)))
        other = s2_2_shares.layout(self.small((0x100, 3), ended_by="the device named an address outside the envelope"))
        self.assertEqual((still["shows"], other["shows"]), ([0x100, 0x101, 0x102, 0x102], [0x100, 0x101, 0x102]))
        self.assertEqual(s2_2_shares.register_after(still, 0x102, 0), 0x102)
        self.assertIsNone(s2_2_shares.register_after(other, 0x102, 0))

    def test_a_column_too_long_for_a_list_is_refused_not_cut(self) -> None:
        with self.assertRaises(ValueError):
            s2_2_shares.shares(CENSUS, limit=13)       # a column of 42 frames is 14 reads


class TheAddressRegister(unittest.TestCase):
    """After a read of n frames the register is n + 1 places on, and after a row's last frame comes a place where it
    still shows that frame's address. Held against every record the board has given."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.lay = s2_2_shares.layout(CENSUS)

    def test_the_rule_at_the_ends(self) -> None:
        after = lambda far, n: s2_2_shares.register_after(self.lay, far, n)   # noqa: E731
        self.assertEqual(after(0xB99, 1), 0xB9B)
        self.assertEqual(after(0xB98, 3), 0xB9C)
        self.assertEqual(after(0x29, 0), 0x80, "the pad alone at a column's last frame: the next column")
        self.assertEqual(after(0x27, 3), 0x81, "three frames to a column's end: one place into the next column")
        self.assertEqual(after(0x1BA9, 0), 0x1BA9, "the pad alone at a row's last frame: the register stands still")
        self.assertEqual(after(0x1BA9, 1), 0x400000)
        self.assertEqual(after(0x1BA7, 3), 0x400000)
        self.assertEqual(after(0x401BA7, 3), 0x800000, "past block type 0: what the device named after it")
        self.assertIsNone(after(0x2A, 1), "an address the census does not have")

    def test_every_stored_record_of_the_chains_obeys_it(self) -> None:
        checked = {0: 0, 1: 0, 3: 0}
        to_a_row_end = 0
        row_last = {int(r["last"], 16) for r in CENSUS["rows"]}
        for path in sorted(EVIDENCE.glob("s1b[3456]*_17A6_*/run*/verdict.json")):
            for rec in json.loads(path.read_text())["records"]:
                if rec.get("code") != "0x0" or "far_read_back" not in rec:
                    continue
                far, n = int(rec["far"], 16), rec["frames"]
                want = s2_2_shares.register_after(self.lay, far, n)
                if want is None:
                    continue
                self.assertEqual(int(rec["far_read_back"], 16), want, f"{path.parent.parent.name}/{path.parent.name} record {rec['index']}")
                checked[n] += 1
                to_a_row_end += n == 3 and far + 2 in row_last
        self.assertGreater(checked[0], 11000)
        self.assertGreater(checked[1], 12000)
        self.assertGreater(checked[3], 1800, "reads of three frames, the form S2.2 uses")
        self.assertGreater(to_a_row_end, 0, "among them reads that end at a row's last frame")

    def test_the_two_runs_of_s2_obey_it(self) -> None:
        for d in ("s2_0_17A6_2026-11-20", "s2_1_17A6_2026-11-20"):
            for rec in json.loads((EVIDENCE / d / "run" / "verdict.json").read_text())["records"]:
                if rec["register"] == "FAR":
                    self.assertEqual(int(rec["value_read"], 16), s2_2_shares.register_after(self.lay, int(rec["far"], 16), rec["frames"]), (d, rec["index"]))


class Judge(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run()
        cls.v = judged(cls.r)

    def test_a_clean_run_passes_and_the_candidates_are_the_places_where_the_cells_show(self) -> None:
        v = self.v
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(found(v), places(self.r.cells))
        self.assertEqual(v["finding"]["bits"], {"still": 55 * FRAME * 32 - 256, "candidates": 256, "candidates_inverted": 0, "restless": 0})
        self.assertEqual((v["finding"]["frames"], v["finding"]["states_read_whole"]), (55, 3))
        self.assertEqual(v["list"], {"reads": 20, "frames": 55, "first": "0x00000a00", "last": "0x00400a82"})
        self.assertEqual(v["params"]["states"], ["all zero", "all one", "all zero"])

    def test_what_the_verdict_says_of_the_run_itself(self) -> None:
        v, r = self.v, self.r
        self.assertEqual(v["expected_console"], r.uart.strip().split("\r\n"))
        self.assertEqual(v["expected_return_code"], "0x0")
        self.assertEqual(v["pl"]["accesses"], 1418)
        self.assertEqual((v["pl"]["id"], v["pl"]["passes_the_ram_held_through"], v["pl"]["writes_counted"]), ("0x53324131", 3, {"ram": 192, "shifts": 0}))
        self.assertEqual(v["pl"]["shift_registers_hold"], ["0xa5c30f69", "0x0f1e2d3c", "0x13579bdf", "0xfedcba98"])
        self.assertEqual(len(v["pl"]["counter"]), 6)
        self.assertEqual(v["registers"]["CTL0"]["GLUTMASK_B"], 1)
        self.assertEqual(v["registers"]["CTL0"]["values"], {"0x00000501": [1, N - 2]})
        self.assertEqual(v["bit_5"], {"shown_after_records": [], "cleared_after_records": [], "still_set_after_clearing": []})
        self.assertEqual(len(v["records"]), N)
        self.assertEqual(v["records"][2]["int_sts_after"], f"{r.rec(2)['after']:08x}")
        self.assertIn("int_sts_after", v["records"][1], "the status after every read, of the list or not")
        self.assertNotIn("int_sts_after_clearing_bit_5", v["records"][1])

    def test_wherever_the_cells_are_put_that_is_where_they_are_found(self) -> None:
        for seed in (2, 3, 5, 11):
            with self.subTest(seed=seed):
                r = Run(cells=T.ram_map(seed=seed))
                v = judged(r)
                self.assertEqual((v["verdict"], found(v)), ("PASS", places(r.cells)))

    def test_cells_shown_inverted_are_candidates_and_said_to_be_inverted(self) -> None:
        r = Run(cells=T.ram_map(seed=4, inverted=40))
        v = judged(r)
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual((v["finding"]["bits"]["candidates"], v["finding"]["bits"]["candidates_inverted"]), (216, 40))
        self.assertEqual(found(v), places(r.cells))

    def test_fewer_none_and_more_are_what_the_run_shows_and_not_a_failure_of_the_run(self) -> None:
        for name, kw, count in (("some cells not seen", {"cells": T.ram_map(cells=200)}, 200), ("a mask that hides them all", {"fault": "masked"}, 0),
                                ("no cell anywhere in these frames", {"cells": []}, 0), ("cells seen at two places", {"cells": T.ram_map(twice=12)}, 268)):
            with self.subTest(name):
                v = judged(Run(**kw))
                self.assertEqual((v["verdict"], len(v["finding"]["candidates"])), ("PASS", count))

    def test_a_bit_that_reads_differently_in_the_two_all_zero_states_is_restless_and_fails_the_run(self) -> None:
        for name, at, readings in (("in the last state", 1 + 2 * N_LIST + 3, "001"), ("in the first", 1 + 3, "100")):
            with self.subTest(name):
                v = judged(Run(f"flip@{at}", cells=[]))
                self.assertEqual(v["verdict"], "FAIL")
                self.assertEqual(v["finding"]["bits"]["restless"], 1)
                self.assertEqual(v["finding"]["restless"], [{"far": "0x00000a06", "word": 3, "bit": 16, "readings": readings}])
                self.assertTrue(any("restless" in p for p in v["problems"]))

    def test_a_bit_that_flips_once_in_the_all_one_state_cannot_be_told_from_a_cell(self) -> None:
        """Three states are not enough to tell: it reads 0, 1, 0 as a cell does. The count of candidates over all
        runs is what stands against it (one more than the RAM has cells), and after that the code probes of S2.3."""
        v = judged(Run(f"flip@{1 + N_LIST + 3}", cells=T.ram_map()))
        self.assertEqual((v["verdict"], v["finding"]["bits"]["candidates"]), ("PASS", 257))

    def test_a_ram_that_did_not_hold_its_state_fails_the_run_and_nothing_is_called_a_candidate(self) -> None:
        v = judged(Run("ramdisturb@6"))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("the run did not complete: status 0xa09 (the RAM did not hold its state after the frames were read)", v["problems"])
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertEqual((v["pl"]["code"], v["pl"]["passes_the_ram_held_through"]), ("0x9", 0))
        self.assertEqual((v["finding"]["candidates"], v["finding"]["frames"]), ([], 0))
        v = judged(Run(f"ramdisturb@{1 + N_LIST + 3}"))
        self.assertEqual((v["pl"]["passes_the_ram_held_through"], v["finding"]["candidates"]), (1, []))

    def test_every_other_way_the_design_may_fail_is_named_and_nothing_else_is_wrong(self) -> None:
        for fault, code, says in (("plid", 2, "the identification register"), ("ramstuck", 5, "the LUT RAM"), ("countstuck", 4, "the counter"),
                                  ("srlmoves", 6, "the shift registers"), ("plcount", 7, "the design's count of writes")):
            with self.subTest(fault):
                v = judged(Run(fault))
                self.assertEqual(v["problems"], [f"the run did not complete: status {0xA00 | code:#x} ({says})"])

    def test_an_envelope_that_leaves_registers_out(self) -> None:
        r = Run(w25=PL + 0x17)
        v = judged(r)
        self.assertEqual(v["problems"], ["the run did not complete: status 0xa01 (the prober's own helper refused an address)"])

    def test_bit_5_is_reported_and_is_not_a_failure(self) -> None:
        v = judged(Run("bit5@6"))
        self.assertEqual((v["verdict"], v["bit_5"]), ("PASS", {"shown_after_records": [6], "cleared_after_records": [6], "still_set_after_clearing": []}))
        self.assertIn("int_sts_after_clearing_bit_5", v["records"][6])
        v = judged(Run("bit5@6,bit5stays"))
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["bit_5"]["still_set_after_clearing"], list(range(6, 2 + 3 * N_LIST)))

    def test_a_status_that_is_amiss_after_a_read_or_after_the_clearing_is_a_stop_the_record_itself_shows(self) -> None:
        """Review of 0417966 (section 22). The prober ends the run at such a read and the record's code says why;
        the judge derives the same code from the two status words, so the stop is one it can follow: nothing is
        said but that the run did not complete."""
        for fault, code in (("lateerr@14", 0x21), ("latedrop@14", 0x23), ("bit5@2,clearerr", 0x21), ("bit5@2,dropafter@14", 0x23),
                            ("bit5@2,lateerr@14", 0x21), (f"lateerr@{14 + 5 * (N_LIST + 3)}", 0x21)):
            with self.subTest(fault):
                r = Run(fault)
                v = judged(r)
                self.assertEqual((v["verdict"], v["problems"]), ("FAIL", [f"the run did not complete: status {0x200 | code:#x}", "1 anomalous read(s)"]))
                self.assertEqual(v["records"][-1]["code"], f"{code:#x}")
        # review of 334df53: after the reads that are not of the list as well
        for fault, status, tail in (("lateerr@5", 0x621, []), ("lateerr@9", 0x221, ["1 anomalous read(s)"]), ("lateerr@313", 0x221, ["1 anomalous read(s)"]),
                                    ("lateerr@318", 0x221, []), ("latedrop@9", 0x223, ["1 anomalous read(s)"]), ("latedrop@318", 0x223, [])):
            with self.subTest(fault):
                v = judged(Run(fault))
                self.assertEqual((v["verdict"], v["problems"]), ("FAIL", [f"the run did not complete: status {status:#x}"] + tail))
        v = judged(Run("donestays"))                     # a done bit that would not clear: the other code of a transfer that was never queued
        self.assertEqual((v["verdict"], v["problems"], v["records"][0]["code"]), ("FAIL", ["the run did not complete: status 0x620"], "0x20"))
        v = judged(Run("bit5@2,short@2"))              # a read that failed by itself, bit 5 showing after it: nothing is cleared, and nothing is missed
        self.assertEqual((v["verdict"], v["bit_5"]), ("FAIL", {"shown_after_records": [2], "cleared_after_records": [], "still_set_after_clearing": []}))
        self.assertFalse([p for p in v["problems"] if "clearing" in p or "raw words" in p], v["problems"])

    def test_an_error_bit_met_before_a_transfer_begins_is_a_stop_the_record_itself_shows(self) -> None:
        """Review of 9fa606e (section 23): stage 8 reads the register before it clears it; code 0x24."""
        for fault, status in (("lateerr@2", 0x624), ("lateerr@7", 0x224), ("lateerr@10", 0x224), ("lateerr@11", 0x224), ("lateerr@12", 0x224), ("lateerr@13", 0x224),
                              ("lateerr@311", 0x224), ("lateerr@315", 0x224),
                              # review of 334df53: the bit set just before the write that begins a transfer — it passed
                              ("preclear@1", 0x624), ("preclear@6", 0x224), ("preclear@10", 0x224), ("preclear@11", 0x224), ("preclear@14", 0x224),
                              ("preclear@15", 0x224), ("preclear@314", 0x224)):
            with self.subTest(fault):
                r = Run(fault)
                v = judged(r)
                self.assertEqual((r.status, v["verdict"], v["problems"][0]), (status, "FAIL", f"the run did not complete: status {status:#x}"))
                self.assertFalse([p for p in v["problems"] if "raw words" in p or "implies" in p or "imply" in p], v["problems"])
                self.assertEqual(v["records"][-1]["code"], "0x24")

    def test_gates_and_refused_parameters(self) -> None:
        for fault, says in (("seu", "SEU_EN gate"), ("ctrl", "CTRL gate"), ("lpbk", "loopback gate"), ("nodone", "PCFG_DONE gate"), ("dcache", "data-cache gate"),
                            ("lvl", "LVL_SHFTR_EN gate"), ("fpgarst", "FPGA_RST_CTRL gate"), ("fclk", "FPGA0_CLK_CTRL gate"), ("pll", "PLL_STATUS gate")):
            with self.subTest(fault):
                v = judged(Run(fault))
                self.assertEqual((v["verdict"], v["problems"]), ("FAIL", [f"the run stopped at the {says}"]))
        r = Run(w7=0)
        v = judged(r)
        self.assertEqual((v["verdict"], v["problems"]), ("FAIL", ["the run stopped: bad parameters"]))
        self.assertEqual(v["expected_console"], ["SM8 start", "SM8 end status=00000500"])

    def test_a_read_that_fails_ends_the_run_and_the_verdict_says_where(self) -> None:
        for fault, status in (("err@11", 0x221), ("timeout@11", 0x222), ("drop@11", 0x223), ("short@4", 0x400), ("padnz@3", 0x400), ("farshort@4", 0x400),
                              ("farshort@2", 0x400), ("short@1", 0x610)):
            with self.subTest(fault):
                r = Run(fault)
                v = judged(r)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertEqual(v["problems"][0], f"the run did not complete: status {status:#x}")
                self.assertLessEqual(len(v["problems"]), 2, v["problems"])
                self.assertEqual(v["expected_return_code"], f"{status:#x}")
                self.assertEqual(v["expected_console"], r.uart.strip().split("\r\n"))

    def test_a_reference_frame_that_changed_is_a_health_stop(self) -> None:
        v = judged(Run(f"flip@{1 + 3 * N_LIST + 1}"))
        self.assertEqual(v["problems"], ["the run did not complete: status 0x300"])

    def test_one_and_two_states(self) -> None:
        v = judged(Run(states=(0, 1)))
        self.assertEqual((v["verdict"], v["finding"]["bits"]["candidates"]), ("PASS", 256))
        v = judged(Run(states=(1,), cells=[]))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("the states are all the same: a bit that follows the RAM cannot be told from one that is still", v["problems"])


class WhatTheJudgeIsGiven(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run()

    def test_another_parameter_block_than_the_one_planned(self) -> None:
        planned = self.r.planned(); planned[9] += 1
        v = judged(self.r, planned=planned)
        self.assertEqual(v["problems"], ["the parameters the prober echoed are not the planned ones (word(s) [9]): the run did not do what was asked"])

    def test_another_list_than_the_one_the_prober_read(self) -> None:
        planned = self.r.planned(); planned[32 + 4] = 1 << 28 | 0xA82      # read 4 was 0xa83 x1
        v = judged(self.r, planned=planned)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any(p.startswith("record 6: expected the target read of 0x00000a82 x1") for p in v["problems"]), v["problems"])
        self.assertTrue(any("already read" in p for p in v["problems"]), "and that list reads an address twice")

    def test_a_planned_list_of_another_length(self) -> None:
        v = judged(self.r, planned=self.r.planned()[:-1])
        self.assertEqual((v["verdict"], v["problems"]), ("INVALID", ["the parameter block names 20 reads; the list the host planned has 19"]))

    def test_a_list_that_was_not_made_from_the_census_fails_the_run_that_read_it(self) -> None:
        reads = [(0xA00, 3), (0xA05, 3), (0xB80, 2)]                      # the second runs across the end of a column
        r = Run(reads=reads, cells=[])
        self.assertEqual(r.status, 1, "the prober reads what it is given inside the envelope")
        v = judged(r)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any(p.startswith("the list is not one made from the census: read 1") for p in v["problems"]), v["problems"])

    def test_without_the_census_or_the_design_s_words_nothing_can_be_held_to_them(self) -> None:
        v = judged(self.r, known=DESIGN)
        self.assertIn("the census was not given: the list and the address register cannot be held to anything", v["problems"])
        v = judged(self.r, known={"census": T.census()})
        self.assertIn("the words the design loads into its shift registers were not given: what they read as cannot be held to anything", v["problems"])
        other = json.loads(json.dumps(KNOWN)); other["srl"]["cells"]["2"]["init"] = "0x13579BDE"
        v = judged(self.r, known=other)
        self.assertTrue(any(p.startswith("the shift registers do not hold what the design's source loads into them") for p in v["problems"]))

    def test_a_census_in_which_the_register_goes_another_way(self) -> None:
        other = T.census(); other["rows"] = other["rows"][1:]             # no standstill after the top row's last frame
        v = judged(self.r, known=dict(DESIGN, census=other))
        self.assertEqual(v["verdict"], "FAIL")
        wrong = [p for p in v["problems"] if "by the census it is" in p]
        self.assertEqual(len(wrong), 3, "the read that ends at that frame, once in each state")
        self.assertIn("the address register reads 0x00400a00 after the pad and 3 frame(s) at 0x00000b9b; by the census it is 0x00400a01", wrong[0])


class Tampered(unittest.TestCase):
    """A clean result with one thing changed in its raw words: each must be said, in words that name it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.r = Run("bit5@6")                          # a clean run in which bit 5 showed once (record 6), so that both forms are there

    def changed(self, edits: dict[int, int] | None = None, cut: int | None = None, fn=None) -> dict:
        w = list(self.r.words)
        for at, value in (edits or {}).items():
            w[at] = value
        if fn:
            fn(w)
        return judged(self.r, words=w[:cut] if cut else w)

    def says(self, v: dict, *texts: str, verdict: str = "FAIL") -> None:
        self.assertEqual(v["verdict"], verdict, v["problems"])
        for t in texts:
            self.assertTrue(any(t in p for p in v["problems"]), f"{t!r} not in {v['problems']}")

    def rec_at(self, i: int, field: int) -> int:
        return HB + i * REC + field

    def log_at(self, k: int) -> int:
        return 64 + 16 + 2 * k + 1

    def test_it_is_clean_as_it_stands(self) -> None:
        self.assertEqual(self.changed()["problems"], [])

    def test_the_header(self) -> None:
        self.says(self.changed({0: 0}), "not a result buffer", verdict="INVALID")
        self.says(self.changed({6: 266}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed({7: 64}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed({5: self.r.total + 1}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed(cut=len(self.r.words) - 1), "the buffer has", verdict="INVALID")
        self.says(self.changed({3: 539, 5: HB + 539 * REC}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed({2: 0x400}), "the header's status is 0x400; the records and the log imply 0x1", "the run did not complete")
        self.says(self.changed({4: 1}), "the header counts 1 anomalies; the records show 0", "1 anomalous read(s)")
        self.says(self.changed({18: 5}), "the header's stop record is 0x5")
        self.says(self.changed({20: 1}), "reserved header words are not zero")
        self.says(self.changed({16: 0x50033000}), "its final INT_STS 50033000 has PCFG_DONE clear or an error bit set")
        self.says(self.changed({16: 0x50073004}), "its final INT_STS 50073004")

    def test_the_gate_readings(self) -> None:
        self.says(self.changed({8: self.r.words[8] | 0x100}), "the readings in the header fail the SEU_EN gate, yet the run went on")
        self.says(self.changed({8: self.r.words[8] & ~0x08000000}), "fail the CTRL gate")
        self.says(self.changed({9: self.r.words[9] | 0x10}), "fail the loopback gate")
        self.says(self.changed({10: self.r.words[10] & ~4}), "fail the PCFG_DONE gate")
        self.says(self.changed({12: self.r.words[12] | 4}), "fail the data-cache gate")
        self.says(self.changed({64 + 6: 0x00200A00}), "fail the FPGA0_CLK_CTRL gate")
        gate = Run("lpbk")
        v = s2_2_judge.judge(gate.words[:2] + [0x103] + gate.words[3:], KNOWN, gate.planned())
        self.assertIn("the run reports a stop at the PCFG_DONE gate, but the readings in its header fail the loopback gate", v["problems"])
        v = s2_2_judge.judge(gate.words[:64 + 4] + [0xF] + gate.words[64 + 5:], KNOWN, gate.planned())
        self.assertIn("SLCR words are recorded although a gate before them fails", v["problems"])

    def test_the_echoed_parameters(self) -> None:
        self.says(self.changed({32 + 13: 1}), "the echoed parameters are not a valid stage-8 parameter block", verdict="INVALID")
        self.says(self.changed({32 + 17: 0x210}), "not a valid stage-8 parameter block", verdict="INVALID")
        self.says(self.changed({32 + 7: 2}), "the parameters the prober echoed are not the planned ones (word(s) [7])")

    def test_the_pl_block_s_form(self) -> None:
        self.says(self.changed({64: 0}), "the PL block does not begin with its magic", verdict="INVALID")
        self.says(self.changed({65: 1441}), "more than it has room for", verdict="INVALID")
        self.says(self.changed({64 + 9: 1}), "reserved words of the PL block are not zero")
        self.says(self.changed({64 + 16 + 2 * 1418: 0x40000001}), "the PL block holds words after the last access it counts")

    def test_the_log_of_accesses_to_the_design(self) -> None:
        self.says(self.changed({self.log_at(0): 0x53324132}), "the PL block's code is 0x0 (nothing wrong); its log implies 0x2 (the identification register)",
                  "access(es) to the design after the point where the sequence ends (access 1)", "the header's status is 0x1; the records and the log imply 0xa02")
        first_ram_write = 65 + 1
        self.says(self.changed({self.log_at(first_ram_write): 1}), f"PL access {first_ram_write}: 0x00000001 written to offset 0x10, where 0x00000000 is due")
        self.says(self.changed({self.log_at(first_ram_write) - 1: PL + 0x04 | 1}), f"PL access {first_ram_write}: a write to offset 0x4, where a write to offset 0x10 is due")
        self.says(self.changed({self.log_at(first_ram_write) - 1: PL + 0x18 | 1}), "write to 0x40000018 is outside what the prober may touch")
        self.says(self.changed({self.log_at(first_ram_write) - 1: PL + 0x12}), "is outside what the prober may touch")
        back_after = 65 + 128 + 128 + 1 + 1            # the first read-back after the first state's frames were read
        self.says(self.changed({self.log_at(back_after): 4}), "its log implies 0x9 (the RAM did not hold its state after the frames were read)")
        back_before = 65 + 128 + 1
        self.says(self.changed({self.log_at(back_before): 4}), "its log implies 0x5 (the LUT RAM)")
        count_after = 65 + 128 + 128 + 1 + 128
        self.says(self.changed({self.log_at(count_after): self.r.words[self.log_at(count_after - 129)]}), "its log implies 0x4 (the counter)")
        srl_after = count_after + 2
        self.says(self.changed({self.log_at(srl_after): self.r.words[self.log_at(srl_after)] ^ 1}), "its log implies 0x6 (the shift registers)")
        writes = 65 + 451 - 1
        self.says(self.changed({self.log_at(writes): 65}), "its log implies 0x7 (the design's count of writes)")
        self.says(self.changed({65: 1417, 64 + 16 + 2 * 1417: 0, 64 + 16 + 2 * 1417 + 1: 0}), "the log of PL accesses ends after 1417")
        self.says(self.changed({65: 1419, 64 + 16 + 2 * 1418: PL + 0x1C, 64 + 16 + 2 * 1418 + 1: 192}), "1 access(es) to the design after the point where the sequence ends")
        self.says(self.changed({66: 5}), "the PL block's code is 0x5 (the LUT RAM); its log implies 0x0 (nothing wrong)", "the PL block says it stopped at access 0xffffffff")
        self.says(self.changed({67: 7}), "the PL block says it stopped at access 0x7")

    def test_the_shift_registers_first_reading(self) -> None:
        def all_of_them(w):                              # every reading of output 0 changed alike: the readings agree, the words do not
            for k in range(1418):
                if w[64 + 16 + 2 * k] == PL + 0x18:
                    w[64 + 16 + 2 * k + 1] ^= 1
        self.says(self.changed(fn=all_of_them), "the shift registers do not hold what the design's source loads into them")
        self.says(self.changed({self.log_at(2): 0x1F}), "has bits set above the four there are")

    def test_a_record_s_own_words(self) -> None:
        i = 9
        self.says(self.changed({self.rec_at(i, 0): 0xA05}), "record 9: expected the target read of", "is not the pinned one")
        self.says(self.changed({self.rec_at(i, 1): 1}), "record 9: expected the target read of")
        self.says(self.changed({self.rec_at(i, 12): 2}), "record 9: expected the target read of")
        self.says(self.changed({self.rec_at(i, 15): 3}), "record 9: expected the target read of")
        self.says(self.changed({self.rec_at(i, 14): 2}), "record 9: expected the target read of")
        self.says(self.changed({self.rec_at(i, 14): 4}), "record 9: 4 frames per read")
        self.says(self.changed({self.rec_at(i, 0): 0x900}), "record 9: reads 0x00000900 + 3 frame(s), outside the envelope")
        self.says(self.changed({self.rec_at(i, 16 + 9): 0x30004001}), "record 9: the frame read stream is not read-only")
        self.says(self.changed({self.rec_at(i, 2): 0x10}), "record 9: code 0x10, but its raw words say 0x0")
        self.says(self.changed({self.rec_at(i, 13): 1}), "record 9: the prober's guard refused its own stream")
        self.says(self.changed({self.rec_at(i, 16 + 5): 0x30008001}), "record 9: the frame read stream is not the pinned one")
        self.says(self.changed({self.rec_at(i, 59 + 1): 0x2800E001}), "record 9: the FAR read stream is not the pinned one")
        self.says(self.changed({self.rec_at(i, 63): 0}), "record 9: the cleanup stream is not the pinned one")
        self.says(self.changed({self.rec_at(i, 9): 1}), "record 9: 0 sentinel word(s) in the data, the record says 1")
        self.says(self.changed({self.rec_at(i, DATA + 5): 1}), "record 9: code 0x0, but its raw words say 0x11")
        self.says(self.changed({self.rec_at(i, DATA + FRAME + 5): 0xA5A55A5A}), "record 9: 1 sentinel word(s)", "raw words say 0x10")
        self.says(self.changed({self.rec_at(i, 3): 0x50073004}), "record 9: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(i, 4): 1001}), "record 9: 1001 polls, above the limit 1000")
        self.says(self.changed({self.rec_at(i, FARBLK + 5): 1}), "record 9: the value")
        self.says(self.changed({self.rec_at(i, FARBLK + 4): self.r.words[self.rec_at(i, FARBLK + 4)] + 1}), "record 9: the address register reads", "by the census it is")
        self.assertEqual(self.r.rec(4)["n"], 1, "record 4 reads one frame: 202 words of data, and the rest of its room is empty")
        self.says(self.changed({self.rec_at(4, DATA + 202 + 5): 1}), "record 4: words after the 202 data words are not zero")
        self.says(self.changed({self.rec_at(1, 59 + 1): 0x28002001}), "record 1: the CTL0 read stream is not the pinned one")
        self.says(self.changed({self.rec_at(1, 5): 0x50033004}), "record 1: a frame read transfer has a status in an operation that reads nothing")
        self.says(self.changed({self.rec_at(0, 10): 1}), "record 0: a health flag on a baseline read")
        self.says(self.changed({self.rec_at(1, 10): 0}), "record 1: a health flag on a target read")
        self.says(self.changed({self.rec_at(N - 1, 10): 0}), "the final reference flag is 0x0, the data say 1")

    def test_the_status_after_a_read_and_the_clearing_of_bit_5(self) -> None:
        after, cleared = FARBLK + 7, 10
        self.assertTrue(self.r.words[self.rec_at(6, after)] & 0x20)
        self.says(self.changed({self.rec_at(6, cleared): 0xFFFFFFFF}), "record 6: bit 5 shows in the status after the read", "nothing is recorded of its clearing")
        self.says(self.changed({self.rec_at(7, cleared): 0x50033004}), "record 7: a clearing of bit 5 is recorded (50033004) although the status after the read")
        self.says(self.changed({self.rec_at(6, 2): 0x23}), "record 6: code 0x23, but its raw words say 0x0")
        # the reads that are not of the list have the word too (review of 334df53), held to the same; nothing is cleared after them
        w = self.r.words
        for i in (0, 1, N - 2, N - 1):
            self.says(self.changed({self.rec_at(i, after): w[self.rec_at(i, after)] | 0x00040000}), f"record {i}: code 0x0, but its raw words say 0x21")
            self.says(self.changed({self.rec_at(i, after): w[self.rec_at(i, after)] & ~4}), f"record {i}: code 0x0, but its raw words say 0x23")
            self.says(self.changed({self.rec_at(i, after): 0}), f"record {i}: code 0x0, but its raw words say 0x23")
        v = self.changed({self.rec_at(1, after): w[self.rec_at(1, after)] | 0x20})
        self.assertEqual((v["verdict"], v["bit_5"]["shown_after_records"], v["bit_5"]["cleared_after_records"]), ("PASS", [1, 6], [6]), "bit 5 after CTL0: recorded, reported, left")
        v = self.changed({self.rec_at(6, cleared): self.r.words[self.rec_at(6, cleared)] | 0x20})
        self.assertEqual((v["verdict"], v["bit_5"]["still_set_after_clearing"]), ("PASS", [6]), "a bit 5 that did not clear is reported, not judged")

    def test_a_status_after_a_read_that_is_amiss_in_a_run_that_went_on(self) -> None:
        """Review of 0417966: a result in which a status read between transfers has an error bit, or has lost
        PCFG_DONE, and the read's code is zero and the run went on, passed. Record 6 has bit 5 and its clearing,
        record 7 neither."""
        after, cleared = FARBLK + 7, 10
        w = self.r.words
        for bit in (6, 11, 14, 15, 18, 20, 21, 22, 23):                     # every bit of a transfer's error mask
            self.says(self.changed({self.rec_at(7, after): w[self.rec_at(7, after)] | 1 << bit}), "record 7: code 0x0, but its raw words say 0x21")
            self.says(self.changed({self.rec_at(6, cleared): w[self.rec_at(6, cleared)] | 1 << bit}), "record 6: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(7, after): w[self.rec_at(7, after)] & ~4}), "record 7: code 0x0, but its raw words say 0x23")
        self.says(self.changed({self.rec_at(6, cleared): w[self.rec_at(6, cleared)] & ~4}), "record 6: code 0x0, but its raw words say 0x23")
        self.says(self.changed({self.rec_at(7, after): (w[self.rec_at(7, after)] | 0x00040000) & ~4}), "record 7: code 0x0, but its raw words say 0x21")
        # bit 5 cleared although the status that showed it was amiss: the prober writes nothing after such a status
        self.says(self.changed({self.rec_at(6, after): w[self.rec_at(6, after)] | 0x00040000}),
                  "record 6: bit 5 was cleared", "record 6: code 0x0, but its raw words say 0x21")
        # a code that says so, and a run that went on all the same
        self.says(self.changed({self.rec_at(7, after): w[self.rec_at(7, after)] | 0x00040000, self.rec_at(7, 2): 0x21}),
                  "56 record(s) after the point where the schedule ends (record 8)", "the header's status is 0x1; the records and the log imply 0x221")

    def test_a_run_that_stopped_at_such_a_status_with_one_thing_changed(self) -> None:
        after, cleared, code = FARBLK + 7, 10, 2
        r = Run("lateerr@14")
        at = lambda field: HB + 2 * REC + field
        problems = lambda edits, run: judged(run, words=[edits.get(k, x) for k, x in enumerate(run.words)])["problems"]
        self.assertIn("record 2: code 0x0, but its raw words say 0x21", problems({at(code): 0}, r))
        self.assertIn("record 2: code 0x23, but its raw words say 0x21", problems({at(code): 0x23, at(cleared): 0x50023004}, r))
        self.assertIn("record 2: code 0x21, but its raw words say 0x0", problems({at(after): r.words[at(after)] & ~0x00040000}, r))
        # a clearing recorded after a status that was amiss, and after a read that failed by itself
        r = Run("bit5@2,lateerr@14")
        self.assertTrue(any("record 2: bit 5 was cleared (50063004) after a read that was not clean" in p for p in problems({at(cleared): 0x50063004}, r)))
        r = Run("bit5@2,short@2")
        self.assertTrue(any("record 2: bit 5 was cleared (50023004) after a read that was not clean" in p for p in problems({at(cleared): 0x50023004}, r)))
        # a stop after the clearing whose word is clean after all
        r = Run("bit5@2,clearerr")
        self.assertIn("record 2: code 0x21, but its raw words say 0x0", problems({at(cleared): r.words[at(cleared)] & ~0x00040000}, r))

    def test_the_code_of_an_error_bit_met_before_a_transfer_with_one_thing_changed(self) -> None:
        """Stage 8 never clears an error bit, so the word of a transfer that was never queued says which it was: with
        an error bit, one that stood there before the transfer (0x24); with a done bit still set, one that would not
        clear (0x20). Section 23 had to take either code; now each is held."""
        r = Run("lateerr@11")                            # record 2: the frames were read, then the register command met the bit
        at = lambda field: HB + 2 * REC + field         # noqa: E731
        problems = lambda edits: judged(r, words=[edits.get(k, x) for k, x in enumerate(r.words)])["problems"]   # noqa: E731
        word = r.words[at(FARBLK)]
        self.assertEqual((word & 0x00043000, r.words[at(FARBLK + 1)]), (0x00040000, 0), "the error bit, the done bits cleared, no poll")
        for code in (0, 0x20, 0x21, 0x23):
            self.assertIn(f"record 2: code {code:#x}, but its raw words say 0x24", problems({at(2): code}))
        self.assertIn("record 2: code 0x24, but its raw words say 0x20", problems({at(FARBLK): (word & ~0x00040000) | 0x1000}), "a done bit and no error bit: 0x20 alone")
        self.assertIn("record 2: code 0x24, but its raw words say 0x21", problems({at(FARBLK + 1): 2}), "with polls it is a transfer that failed while it ran")
        self.says(self.changed({self.rec_at(7, 2): 0x24}), "record 7: code 0x24, but its raw words say 0x0")
        r = Run("donestays")
        v = judged(r, words=[0x24 if k == HB + 2 else x for k, x in enumerate(r.words)])
        self.assertIn("record 0: code 0x24, but its raw words say 0x20", v["problems"])

    def test_ctl0_read_differently_before_and_after(self) -> None:
        self.says(self.changed({self.rec_at(N - 2, FARBLK + 4): 0x00000401}), "CTL0 does not read the same before and after: 0x00000401 in record(s) [62], 0x00000501 in record(s) [1]")

    def test_a_frame_changed_in_one_state(self) -> None:
        third = 2 + 2 * N_LIST + 1                       # read 1 of the list in the third state: three frames from 0xa03
        at = self.rec_at(third, DATA + 2 * FRAME + 7)   # its second frame, 0xa04: word 7
        self.assertFalse(any(far == 0xA04 and word == 7 and bit == 7 for _, _, far, word, bit, _ in self.r.cells), "no cell was put there")
        v = self.changed({at: self.r.words[at] ^ 0x80})
        self.says(v, "1 bit(s) read differently")
        self.assertEqual(v["finding"]["restless"], [{"far": "0x00000a04", "word": 7, "bit": 7, "readings": "001"}])
        self.assertEqual(v["finding"]["bits"]["candidates"], 256, "and the cells are found all the same")

    def test_a_bit_that_comes_on_with_the_all_one_state_and_stays_is_restless_not_a_candidate(self) -> None:
        second, third = 2 + N_LIST + 1, 2 + 2 * N_LIST + 1
        at = [self.rec_at(k, DATA + 2 * FRAME + 7) for k in (second, third)]
        v = self.changed({a: self.r.words[a] | 0x80 for a in at})
        self.says(v, "1 bit(s) read differently")
        self.assertEqual(v["finding"]["restless"], [{"far": "0x00000a04", "word": 7, "bit": 7, "readings": "011"}])
        first = self.rec_at(2 + 1, DATA + 2 * FRAME + 7)
        v = self.changed({first: self.r.words[first] | 0x80, at[0]: self.r.words[at[0]] | 0x80})
        self.assertEqual(v["finding"]["restless"], [{"far": "0x00000a04", "word": 7, "bit": 7, "readings": "110"}])

    def test_a_log_in_a_run_that_never_came_to_the_design(self) -> None:
        r = Run("short@1")                               # the reference frame's first reading fails: nothing of the design is touched
        self.assertEqual((r.status, r.plb[1]), (0x610, 0))
        w = list(r.words); w[65] = 1; w[64 + 16], w[64 + 17] = PL, 0x53324131
        v = s2_2_judge.judge(w, KNOWN, r.planned())
        self.assertIn("the PL block shows an access to the design in a run that never came to it", v["problems"])

    def test_records_missing_and_records_too_many(self) -> None:
        short = lambda w: w.__setitem__(3, N - 1) or w.__setitem__(5, HB + (N - 1) * REC)   # noqa: E731
        self.says(self.changed(fn=short, cut=HB + (N - 1) * REC), "the records end at 63; a final read of 0x00000b99 x1 (state 3) is missing")

        def one_more(w):
            w[3], w[5] = N + 1, HB + (N + 1) * REC
            w.extend(w[HB + (N - 1) * REC: HB + N * REC])
        self.says(self.changed(fn=one_more), "1 record(s) after the point where the schedule ends (record 64)")


class Board8(Board):
    """The pretend board with the list of reads where the run script sends it, and a device given as a census: the
    twin is told which address follows which around the reads of the list, and where the cells of the RAM show."""

    def c_go(self, w):
        tmp = Path(scratch_dirs.mkdtemp(prefix="smlist_"))
        blob = self.blobs.get(s1a_run.LIST_ADDR, b"")
        (tmp / "list.txt").write_text("\n".join(f"{x:x}" for x in struct.unpack("<%dI" % (len(blob) // 4), blob)) + "\n")
        (tmp / "rammap.txt").write_text("".join("%d %d %x %d %d %d\n" % c for c in self.q.get("cells", [])))
        self.q["env"] = dict(self.q.get("env", {}), SM_LIST=str(tmp / "list.txt"), SM_RAMMAP=str(tmp / "rammap.txt"))
        return super().c_go(w)

    def load(self, loady: str, path: str):
        reply = super().load(loady, path)
        if self.q.get("corrupt_list") and f"{s1a_run.LIST_ADDR:08x}" in loady:
            blob = self.blobs[s1a_run.LIST_ADDR]; self.blobs[s1a_run.LIST_ADDR] = blob[:4] + bytes([blob[4] ^ 1]) + blob[5:]
        return reply


def device(census: dict, reads) -> dict:
    """For the twin: which address follows which, and what the register shows where it stands still — for the places
    around the reads of a list, taken from a census."""
    lay = s2_2_shares.layout(census)
    shows = lay["shows"]
    ident = lambda at: shows[at] if at == lay["place"].get(shows[at]) else 0xFFF00000 + at   # noqa: E731  a place with no address of its own
    lo = max(0, min(lay["place"][far] for far, _ in reads) - 1)
    hi = min(len(shows) - 1, max(lay["place"][far] + n for far, n in reads) + 2)
    succ = {ident(at): ident(at + 1) for at in range(lo, hi) if ident(at + 1) != ident(at) + 1}
    return {"succ": succ, "shows": {ident(at): shows[at] for at in range(lo, hi + 1) if ident(at) != shows[at]}}


def cells_in(reads, seed: int = 1, cells: int = 256, **kw) -> list:
    """The cells of the RAM somewhere in the frames a list reads (as test_prober_s2_2.ram_map, for any list)."""
    fars = [far + j for far, n in reads for j in range(n) if far + j != REF]
    out, used, x = [], set(), seed * 2654435761 % 2 ** 32
    for c in range(cells):
        while True:
            x = (x * 1103515245 + 12345) % 2 ** 31
            p = (fars[x % len(fars)], (x >> 8) % FRAME, (x >> 16) % 32)
            if p not in used:
                used.add(p); break
        out.append((c // 4, c % 4, *p, 0))
    return out


LIMIT = 10                                             # the made-up device in three shares: 7, 10 and 3 reads


def run8(share: int, census: dict | None = None, limit: int = s2_2_shares.LIST_MAX, fault: str = "", out: Path | None = None, cells=None, **quirks):
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
    census = CENSUS if census is None else census
    base = json.loads(s1a_run.STAGES["s2_2"]["expected"].read_text())
    exp = s1a_run.with_share("s2_2", base, share, census, limit)
    reads = s2_2_shares.shares(census, limit)[share]
    out = Path(scratch_dirs.mkdtemp(prefix="smout8_")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "list.bin").write_bytes(s1a_run.list_bytes(exp))
    exp = dict(exp, list_file=str(out / "list.bin"))
    pl = s1a_run.pl_file(exp).read_bytes()
    u = Board8(fault, far_rule="skip", card_has_s2a=True, cells=cells_in(reads) if cells is None else cells, **device(census, reads), **quirks)
    known = dict(DESIGN, census=census)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), known, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s800000{share}.bin", "s2_2")
    return rec, u, out


class WithAShare(unittest.TestCase):
    def setUp(self) -> None:
        # Before every test, not once for the class: where the image's own tests fail, each test here must be a test
        # that ran and failed. Made ready once for the class, none of them ran, the suite counted six tests fewer, and
        # the mutant tool took every mutant the image's tests are there to catch for one that did not build
        # (docs/s2_plan.md, section 25; tests/test_stage_designs.py holds every test file to this).
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        self.base = json.loads(s1a_run.STAGES["s2_2"]["expected"].read_text())

    def test_the_set_as_the_tests_write_it(self) -> None:
        par = [int(w, 16) for w in self.base["params"]]
        lay = s2_2_shares.layout(CENSUS)
        self.assertEqual(par[0:10], [0x31504D53, 1, 8, min(lay["block0"]), max(lay["block0"]), 0xB99, 0, 3, 0, 0x00200000])
        self.assertEqual((par[3], par[4]), (0x00000000, 0x00401BA9))
        self.assertEqual((par[15], par[16], par[17]), (0x200, 0, 0x010), "the quiet wait; no list yet; all zero, all one, all zero")
        self.assertEqual(par[24:32], [PL, PL + 0x1F, 0x53324131, 0, 0x0000000F, 0x00000000, 0x00400800, 0x0000003F])
        self.assertFalse(s2_2_judge.params_valid(par), "without a share it is not a block the prober would run with")
        self.assertEqual(self.base["pl_design"]["card_name"], "s2a.bit")
        self.assertEqual(self.base["image_sha256"], json.loads(s1a_run.STAGES["s2_1"]["expected"].read_text())["image_sha256"], "one image for every set")

    def test_a_share_fills_in_the_list_and_what_follows_from_its_length(self) -> None:
        for k, reads in enumerate(s2_2_shares.shares(CENSUS)):
            exp = s1a_run.with_share("s2_2", self.base, k)
            par = [int(w, 16) for w in exp["params"]]
            self.assertTrue(s2_2_judge.params_valid(par))
            self.assertEqual(par[16], len(reads))
            self.assertEqual([int(w, 16) for w in exp["list"]], s2_2_shares.list_words(reads))
            records = 4 + 3 * len(reads)
            self.assertEqual((exp["records"], exp["result_words"]), (records, HB + records * REC))
            self.assertLessEqual(exp["result_words"], 0x40000, "the result area")
            self.assertEqual(exp["console"][1], "SM8 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (records, exp["result_words"]))
            self.assertEqual(exp["share"]["index"], k)
            self.assertEqual(s1a_run.planned_words(exp), par + s2_2_shares.list_words(reads))
        self.assertEqual(s1a_run.with_share("s2_2", self.base, 3)["share"],
                         {"index": 3, "of": 8, "reads": 176, "frames": 524, "first": "0x00001680", "last": "0x004001a3"})

    def test_what_is_refused(self) -> None:
        for share in (-1, 8):
            with self.assertRaises(ValueError):
                s1a_run.with_share("s2_2", self.base, share)
        with self.assertRaises(ValueError):
            s1a_run.with_share("s2_1", self.base, 0)
        for args, says in ((["--stage", "s2_2"], "REFUSED: s2_2 is run a share at a time (--share)"), (["--stage", "s2_2", "--share", "8"], "REFUSED: there are 8 shares"),
                           (["--stage", "s2_1", "--share", "0"], "REFUSED: s2_1 has no shares")):
            p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), *args, "--dry-run"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn(says, p.stdout)

    def test_the_dry_run_says_how_long_the_result_is_for_the_layout_of_the_stage(self) -> None:
        """Review of 9fa606e: it said 64 + 480 N words for every stage; with the PL block the records begin later."""
        for args, size in ((("--stage", "s2_2", "--share", "0"), "2960+480*N"), (("--stage", "s2_1"), "2640+480*N"), (("--stage", "s1b4"), "64+480*N"),
                           (("--stage", "s1a"), "64+266*N")):
            with self.subTest(args):
                text = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), *args, "--dry-run"], capture_output=True, text=True).stdout
                self.assertEqual(sorted(set(re.findall(r"<(?:4\*\()?(\d+\+\d+\*N)\)?>", text))), [size])
                self.assertEqual(len(re.findall(re.escape(size), text)), 2, "the checksum's length and the pull's")
        self.assertEqual((s2_2_judge.HDR, s2_2_judge.REC), (2960, 480))

    def test_a_dry_run_given_a_directory_says_what_the_run_would_say_of_it(self) -> None:
        tmp = Path(scratch_dirs.mkdtemp(prefix="smdry_"))
        dry = lambda out: subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_2", "--share", "0", "--dry-run", "--out", str(out)],  # noqa: E731
                                         capture_output=True, text=True)
        p = dry(tmp / "new")
        self.assertEqual((p.returncode, p.stdout.strip().splitlines()[-1], (tmp / "new").exists()), (0, "Dry run: nothing was sent.", False))
        p = dry(tmp)
        self.assertEqual((p.returncode, p.stdout.strip()), (2, "REFUSED: --out must name a directory that does not exist yet"))

    def test_the_dry_run_lists_the_list_s_transfer_and_its_checksum_and_sends_nothing(self) -> None:
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_2", "--share", "7", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("stage s2_2, share 7 of 8: 82 reads, 244 frames, 0x00401880 .. 0x00401ba9", p.stdout)
        self.assertRegex(p.stdout, r"loady 10180000 +# send the list of reads \(82 reads, 328 bytes\) by YMODEM")
        self.assertRegex(p.stdout, r"crc32 10180000 148 +# the list in RAM is the list")
        self.assertIn("md.l 40000000 1", p.stdout)
        self.assertIn("Dry run: nothing was sent.", p.stdout)

    def test_the_steps_before_go(self) -> None:
        exp = s1a_run.with_share("s2_2", self.base, 7)
        steps = s1a_run.before_go(dict(exp, list_file="/somewhere/list.bin"), 2083859, "6a1efe06")
        cmds = [s["cmd"] for s in steps]
        at = cmds.index("loady 10180000")
        self.assertEqual((steps[at]["ymodem"], steps[at]["size"]), ("/somewhere/list.bin", 328))
        self.assertEqual(steps[at + 1]["cmd"], "crc32 10180000 148")
        self.assertEqual(steps[at + 1]["crc"], f"{zlib.crc32(s1a_run.list_bytes(exp)) & 0xFFFFFFFF:08x}")
        self.assertLess(cmds.index("crc32 10100000 80"), at, "after the parameter block")
        self.assertLess(at, cmds.index("loady 02000000"), "before the prober is sent")
        self.assertLess(cmds.index("md.l 40000000 1"), cmds.index("mw.l 10100000 0 20"), "the design is asked at the prompt before anything is prepared")
        self.assertEqual([c for c in cmds if c.startswith("md.l f8000")], ["md.l f8000900 1", "md.l f8000240 1", "md.l f8000170 1", "md.l f800010c 1"])
        self.assertNotIn("loady 10180000", [s["cmd"] for s in s1a_run.before_go(json.loads(s1a_run.STAGES["s2_1"]["expected"].read_text()), 2083859, "6a1efe06")])


class ThroughTheRunScript(unittest.TestCase):
    def test_a_share_of_the_made_up_device(self) -> None:
        rec, u, out = run8(1, T.census(), LIMIT)
        self.assertEqual((rec["verdict"], rec["problems"], rec["judge"]), ("PASS", [], "PASS"))
        self.assertEqual(rec["share"], {"index": 1, "of": 3, "reads": 10, "frames": 30, "first": "0x00000b80", "last": "0x00000b9d"})
        self.assertEqual((rec["result_layout"], rec["result_words"], rec["pl_source"]), ("s2_2", HB + 34 * REC, "card"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertEqual(rec["console"], ["SM8 start", "SM8 end status=00000001 records=00000022 anomalies=00000000 words=%08x" % (HB + 34 * REC)])
        v = json.loads((out / "verdict.json").read_text())
        self.assertEqual((v["finding"]["bits"]["candidates"], v["finding"]["frames"]), (256, 30))
        self.assertEqual(u.blobs[s1a_run.LIST_ADDR], (out / "list.bin").read_bytes())
        self.assertIn("fatload mmc 0:1 04000000 s2a.bit", u.commands)
        self.assertLess(u.commands.index("md.l 40000000 1"), u.commands.index("loady 10180000"))
        self.assertLess(u.commands.index("crc32 10180000 28"), u.commands.index("go 02000000"))

    def test_a_real_share_across_the_end_of_the_row_and_the_last_one(self) -> None:
        for share, reads, frames in ((3, 176, 524), (7, 82, 244)):
            with self.subTest(share=share):
                rec, u, out = run8(share)
                self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
                self.assertEqual((rec["share"]["reads"], rec["share"]["frames"]), (reads, frames))
                v = json.loads((out / "verdict.json").read_text())
                self.assertEqual((v["finding"]["frames"], v["finding"]["bits"]["candidates"]), (frames, 256))
                self.assertEqual(rec["result_words"], HB + (4 + 3 * reads) * REC)
                self.assertFalse([e for e in u.twin_lines if e.startswith("VIOLATION")])

    def test_a_list_that_did_not_arrive_whole_stops_the_run_before_go(self) -> None:
        rec, u, out = run8(0, T.census(), LIMIT, corrupt_list=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("crc32 10180000 1c", rec["stop"])
        self.assertNotIn("go 02000000", u.commands)
        self.assertFalse(rec.get("went"))

    def test_a_restart_shown_in_the_reply_to_the_list_s_transfer_stops_the_run(self) -> None:
        probe, _, _ = run8(0, T.census(), LIMIT)
        at = next(s["n"] for s in probe["steps"] if s["cmd"] == "loady 10180000")
        rec, u, out = run8(0, T.census(), LIMIT, restarts_after_transfer_at=(at,))
        self.assertEqual(rec["restart"]["cmd"], "loady 10180000")
        self.assertEqual(u.commands[-1], "loady 10180000", "nothing more was sent")

    def test_the_design_that_does_not_answer_at_the_prompt(self) -> None:
        rec, u, out = run8(0, T.census(), LIMIT, pl_does_not_answer=True)
        self.assertEqual((rec["verdict"], u.commands[-1]), ("FAIL", "md.l 40000000 1"))
        self.assertNotIn("loady 10180000", u.commands)

    def test_what_the_twin_says_no_to_fails_through_the_run_script_as_well(self) -> None:
        for fault, status in (("ramdisturb@6", "0xa09"), ("seu", "0x105"), ("err@11", "0x221")):
            with self.subTest(fault):
                rec, u, out = run8(0, T.census(), LIMIT, fault=fault)
                self.assertEqual((rec["verdict"], rec["judge"], rec["return_code"]), ("FAIL", "FAIL", status))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result, "saved whole whatever it says")
                self.assertEqual(rec["card_verified"], True)

    def test_the_audit_s_way_of_judging_a_stored_run_is_the_run_script_s(self) -> None:
        rec, u, out = run8(2, T.census(), LIMIT)
        raw = (out / "result.bin").read_bytes()
        base = json.loads(s1a_run.STAGES["s2_2"]["expected"].read_text())
        exp = s1a_run.with_share("s2_2", base, rec["share"]["index"], T.census(), LIMIT)
        again = s2_2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), dict(DESIGN, census=T.census()), s1a_run.planned_words(exp))
        self.assertEqual(json.loads(json.dumps(again)), json.loads((out / "verdict.json").read_text()))


class Chain(unittest.TestCase):
    """The chain over the made-up device: three shares."""

    def setUp(self) -> None:
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain8_")) / "chain"
        self.base = json.loads(s1a_run.STAGES["s2_2"]["expected"].read_text())
        self.known = dict(DESIGN, census=T.census())
        self.calls: list[int] = []
        every = s2_2_shares.shares(T.census(), LIMIT)
        allr = [r for s in every for r in s]
        self.cells = cells_in(allr)                     # the 256 cells, somewhere in the whole device

    def runner(self, faults: dict | None = None, cells=None, **quirks):
        def run(share: int, out: Path) -> None:
            self.calls.append(share)
            run8(share, T.census(), LIMIT, fault=(faults or {}).get(share, ""), out=out, cells=self.cells if cells is None else cells, **quirks)
        return run

    def drive(self, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")     # the run directories here are in no repository: said to be committed, unless a test asks
        return s2_2_chain.drive(self.root, self.base, self.known, kw.pop("runner", self.runner()), limit=LIMIT, **kw)

    def edit_record(self, run: str, fn) -> None:
        f = self.root / run / "run.json"
        rec = json.loads(f.read_text()); fn(rec); f.write_text(json.dumps(rec))

    def why(self) -> list[str]:
        a = self.assess()
        self.assertEqual(a["state"], "halted")
        return a["why"]

    # ---- review of 9fa606e (docs/s2_plan.md, section 23)
    def test_no_second_run_is_started_before_the_first_is_committed(self) -> None:
        a = self.drive(committed=s2_2_chain.committed)   # the real question, of a directory that is in no repository
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no second run before the first is committed: run00", a["held"])
        self.assertNotIn("blocked", a, "a run is waited for; none failed to start")
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["held"], a["held"])
        asked: list[Path] = []
        a = self.drive(committed=lambda path: asked.append(path) or "run00 has files that are not committed as they stand")
        self.assertEqual((self.calls, asked, "held" in a), ([0], [self.root / "run00"], True), "nothing more is run, however often it is started")
        a = self.drive(max_new=5, committed=s2_2_chain.committed)
        self.assertEqual(self.calls, [0], "and --max-new does not get past it")
        a = self.drive()
        self.assertEqual((a["state"], self.calls, "held" in a), ("complete", [0, 1, 2], False))

    def test_what_committed_means(self) -> None:
        repo = Path(scratch_dirs.mkdtemp(prefix="smgit_"))
        git = lambda *args: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], check=True, capture_output=True)  # noqa: E731
        run = repo / "evidence" / "run00"
        self.assertIn("is not there", s2_2_chain.committed(run))
        run.mkdir(parents=True)
        self.assertIn("is not in a git repository", s2_2_chain.committed(run))
        git("init", "-q")
        self.assertIn("is not committed whole", s2_2_chain.committed(run), "an empty directory holds no run")
        (run / "result.bin").write_bytes(b"\x01\x02"); (run / "run.json").write_text("{}")
        self.assertIn("not in the last commit as they stand: ['result.bin', 'run.json']", s2_2_chain.committed(run), "a repository with no commit yet")
        git("add", "evidence/run00/run.json"); git("commit", "-q", "-m", "one of two")
        self.assertIn("['result.bin']", s2_2_chain.committed(run), "one file committed is not the run committed")
        git("add", "-A")
        self.assertIn("['result.bin']", s2_2_chain.committed(run), "added and not committed")
        git("commit", "-q", "-m", "the run")
        self.assertEqual(s2_2_chain.committed(run), "")
        (run / "result.bin").write_bytes(b"\x01\x03")
        self.assertIn("['result.bin']", s2_2_chain.committed(run), "a file changed since")
        # review of 334df53: a file git was told to assume unchanged, or to skip, shows in no `git status` — the bytes are what is held
        for flag, back in (("--assume-unchanged", "--no-assume-unchanged"), ("--skip-worktree", "--no-skip-worktree")):
            git("update-index", flag, "evidence/run00/result.bin")
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout, "", flag)
            self.assertIn("['result.bin']", s2_2_chain.committed(run), flag)
            git("update-index", back, "evidence/run00/result.bin")
        git("checkout", "-q", "--", "."); self.assertEqual(s2_2_chain.committed(run), "")
        (run / "result.bin").unlink()
        self.assertIn("['result.bin']", s2_2_chain.committed(run), "a file of the commit that is gone")
        git("checkout", "-q", "--", ".")
        (repo / ".gitignore").write_text("*.log\n"); git("add", ".gitignore"); git("commit", "-q", "-m", "ignore")
        (run / "console.log").write_text("x")
        self.assertIn("['console.log']", s2_2_chain.committed(run), "a file git ignores is a file that is not committed")
        (run / "console.log").unlink()
        self.assertEqual(s2_2_chain.committed(run), "")
        # review of c1e932b: links. One that leads nowhere was passed by; a file replaced by a link to the same bytes passed
        os.symlink("nowhere", run / "dangling")
        self.assertIn("holds something that is not a plain file: ['dangling']", s2_2_chain.committed(run))
        (run / "dangling").unlink()
        (repo / "copy.bin").write_bytes((run / "result.bin").read_bytes())
        (run / "result.bin").unlink(); os.symlink("../../copy.bin", run / "result.bin")
        self.assertEqual((run / "result.bin").read_bytes(), b"\x01\x02", "the same bytes are read through it")
        self.assertIn("holds something that is not a plain file: ['result.bin']", s2_2_chain.committed(run))
        git("add", "-A"); git("commit", "-q", "-m", "the link itself committed")
        self.assertIn("holds something that is not a plain file: ['result.bin']", s2_2_chain.committed(run), "committed or not, a link is not the result")
        (run / "result.bin").unlink(); (run / "result.bin").write_bytes(b"\x01\x02")
        self.assertIn("holds something that is not a plain file: ['result.bin']", s2_2_chain.committed(run), "the commit has a link where the file is")
        git("add", "-A"); git("commit", "-q", "-m", "the file again")
        self.assertEqual(s2_2_chain.committed(run), "")
        (run / "sub").mkdir(); os.symlink(".", run / "sub" / "loop")
        self.assertIn("['sub/loop']", s2_2_chain.committed(run), "a link to a directory, under a directory")
        (run / "sub" / "loop").unlink(); (run / "sub").rmdir()
        os.symlink("run00", run.parent / "run00link")
        self.assertIn("run00link is not there as a directory", s2_2_chain.committed(run.parent / "run00link"), "the run's directory itself")

    def test_nothing_is_sent_for_a_run_the_run_script_would_refuse(self) -> None:
        """Review of 334df53: the chain looked at the image kept with the runs, the run script loads the build's. With
        the two apart the board was reset, the script refused, and a run directory without a record halted the chain."""
        self.drive(max_new=1)
        self.assertEqual(s2_2_chain.ready(self.root, self.base), "")
        build = s1a_run.IMAGE
        other = Path(scratch_dirs.mkdtemp(prefix="smimg_")) / "prober.bin"
        other.write_bytes(build.read_bytes()[:-1] + bytes([build.read_bytes()[-1] ^ 1]))
        s1a_run.IMAGE = other
        self.addCleanup(setattr, s1a_run, "IMAGE", build)
        self.assertEqual(self.assess()["state"], "go on", "what is stored stands: the image kept with the runs is the set's")
        a = self.drive()
        self.assertEqual((a["state"], self.calls, (self.root / "run01").exists()), ("go on", [0], False), "no run was started and no directory left")
        self.assertEqual((a["held"], a["blocked"]), ("nothing was sent: the image of the build, which the run script would load, is not the image the set declares", True))
        stored = json.loads((self.root / "chain.json").read_text())
        self.assertEqual((stored["held"], stored["blocked"]), (a["held"], True))
        # a set that declares the build's image, while another is kept with the runs
        moved = dict(self.base, image_sha256=hashlib.sha256(other.read_bytes()).hexdigest(), image_crc32=f"{zlib.crc32(other.read_bytes()) & 0xFFFFFFFF:08x}")
        self.assertEqual(s2_2_chain.ready(self.root, moved), "the image of the build, which the run script would load, is not the image kept with the runs")
        s1a_run.IMAGE = other.parent / "none.bin"
        self.assertEqual(s2_2_chain.ready(self.root, self.base), "there is no image of the build for the run script to load")
        s1a_run.IMAGE = build
        self.assertEqual(self.drive()["state"], "complete")

    def test_the_run_script_s_own_dry_run_says_what_the_run_would_be_refused_for(self) -> None:
        tmp = Path(scratch_dirs.mkdtemp(prefix="smref_"))
        self.assertEqual(s2_2_chain.refusal(0, tmp / "run00"), "")
        self.assertFalse((tmp / "run00").exists(), "and it makes nothing")
        self.assertTrue(s2_2_chain.refusal(8, tmp / "run00").startswith("REFUSED: "), s2_2_chain.refusal(8, tmp / "run00"))
        # review of c1e932b: the directory the run is to write into is part of what is asked
        (tmp / "a_file").write_text("x"); (tmp / "a_dir").mkdir(); os.symlink("nowhere", tmp / "a_link")
        for name in ("a_file", "a_dir", "a_link"):
            self.assertEqual(s2_2_chain.refusal(0, tmp / name), "REFUSED: --out must name a directory that does not exist yet", name)

    def test_what_the_run_script_would_refuse_is_asked_before_the_runner_and_stands_in_the_chain_s_file(self) -> None:
        """Review of c1e932b: the refusal was raised inside the runner; the command said HALT while chain.json said
        "go on" and gave no reason. The asking is the driver's now, before the runner — which on the board resets it."""
        asked: list = []

        def refuses(share: int, out: Path) -> str:
            asked.append((share, out)); return "the run script refuses the run (REFUSED: for the test)"
        a = self.drive(refuses=refuses, runner=lambda *_: self.fail("the runner was called"))
        self.assertEqual((a["state"], a["held"], a["blocked"]), ("go on", "nothing was sent: the run script refuses the run (REFUSED: for the test)", True))
        self.assertEqual(asked, [(0, self.root / "run00")])
        stored = json.loads((self.root / "chain.json").read_text())
        self.assertEqual((stored["state"], stored["held"], stored["blocked"]), ("go on", a["held"], True))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["chain.json"], "no directory for the run, and no image kept for a run that was not made")
        a = self.drive(max_new=1)
        self.assertEqual((self.calls, "held" in a, "blocked" in a), ([0], False, False))
        self.assertNotIn("held", json.loads((self.root / "chain.json").read_text()), "what held it is gone once it goes on")
        a = self.drive(refuses=refuses, runner=lambda *_: self.fail("the runner was called"))
        self.assertEqual((asked[-1], a["blocked"], (self.root / "run01").exists()), ((1, self.root / "run01"), True, False))

    def test_a_runner_that_could_not_begin_holds_the_chain_and_says_so_in_its_file(self) -> None:
        def runner(share: int, out: Path) -> None:
            raise RuntimeError(f"before {out.name}: reset did not give the usual fresh prompt; nothing was run")
        a = self.drive(runner=runner)
        self.assertEqual((a["state"], a["held"], a["blocked"]), ("go on", "before run00: reset did not give the usual fresh prompt; nothing was run", True))
        stored = json.loads((self.root / "chain.json").read_text())
        self.assertEqual((stored["held"], stored["blocked"], (self.root / "run00").exists()), (a["held"], True, False))

    def test_the_command_ends_with_a_code_when_a_run_could_not_be_started(self) -> None:
        import contextlib, io
        build = s1a_run.IMAGE
        other = Path(scratch_dirs.mkdtemp(prefix="smimg_")) / "prober.bin"
        other.write_bytes(build.read_bytes()[:-1] + bytes([build.read_bytes()[-1] ^ 1]))
        root = Path(scratch_dirs.mkdtemp(prefix="smcmd_")) / "chain"
        root.mkdir()
        (root / "prober.bin").write_bytes(build.read_bytes())   # the image kept with the runs is the set's: what is stored stands
        keep_argv, keep_log = sys.argv, os.environ.get("SELFMAP_CONSOLE_LOG")
        self.addCleanup(setattr, s1a_run, "IMAGE", build)
        self.addCleanup(setattr, sys, "argv", keep_argv)
        self.addCleanup(lambda: os.environ.pop("SELFMAP_CONSOLE_LOG", None) if keep_log is None else os.environ.__setitem__("SELFMAP_CONSOLE_LOG", keep_log))
        s1a_run.IMAGE = other                            # the image the run script would load is not the set's: nothing is opened, nothing sent
        sys.argv = ["s2_2_chain.py", "--dir", str(root), "--go"]
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            rc = s2_2_chain.main()
        self.assertEqual(rc, 1)
        self.assertIn("HELD: nothing was sent: the image of the build", said.getvalue())
        self.assertIn("0 run(s) stored of 8; the chain: go on", said.getvalue())
        stored = json.loads((root / "chain.json").read_text())
        self.assertEqual((stored["state"], stored["blocked"], stored["held"].startswith("nothing was sent: ")), ("go on", True, True))
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["chain.json", "prober.bin"])

    def test_a_run_s_name_taken_by_something_that_is_not_a_directory_halts_the_chain_before_anything_is_asked(self) -> None:
        """Review of c1e932b: only directories were looked at. With a file called run00 the chain took run00 for the
        next run, the board was reset, and the run script then refused the directory."""
        self.root.mkdir(parents=True)
        (self.root / "run00").write_text("not a directory")
        self.assertEqual(self.why(), ["what has the name of a run and is not a directory: ['run00']"])
        a = self.drive(runner=lambda *_: self.fail("the runner was called"), refuses=lambda *_: self.fail("the run script was asked"))
        self.assertEqual((a["state"], json.loads((self.root / "chain.json").read_text())["state"]), ("halted", "halted"))
        (self.root / "run00").unlink()
        self.drive(max_new=1)
        os.symlink("nowhere", self.root / "run01")       # a link that leads nowhere, where the next run is to be
        self.assertEqual(self.why(), ["what has the name of a run and is not a directory: ['run01']"])
        (self.root / "run01").unlink()
        os.symlink("run00", self.root / "run01")         # a link to a run's directory is not a second run
        self.assertEqual(self.why(), ["what has the name of a run and is not a directory: ['run01']"])
        (self.root / "run01").unlink()
        (self.root / "run07").write_text("")             # nor further on
        self.assertEqual(self.why(), ["what has the name of a run and is not a directory: ['run07']"])
        (self.root / "run07").unlink()
        self.assertEqual(self.drive()["state"], "complete")

    def test_the_driver_keeps_the_image_with_the_runs_and_the_chain_says_what_it_was_made_with(self) -> None:
        a = self.drive(max_new=1)
        self.assertEqual((self.root / "prober.bin").read_bytes(), s1a_run.IMAGE.read_bytes())
        pl = s1a_run.pl_file(self.base).read_bytes()
        self.assertEqual(a["made_with"], {"image_bytes": self.base["image_bytes"], "image_crc32": self.base["image_crc32"], "image_sha256": self.base["image_sha256"],
                                          "image_from": "kept with the runs", "design_bytes": len(pl), "design_crc32": f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}",
                                          "design_sha256": self.base["pl_design"]["sha256"]})
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["made_with"], a["made_with"])

    def test_stored_runs_are_held_to_the_image_and_the_design_the_set_declares(self) -> None:
        """The review's case: with the two declared hashes changed, the stored runs still passed and the chain went on."""
        self.drive(max_new=2)
        good = self.base
        self.base = dict(good, image_sha256="0" * 64)
        self.assertEqual(self.why(), ["the image kept with the runs is not the image the set declares"])
        self.base = dict(good, pl_design=dict(good["pl_design"], sha256="0" * 64))
        self.assertEqual(self.why(), ["the staged design is not the design the set declares"])
        self.base = dict(good, pl_design=dict(good["pl_design"], file="build/pl/nothing.bit"))
        self.assertEqual(self.why(), ["the design the set declares is not staged (build/pl/nothing.bit)"])
        self.base = {k: v for k, v in good.items() if k != "pl_design"}
        self.assertEqual(self.why(), ["the set declares no design"])
        self.base = good
        self.assertEqual(self.assess()["state"], "go on")
        self.assertEqual(self.drive(runner=lambda *_: self.fail("a run was started"), max_new=0)["state"], "go on")
        # the image kept with the runs is not the build's any more: another image was built since the chain began
        kept = (self.root / "prober.bin").read_bytes()
        (self.root / "prober.bin").write_bytes(kept[:-1] + bytes([kept[-1] ^ 1]))
        self.assertEqual(self.why(), ["the image kept with the runs is not the image the set declares"])
        self.base = dict(good, image_sha256=hashlib.sha256((self.root / "prober.bin").read_bytes()).hexdigest(),
                         image_crc32=f"{zlib.crc32((self.root / 'prober.bin').read_bytes()) & 0xFFFFFFFF:08x}")
        why = self.why()                                 # and a set that declares the other image: the runs were not made with it
        self.assertTrue(why[0].startswith(f"run00: the run record does not show the declared image (crc32 {self.base['image_crc32']}) in RAM just before"), why)
        self.assertEqual(self.calls, [0, 1])

    def test_what_a_run_s_record_must_show_of_the_image_the_design_and_the_list(self) -> None:
        self.drive()
        self.assertEqual(self.assess()["state"], "complete")
        keep = (self.root / "run01" / "run.json").read_text()
        image = f"crc32 {s1a_run.IMG_ADDR:08x} {self.base['image_bytes']:x}"
        design = f"crc32 {s1a_run.PL_ADDR:08x} {self.base['pl_design']['bytes']:x}"
        listc = f"crc32 {s1a_run.LIST_ADDR:08x}"

        def steps_of(rec: dict, cmd: str) -> list[int]:
            return [n for n, s in enumerate(rec["steps"]) if s["cmd"].startswith(cmd)]

        def other(reply: str) -> str:                    # the same reply with another checksum in it
            return re.sub(r"==> ([0-9a-f]{8})", lambda m: "==> %08x" % (int(m.group(1), 16) ^ 1), reply)

        cases = {
            "the image's checksum before the start is another": (lambda r: r["steps"][steps_of(r, image)[0]].update(reply=other(r["steps"][steps_of(r, image)[0]]["reply"])), "does not show the declared image"),
            "the image's checksum after the return is another": (lambda r: r["steps"][steps_of(r, image)[-1]].update(reply=other(r["steps"][steps_of(r, image)[-1]]["reply"])), "does not show the declared image"),
            "the image was not looked at after the return": (lambda r: r["steps"].pop(steps_of(r, image)[-1]), "does not show the declared image"),
            "the image's checksum is not the step before the start": (lambda r: r["steps"].insert(steps_of(r, "go ")[0], {"n": 0, "cmd": "version", "reply": ""}), "does not show the declared image"),
            "the design's checksum is another": (lambda r: r["steps"][steps_of(r, design)[0]].update(reply=other(r["steps"][steps_of(r, design)[0]]["reply"])), "does not show the declared design"),
            "the design's checksum comes after its load": (lambda r: r["steps"].insert(steps_of(r, "fpga loadb")[0] + 1, r["steps"].pop(steps_of(r, design)[0])), "does not show the declared design"),
            "the design was loaded twice": (lambda r: r["steps"].append(dict(r["steps"][steps_of(r, "fpga loadb")[0]])), "does not show one load of the declared design"),
            "the prober was not started": (lambda r: r["steps"].pop(steps_of(r, "go ")[0]), "does not show one load of the declared design"),
            "the list's checksum is another": (lambda r: r["steps"][steps_of(r, listc)[0]].update(reply=other(r["steps"][steps_of(r, listc)[0]]["reply"])), "does not show the list planned for the share"),
            "the list was not looked at": (lambda r: r["steps"].pop(steps_of(r, listc)[0]), "does not show the list planned for the share"),
            "the steps are no list": (lambda r: r.update(steps="none"), "the run record has no list of steps"),
            "a step is no step": (lambda r: r["steps"].append(7), "the run record has no list of steps"),
        }
        for name, (change, says) in cases.items():
            with self.subTest(name):
                (self.root / "run01" / "run.json").write_text(keep)
                self.edit_record("run01", change)
                why = self.why()
                self.assertTrue(any(w.startswith("run01: ") and says in w for w in why), why)
        (self.root / "run01" / "run.json").write_text(keep)
        self.assertEqual(self.assess()["state"], "complete")
        blob = (self.root / "run01" / "list.bin").read_bytes()
        (self.root / "run01" / "list.bin").write_bytes(blob[:8] + bytes([blob[8] ^ 1]) + blob[9:])
        self.assertIn("run01: the list kept beside the run is not the list planned for its share", self.why())
        (self.root / "run01" / "list.bin").unlink()
        self.assertIn("run01: no list is kept beside the run", self.why())

    def test_a_record_that_is_not_a_record_halts_the_chain_and_does_no_more(self) -> None:
        self.drive(max_new=2)
        for text, says in (("[]", "the run record is not a record"), ('"x"', "the run record is not a record"), ("{", "there is no run record"),
                           ('{"stage": "s2_2", "share": "first", "steps": []}', "the run is of share None")):
            with self.subTest(text):
                (self.root / "run01" / "run.json").write_text(text)
                self.assertTrue(any(says in w for w in self.why()), self.why())
                a = self.drive(runner=lambda *_: self.fail("a run was started"))
                self.assertEqual(a["state"], "halted")

    def test_a_list_of_candidates_does_not_outlive_the_chain_it_was_written_for(self) -> None:
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], a["candidates_file"], (self.root / "candidates.json").is_file()), ("complete", "there", True))
        self.assertEqual(self.assess()["candidates_file"], "there")
        (self.root / "run02" / "list.bin").unlink()      # something of a stored run is not as it was
        a = self.assess()
        self.assertEqual((a["state"], a["candidates_file"]), ("halted", "there"), "looking takes nothing away, and says the file is there")
        self.assertTrue((self.root / "candidates.json").is_file())
        a = self.drive(say=said.append, runner=lambda *_: self.fail("a run was started"))
        self.assertEqual((a["state"], "candidates_file" in a, (self.root / "candidates.json").exists()), ("halted", False, False))
        self.assertIn("candidates.json taken away: the chain is not complete as it is stored now", said)
        self.assertNotIn("candidates_file", json.loads((self.root / "chain.json").read_text()))

    def assess(self) -> dict:
        return s2_2_chain.assess(self.root, self.base, self.known, LIMIT)

    def test_three_runs_and_the_step_is_closed(self) -> None:
        a = self.drive()
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", [0, 1, 2], ["go on", "go on", "complete"]))
        c = a["closing"]
        self.assertEqual((c["addresses_read"], c["candidates"], c["cells_in_the_design"], c["problems"]), (55, 256, 256, []))
        self.assertTrue(c["outcome"].startswith("1: as many candidates as the RAM has cells"))
        self.assertEqual({(x["far"], x["word"], x["bit"], x["inverted"]) for x in c["found"]}, places(self.cells))
        self.assertEqual(sum(c["frames_with_candidates"].values()), 256)
        self.assertEqual(c["ctl0"], ["0x00000501"])
        f = json.loads((self.root / "candidates.json").read_text())
        self.assertEqual((f["label"], f["candidates"], len(f["places"]), f["design"]), ("closed-book", 256, 256, "s2a"))
        self.assertEqual([r["share"] for r in f["runs"]], [0, 1, 2])
        self.assertTrue(all(p["run"] in ("run00", "run01", "run02") for p in f["places"]))
        b = json.loads((self.root / "chain.json").read_text())
        self.assertEqual((b["state"], [r["candidates"] for r in b["runs"]]), ("complete", [len(r["candidates"]) for r in a["runs"]]))
        self.assertNotIn("found", b["closing"])
        self.assertEqual(self.assess()["state"], "complete", "and it stands so when looked at again")

    def test_looking_at_a_chain_writes_nothing_and_runs_nothing(self) -> None:
        a = self.assess()
        self.assertEqual(a.pop("made_with")["image_from"], "of the build", "no run yet, so no image kept with the runs")
        self.assertEqual(a, {"stage": "s2_2", "shares": 3, "runs": [], "set_aside": [], "state": "go on", "next_run": 0, "next_share": 0})
        self.assertFalse(self.root.exists())
        self.drive(max_new=1)
        before = sorted(p.name for p in self.root.iterdir())
        a = self.assess()
        self.assertEqual((a["state"], a["next_share"], self.calls), ("go on", 1, [0]))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_it_goes_on_where_it_stands(self) -> None:
        self.drive(max_new=2)
        self.assertEqual(self.calls, [0, 1])
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("complete", [0, 1, 2]))

    def test_a_run_that_is_not_a_passing_run_halts_the_chain_and_nothing_is_run_again(self) -> None:
        for name, kw, says in (("the RAM did not hold", {"faults": {1: "ramdisturb@6"}}, "the run script's verdict is FAIL"),
                               ("a read failed", {"faults": {1: "err@11"}}, "the run script's verdict is FAIL"),
                               ("a gate", {"faults": {1: "seu"}}, "the run script's verdict is FAIL")):
            with self.subTest(name):
                self.setUp()
                a = self.drive(runner=self.runner(**kw))
                self.assertEqual((a["state"], self.calls, a["runs"][-1]["decision"]), ("halted", [0, 1], "halt"))
                self.assertTrue(any(says in w for w in a["why"]), a["why"])
                again = self.drive(runner=self.runner())
                self.assertEqual((again["state"], self.calls), ("halted", [0, 1]), "the run directory stays, and nothing is run in its place")
                self.assertFalse((self.root / "candidates.json").exists())

    def test_a_restart_halts_it(self) -> None:
        probe, _, _ = run8(0, T.census(), LIMIT)
        at = next(s["n"] for s in probe["steps"] if s["cmd"].startswith("go "))
        a = self.drive(runner=self.runner(restarts_at=(at,)))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertTrue(any("a reply showed an exception or a restart" in w for w in a["why"]), a["why"])

    def test_a_run_that_left_nothing_behind_halts_it(self) -> None:
        a = s2_2_chain.drive(self.root, self.base, self.known, lambda share, out: None, limit=LIMIT)
        self.assertEqual((a["state"], a["why"]), ("halted", ["run00: there is no run record"]))

    def test_what_is_stored_is_judged_again_and_must_be_what_it_was(self) -> None:
        self.drive()
        d = self.root / "run01"

        def changed(edit, says: str) -> None:
            keep = {p.name: p.read_bytes() for p in d.iterdir()}
            edit()
            a = self.assess()
            self.assertEqual(a["state"], "halted", says)
            self.assertTrue(any(says in w for w in a["why"]), a["why"])
            self.assertTrue(any("run02" in w and "not looked at" in w for w in a["why"]))
            for name, data in keep.items():
                (d / name).write_bytes(data)
            self.assertEqual(self.assess()["state"], "complete")

        raw = (d / "result.bin").read_bytes()
        changed(lambda: (d / "result.bin").write_bytes(raw[:4000] + bytes([raw[4000] ^ 1]) + raw[4001:]), "the stored result is not the one whose checksum the board gave")
        rec = json.loads((d / "run.json").read_text())
        put = lambda **kw: (d / "run.json").write_text(json.dumps(dict(rec, **kw)))   # noqa: E731
        changed(lambda: put(share=dict(rec["share"], index=2)), "the run is of share 2; the chain plans share 1 for it")
        changed(lambda: put(stage="s2_1"), "the run record is of stage s2_1")
        changed(lambda: put(verdict="FAIL"), "the run script's verdict is FAIL")
        changed(lambda: put(stop="something"), "the run script stopped: something")
        changed(lambda: put(went=False), "the prober was not started")
        changed(lambda: put(card_verified=False), "the card copy was not verified")
        changed(lambda: put(restart={"step": 3}), "a reply showed an exception or a restart")
        changed(lambda: (d / "run.json").unlink(), "there is no run record")
        changed(lambda: (d / "result.bin").unlink(), "there is no stored result")
        v = json.loads((d / "verdict.json").read_text())
        changed(lambda: (d / "verdict.json").write_text(json.dumps(dict(v, finding=dict(v["finding"], candidates=[])))), "the verdict stored beside the result is not what the judge says")
        changed(lambda: (d / "verdict.json").unlink(), "the verdict stored beside the result is not what the judge says")

    def test_a_result_that_is_another_share_s_fails_the_judge(self) -> None:
        self.drive()
        a, b = self.root / "run00", self.root / "run02"
        rec = json.loads((b / "run.json").read_text())
        for name in ("result.bin", "verdict.json"):
            (a / name).write_bytes((b / name).read_bytes())
        ra = json.loads((a / "run.json").read_text())
        (a / "run.json").write_text(json.dumps(dict(ra, board_crc32=rec["board_crc32"])))
        s = self.assess()
        self.assertEqual(s["state"], "halted")
        self.assertTrue(any("run00: the judge says" in w for w in s["why"]), s["why"])

    def test_gaps_and_too_many(self) -> None:
        self.drive()
        (self.root / "run03").mkdir()
        self.assertEqual(self.assess()["why"], ["4 run directories for 3 shares"])
        (self.root / "run03").rmdir()
        (self.root / "run01").rename(self.root / "run01_aside")
        a = self.assess()
        self.assertEqual((a["state"], a["set_aside"]), ("halted", ["run01_aside"]))
        self.assertIn("without a gap", a["why"][0])

    def closing_with(self, cells) -> dict:
        a = self.drive(runner=self.runner(cells=cells))
        self.assertEqual(a["state"], "complete")
        return a["closing"]

    def test_the_outcomes_the_plan_named(self) -> None:
        for name, cells, n, begins in (("none", [], 0, "2: no candidate"), ("fewer", self.cells[:200], 200, "3: fewer candidates (200) than the RAM has cells (256)"),
                                       ("more", self.cells + [(0, 0, 0xA01, 50, 5, 0)], 257, "4: more candidates (257) than the RAM has cells (256)"),
                                       ("some inverted", [c[:5] + (1,) for c in self.cells[:30]] + self.cells[30:], 256, "1: as many candidates")):
            with self.subTest(name):
                self.setUp()
                c = self.closing_with(cells)
                self.assertEqual(c["candidates"], n)
                self.assertTrue(c["outcome"].startswith(begins), c["outcome"])
                if name == "some inverted":
                    self.assertTrue(c["outcome"].endswith("30 of them inverted (5)"))
                    self.assertEqual(c["candidates_inverted"], 30)

    def test_bit_5_is_reported_by_run(self) -> None:
        a = self.drive(runner=self.runner(faults={1: "bit5@6"}))
        self.assertEqual((a["state"], a["closing"]["bit_5"]), ("complete", {"run01": [6]}))

    def test_what_the_closing_holds_the_runs_to(self) -> None:
        self.drive()
        a = self.assess()
        runs = json.loads(json.dumps(a["runs"]))
        c = s2_2_chain.close(runs, T.census(), 256)
        self.assertEqual(c["problems"], [])
        fewer = json.loads(json.dumps(runs)); fewer[1]["frames"] -= 1
        self.assertEqual(s2_2_chain.close(fewer, T.census(), 256)["problems"], ["the runs read 54 addresses; block type 0 has 55 in the census"])
        twice = json.loads(json.dumps(runs)); twice[0]["candidates"].append(dict(twice[1]["candidates"][0]))
        self.assertIn("a place is a candidate in two runs: the shares are not apart", s2_2_chain.close(twice, T.census(), 256)["problems"])
        ctl = json.loads(json.dumps(runs)); ctl[2]["ctl0"] = "0x00000401"
        self.assertIn("CTL0 did not read the same in every run: ['0x00000401', '0x00000501']", s2_2_chain.close(ctl, T.census(), 256)["problems"])

    def test_runs_that_pass_each_alone_and_do_not_agree_halt_the_chain(self) -> None:
        """CTL0 reads as another value all through one run: that run's judge has nothing against it (it holds the two
        reads of a run to each other), the closing has, and what the closing has against the runs halts the chain."""
        plain, other = self.runner(), self.runner(env={"SM_CREG": "ctl0:00000401"})
        a = self.drive(runner=lambda share, out: (other if share == 1 else plain)(share, out))
        self.assertEqual([(r["decision"], r["problems"], r["ctl0"]) for r in a["runs"]],
                         [("go on", [], "0x00000501"), ("go on", [], "0x00000401"), ("complete", [], "0x00000501")])
        self.assertEqual((a["state"], a.get("why")), ("halted", ["CTL0 did not read the same in every run: ['0x00000401', '0x00000501']"]))
        self.assertFalse((self.root / "candidates.json").exists(), "no candidates are written for a chain that is halted")
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["state"], "halted")
        self.assertEqual(self.assess()["state"], "halted", "and it is halted when it is looked at again")

    def test_the_real_census_makes_eight(self) -> None:
        a = s2_2_chain.assess(self.root, self.base, s1a_run.known_for("s2_2"))
        self.assertEqual((a["shares"], a["state"], a["next_share"]), (8, "go on", 0))


class NothingOfThePart(unittest.TestCase):
    def test_the_programs_of_this_step_name_no_database_and_carry_no_number_of_the_part(self) -> None:
        """Closed-book, for the sources: what they know of the device they take from the census at run time."""
        for name in ("s2_2_shares.py", "s2_2_judge.py", "s2_2_chain.py"):
            text = (ROOT / "host" / name).read_text().lower()
            for word in ("prjxray", "segbits", "tilegrid", "part.json", "frame_count", "grade_", "1ba", "400000", "800000", "slice_x"):
                self.assertNotIn(word, text, f"{name}: {word}")
        core = (ROOT / "prober" / "sm_core.c").read_text()
        stage8 = core[core.index("stage 8 (S2.2)"):core.index("/* ------------------------------------------------------------------ stage S1a")]
        for word in ("1ba", "400000", "800000", "0xb9"):
            self.assertNotIn(word, stage8.lower(), word)


if __name__ == "__main__":
    unittest.main()

"""S2.3 on the host — docs/s2_plan.md, sections 29 and 30: the states and the two lists, the judge, the table, the run
script's part, and the chain of five runs.

The device, the design and where the cells of the RAM show are models (prober/twin_hal.c; the made-up device of the
stage-8 tests, with the 256 cells put into one of its columns). What is asked here is whether the host says the right
thing of a result — a clean one, one from a device that does not behave, and one with a word changed."""
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

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_2_shares  # noqa: E402
import s2_3_chain  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_3_states as st  # noqa: E402
import s2_3_table  # noqa: E402
import test_prober_s2_2 as T8  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402
from test_prober_s2_3 import COLUMN_READS, DESIGN, FARBLK, FIXED, PL_COUNT, PL_RAM_DATA, PL_SRL_DATA, REC, Run  # noqa: E402
from test_s2_2_host import Board8, device  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "ram_map_v1.schema.json").read_text())
CENSUS = json.loads(s2_2_shares.CENSUS.read_text())
REAL_CANDIDATES = json.loads(st.CANDIDATES.read_text())
DATA, FRAME = 76, 101


def candidates_of(cells) -> dict:
    """What S2.2 would have written of a device whose cells show at these places: the frames and the places."""
    return {"frames_with_candidates": {f"{far:#010x}": 0 for far in sorted({c[2] for c in cells})},
            "places": [{"far": f"{far:#010x}", "word": word, "bit": bit, "inverted": bool(inv)} for _, _, far, word, bit, inv in cells]}


CELLS = T.ram_map()                                   # the 256 cells, in three frames of the first column of the made-up device
KNOWN = dict(DESIGN, census=T8.census(), candidates=candidates_of(CELLS))


def known_for(cells) -> dict:
    return dict(DESIGN, census=T8.census(), candidates=candidates_of(cells))


def plan(kind: str, share: int | None = None, known: dict = KNOWN) -> dict:
    return st.plan(kind, share, known, known["census"], known["candidates"])


def twin(kind: str = "code", share: int | None = None, fault: str = "", cells=None, known: dict | None = None, **over) -> tuple[dict, Run]:
    """One run of the step on the twin: the plan made as the host makes it, and what the prober did with it."""
    cells = CELLS if cells is None else cells
    p = plan(kind, share, known_for(cells) if known is None else known)
    return p, Run(states=p["states"], reads=p["reads"], cells=cells, fault=fault, w19=p["may_write"], **over)


def planned(p: dict, r: Run) -> list[int]:
    return s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN)


def judged(p: dict, r: Run, known: dict | None = None, words=None, plan_words=None) -> dict:
    return s2_3_judge.judge(r.words if words is None else words, known_for(r.cells) if known is None else known, planned(p, r) if plan_words is None else plan_words)


def where(cells) -> dict:
    return {(f"{far:#010x}", word, bit): (mem * st.DEPTH + addr, bool(inv)) for addr, mem, far, word, bit, inv in cells}


_memo: dict = {}


def once(name: str, make):
    if name not in _memo:
        _memo[name] = make()
    return _memo[name]


def clean(kind: str = "code", share: int | None = None) -> tuple[dict, Run, dict]:
    def make():
        p, r = twin(kind, share)
        return p, r, judged(p, r)
    return once(("clean", kind, share), make)


class States(unittest.TestCase):
    def test_a_cell_s_number(self) -> None:
        self.assertEqual((st.number(0, 0), st.number(0, 63), st.number(1, 0), st.number(3, 63), st.CELLS), (0, 63, 64, 255, 256))

    def test_in_a_code_state_every_cell_holds_that_bit_of_its_number_and_in_the_complement_the_opposite(self) -> None:
        for j in range(8):
            for n in range(st.CELLS):
                self.assertEqual(st.cell(st.code(j), n), n >> j & 1, (j, n))
                self.assertEqual(st.cell(st.code(j, True), n), 1 - (n >> j & 1), (j, n))
        self.assertEqual(st.code(0)[:4], [0, 0xF, 0, 0xF], "bit 0 of the number is bit 0 of the address, in all four memories")
        self.assertEqual((st.code(6), st.code(7)), ([0xA] * 64, [0xC] * 64), "bits 6 and 7 are the memory: the same at every address")

    def test_the_code_run_tells_every_cell_from_every_other(self) -> None:
        states = st.code_run()
        self.assertEqual([s["name"] for s in states][:5], ["base", "code 0", "code 0 complement", "code 1", "code 1 complement"])
        self.assertEqual((len(states), states[0]["ram"], states[-1]["ram"]), (18, [0] * 64, [0] * 64))
        rows = {tuple(st.cell(s["ram"], n) for s in states) for n in range(st.CELLS)}
        self.assertEqual(len(rows), 256)
        self.assertFalse(rows & {tuple(1 - v for v in row) for row in rows}, "and no cell's row is the opposite of another's: inverted is told from as written")

    def test_a_single_sets_one_cell(self) -> None:
        for n in (0, 63, 64, 200, 255):
            self.assertEqual([m for m in range(st.CELLS) if st.cell(st.single(n), m)], [n])
        runs = [st.single_run(r) for r in range(4)]
        self.assertEqual([len(r) for r in runs], [66] * 4)
        self.assertEqual(sorted(s["cell"] for r in runs for s in r if s["kind"] == "single"), list(range(256)), "every cell once, over the four runs")
        self.assertEqual([(r[0]["kind"], r[-1]["kind"]) for r in runs], [("base", "base")] * 4)
        self.assertRaises(ValueError, st.single_run, 4)

    def test_the_list_of_accesses_is_one_the_prober_takes(self) -> None:
        for states in (st.code_run(), st.single_run(1)):
            e = st.accesses(states, DESIGN)
            words = st.acc_words(e, DESIGN)
            par = [0] * 32
            par[7], par[18], par[19], par[24], par[25] = len(states), len(e), st.may_write(e, DESIGN), 0x40000000, 0x4000001F
            self.assertEqual(s2_3_judge.entries_problems(s2_3_judge.entries_of(words), par), [])
            self.assertEqual(sum(1 for kind, _, _ in e if kind == st.A_MARK), 2 * len(states))
            self.assertEqual(st.may_write(e, DESIGN), 1 << 0x0C | 1 << 0x10 | 1 << 0x14, "the two address registers and the RAM's data; never the shift registers' data")
            self.assertTrue(all(w < 0x20 | 3 for w in words[0::2]), "the list has offsets, not addresses")

    def test_what_the_list_does_for_a_state(self) -> None:
        e = st.accesses(st.code_run(), DESIGN)
        marks = [i for i, (kind, _, _) in enumerate(e) if kind == st.A_MARK]
        first, after = e[:marks[0]], e[marks[0] + 1:marks[1]]
        reg = st.registers(DESIGN)
        self.assertEqual(len(first), 64 + 128 + 128 + 1, "the shift registers; the RAM written whole; read back whole; the counter")
        self.assertEqual([x for x in first[:64:2]], [(st.A_WRITE, reg["SRL_ADDR"], a) for a in range(32)])
        self.assertEqual([x for x in first[65:64 + 128:2]], [(st.A_WRITE, reg["RAM_DATA"], 0)] * 64)
        self.assertEqual([x for x in first[64 + 129:64 + 256:2]], [(st.A_EXPECT, reg["RAM_DATA"], 0)] * 64)
        self.assertEqual(first[-1], (st.A_READ, reg["COUNT"], 0))
        self.assertEqual(len(after), 128 + 1 + 1 + 64, "the RAM read back whole; the counter; the count of writes; the shift registers")
        self.assertEqual(after[129], (st.A_EXPECT, reg["WRITES"], 64))
        states = [s["ram"] for s in st.code_run()]
        differ = [64] + [sum(1 for a in range(64) if x[a] != y[a]) for x, y in zip(states, states[1:])]
        self.assertEqual(differ[:5], [64, 32, 64, 32, 64], "the base whole; a code state of an address bit differs from what was there at half the addresses; a complement at all")
        counted = [v for kind, addr, v in e if addr == reg["WRITES"]]
        self.assertEqual(counted, [sum(differ[:k + 1]) for k in range(18)], "what the design must have counted after every state: the writes made so far")
        self.assertEqual(counted[-1], 960)

    def test_a_later_state_is_written_only_where_it_differs_and_read_back_whole(self) -> None:
        e = st.accesses(st.single_run(0), DESIGN)
        reg = st.registers(DESIGN)
        marks = [i for i, (kind, _, _) in enumerate(e) if kind == st.A_MARK]
        per_state = [e[(marks[2 * s - 1] + 1 if s else 0):marks[2 * s]] for s in range(66)]
        writes = [sum(1 for kind, addr, _ in part if kind == st.A_WRITE and addr == reg["RAM_DATA"]) for part in per_state]
        self.assertEqual(writes, [64, 1] + [2] * 63 + [1], "the base whole; cell 0 set; then one cell cleared and the next set; the last cleared")
        for part in per_state:
            self.assertEqual(sum(1 for kind, addr, _ in part if kind == st.A_EXPECT and addr == reg["RAM_DATA"]), 64)

    def test_the_reads_come_from_the_census_and_from_what_s2_2_found(self) -> None:
        col = st.column_reads(CENSUS, REAL_CANDIDATES)
        self.assertEqual((len(col), col[0], col[-1], sum(n for _, n in col)), (12, (0x00401200, 3), (0x00401221, 3), 36))
        self.assertEqual(st.candidate_reads(CENSUS, REAL_CANDIDATES), [(0x0040121E, 3), (0x00401221, 3)])
        self.assertEqual(s2_2_shares.list_problems(s2_2_shares.layout(CENSUS), col), [])
        self.assertEqual(st.column_reads(KNOWN["census"], KNOWN["candidates"]), COLUMN_READS)
        self.assertEqual(st.candidate_reads(KNOWN["census"], KNOWN["candidates"]), [(0xA03, 3)])

    def test_candidates_in_two_columns_or_none_give_no_reads(self) -> None:
        two = candidates_of(CELLS[:200] + [(a, m, 0xA80, w, b, i) for a, m, _, w, b, i in CELLS[200:]])
        self.assertRaisesRegex(ValueError, "do not lie in one column", st.column_reads, KNOWN["census"], two)
        self.assertRaisesRegex(ValueError, "no candidate", st.column_reads, KNOWN["census"], {"frames_with_candidates": {}})
        outside = candidates_of([(a, m, 0xC00, w, b, i) for a, m, _, w, b, i in CELLS])
        self.assertRaisesRegex(ValueError, "do not lie in one column", st.column_reads, KNOWN["census"], outside)

    def test_a_list_or_a_result_too_large_is_not_made(self) -> None:
        self.assertRaisesRegex(ValueError, "entries; a list holds 32768", st.accesses, st.code_run() * 5, DESIGN)
        long = [("top", 0, 20, 0xA00, 100)]            # a made-up column of a hundred frames: 34 reads a state
        entries = [{"far": f"{base + m:#010x}", "block_type": 0, "half": half, "row": row, "column": col, "minor": m} for half, row, col, base, n in long for m in range(n)]
        census = {"entries": entries, "rows": [{"last": "0x00000a63", "ended_by": "the register stood still"}]}
        self.assertEqual(len(st.column_reads(census, KNOWN["candidates"])), 34)
        self.assertRaisesRegex(ValueError, r"the result would have 3\d{5} words; its area holds 262144", st.plan, "code", None, DESIGN, census, KNOWN["candidates"])
        self.assertEqual(st.plan("singles", 0, DESIGN, census, KNOWN["candidates"])["reads"], [(0xA03, 3)], "the singles of the same device fit")

    def test_the_runs_as_they_are_planned_for_the_board(self) -> None:
        got = []
        for kind, share in [("code", None)] + [("singles", r) for r in range(4)]:
            p = st.plan(kind, share, DESIGN, CENSUS, REAL_CANDIDATES)
            got.append((len(p["states"]), len(p["entries"]), len(p["log"]), len(p["reads"]), p["may_write"], p["result_words"]))
            self.assertLess(p["result_words"], st.RESULT_MAX_WORDS)
        self.assertEqual(got, [(18, 7834, 7799, 12, 0x00111000, 121278)] + [(66, 21898, 21767, 2, 0x00111000, 108894)] * 4)
        self.assertEqual((s2_3_judge.layout_hdr("code"), s2_3_judge.layout_hdr("singles")), (64 + 16 + 2 * 7799, 64 + 16 + 2 * 21767))
        self.assertRaises(ValueError, st.plan, "singles", None, DESIGN, CENSUS, REAL_CANDIDATES)
        self.assertRaises(ValueError, st.plan, "walk", None, DESIGN, CENSUS, REAL_CANDIDATES)


class Judge(unittest.TestCase):
    def test_a_clean_code_run_passes_and_every_bit_that_follows_is_where_that_cell_was_put(self) -> None:
        p, r, v = clean()
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(v["run"]["kind"], "code")
        self.assertEqual(v["finding"]["bits"], {"still": 7 * 101 * 32 - 256, "follow": 256, "follow_inverted": 0, "irregular": 0})
        self.assertEqual({(x["far"], x["word"], x["bit"]): (x["cell"], x["inverted"]) for x in v["finding"]["follows"]}, where(CELLS))
        for x in v["finding"]["follows"]:
            self.assertEqual((x["memory"], x["address"]), divmod(x["cell"], 64))

    def test_what_the_verdict_says_of_the_run_itself(self) -> None:
        p, r, v = clean()
        self.assertEqual(v["expected_console"], r.uart.strip().split("\r\n"))
        self.assertEqual((v["expected_return_code"], v["header"]["status"], v["header"]["records"]), ("0x0", "0x1", 4 + 18 * 3))
        self.assertEqual((v["params"]["states"], v["params"]["reads_in_the_list"], v["params"]["may_write"]), (18, 3, "0x00111000"))
        self.assertEqual((v["pl"]["code"], v["pl"]["passes_the_ram_held_through"], v["pl"]["id"], v["pl"]["accesses"]), ("0x0", 18, "0x53324131", len(p["log"])))
        self.assertEqual(v["pl"]["writes_counted"], {"ram": 960, "shifts": 0})
        self.assertEqual(v["pl"]["shift_registers_hold"], ["0xa5c30f69", "0x0f1e2d3c", "0x13579bdf", "0xfedcba98"])
        self.assertEqual(len(v["pl"]["counter"]), 36)
        self.assertEqual((v["registers"]["CTL0"]["value"], v["registers"]["CTL0"]["GLUTMASK_B"]), ("0x00000501", 1))
        self.assertEqual(v["run"]["states"][:3], ["base", "code 0", "code 0 complement"])
        self.assertEqual(v["finding"]["states_read_whole"], 18)

    def test_wherever_the_cells_are_put_that_is_where_they_are_found(self) -> None:
        for seed, frames in ((2, (0xA03, 0xA04, 0xA05)), (3, (0xA00,)), (5, (0xA01, 0xA06))):
            with self.subTest(seed=seed):
                cells = T.ram_map(seed, frames)
                p, r = twin(cells=cells)
                v = judged(p, r)
                self.assertEqual(v["problems"], [])
                self.assertEqual({(x["far"], x["word"], x["bit"]): (x["cell"], x["inverted"]) for x in v["finding"]["follows"]}, where(cells))

    def test_cells_shown_inverted_follow_and_are_said_to_be_inverted(self) -> None:
        cells = T.ram_map(4, inverted=9)
        p, r = twin(cells=cells)
        v = judged(p, r)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"], v["finding"]["bits"]["follow_inverted"]), ("PASS", 247, 9))
        self.assertEqual({(x["far"], x["word"], x["bit"]): (x["cell"], x["inverted"]) for x in v["finding"]["follows"]}, where(cells))

    def test_a_run_of_the_singles(self) -> None:
        p, r, v = clean("singles", 2)
        self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], v["run"]["share"]), ("PASS", [], "singles", 2))
        self.assertEqual(v["finding"]["bits"], {"still": 3 * 101 * 32 - 64, "follow": 64, "follow_inverted": 0, "irregular": 0})
        self.assertEqual(sorted(x["cell"] for x in v["finding"]["follows"]), list(range(128, 192)))
        places = where(CELLS)
        self.assertTrue(all(places[(x["far"], x["word"], x["bit"])][0] == x["cell"] for x in v["finding"]["follows"]))
        self.assertEqual(v["pl"]["writes_counted"], {"ram": 64 + 1 + 2 * 63 + 1, "shifts": 0})

    def test_fewer_cells_seen_or_a_cell_seen_twice_is_what_the_run_shows_and_not_a_failure_of_the_run(self) -> None:
        """Whether every cell has its bit is the closing's question (s2_3_table), not the judge's."""
        p, r = twin(cells=CELLS[:200], known=KNOWN)
        v = judged(p, r, known=KNOWN)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"]), ("PASS", 200))
        twice = CELLS + [(5, 1, 0xA06, 7, 7, 0)]       # cell 69 at a second place
        p, r = twin(cells=twice, known=KNOWN)
        v = judged(p, r, known=KNOWN)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"]), ("PASS", 257))
        self.assertEqual(sorted(x["far"] for x in v["finding"]["follows"] if x["cell"] == 69)[-1], "0x00000a06")

    def test_a_bit_that_changes_and_follows_no_cell_is_irregular_and_fails_the_run(self) -> None:
        p, r = twin(fault="flip@7")                   # one frame read delivers a flipped bit, once
        v = judged(p, r)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["irregular"], v["finding"]["bits"]["follow"]), ("FAIL", 1, 256))
        self.assertTrue(any("irregular" in x for x in v["problems"]))
        (bit,) = v["finding"]["irregular"]
        self.assertEqual((len(bit["readings"]), bit["readings"].count("1")), (18, 1))

    def test_a_bit_that_follows_all_ones_and_not_the_patterns_is_irregular(self) -> None:
        """What three uniform states could not tell from a cell: a bit that is set in every state but the base. No
        cell has that row."""
        p, r = twin()
        w = list(r.words)
        for s in range(1, 17):
            w[r.hb + (2 + s * 3) * REC + DATA + FRAME + 50] |= 1 << 9      # the first read of the list: frame 0xa00, word 50, bit 9
        v = judged(p, r, words=w)
        self.assertEqual(v["finding"]["irregular"], [{"far": "0x00000a00", "word": 50, "bit": 9, "readings": "0" + "1" * 16 + "0"}])
        self.assertEqual(v["verdict"], "FAIL")

    def test_a_reading_before_the_frames_that_is_not_what_the_list_says(self) -> None:
        p, r = twin(fault="ramstuck")
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"]), (0xA0A, "FAIL"))
        self.assertEqual([x for x in v["problems"] if "status" in x], ["the run did not complete: status 0xa0a (a reading before the frames of a state was not what the list says)"])
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertEqual((v["finding"]["follows"], v["run"]["kind"]), ([], None), "nothing is made of a run that did not go through")

    def test_a_ram_that_did_not_hold_fails_the_run_and_the_verdict_says_so(self) -> None:
        p, r = twin(fault="ramdisturb@9")
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"], v["pl"]["code"]), (0xA0B, "FAIL", "0xb"))
        self.assertEqual(v["problems"], ["the run did not complete: status 0xa0b (a reading after the frames of a state was not what the list says: the design did not hold)"])
        self.assertEqual(v["finding"]["follows"], [])

    def test_the_other_ways_the_design_may_fail_are_stops_the_log_itself_shows(self) -> None:
        for fault, status in (("srlmoves", 0xA0B), ("plcount", 0xA0B), ("plid", 0xA02)):
            with self.subTest(fault=fault):
                p, r = twin(fault=fault)
                v = judged(p, r)
                self.assertEqual((r.status, v["verdict"], len(v["problems"])), (status, "FAIL", 1), v["problems"])

    def test_a_counter_that_stands_still_is_the_judge_s_to_find(self) -> None:
        """The prober knows nothing of a counter: it records two readings. That they must differ is held here."""
        p, r = twin(fault="countstuck")
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"]), (1, "FAIL"))
        self.assertEqual([x[:8] for x in v["problems"]], [f"state {s}:"[:8] for s in range(18)], "said of every state, and nothing else is wrong")
        self.assertTrue(all("the design's clock did not go on" in x for x in v["problems"]))

    def test_no_bit_is_said_to_follow_a_cell_in_a_run_that_did_not_complete(self) -> None:
        """Every state went through and every read is clean, but the reference frame read at the end is not the one
        read at first: a health stop. Nothing is made of the frames of such a run."""
        probe = clean()[1]
        frames = sum(1 for e in probe.dmas if int(e[5].split("=")[1]) > 1)
        p, r = twin(fault=f"flip@{frames}")
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"], v["pl"]["passes_the_ram_held_through"]), (0x300, "FAIL", 18))
        self.assertEqual((v["finding"]["follows"], v["finding"]["frames"], v["run"]["kind"]), ([], 0, None))

    def custom(self, change, fault: str = "") -> dict:
        """The code run with its list of accesses changed by the test — a list the plan does not make. What the judge
        says of the design in such a run does not depend on the list being the plan's."""
        p = plan("code")
        entries = change(list(p["entries"]))
        r = Run(states=p["states"], reads=p["reads"], cells=CELLS, entries=entries, fault=fault, w19=p["may_write"])
        return s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, entries, DESIGN))

    def test_a_list_that_does_not_read_the_ram_back_or_the_shift_registers_gives_no_state(self) -> None:
        reg = st.registers(DESIGN)
        marks = lambda e: [i for i, (kind, _, _) in enumerate(e) if kind == st.A_MARK]   # noqa: E731

        def no_ram_after(e):                           # the readings of the RAM after the first state's frames taken out
            m = marks(e)
            return e[:m[0] + 1] + [x for x in e[m[0] + 1:m[1]] if x[1] not in (reg["RAM_ADDR"], reg["RAM_DATA"])] + e[m[1]:]
        v = self.custom(no_ram_after)
        self.assertIn("state 0: the RAM was not read back at every address before the frames and after them", v["problems"])
        self.assertEqual(v["finding"]["follows"], [])

        def no_srl_after(e):
            m = marks(e)
            return e[:m[0] + 1] + [x for x in e[m[0] + 1:m[1]] if x[1] not in (reg["SRL_ADDR"], reg["SRL_DATA"])] + e[m[1]:]
        v = self.custom(no_srl_after)
        self.assertIn("state 0: the shift registers were not read at every address after the frames", v["problems"])

        def ram_changed_after(e):                      # after the first state's frames the list itself writes address 3, and holds the readings to that
            m = marks(e)
            after = list(e[m[0] + 1:m[1]])
            at = after.index((st.A_WRITE, reg["RAM_ADDR"], 3))
            after[at + 1] = (st.A_EXPECT, reg["RAM_DATA"], 0xF)
            after = [(k, a, val + 1) if a == reg["WRITES"] else (k, a, val) for k, a, val in after]      # one write more than the plan made
            return e[:m[0] + 1] + [(st.A_WRITE, reg["RAM_ADDR"], 3), (st.A_WRITE, reg["RAM_DATA"], 0xF)] + after + e[m[1]:]
        v = self.custom(ram_changed_after)
        self.assertIn("state 0: the RAM did not read back after the frames as before them", v["problems"])
        self.assertEqual(v["pl"]["passes_the_ram_held_through"], 1, "every reading of the first state was what that list said; the judge looks at what they were")

    def test_readings_the_list_only_records_are_held_by_the_judge_where_the_design_s_own_facts_say_what_they_must_be(self) -> None:
        reg = st.registers(DESIGN)
        record_only = lambda which: (lambda e: [(st.A_READ, a, 0) if k == st.A_EXPECT and a == reg[which] else (k, a, val) for k, a, val in e])   # noqa: E731
        v = self.custom(record_only("WRITES"), fault="plcount")
        self.assertTrue(any("state 0: the design counted 65 write(s) and 0 shift(s); the log has 64 write(s) to the RAM and no shift" in x for x in v["problems"]), v["problems"])
        v = self.custom(record_only("SRL_DATA"), fault="srlmoves")
        self.assertTrue(any("the shift registers do not read as the design loads them" in x for x in v["problems"]), v["problems"])
        v = self.custom(record_only("WRITES"))
        self.assertEqual(v["problems"], ["the list of accesses is not the one the plan makes for this run"], "with a design that answers as it must, only that")

    def test_sixty_six_states_that_are_no_run_of_the_singles_are_not_taken_for_the_code_run(self) -> None:
        states = st.single_run(1)
        states = states[:1] + states[1:65][::-1] + states[65:]      # the singles of a run in another order
        r = Run(states=states, reads=[(0xA03, 3)], cells=CELLS)
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, r.entries, DESIGN))
        self.assertEqual(v["problems"], ["the states the RAM read back as are not those of the code run or of a run of the singles"])
        self.assertEqual((v["run"]["kind"], v["finding"]["bits"]["follow"]), (None, 64), "what follows is still said: the states tell these cells apart")

    def test_bit_5_is_reported_and_is_not_a_failure(self) -> None:
        p, r = twin(fault="bit5@3")                   # the third frame read: the second read of the list, record 3
        v = judged(p, r)
        self.assertEqual((v["verdict"], v["bit_5"]["shown_after_records"], v["bit_5"]["cleared_after_records"], v["bit_5"]["still_set_after_clearing"]),
                         ("PASS", [3], [3], []))
        stays = judged(*twin(fault="bit5@3,bit5stays"))
        of_the_list = list(range(3, 2 + 18 * 3))
        self.assertEqual((stays["verdict"], stays["bit_5"]["still_set_after_clearing"]), ("PASS", of_the_list), "a bit 5 that does not clear shows after every read from then on")
        self.assertEqual(stays["bit_5"]["shown_after_records"], of_the_list + [56, 57], "and after CTL0 and the reference frame, where nothing is cleared")

    def test_gates_refused_parameters_and_reads_that_fail(self) -> None:
        for fault, status, words in (("seu", 0x105, "SEU_EN gate"), ("pll", 0x113, "PLL_STATUS gate"), ("err@12", 0x221, "status 0x221"),
                                     ("lateerr@14", 0x221, "status 0x221"), ("short@3", 0x400, "status 0x400"), ("flip@1", 0x300, "0x300")):
            with self.subTest(fault=fault):
                p, r = twin(fault=fault)
                v = judged(p, r)
                self.assertEqual((r.status, v["verdict"]), (status, "FAIL"))
                self.assertTrue(any(words in x for x in v["problems"]), v["problems"])
                self.assertEqual([x for x in v["problems"] if words not in x and x != "1 anomalous read(s)"], [], "that, and nothing else")
        p, r = twin(w16=0)
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"], v["problems"]), (0x500, "FAIL", ["the run stopped: bad parameters"]))


class WhatTheJudgeIsGiven(unittest.TestCase):
    def test_another_parameter_block_than_the_one_planned(self) -> None:
        p, r, _ = clean()
        plan_words = planned(p, r)
        plan_words[9] += 1
        v = judged(p, r, plan_words=plan_words)
        self.assertEqual(v["problems"], ["the parameters the prober echoed are not the planned ones (word(s) [9]): the run did not do what was asked"])

    def test_a_plan_of_another_length_or_form(self) -> None:
        p, r, _ = clean()
        self.assertEqual(judged(p, r, plan_words=planned(p, r)[:-2])["verdict"], "INVALID")
        broken = planned(p, r)
        broken[32 + 3] |= 3                            # the first entry of the list of accesses made a mark
        v = judged(p, r, plan_words=broken)
        self.assertEqual(v["verdict"], "INVALID")
        self.assertIn("the planned list of accesses is not one the prober takes", v["problems"][0])

    def test_a_plan_with_words_after_its_two_lists(self) -> None:
        p, r, _ = clean()
        v = judged(p, r, plan_words=planned(p, r) + [0, 0])
        self.assertEqual((v["verdict"], v["problems"]), ("INVALID", ["the parameter block names 3 reads and 7834 entries; the plan has 15673 words after the block"]))

    def test_the_judge_s_own_question_of_a_list_is_the_prober_s(self) -> None:
        states = T.few(st.code_run(), 2)
        e = [(kind, addr - 0x40000000 if kind != st.A_MARK else 0, value) for kind, addr, value in st.accesses(states, DESIGN)]
        par = [0] * 32
        par[7], par[18], par[19], par[24], par[25] = 2, len(e), 1 << 0x0C | 1 << 0x10 | 1 << 0x14, 0x40000000, 0x4000001F
        marks = [i for i, (kind, _, _) in enumerate(e) if kind == st.A_MARK]
        self.assertEqual(s2_3_judge.entries_problems(e, par), [])
        for why, entries, says in (
                ("the last mark is missing", e[:-1], "the list ends inside state 1"),
                ("an entry after the last state's end", e + [(st.A_READ, 0x08, 0)], "something after the end of the last state"),
                ("the end before the frames", e[:marks[0]] + [(st.A_MARK, 0, st.MARK_END)] + e[marks[0] + 1:], "a mark that is not the one due"),
                ("the frames twice in a state", e[:marks[1]] + [(st.A_MARK, 0, st.MARK_FRAMES)] + e[marks[1] + 1:], "a mark that is not the one due"),
                ("a mark with an offset", e[:marks[0]] + [(st.A_MARK, 0x08, st.MARK_FRAMES)] + e[marks[0] + 1:], "a mark that is not the one due"),
                ("a register beyond the design", [(st.A_READ, 0x20, 0)] + e, "offset 0x20 is no register of the design inside the envelope"),
                ("a write the run's word does not name", [(st.A_WRITE, 0x18, 1)] + e, "a write to offset 0x18, which the run may not write"),
                ("a recorded reading with a value", [(st.A_READ, 0x08, 1)] + e, "a reading that is only recorded has a value")):
            with self.subTest(why=why):
                problems = s2_3_judge.entries_problems(entries, dict(enumerate(par)) | {18: len(entries)})
                self.assertTrue(any(says in x for x in problems), problems)
        self.assertTrue(s2_3_judge.entries_problems(e, dict(enumerate(par)) | {7: 3}), "one state fewer in the list than the block says")
        self.assertTrue(s2_3_judge.entries_problems(e, dict(enumerate(par)) | {25: 0x4000000F}), "an envelope that leaves the RAM's data out")

    def test_a_list_of_reads_that_reads_an_address_twice_is_not_one_made_from_the_census(self) -> None:
        p = plan("code")
        reads = [(0xA00, 3), (0xA02, 3)]
        r = Run(states=p["states"], reads=reads, cells=CELLS, w19=p["may_write"])
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, reads, p["entries"], DESIGN))
        self.assertIn("the list of reads is not one made from the census: read 1: 0x00000a02 x3 reads an address the list has already read", v["problems"])

    def test_without_the_words_the_shift_registers_are_loaded_with_that_is_said(self) -> None:
        p, r, _ = clean()
        known = {k: x for k, x in KNOWN.items() if k != "srl"}
        v = s2_3_judge.judge(r.words, known, planned(p, r))
        self.assertIn("the words the design loads into its shift registers were not given: what they read as cannot be held to anything", v["problems"])

    def test_another_list_of_accesses_than_the_prober_made(self) -> None:
        p, r, _ = clean()
        other = planned(p, r)
        at = 32 + 3 + 2 * 70 + 1                       # the value of an entry: one of the first writes to the RAM's data
        other[at] ^= 1
        v = judged(p, r, plan_words=other)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("written to" in x and "is due" in x for x in v["problems"]), v["problems"])

    def test_states_that_are_not_those_of_a_run_of_the_step(self) -> None:
        states = T.few(st.code_run(), 4)
        r = Run(states=states)
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, r.entries, DESIGN))
        self.assertEqual(v["problems"][0], "the states the RAM read back as are not those of the code run or of a run of the singles")
        self.assertIn("the states do not tell 4 group(s) of cells apart: a bit could not be said to follow one of them", v["problems"])
        self.assertEqual(v["finding"]["cells_not_told_apart"][0][:3], [0, 4, 8], "four states tell few cells apart, and the verdict lists which not")
        self.assertEqual((v["finding"]["bits"]["follow"], v["finding"]["bits"]["irregular"]), (0, 256), "and no bit is said to follow a cell")

    def test_lists_that_are_not_the_plan_s(self) -> None:
        p = plan("code")
        r = Run(states=p["states"], reads=COLUMN_READS[:2], cells=CELLS, w19=p["may_write"])     # a read of the column left out
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, p["entries"], DESIGN))
        self.assertEqual(v["problems"], ["the list of reads is not the one the plan makes for this run"])
        entries = [(st.A_READ, PL_COUNT, 0)] + p["entries"]                                      # an access more than the plan has
        r = Run(states=p["states"], reads=p["reads"], cells=CELLS, entries=entries, w19=p["may_write"])
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, entries, DESIGN))
        self.assertEqual(v["problems"], ["the list of accesses is not the one the plan makes for this run"])
        r = Run(states=p["states"], reads=p["reads"], cells=CELLS, w19=p["may_write"] | 1 << 0x04)   # a run allowed to write more than its lists write
        v = s2_3_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, r.reads, p["entries"], DESIGN))
        self.assertEqual(v["problems"], ["the run's word of what it may write is 0x00111010; the plan's lists write 0x00111000"])

    def test_without_the_census_what_s2_2_found_or_the_design_nothing_can_be_held_to_them(self) -> None:
        p, r, _ = clean()
        v = judged(p, r, known=dict(DESIGN, candidates=KNOWN["candidates"]))
        self.assertIn("the census was not given: the list of reads and the address register cannot be held to anything", v["problems"])
        v = judged(p, r, known=dict(DESIGN, census=KNOWN["census"]))
        self.assertEqual(v["problems"], ["the census and what S2.2 found were not given: the lists cannot be held to the plan of the run"])
        v = judged(p, r, known={"census": KNOWN["census"], "candidates": KNOWN["candidates"]})
        self.assertIn("the design's registers were not given: what the log says of the RAM cannot be read", v["problems"])

    def test_candidates_elsewhere_than_where_the_run_read(self) -> None:
        p, r, _ = clean()
        other = known_for([(a, m, 0xA80 + (far - 0xA03) % 4, w, b, i) for a, m, far, w, b, i in CELLS])
        v = judged(p, r, known=other)
        self.assertEqual(v["problems"], ["the list of reads is not the one the plan makes for this run"])


class Tampered(unittest.TestCase):
    """A clean result with one thing changed in its raw words: each must be said, in words that name it."""

    def setUp(self) -> None:
        self.p, self.r = once("tamper", lambda: twin(fault="bit5@3"))   # a clean run in which bit 5 showed once (record 3), so that both forms are there

    def changed(self, edits: dict[int, int] | None = None, cut: int | None = None, fn=None) -> dict:
        w = list(self.r.words)
        for at, value in (edits or {}).items():
            w[at] = value
        if fn:
            fn(w)
        return judged(self.p, self.r, words=w[:cut] if cut else w)

    def says(self, v: dict, *texts: str, verdict: str = "FAIL") -> None:
        self.assertEqual(v["verdict"], verdict, v["problems"])
        for t in texts:
            self.assertTrue(any(t in p for p in v["problems"]), f"{t!r} not in {v['problems']}")

    def rec_at(self, i: int, field: int) -> int:
        return self.r.hb + i * REC + field

    def log_at(self, k: int, value: bool = True) -> int:
        return 64 + FIXED + 2 * k + int(value)

    def test_it_is_clean_as_it_stands(self) -> None:
        self.assertEqual(self.changed()["problems"], [])

    def test_the_header(self) -> None:
        r = self.r
        self.says(self.changed({0: 0}), "not a result buffer", verdict="INVALID")
        self.says(self.changed({7: r.hb + 2}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed({6: REC + 1}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed({3: r.n_records - 1}), "sizes do not add up", verdict="INVALID")
        self.says(self.changed(cut=len(r.words) - 1), "the buffer has", verdict="INVALID")
        self.says(self.changed({2: 0x221}), "the header's status is 0x221; the records and the log imply 0x1")
        self.says(self.changed({4: 1}), "the header counts 1 anomalies")
        self.says(self.changed({18: 3}), "the header's stop record is 0x3")
        self.says(self.changed({20: 1}), "reserved header words are not zero")
        self.says(self.changed({16: 0x50033000}), "final INT_STS")

    def test_the_echoed_parameters(self) -> None:
        self.says(self.changed({32 + 9: 999}), "the parameters the prober echoed are not the planned ones (word(s) [9])")
        self.says(self.changed({32 + 18: self.r.params[18] + 2}), "sizes do not add up", verdict="INVALID")   # another count of entries is another header
        self.says(self.changed({32 + 19: 0x00111010}), "the parameters the prober echoed are not the planned ones (word(s) [19])")
        self.says(self.changed({32 + 6: 1}), "not a valid stage-9 parameter block", verdict="INVALID")

    def test_the_gate_readings(self) -> None:
        self.says(self.changed({8: self.r.words[8] | 0x100}), "the readings in the header fail the SEU_EN gate, yet the run went on")
        self.says(self.changed({64 + 4: 0xA}), "the readings in the header fail the LVL_SHFTR_EN gate, yet the run went on")

    def test_the_pl_block_s_form(self) -> None:
        self.says(self.changed({64: 0}), "the PL block does not begin with its magic", verdict="INVALID")
        self.says(self.changed({65: self.r.n_log + 1}), "more than it has room for", verdict="INVALID")
        self.says(self.changed({64 + 9: 1}), "reserved words of the PL block are not zero")
        self.says(self.changed({65: self.r.n_log - 1}), "the PL block holds words after the last access it counts")

    def test_the_log_of_accesses_to_the_design(self) -> None:
        log = self.r.pl_log()
        write = next(k for k, (a, w, _) in enumerate(log) if w and a == PL_RAM_DATA)
        expect = next(k for k, (a, w, _) in enumerate(log) if not w and a == PL_RAM_DATA)
        count = [k for k, (a, w, _) in enumerate(log) if a == PL_COUNT]
        self.says(self.changed({self.log_at(0): 0x53324132}), "the header's status is 0x1; the records and the log imply 0xa02")
        self.says(self.changed({self.log_at(write): 5}), f"PL access {write}: 0x00000005 written to 0x40000010, where 0x00000000 is due")
        self.says(self.changed({self.log_at(write, False): PL_RAM_DATA}), f"PL access {write}: a read of 0x40000010, where a write to 0x40000010 is due")
        self.says(self.changed({self.log_at(expect, False): PL_COUNT}), f"PL access {expect}: a read of 0x40000008, where a read of 0x40000010 is due")
        self.says(self.changed({self.log_at(expect): 1}), "the header's status is 0x1; the records and the log imply 0xa0a", "the PL block's code is 0x0")
        self.says(self.changed({self.log_at(count[1]): log[count[0]][2]}), "state 0: the counter read", "the design's clock did not go on")
        self.says(self.changed({self.log_at(write, False): PL_SRL_DATA | 1}), "is outside what the run may touch", "a write to the shift registers' data — a shift")
        self.says(self.changed({66: 5}), "the PL block's code is 0x5", "its log implies 0x0")
        self.says(self.changed({67: 12}), "the PL block says it stopped at access 0xc")

    def test_a_reading_after_the_frames_that_differs_is_a_stop_the_header_must_show(self) -> None:
        log = self.r.pl_log()
        marks = [i for i, (kind, _, _) in enumerate(self.p["entries"]) if kind == st.A_MARK]
        first_after = 1 + marks[0]                     # the log's index of the first access after the first mark: a write of the RAM's address
        self.assertEqual(log[first_after + 1][0:2], (PL_RAM_DATA, False))
        v = self.changed({self.log_at(first_after + 1): 0xF})
        self.says(v, "the header's status is 0x1; the records and the log imply 0xa0b")

    def test_the_shift_registers_and_the_count_of_writes(self) -> None:
        log = self.r.pl_log()
        srl = next(k for k, (a, w, _) in enumerate(log) if not w and a == PL_SRL_DATA)
        self.says(self.changed({self.log_at(srl): log[srl][2] ^ 1}), "the records and the log imply 0xa0a")

    def test_a_record_s_own_words(self) -> None:
        r = self.r
        self.says(self.changed({self.rec_at(2, 0): 0xA01}), "record 2: expected the target read of 0x00000a00 x3", "is not the pinned one")
        self.says(self.changed({self.rec_at(2, 2): 0x21}), "record 2: code 0x21, but its raw words say 0x0")
        self.says(self.changed({self.rec_at(2, 12): 1}), "record 2: expected the target read of 0x00000a00 x3 (state 0")
        self.says(self.changed({self.rec_at(2, 13): 1}), "record 2: the prober's guard refused its own stream")
        self.says(self.changed({self.rec_at(2, 16 + 5): 0}), "record 2: the frame read stream is not the pinned one")
        self.assertEqual(r.words[self.rec_at(2, FARBLK + 4)], 0xA04, "after the pad and three frames from 0xa00")
        self.says(self.changed({self.rec_at(2, FARBLK + 4): 0xA05}), "record 2: the address register reads 0x00000a05")
        self.says(self.changed({self.rec_at(2, DATA + 3): 1}), "record 2: code 0x0, but its raw words say 0x11")
        self.says(self.changed({self.rec_at(4, REC - 1): 1}), "record 4: words after the")   # the read of one frame: its record has room left
        self.says(self.changed({self.rec_at(1, 10): 0}), "record 1: a health flag on a target read")
        self.says(self.changed({self.rec_at(r.n_records - 1, 10): 0}), "the final reference flag is 0x0")

    def test_the_status_after_a_read_and_the_clearing_of_bit_5(self) -> None:
        self.assertEqual(self.r.rec(3)["after"] & 0x20, 0x20, "bit 5 showed after the second read of the list")
        self.says(self.changed({self.rec_at(3, 10): 0xFFFFFFFF}), "record 3: bit 5 shows in the status after the read", "nothing is recorded of its clearing")
        self.says(self.changed({self.rec_at(4, 10): 0x50033004}), "record 4: a clearing of bit 5 is recorded")
        self.says(self.changed({self.rec_at(4, FARBLK + 7): 0x50073004}), "record 4: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(3, 10): 0x50033000}), "record 3: code 0x0, but its raw words say 0x23")

    def test_more_of_the_header_and_the_gates(self) -> None:
        r = self.r
        self.says(self.changed({16: 0x50073004}), "its final INT_STS 50073004")
        self.says(self.changed({4: 1}), "the header counts 1 anomalies; the records show 0", "1 anomalous read(s)")
        self.says(self.changed({8: r.words[8] & ~0x08000000}), "fail the CTRL gate")
        self.says(self.changed({9: r.words[9] | 0x10}), "fail the loopback gate")
        self.says(self.changed({10: r.words[10] & ~4}), "fail the PCFG_DONE gate")
        self.says(self.changed({12: r.words[12] | 4}), "fail the data-cache gate")
        self.says(self.changed({64 + 6: 0x00200A00}), "fail the FPGA0_CLK_CTRL gate")
        p, gate = twin(fault="lpbk")
        v = judged(p, gate, words=gate.words[:2] + [0x103] + gate.words[3:])
        self.assertIn("the run reports a stop at the PCFG_DONE gate, but the readings in its header fail the loopback gate", v["problems"])
        v = judged(p, gate, words=gate.words[:64 + 4] + [0xF] + gate.words[64 + 5:])
        self.assertIn("SLCR words are recorded although a gate before them fails", v["problems"])
        self.assertEqual(judged(p, gate)["problems"], ["the run stopped at the loopback gate"])

    def test_more_of_a_record_s_own_words(self) -> None:
        r, i = self.r, 5                               # record 5: the first read of the list in the second state
        self.says(self.changed({self.rec_at(i, 1): 1}), "record 5: expected the target read of")
        self.says(self.changed({self.rec_at(i, 15): 2}), "record 5: expected the target read of")
        self.says(self.changed({self.rec_at(i, 14): 2}), "record 5: expected the target read of")
        self.says(self.changed({self.rec_at(i, 14): 4}), "record 5: 4 frames per read")
        self.says(self.changed({self.rec_at(i, 0): 0x900}), "record 5: reads 0x00000900 + 3 frame(s), outside the envelope")
        self.says(self.changed({self.rec_at(i, 16 + 9): 0x30004001}), "record 5: the frame read stream is not read-only")
        self.says(self.changed({self.rec_at(i, 59 + 1): 0x2800E001}), "record 5: the FAR read stream is not the pinned one")
        self.says(self.changed({self.rec_at(i, 63): 0}), "record 5: the cleanup stream is not the pinned one")
        self.says(self.changed({self.rec_at(i, 9): 1}), "record 5: 0 sentinel word(s) in the data, the record says 1")
        self.says(self.changed({self.rec_at(i, DATA + FRAME + 5): 0xA5A55A5A}), "record 5: 1 sentinel word(s)", "raw words say 0x10")
        self.says(self.changed({self.rec_at(i, 3): 0x50073004}), "record 5: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(i, 4): 1001}), "record 5: 1001 polls, above the limit 1000")
        self.says(self.changed({self.rec_at(i, FARBLK + 5): 1}), "record 5: the value")
        self.says(self.changed({self.rec_at(1, 59 + 1): 0x28002001}), "record 1: the CTL0 read stream is not the pinned one")
        self.says(self.changed({self.rec_at(1, 5): 0x50033004}), "record 1: a frame read transfer has a status in an operation that reads nothing")
        self.says(self.changed({self.rec_at(0, 10): 1}), "record 0: a health flag on a baseline read")

    def test_the_status_after_the_reads_that_are_not_of_the_list_and_every_error_bit(self) -> None:
        after, cleared = FARBLK + 7, 10
        w, n = self.r.words, self.r.n_records
        for i in (0, 1, n - 2, n - 1):
            self.says(self.changed({self.rec_at(i, after): w[self.rec_at(i, after)] | 0x00040000}), f"record {i}: code 0x0, but its raw words say 0x21")
            self.says(self.changed({self.rec_at(i, after): w[self.rec_at(i, after)] & ~4}), f"record {i}: code 0x0, but its raw words say 0x23")
        v = self.changed({self.rec_at(1, after): w[self.rec_at(1, after)] | 0x20})
        self.assertEqual((v["verdict"], v["bit_5"]["shown_after_records"], v["bit_5"]["cleared_after_records"]), ("PASS", [1, 3], [3]), "bit 5 after CTL0: recorded, reported, left")
        v = self.changed({self.rec_at(3, cleared): w[self.rec_at(3, cleared)] | 0x20})
        self.assertEqual((v["verdict"], v["bit_5"]["still_set_after_clearing"]), ("PASS", [3]), "a bit 5 that did not clear is reported, not judged")
        for bit in (6, 11, 14, 15, 18, 20, 21, 22, 23):                     # every bit of a transfer's error mask
            self.says(self.changed({self.rec_at(4, after): w[self.rec_at(4, after)] | 1 << bit}), "record 4: code 0x0, but its raw words say 0x21")
            self.says(self.changed({self.rec_at(3, cleared): w[self.rec_at(3, cleared)] | 1 << bit}), "record 3: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(3, after): w[self.rec_at(3, after)] | 0x00040000}), "record 3: bit 5 was cleared", "record 3: code 0x0, but its raw words say 0x21")
        self.says(self.changed({self.rec_at(3, 2): 0x23}), "record 3: code 0x23, but its raw words say 0x0")

    def test_a_run_that_stopped_at_a_status_with_one_thing_changed(self) -> None:
        after, cleared, code = FARBLK + 7, 10, 2

        def problems(fault: str, edits: dict) -> list[str]:
            p, r = twin(fault=fault)
            at = lambda field: r.hb + 2 * REC + field   # noqa: E731  record 2: the first read of the list
            return judged(p, r, words=[{at(k): x for k, x in edits.items()}.get(i, w) for i, w in enumerate(r.words)])["problems"]
        self.assertIn("record 2: code 0x0, but its raw words say 0x21", problems("lateerr@14", {code: 0}))
        self.assertIn("record 2: code 0x23, but its raw words say 0x21", problems("lateerr@14", {code: 0x23, cleared: 0x50023004}))
        self.assertTrue(any("record 2: bit 5 was cleared (50063004) after a read that was not clean" in x for x in problems("bit5@2,lateerr@14", {cleared: 0x50063004})))
        self.assertTrue(any("record 2: bit 5 was cleared (50023004) after a read that was not clean" in x for x in problems("bit5@2,short@2", {cleared: 0x50023004})))
        late = problems("lateerr@11", {})
        self.assertEqual(late, ["the run did not complete: status 0x224", "1 anomalous read(s)"], "an error bit met before a transfer of record 2 began")
        for c in (0, 0x20, 0x21, 0x23):
            self.assertIn(f"record 2: code {c:#x}, but its raw words say 0x24", problems("lateerr@11", {code: c}))

    def test_accesses_after_the_run_must_have_ended_and_a_log_that_ends_early(self) -> None:
        p, r = twin(fault="ramstuck")                 # stopped at a reading before the frames of the second state
        n = r.plb[1]
        w = list(r.words)
        w[65] = n + 1; w[64 + FIXED + 2 * n], w[64 + FIXED + 2 * n + 1] = PL_COUNT, 7
        v = judged(p, r, words=w)
        self.assertIn(f"1 access(es) to the design after the point where the list ends or the run must have ended (access {n})", v["problems"])

        def shorter(w):                                # the clean run with the last access of its log taken away
            k = self.r.n_log
            w[65] = k - 1; w[64 + FIXED + 2 * (k - 1)] = w[64 + FIXED + 2 * (k - 1) + 1] = 0
        self.says(self.changed(fn=shorter), f"the log of PL accesses ends after {self.r.n_log - 1}, where access {self.r.n_log - 1} of the list is due")

    def test_a_log_in_a_run_that_never_came_to_the_design(self) -> None:
        p, r = twin(fault="short@1")                  # the reference frame's first reading fails: nothing of the design is touched
        self.assertEqual((r.status, r.plb[1]), (0x610, 0))
        w = list(r.words); w[65] = 1; w[64 + FIXED], w[64 + FIXED + 1] = 0x40000000, 0x53324131
        self.assertIn("the PL block shows an access to the design in a run that never came to it", judged(p, r, words=w)["problems"])

    def test_ctl0_read_differently_before_and_after(self) -> None:
        self.says(self.changed({self.rec_at(self.r.n_records - 2, FARBLK + 4): 0x00000401}), "CTL0 does not read the same before and after")

    def test_a_frame_changed_in_one_state(self) -> None:
        v = self.changed({self.rec_at(2 + 5 * 3, DATA + FRAME + 10): 0x80})
        self.says(v, "1 bit(s) changed and follow no cell of the RAM: irregular")
        self.assertEqual(v["finding"]["irregular"][0]["far"], "0x00000a00")

    def test_a_cell_s_bit_changed_in_one_state_is_no_longer_that_cell_s(self) -> None:
        x = clean()[2]["finding"]["follows"][0]
        far, word, bit = int(x["far"], 16), x["word"], x["bit"]
        k = next(i for i, (f, n) in enumerate(self.p["reads"]) if f <= far < f + n)
        at = self.rec_at(2 + 4 * 3 + k, DATA + FRAME * (1 + far - self.p["reads"][k][0]) + word)
        v = self.changed({at: self.r.words[at] ^ 1 << bit})
        self.says(v, "irregular")
        self.assertEqual(v["finding"]["bits"]["follow"], 255)

    def test_records_missing_and_records_too_many(self) -> None:
        r = self.r
        fewer = self.changed({3: r.n_records - 1, 5: r.total - REC}, cut=len(r.words) - REC)
        self.says(fewer, "the records end at", "is missing")
        def more(w):
            w[3] += 1; w[5] += REC; w += w[-REC:]
        self.says(self.changed(fn=more), "1 record(s) after the point where the schedule ends")


class Table(unittest.TestCase):
    def closing(self, cells=None, candidates: dict | None = None) -> tuple[dict, dict]:
        cells = CELLS if cells is None else cells
        known = dict(DESIGN, census=T8.census(), candidates=KNOWN["candidates"])
        p, r = twin(cells=cells, known=known)
        v = judged(p, r, known=known)
        return v, s2_3_table.close_code(v, KNOWN["candidates"] if candidates is None else candidates)

    def test_a_clean_code_run_closes_into_the_table(self) -> None:
        v, c = self.closing()
        self.assertEqual((c["problems"], c["outcome"][:2], len(c["table"]), c["inverted"], c["cells_with_one_bit"]), ([], "1:", 256, 0, 256))
        self.assertEqual([row["cell"] for row in c["table"]], list(range(256)))
        self.assertEqual({(row["far"], row["word"], row["bit"]): (row["cell"], row["inverted"]) for row in c["table"]}, where(CELLS))
        for row in c["table"]:
            self.assertEqual((row["memory"], row["address"]), divmod(row["cell"], 64))

    def test_a_cell_with_no_bit_or_with_two_gives_no_table(self) -> None:
        v, c = self.closing(CELLS[:255])
        self.assertEqual((v["verdict"], c["table"], c["cells_with_no_bit"], c["outcome"][:2]), ("PASS", None, [255], "2:"))
        self.assertIn("1 cell(s) of the RAM have no bit that follows them", c["problems"])
        self.assertIn("1 place(s) S2.2 found follow no cell", c["problems"])
        v, c = self.closing(CELLS + [(5, 1, 0xA06, 7, 7, 0)])
        self.assertEqual((v["verdict"], c["table"], c["cells_with_several_bits"]), ("PASS", None, [69]))
        self.assertIn("1 bit(s) follow a cell at a place S2.2 did not find", c["problems"])

    def test_the_places_must_be_those_s2_2_found_and_shown_the_same_way(self) -> None:
        moved = [c if i else (c[0], c[1], 0xA06, 3, 3, 0) for i, c in enumerate(CELLS)]   # cell 0 elsewhere than S2.2 has it
        v, c = self.closing(moved)
        self.assertEqual((v["verdict"], c["table"], c["outcome"][:2]), ("PASS", None, "4:"))
        self.assertEqual((c["places_s2_2_did_not_have"], len(c["places_of_s2_2_that_follow_no_cell"])), ([["0x00000a06", 3, 3]], 1))
        turned = [c if i else (*c[:5], 1) for i, c in enumerate(CELLS)]                   # cell 0 shown inverted, where S2.2 saw it as written
        v, c = self.closing(turned)
        self.assertEqual((v["verdict"], c["table"]), ("PASS", None))
        self.assertIn("1 place(s) are shown the other way than S2.2 saw them", c["problems"])

    def test_a_cell_with_two_bits_gives_no_table_even_where_s2_2_found_both(self) -> None:
        twice = CELLS + [(5, 1, 0xA06, 7, 7, 0)]
        known = dict(DESIGN, census=T8.census(), candidates=KNOWN["candidates"])
        p, r = twin(cells=twice, known=known)
        c = s2_3_table.close_code(judged(p, r, known=known), candidates_of(twice))
        self.assertEqual((c["table"], c["problems"], c["cells_with_several_bits"]), (None, ["1 cell(s) of the RAM are followed by more than one bit"], [69]))

    def test_only_a_passing_code_run_is_closed(self) -> None:
        p, r = twin(fault="flip@7")
        self.assertEqual(s2_3_table.close_code(judged(p, r), KNOWN["candidates"])["problems"], ["the code run is not a passing run"])
        _, _, v = clean("singles", 0)
        self.assertEqual(s2_3_table.close_code(v, KNOWN["candidates"])["problems"], ["the verdict is not of the code run"])

    def test_inverted_cells_are_in_the_table_as_inverted(self) -> None:
        cells = T.ram_map(4, inverted=9)
        p, r = twin(cells=cells)
        c = s2_3_table.close_code(judged(p, r), candidates_of(cells))
        self.assertEqual((c["problems"], c["inverted"], [row["cell"] for row in c["table"] if row["inverted"]]), ([], 9, list(range(9))))

    def test_a_run_of_the_singles_held_to_the_table(self) -> None:
        table = self.closing()[1]["table"]
        _, _, v = clean("singles", 2)
        h = s2_3_table.hold_singles(v, table)
        self.assertEqual((h["problems"], h["confirmed"], h["contradictions"]), ([], list(range(128, 192)), []))

    def test_a_table_that_has_two_cells_the_wrong_way_round_is_contradicted_by_their_singles(self) -> None:
        table = [dict(row) for row in self.closing()[1]["table"]]
        a, b = table[130], table[131]
        for key in ("far", "word", "bit"):
            a[key], b[key] = b[key], a[key]
        _, _, v = clean("singles", 2)
        h = s2_3_table.hold_singles(v, table)
        self.assertEqual((sorted(h["confirmed"]), [c["cell"] for c in h["contradictions"]]), ([n for n in range(128, 192) if n not in (130, 131)], [130, 131]))
        self.assertEqual(h["contradictions"][0]["the_single_shows"], [[b["far"], b["word"], b["bit"]]])
        self.assertTrue(all("not the one the table has" in x for x in h["problems"]))

    def test_a_single_that_changes_two_bits_or_none_is_a_contradiction(self) -> None:
        table = self.closing()[1]["table"]
        cells = CELLS + [(5, 2, 0xA05, 9, 9, 0)]      # cell 133 shows at a second place, in a frame the singles read
        p, r = twin("singles", 2, cells=cells, known=KNOWN)
        h = s2_3_table.hold_singles(judged(p, r, known=KNOWN), table)
        self.assertEqual([c["cell"] for c in h["contradictions"]], [133])
        self.assertIn("cell 133: its single changes 2 bit(s)", h["problems"][0])
        fewer = [c for c in CELLS if not (c[0] == 5 and c[1] == 2)]
        p, r = twin("singles", 2, cells=fewer, known=KNOWN)
        h = s2_3_table.hold_singles(judged(p, r, known=KNOWN), table)
        self.assertEqual(([c["cell"] for c in h["contradictions"]], h["contradictions"][0]["the_single_shows"]), ([133], []))
        self.assertIn("cell 133: its single changes 0 bit(s)", h["problems"][0])

    def test_a_single_shown_the_other_way_than_the_table_has_it_is_a_contradiction(self) -> None:
        table = [dict(row) for row in self.closing()[1]["table"]]
        table[140]["inverted"] = True
        h = s2_3_table.hold_singles(clean("singles", 2)[2], table)
        self.assertEqual(([c["cell"] for c in h["contradictions"]], len(h["confirmed"])), ([140], 63))

    def test_a_failing_run_of_the_singles_and_a_bit_that_follows_a_cell_of_another_run(self) -> None:
        table = self.closing()[1]["table"]
        p, r = twin("singles", 2, fault="countstuck")
        v = judged(p, r)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(s2_3_table.hold_singles(v, table), {"problems": ["not a passing run of the singles"], "confirmed": [], "contradictions": []})
        # A bit that flips once, in the state of one single, has that cell's row: the judge says it follows the cell —
        # one state cannot tell them apart — and the table says the cell has two bits.
        p, r = twin("singles", 2, fault="flip@5")     # the frame read of the fourth state: the single of cell 130
        v = judged(p, r)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"]), ("PASS", 65))
        h = s2_3_table.hold_singles(v, table)
        self.assertEqual(([c["cell"] for c in h["contradictions"]], len(h["confirmed"])), ([130], 63))
        self.assertIn("cell 130: its single changes 2 bit(s)", h["problems"][0])
        v = json.loads(json.dumps(clean("singles", 2)[2]))
        v["finding"]["follows"].append({"far": "0x00000a03", "word": 0, "bit": 0, "cell": 7, "memory": 0, "address": 7, "inverted": False})
        h = s2_3_table.hold_singles(v, table)
        self.assertEqual((h["problems"], len(h["confirmed"])), (["a bit follows cell 7, which is not a cell of this run"], 64))

    def test_the_transition_written_for_an_inverted_place_is_the_one_seen(self) -> None:
        cells = T.ram_map(4, inverted=9)
        p, r = twin(cells=cells)
        c = s2_3_table.close_code(judged(p, r), candidates_of(cells))
        doc = s2_3_table.ram_map(DESIGN, c["table"], {"dir": "run00", "result_sha256": "0" * 64, "reads": p["reads"], "states": p["states"]}, [])
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual([e["observed_transition"] for e in doc["entries"][:10]], [{"base": 1, "set": 0}] * 9 + [{"base": 0, "set": 1}])
        self.assertEqual([e["inverted"] for e in doc["entries"][:10]], [True] * 9 + [False])

    def test_what_is_not_a_run_of_the_singles_or_not_a_table(self) -> None:
        table = self.closing()[1]["table"]
        self.assertEqual(s2_3_table.hold_singles(clean()[2], table)["problems"], ["not a passing run of the singles"])
        self.assertEqual(s2_3_table.hold_singles(clean("singles", 2)[2], table[:-1])["problems"], ["the table is not one of every cell"])

    def description(self, upto: int = 4) -> tuple[dict, list]:
        v, c = self.closing()
        pc = plan("code")
        code = {"dir": "run00", "result_sha256": "0" * 64, "reads": pc["reads"], "states": pc["states"]}
        singles = []
        for share in range(upto):
            p, r, sv = clean("singles", share)
            singles.append({"dir": f"run{share + 1:02d}", "share": share, "result_sha256": f"{share + 1}" * 64, "reads": p["reads"], "states": p["states"],
                            "held": s2_3_table.hold_singles(sv, c["table"]), "run": r})
        doc = s2_3_table.ram_map(DESIGN, c["table"], code, [{k: x for k, x in s.items() if k != "run"} for s in singles],
                                 json.loads((ROOT / "pl" / "s2a" / "build.json").read_text()))
        return doc, singles

    def test_the_description_written_out(self) -> None:
        doc, singles = self.description()
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["schema"], doc["label"], doc["design"], doc["cells"], len(doc["entries"])), ("ram_map", "closed-book", "s2a", 256, 256))
        self.assertEqual(doc["counts"], {"confirmed": 256, "decoded": 0, "contradiction": 0})
        places = where(CELLS)
        for e in doc["entries"]:
            far, word, bit = e["address"].split("/")
            self.assertEqual(places[(far, int(word), int(bit))], (e["cell"], e["inverted"]))
            self.assertEqual((e["memory"], e["ram_address"], e["confidence"], e["state"]), (*divmod(e["cell"], 64), 2, "confirmed"))
            self.assertEqual(e["evidence"]["code_states"], [1 + 2 * j + (0 if e["cell"] >> j & 1 else 1) for j in range(8)], "the code state, or its complement, in which the cell was set")
        self.assertEqual(doc["as_the_build_placed_them"]["memories"], {"0": "D6LUT", "1": "A6LUT", "2": "B6LUT", "3": "C6LUT"})
        self.assertNotIn("lut_init", json.dumps(doc), "nothing here says a RAM's address is a LUT's index")

    def test_the_records_an_entry_names_are_the_records_that_show_it(self) -> None:
        doc, singles = self.description()
        code_run = clean()[1]
        for e in doc["entries"][::17]:
            far, word, bit = (int(x, 0) for x in e["address"].split("/"))
            for record in e["evidence"]["code_records"]:
                rec = code_run.rec(record)
                self.assertEqual((rec["frames"][far - rec["far"]][word] >> bit) & 1, 1, (e["cell"], record))
            s = e["evidence"]["single"]
            run = next(x["run"] for x in singles if x["dir"] == s["run"])
            rec = run.rec(s["record"])
            self.assertEqual(((rec["frames"][far - rec["far"]][word] >> bit) & 1, rec["state"]), (1, s["state"]))

    def test_a_cell_whose_single_was_not_made_is_decoded_and_one_contradicted_is_said_so(self) -> None:
        doc, _ = self.description(upto=2)
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual(doc["counts"], {"confirmed": 128, "decoded": 128, "contradiction": 0})
        self.assertEqual({(e["state"], e["confidence"], e["evidence"]["single"] is None) for e in doc["entries"][128:]}, {("decoded", 1, True)})
        v, c = self.closing()
        table = [dict(row) for row in c["table"]]
        for key in ("far", "word", "bit"):
            table[0][key], table[1][key] = table[1][key], table[0][key]
        p, r, sv = clean("singles", 0)
        held = s2_3_table.hold_singles(sv, table)
        pc = plan("code")
        doc = s2_3_table.ram_map(DESIGN, table, {"dir": "run00", "result_sha256": "0" * 64, "reads": pc["reads"], "states": pc["states"]},
                                 [{"dir": "run01", "share": 0, "result_sha256": "1" * 64, "reads": p["reads"], "states": p["states"], "held": held}])
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual(doc["counts"], {"confirmed": 62, "decoded": 192, "contradiction": 2})
        self.assertEqual([(e["cell"], e["confidence"]) for e in doc["entries"] if e["state"] == "contradiction"], [(0, 0), (1, 0)])
        self.assertNotIn("as_the_build_placed_them", doc)

    def test_the_schema_refuses_what_is_not_such_a_description(self) -> None:
        doc, _ = self.description()
        ok = jsonschema.Draft202012Validator(SCHEMA)
        for change in (lambda d: d.update(label="open"), lambda d: d["entries"][0].update(confidence=1), lambda d: d["entries"][0].update(state="unknown"),
                       lambda d: d["entries"][0].update(address="0xa03/1/2"), lambda d: d["entries"][0].update(relation={"kind": "lut_init"}),
                       lambda d: d.pop("runs")):
            bad = json.loads(json.dumps(doc))
            change(bad)
            self.assertFalse(ok.is_valid(bad))


class Board9(Board8):
    """The pretend board of the stage-8 tests with the list of accesses where the run script sends it."""

    def c_go(self, w):
        tmp = Path(scratch_dirs.mkdtemp(prefix="smacc_"))
        blob = self.blobs.get(s1a_run.ACC_ADDR, b"")
        (tmp / "acc.txt").write_text("\n".join(f"{x:x}" for x in struct.unpack("<%dI" % (len(blob) // 4), blob)) + "\n")
        self.q["env"] = dict(self.q.get("env", {}), SM_ACC=str(tmp / "acc.txt"))
        return super().c_go(w)

    def load(self, loady: str, path: str):
        reply = super().load(loady, path)
        if self.q.get("corrupt_acc") and f"{s1a_run.ACC_ADDR:08x}" in loady:
            blob = self.blobs[s1a_run.ACC_ADDR]; self.blobs[s1a_run.ACC_ADDR] = blob[:12] + bytes([blob[12] ^ 1]) + blob[13:]
        return reply


def prepared() -> None:
    """The sets are written by the image's tests; a test that reads them makes sure they are there."""
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)


def run9(k: int, known: dict | None = None, fault: str = "", out: Path | None = None, cells=None, **quirks):
    """Run k of the chain through the run script, on the pretend board, over the made-up device."""
    prepared()
    known = KNOWN if known is None else known
    stage, share = s2_3_chain.run_of(k)
    exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), share, known)
    reads = [(int(w, 16) & 0x0FFFFFFF, int(w, 16) >> 28) for w in exp["list"]]
    out = Path(scratch_dirs.mkdtemp(prefix="smout9_")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "list.bin").write_bytes(s1a_run.list_bytes(exp))
    (out / "acc.bin").write_bytes(s1a_run.acc_bytes(exp))
    exp = dict(exp, list_file=str(out / "list.bin"), acc_file=str(out / "acc.bin"))
    pl = s1a_run.pl_file(exp).read_bytes()
    u = Board9(fault, far_rule="skip", card_has_s2a=True, cells=CELLS if cells is None else cells, **device(known["census"], reads), **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), known, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s900000{k}.bin", stage)
    return rec, u, out


class WithAPlan(unittest.TestCase):
    def setUp(self) -> None:
        prepared()
        self.base = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in ("s2_3c", "s2_3s")}

    def test_the_sets_as_the_tests_write_them(self) -> None:
        for stage, base in self.base.items():
            par = [int(w, 16) for w in base["params"]]
            self.assertEqual((par[2], par[3], par[4], par[5], par[7], par[16], par[18], par[19]), (9, 0, 0x00401BA9, 0xB99, 0, 0, 0, 0), stage)
            self.assertEqual((par[24], par[25], par[26], par[28:32]), (0x40000000, 0x4000001F, 0x53324131, [0xF, 0, 0x00400800, 0x3F]), stage)
            self.assertEqual(base["pl_design"]["card_name"], "s2a.bit")
            self.assertNotIn("list", base); self.assertNotIn("acc", base)
        self.assertEqual(self.base["s2_3c"]["image_sha256"], hashlib.sha256(s1a_run.IMAGE.read_bytes()).hexdigest())

    def test_a_plan_fills_in_both_lists_and_what_follows_from_them(self) -> None:
        exp = s1a_run.with_plan("s2_3c", self.base["s2_3c"], None)
        par = [int(w, 16) for w in exp["params"]]
        self.assertEqual((par[7], par[16], par[18], par[19]), (18, 12, 7834, 0x00111000))
        self.assertEqual((len(exp["list"]), len(exp["acc"]), exp["records"], exp["result_words"]), (12, 2 * 7834, 4 + 18 * 12, 121278))
        self.assertEqual(exp["console"], ["SM9 start", "SM9 end status=00000001 records=000000dc anomalies=00000000 words=0001d9be"])
        self.assertEqual(exp["plan"], {"kind": "code", "share": None, "states": 18, "entries": 7834, "accesses": 7799, "reads": 12, "frames": 36,
                                       "first": "0x00401200", "last": "0x00401223"})
        self.assertEqual(exp["result_words"], s2_3_judge.layout_hdr("code") + exp["records"] * 480)
        self.assertEqual(len(s1a_run.planned_words(exp)), 32 + 12 + 2 * 7834)
        exp = s1a_run.with_plan("s2_3s", self.base["s2_3s"], 3)
        self.assertEqual((exp["plan"]["kind"], exp["plan"]["share"], exp["plan"]["states"], exp["plan"]["reads"], exp["plan"]["first"]), ("singles", 3, 66, 2, "0x0040121e"))
        self.assertEqual(exp["result_words"], s2_3_judge.layout_hdr("singles") + (4 + 66 * 2) * 480)

    def test_what_is_refused(self) -> None:
        self.assertRaisesRegex(ValueError, "one of four", s1a_run.with_plan, "s2_3s", self.base["s2_3s"], None)
        self.assertRaisesRegex(ValueError, "the code run is one run", s1a_run.with_plan, "s2_3c", self.base["s2_3c"], 0)
        self.assertRaisesRegex(ValueError, "no run 4", s1a_run.with_plan, "s2_3s", self.base["s2_3s"], 4)
        self.assertRaisesRegex(ValueError, "no plan made at run time", s1a_run.with_plan, "s2_2", self.base["s2_3s"], 0)
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--dry-run"]
        for args, why in ((["--stage", "s2_3s"], "REFUSED: a run of the singles is one of four (--share)"), (["--stage", "s2_3c", "--share", "0"], "REFUSED: the code run is one run"),
                          (["--stage", "s2_3s", "--share", "9"], "REFUSED: there is no run 9 of the singles")):
            r = subprocess.run(prog + args, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout.strip()), (2, why))

    def test_the_dry_run_lists_both_transfers_and_their_checksums_and_sends_nothing(self) -> None:
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_3s", "--share", "1", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        self.assertIn("stage s2_3s, the singles, run 1: 66 states, 21898 entries in the list of accesses, 2 reads a state, 0x0040121e .. 0x00401223", lines[0])
        text = " ".join(lines)
        for part in ("loady 10180000", "crc32 10180000 8", "loady 10190000", "send the list of accesses (21898 entries, 175184 bytes) by YMODEM", "crc32 10190000 2ac50",
                     f"4*({s2_3_judge.layout_hdr('singles')}+480*N)", "md.l 40000000 1", "Dry run: nothing was sent."):
            self.assertIn(part, text)
        order = [text.index(x) for x in ("md.l 40000000 1", "loady 10180000", "loady 10190000", "loady 02000000", "go 02000000")]
        self.assertEqual(order, sorted(order))


class ThroughTheRunScript(unittest.TestCase):
    def test_the_code_run_over_the_made_up_device(self) -> None:
        rec, u, out = run9(0)
        self.assertEqual((rec["verdict"], rec["problems"], rec["judge"]), ("PASS", [], "PASS"))
        self.assertEqual((rec["plan"]["kind"], rec["plan"]["share"], rec["plan"]["states"], rec["plan"]["reads"]), ("code", None, 18, 3))
        self.assertEqual((rec["result_layout"], rec["result_words"], rec["pl_source"]), ("s2_3c", s2_3_judge.layout_hdr("code") + 58 * 480, "card"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        v = json.loads((out / "verdict.json").read_text())
        self.assertEqual((v["run"]["kind"], v["finding"]["bits"]["follow"]), ("code", 256))
        self.assertEqual((u.blobs[s1a_run.LIST_ADDR], u.blobs[s1a_run.ACC_ADDR]), ((out / "list.bin").read_bytes(), (out / "acc.bin").read_bytes()))
        order = [u.commands.index(c) for c in ("md.l 40000000 1", "loady 10180000", "loady 10190000", "crc32 10190000 f4d0", "loady 02000000", "go 02000000")]
        self.assertEqual(order, sorted(order))
        self.assertFalse([e for e in u.twin_lines if e.startswith("VIOLATION")])

    def test_a_run_of_the_singles_over_the_made_up_device(self) -> None:
        rec, u, out = run9(3)
        self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
        self.assertEqual((rec["plan"]["kind"], rec["plan"]["share"], rec["result_layout"]), ("singles", 2, "s2_3s"))
        v = json.loads((out / "verdict.json").read_text())
        self.assertEqual(sorted(x["cell"] for x in v["finding"]["follows"]), list(range(128, 192)))

    def test_a_list_of_accesses_that_did_not_arrive_whole_stops_the_run_before_go(self) -> None:
        rec, u, out = run9(0, corrupt_acc=True)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn("crc32 10190000 f4d0", rec["stop"])
        self.assertNotIn("go 02000000", u.commands)
        self.assertFalse(rec.get("went"))

    def test_what_the_twin_says_no_to_fails_through_the_run_script_as_well(self) -> None:
        for fault, status in (("ramdisturb@9", "0xa0b"), ("ramstuck", "0xa0a"), ("seu", "0x105")):
            with self.subTest(fault):
                rec, u, out = run9(0, fault=fault)
                self.assertEqual((rec["verdict"], rec["judge"], rec["return_code"]), ("FAIL", "FAIL", status))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result, "saved whole whatever it says")

    def test_a_result_of_the_other_kind_of_run_has_another_layout(self) -> None:
        self.assertNotEqual(s1a_run.STAGES["s2_3c"]["judge"].HDR, s1a_run.STAGES["s2_3s"]["judge"].HDR)
        layouts = [(m["judge"].HDR, m["judge"].REC) for name, m in s1a_run.STAGES.items() if name in ("s2_2", "s2_3c", "s2_3s", "s2_1")]
        self.assertEqual(len(set(layouts)), 4, "no two of these stages' results can be taken for one another")
        self.assertLessEqual(s1a_run.MAX_RESULT_WORDS, 0x40000)

    def test_the_way_of_judging_a_stored_run_again_is_the_run_script_s(self) -> None:
        rec, u, out = run9(2)
        raw = (out / "result.bin").read_bytes()
        exp = s1a_run.with_plan("s2_3s", json.loads(s1a_run.STAGES["s2_3s"]["expected"].read_text()), 1, KNOWN)
        again = s2_3_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, s1a_run.planned_words(exp))
        self.assertEqual(json.loads(json.dumps(again)), json.loads((out / "verdict.json").read_text()))


class Chain(unittest.TestCase):
    """The chain over the made-up device: the code run, the table, the four runs of the singles."""

    def setUp(self) -> None:
        prepared()
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain9_")) / "chain"
        self.bases = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in ("s2_3c", "s2_3s")}
        self.calls: list[int] = []

    def runner(self, faults: dict | None = None, cells: dict | None = None, **quirks):
        def run(k: int, out: Path) -> None:
            self.calls.append(k)
            run9(k, KNOWN, fault=(faults or {}).get(k, ""), out=out, cells=(cells or {}).get(k), **quirks)
        return run

    def drive(self, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")     # the directories here are in no repository: said to be committed, unless a test asks
        return s2_3_chain.drive(self.root, self.bases, KNOWN, kw.pop("runner", self.runner()), **kw)

    def assess(self) -> dict:
        return s2_3_chain.assess(self.root, self.bases, KNOWN)

    def test_five_runs_and_the_step_is_closed(self) -> None:
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", [0, 1, 2, 3, 4], ["go on"] * 4 + ["complete"]))
        self.assertEqual((a["closing"]["confirmed"], a["closing"]["contradictions"], a["closing"]["ctl0"]), (256, 0, ["0x00000501"]))
        self.assertEqual([r.get("confirmed") for r in a["runs"]], [None] + [list(range(64 * k, 64 * k + 64)) for k in range(4)])
        doc = json.loads((self.root / "ram_map.json").read_text())
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["counts"], doc["runs"]["code"]["dir"], [s["dir"] for s in doc["runs"]["singles"]]),
                         ({"confirmed": 256, "decoded": 0, "contradiction": 0}, "run00", ["run01", "run02", "run03", "run04"]))
        places = where(CELLS)
        self.assertEqual({tuple(int(x, 0) if i else x for i, x in enumerate(e["address"].split("/"))): (e["cell"], e["inverted"]) for e in doc["entries"]}, places)
        table = json.loads((self.root / "table" / "table.json").read_text())
        self.assertEqual((table["schema"], table["outcome"][:2], len(table["table"]), table["code_run"]["dir"]), ("s2_3_table", "1:", 256, "run00"))
        stored = json.loads((self.root / "chain.json").read_text())
        self.assertEqual(stored, json.loads(json.dumps(s2_3_chain.brief(a))))
        self.assertNotIn("table", stored); self.assertEqual(len(stored["table_sha256"]), 64)
        self.assertEqual(stored["table_sha256"], hashlib.sha256((self.root / "table" / "table.json").read_bytes()).hexdigest())
        self.assertIn("the table written: table/table.json", said)
        self.assertTrue(said[-1].startswith("run04: singles 3, 64 bit(s) follow a cell, 0 inverted, 0 irregular, 64 cell(s) confirmed — complete"), said[-1])
        self.assertTrue((self.root / "prober.bin").read_bytes() == s1a_run.IMAGE.read_bytes())
        self.assertEqual(self.assess()["state"], "complete", "and it stands when looked at again")

    def test_looking_at_a_chain_writes_nothing_and_runs_nothing(self) -> None:
        a = self.assess()
        self.assertEqual((a["state"], a["next_run"], a["runs"], self.root.exists()), ("go on", 0, [], False))

    def test_no_single_is_started_before_the_code_run_and_the_table_are_committed(self) -> None:
        a = self.drive(committed=s2_3_chain.committed)   # the real question, of directories that are in no repository
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no single before the code run and its table are committed: run00", a["held"])
        self.assertNotIn("blocked", a)
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["held"], a["held"], "what holds it is in the chain's file")
        self.assertTrue((self.root / "table" / "table.json").is_file(), "the table is written when the code run is closed, before anything is asked of git")
        asked: list[Path] = []
        a = self.drive(committed=lambda path: asked.append(path) or ("" if path.name == "run00" else "table has files that are not in the last commit"))
        self.assertEqual((self.calls, asked), ([0], [self.root / "run00", self.root / "table"]), "both are asked, and the table alone holds it too")
        self.assertIn("no single before the code run and its table are committed: table has files", a["held"])
        a = self.drive(max_new=5, committed=s2_3_chain.committed)
        self.assertEqual(self.calls, [0], "and --max-new does not get past it")
        a = self.drive(max_new=1)
        self.assertEqual((a["state"], self.calls), ("go on", [0, 1]))

    def test_the_code_run_alone_with_max_new(self) -> None:
        a = self.drive(max_new=1)
        self.assertEqual((a["state"], a["next_run"], self.calls), ("go on", 1, [0]))
        self.assertEqual(a["closing_of_the_code_run"]["outcome"][:2], "1:")
        self.assertFalse((self.root / "ram_map.json").exists())

    def test_a_code_run_that_gives_no_table_halts_the_chain_and_no_single_is_run(self) -> None:
        a = self.drive(runner=self.runner(cells={0: CELLS[:255]}))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("run00: closed without a table — 2: a cell has no bit, or more than one — no table", a["why"])
        self.assertIn("run00: 1 cell(s) of the RAM have no bit that follows them", a["why"])
        self.assertFalse((self.root / "table").exists())
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []), "and nothing is run again")

    def test_a_code_run_that_is_not_a_passing_run_halts_it(self) -> None:
        for fault, words in (("ramdisturb@9", "0xa0b"), ("flip@7", "irregular")):
            with self.subTest(fault):
                self.setUp()
                a = self.drive(runner=self.runner(faults={0: fault}))
                self.assertEqual((a["state"], self.calls), ("halted", [0]))
                self.assertTrue(any(words in w for w in a["why"]), a["why"])
                self.assertFalse((self.root / "table").exists())

    def test_a_single_that_contradicts_the_table_halts_the_chain_there(self) -> None:
        other = CELLS + [(5, 1, 0xA05, 9, 9, 0)]       # in the second run of the singles, cell 69 shows at a second place as well
        a = self.drive(runner=self.runner(cells={2: other}))
        self.assertEqual((a["state"], self.calls), ("halted", [0, 1, 2]))
        self.assertEqual((a["runs"][2]["contradictions"][0]["cell"], len(a["runs"][2]["confirmed"])), (69, 63))
        self.assertTrue(any("run02: cell 69: its single changes 2 bit(s)" in w for w in a["why"]), a["why"])
        self.assertFalse((self.root / "ram_map.json").exists())
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []))

    def test_a_table_that_is_stored_is_held_to_the_code_run_and_never_written_over(self) -> None:
        self.drive(max_new=1)
        f = self.root / "table" / "table.json"
        table = json.loads(f.read_text())
        table["table"][0]["bit"] ^= 1
        f.write_text(json.dumps(table, indent=1) + "\n")
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("run00: the table stored with the chain is not the table the code run's verdict gives", a["why"])
        self.assertEqual(json.loads(f.read_text()), table, "it is left as it was found")

    def test_singles_without_a_table_and_a_table_without_a_code_run(self) -> None:
        self.drive(max_new=2)
        (self.root / "table" / "table.json").unlink(); (self.root / "table").rmdir()
        self.assertIn("run00: singles are stored and no table is", self.assess()["why"])
        self.setUp()
        (self.root / "table").mkdir(parents=True)
        self.assertEqual(self.assess()["why"], ["a table is stored and no code run"])

    def test_a_directory_for_the_table_without_the_table_starts_no_single(self) -> None:
        """Review of 5936a8e: run00 and table/ committed, the table itself not in it. The driver writes the table only
        where nothing has that name, so it would never come; a single was started all the same."""
        self.drive(max_new=1)
        f = self.root / "table" / "table.json"
        kept = f.read_bytes()
        f.unlink()
        (self.root / "table" / "README").write_text("the table comes later\n")
        asked: list[Path] = []
        a = self.drive(committed=lambda path: asked.append(path) or "")      # git has nothing against either directory
        self.assertEqual((a["state"], self.calls, asked), ("halted", [0], []))
        self.assertIn("run00: table/ is stored and the table (table.json) is not in it", a["why"])
        self.assertFalse(f.exists(), "and it is not written into a directory that was there")
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["state"], "halted")
        for what in ("a directory", "a link"):
            with self.subTest(what):
                if what == "a directory":
                    f.mkdir()
                else:
                    f.rmdir()
                    (self.root / "elsewhere.json").write_bytes(kept)
                    f.symlink_to(self.root / "elsewhere.json")       # the right words, and not a file of the table's directory
                self.assertIn("run00: table/ is stored and the table (table.json) is not in it", self.drive()["why"])
                self.assertEqual(self.calls, [0])
        f.unlink(); f.write_bytes(kept); (self.root / "table" / "README").unlink()
        self.assertEqual((self.drive(max_new=1)["state"], self.calls), ("go on", [0, 1]), "with the table back as it was written, it goes on")

    def test_a_link_that_leads_nowhere_in_the_table_s_place(self) -> None:
        self.drive(max_new=1)
        (self.root / "table" / "table.json").unlink(); (self.root / "table").rmdir()
        (self.root / "table").symlink_to(self.root / "nowhere")
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("run00: table/ is stored and the table (table.json) is not in it", a["why"])
        self.setUp()
        self.root.mkdir(parents=True)
        (self.root / "table").symlink_to(self.root / "nowhere")
        self.assertEqual(self.assess()["why"], ["a table is stored and no code run"])

    def test_a_run_made_under_another_ctl0_halts_the_chain_there(self) -> None:
        """Review of 5936a8e. CTL0 reads as another value all through one run of the singles: that run's judge has
        nothing against it (it holds the reads of a run to each other); the chain has, at that run, and no description
        is written."""
        plain, other = self.runner(), self.runner(env={"SM_CREG": "ctl0:00000401"})
        a = self.drive(runner=lambda k, out: (other if k == 2 else plain)(k, out))
        self.assertEqual((a["state"], self.calls), ("halted", [0, 1, 2]))
        self.assertEqual([(r["judge"], r["ctl0"], r["decision"]) for r in a["runs"]],
                         [("PASS", "0x00000501", "go on"), ("PASS", "0x00000501", "go on"), ("PASS", "0x00000401", "halt")])
        self.assertEqual(a["why"], ["run02: CTL0 read 0x00000401 in this run and 0x00000501 in the code run"])
        self.assertFalse((self.root / "ram_map.json").exists())
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []), "and nothing is run again")
        self.setUp()
        a = self.drive(runner=lambda k, out: (other if k == 0 else plain)(k, out), max_new=2)
        self.assertEqual((a["state"], self.calls, a["why"]), ("halted", [0, 1], ["run01: CTL0 read 0x00000501 in this run and 0x00000401 in the code run"]))

    def test_a_console_that_fails_before_a_run_holds_the_chain_and_says_so_in_its_file(self) -> None:
        """Review of 5936a8e: the serial adapter could not be opened, the exception ended the driver, and chain.json
        said "go on" and nothing of why."""
        import serial, uboot_console
        opened: list[object] = []

        class Port:
            def __init__(self, fails_at: str) -> None:
                self.fails_at, self.closed = fails_at, 0
                self.s = self.log = self
                opened.append(self)

            def close(self) -> None:
                self.closed += 1

            def interrupt(self):
                if self.fails_at == "interrupt":
                    raise OSError(5, "Input/output error")
                return b"", True

            def cmd(self, line: str, timeout: int):
                raise termios_error("(5, 'Input/output error')")

        import termios
        termios_error = termios.error

        def no_port():
            raise serial.SerialException("[Errno 2] could not open port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0")
        keep_log = os.environ.get("SELFMAP_CONSOLE_LOG")
        self.addCleanup(setattr, uboot_console, "UB", uboot_console.UB)
        self.addCleanup(lambda: os.environ.pop("SELFMAP_CONSOLE_LOG", None) if keep_log is None else os.environ.__setitem__("SELFMAP_CONSOLE_LOG", keep_log))
        for ub, words, closed in ((no_port, "SerialException: [Errno 2] could not open port", None), (lambda: Port("interrupt"), "OSError: [Errno 5] Input/output error", 2),
                                  (lambda: Port("cmd"), "error: (5, 'Input/output error')", 2)):
            with self.subTest(words):
                self.setUp(); opened.clear()
                uboot_console.UB = ub
                a = self.drive(runner=s2_3_chain.board_runner(self.root))
                self.assertEqual((a["state"], a.get("blocked")), ("go on", True))
                self.assertTrue(a["held"].startswith(f"before run00: the console failed — {words}"), a["held"])
                self.assertTrue(a["held"].endswith("; the run script was not started"), a["held"])
                stored = json.loads((self.root / "chain.json").read_text())
                self.assertEqual((stored["state"], stored["held"], stored["blocked"]), ("go on", a["held"], True))
                self.assertFalse((self.root / "run00").exists(), "no directory for a run that was not made")
                self.assertEqual([p.closed for p in opened], [] if closed is None else [closed], "a line that was opened is closed again")

    def test_it_goes_on_where_it_stands(self) -> None:
        self.drive(max_new=2)
        self.assertEqual(self.calls, [0, 1])
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("complete", [0, 1, 2, 3, 4]))

    def test_a_run_that_stopped_or_left_nothing_behind_halts_it_and_nothing_is_run_again(self) -> None:
        a = self.drive(runner=self.runner(faults={2: "err@40"}))
        self.assertEqual((a["state"], self.calls), ("halted", [0, 1, 2]))
        self.assertTrue(any("run02: the run script's verdict is FAIL" in w for w in a["why"]))
        self.setUp()
        a = self.drive(runner=lambda k, out: self.calls.append(k))
        self.assertEqual((a["state"], self.calls, a["why"]), ("halted", [0], ["run00: there is no run record"]))

    def test_what_is_stored_is_judged_again_and_must_be_what_it_was(self) -> None:
        self.drive(max_new=2)
        for name, change, words in (
                ("run01", lambda d: (d / "result.bin").write_bytes((d / "result.bin").read_bytes()[:-4] + b"\x01\x00\x00\x00"), "the stored result is not the one whose checksum the board gave"),
                ("run01", lambda d: (d / "verdict.json").write_text(json.dumps(dict(json.loads((d / "verdict.json").read_text()), verdict="pass"))), "the verdict stored beside the result is not what the judge says"),
                ("run00", lambda d: (d / "acc.bin").write_bytes(b"\0" * 8), "the list of accesses kept beside the run is not the list planned for it"),
                ("run00", lambda d: (d / "acc.bin").unlink(), "no list of accesses is kept beside the run"),
                ("run00", lambda d: (d / "list.bin").write_bytes(b"\0" * 4), "the list kept beside the run is not the list planned for its share")):
            with self.subTest(words):
                d = self.root / name
                kept = {p.name: p.read_bytes() for p in d.iterdir()}
                change(d)
                a = self.assess()
                self.assertEqual(a["state"], "halted")
                self.assertTrue(any(f"{name}: {words}" in w for w in a["why"]), a["why"])
                for n, b in kept.items():
                    (d / n).write_bytes(b)
        self.assertEqual(self.assess()["state"], "go on")

    def test_what_a_run_s_record_must_show_of_the_list_of_accesses(self) -> None:
        self.drive(max_new=1)
        f = self.root / "run00" / "run.json"
        rec = json.loads(f.read_text())
        cmd = next(s["cmd"] for s in rec["steps"] if s["cmd"].startswith("crc32 10190000"))

        def with_steps(fn) -> list[str]:
            r = json.loads(json.dumps(rec)); fn(r); f.write_text(json.dumps(r))
            a = self.assess()
            return a.get("why", [])
        gone = with_steps(lambda r: r.update(steps=[s for s in r["steps"] if s["cmd"] != cmd]))
        self.assertTrue(any("does not show the list of accesses planned for the run" in w for w in gone), gone)
        late = with_steps(lambda r: r["steps"].append(next(s for s in r["steps"] if s["cmd"] == cmd)) or r.update(steps=[s for i, s in enumerate(r["steps"]) if s["cmd"] != cmd or i == len(r["steps"]) - 1]))
        self.assertTrue(any("does not show the list of accesses planned for the run" in w for w in late), "a checksum after the start does not stand for one before it")
        other = with_steps(lambda r: [s.update(reply=s["reply"].replace("==> ", "==> 0")[:-1] if False else s["reply"][:-18] + "==> 00000000\r\nZynq> ") for s in r["steps"] if s["cmd"] == cmd])
        self.assertTrue(any("does not show the list of accesses planned for the run" in w for w in other), other)
        f.write_text(json.dumps(rec))
        self.assertEqual(self.assess()["state"], "go on")

    def edit_record(self, run: str, fn) -> None:
        f = self.root / run / "run.json"
        rec = json.loads(f.read_text()); fn(rec); f.write_text(json.dumps(rec))

    def test_what_a_run_s_record_must_say_of_the_run(self) -> None:
        self.drive(max_new=2)
        f = self.root / "run01" / "run.json"
        kept = f.read_text()
        for fn, says in ((lambda r: r.update(restart={"step": 5, "cmd": "go 02000000", "line": "resetting ..."}), "run01: a reply showed an exception or a restart"),
                         (lambda r: r.update(went=False), "run01: the prober was not started"),
                         (lambda r: r.update(stop="no prompt after 'md.l 10000000 40'"), "run01: the run script stopped: no prompt after"),
                         (lambda r: r.update(card_verified=False), "run01: the card copy was not verified"),
                         (lambda r: r.update(stage="s2_2"), "run01: the run record is of stage s2_2, not s2_3s"),
                         (lambda r: r.update(verdict="FAIL"), "run01: the run script's verdict is FAIL")):
            with self.subTest(says):
                self.edit_record("run01", fn)
                why = self.assess()["why"]
                self.assertTrue(any(says in w for w in why), why)
                f.write_text(kept)
        for text, says in (("[]", "the run record is not a record"), ('"x"', "the run record is not a record"), ("{", "there is no run record")):
            with self.subTest(text):
                f.write_text(text)
                self.assertTrue(any(says in w for w in self.assess()["why"]))
                self.assertEqual(self.drive(runner=lambda *_: self.fail("a run was started"))["state"], "halted")
        f.write_text(kept)
        self.assertEqual(self.assess()["state"], "go on")

    def test_sets_that_do_not_declare_the_same_image_and_design(self) -> None:
        other = dict(self.bases, s2_3s=dict(self.bases["s2_3s"], image_sha256="0" * 64))
        a = s2_3_chain.assess(self.root, other, KNOWN)
        self.assertEqual((a["state"], a["why"]), ("halted", ["the two sets of the step do not declare the same image and the same design"]))
        other = dict(self.bases, s2_3s=dict(self.bases["s2_3s"], pl_design=dict(self.bases["s2_3s"]["pl_design"], bytes=1)))
        self.assertEqual(s2_3_chain.assess(self.root, other, KNOWN)["state"], "halted")

    def test_a_link_where_a_run_is_to_be_is_no_run(self) -> None:
        self.drive(max_new=1)
        os.symlink("run00", self.root / "run01")         # a link to the code run's directory is not the first run of the singles
        self.assertEqual(self.assess()["why"], ["what has the name of a run and is not a directory: ['run01']"])
        a = self.drive(runner=lambda *_: self.fail("the runner was called"), refuses=lambda *_: self.fail("the run script was asked"))
        self.assertEqual((a["state"], json.loads((self.root / "chain.json").read_text())["state"]), ("halted", "halted"))

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
        sys.argv = ["s2_3_chain.py", "--dir", str(root), "--go"]
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            rc = s2_3_chain.main()
        self.assertEqual(rc, 1)
        self.assertIn("HELD: nothing was sent: the image of the build", said.getvalue())
        self.assertIn("0 run(s) stored of 5; the chain: go on", said.getvalue())
        stored = json.loads((root / "chain.json").read_text())
        self.assertEqual((stored["state"], stored["blocked"], stored["held"].startswith("nothing was sent: ")), ("go on", True, True))
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["chain.json", "prober.bin"])

    def test_a_run_of_another_kind_or_share_in_a_run_s_place(self) -> None:
        self.drive(max_new=3)
        a, b = self.root / "run01", self.root / "run02"
        tmp = self.root / "swap"
        a.rename(tmp); b.rename(a); tmp.rename(b)
        why = self.assess()["why"]
        self.assertTrue(any("run01: the run is singles, share 1; the chain plans singles, share 0 for it" in w for w in why), why)

    def test_gaps_and_too_many_and_what_is_not_a_directory(self) -> None:
        self.drive(max_new=1)
        (self.root / "run02").mkdir()
        self.assertIn("without a gap", self.assess()["why"][0])
        (self.root / "run02").rmdir()
        (self.root / "run01").write_text("x")
        self.assertIn("what has the name of a run and is not a directory", self.assess()["why"][0])
        (self.root / "run01").unlink()
        for k in range(1, 6):
            (self.root / f"run{k:02d}").mkdir()
        self.assertIn("6 run directories for 5 runs", self.assess()["why"][0])

    def test_directories_that_are_no_runs_are_set_aside_and_the_table_s_is_not_one_of_them(self) -> None:
        self.drive(max_new=1)
        (self.root / "halted_at_run01").mkdir()
        a = self.assess()
        self.assertEqual((a["state"], a["set_aside"]), ("go on", ["halted_at_run01"]))

    def test_nothing_is_sent_for_a_run_that_would_be_refused_or_with_another_image(self) -> None:
        a = self.drive(refuses=lambda k, out: "the run script refuses the run (REFUSED: x)")
        self.assertEqual((a["state"], self.calls, a["held"], a.get("blocked")), ("go on", [], "nothing was sent: the run script refuses the run (REFUSED: x)", True))
        self.assertFalse((self.root / "run00").exists())
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "prober.bin").write_bytes(b"another image")
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("halted", []))
        self.assertIn("the image kept with the runs is not the image the set declares", a["why"])

    def test_a_runner_that_could_not_begin_holds_the_chain(self) -> None:
        def cannot(k, out):
            raise RuntimeError("before run00: reset did not give the usual fresh prompt; nothing was run")
        a = self.drive(runner=cannot)
        self.assertEqual((a["state"], a.get("blocked"), a["held"]), ("go on", True, "before run00: reset did not give the usual fresh prompt; nothing was run"))

    def test_a_description_does_not_outlive_the_chain_it_was_written_for(self) -> None:
        self.drive()
        self.assertTrue((self.root / "ram_map.json").exists())
        (self.root / "run04" / "run.json").write_text("{}")
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual(a["state"], "halted")
        self.assertFalse((self.root / "ram_map.json").exists())
        self.assertIn("ram_map.json taken away: the chain is not complete as it is stored now", said)

    def test_the_real_plan_is_five_runs(self) -> None:
        self.assertEqual([s2_3_chain.run_of(k) for k in range(5)], [("s2_3c", None), ("s2_3s", 0), ("s2_3s", 1), ("s2_3s", 2), ("s2_3s", 3)])
        self.assertEqual(s2_3_chain.RUNS, 5)

    def test_the_run_script_s_own_dry_run_says_what_a_run_would_be_refused_for(self) -> None:
        self.assertEqual(s2_3_chain.refusal(0, self.root / "run00"), "")
        self.assertEqual(s2_3_chain.refusal(4, self.root / "run04"), "")
        self.root.mkdir(parents=True)
        (self.root / "run00").mkdir()
        self.assertEqual(s2_3_chain.refusal(0, self.root / "run00"), "REFUSED: --out must name a directory that does not exist yet")


class NothingOfThePart(unittest.TestCase):
    def test_the_programs_of_this_step_name_no_database_and_carry_no_number_of_the_part(self) -> None:
        """Closed-book, for the sources: what they know of the device they take from the census and from what S2.2
        found, at run time."""
        for name in ("s2_3_states.py", "s2_3_judge.py", "s2_3_table.py", "s2_3_chain.py", "s2_3c_judge.py", "s2_3s_judge.py"):
            text = (ROOT / "host" / name).read_text().lower()
            for word in ("prjxray", "segbits", "tilegrid", "part.json", "frame_count", "grade_", "1ba", "400000", "800000", "slice_x", "401220", "0x4012"):
                self.assertNotIn(word, text, f"{name}: {word}")
        core = (ROOT / "prober" / "sm_core.c").read_text()
        stage9 = core[core.index("stage 9 (S2.3)"):core.index("/* ------------------------------------------------------------------ stage S1a")]
        for word in ("1ba", "400000", "800000", "0xb9", "4012", "ram_pattern", "ram_depth", "srl_depth", "pl_ram", "pl_srl", "pl_count", "pl_writes"):
            self.assertNotIn(word, stage9.lower(), f"stage 9 knows no address of configuration memory and no register of the design but its identification: {word}")
        self.assertEqual(len(re.findall(r"\bPL_ID\b", stage9)), 1)


if __name__ == "__main__":
    unittest.main()

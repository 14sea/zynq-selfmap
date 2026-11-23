#!/usr/bin/env python3
"""S2.4: the states of the shift registers and the lists of a run (docs/s2_plan.md, sections 37 and 38) — and that
the stage of the prober as S2.3 left it runs them: on the twin, with the image's own source, nothing changed."""
from __future__ import annotations

import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s2_2_shares  # noqa: E402
import s2_3_states as st9  # noqa: E402
import s2_4_states as st  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402

DESIGN = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
CENSUS = json.loads(s2_2_shares.CENSUS.read_text())
WORDS = [0xA5C30F69, 0x0F1E2D3C, 0x13579BDF, 0xFEDCBA98]       # what the design loads its four shift registers with (pl/s2a/design.json)
LOADED = [sum(((WORDS[k] >> a) & 1) << k for k in range(4)) for a in range(32)]   # as a state: the word at address a, bit k from register k
REG = {"RAM_ADDR": 0x4000000C, "RAM_DATA": 0x40000010, "SRL_ADDR": 0x40000014, "SRL_DATA": 0x40000018, "COUNT": 0x40000008, "WRITES": 0x4000001C}
CANDIDATES = {"frames_with_candidates": {f"{f:#010x}": 64 for f in range(0x1820, 0x1824)}}     # where the prediction points: a made-up file of part 1


def word_of(state: list[int], k: int) -> int:
    return sum(((state[a] >> k) & 1) << a for a in range(32))


class TheStates(unittest.TestCase):
    def test_what_the_design_loads_and_the_numbering(self) -> None:
        self.assertEqual(st9.srl_words(DESIGN), LOADED)
        self.assertEqual(LOADED[:4] + LOADED[-2:], [0x5, 0x4, 0x6, 0xF, 0x8, 0x9], "the first and the last, written out")
        self.assertEqual([word_of(LOADED, k) for k in range(4)], WORDS)
        self.assertEqual((st.CELLS, st.number(0, 0), st.number(3, 31), st.number(1, 5)), (128, 0, 127, 37))
        self.assertEqual([st.cell(LOADED, st.number(k, a)) for k in range(4) for a in range(32)], [(WORDS[k] >> a) & 1 for k in range(4) for a in range(32)])

    def test_the_code_states_tell_every_cell_from_every_other(self) -> None:
        states = [x["srl"] for x in st.code_run(LOADED)][1:-1]
        self.assertEqual(len(states), 14)
        rows = {n: tuple(st.cell(s, n) for s in states) for n in range(128)}
        self.assertEqual(len(set(rows.values())), 128)
        for n, row in rows.items():
            self.assertEqual(row, tuple(x for j in range(7) for x in ((n >> j) & 1, 1 - ((n >> j) & 1))), n)
        self.assertEqual([word_of(st.code(0), k) for k in range(4)], [0xAAAAAAAA] * 4)
        self.assertEqual([word_of(st.code(5), k) for k in range(4)], [0, 0xFFFFFFFF, 0, 0xFFFFFFFF], "bit 5 of a cell's number: which register, its low bit")
        self.assertEqual([word_of(st.code(6, True), k) for k in range(4)], [0xFFFFFFFF, 0xFFFFFFFF, 0, 0])

    def test_a_single_is_the_loaded_content_with_one_cell_the_other_way(self) -> None:
        for n in (0, 31, 32, 77, 127):
            s = st.single(LOADED, n)
            self.assertEqual([m for m in range(128) if st.cell(s, m) != st.cell(LOADED, m)], [n])
        self.assertEqual(st.single(LOADED, 77), LOADED[:13] + [LOADED[13] ^ 4] + LOADED[14:])

    def test_thirty_two_shifts_make_a_state_whatever_was_there(self) -> None:
        self.assertEqual(st.shifted([1, 2, 3, 4], 0x1F), [0xF, 1, 2, 3], "one shift: the word comes in at output 0, the rest move up, the last is lost")
        for state in (st.code(3), st.single(LOADED, 77), LOADED, st.uniform(1), st.uniform(0)):
            for before in ([9] * 32, LOADED, st.uniform(1)):
                held = list(before)
                for w in st.shifts(state):
                    held = st.shifted(held, w)
                self.assertEqual(held, state)
        self.assertEqual(st.shifts(LOADED), LOADED[::-1], "what is to end at output 31 is written first")

    def test_the_runs(self) -> None:
        self.assertEqual([(x["name"], x["srl"], x["shifted"]) for x in st.find_run()], [("all zero", [0] * 32, True), ("all one", [15] * 32, True), ("all zero", [0] * 32, True)])
        code = st.code_run(LOADED)
        self.assertEqual([x["name"] for x in code], ["as loaded"] + [f"code {j}{c}" for j in range(7) for c in ("", " complement")] + ["loaded again"])
        self.assertEqual([(x["srl"], x["shifted"]) for x in (code[0], code[-1])], [(LOADED, False), (LOADED, True)], "the same content, once loaded and once shifted in")
        self.assertEqual({x["shifted"] for x in code[1:]}, {True})
        singles = [st.single_run(LOADED, r) for r in range(2)]
        self.assertEqual([[x["name"] for x in run] for run in singles],
                         [["as loaded"] + [f"single {n}" for n in range(64 * r, 64 * r + 64)] + ["loaded again"] for r in range(2)])
        self.assertEqual(sorted(x["cell"] for run in singles for x in run if x["kind"] == "single"), list(range(128)))
        self.assertEqual([(run[0]["shifted"], run[1]["shifted"], run[-1]["shifted"]) for run in singles], [(False, True, True)] * 2)
        for r in (-1, 2):
            self.assertRaisesRegex(ValueError, "no run", st.single_run, LOADED, r)


class TheLists(unittest.TestCase):
    def test_the_accesses_of_a_run_state_by_state(self) -> None:
        """Written out here for the three states of part 1: the shifts; all 32 outputs read back and held; the counter;
        the mark; the outputs again; the counter; the design's count — the shifts so far in its high half and no write
        to the RAM; the mark. The RAM, all 64 addresses held to zero, before the first state's frames and after the
        last state's."""
        e = st.accesses(st.find_run(), DESIGN)
        back = lambda v: [x for a in range(32) for x in ((st.A_WRITE, REG["SRL_ADDR"], a), (st.A_EXPECT, REG["SRL_DATA"], v))]
        ram = [x for a in range(64) for x in ((st.A_WRITE, REG["RAM_ADDR"], a), (st.A_EXPECT, REG["RAM_DATA"], 0))]
        count, frames, end = (st.A_READ, REG["COUNT"], 0), (st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)
        want: list = []
        for i, v in enumerate((0, 15, 0)):
            want += [(st.A_WRITE, REG["SRL_DATA"], v)] * 32 + back(v) + (ram if i == 0 else []) + [count, frames] + back(v)
            want += [count, (st.A_EXPECT, REG["WRITES"], (32 * (i + 1)) << 16)] + (ram if i == 2 else []) + [end]
        self.assertEqual(e, want)
        self.assertEqual(len(e), 751)

    def test_a_state_as_loaded_is_made_by_no_shift_and_counts_none(self) -> None:
        e = st.accesses(st.code_run(LOADED), DESIGN)
        first = e[:e.index((st.A_MARK, 0, st.MARK_END)) + 1]
        self.assertNotIn(REG["SRL_DATA"], {a for k, a, _ in first if k == st.A_WRITE}, "nothing shifted")
        self.assertEqual([v for k, a, v in first if a == REG["SRL_DATA"]], LOADED * 2, "read back as loaded, before the frames and after")
        self.assertIn((st.A_EXPECT, REG["WRITES"], 0), first)
        counts = [v for k, a, v in e if a == REG["WRITES"]]
        self.assertEqual(counts, [(32 * i) << 16 for i in range(16)], "fifteen states of thirty-two shifts after it")
        self.assertEqual(sum(1 for k, a, _ in e if k == st.A_WRITE and a == REG["SRL_DATA"]), 15 * 32)
        self.assertEqual(st9.may_write(e, DESIGN), 1 << 0x0C | 1 << 0x14 | 1 << 0x18, "the two address registers and the shift registers' data: inside the image's bound")
        self.assertEqual(st9.may_write(e, DESIGN) & ~T.BOUND, 0)

    def test_the_plans(self) -> None:
        shares = s2_2_shares.shares(CENSUS)
        for share in range(8):
            p = st.plan("find", share, DESIGN, CENSUS)
            self.assertEqual((p["reads"], len(p["states"]), len(p["entries"]), p["may_write"]), (shares[share], 3, 751, 0x01101000), share)
            self.assertLessEqual(p["result_words"], st.RESULT_MAX_WORDS)
        self.assertEqual([st.plan("find", s, DESIGN, CENSUS)["result_words"] for s in (0, 3, 7)], [254052, 256932, 121572])
        code = st.plan("code", None, DESIGN, CENSUS, CANDIDATES)
        self.assertEqual((len(code["states"]), code["reads"], len(code["entries"]), code["result_words"]),
                         (16, [(0x1800 + 3 * i, 3) for i in range(12)], 2864, 99826))
        for r in range(2):
            p = st.plan("singles", r, DESIGN, CENSUS, CANDIDATES)
            self.assertEqual((len(p["states"]), p["reads"], len(p["entries"]), p["result_words"]), (66, [(0x181E, 3), (0x1821, 3)], 11114, 87326))

    def test_what_is_no_run_of_the_step_gives_no_plan(self) -> None:
        for kind, share, cand, why in (("find", None, None, "which"), ("find", 8, None, "which"), ("find", -1, None, "which"), ("code", 0, CANDIDATES, "one run"),
                                       ("code", None, None, "what part 1 found is not given"), ("singles", None, CANDIDATES, "which"),
                                       ("singles", 2, CANDIDATES, "no run 2"), ("singles", 0, None, "what part 1 found is not given"), ("pairs", None, CANDIDATES, "no run of the kind")):
            self.assertRaisesRegex(ValueError, why, st.plan, kind, share, DESIGN, CENSUS, cand)
        fewer = dict(CENSUS, entries=CENSUS["entries"][:2000])
        try:
            n = len(s2_2_shares.shares(fewer))
        except ValueError:
            n = None
        if n is not None and n != 8:
            self.assertRaisesRegex(ValueError, "not the 8 the step is planned for", st.plan, "find", 0, DESIGN, fewer)

    def test_a_list_or_a_result_too_long_for_the_stage_is_refused(self) -> None:
        many = [dict(st.find_run()[1]) for _ in range(81)]
        self.assertRaisesRegex(ValueError, "entries; a list holds", st.accesses, [dict(st.find_run()[1]) for _ in range(300)], DESIGN)
        keep = st.find_run
        try:
            st.find_run = lambda: many
            self.assertRaisesRegex(ValueError, "81 states; the stage takes 80", st.plan, "find", 0, DESIGN, CENSUS)
            st.find_run = lambda: many[:4]
            self.assertRaisesRegex(ValueError, r"the result would have 3\d{5} words; its area holds 262144", st.plan, "find", 3, DESIGN, CENSUS)
        finally:
            st.find_run = keep


class TheStageAsItIs(unittest.TestCase):
    """Section 38, point 3: no new image. The lists of S2.4 on the twin of the prober, whose source is the image's."""

    def run9(self, states: list[dict], **kw) -> T.Run:
        e = st.accesses(states, DESIGN)
        return T.Run(states=states, entries=e, shifts=True, w19=st9.may_write(e, DESIGN), **kw)

    def test_the_stage_runs_the_states_of_s2_4_to_their_end(self) -> None:
        for name, states in (("part 1", st.find_run()), ("the code run", st.code_run(LOADED)), ("some singles", st.single_run(LOADED, 1)[:4] + st.single_run(LOADED, 1)[-1:])):
            r = self.run9(states)
            self.assertEqual((r.status, r.rc, r.n_records, r.plb[2]), (1, 0, 4 + len(states) * len(T.COLUMN_READS), 0), name)
            self.assertEqual(r.violations, [], name)
            shifts = [v for a, w, v in r.pl_accesses() if w and a == REG["SRL_DATA"]]
            self.assertEqual(shifts, [w for s in states if s["shifted"] for w in st.shifts(s["srl"])], name)
            self.assertEqual(r.pl_log(), [(a, w, v) for a, w, v in r.pl_accesses()], "the log is what was done")
            self.assertEqual([v for a, w, v in r.pl_accesses() if not w and a == REG["WRITES"]], [(sum(32 for s in states[:i + 1] if s["shifted"])) << 16 for i in range(len(states))], name)

    def test_a_set_that_does_not_allow_the_shift_is_refused_before_anything_is_touched(self) -> None:
        e = st.accesses(st.find_run(), DESIGN)
        r = T.Run(states=st.find_run(), entries=e, shifts=True, w19=T.MAY_WRITE)
        self.assertEqual((r.status, r.touched()), (0x500, False))

    def test_shift_registers_that_do_not_hold_what_was_shifted_in_stop_the_run_there(self) -> None:
        wrong = [dict(s) for s in st.find_run()]
        e = st.accesses(wrong, DESIGN)
        at = next(i for i, (k, a, v) in enumerate(e) if k == st.A_EXPECT and a == REG["SRL_DATA"])
        e[at + 10] = (st.A_EXPECT, REG["SRL_DATA"], 1)          # the list says an output holds what was not shifted in
        r = T.Run(states=wrong, entries=e, shifts=True, w19=st9.may_write(e, DESIGN))
        self.assertEqual((r.status >> 8, r.plb[2] != 0, r.n_records), (0xA, True, 2), "stopped at the reading, before any frame of the list")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""S2.5, part 1 (docs/s2_plan.md, sections 45 to 47): the states and lists, the twin's model of the design s2b, the
judge of a run of the step, the sets in the run script, the search for the loaded words, and the chain over the shares
— on the twin and on the pretend board, over a made-up device (tests/s2_5_made_up.py). No board is touched."""
from __future__ import annotations

import copy, hashlib, json, struct, subprocess, sys, unittest, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_2_shares  # noqa: E402
import s2_3_states as st9  # noqa: E402
import s2_5_chain  # noqa: E402
import s2_5_find  # noqa: E402
import s2_5_judge  # noqa: E402
import s2_5_predict  # noqa: E402
import s2_5_states as st  # noqa: E402
import s2_5_made_up as M  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402
import test_s2_3_host as H9  # noqa: E402
from s2_5_made_up import CTL0, DESIGN, ID, KNOWN, LOADED, RULE, SITES, WORDS, alike, b_map, judged, once, run5, twin  # noqa: E402

REG = st9.registers(DESIGN)
CENSUS = json.loads(s2_2_shares.CENSUS.read_text())


def clean(kind: str = "find", share: int | None = 1) -> tuple[dict, T.Run, dict]:
    def make():
        known = KNOWN if kind == "find" else dict(KNOWN, candidates={"frames_with_candidates": {f"{g + f:#010x}": 0 for g in M.GROUPS for f in range(4)}})
        p, r = twin(kind, share, known=known)
        return p, r, judged(p, r, known)
    return once(("clean", kind, share), make)


class TheStates(unittest.TestCase):
    def test_the_runs(self) -> None:
        self.assertEqual([(s["name"], s["ram"] and s["ram"][:2]) for s in st.find_run()], [("as loaded", None), ("all one", [15, 15]), ("all zero", [0, 0])])
        code = st.code_run()
        self.assertEqual((len(code), code[0]["ram"], code[-1]["ram"], code[1]["name"], code[2]["name"]), (18, [0] * 64, [0] * 64, "code 0", "code 0 complement"))
        self.assertEqual([st.cell(code[1 + 2 * j]["ram"], 0xB5) for j in range(8)], [1, 0, 1, 0, 1, 1, 0, 1], "in code state j a cell holds bit j of its number")
        self.assertEqual({tuple(st.cell(s["ram"], n) for s in code) for n in range(256)}.__len__(), 256, "and the states tell every cell from every other")
        one = st.single_run(3)
        self.assertEqual((len(one), [s.get("cell") for s in one[1:-1]], one[0]["ram"], one[-1]["ram"]), (18, list(range(48, 64)), [0] * 64, [0] * 64))
        self.assertEqual([sum(bin(v).count("1") for v in s["ram"]) for s in one], [0] + [1] * 16 + [0])
        self.assertEqual(sorted(s["cell"] for r in range(st.SINGLE_RUNS) for s in st.single_run(r)[1:-1]), list(range(256)), "sixteen runs, every cell once")
        self.assertRaisesRegex(ValueError, "no run 16 of the singles", st.single_run, 16)
        self.assertRaisesRegex(ValueError, "no run -1 of the singles", st.single_run, -1)

    def test_what_the_design_loads_and_what_the_reading_over_all_sites_gives(self) -> None:
        self.assertEqual((len(LOADED), len(WORDS), len(set(WORDS)), f"{LOADED[0][0]:#x}"), (110, 440, 440, "0xca009717f87d8879"))
        self.assertEqual([st.check_of(v) for v in ([0] * 110, [15] * 110, [5] * 110, [5] * 109 + [4], [1, 2])], [0x000, 0x0FF, 0x055, 0x145, 0x303])
        loaded = st.checks(None, DESIGN)
        for a in (0, 17, 63):                           # written out again: bit a of every site's word of memory k
            held = [sum(((w[k] >> a) & 1) << k for k in range(4)) for w in LOADED]
            self.assertEqual(loaded[a], (15 if any(held) else 0) & __import__("functools").reduce(int.__or__, held) | __import__("functools").reduce(int.__and__, held) << 4
                             | __import__("functools").reduce(int.__xor__, held) << 8)
        self.assertEqual(len({x >> 8 for x in loaded}), 16, "the parities of the loaded words take every value: a wrong address would be seen")
        self.assertEqual(st.checks([3] * 64, DESIGN), [0x033] * 64, "110 sites alike: no parity")
        bad = copy.deepcopy(DESIGN); bad["ram"]["sites"][4]["site"] = 9
        self.assertRaisesRegex(ValueError, "does not list its sites in order", st.loaded, bad)

    def test_the_list_of_accesses_of_a_run_of_part_1(self) -> None:
        e = st.accesses(st.find_run(), DESIGN)
        site, addr, data, check, count, writes = (REG[n] for n in ("SITE", "RAM_ADDR", "RAM_DATA", "CHECK", "COUNT", "WRITES"))
        self.assertEqual(e[:2], [(st.A_WRITE, site, 0x100), (st.A_EXPECT, site, 0x100)], "every write of the run goes to every site")
        self.assertEqual((len(e), sum(1 for x in e if x[0] == st.A_MARK), sum(1 for x in e if x[:2] == (st.A_WRITE, data))), (1044, 6, 128))
        self.assertEqual({x[1] for x in e if x[0] == st.A_WRITE}, {site, addr, data}, "the three registers the design takes a write at")
        self.assertEqual(st9.may_write(e, DESIGN), 0x00011010)
        self.assertFalse([x for x in e if x[1] == data and x[0] != st.A_WRITE], "no site is read alone")
        marks = [i for i, x in enumerate(e) if x[0] == st.A_MARK]
        first = e[2:marks[0]]                             # the state as loaded: nothing written, the reading over all sites at every address, the counter
        self.assertEqual(first[:-1], [x for a, v in enumerate(st.checks(None, DESIGN)) for x in ((st.A_WRITE, addr, a), (st.A_EXPECT, check, v))])
        self.assertEqual(first[-1], (st.A_READ, count, 0))
        after = e[marks[0] + 1:marks[1]]
        self.assertEqual(after[:128], first[:-1], "and the same readings again after the frames")
        self.assertEqual(after[128:], [(st.A_READ, count, 0), (st.A_EXPECT, writes, 0), (st.A_EXPECT, site, 0x100)])
        second = e[marks[1] + 1:marks[2]]
        self.assertEqual(second[:128], [x for a in range(64) for x in ((st.A_WRITE, addr, a), (st.A_WRITE, data, 15))])
        self.assertEqual(second[128:256], [x for a in range(64) for x in ((st.A_WRITE, addr, a), (st.A_EXPECT, check, 0x0FF))])
        self.assertEqual(e[marks[4] + 1:marks[5]][-2], (st.A_EXPECT, writes, 128))
        self.assertEqual([(x[2]) for x in e if x[0] == st.A_MARK], [st.MARK_FRAMES, st.MARK_END] * 3)

    def test_a_later_state_is_written_only_where_it_differs(self) -> None:
        e = st.accesses(st.single_run(0), DESIGN)
        data = REG["RAM_DATA"]
        marks = [i for i, x in enumerate(e) if x[0] == st.A_MARK]
        written = [[x[2] for x in e[(marks[2 * s - 1] + 1 if s else 0):marks[2 * s]] if x[:2] == (st.A_WRITE, data)] for s in range(18)]
        self.assertEqual([len(w) for w in written], [64, 1] + [2] * 15 + [1], "the base whole; the first single one write; then one cleared and one set; the base again")
        self.assertEqual({len(st.accesses(st.single_run(r), DESIGN)) for r in range(16)}, {4910}, "every run of the singles is as long: one layout for the sixteen")
        self.assertEqual(len(st.accesses(st.code_run(), DESIGN)), 6638)
        self.assertRaisesRegex(ValueError, "the state as loaded can only be a run's first", st.accesses, st.find_run()[1:] + st.find_run()[:1], DESIGN)

    def test_the_plans_of_the_device(self) -> None:
        plans = [st.plan("find", s, DESIGN, CENSUS) for s in range(8)]
        self.assertEqual([len(p["reads"]) for p in plans], [174, 174, 174, 176, 172, 176, 172, 82])
        self.assertEqual({(len(p["states"]), len(p["entries"]), len(p["log"]), p["may_write"]) for p in plans}, {(3, 1044, 1039, 0x00011010)})
        self.assertEqual(max(p["result_words"] for p in plans), 257518)
        self.assertLess(257518, st.RESULT_MAX_WORDS)
        self.assertEqual(sum(n for p in plans for _, n in p["reads"]), 3864, "all of block type 0, once")
        self.assertRaisesRegex(ValueError, "one share of 8: which", st.plan, "find", None, DESIGN, CENSUS)
        self.assertRaisesRegex(ValueError, "one share of 8: which", st.plan, "find", 8, DESIGN, CENSUS)
        self.assertRaisesRegex(ValueError, "no run of the kind 'pairs'", st.plan, "pairs", None, DESIGN, CENSUS)
        self.assertRaisesRegex(ValueError, "what part 1 found is not given", st.plan, "code", None, DESIGN, CENSUS)
        # part 2 over what the prediction says part 1 will find: 24 reads, and both kinds of run fit
        said = json.loads(s2_5_chain.PREDICTION.read_text())
        cand = {"frames_with_candidates": sorted({f"{k[0]:#010x}" for k in s2_5_predict.places(said)})}
        code, single = st.plan("code", None, DESIGN, CENSUS, cand), st.plan("singles", 15, DESIGN, CENSUS, cand)
        self.assertEqual((len(code["reads"]), len(code["states"]), len(code["entries"]), code["result_words"]), (24, 18, 6638, 222566))
        self.assertEqual((len(single["reads"]), len(single["states"]), len(single["entries"]), single["result_words"], single["may_write"]), (24, 18, 4910, 219110, 0x00011010))
        self.assertEqual(code["reads"][:2], [(0x0000121E, 3), (0x00001221, 3)], "a column's last four frames lie in its last two reads of three")
        self.assertRaisesRegex(ValueError, "the code run is one run", st.plan, "code", 0, DESIGN, CENSUS, cand)
        self.assertRaisesRegex(ValueError, "one of 16: which", st.plan, "singles", None, DESIGN, CENSUS, cand)
        self.assertRaisesRegex(ValueError, "no candidate", st.plan, "code", None, DESIGN, CENSUS, {"frames_with_candidates": []})
        self.assertRaisesRegex(ValueError, "no address of block type 0", st.plan, "code", None, DESIGN, CENSUS, {"frames_with_candidates": ["0x00c00000"]})
        every = {"frames_with_candidates": [f"{far:#010x}" for far in s2_2_shares.layout(CENSUS)["block0"]]}
        self.assertRaisesRegex(ValueError, "1300 reads; a run's list holds 178", st.plan, "code", None, DESIGN, CENSUS, every)
        much = {"frames_with_candidates": [f"{far:#010x}" for far in s2_2_shares.layout(CENSUS)["block0"][:90]]}
        self.assertRaisesRegex(ValueError, "the result would have .* words; its area holds", st.plan, "code", None, DESIGN, CENSUS, much)


class TheTwinSModelOfTheDesign(unittest.TestCase):
    """The registers of s2b on the twin, asked through a list of accesses as the prober makes one."""

    def run_of(self, entries, **kw) -> T.Run:
        reg = REG
        full = [(k, reg[n] if isinstance(n, str) else n, v) for k, n, v in entries] + [(st.A_MARK, 0, st.MARK_FRAMES), (st.A_MARK, 0, st.MARK_END)]
        return T.Run(states=[{}], entries=full, w19=T.BOUND, w26=ID, cells=[], design_b=(WORDS, kw.pop("cells", [])), **kw)

    def test_one_site_and_every_site(self) -> None:
        R, W = st.A_READ, st.A_WRITE
        w5, w6 = LOADED[5], LOADED[6]
        bits = lambda w, a: sum(((w[k] >> a) & 1) << k for k in range(4))   # noqa: E731
        r = self.run_of([(R, "SITE", 0), (W, "SITE", 5), (W, "RAM_ADDR", 3), (R, "RAM_DATA", 0), (W, "RAM_DATA", 0xA), (R, "RAM_DATA", 0),
                         (W, "SITE", 6), (R, "RAM_DATA", 0), (R, "CHECK", 0), (W, "SITE", 0x100 | 6), (R, "SITE", 0), (W, "RAM_DATA", 0x6), (R, "RAM_DATA", 0),
                         (W, "SITE", 5), (R, "RAM_DATA", 0), (R, "CHECK", 0), (R, "WRITES", 0), (W, "SITE", 0x7F), (R, "RAM_DATA", 0), (W, "RAM_DATA", 0xF),
                         (W, "SITE", 0), (R, "RAM_DATA", 0), (R, 0x40000014, 0), (W, "SITE", 0xFFFFFFFF), (R, "SITE", 0), (W, "RAM_ADDR", 0x43), (R, "RAM_ADDR", 0)])
        self.assertEqual((r.status, r.violations), (1, []))
        got = [v for a, w, v in r.pl_log() if not w][1:]
        held = [bits(w, 3) for w in LOADED]; held[5] = 0xA
        self.assertEqual(got, [0, bits(w5, 3), 0xA, bits(w6, 3), st.check_of(held), 0x106, 0x6, 0x6, 0x066, 2, 0, 0x6, 0, 0x17F, 3])

    def test_a_write_to_what_takes_none_is_said(self) -> None:
        r = self.run_of([(st.A_WRITE, 0x40000014, 1), (st.A_WRITE, 0x40000018, 1), (st.A_READ, "WRITES", 0)])
        self.assertEqual(len(r.violations), 2, r.violations)
        self.assertEqual([v for a, w, v in r.pl_log() if not w][1:], [0])

    def test_the_cells_show_where_the_map_says(self) -> None:
        p, r, v = clean()
        frames = s2_5_find.frames_in_state(r.words, 0)
        for (far, word, bit), (s, k, a) in list(M.where(b_map()).items())[::997]:
            self.assertEqual(frames[far][word] >> bit & 1, LOADED[s][k] >> a & 1, (s, k, a))
        ones = s2_5_find.frames_in_state(r.words, 1)
        self.assertEqual(ones[0xB84][0], 0xFFFFFFFF)
        self.assertEqual(s2_5_find.frames_in_state(r.words, 2)[0xB84][:3], (0, 0, 0))


class TheJudge(unittest.TestCase):
    def test_a_run_of_part_1_passes_and_says_what_follows(self) -> None:
        p, r, v = clean()
        self.assertEqual((r.status, r.violations, v["verdict"], v["problems"]), (1, [], "PASS", []))
        self.assertEqual(v["run"], {"kind": "find", "share": 1, "states": ["as loaded", "all one", "all zero"]})
        f = v["finding"]
        self.assertEqual((f["states_read_whole"], f["frames"], f["bits"]), (3, 30, {"still": 30 * 101 * 32 - 28160, "follow": 28160, "follow_inverted": 0, "irregular": 0}))
        got = s2_5_judge.places(f["follows"])
        want = {place: (LOADED[s][k] >> a & 1, False) for place, (s, k, a) in M.where(b_map()).items()}
        alike(self, got, want, "every place of every cell, each with what it read as loaded: the bit its memory's word has there")
        self.assertEqual((len(f["follows"]), set(f["follows"][0]), f["follows"][0]["bits"]), (880, {"far", "word", "bits", "inverted", "as_loaded"}, list(range(32))))
        pl = v["pl"]
        self.assertEqual((pl["code"], pl["id"], pl["sites"], pl["passes_the_sites_held_through"], pl["writes_counted"], pl["addresses_as_loaded"], pl["accesses"]),
                         ("0x0", "0x53324231", 110, 3, 128, [64, 0, 0], 1039))
        self.assertEqual(v["registers"]["CTL0"]["value"], CTL0)

    def test_the_other_shares_read_no_candidate_and_pass(self) -> None:
        for share in (0, 2):
            p, r = twin("find", share)
            v = judged(p, r)
            self.assertEqual((v["verdict"], v["run"]["share"], v["finding"]["bits"]["follow"], v["finding"]["follows"]), ("PASS", share, 0, []), share)

    def test_the_code_run_and_a_run_of_the_singles_pass_and_name_the_cells(self) -> None:
        p, r, v = clean("code", None)
        self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], v["run"]["share"], len(v["run"]["states"])), ("PASS", [], "code", None, 18))
        f = v["finding"]
        self.assertEqual((f["bits"]["follow"], f["bits"]["follow_inverted"], f["bits"]["irregular"], f["cells_not_told_apart"], f["cells_not_told_from_another_inverted"]),
                         (28160, 0, 0, [], []))
        alike(self, s2_5_judge.places(f["follows"]), {place: (64 * k + a, False) for place, (s, k, a) in M.where(b_map()).items()}, "every place with its cell")
        self.assertEqual(v["pl"]["addresses_as_loaded"], [0] * 18, "every address was written before the first frames were read")
        p, r, v = clean("singles", 3)
        self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], v["run"]["share"]), ("PASS", [], "singles", 3))
        got = s2_5_judge.places(v["finding"]["follows"])
        alike(self, got, {place: (64 * k + a, False) for place, (s, k, a) in M.where(b_map()).items() if 48 <= 64 * k + a < 64}, "the places of the run's sixteen cells")
        self.assertEqual((len(got), v["finding"]["bits"]["follow"]), (16 * 110, 1760))

    def test_a_place_shown_inverted_follows_inverted(self) -> None:
        p, r = twin(cells=b_map(inverted={(7, 2, 9), (99, 0, 0)}))
        v = judged(p, r)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"], v["finding"]["bits"]["follow_inverted"]), ("PASS", 28158, 2))
        got = s2_5_judge.places(v["finding"]["follows"])
        self.assertEqual({k for k, (_, inv) in got.items() if inv}, {M.at(7, 2, 9), M.at(99, 0, 0)})
        self.assertEqual(got[M.at(7, 2, 9)][0], 1 - (LOADED[7][2] >> 9 & 1), "what it read as loaded is set down as read: the opposite of the cell's bit")

    def test_a_bit_that_moves_and_follows_no_cell_fails_the_run(self) -> None:
        p, r, v = clean()
        w = list(r.words)
        i = r.hb + (2 + 1 * len(p["reads"]) + 0) * T.REC + T.DATA + T.FRAME * 1 + 100   # state "all one", the first read's first frame (0xb80), word 100
        w[i] ^= 1 << 7
        v1 = judged(p, r, words=w)                       # zero, one, zero: that is what a cell loaded with zero reads. In part 1 it is a candidate —
        self.assertEqual((v1["verdict"], v1["finding"]["bits"]["follow"], v1["finding"]["irregular"]), ("PASS", 28161, []))   # whose, the chain asks
        self.assertEqual(s2_5_judge.places(v1["finding"]["follows"])[(0xB80, 100, 7)], (0, False))
        w = list(r.words)
        i = r.hb + (2 + 0 * len(p["reads"]) + 0) * T.REC + T.DATA + T.FRAME * 1 + 100   # the same place as loaded: it reads another there, and the same in both written states
        w[i] ^= 1 << 7
        v2 = judged(p, r, words=w)
        self.assertEqual((v2["verdict"], v2["finding"]["irregular"]), ("FAIL", [{"far": "0x00000b80", "word": 100, "bit": 7, "readings": "100"}]))
        self.assertTrue(any("1 bit(s) changed and follow no cell of the memories" in x for x in v2["problems"]))

    def test_a_memory_that_does_not_hold_stops_the_run_and_fails_it(self) -> None:
        for fault, stop, state in (("bstuck", 10, 1), ("bmiss", 10, 1), ("bdisturb@4", 11, 0)):
            with self.subTest(fault):
                p, r = twin(fault=fault)
                v = judged(p, r)
                self.assertEqual((r.status & 0xFFF, v["verdict"]), (0xA00 | stop, "FAIL"), hex(r.status))
                self.assertEqual(v["pl"]["passes_the_sites_held_through"], state)
                self.assertTrue(any("the run did not complete" in x for x in v["problems"]), v["problems"])
                self.assertEqual(v["finding"]["follows"], [], "and nothing is said of what its bits follow")

    def test_the_clock_and_the_count(self) -> None:
        p, r = twin(fault="countstuck")
        v = judged(p, r)
        self.assertTrue(any("the design's clock did not go on" in x for x in v["problems"]), v["problems"])
        p, r = twin(fault="plcount")
        self.assertEqual((r.status & 0xFFF, judged(p, r)["verdict"]), (0xA0B, "FAIL"), "the list holds the count to the writes made, and the prober stops there")

    def test_what_the_sites_hold_is_worked_out_from_the_log_and_not_from_the_plan(self) -> None:
        """Lists that are not the plan's, made by the prober as they stand: the judge reads what they did."""
        site, addr, data, check, count, writes = (REG[n] for n in ("SITE", "RAM_ADDR", "RAM_DATA", "CHECK", "COUNT", "WRITES"))
        p = st.plan("find", 1, KNOWN, KNOWN["census"])
        # the plan's list with every reading the prober would stop at taken as a reading it only records: what the design answered is then in the log
        e = [(st.A_READ, x[1], 0) if x[0] == st.A_EXPECT and x[1] in (check, writes) else x for x in p["entries"]]
        first = next(i for i, x in enumerate(e) if x[:2] == (st.A_WRITE, data))
        frames = next(i for i, x in enumerate(e) if x[0] == st.A_MARK)
        back = next(i for i in range(frames, len(e)) if e[i] == (st.A_WRITE, addr, 9))      # the reading at address 9 after the first state's frames
        for name, change, fault, says in (
                ("a write to one site alone", lambda e: e[:first] + [(st.A_WRITE, site, 3), e[first], (st.A_WRITE, site, 0x100)] + e[first + 1:], "",
                 "a write with the site register at 0x3: not to every site"),
                ("the site register left at one site", lambda e: e[:2] + [(st.A_WRITE, site, 0x100 | 5), (st.A_WRITE, site, 5)] + [x for x in e[2:] if x[:2] != (st.A_EXPECT, site)], "",
                 "a write with the site register at 0x5"),
                ("a site read alone", lambda e: e[:2] + [(st.A_READ, data, 0)] + e[2:], "", "a reading of one site alone"),
                ("no reading of the site register at a state's end", lambda e: e[:2] + [x for x in e[2:] if x[:2] != (st.A_EXPECT, site)], "",
                 "the site register was not read as naming every site"),
                ("an address not read back after the frames", lambda e: e[:back] + e[back + 2:], "",
                 "state 0: the reading over all sites was not made at every address before the frames and after them"),
                ("a cell that does not take what was written", lambda e: e, "bstuck", "at address 5 the reading over all sites is 0x4bf; by the log the sites hold what gives 0x0ff"),
                ("a site the write to every site does not reach", lambda e: e, "bmiss", "by the log the sites hold what gives 0x0ff"),
                ("a cell changed while the frames were read", lambda e: e, "bdisturb@4", "at address 9 the reading over all sites is"),
                ("a count that is not the writes made", lambda e: e, "plcount", "state 0: the design counted 1 write(s); the log has 0"),
                ("a write after the frames and before the state's end", lambda e: e[:back] + [(st.A_WRITE, data, 0)] + e[back:], "",
                 "a write after the frames of state 0 were read and before its end")):
            with self.subTest(name):
                made = change(e)
                r = T.Run(states=p["states"], reads=p["reads"], entries=made, w19=p["may_write"], w26=ID, cells=[], design_b=(WORDS, b_map()), fault=fault)
                v = s2_5_judge.judge(r.words, KNOWN, __import__("s2_3_judge").planned_words(r.params, p["reads"], made, DESIGN))
                self.assertEqual((r.status, v["verdict"]), (1, "FAIL"), "the prober made the whole list; it is the judge that reads what the design answered")
                self.assertTrue(any(says in x for x in v["problems"]), v["problems"])

    def test_a_site_register_that_does_not_read_as_written_and_a_word_of_what_may_be_written_that_is_not_the_plan_s(self) -> None:
        p = st.plan("find", 1, KNOWN, KNOWN["census"])
        made = p["entries"][:2] + [(st.A_READ, REG["SITE"], 0)] + p["entries"][2:]      # the site register read once more, its reading only recorded
        r = T.Run(states=p["states"], reads=p["reads"], entries=made, w19=p["may_write"], w26=ID, cells=[], design_b=(WORDS, b_map()))
        plan = __import__("s2_3_judge").planned_words(r.params, p["reads"], made, DESIGN)
        self.assertFalse(any("the site register read" in x for x in s2_5_judge.judge(r.words, KNOWN, plan)["problems"]))
        w = list(r.words)
        at = 64 + T.FIXED + 2 * 3                         # the log's fourth access: the identification, the write, the reading held, this reading
        self.assertEqual((w[at] & ~3, w[at + 1]), (REG["SITE"], 0x100))
        w[at + 1] = 0x105
        v = s2_5_judge.judge(w, KNOWN, plan)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("PL access 3: the site register read 0x105; by the log it was last written 0x100", v["problems"])
        # a run that was allowed to write more registers than its lists write: the prober makes it, and the judge says the word is not the plan's
        r = T.Run(states=p["states"], reads=p["reads"], entries=p["entries"], w19=p["may_write"] | 1 << 0x14, w26=ID, cells=[], design_b=(WORDS, b_map()))
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"]), (1, "FAIL"))
        self.assertIn("the run's word of what it may write is 0x00111010; the plan's lists write 0x00011010", v["problems"])

    def test_which_run_it_is_and_the_plan_it_is_held_to(self) -> None:
        p, r, v = clean()
        other = dict(KNOWN, reads_a_run=20)                # the made-up device in other shares: these reads are no share of it
        v2 = judged(p, r, other)
        self.assertEqual(v2["verdict"], "FAIL")
        self.assertTrue(any("the list of reads is no share" in x for x in v2["problems"]), v2["problems"])
        self.assertIn("the census was not given: the lists cannot be held to the plan of the run", judged(p, r, {k: x for k, x in KNOWN.items() if k != "census"})["problems"])
        none = judged(p, r, {"census": KNOWN["census"]})
        self.assertTrue(any("the design's registers and what it loads into its memories were not given" in x for x in none["problems"]), none["problems"])
        broken = copy.deepcopy(KNOWN); del broken["registers"]["CHECK"]
        self.assertTrue(any("the design's record is not one of a design with RAM at sites behind these registers" in x for x in judged(p, r, broken)["problems"]))
        # a run whose states are no run's: the code run cut to its first six states
        cand = dict(KNOWN, candidates={"frames_with_candidates": {f"{M.GROUPS[0]:#010x}": 0}})
        pc = st.plan("code", None, cand, cand["census"], cand["candidates"])
        states = pc["states"][:6]
        made = st.accesses(states, DESIGN)
        r6 = T.Run(states=states, reads=pc["reads"], entries=made, w19=pc["may_write"], w26=ID, cells=[], design_b=(WORDS, b_map()))
        v6 = s2_5_judge.judge(r6.words, cand, __import__("s2_3_judge").planned_words(r6.params, pc["reads"], made, DESIGN))
        self.assertTrue(any("are not those of a run of part 1, of the code run or of a run of the singles" in x for x in v6["problems"]), v6["problems"])
        self.assertEqual(v6["finding"]["follows"], [], "and nothing is said of what its bits follow")

    def test_the_layouts(self) -> None:
        self.assertEqual([s2_5_judge.layout_hdr(k) for k in ("find", "code", "singles")], [2158, 13286, 9830])
        self.assertEqual(s2_5_judge.SETS, {"find": "s2_5f", "code": "s2_5c", "singles": "s2_5s"})
        for stage in s2_5_judge.SETS.values():
            self.assertEqual(s1a_run.STAGES[stage]["judge"].HDR, s2_5_judge.layout_hdr(s1a_run.STAGES[stage]["judge"].KIND))


class TheSets(unittest.TestCase):
    def setUp(self) -> None:
        H9.prepared()
        self.base = json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text())

    def test_the_set_is_the_set_of_s2_3_with_the_other_design(self) -> None:
        other = json.loads(s1a_run.STAGES["s2_3c"]["expected"].read_text())
        differ = [i for i, (a, b) in enumerate(zip(self.base["params"], other["params"])) if a != b]
        self.assertEqual((differ, self.base["params"][26], self.base["image_sha256"]), ([26], "53324231", other["image_sha256"]))
        self.assertEqual(self.base["image_sha256"], "8bf3799cd5a29b92d9196dfd432e8e4db13e977000bc67503c69cba819e62a8b", "the image of section 32: no new one")
        built = json.loads((ROOT / "pl" / "s2b" / "build.json").read_text())["bitstream"]
        self.assertEqual(self.base["pl_design"], {"sha256": built["sha256"], "bytes": built["bytes"], "file": "build/pl/s2b.bit", "card_name": "s2b.bit",
                                                  "note": "the probe design s2b (pl/s2b), built here and loaded as an opaque file"})
        for stage in ("s2_5c", "s2_5s"):
            b = json.loads(s1a_run.STAGES[stage]["expected"].read_text())
            self.assertEqual((b["params"], b["image_sha256"], b["pl_design"]), (self.base["params"], self.base["image_sha256"], self.base["pl_design"]))
        exp = s1a_run.with_plan("s2_5f", self.base, 3)
        par = [int(w, 16) for w in exp["params"]]
        self.assertEqual((par[2], par[7], par[16], par[18], par[19]), (9, 3, 176, 1044, 0x00011010))
        self.assertEqual(par[19] & ~0x01111010, 0, "inside what the image lets a run write")
        self.assertEqual(exp["plan"], {"kind": "find", "share": 3, "states": 3, "entries": 1044, "accesses": 1039, "reads": 176, "frames": 524,
                                       "first": "0x00001680", "last": "0x004001a3"})
        self.assertEqual((exp["records"], exp["result_words"]), (532, 2158 + 532 * 480))
        self.assertEqual(exp["console"], ["SM9 start", "SM9 end status=00000001 records=00000214 anomalies=00000000 words=0003edee"])

    def test_what_is_refused(self) -> None:
        self.assertRaisesRegex(ValueError, r"one share of the census's addresses \(--share\)", s1a_run.with_plan, "s2_5f", self.base, None)
        self.assertRaisesRegex(ValueError, "which", s1a_run.with_plan, "s2_5f", self.base, 8)
        cand = dict(KNOWN, candidates={"frames_with_candidates": {f"{M.GROUPS[0]:#010x}": 0}})
        self.assertRaisesRegex(ValueError, r"a run of the singles is one of sixteen \(--share\)", s1a_run.with_plan, "s2_5s", self.base, None, cand)
        self.assertRaisesRegex(ValueError, "the code run is one run", s1a_run.with_plan, "s2_5c", self.base, 0, cand)
        self.assertRaisesRegex(ValueError, r"a run of the singles is one of two \(--share\)", s1a_run.with_plan, "s2_4s", self.base, None, cand)

    def test_what_the_run_script_gives_the_judge_of_the_set(self) -> None:
        known = s1a_run.known_for("s2_5f")
        self.assertEqual((known["name"], known["id"], known["ctl0_in_s2_2"], "candidates" in known, len(known["ram"]["sites"])), ("s2b", "0x53324231", "0x00000501", False, 110))
        self.assertEqual(len(st.shares(known["census"], known)), 8)

    def test_a_set_of_part_2_has_no_run_until_part_1_is_stored(self) -> None:
        kept = s1a_run.STAGES["s2_5c"]
        try:                                             # asked of the set with its files named where nothing is, whatever is stored by now
            for what in ("candidates", "chain_of_part_1"):
                there = dict(kept, candidates=s2_5_chain.PREDICTION, chain_of_part_1=s2_5_chain.PREDICTION)   # files that are there, whatever they hold
                s1a_run.STAGES["s2_5c"] = dict(there, **{what: ROOT / "evidence" / "none_such" / "x.json"})
                self.assertRaisesRegex(ValueError, r"s2_5c is run over what the part before it found, and that is not stored \(evidence/none_such/x.json\)",
                                       s1a_run.known_for, "s2_5c")
        finally:
            s1a_run.STAGES["s2_5c"] = kept
        if st.CANDIDATES.is_file():
            self.skipTest("part 1 is stored")
        for stage in ("s2_5c", "s2_5s"):
            self.assertRaisesRegex(ValueError, f"{stage} is run over what the part before it found, and that is not stored \\(evidence/s2_5_17A6/candidates.json\\)",
                                   s1a_run.known_for, stage)
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_5c", "--dry-run"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (2, ""))
        self.assertIn("REFUSED: s2_5c is run over what the part before it found, and that is not stored", r.stdout)

    def test_the_dry_run_of_the_run_script(self) -> None:
        run = lambda *a: subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_5f", *a, "--dry-run"], capture_output=True, text=True)  # noqa: E731
        r = run("--share", "6")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stage s2_5f, part 1, share 6: 3 states, 1044 entries in the list of accesses, 172 reads a state, 0x00401100 .. 0x00401823", r.stdout)
        self.assertIn("fatload mmc 0:1 04000000 s2b.bit", r.stdout)
        self.assertRegex(r.stdout, r"md\.l 40000000 1 .*reads 53324231")
        self.assertIn("Dry run: nothing was sent.", r.stdout)
        self.assertEqual((run().returncode, run("--share", "8").returncode), (2, 2))


class TheSearch(unittest.TestCase):
    def frames(self, **kw) -> dict:
        if not kw:
            return s2_5_find.frames_in_state(clean()[1].words, 0)
        p, r = twin(**kw)
        return s2_5_find.frames_in_state(r.words, 0)

    def test_every_memory_s_word_is_found_once_where_it_lies(self) -> None:
        looked, hits = s2_5_find.search(self.frames(), RULE, LOADED)
        self.assertEqual((looked, len(hits)), (27 * 101 * 2, 440), "every four frames next to each other of the 30, every word, both halves")
        self.assertEqual({(h["site"], h["memory"]) for h in hits}, {(s, k) for s in range(110) for k in range(4)})
        for h in hits[::37]:
            s, k = h["site"], h["memory"]
            low, word, half = M.GROUPS[s // 50], 2 * (s % 50) + M.POSITION[k][0], M.POSITION[k][1]
            self.assertEqual((h["frames"], h["word"], h["bits"], h["inverted"], h["loaded_word"]),
                             ([f"{low + f:#010x}" for f in range(4)], word, f"{half + 15} down to {half}", False, f"{LOADED[s][k]:#018x}"))
            self.assertEqual(s2_5_find.places_of(h, RULE), {M.at(s, k, a): a for a in range(64)})
        self.assertEqual(s2_5_find.chance(2 ** 40, 512), 2 ** 40 * 2 * 512 / 2 ** 64, "each place holds one of 2^64 contents, and each word hits as it is and inverted")

    def test_a_memory_shown_inverted_is_found_as_inverted_and_one_laid_out_otherwise_is_not_found(self) -> None:
        inv = {(20, 1, a) for a in range(64)}
        looked, hits = s2_5_find.search(self.frames(cells=b_map(moved={**M.swap(30, 2), **M.swap(31, 0, alike=True)}, inverted=inv)), RULE, LOADED)
        by = {(h["site"], h["memory"]): h for h in hits}        # two cells of a memory in each other's places: by the six moves it holds another word —
        self.assertEqual((len(hits), by[(20, 1)]["inverted"], (30, 2) in by, sum(h["inverted"] for h in hits)), (439, True, False, 1))
        self.assertIn((31, 0), by, "unless the two were loaded alike: then the word is there, and only part 2 can say that the places are not the cells")

    def test_what_is_not_searched(self) -> None:
        self.assertRaisesRegex(ValueError, "does not give each of 64 addresses a place of its own", s2_5_find.search, self.frames(), RULE[:-1] + [RULE[0]], LOADED)
        self.assertEqual(s2_5_find.search({0xB84: (0,) * 101, 0xB85: (0,) * 101, 0xB86: (0,) * 101}, RULE, LOADED), (0, []), "three frames are no group of four")
        p, r, v = clean()
        w = list(r.words)
        i = r.hb + (2 + 1) * T.REC                        # the second read of the first state: said to be at the address of the first
        w[i] = w[r.hb + 2 * T.REC]
        self.assertRaisesRegex(ValueError, "is read twice in one state", s2_5_find.frames_in_state, w, 0)


def made_up_prediction(form: int = 49, moved: dict | None = None) -> dict:
    """A prediction of the form s2_5_predict writes, saying of the made-up device what tests/s2_5_made_up.py does."""
    sites = []
    for s, site in enumerate(DESIGN["ram"]["sites"]):
        low = (moved or {}).get(s, M.GROUPS[s // 50])
        sites.append({"site": s, "name": site["name"], "row_of_its_half": s % 50, "frames": [f"{low + f:#010x}" for f in range(4)],
                      "memories": [{"memory": k, "position": ("D6LUT", "A6LUT", "B6LUT", "C6LUT")[k], "bits": f"{M.POSITION[k][1] + 15} down to {M.POSITION[k][1]}"}
                                   for k in range(4)]})
    return {"rules": {"the_word": {"one_word_more_after_row": [20, 49], "named_first": form}}, "sites": sites,
            "the_six_moves": [{"address": a, "frame_above_the_lowest": f, "bit_of_the_half_word": b} for a, (f, b) in enumerate(RULE)]}


class TheChain(unittest.TestCase):
    """The chain over the made-up device: three shares."""

    def setUp(self) -> None:
        H9.prepared()
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain5_")) / "chain"
        self.base = json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text())
        self.calls: list[int] = []

    def runner(self, per_run: dict | None = None, **kw):
        def run(share: int, out: Path) -> None:
            self.calls.append(share)
            run5("s2_5f", share, kw.get("known", KNOWN), out=out, **{k: v for k, v in kw.items() if k != "known"}, **(per_run or {}).get(share, {}))
        return run

    def drive(self, known: dict = KNOWN, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")     # the directories here are in no repository: said to be committed, unless a test asks
        return s2_5_chain.drive(self.root, self.base, known, kw.pop("runner", self.runner()), **kw)

    def test_three_runs_the_candidates_and_whose_memory_each_is(self) -> None:
        said: list[str] = []
        known = dict(KNOWN, prediction=made_up_prediction())
        a = self.drive(known, say=said.append)
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", [0, 1, 2], ["go on", "go on", "complete"]))
        c = a["closing"]
        self.assertEqual((c["problems"], c["addresses_read"], c["sites"], c["memories_in_the_design"], c["cells_in_the_design"], c["candidates"], c["candidates_inverted"]),
                         ([], 55, 110, 440, 28160, 28160, 0))
        self.assertEqual((c["memories_found_once"], c["memories_not_found"], c["memories_found_more_than_once"], c["candidates_of_no_memory_found"],
                          c["memories_found_whose_places_are_not_all_candidates"]), (440, [], [], 0, []))
        self.assertEqual(c["places_looked_at"], (4 + 1 + 3 + 27 + 2) * 202, "every group of four frames of every column that has four")
        self.assertTrue(c["outcome"].startswith("1: as many bits follow as the design has cells, each memory's word is found once"), c["outcome"])
        self.assertIn("under the form with the one word more after row 49", c["outcome"])
        self.assertEqual((c["prediction"]["memories_named"], c["prediction"]["forms"], c["prediction"]["forms_under_which_every_memory_is_where_it_said"],
                          c["prediction"]["not_where_it_said"]), (440, {"20": 4 * (21 + 21 + 10), "49": 440}, [49], []))   # under the other form: the rows up to 20
        self.assertEqual((c["ctl0"], c["ctl0_in_s2_2"], c["bit_5"]), ([CTL0], CTL0, {}))
        self.assertEqual((sum(c["frames_with_candidates"].values()), set(c["frames_with_candidates"])), (28160, {f"{g + f:#010x}" for g in M.GROUPS for f in range(4)}))
        doc = json.loads((self.root / "candidates.json").read_text())
        self.assertEqual((doc["schema"], doc["label"], doc["candidates"], doc["design"], doc["sites"], len(doc["memories"]), doc["memories_not_found"]),
                         ("s2_5_candidates", "closed-book", 28160, "s2b", 110, 440, []))
        self.assertEqual(doc["memories"][5], {"site": 1, "memory": 1, "loaded_word": f"{LOADED[1][1]:#018x}", "frames": [f"{0xB84 + f:#010x}" for f in range(4)], "word": 2,
                                              "bits": "15 down to 0", "inverted": False, "run": "run01", "name": "SLICE_X16Y1"})
        self.assertEqual([(m["address"], m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in doc["the_six_moves"]], [(a, f, b) for a, (f, b) in enumerate(RULE)])
        self.assertTrue(set(s2_5_judge.places(doc["places"])) == set(M.where(b_map())), "the places written out are the places of the cells")
        self.assertEqual({x["run"] for x in doc["places"]}, {"run01"})
        self.assertEqual([(r["dir"], r["share"]) for r in doc["runs"]], [("run00", 0), ("run01", 1), ("run02", 2)])
        chain = json.loads((self.root / "chain.json").read_text())
        self.assertEqual(chain, json.loads(json.dumps(s2_5_chain.brief(a))))
        self.assertEqual((chain["runs"][1]["candidates"], chain["runs"][1]["memories"], "found" in chain["closing"], "memories" in chain["closing"]), (28160, 440, False, False))
        self.assertTrue(said[1].startswith("run01: share 1, 30 addresses, 28160 bit(s) follow, 0 inverted, 0 irregular, 440 memory word(s) found — go on"), said[1])
        self.assertTrue((self.root / "prober.bin").read_bytes() == s1a_run.IMAGE.read_bytes())
        self.assertEqual(s2_5_chain.assess(self.root, self.base, known)["state"], "complete", "and it stands when looked at again")
        self.assertEqual(st.candidate_reads(KNOWN["census"], doc), [(0xB83, 3), (0xB86, 3), (0xB89, 3), (0xB8C, 3), (0xB8F, 3)], "what part 2 would read")

    def test_looking_at_a_chain_writes_nothing_and_runs_nothing(self) -> None:
        a = s2_5_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["next_run"], a["next_share"], a["runs"], a["shares"], self.root.exists()), ("go on", 0, 0, [], 3, False))

    def test_no_second_run_before_the_first_is_committed(self) -> None:
        a = self.drive(committed=s2_5_chain.committed)   # the real question, of a directory that is in no repository
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no second run before the first is committed: run00", a["held"])
        self.assertNotIn("blocked", a)
        a = self.drive(max_new=1)
        self.assertEqual((self.calls, a["state"], len(a["runs"])), ([0, 1], "go on", 2), "one run more, and no further")

    def test_memories_that_are_not_where_the_prediction_said_are_outcome_2_and_named(self) -> None:
        a = self.drive(dict(KNOWN, prediction=made_up_prediction(moved={3: 0xB88, 104: 0xB90})))
        c = a["closing"]
        self.assertEqual((a["state"], c["outcome"][:2], c["prediction"]["forms"]["49"], c["prediction"]["best_form"], len(c["prediction"]["not_where_it_said"])),
                         ("complete", "2:", 432, 49, 8))
        self.assertTrue(c["prediction"]["says"].startswith("miss: under its best form (after row 49) 8 of 440 memories are not where it said"))
        self.assertEqual(c["prediction"]["not_where_it_said"][0], {"site": 3, "name": "SLICE_X16Y3", "memory": 0,
                                                                   "said": {"frames": [f"{0xB88 + f:#010x}" for f in range(4)], "word_under_the_form": 7, "bits": "31 down to 16"},
                                                                   "found": {"frames": [f"{0xB84 + f:#010x}" for f in range(4)], "word": 7, "bits": "31 down to 16", "inverted": False}})
        self.assertTrue((self.root / "candidates.json").is_file())

    def test_without_a_prediction_the_outcome_says_so(self) -> None:
        self.assertTrue(self.drive()["closing"]["outcome"].startswith("1 or 2: every memory's word is found once"))

    def test_a_memory_not_laid_out_by_the_six_moves_is_outcome_3_and_the_chain_is_complete(self) -> None:
        a = self.drive(runner=self.runner(cells=b_map(moved=M.swap(30, 2))))
        c = a["closing"]
        self.assertEqual((a["state"], c["candidates"], c["memories_found_once"], c["memories_not_found"], c["candidates_of_no_memory_found"]),
                         ("complete", 28160, 439, [{"site": 30, "name": "SLICE_X16Y30", "memory": 2}], 64))
        self.assertTrue(c["outcome"].startswith("3: 1 memory word(s) are not found; 28160 bit(s) follow for 28160 cells, 64 of them of no memory found"), c["outcome"])
        doc = json.loads((self.root / "candidates.json").read_text())
        self.assertEqual((len(doc["memories"]), doc["memories_not_found"], doc["candidates_of_no_memory_found"]), (439, [{"site": 30, "name": "SLICE_X16Y30", "memory": 2}], 64))

    def test_fewer_cells_that_show_and_cells_shown_inverted_are_outcome_4(self) -> None:
        a = self.drive(runner=self.runner(cells=b_map(sites=range(109), inverted={(7, 2, 9)})))
        c = a["closing"]
        self.assertEqual((a["state"], c["candidates"], c["candidates_inverted"], c["memories_found_once"], len(c["memories_not_found"])), ("complete", 109 * 256, 1, 435, 5))
        self.assertTrue(c["outcome"].startswith("3: 5 memory word(s) are not found"), c["outcome"])
        self.root = self.root.parent / "other"; self.calls = []
        every = {(7, 2, a) for a in range(64)}            # a whole memory shown inverted: found, as inverted, and its places are candidates that follow inverted
        a = self.drive(dict(KNOWN, prediction=made_up_prediction()), runner=self.runner(cells=b_map(inverted=every)))
        c = a["closing"]
        self.assertEqual(c["prediction"]["forms"]["49"], 439, "a memory found inverted is not where a prediction of memories shown as they are said")
        self.assertEqual((a["state"], c["candidates_inverted"], c["memories_found_once"], c["memories_found_inverted"], c["memories_found_whose_places_are_not_all_candidates"]),
                         ("complete", 64, 440, 1, []))
        self.assertTrue(c["outcome"].startswith("4: 28160 bit(s) follow (64 inverted) for 28160 cells; 0 of no memory found"), c["outcome"])

    def test_what_the_closing_asks_of_the_runs_together(self) -> None:
        a = self.drive()
        runs = a["runs"]
        clean = s2_5_chain.close(runs, KNOWN)
        self.assertEqual((clean["problems"], clean["outcome"][:6]), ([], "1 or 2"))

        def closed(change) -> dict:
            its = copy.deepcopy(runs); change(its)
            return s2_5_chain.close(its, KNOWN)

        def a_bit_less(r): r[1]["candidates"][0]["bits"].pop(); r[1]["candidates"][0]["as_loaded"].pop()
        c = closed(a_bit_less)                           # a memory whose loaded word is found, and one of its places did not follow the writes
        self.assertEqual((c["candidates"], c["memories_found_once"], len(c["memories_found_whose_places_are_not_all_candidates"]), c["outcome"][:2]), (28159, 440, 1, "4:"))
        self.assertEqual(c["memories_found_whose_places_are_not_all_candidates"][0]["places_that_are_no_such_candidate"], 1)

        def a_word_twice(r): r[1]["memories"].append(dict(r[1]["memories"][0], frames=[f"{0xB90 + f:#010x}" for f in range(4)]))
        c = closed(a_word_twice)
        first = runs[1]["memories"][0]
        self.assertEqual((c["memories_found_once"], c["memories_found_more_than_once"], c["outcome"][:2], c["candidates_of_no_memory_found"]),
                         (439, [{"site": first["site"], "name": "SLICE_X16Y0", "memory": first["memory"], "times": 2}], "3:", 64))

        def a_run_less(r): del r[2]
        self.assertEqual(closed(a_run_less)["problems"], ["the runs read 47 addresses; block type 0 has 55 in the census"])

        def a_run_twice(r): r[2]["candidates"] = r[1]["candidates"]
        self.assertEqual(closed(a_run_twice)["problems"], ["a place is a candidate in two runs: the shares are not apart"])

        def two_in_one_place(r): r[1]["memories"][1] = dict(r[1]["memories"][1], frames=r[1]["memories"][0]["frames"], word=r[1]["memories"][0]["word"], bits=r[1]["memories"][0]["bits"])
        self.assertIn("64 place(s) lie in two memories found: the words are not apart", closed(two_in_one_place)["problems"])

    def test_a_run_in_another_run_s_place_and_a_verdict_that_is_not_the_judge_s(self) -> None:
        self.drive()
        v = self.root / "run02" / "verdict.json"
        kept = v.read_text()
        v.write_text(kept.replace('"verdict": "PASS"', '"verdict": "pass"'))
        a = s2_5_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["why"]), ("halted", ["run02: the verdict stored beside the result is not what the judge says of the stored result"]))
        v.write_text(kept)
        (self.root / "run00").rename(self.root / "x"); (self.root / "run01").rename(self.root / "run00"); (self.root / "x").rename(self.root / "run01")
        a = s2_5_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual(a["state"], "halted")
        self.assertIn("run00: the run is find, share 1; the chain plans part 1, share 0 for it", a["why"])

    def test_nothing_that_follows_halts_the_chain_when_it_is_closed(self) -> None:
        a = self.drive(runner=self.runner(cells=[]))
        self.assertEqual((a["state"], len(a["runs"]), a["closing"]["candidates"]), ("halted", 3, 0))
        self.assertEqual(a["why"], ["5: nothing follows the states written to the memories"])
        self.assertFalse((self.root / "candidates.json").exists())

    def test_a_first_run_under_another_ctl0_halts_the_chain_and_so_does_a_later_one(self) -> None:
        a = self.drive(dict(KNOWN, ctl0_in_s2_2="0x00000d01"))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("CTL0 read 0x00000501 in the first run and 0x00000d01 in the runs of S2.2", a["why"][0])
        self.root = self.root.parent / "other"; self.calls = []
        a = self.drive(runner=self.runner(per_run={1: {"env": {"SM_CREG": "ctl0:00000d01"}}}))
        self.assertEqual((a["state"], self.calls), ("halted", [0, 1]))
        self.assertIn("run01: CTL0 read 0x00000d01 in this run and 0x00000501 in the first run", a["why"][0])
        self.root = self.root.parent / "third"; self.calls = []
        a = self.drive({k: v for k, v in KNOWN.items() if k != "ctl0_in_s2_2"})
        self.assertEqual((a["state"], self.calls), ("halted", [0]), "with no word of S2.2 to hold the first run to, it is not held to none")

    def test_a_run_that_fails_halts_the_chain_there_and_nothing_is_run_again(self) -> None:
        a = self.drive(runner=self.runner(per_run={1: {"fault": "bstuck"}}))
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("halted", [0, 1], ["go on", "halt"]))
        self.assertTrue(any("run01: the run script's verdict is FAIL" in w for w in a["why"]), a["why"])
        self.assertEqual((self.drive()["state"], self.calls), ("halted", [0, 1]), "driven again, it runs nothing")

    def test_a_stored_run_that_was_changed_is_not_relied_on(self) -> None:
        self.drive()
        raw = bytearray((self.root / "run01" / "result.bin").read_bytes()); raw[-5] ^= 1
        (self.root / "run01" / "result.bin").write_bytes(bytes(raw))
        a = s2_5_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["candidates_file"]), ("halted", "there"))
        self.assertIn("run01: the stored result is not the one whose checksum the board gave", a["why"][0])
        self.assertIn("the run directories after it were not looked at: ['run02']", a["why"][-1])
        said: list[str] = []
        self.drive(say=said.append)
        self.assertFalse((self.root / "candidates.json").exists())
        self.assertIn("candidates.json taken away: the chain is not complete as it is stored now", said)

    def test_without_the_six_moves_a_run_s_frames_are_not_searched_and_the_chain_halts(self) -> None:
        a = self.drive({k: v for k, v in KNOWN.items() if k != "rule"})
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("the frames as loaded could not be searched: the six moves of S2.3 were not given", a["why"][0])

    def test_what_the_chain_is_held_to_on_the_device(self) -> None:
        known = s2_5_chain.known_of_the_device()
        self.assertEqual((known["rule"], known["name"], known["ctl0_in_s2_2"], known["prediction"]["memories"]), (RULE, "s2b", CTL0, 440))
        self.assertEqual(s2_5_chain.STAGE, "s2_5f")
        a = s2_5_chain.assess(Path(scratch_dirs.mkdtemp(prefix="smnone_")) / "none", self.base, known)
        self.assertEqual((a["state"], a["shares"], a["next_share"]), ("go on", 8, 0))


class ARunOfTheDeviceSPlan(unittest.TestCase):
    """A rehearsal of storing: a run made with the plan of the device itself — a share of the real census — on the
    pretend board, taken again the way the audit of stored evidence takes every stored run."""

    def test_it_is_judged_again_as_it_was_judged(self) -> None:
        H9.prepared()
        known = s1a_run.known_for("s2_5f")
        rec, u, out = run5("s2_5f", 7, known=known, cells=[])     # the last share: 82 reads; the made-up frames of the pretend board read zero there
        self.assertEqual((rec["verdict"], rec["problems"], rec["plan"]["kind"], rec["plan"]["share"], rec["plan"]["reads"]), ("PASS", [], "find", 7, 82))
        self.assertIn("fatload mmc 0:1 04000000 s2b.bit", u.commands)
        self.assertEqual(u.blobs[0x04000000], (ROOT / "build" / "pl" / "s2b.bit").read_bytes())
        stored_rec = json.loads((out / "run.json").read_text())
        raw = (out / "result.bin").read_bytes()
        exp = json.loads(s1a_run.STAGES[stored_rec["stage"]]["expected"].read_text())
        self.assertIn(stored_rec["stage"], s1a_run.PLANS_AT_RUN_TIME)
        exp = s1a_run.with_plan(stored_rec["stage"], exp, (stored_rec.get("plan") or {}).get("share"))
        now = s1a_run.STAGES[stored_rec["stage"]]["judge"].judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), s1a_run.known_for(stored_rec["stage"]),
                                                              s1a_run.planned_words(exp))
        self.assertEqual(json.loads(json.dumps(now)), json.loads((out / "verdict.json").read_text()))
        self.assertEqual((now["verdict"], now["run"]["kind"], now["run"]["share"], now["finding"]["bits"]["follow"], len(raw)), ("PASS", "find", 7, 0, 4 * 122158))
        self.assertEqual(f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}", stored_rec["board_crc32"])
        import status_seen
        self.assertEqual(status_seen.seen(now)["bits"], [], "and the listing of status bits reads its verdict")
        cmd = lambda *a: subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_5_judge.py"), str(out / "result.bin"), *a], capture_output=True, text=True)  # noqa: E731
        r = cmd("find", "7")
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, json.loads((out / "verdict.json").read_text())), r.stderr)
        self.assertEqual(cmd("find", "6").returncode, 1, "judged against another share's plan it does not pass")
        for args in (("find",), ("find", "x"), ("find", "7", "8"), (), ("code", "0"), ("singles",), ("pairs",)):
            r = cmd(*args)
            self.assertEqual((r.returncode, r.stderr, "s2_5_judge.py <result.bin> find <share>" in r.stdout), (2, "", True), args)
        r = cmd("find", "8")
        self.assertEqual((r.returncode, r.stderr), (2, ""), r.stdout)
        self.assertIn("no plan for that run", r.stdout)
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_5f_judge.py"), str(out / "result.bin"), "7"], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["verdict"]), (0, "PASS"), r.stderr)

    def test_a_card_without_the_design_gets_it_by_ymodem(self) -> None:
        rec, u, out = run5("s2_5f", 0, card_is_empty=True)
        self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
        self.assertIn("loady 04000000", u.commands)

    def test_another_design_behind_the_registers_is_not_run(self) -> None:
        rec, u, out = run5("s2_5f", 0, pl_id=0x53324131)   # the first probe design answers
        self.assertEqual((rec["verdict"], bool(rec.get("went")), u.commands[-1]), ("FAIL", False, "md.l 40000000 1"))


if __name__ == "__main__":
    unittest.main()

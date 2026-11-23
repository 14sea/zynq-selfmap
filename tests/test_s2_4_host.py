#!/usr/bin/env python3
"""S2.4, part 1 (docs/s2_plan.md, sections 37 and 38): the judge of a run of the step, the set in the run script, and
the chain over the shares — on the twin and on the pretend board, over a made-up device. No board is touched.

The made-up device is the one of the stage-8 tests (test_prober_s2_2): 55 frames of block type 0 in six columns. Its
shift registers' outputs show where a test says: by default as the prediction of part 0 has the real ones — register k
a half word of word 40 or 41 in four frames next to each other, output a at the place the rule of S2.3 gives address
2 a + 1 — and, as the note beside the prediction has it, with the outputs 0 to 30 shown inverted as well, at the
place of address 2 a + 2. Nothing here says the device is so; the tests give the model other answers too."""
from __future__ import annotations

import hashlib, json, os, struct, subprocess, sys, unittest, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_2_shares  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_3_states as st9  # noqa: E402
import s2_4_chain  # noqa: E402
import s2_4_judge  # noqa: E402
import s2_4_predict  # noqa: E402
import s2_4_states as st  # noqa: E402
import test_prober_s2_2 as T8  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402
import test_s2_2_host as H8  # noqa: E402
import test_s2_3_host as H9  # noqa: E402

DESIGN = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
LOADED = st9.srl_words(DESIGN)
RULE = [(2 + (a & 1) - 2 * (a >> 3 & 1), 15 - ((a >> 1 & 1) + 2 * (a >> 2 & 1) + 4 * (a >> 4 & 1) + 8 * (a >> 5 & 1))) for a in range(64)]
LOW = 0xB90                                              # the lowest of the four frames the outputs show in: the 30-frame column of the made-up device
CTL0 = "0x00000501"
RAM_CELLS = T.ram_map()                                  # where the RAM's cells show in the made-up device (frames 0xa03 to 0xa05)


def place(k: int, address: int) -> tuple[int, int, int]:
    f, b = RULE[address]
    return LOW + f, 40 + k // 2, 16 * (k % 2) + b


def srl_map(inverted: bool = True, outputs: int = 32) -> list[tuple[int, int, int, int, int, int]]:
    """Where outputs of the shift registers show: (output, register, frame address, word, bit, inverted)."""
    out = [(a, k, *place(k, 2 * a + 1), 0) for k in range(4) for a in range(outputs)]
    if inverted:
        out += [(a, k, *place(k, 2 * a + 2), 1) for k in range(4) for a in range(min(outputs, 31))]
    return out


def where(cells) -> dict:
    return {(f"{far:#010x}", word, bit): (32 * k + a, bool(inv)) for a, k, far, word, bit, inv in cells}


def known_for(reads_a_run: int | None = 10, **more) -> dict:
    """What is known of the made-up device. With ten reads a run it has three shares: 7, 10 and 3 reads."""
    known = dict(DESIGN, census=T8.census(), ctl0_in_s2_2=CTL0, ram_places=H9.candidates_of(RAM_CELLS), **more)
    return known if reads_a_run is None else dict(known, reads_a_run=reads_a_run)


KNOWN = known_for()
SHARES = st.shares(KNOWN["census"], KNOWN)


def twin(kind: str = "find", share: int | None = 1, cells=None, known: dict | None = None, **over) -> tuple[dict, T.Run]:
    """One run of the step on the twin: the plan made as the host makes it, and what the prober did with it."""
    known = KNOWN if known is None else known
    p = st.plan(kind, share, known, known["census"], known.get("candidates"))
    return p, T.Run(states=p["states"], reads=p["reads"], entries=p["entries"], shifts=True, w19=p["may_write"],
                    srl_cells=srl_map() if cells is None else cells, **over)


def planned(p: dict, r: T.Run) -> list[int]:
    return s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN)


def judged(p: dict, r: T.Run, known: dict | None = None, words=None) -> dict:
    return s2_4_judge.judge(r.words if words is None else words, KNOWN if known is None else known, planned(p, r))


_memo: dict = {}


def once(name, make):
    if name not in _memo:
        _memo[name] = make()
    return _memo[name]


def clean(kind: str = "find", share: int | None = 1) -> tuple[dict, T.Run, dict]:
    def make():
        known = KNOWN if kind == "find" else dict(KNOWN, candidates={"frames_with_candidates": {f"{LOW + f:#010x}": 0 for f in range(4)}})
        p, r = twin(kind, share, known=known)
        return p, r, judged(p, r, known)
    return once(("clean", kind, share), make)


class TheJudge(unittest.TestCase):
    def test_a_run_of_part_1_passes_and_says_what_follows(self) -> None:
        p, r, v = clean()
        self.assertEqual((r.status, v["verdict"], v["problems"]), (1, "PASS", []))
        self.assertEqual(v["run"], {"kind": "find", "share": 1, "states": ["all zero", "all one", "all zero"]})
        f = v["finding"]
        self.assertEqual((f["states_read_whole"], f["frames"], f["bits"]["follow"], f["bits"]["follow_inverted"], f["bits"]["irregular"]), (3, 30, 128, 124, 0))
        self.assertEqual(f["bits"]["still"], 30 * 101 * 32 - 252)
        self.assertEqual({(x["far"], x["word"], x["bit"]): x["inverted"] for x in f["follows"]}, {k: inv for k, (_, inv) in where(srl_map()).items()})
        self.assertNotIn("cell", f["follows"][0], "in part 1 no cell is named: every output holds the same in a state")
        self.assertEqual((f["cells_not_told_apart"], f["cells_not_told_from_another_inverted"]), ([], []))
        pl = v["pl"]
        self.assertEqual((pl["code"], pl["passes_the_shift_registers_held_through"], pl["writes_counted"], pl["ram_readings_all_zero"], pl["id"]),
                         ("0x0", 3, {"ram": 0, "shifts": 96}, 128, "0x53324131"))
        self.assertEqual(pl["shift_registers_held"], [["0x00000000"] * 4, ["0xffffffff"] * 4, ["0x00000000"] * 4])
        self.assertEqual(v["registers"]["CTL0"]["value"], CTL0)

    def test_the_other_shares_read_no_candidate_and_pass(self) -> None:
        for share in (0, 2):
            p, r = twin("find", share)
            v = judged(p, r)
            self.assertEqual((v["verdict"], v["run"]["share"], v["finding"]["bits"]["follow"], v["finding"]["bits"]["follow_inverted"], v["finding"]["follows"]),
                             ("PASS", share, 0, 0, []), share)

    def test_the_code_run_and_the_singles_pass_and_name_every_cell(self) -> None:
        p, r, v = clean("code", None)
        self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], len(v["run"]["states"])), ("PASS", [], "code", 17))
        self.assertEqual({(x["far"], x["word"], x["bit"]): (x["cell"], x["inverted"]) for x in v["finding"]["follows"]}, where(srl_map()))
        self.assertEqual({(x["cell"], x["register"], x["output"]) for x in v["finding"]["follows"]}, {(32 * k + a, k, a) for k in range(4) for a in range(32)})
        self.assertEqual(v["pl"]["shift_registers_held"][0], v["pl"]["shift_registers_held"][-1], "as loaded, and the same shifted in again")
        self.assertEqual(v["pl"]["shift_registers_held"][0], ["0xa5c30f69", "0x0f1e2d3c", "0x13579bdf", "0xfedcba98"])
        for run in (0, 1):
            p, r, v = clean("singles", run)
            self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], v["run"]["share"]), ("PASS", [], "singles", run))
            cells = {x["cell"] for x in v["finding"]["follows"]}
            self.assertEqual(cells, set(range(64 * run, 64 * run + 64)))
            self.assertEqual({(x["far"], x["word"], x["bit"]): (x["cell"], x["inverted"]) for x in v["finding"]["follows"]},
                             {k: c for k, c in where(srl_map()).items() if c[0] in cells})

    def test_what_the_registers_hold_is_worked_out_from_the_log_and_every_reading_held_to_it(self) -> None:
        p, r, v = clean()
        log_at = 64 + T.FIXED
        shifts = [i for i in range(r.n_log) if r.words[log_at + 2 * i] == (0x40000018 | 1)]
        readings = [i for i in range(r.n_log) if r.words[log_at + 2 * i] == 0x40000018]
        self.assertEqual((len(shifts), len(readings)), (96, 6 * 32))
        # A log that is not the list fails by the stage's judge already. What is asked here is more: the list itself
        # is not believed. A list — and a log that follows it word for word — in which one shift brought another bit
        # than the readings after it show, or one reading is held to another value than the shifts give:
        entry = [i for i, (kind, addr, _) in enumerate(p["entries"]) if kind == st.A_WRITE and addr == 0x40000018][40]
        w, plan = list(r.words), planned(p, r)
        w[log_at + 2 * shifts[40] + 1] ^= 0x4; plan[32 + len(p["reads"]) + 2 * entry + 1] ^= 0x4
        bad = s2_4_judge.judge(w, KNOWN, plan)
        self.assertEqual(bad["verdict"], "FAIL")
        self.assertTrue(any("of the shift registers read 0xf; by the shifts of the log it holds 0xb" in x for x in bad["problems"]), bad["problems"][:3])
        entry = [i for i, (kind, addr, _) in enumerate(p["entries"]) if kind == st.A_EXPECT and addr == 0x40000018][70]
        w, plan = list(r.words), planned(p, r)
        w[log_at + 2 * readings[70] + 1] ^= 0x1; plan[32 + len(p["reads"]) + 2 * entry + 1] ^= 0x1
        bad = s2_4_judge.judge(w, KNOWN, plan)
        self.assertEqual(bad["verdict"], "FAIL")
        self.assertTrue(any("of the shift registers read 0xe; by the shifts of the log it holds 0xf" in x for x in bad["problems"]), bad["problems"][:3])
        # and the log alone, against the list: the stage's judge
        w = list(r.words); w[log_at + 2 * readings[70] + 1] ^= 0x1
        self.assertEqual(judged(p, r, words=w)["verdict"], "FAIL")

    def consistently(self, p: dict, r: T.Run, which, change) -> dict:
        """The run judged with one entry of its list and the log's word for it changed alike: a list that is not the
        plan's, followed by the prober word for word. `which`: the entry, by a test on (kind, address, value) and its
        number among those; `change`: what its value becomes."""
        test, nth = which
        entry = [i for i, e in enumerate(p["entries"]) if test(*e)][nth]
        access = 1 + sum(1 for e in p["entries"][:entry] if e[0] != st.A_MARK)          # the log's first access is the prober's own
        w, plan = list(r.words), planned(p, r)
        at = 64 + T.FIXED + 2 * access + 1
        self.assertEqual(w[at], p["entries"][entry][2], "the log has the entry's value there")
        w[at] = plan[32 + len(p["reads"]) + 2 * entry + 1] = change(w[at])
        return s2_4_judge.judge(w, KNOWN, plan)

    def test_what_else_of_the_design_s_side_is_held_whatever_the_list_says(self) -> None:
        p, r, v = clean()
        count = lambda kind, addr, value: kind == st.A_EXPECT and addr == 0x4000001C     # noqa: E731
        bad = self.consistently(p, r, (count, 1), lambda x: x + (1 << 16))
        self.assertTrue(any("state 1: the design counted 0 write(s) and 65 shift(s); the log has no write to the RAM and 64 shift(s)" in x for x in bad["problems"]), bad["problems"][:3])
        ram = lambda kind, addr, value: kind == st.A_EXPECT and addr == 0x40000010       # noqa: E731
        bad = self.consistently(p, r, (ram, 9), lambda x: 2)
        self.assertTrue(any("the RAM read 0x2 at address 9; it was never written and is loaded with zero" in x for x in bad["problems"]), bad["problems"][:3])
        self.assertEqual(bad["verdict"], "FAIL")

    def test_a_counter_that_stands_still_fails_the_run(self) -> None:
        p, r = twin(fault="countstuck")
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"]), (1, "FAIL"))
        self.assertTrue(any("the design's clock did not go on" in x for x in v["problems"]), v["problems"][:3])

    def test_a_list_that_shifts_after_the_frames_or_does_not_read_every_output_back(self) -> None:
        p = st.plan("find", 1, KNOWN, KNOWN["census"])
        e = list(p["entries"])
        end = e.index((st.A_MARK, 0, st.MARK_END))
        e.insert(end, (st.A_WRITE, 0x40000018, 0))                           # one shift more, after the frames of the first state and its readings
        r = T.Run(states=p["states"], reads=p["reads"], entries=e, shifts=True, w19=p["may_write"], srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], e, DESIGN))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("a shift after the frames of state 0 were read and before its end" in x for x in v["problems"]), v["problems"][:3])
        e = list(p["entries"])
        first = next(i for i, x in enumerate(e) if x[0] == st.A_EXPECT and x[1] == 0x40000018)
        del e[first + 20: first + 24]                                        # two outputs are not read back before the frames of the first state
        r = T.Run(states=p["states"], reads=p["reads"], entries=e, shifts=True, w19=p["may_write"], srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], e, DESIGN))
        self.assertEqual((r.status, v["verdict"]), (1, "FAIL"))
        self.assertTrue(any("state 0: the shift registers were not read at every address before the frames and after them" in x for x in v["problems"]), v["problems"][:3])

    def test_a_run_whose_word_allows_more_than_its_lists_write_or_that_reads_other_frames_than_planned(self) -> None:
        p = st.plan("find", 1, KNOWN, KNOWN["census"])
        r = T.Run(states=p["states"], reads=p["reads"], entries=p["entries"], shifts=True, w19=p["may_write"] | 1 << 0x04, srl_cells=srl_map())
        v = judged(p, r)
        self.assertEqual((r.status, v["verdict"]), (1, "FAIL"))
        self.assertEqual(v["problems"], ["the run's word of what it may write is 0x01101010; the plan's lists write 0x01101000"])
        known = dict(KNOWN, candidates={"frames_with_candidates": {f"{LOW + f:#010x}": 0 for f in range(4)}})
        pc = st.plan("code", None, known, known["census"], known["candidates"])
        fewer = st9.candidate_reads(known["census"], known["candidates"])
        r = T.Run(states=pc["states"], reads=fewer, entries=pc["entries"], shifts=True, w19=pc["may_write"], srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, known, s2_3_judge.planned_words(r.params, fewer, pc["entries"], DESIGN))
        self.assertEqual((r.status, v["verdict"], v["problems"]), (1, "FAIL", ["the list of reads is not the one the plan makes for this run"]))

    def test_ctl0_that_reads_otherwise_at_the_end_fails_the_run(self) -> None:
        p, r, v = clean()
        last = r.hb + (r.n_records - 2) * T.REC                              # the read of CTL0 after the last state
        w = list(r.words); w[last + T.FARBLK + 4] ^= 0x100
        bad = judged(p, r, words=w)
        self.assertEqual(bad["verdict"], "FAIL")
        self.assertTrue(any(x.startswith("CTL0 does not read the same before and after") for x in bad["problems"]), bad["problems"][:3])

    def test_states_under_which_a_cell_inverted_would_pass_for_another_are_said_to_be_so(self) -> None:
        """The code run without its all-zero state (what was first proposed): over such states 72 of the 128 cells read
        as another cell inverted would — which ones depends on the words the registers are loaded with. The judge says
        so of any run whose states leave that open, and fails it."""
        keep = st.code_run
        try:
            st.code_run = lambda loaded: [x for x in keep(loaded) if x["name"] != "all zero"]
            known = dict(KNOWN, candidates={"frames_with_candidates": {f"{LOW + f:#010x}": 0 for f in range(4)}})
            p, r = twin("code", None, known=known)
            v = judged(p, r, known)
        finally:
            st.code_run = keep
        self.assertEqual((r.status, v["verdict"], v["run"]["kind"], len(v["run"]["states"])), (1, "FAIL", "code", 16))
        self.assertEqual(len(v["finding"]["cells_not_told_from_another_inverted"]), 72)
        self.assertEqual(v["problems"], ["the states do not tell 72 cell(s) from another cell shown inverted"])

    def test_shift_registers_that_do_not_hold_after_the_frames_stop_the_run_and_fail_it(self) -> None:
        p, r = twin(fault="srlmoves")
        v = judged(p, r)
        self.assertEqual((r.status >> 8, v["verdict"]), (0xA, "FAIL"))
        self.assertEqual(v["finding"]["follows"], [], "nothing is found by a run that stopped")

    def test_a_bit_that_moves_and_does_not_follow_fails_the_run(self) -> None:
        p, r, v = clean()
        rec0 = r.hb + (2 + 0 * len(p["reads"]) + 1) * T.REC                 # the second read of the list in the first state
        w = list(r.words); w[rec0 + T.DATA + T.FRAME + 5] ^= 0x100
        bad = judged(p, r, words=w)
        self.assertEqual((bad["verdict"], bad["finding"]["bits"]["irregular"], [x["readings"] for x in bad["finding"]["irregular"]]), ("FAIL", 1, ["100"]))

    def test_a_list_that_writes_the_ram_or_leaves_it_unread_is_no_run_of_the_step(self) -> None:
        p = st.plan("find", 1, KNOWN, KNOWN["census"])
        e = list(p["entries"])
        at = next(i for i, x in enumerate(e) if x == (st.A_EXPECT, 0x40000010, 0))
        e[at] = (st.A_WRITE, 0x40000010, 0)
        r = T.Run(states=p["states"], reads=p["reads"], entries=e, shifts=True, w19=p["may_write"] | 1 << 0x10, srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], e, DESIGN))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any("a write to the RAM" in x for x in v["problems"]), v["problems"][:3])
        e = [x for x in p["entries"] if x[1] not in (0x4000000C, 0x40000010)]
        r = T.Run(states=p["states"], reads=p["reads"], entries=e, shifts=True, w19=p["may_write"], srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], e, DESIGN))
        self.assertTrue(any("the RAM was not read at every address before the first" in x for x in v["problems"]), v["problems"][:4])
        self.assertTrue(any("the RAM was not read at every address after the last" in x for x in v["problems"]), v["problems"][:4])
        self.assertTrue(any("the list of accesses is not the one the plan makes" in x for x in v["problems"]), v["problems"][:4])

    def test_states_that_are_no_run_of_the_step_and_reads_that_are_no_share(self) -> None:
        states = st.find_run()[:2]
        e = st.accesses(states, DESIGN)
        r = T.Run(states=states, reads=SHARES[1], entries=e, shifts=True, w19=st9.may_write(e, DESIGN), srl_cells=srl_map())
        v = s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, SHARES[1], e, DESIGN))
        self.assertEqual((r.status, v["verdict"], v["run"]["kind"]), (1, "FAIL", None))
        self.assertTrue(any("are not those of a run of part 1" in x for x in v["problems"]))
        p, r, _ = clean()
        v = judged(p, r, known=known_for(reads_a_run=None))
        self.assertTrue(any("no share of the census's addresses" in x for x in v["problems"]), v["problems"])
        v = judged(p, r, known={k: x for k, x in KNOWN.items() if k != "census"})
        self.assertIn("the census was not given: the lists cannot be held to the plan of the run", v["problems"])

    def test_a_run_of_s2_3_is_judged_as_it_always_was(self) -> None:
        """The seam: without the design's side of another step, the stage's judge is the judge of S2.3 — and a shift
        in a run of S2.3 is still a fault there."""
        p, r, v = H9.clean()
        self.assertEqual((v["verdict"], s2_3_judge.judge(r.words, H9.KNOWN, H9.planned(p, r), rest=None)), ("PASS", v))
        p4, r4, _ = clean()
        as_s2_3 = s2_3_judge.judge(r4.words, KNOWN, planned(p4, r4))
        self.assertEqual(sum(1 for x in as_s2_3["problems"] if "a write to the shift registers' data — a shift" in x), 96)


class WithAPlan(unittest.TestCase):
    def setUp(self) -> None:
        H9.prepared()
        self.base = json.loads(s1a_run.STAGES["s2_4f"]["expected"].read_text())

    def test_the_set_is_the_set_of_s2_3_and_the_plan_fills_it_in(self) -> None:
        other = json.loads(s1a_run.STAGES["s2_3c"]["expected"].read_text())
        self.assertEqual((self.base["params"], self.base["image_sha256"], self.base["pl_design"]), (other["params"], other["image_sha256"], other["pl_design"]))
        self.assertEqual(self.base["image_sha256"], "8bf3799cd5a29b92d9196dfd432e8e4db13e977000bc67503c69cba819e62a8b", "the image of section 32: no new one")
        exp = s1a_run.with_plan("s2_4f", self.base, 3)
        par = [int(w, 16) for w in exp["params"]]
        self.assertEqual((par[2], par[7], par[16], par[18], par[19]), (9, 3, 176, 751, 0x01101000))
        self.assertEqual(exp["plan"], {"kind": "find", "share": 3, "states": 3, "entries": 751, "accesses": 746, "reads": 176, "frames": 524,
                                       "first": "0x00001680", "last": "0x004001a3"})
        self.assertEqual((exp["records"], exp["result_words"]), (532, s2_4_judge.layout_hdr("find") + 532 * 480))
        self.assertEqual((exp["result_words"], s2_4_judge.layout_hdr("find")), (256932, 1572))
        self.assertEqual(exp["console"], ["SM9 start", "SM9 end status=00000001 records=00000214 anomalies=00000000 words=0003eba4"])
        self.assertEqual(len(s1a_run.planned_words(exp)), 32 + 176 + 2 * 751)
        self.assertEqual([s1a_run.with_plan("s2_4f", self.base, s)["plan"]["frames"] for s in range(8)], [516, 516, 520, 524, 508, 524, 512, 244])
        self.assertEqual(sum(s1a_run.with_plan("s2_4f", self.base, s)["plan"]["frames"] for s in range(8)), 3864)

    def test_what_is_refused(self) -> None:
        self.assertRaisesRegex(ValueError, r"one share of the census's addresses \(--share\)", s1a_run.with_plan, "s2_4f", self.base, None)
        self.assertRaisesRegex(ValueError, "which", s1a_run.with_plan, "s2_4f", self.base, 8)

    def test_what_the_run_script_gives_the_judge_of_the_set(self) -> None:
        known = s1a_run.known_for("s2_4f")
        self.assertEqual((known["name"], known["ctl0_in_s2_2"], len(known["ram_places"]["places"]), "candidates" in known), ("s2a", "0x00000501", 256, False))
        self.assertEqual(len(st.shares(known["census"], known)), 8)

    def test_the_dry_run_of_the_run_script(self) -> None:
        run = lambda *a: subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s2_4f", *a, "--dry-run"], capture_output=True, text=True)  # noqa: E731
        r = run("--share", "6")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stage s2_4f, part 1, share 6: 3 states, 751 entries in the list of accesses, 172 reads a state, 0x00401100 .. 0x00401823", r.stdout)
        self.assertIn("Dry run: nothing was sent.", r.stdout)
        self.assertEqual((run().returncode, run("--share", "8").returncode), (2, 2))


class ARunOfTheDeviceSPlan(unittest.TestCase):
    """A rehearsal of storing (section 36 said what was missed before S2.3 went on the board): a run made with the plan
    of the device itself — a share of the real census — on the pretend board, taken again the way the audit of stored
    evidence takes every stored run (tests/test_evidence_audit.py): the set kept beside it, the plan made again from
    what the record says, the result judged from its raw words. What comes out must be what was stored."""

    def test_it_is_judged_again_as_it_was_judged(self) -> None:
        H9.prepared()
        known = s1a_run.known_for("s2_4f")
        rec, u, out = run4(7, known=known, cells=[])     # the last share: 82 reads; the made-up frames of the pretend board read zero there
        self.assertEqual((rec["verdict"], rec["problems"], rec["plan"]["kind"], rec["plan"]["share"], rec["plan"]["reads"]), ("PASS", [], "find", 7, 82))
        stored_rec = json.loads((out / "run.json").read_text())
        raw = (out / "result.bin").read_bytes()
        exp = json.loads(s1a_run.STAGES[stored_rec["stage"]]["expected"].read_text())
        self.assertIn(stored_rec["stage"], s1a_run.PLANS_AT_RUN_TIME)
        exp = s1a_run.with_plan(stored_rec["stage"], exp, (stored_rec.get("plan") or {}).get("share"))
        now = s1a_run.STAGES[stored_rec["stage"]]["judge"].judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), s1a_run.known_for(stored_rec["stage"]),
                                                              s1a_run.planned_words(exp))
        self.assertEqual(json.loads(json.dumps(now)), json.loads((out / "verdict.json").read_text()))
        self.assertEqual((now["verdict"], now["run"]["kind"], now["run"]["share"], now["finding"]["bits"]["follow"]), ("PASS", "find", 7, 0))
        self.assertEqual(f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}", stored_rec["board_crc32"])
        import status_seen
        self.assertEqual(status_seen.seen(now)["bits"], [], "and the listing of status bits reads its verdict")


def run4(share: int, known: dict | None = None, out: Path | None = None, cells=None, fault: str = "", env: dict | None = None, **quirks):
    """The run of a share through the run script, on the pretend board, over the made-up device."""
    H9.prepared()
    known = KNOWN if known is None else known
    exp = s1a_run.with_plan("s2_4f", json.loads(s1a_run.STAGES["s2_4f"]["expected"].read_text()), share, known)
    reads = [(int(w, 16) & 0x0FFFFFFF, int(w, 16) >> 28) for w in exp["list"]]
    out = Path(scratch_dirs.mkdtemp(prefix="smout4_")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "list.bin").write_bytes(s1a_run.list_bytes(exp))
    (out / "acc.bin").write_bytes(s1a_run.acc_bytes(exp))
    exp = dict(exp, list_file=str(out / "list.bin"), acc_file=str(out / "acc.bin"))
    pl = s1a_run.pl_file(exp).read_bytes()
    srl = Path(scratch_dirs.mkdtemp(prefix="smsrl_")) / "srlmap.txt"
    srl.write_text("".join("%d %d %x %d %d %d\n" % c for c in (srl_map() if cells is None else cells)))
    u = H9.Board9(fault, far_rule="skip", card_has_s2a=True, cells=RAM_CELLS, env=dict({"SM_SRLMAP": str(srl), "SM_SHIFTS": "allowed"}, **(env or {})),
                  **H8.device(known["census"], reads), **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), known, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s400000{share}.bin", "s2_4f")
    return rec, u, out


class TheChain(unittest.TestCase):
    """The chain over the made-up device: three shares."""

    def setUp(self) -> None:
        H9.prepared()
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain4_")) / "chain"
        self.base = json.loads(s1a_run.STAGES["s2_4f"]["expected"].read_text())
        self.calls: list[int] = []

    def runner(self, per_run: dict | None = None, **kw):
        def run(share: int, out: Path) -> None:
            self.calls.append(share)
            run4(share, kw.get("known", KNOWN), out=out, **{k: v for k, v in kw.items() if k != "known"}, **(per_run or {}).get(share, {}))
        return run

    def drive(self, known: dict = KNOWN, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")     # the directories here are in no repository: said to be committed, unless a test asks
        return s2_4_chain.drive(self.root, self.base, known, kw.pop("runner", self.runner()), **kw)

    def test_three_runs_and_the_candidates(self) -> None:
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", [0, 1, 2], ["go on", "go on", "complete"]))
        c = a["closing"]
        self.assertEqual((c["problems"], c["addresses_read"], c["outputs_in_the_design"], c["candidates"], c["candidates_as_they_are"], c["candidates_inverted"]),
                         ([], 55, 128, 252, 128, 124))
        self.assertTrue(c["outcome"].startswith("2: more bits follow than the shift registers have outputs (128): 128 as they are, 124 inverted"), c["outcome"])
        self.assertEqual((c["ctl0"], c["ctl0_in_s2_2"], c["bit_5"]), ([CTL0], CTL0, {}))
        self.assertEqual(sum(c["frames_with_candidates"].values()), 252)
        self.assertEqual(set(c["frames_with_candidates"]), {f"{LOW + f:#010x}" for f in range(4)})
        doc = json.loads((self.root / "candidates.json").read_text())
        self.assertEqual((doc["schema"], doc["label"], doc["candidates"], doc["candidates_as_they_are"], doc["candidates_inverted"], doc["design"]),
                         ("s2_4_candidates", "closed-book", 252, 128, 124, "s2a"))
        self.assertEqual({(x["far"], x["word"], x["bit"]): x["inverted"] for x in doc["places"]}, {k: inv for k, (_, inv) in where(srl_map()).items()})
        self.assertEqual({x["run"] for x in doc["places"]}, {"run01"})
        self.assertEqual([(r["dir"], r["share"]) for r in doc["runs"]], [("run00", 0), ("run01", 1), ("run02", 2)])
        self.assertEqual(json.loads((self.root / "chain.json").read_text()), json.loads(json.dumps(s2_4_chain.brief(a))))
        self.assertNotIn("found", json.loads((self.root / "chain.json").read_text())["closing"])
        self.assertTrue(said[-1].startswith("run02: share 2, 8 addresses, 0 bit(s) follow, 0 inverted, 0 irregular — complete"), said[-1])
        self.assertTrue(said[1].startswith("run01: share 1, 30 addresses, 128 bit(s) follow, 124 inverted, 0 irregular — go on"), said[1])
        self.assertTrue((self.root / "prober.bin").read_bytes() == s1a_run.IMAGE.read_bytes())
        self.assertEqual(s2_4_chain.assess(self.root, self.base, KNOWN)["state"], "complete", "and it stands when looked at again")
        # what part 2 would read: the column the candidates lie in, and the reads that deliver them
        self.assertEqual(st9.candidate_reads(KNOWN["census"], doc), [(LOW - 1, 3), (LOW + 2, 3)], "the column is read in threes from its first frame")

    def test_looking_at_a_chain_writes_nothing_and_runs_nothing(self) -> None:
        a = s2_4_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["next_run"], a["next_share"], a["runs"], a["shares"], self.root.exists()), ("go on", 0, 0, [], 3, False))

    def test_no_second_run_before_the_first_is_committed(self) -> None:
        a = self.drive(committed=s2_4_chain.committed)   # the real question, of a directory that is in no repository
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no second run before the first is committed: run00", a["held"])
        self.assertNotIn("blocked", a)
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["held"], a["held"])
        a = self.drive(max_new=1)
        self.assertEqual((self.calls, a["state"], len(a["runs"])), ([0, 1], "go on", 2), "one run more, and no further")

    def test_outputs_shown_once_each_and_none_inverted_are_outcome_1(self) -> None:
        a = self.drive(runner=self.runner(cells=srl_map(inverted=False)))
        c = a["closing"]
        self.assertEqual((a["state"], c["candidates"], c["candidates_inverted"], c["outcome"][:2]), ("complete", 128, 0, "1:"))

    def test_fewer_bits_than_outputs_are_reported_and_the_chain_is_complete(self) -> None:
        a = self.drive(runner=self.runner(cells=srl_map(outputs=30)))
        c = a["closing"]
        self.assertEqual((a["state"], c["candidates_as_they_are"], c["candidates_inverted"]), ("complete", 120, 120))
        self.assertTrue(c["outcome"].startswith("3: fewer bits follow as they are (120) than the shift registers have outputs (128); 120 follow inverted"), c["outcome"])
        self.assertTrue((self.root / "candidates.json").is_file())

    def test_nothing_that_follows_halts_the_chain_when_it_is_closed(self) -> None:
        a = self.drive(runner=self.runner(cells=[]))
        self.assertEqual((a["state"], self.calls, a["why"]), ("halted", [0, 1, 2], ["4: nothing follows the states of the shift registers"]))
        self.assertFalse((self.root / "candidates.json").exists())
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []), "and nothing is run again")

    def test_a_candidate_among_the_ram_s_places_halts_the_chain_when_it_is_closed(self) -> None:
        cells = srl_map()
        a_, m_, far, word, bit, _ = RAM_CELLS[5]
        cells[3] = (cells[3][0], cells[3][1], far, word, bit, 0)
        a = self.drive(runner=self.runner(cells=cells))
        self.assertEqual(a["state"], "halted")
        self.assertTrue(a["why"][0].startswith("5: 1 candidate(s) lie among the places of the RAM's cells"), a["why"])
        self.setUp()
        a = self.drive(known={k: v for k, v in KNOWN.items() if k != "ram_places"}, runner=self.runner(known={k: v for k, v in KNOWN.items() if k != "ram_places"}))
        self.assertEqual((a["state"], a["why"]), ("halted", ["where the RAM's cells are was not given: the candidates cannot be held apart from them"]))

    def test_a_first_run_under_another_ctl0_than_s2_2_s_halts_the_chain_there(self) -> None:
        other = {"SM_CREG": "ctl0:00000401"}
        a = self.drive(runner=self.runner(env=other))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertEqual([(r["judge"], r["ctl0"], r["decision"]) for r in a["runs"]], [("PASS", "0x00000401", "halt")])
        self.assertEqual(a["why"], ["run00: CTL0 read 0x00000401 in the first run and 0x00000501 in the runs of S2.2, whose frames this step is held against"])
        self.setUp()
        a = self.drive(runner=self.runner(per_run={1: {"env": other}}))
        self.assertEqual((a["state"], self.calls, a["why"]), ("halted", [0, 1], ["run01: CTL0 read 0x00000401 in this run and 0x00000501 in the first run"]))
        self.setUp()
        untold = {k: v for k, v in KNOWN.items() if k != "ctl0_in_s2_2"}
        a = self.drive(known=untold, runner=self.runner(known=untold))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("and None in the runs of S2.2", a["why"][0])

    def test_a_run_that_fails_halts_the_chain_and_nothing_is_run_again(self) -> None:
        a = self.drive(runner=self.runner(per_run={1: {"fault": "srlmoves"}}))
        self.assertEqual((a["state"], self.calls, a["runs"][-1]["decision"]), ("halted", [0, 1], "halt"))
        self.assertTrue(any("the run script's verdict is FAIL" in w for w in a["why"]), a["why"])
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []))

    def test_a_stored_run_that_was_altered_halts_the_chain(self) -> None:
        self.drive()
        v = json.loads((self.root / "run01" / "verdict.json").read_text())
        v["finding"]["follows"] = v["finding"]["follows"][:-1]
        (self.root / "run01" / "verdict.json").write_text(json.dumps(v, indent=1) + "\n")
        a = s2_4_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["why"][0]), ("halted", "run01: the verdict stored beside the result is not what the judge says of the stored result"))
        a = self.drive()
        self.assertFalse((self.root / "candidates.json").exists(), "what a complete chain wrote is taken away when it no longer stands")
        self.setUp(); self.drive()
        raw = bytearray((self.root / "run02" / "result.bin").read_bytes()); raw[5000] ^= 1
        (self.root / "run02" / "result.bin").write_bytes(bytes(raw))
        a = s2_4_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], a["why"][0]), ("halted", "run02: the stored result is not the one whose checksum the board gave"))
        self.setUp(); self.drive()
        (self.root / "run00" / "acc.bin").write_bytes(b"\0" * 8)
        self.assertIn("run00: the list of accesses kept beside the run is not the list planned for it", s2_4_chain.assess(self.root, self.base, KNOWN)["why"])

    def test_run_directories_that_are_not_the_chain_s(self) -> None:
        self.drive(max_new=1)
        (self.root / "run02").mkdir()
        self.assertIn("without a gap", s2_4_chain.assess(self.root, self.base, KNOWN)["why"][0])
        (self.root / "run02").rmdir(); (self.root / "run01").write_text("x")
        self.assertIn("what has the name of a run and is not a directory", s2_4_chain.assess(self.root, self.base, KNOWN)["why"][0])
        (self.root / "run01").unlink()
        for k in (1, 2, 3):
            (self.root / f"run{k:02d}").mkdir()
        self.assertEqual(s2_4_chain.assess(self.root, self.base, KNOWN)["why"], ["4 run directories for 3 shares"])

    def test_a_stored_run_the_judge_fails_now_halts_the_chain_whatever_was_recorded_of_it(self) -> None:
        """The result, the board's checksum in the record and the verdict beside it all changed alike: only the judging
        of the stored result, now, can say that the run does not pass."""
        self.drive()
        d = self.root / "run01"
        raw = (d / "result.bin").read_bytes()
        w = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        w[w[7] + 3 * 480 + 76 + 101 + 5] ^= 0x100                             # a bit of a frame of the first state reads otherwise: irregular
        raw = struct.pack("<%dI" % len(w), *w)
        (d / "result.bin").write_bytes(raw)
        rec = json.loads((d / "run.json").read_text()); rec["board_crc32"] = rec["host_crc32"] = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        (d / "run.json").write_text(json.dumps(rec, indent=1) + "\n")
        exp = s1a_run.with_plan("s2_4f", self.base, 1, KNOWN)
        v = s2_4_judge.judge(w, KNOWN, s1a_run.planned_words(exp))
        (d / "verdict.json").write_text(json.dumps(v, indent=1) + "\n")
        a = s2_4_chain.assess(self.root, self.base, KNOWN)
        self.assertEqual((a["state"], len(a["why"])), ("halted", 2), a.get("why"))
        self.assertTrue(a["why"][0].startswith("run01: the judge says FAIL: ['1 bit(s) changed and follow no cell"), a["why"])

    def test_what_the_closing_asks_of_the_runs_together(self) -> None:
        a = self.drive()
        runs = json.loads(json.dumps(a["runs"]))
        self.assertEqual(s2_4_chain.close(runs, KNOWN)["problems"], [])
        twice = json.loads(json.dumps(runs)); twice[2]["candidates"] = [dict(twice[1]["candidates"][0])]
        self.assertEqual(s2_4_chain.close(twice, KNOWN)["problems"], ["a place is a candidate in two runs: the shares are not apart"])
        fewer = json.loads(json.dumps(runs)); fewer[0]["frames"] -= 1
        self.assertEqual(s2_4_chain.close(fewer, KNOWN)["problems"], ["the runs read 54 addresses; block type 0 has 55 in the census"])

    def test_a_console_that_fails_before_a_run_holds_the_chain_and_no_run_is_started(self) -> None:
        """The board's runner as it is on the device, with the console replaced: the reset before a run is S2.2's
        (came_up_fresh), and a console that cannot be opened holds the chain, blocked, with the reason in its file."""
        import serial, uboot_console

        def no_port():
            raise serial.SerialException("[Errno 2] could not open port: made up")
        keep_log = os.environ.get("SELFMAP_CONSOLE_LOG")
        self.addCleanup(setattr, uboot_console, "UB", uboot_console.UB)
        self.addCleanup(lambda: os.environ.pop("SELFMAP_CONSOLE_LOG", None) if keep_log is None else os.environ.__setitem__("SELFMAP_CONSOLE_LOG", keep_log))
        uboot_console.UB = no_port
        self.root.mkdir(parents=True)
        a = s2_4_chain.drive(self.root, self.base, KNOWN, s2_4_chain.board_runner(self.root), committed=lambda path: "")
        self.assertEqual((a["state"], a.get("blocked"), a["runs"]), ("go on", True, []))
        self.assertIn("before run00: the console failed — SerialException: [Errno 2] could not open port: made up; the run script was not started", a["held"])
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["held"], a["held"])
        self.assertFalse((self.root / "run00").exists()); self.assertFalse((self.root / "run00.out").exists())

    def test_the_command_looks_at_a_chain_and_touches_nothing(self) -> None:
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_chain.py"), "--dir", str(self.root)], capture_output=True, text=True,
                           env=dict(os.environ, SELFMAP_NO_BOARD="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 run(s) stored of 8; the chain: go on", r.stdout)
        self.assertFalse(self.root.exists())

    def frames_as_loaded(self) -> dict:
        """What the made-up device's frames read with the shift registers as loaded: the frames of a complete chain's
        first state, with every place of an output put back to what the output is loaded with."""
        before: dict[int, list[int]] = {}
        for k in range(3):
            raw = (self.root / f"run{k:02d}" / "result.bin").read_bytes()
            w = struct.unpack("<%dI" % (len(raw) // 4), raw)
            for i in range(w[3]):
                r = w[w[7] + i * 480: w[7] + (i + 1) * 480]
                if r[1] == 0 and r[12] == 0 and r[15] < 0x100 and r[14] != 0xF:
                    for j in range(r[14]):
                        before[r[0] + j] = list(r[76 + 101 * (j + 1): 76 + 101 * (j + 2)])
        for a, k, far, word, bit, inv in srl_map():
            before[far][word] = (before[far][word] & ~(1 << bit)) | (((LOADED[a] >> k) & 1) ^ inv) << bit
        return {far: tuple(f) for far, f in before.items()}

    def test_the_frames_are_held_against_what_was_stored_before_and_what_reads_otherwise_is_said(self) -> None:
        a = self.drive()
        self.assertEqual(a["closing"]["frames_that_read_otherwise_than_in_s2_2_elsewhere"], "not compared: the frames S2.2 stored were not given")
        before = self.frames_as_loaded()
        a = s2_4_chain.assess(self.root, self.base, dict(KNOWN, frames_before=before))
        self.assertEqual((a["state"], a["closing"]["frames_that_read_otherwise_than_in_s2_2_elsewhere"], [r["elsewhere"] for r in a["runs"]]), ("complete", [], [[], [], []]))
        other = dict(before); f = list(other[0xA81]); f[7] ^= 0x8000; other[0xA81] = tuple(f)
        del other[0x400A01]
        a = s2_4_chain.assess(self.root, self.base, dict(KNOWN, frames_before=other))
        self.assertEqual(a["state"], "complete", "reported, and no failure")
        self.assertEqual(a["closing"]["frames_that_read_otherwise_than_in_s2_2_elsewhere"],
                         [{"far": "0x00000a81", "word": 7, "bit": 15, "what": "reads otherwise than S2.2 stored it, and follows nothing", "run": "run00"},
                          {"far": "0x00400a01", "word": None, "bit": None, "what": "a frame S2.2 did not store", "run": "run02"}])
        self.assertEqual(s2_4_chain.brief(a)["runs"][0]["elsewhere"], 1)

    def test_the_prediction_is_held_against_the_candidates(self) -> None:
        self.drive()
        keep = s2_4_predict.places
        try:
            s2_4_predict.places = lambda _: {(far, word, bit): (k, a, False) for a, k, far, word, bit, inv in srl_map() if not inv}
            p = s2_4_chain.assess(self.root, self.base, dict(KNOWN, prediction={}))["closing"]["prediction"]
            self.assertEqual(p, {"places_named": 128, "candidates_as_they_are_among_them": 128,
                                 "says": "hit: every place the prediction names is a candidate that follows as it is", "not_such": []})
            s2_4_predict.places = lambda _: {(far + (1 if a == 0 else 0), word, bit): (k, a, False) for a, k, far, word, bit, inv in srl_map() if not inv}
            p = s2_4_chain.assess(self.root, self.base, dict(KNOWN, prediction={}))["closing"]["prediction"]
            self.assertEqual((p["says"], p["candidates_as_they_are_among_them"], len(p["not_such"])), ("miss: 4 place(s) it names are not such candidates", 124, 4))
            s2_4_predict.places = lambda _: {(far, word, bit): (k, a, False) for a, k, far, word, bit, inv in srl_map() if inv}
            p = s2_4_chain.assess(self.root, self.base, dict(KNOWN, prediction={}))["closing"]["prediction"]
            self.assertTrue(p["says"].startswith("miss: 124"), "places that follow inverted are not what it names")
            s2_4_predict.places = lambda _: {(far, word, bit): (k, a, True) for a, k, far, word, bit, inv in srl_map() if not inv}
            p = s2_4_chain.assess(self.root, self.base, dict(KNOWN, prediction={}))["closing"]["prediction"]
            self.assertTrue(p["says"].startswith("miss: 128"), "nor is a place it names as inverted, where the bit follows as it is")
            s2_4_predict.places = lambda _: {}
            self.assertEqual(s2_4_chain.assess(self.root, self.base, dict(KNOWN, prediction={}))["closing"]["prediction"]["says"], "the prediction names no place")
        finally:
            s2_4_predict.places = keep
        self.assertNotIn("prediction", s2_4_chain.assess(self.root, self.base, KNOWN)["closing"])

    def test_the_stored_prediction_as_places(self) -> None:
        said = s2_4_predict.places(json.loads(s2_4_chain.PREDICTION.read_text()))
        self.assertEqual(len(said), 128)
        self.assertEqual({(far, word, bit): (k, a, False) for k in range(4) for a in range(32)
                          for far, word, bit in [(0x1820 + RULE[2 * a + 1][0], 40 + k // 2, 16 * (k % 2) + RULE[2 * a + 1][1])]}, said)
        self.assertEqual(sorted({far for far, _, _ in said}), [0x1821, 0x1823])


if __name__ == "__main__":
    unittest.main()

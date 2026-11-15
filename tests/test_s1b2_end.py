"""S1b.2b: the end of the row (docs/s1b_plan.md, section 29) — the two table runs through the run script on the twin
behind the pretended board, their judge, and the program that lays them out. The twin is given several ends of a row;
what the device does there is not known, and nothing here says which of them it is."""
from __future__ import annotations

import ast
import json
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
import dx_judge  # noqa: E402
import s1a_run  # noqa: E402
import s1b2_end as layout  # noqa: E402
import s1b2_judge  # noqa: E402
import s1b2e_judge  # noqa: E402
import test_s1a_run as fake  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
LAST = 0x1BA9                                        # the last address the device named in the row (S1b.2, run 30)
STARTS = [0x1BA6, 0x1BA7, 0x1BA8, 0x1BA9]
COLUMN = list(range(0x1B80, LAST + 1))
H1, H2 = 0x7F000001, 0x7F000002                      # places without an address of their own: numbers no frame has (the twin's SM_SHOWS)
NEXT_ROW = 0x00400000
# ends of a row for the twin: which place follows which, and what the register shows at a place that is not its own number
ENDS = {"one place where the register stands still": ({LAST: H1, H1: NEXT_ROW}, {H1: LAST}),
        "two places, the register still at the first": ({LAST: H1, H1: H2, H2: NEXT_ROW}, {H1: LAST, H2: NEXT_ROW}),
        "two places, the register still at both": ({LAST: H1, H1: H2, H2: NEXT_ROW}, {H1: LAST, H2: LAST}),
        "no such place": ({LAST: NEXT_ROW}, {})}
ONE, TWO, BOTH, NONE = ENDS
# what the register shows 1, 2, 3, 4 steps beyond the last address, and at which of those steps it did not change
SHOWN = {ONE: ([LAST, NEXT_ROW, NEXT_ROW + 1, NEXT_ROW + 2], [1]), TWO: ([LAST, NEXT_ROW, NEXT_ROW, NEXT_ROW + 1], [1, 3]),
         BOTH: ([LAST, LAST, NEXT_ROW, NEXT_ROW + 1], [1, 2]), NONE: ([NEXT_ROW, NEXT_ROW + 1, NEXT_ROW + 2, NEXT_ROW + 3], [])}
PLACES = {ONE: [H1, NEXT_ROW], TWO: [H1, H2], BOTH: [H1, H2], NONE: [NEXT_ROW, NEXT_ROW + 1]}      # what lies 1 and 2 places beyond

_MADE: dict = {}


def once(name: str, make):
    """Made by the first test that asks, kept for the rest; a failure is kept as well, so that each test fails by itself."""
    if name not in _MADE:
        try:
            _MADE[name] = (make(), None)
        except Exception as e:
            _MADE[name] = (None, e)
    value, error = _MADE[name]
    if error is not None:
        raise error
    return value


def the_set(stage: str) -> dict:
    def make() -> dict:
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        return {s: json.loads(s1a_run.STAGES[s]["expected"].read_text()) for s in ("s1b2", "s1b2e", "s1b2c")}
    return json.loads(json.dumps(once("sets", make)[stage]))


def run(stage: str, end: str = ONE, fault: str = "", frames: dict | None = None, start: int | None = None, **quirks):
    """One run through the run script on the pretended board, whose twin has the given end of the row. Returns the
    run record, the verdict, the board and the directory."""
    succ, shows = ENDS[end]
    model = frames_for(COLUMN + [H1, H2, NEXT_ROW, NEXT_ROW + 1]) if frames is None else frames
    pl = s1a_run.PL.read_bytes()
    exp = the_set(stage)
    if start is not None:
        exp = s1a_run.with_start(stage, exp, start, "a test")
    u = fake.FakeUBoot(fault, far_rule="skip", succ=succ, shows=shows, frames=model, **quirks)
    out = Path(scratch_dirs.mkdtemp(prefix="smend_")) / "run"
    out.mkdir()
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", stage)
    verdict = json.loads((out / "verdict.json").read_text()) if (out / "verdict.json").exists() else None
    return rec, verdict, u, out


def the(stage: str, end: str = ONE):
    return once(f"{stage} / {end}", lambda: run(stage, end, start=0x1B80 if stage == "s1b2" else None))


def h(a: int) -> str:
    return f"{a:#010x}"


class TheTwoSets(unittest.TestCase):
    def test_they_are_the_tables_that_were_proposed(self) -> None:
        e, c = ([int(w, 16) for w in the_set(s)["params"]] for s in ("s1b2e", "s1b2c"))
        for p in (e, c):
            self.assertEqual((p[0], p[1], p[2], p[3], p[4], p[5], p[8], p[9], p[12], p[13], p[14], p[15]),
                             (0x31504D53, 1, 5, 0, 0x1FFFF, 0xB99, 0, 0x00200000, 0, 0, 0, 2 << 8), "stage 5, the row's envelope, no budget, the table form, the wait that touches no memory")
        ops = lambda p: [(p[16 + k], (p[10 + k // 8] >> (4 * (k % 8))) & 0xF) for k in range(p[6])]
        self.assertEqual((ops(e), e[7]), ([(a, n) for a in STARTS for n in (0, 1, 2, 3)], 3))
        self.assertEqual((ops(c), c[7], c[16 + 14:]), ([(0x1B80 + 3 * k, 3) for k in range(14)], 2, [0, 0]))
        self.assertEqual(sorted(a + j for a, n in ops(c) for j in range(n)), COLUMN, "the 42 addresses of the column, each once")
        for p in (e, c):                                 # the bound that was agreed: no address above the last one named, no read of more than three frames
            self.assertLessEqual(max(a for a, _ in ops(p)), LAST)
            self.assertLessEqual(max(n for _, n in ops(p)), 3)
        self.assertEqual(max(a + n - 1 for a, n in ops(e)) - LAST, 2, "at most two places beyond the last address are delivered")
        self.assertEqual(max(a + n - 1 for a, n in ops(c)), LAST, "the column's reads deliver nothing from beyond it")
        self.assertEqual([the_set(s)["records"] for s in ("s1b2e", "s1b2c")], [50, 30])

    def test_nothing_of_them_is_given_at_run_time(self) -> None:
        for stage in ("s1b2e", "s1b2c"):
            self.assertIs(s1a_run.STAGES[stage]["judge"], s1b2e_judge)
            with self.assertRaises(ValueError):
                s1a_run.with_start(stage, the_set(stage), LAST, "x")
            r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--start", "1ba9", "--dry-run"], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout.strip()), (2, f"REFUSED: the starting address of {stage} is fixed"))
            r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--dry-run"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("mw.l 1010003c 00000200 1", r.stdout, "the wait is chosen in word 15")

    def test_the_prober_writes_no_address_above_the_last_and_reads_no_more_than_was_agreed(self) -> None:
        for stage, records in (("s1b2e", 50), ("s1b2c", 30)):
            for end in (ONE, TWO):
                with self.subTest(stage=stage, end=end):
                    rec, v, u, _ = the(stage, end)
                    self.assertEqual((rec["verdict"], rec["problems"], rec.get("stop"), v["header"]["status"], v["header"]["records"], v["header"]["anomalies"]),
                                     ("PASS", [], None, "0x1", records, 0))
                    streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
                    written = {s[k + 1] for s in streams for k in range(len(s) - 1) if s[k] == 0x30002001}
                    self.assertEqual(written, {0xB99} | (set(STARTS) if stage == "s1b2e" else {0x1B80 + 3 * k for k in range(14)}))
                    self.assertLessEqual(max(int(line.split()[5][5:]) for line in u.twin_lines if line.startswith("DMA")), 404)
                    self.assertEqual([line for line in u.twin_lines if line.startswith("VIOLATION")], [])
                    self.assertEqual(v["params"]["diagnostic"], {"generated_sequence_of_addresses": 0, "extra_stack_words": 0, "polling_loop": dx_judge.s1b0_judge.POLLING[2]})


class TheJudgeOfTheseRuns(unittest.TestCase):
    def test_frames_without_a_known_answer_are_counted_here_and_held_against_the_run_nowhere_else(self) -> None:
        rec, v, u, out = the("s1b2e", ONE)
        raw = (out / "result.bin").read_bytes()
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        block = [int(w, 16) for w in the_set("s1b2e")["params"]]
        mine, theirs = s1b2e_judge.judge(words, KNOWN, block), dx_judge.judge(words, KNOWN, block)
        self.assertEqual((mine, mine["verdict"], mine["problems"], mine["frames_delivered_without_a_known_answer"]), (v, "PASS", [], 3 * 4 * (0 + 1 + 2 + 3)))
        self.assertEqual(theirs["verdict"], "FAIL", "the judge of the diagnostic series, as it was")
        self.assertEqual(len(theirs["problems"]), 72)
        self.assertTrue(all("no known answer for FAR" in p for p in theirs["problems"]))
        self.assertNotIn("frames_delivered_without_a_known_answer", theirs)
        self.assertEqual({k: x for k, x in mine.items() if k not in ("verdict", "problems", "frames_delivered_without_a_known_answer")},
                         {k: x for k, x in theirs.items() if k not in ("verdict", "problems")}, "everything else is that judge, word for word")
        self.assertEqual((s1b2e_judge.HDR, s1b2e_judge.REC, s1b2e_judge.MAX_RECORDS, s1b2e_judge.STAGE), (dx_judge.HDR, dx_judge.REC, dx_judge.MAX_RECORDS, 5))

    def test_a_frame_that_has_a_known_answer_is_still_held_against_it(self) -> None:
        other = frames_for(COLUMN + [H1, H2, NEXT_ROW, NEXT_ROW + 1])
        other[0xB99] = [w ^ (1 if k == 50 else 0) for k, w in enumerate(frames_for([0xB99])[0xB99])]      # the reference frame, one bit off
        rec, v, _, _ = run("s1b2e", ONE, frames=other)
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertTrue(any("differs from the known frame" in p for p in v["problems"]), v["problems"])

    def test_what_stops_such_a_run(self) -> None:
        for fault, status, why in (("err@40", "0x221", "the run did not complete"), ("farflip@30", "0x400", "anomalous read"), ("flip@33", "0x400", "anomalous read")):
            with self.subTest(fault=fault):
                rec, v, _, out = run("s1b2e", ONE, fault=fault)
                self.assertEqual((rec["verdict"], v["header"]["status"]), ("FAIL", status))
                self.assertTrue(any(why in p for p in v["problems"]), v["problems"])
                (out / "v.json").write_text(json.dumps(v))
                p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), str(out / "v.json")], capture_output=True, text=True)
                self.assertEqual(p.returncode, 1)
                self.assertIn("the judge did not pass this run", json.loads(p.stdout)["the_end"]["note"])


class TheLayoutOfTheEnd(unittest.TestCase):
    def test_each_end_of_a_row_is_laid_out_as_it_is(self) -> None:
        for end, (shown, still) in SHOWN.items():
            with self.subTest(end=end):
                rec, v, _, _ = the("s1b2e", end)
                self.assertEqual(rec["verdict"], "PASS")
                e = layout.end(v)
                self.assertEqual((e["run"]["verdict"], e["disagreements"], e["starting_addresses"], e["starting_addresses_one_step_apart"]), ("PASS", [], [h(a) for a in STARTS], True))
                self.assertEqual([p["position"] for p in e["positions"]], list(range(8)), "positions 0..3 are the addresses written, 4..7 lie beyond")
                self.assertEqual([p["register"] for p in e["positions"]], [[]] + [[h(a)] for a in STARTS[1:]] + [[h(a)] for a in shown])
                self.assertEqual([p["beyond_the_last_address_written"] for p in e["positions"]], [0, 0, 0, 0, 1, 2, 3, 4])
                self.assertEqual([len(p["reached_by"]) for p in e["positions"]], [0, 1, 2, 3, 4, 3, 2, 1], "every position but the last from more than one start, or one")
                self.assertTrue(all(p["agree"] for p in e["positions"]))
                self.assertEqual(e["beyond"]["last_address_written"], h(LAST))
                self.assertEqual(e["beyond"]["register_step_by_step"], [{"steps_beyond": k + 1, "register": h(a)} for k, a in enumerate(shown)])
                self.assertEqual(e["beyond"]["steps_at_which_the_register_did_not_change"], still)
                # what was delivered: positions 0..3 are the frames at the addresses written, 4 and 5 lie beyond
                frames = frames_for(COLUMN + [H1, H2, NEXT_ROW, NEXT_ROW + 1])
                sha = lambda a: __import__("hashlib").sha256(b"".join(struct.pack(">I", w) for w in frames[a])).hexdigest()
                self.assertEqual([(d["position"], d["frame_sha256"], d["ways"], d["agree"]) for d in e["delivered"]],
                                 [(k, [sha(a)], n, True) for k, (a, n) in enumerate(zip(STARTS + PLACES[end], (3, 5, 6, 6, 3, 1)))])
                self.assertEqual(e["beyond"]["frames_delivered_from_beyond"], [{"steps_beyond": k + 1, "frame_sha256": [sha(a)], "all_zero": False, "ways": n}
                                                                              for k, (a, n) in enumerate(zip(PLACES[end], (3, 1)))])
                self.assertEqual((e["distinct_contents_delivered"], "note_on_content" in e), (6, False))
        self.assertEqual(len({json.dumps(layout.end(the("s1b2e", end)[1])["beyond"]["register_step_by_step"]) for end in ENDS}), 4, "the four ends are told apart by the register alone")

    def test_the_reads_are_listed_as_they_were_made(self) -> None:
        e = layout.end(the("s1b2e", TWO)[1])
        self.assertEqual([(r["at"], r["steps"], r["frames_delivered"], r["times"]) for r in e["reads"]], [(h(a), k, k - 1, 3) for a in STARTS for k in (1, 2, 3, 4)])
        self.assertEqual([r["register_afterwards"] for r in e["reads"] if r["at"] == h(LAST)], [[h(LAST)], [h(NEXT_ROW)], [h(NEXT_ROW)], [h(NEXT_ROW + 1)]])
        self.assertEqual(e["run"]["polling_loop"], dx_judge.s1b0_judge.POLLING[2])

    def test_where_every_frame_is_the_same_the_content_says_nothing_and_the_layout_says_so(self) -> None:
        zeros = {a: [0] * 101 for a in COLUMN + [H1, H2, NEXT_ROW, NEXT_ROW + 1]}
        rec, v, _, _ = run("s1b2e", TWO, frames=zeros)
        e = layout.end(v)
        self.assertEqual((rec["verdict"], e["disagreements"], e["distinct_contents_delivered"]), ("PASS", [], 1))
        self.assertIn("every frame delivered is the same (all zero)", e["note_on_content"])
        self.assertTrue(all(d["all_zero"] and d["frame_sha256"] == [layout.ALL_ZERO] for d in e["delivered"]))
        self.assertEqual(e["beyond"]["register_step_by_step"], [{"steps_beyond": k + 1, "register": h(a)} for k, a in enumerate(SHOWN[TWO][0])], "the register still tells")
        some = dict(zeros); some[H1] = [0] * 100 + [1]                           # one word in a place beyond the row
        e = layout.end(run("s1b2e", TWO, frames=some)[1])
        self.assertEqual(([d["all_zero"] for d in e["delivered"]], e["distinct_contents_delivered"], "note_on_content" in e), ([True] * 4 + [False, True], 2, False))

    def test_two_ways_to_a_place_that_do_not_agree_are_listed(self) -> None:
        _, v, _, out = the("s1b2e", ONE)

        def changed(change) -> dict:
            w = json.loads(json.dumps(v)); change([r for r in w["records"] if r["kind"] == "target"]); return w
        register = changed(lambda t: [r.update(far_read_back=h(NEXT_ROW)) for r in t if (r["far"], r["frames"]) == (h(0x1BA8), 3)])   # the value of the step before
        e = layout.end(register)
        self.assertEqual(len(e["disagreements"]), 1)
        self.assertIn("position 6: the register read 0x00400000 after [['0x00001ba8', 4]], 0x00400001 after [['0x00001ba9', 3]]", e["disagreements"][0])
        self.assertEqual([p["agree"] for p in e["positions"]], [True] * 6 + [False, True])
        self.assertEqual(e["beyond"]["steps_at_which_the_register_did_not_change"], [1], "a step with two values is not counted either way")
        content = changed(lambda t: [r.update(frame_sha256=r["frame_sha256"][:2] + ["0" * 64]) for r in t if (r["far"], r["frames"]) == (h(0x1BA8), 3)])
        e = layout.end(content)
        self.assertEqual((len(e["disagreements"]), [d["agree"] for d in e["delivered"]]), (1, [True] * 4 + [False, True]))
        self.assertIn("position 4: the frames delivered there differ", e["disagreements"][0])
        once_only = changed(lambda t: t[5].update(far_read_back=h(0x1234)))                  # one repeat of one read
        self.assertTrue(any("did not leave the same thing every time" in d for d in layout.end(once_only)["disagreements"]))
        arrived = changed(lambda t: [r.update(far_read_back=h(0x1BA9)) for r in t if (r["far"], r["frames"]) == (h(0x1BA6), 1)])
        self.assertTrue(any("position 2 is the address written 0x00001ba8, yet the register read" in d for d in layout.end(arrived)["disagreements"]))
        for name, w in (("register", register), ("content", content), ("once", once_only)):  # and the program's exit code says so
            (out / f"{name}.json").write_text(json.dumps(w))
            self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), str(out / f"{name}.json")], capture_output=True).returncode, 1, name)
        (out / "v.json").write_text(json.dumps(v))
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), str(out / "v.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, {"the_end": layout.end(v)}))

    def test_starting_addresses_that_are_not_one_step_apart_give_no_positions(self) -> None:
        succ, shows = ENDS[ONE]
        saved = dict(ENDS)
        ENDS["a gap"] = ({**succ, 0x1BA7: LAST}, shows)                          # after 0x1ba7 the device names 0x1ba9
        try:
            rec, v, _, _ = run("s1b2e", "a gap")
        finally:
            ENDS.clear(); ENDS.update(saved)
        e = layout.end(v)
        self.assertEqual((rec["verdict"], e["starting_addresses_one_step_apart"], "positions" in e, "beyond" in e), ("PASS", False, False, False))
        self.assertIn("no positions are derived", e["note_on_positions"])
        self.assertEqual(len(e["reads"]), 16, "the reads themselves are listed all the same")

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1b2_end.py").read_text()
        numbers = {n.value for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 3, 4, 12, 16, 101}, set(), "no address, no count of steps, no count of frames of any column")
        for word in ("prjxray", "part.json", "frame_count", "1ba", "400000"):
            self.assertNotIn(word, text.lower())
        tree = ast.parse(text)
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "hashlib", "json", "sys", "pathlib"}, set(), "it works from verdict files and nothing else")
        self.assertNotIn("prjxray", (ROOT / "host" / "s1b2e_judge.py").read_text().lower())


class TheColumnAgain(unittest.TestCase):
    def test_the_twin_stops_the_walk_at_such_an_end_as_the_board_did(self) -> None:
        stored = json.loads((ROOT / "evidence" / "s1b2_17A6_2026-11-15" / "run30" / "verdict.json").read_text())
        for end in (ONE, TWO):
            with self.subTest(end=end):
                rec, v, _, _ = the("s1b2", end)
                self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], v["passes"][0]), ("FAIL", "0x800", 42, stored["passes"][0]))
                self.assertEqual([(r["far"], r["frames"], r["far_read_back"]) for r in v["records"][-6:]], [(r["far"], r["frames"], r["far_read_back"]) for r in stored["records"][-6:]],
                                 "the last six records: the addresses, the reads and the register, as stored from the board")
                self.assertEqual(v["problems"], stored["problems"])
        self.assertNotEqual(the("s1b2", NONE)[1]["header"]["status"], "0x800", "an end without such a place is not what the board showed")

    def test_the_column_read_again_is_held_against_the_walk(self) -> None:
        for end in (ONE, TWO):
            with self.subTest(end=end):
                (rec, again, _, _), walk, at_the_end = the("s1b2c", end), the("s1b2", end)[1], the("s1b2e", end)[1]
                self.assertEqual(rec["verdict"], "PASS")
                c = layout.column(again, walk, at_the_end)
                self.assertEqual((c["disagreements"], c["frames_the_walk_delivered"], c["frames_compared"], c["same"]), ([], 42, 42, 42))
                self.assertEqual((c["addresses_of_the_walk_not_read_again"], c["frames_at_places_the_walk_did_not_reach"], c["distinct_contents"], "note_on_content" in c), ([], [], 42, False))
                self.assertEqual((c["run"]["verdict"], c["walk"]), ("PASS", {"verdict": "FAIL", "status": "0x800"}))
                # the register after each read of three: four steps on, by the walk's own successors, as far as they reach
                self.assertEqual([(r["at"], r["steps"], r["register_afterwards"], r["the_walk_says"], r["as_the_walk_says"]) for r in c["register"][:13]],
                                 [(h(0x1B80 + 3 * k), 4, [h(0x1B84 + 3 * k)], h(0x1B84 + 3 * k), True) for k in range(13)])
                self.assertEqual(c["register"][13], {"at": h(0x1BA7), "steps": 4, "register_afterwards": [h(NEXT_ROW)], "the_walk_says": None, "as_the_walk_says": None},
                                 "the last read ends beyond what the walk could say")
                self.assertEqual(c["reads_also_made_at_the_end"], [{"at": h(0x1BA7), "steps": 4}])

    def test_a_frame_or_a_register_that_is_not_the_walks_is_listed(self) -> None:
        again, walk, at_the_end = the("s1b2c", ONE)[1], the("s1b2", ONE)[1], the("s1b2e", ONE)[1]
        other = json.loads(json.dumps(walk)); other["walk"][7]["frame_sha256"] = "0" * 64
        c = layout.column(again, other, at_the_end)
        self.assertEqual((len(c["disagreements"]), c["same"], c["frames_compared"]), (1, 41, 42))
        self.assertIn("the frame at 0x00001b87: the read of 3 frames from 0x00001b86 delivered", c["disagreements"][0])
        moved = json.loads(json.dumps(again)); [r.update(far_read_back=h(0x1B8B)) for r in moved["records"] if r["kind"] == "target" and r["far"] == h(0x1B86)]
        c = layout.column(moved, walk, at_the_end)
        self.assertEqual(c["disagreements"], ["after 4 step(s) from 0x00001b86 the register read ['0x00001b8b']; by the walk's successors it is 0x00001b8a"])
        once_only = json.loads(json.dumps(again))                                              # one repeat of one read leaves another register
        [r.update(far_read_back=h(0x1B8B)) for r in once_only["records"] if r["kind"] == "target" and r["far"] == h(0x1B86) and r["repeat"] == 1]
        self.assertIn("the read of 4 step(s) at 0x00001b86 did not leave the same thing every time", layout.column(once_only, walk, at_the_end)["disagreements"])
        shorter = json.loads(json.dumps(walk)); shorter["walk"] = shorter["walk"][:-2]            # a walk that did not get as far
        c = layout.column(again, shorter, at_the_end)
        self.assertEqual((c["frames_compared"], c["same"], c["disagreements"], len(c["frames_at_places_the_walk_did_not_reach"])), (40, 40, [], 1))
        self.assertEqual(c["frames_at_places_the_walk_did_not_reach"][0]["read_at"], h(0x1BA7))
        longer = json.loads(json.dumps(walk)); longer["walk"].insert(0, {"far": h(0x1B7F), "next": h(0x1B80), "frame_sha256": "1" * 64})
        self.assertEqual(layout.column(again, longer, at_the_end)["addresses_of_the_walk_not_read_again"], [h(0x1B7F)])
        elsewhere = json.loads(json.dumps(at_the_end)); [r.update(far_read_back=h(0x1234)) for r in elsewhere["records"] if r["kind"] == "target" and (r["far"], r["frames"]) == (h(0x1BA7), 3)]
        c = layout.column(again, walk, elsewhere)
        self.assertEqual(c["disagreements"], ["the read of 4 step(s) at 0x00001ba7 left something else in the run at the end of the row"])
        self.assertNotIn("reads_also_made_at_the_end", layout.column(again, walk))

    def test_a_column_of_frames_that_are_all_the_same(self) -> None:
        zeros = {a: [0] * 101 for a in COLUMN + [H1, H2, NEXT_ROW, NEXT_ROW + 1]}
        again, walk = run("s1b2c", ONE, frames=zeros)[1], run("s1b2", ONE, frames=zeros, start=0x1B80)[1]
        c = layout.column(again, walk)
        self.assertEqual((c["disagreements"], c["same"], c["distinct_contents"]), ([], 42, 1))
        self.assertIn("every frame is the same (all zero)", c["note_on_content"])

    def test_the_three_verdicts_through_the_command_line(self) -> None:
        (_, e, _, out), c, w = the("s1b2e", TWO), the("s1b2c", TWO)[1], the("s1b2", TWO)[1]
        for name, v in (("e", e), ("c", c), ("w", w)):
            (out / f"{name}.json").write_text(json.dumps(v))
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), *(str(out / f"{n}.json") for n in "ecw")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, {"the_end": layout.end(e), "the_column_again": layout.column(c, w, e)}))
        bad = json.loads(json.dumps(w)); bad["walk"][3]["frame_sha256"] = "0" * 64
        (out / "w2.json").write_text(json.dumps(bad))
        self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), str(out / "e.json"), str(out / "c.json"), str(out / "w2.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_end.py"), str(out / "e.json"), str(out / "c.json")], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()

"""S1b.4: the chain over block type 1 (docs/s1b_plan.md, section 49) — the one rule of the chain that changed, the
chain driver with the set s1b4 on the twin behind the pretended board, the summary over rows told which set it
reads, the comparison with a stored run, and the grader given block type 1.

The device here is made up: three rows of block type 1 whose columns have lengths no part has, each ending as the
rows of block type 0 did on the board, and variants. No database is read; the grader is given a made-up one. No
number of any real part is in this file but the one address the board named after block type 0."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import grade_s1b3  # noqa: E402
import s1a_run  # noqa: E402
import s1b2_chain as chain  # noqa: E402
import s1b3_rows  # noqa: E402
import s1b4_first as first_run  # noqa: E402
import test_s1a_run as fake  # noqa: E402
import test_s1b2 as row_tests  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2 import KNOWN, once  # noqa: E402
from test_s1b3 import device  # noqa: E402

STAGE = "s1b4"
B = 0x00800000                                       # named by the board after the last frame of block type 0
BOTTOM = 0x00400000
ABOVE = 0x01000000                                   # the first address above the envelope
# made up: 100, 66 and 90 frames — no pass of 64 frames meets two ends
ROWS = [(B, [70, 30]), (B | 1 << 17, [66]), (B | BOTTOM, [40, 50])]
FRAMES = sum(sum(sizes) for _, sizes in ROWS)


def h(a: int) -> str:
    return f"{a:#010x}"


def copy(x):
    return json.loads(json.dumps(x))


def base(stage: str = STAGE) -> list[int]:
    row_tests.the_set()                              # builds the image and writes the sets, once
    return [int(w, 16) for w in json.loads(s1a_run.STAGES[stage]["expected"].read_text())["params"]]


def runner(dev, seen: list | None = None, per_run: dict | None = None, stage: str = STAGE):
    _, places, succ, shows = dev
    pl = s1a_run.PL.read_bytes()
    model = frames_for(places)

    def run(start: int, out: Path, came_from: str) -> None:
        k = int(out.name[3:])
        change = (per_run or {}).get(k, {})
        exp = s1a_run.with_start(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), start, came_from)
        u = fake.FakeUBoot(change.get("fault", ""), far_rule="skip", succ=change.get("succ", succ), shows=change.get("shows", shows),
                           frames={**model, **change.get("frames", {})})
        out.mkdir()
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s{k:07d}.bin", stage)
        if seen is not None:
            seen.append((k, start, u))
    return run


def drive(dev, name: str = "chain", **kw):
    tmp, seen = Path(scratch_dirs.mkdtemp(prefix="smb4_")), []
    a = chain.drive(tmp / name, base(), KNOWN, runner(dev, seen, kw.pop("per_run", None)), chain.BOUNDS[STAGE], stage=STAGE, **kw)
    return tmp / name, seen, a


def the(name: str = "three rows", **kw):
    """(the device, the directory, what the pretended boards saw, the assessment, the summary over rows)"""
    def make():
        dev = device(ROWS, after=ABOVE, **kw)
        root, seen, a = drive(dev)
        return dev, root, seen, a, copy(s1b3_rows.summarize(a, KNOWN))
    return once(f"s1b4 / {name}", make)


def stored_run() -> dict:
    """One run of S1b.4a's set on the same made-up device: what the chain's first run is held against."""
    def make() -> dict:
        _, places, succ, shows = the()[0]
        exp = json.loads(s1a_run.STAGES["s1b4a"]["expected"].read_text())
        pl = s1a_run.PL.read_bytes()
        out = Path(scratch_dirs.mkdtemp(prefix="smb4a_")) / "run"
        out.mkdir()
        u = fake.FakeUBoot("", far_rule="skip", succ=succ, shows=shows, frames=frames_for(places))
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", "s1b4a")
        return json.loads((out / "verdict.json").read_text())
    return copy(once("s1b4 / the stored run", make))


def database(rows=ROWS, more_after: bool = False) -> dict:
    """A part description of the database's shape: these rows as block-RAM content, rows of block type 0 beside them,
    and — only if asked — nothing the grader could take for a block type after this one."""
    out: dict = {"global_clock_regions": {}}
    for base_address, sizes in rows:
        half, k = ("bottom" if base_address & BOTTOM else "top"), (base_address >> 17) & 0x1F
        buses = out["global_clock_regions"].setdefault(half, {"rows": {}})["rows"].setdefault(str(k), {"configuration_buses": {}})["configuration_buses"]
        buses["BLOCK_RAM"] = {"configuration_columns": {str(c): {"frame_count": n} for c, n in enumerate(sizes)}}
        buses["CLB_IO_CLK"] = {"configuration_columns": {"0": {"frame_count": 7}}}
        if more_after:
            buses["CFG_CLB"] = {"configuration_columns": {"0": {"frame_count": 3}}}
    return out


class TheSet(unittest.TestCase):
    def test_it_is_the_set_of_the_one_run_word_for_word_with_the_start_given_at_run_time(self) -> None:
        self.assertEqual(base(), base("s1b4a"))
        self.assertEqual((base()[3], base()[4], base()[10], base()[16]), (0, ABOVE - 1, 1, B))
        self.assertIs(s1a_run.STAGES[STAGE]["judge"], s1a_run.STAGES["s1b3"]["judge"])
        self.assertEqual((STAGE in s1a_run.STARTS_AT_RUN_TIME, "s1b4a" in s1a_run.STARTS_AT_RUN_TIME, chain.BOUNDS[STAGE]), (True, False, 48))
        exp = s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), B + 0x3F, "a test")
        self.assertEqual((exp["params"][16], exp["chain"]["start"]), ("0080003f", "0x0080003f"))
        with self.assertRaises(ValueError):                 # nothing above block type 1 can be started at
            s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), ABOVE, "a test")
        both = [json.loads(s1a_run.STAGES[s]["expected"].read_text()) for s in (STAGE, "s1b4a")]
        self.assertEqual(both[0]["image_sha256"], both[1]["image_sha256"])     # which image that is, is held where it ran: test_board_evidence

    def test_the_chain_begins_at_the_address_the_board_named_after_block_type_0(self) -> None:
        rows = json.loads((ROOT / "evidence" / "s1b3_17A6_2026-11-17" / "rows.json").read_text())
        self.assertEqual(h(base()[chain.P_START]), rows["end"]["named_after_the_last_frame"])
        self.assertTrue(all(int(a, 16) < base()[chain.P_START] for a in KNOWN["frames"]), "every frame with a known answer lies below it")
        self.assertTrue(all(base()[chain.P_LO] <= int(a, 16) <= base()[chain.P_HI] for a in KNOWN["frames"]), "and inside the envelope, where the old rule asked for them")


class TheRule(unittest.TestCase):
    """The chain's own count of the frames with a known answer, on written-out runs: whatever the judges said."""

    def assess(self, start: int, runs: tuple, known: dict, lo: int = 0, hi: int = 0x1FFFF) -> dict:
        block = base("s1b2"); block[chain.P_LO], block[chain.P_HI], block[chain.P_START] = lo, hi, start
        root = Path(scratch_dirs.mkdtemp(prefix="smrule_"))
        for k in range(len(runs)):
            (root / f"run{k:02d}").mkdir()
        saved = chain.read_run
        chain.read_run = lambda d, base, start, known, stage="s1b2": {"dir": d.name, "start": f"{start:#010x}", **copy(runs[int(d.name[3:])])}
        try:
            return chain.assess(root, block, known)
        finally:
            chain.read_run = saved

    @staticmethod
    def made_up(first: int, n: int, ended=chain.LIMIT, named: str | None = None) -> dict:
        walk = [{"far": h(first + i), "next": h(first + i + 1), "frame_sha256": f"h{first + i}"} for i in range(n)]
        one = {"frames": n, "ended": ended, "last_address_named": named or walk[-1]["next"]}
        return {"problems": [], "judge": "PASS", "result_sha256": "x", "walk": walk, "passes": [one, dict(one)]}

    def test_from_its_first_address_on(self) -> None:
        # a chain of three runs from 0x100: 0x100..0x13f, 0x13f..0x17e, 0x17e..0x182, then an address outside
        three = (self.made_up(0x100, 64), self.made_up(0x13F, 64), self.made_up(0x17E, 5, chain.LEFT, "0x00020000"))
        missed = "run02 left the envelope, but no run of the chain walked the known frame(s) "
        for name, frames, state, why in (
                ("nothing known anywhere", [], "complete", None),
                ("known frames below its first address only", [0x10, 0xFF], "complete", None),
                ("one at its first address, walked", [0x100], "complete", None),
                ("one below and two walked", [0xFF, 0x13F, 0x182], "complete", None),
                ("one at or above the first address not walked", [0x10, 0x100, 0x183], "halted", "0x00000183"),
                ("the last address of the envelope, not walked", [0x1FFFF], "halted", "0x0001ffff"),
                ("above the envelope", [0x20000, 0x00400100], "complete", None)):
            with self.subTest(name):
                a = self.assess(0x100, three, {"frames": {h(f): {} for f in frames}})
                self.assertEqual((a["state"], a.get("why")), (state, [missed + why] if why else None))
        # a known frame at or above the chain's first address and below the start of its last run, which the first run
        # went past (its judge would have failed it; this is the chain's own count, whatever the judges said)
        past = copy(three); del past[0]["walk"][0x10]; past[0]["passes"] = [dict(p, frames=63) for p in past[0]["passes"]]
        a = self.assess(0x100, past, {"frames": {h(0x110): {}}})
        self.assertEqual((a["state"], a["why"]), ("halted", [missed + "0x00000110"]))
        # the same three runs as the runs of a chain that began one address lower: that address is asked for
        a = self.assess(0xFF, three, {"frames": {h(0xFF): {}}})
        self.assertEqual((a["state"], a["why"]), ("halted", [missed + "0x000000ff"]))

    def test_a_chain_that_begins_at_the_bottom_of_its_envelope_is_asked_what_it_always_was(self) -> None:
        three = (self.made_up(0, 64), self.made_up(63, 64), self.made_up(126, 5, chain.LEFT, "0x00020000"))
        self.assertEqual(self.assess(0, three, {"frames": {h(5): {}, h(0x80): {}}})["state"], "complete")
        for frames, missed in (([5, 0x90], "0x00000090"), ([0, 0x83], "0x00000083"), ([0xB98, 0xB99, 0xB9A], "0x00000b98, 0x00000b99, 0x00000b9a")):
            a = self.assess(0, three, {"frames": {h(f): {} for f in frames}})
            self.assertEqual((a["state"], a["why"]), ("halted", [f"run02 left the envelope, but no run of the chain walked the known frame(s) {missed}"]))
        for stage in ("s1b2", "s1b3"):                       # the two chains there were: their sets begin where their envelopes do
            self.assertEqual(base(stage)[chain.P_START], base(stage)[chain.P_LO], stage)

    def test_the_stored_chains_come_out_as_they_did(self) -> None:
        for directory, stage, state, runs in (("s1b2_17A6_2026-11-15", "s1b2", "halted", 31), ("s1b3_17A6_2026-11-17", "s1b3", "complete", 62)):
            with self.subTest(stage):
                d = ROOT / "evidence" / directory
                kept = d / f"expected_{stage}.json"
                block = [int(w, 16) for w in json.loads(kept.read_text())["params"]]
                a = chain.assess(d, block, KNOWN, chain.BOUNDS[stage], stage)
                self.assertEqual((a["state"], len(a["runs"])), (state, runs))
                self.assertEqual(chain.brief(a), json.loads((d / "chain.json").read_text()))


class TheChainOverBlockType1(unittest.TestCase):
    def test_three_rows_are_walked_to_the_address_named_above_the_envelope(self) -> None:
        (named, places, _, _), root, seen, a, _ = the()
        self.assertEqual((a["state"], a["named_after_the_last_frame"]), ("complete", h(ABOVE)))
        self.assertEqual(row_tests.walked(a), named)
        self.assertEqual(len(named), FRAMES)
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on"] * (len(a["runs"]) - 1) + ["complete"])
        self.assertEqual([(k, start) for k, start, _ in seen], [(k, int(r["start"], 16)) for k, r in enumerate(a["runs"])])
        self.assertEqual((seen[0][1], a["runs"][0]["start"]), (B, h(B)))
        self.assertTrue(all(r["judge"] == "PASS" for r in a["runs"]))
        self.assertEqual(json.loads((root / "chain.json").read_text()), chain.brief(a))

    def test_no_address_is_written_but_the_reference_frame_and_addresses_of_block_type_1(self) -> None:
        _, _, seen, _, _ = the()
        for k, _, u in seen:
            streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
            written = {s[i + 1] for s in streams for i in range(len(s) - 1) if s[i] == 0x30002001}
            self.assertTrue(all(a == 0xB99 or B <= a < ABOVE for a in written), k)

    def test_the_chain_is_complete_although_no_known_frame_was_walked(self) -> None:
        _, root, _, a, rows = the()
        self.assertEqual((rows["known_frames_walked"], rows["known_frames_not_walked"]), ([], ["0x00000b98", "0x00000b99", "0x00000b9a"]))
        # the same stored runs, taken for a chain whose set begins at the bottom of the envelope: the run directories
        # are not that chain's, and it says so before it asks for anything
        from_the_bottom = base(); from_the_bottom[chain.P_START] = 0
        b = chain.assess(root, from_the_bottom, KNOWN, chain.BOUNDS[STAGE], STAGE)
        self.assertEqual(b["state"], "halted")
        self.assertIn(f"the run was started at {h(B)}; the chain plans 0x00000000 for it", b["why"][0])

    def test_the_driver_says_where_the_stored_chain_stands(self) -> None:
        _, root, _, a, _ = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b2_chain.py"), "--dir", str(root)]
        p = subprocess.run(prog + ["--stage", STAGE], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"{len(a['runs'])} run(s) stored; the chain: complete", p.stdout)
        p = subprocess.run(prog + ["--stage", "s1b3"], capture_output=True, text=True)     # taken for a chain over block type 0, it is not one
        self.assertEqual(p.returncode, 1)
        self.assertIn("the run record is of stage s1b4, not s1b3", p.stdout)
        self.assertEqual(subprocess.run(prog + ["--stage", "s1b4a"], capture_output=True).returncode, 2, "the one run's set is not a chain's")

    def test_an_end_the_walk_does_not_provide_for_halts_the_chain(self) -> None:
        for last, status in (("still at both", "0x800"),):
            with self.subTest(last):
                dev = device(ROWS, last=last, after=ABOVE)
                _, _, a = drive(dev, name="stuck")
                self.assertEqual((a["state"], a["runs"][-1]["decision"]), ("halted", "halt"))
                self.assertTrue(any(f"status {status}" in w for w in a["why"]), a["why"])
                self.assertEqual(row_tests.walked(a), dev[0][:len(row_tests.walked(a))])
                rows = s1b3_rows.summarize(a, KNOWN)
                self.assertEqual((rows["chain"]["state"], rows["end"]["reached"], rows["frames_per_row"][:2]), ("halted", False, [[1, "top", 0, 100], [1, "top", 1, 66]]))

    def test_the_bound_stops_it_where_it_stands(self) -> None:
        dev = device(ROWS, after=ABOVE)
        tmp = Path(scratch_dirs.mkdtemp(prefix="smb4_"))
        a = chain.drive(tmp / "bound", base(), KNOWN, runner(dev), 2, stage=STAGE)
        self.assertEqual((a["state"], len(a["runs"]), a["why"]), ("halted", 2, [f"the bound of 2 runs is reached; the last frame walked is {a['runs'][1]['last']}"]))


class TheSummaryOverRows(unittest.TestCase):
    def test_the_rows_of_block_type_1_as_the_device_named_them(self) -> None:
        _, _, _, _, rows = the()
        self.assertEqual((rows["chain"]["state"], rows["frames"], rows["unexpected"]), ("complete", FRAMES, []))
        self.assertEqual(rows["frames_per_row"], [[1, "top", 0, 100], [1, "top", 1, 66], [1, "bottom", 0, 90]])
        self.assertEqual([r["frames_per_column"] for r in rows["rows"]], [[[0, 70], [1, 30]], [[0, 66]], [[0, 40], [1, 50]]])
        self.assertTrue(all(r["walked_whole"] and r["ended_by"] == "the register stood still" for r in rows["rows"]))
        last = [(base_address | (len(sizes) - 1) << 7) + sizes[-1] - 1 for base_address, sizes in ROWS]
        self.assertEqual(rows["standstills"], [{"after": h(last[0]), "named": h(ROWS[1][0])}, {"after": h(last[1]), "named": h(ROWS[2][0])}, {"after": h(last[2]), "named": h(ABOVE)}])
        self.assertEqual(rows["end"], {"reached": True, "last_frame": h(last[2]), "named_after_the_last_frame": h(ABOVE), "after_a_standstill": True,
                                       "that_address": {"block_type": 2, "half": "top", "row": 0, "column": 0, "minor": 0}})

    def test_the_program_is_told_which_sets_chain_it_reads(self) -> None:
        _, root, _, _, rows = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b3_rows.py"), str(root)]
        p = subprocess.run(prog + [STAGE], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, rows), p.stderr)
        p = subprocess.run(prog, capture_output=True, text=True)             # no set named: the chain over block type 0, which these runs are not
        self.assertEqual(p.returncode, 0)
        self.assertEqual((json.loads(p.stdout)["chain"]["state"], json.loads(p.stdout)["frames"]), ("halted", 0))
        self.assertEqual(subprocess.run(prog + ["s1b4a"], capture_output=True).returncode, 2, "not a set a chain is driven with")
        for word in ("s1b4a", "anything"):                                   # nor is it one because the directory is called the same
            p = subprocess.run(prog[:-1] + [word, word], capture_output=True, text=True, cwd=root)
            self.assertEqual((p.returncode, p.stderr), (2, ""), word)
        self.assertEqual(subprocess.run(prog + [STAGE, "more"], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(prog[:-1], capture_output=True).returncode, 2)


class TheFirstRunAgainstTheStoredOne(unittest.TestCase):
    def test_the_chain_and_the_stored_run_agree(self) -> None:
        _, _, _, _, rows = the()
        v = stored_run()
        self.assertEqual((v["verdict"], len(v["walk"]), v["walk"][0]["far"]), ("PASS", 64, h(B)))
        out = first_run.against(rows, v)
        self.assertEqual(out, {"chain": "complete", "stored_run": {"verdict": "PASS", "status": "0x1"}, "disagreements": [], "addresses_of_the_stored_run": 64,
                               "of_which_in_the_chain": 64, "same_frames": 64, "same_address_named": 64, "frames_not_all_zero": 64, "distinct_contents": 64})

    def test_what_does_not_agree_is_listed(self) -> None:
        _, _, _, _, rows = the()
        v = stored_run()
        def said(rows2=None, v2=None) -> list[str]:
            return first_run.against(rows if rows2 is None else rows2, v if v2 is None else v2)["disagreements"]
        r = copy(rows); r["addresses"][7]["frame_sha256"] = "7" * 64
        self.assertEqual(said(r), [f"the frame at {h(B + 7)}: the chain has 777777777777…, the stored run {v['walk'][7]['frame_sha256'][:12]}…"])
        r = copy(rows); r["addresses"][9]["next"] = h(B + 0x80)
        self.assertEqual(said(r), [f"after {h(B + 9)} the chain was told {h(B + 0x80)}, the stored run {h(B + 10)}"])
        r = copy(rows); r["addresses"][9]["stood_still"] = True
        self.assertEqual(said(r), [f"at {h(B + 9)} the register stood still in one of the two and not in the other"])
        w = copy(v); w["walk"][9]["stood_still"] = True
        self.assertEqual(said(v2=w), [f"at {h(B + 9)} the register stood still in one of the two and not in the other"])
        r = copy(rows); del r["addresses"][20]
        self.assertEqual(said(r), [f"1 address(es) of the stored run are not in the chain's list; the first is {h(B + 20)}",
                                   f"between {h(B)} and {h(B + 63)} the chain lists 63 address(es), the stored run 64, or not in the same order"])
        w = copy(v); del w["walk"][20]                       # the chain has an address there that the stored run did not walk
        self.assertEqual(said(v2=w), [f"between {h(B)} and {h(B + 63)} the chain lists 64 address(es), the stored run 63, or not in the same order"])
        r = copy(rows); r["addresses"][4], r["addresses"][5] = r["addresses"][5], r["addresses"][4]
        self.assertEqual(said(r), [f"between {h(B)} and {h(B + 63)} the chain lists 64 address(es), the stored run 64, or not in the same order"])
        w = copy(v); w["verdict"] = "FAIL"
        self.assertEqual(said(v2=w), ["the stored run is not one its judge passed"])
        self.assertEqual(said(v2={"verdict": "PASS", "walk": []}), ["the stored run walked nothing"])
        self.assertEqual(first_run.against({}, v)["of_which_in_the_chain"], 0)
        self.assertEqual(len(first_run.against({}, v)["disagreements"]), 2)

    def test_frames_that_are_all_alike_are_said_to_be(self) -> None:
        _, _, _, _, rows = the()
        v = stored_run()
        zero = first_run.ALL_ZERO
        r = copy(rows); [s.update(frame_sha256=zero) for s in r["addresses"]]
        w = copy(v); [s.update(frame_sha256=zero) for s in w["walk"]]
        out = first_run.against(r, w)
        self.assertEqual((out["disagreements"], out["same_frames"], out["frames_not_all_zero"], out["distinct_contents"]), ([], 64, 0, 1))
        self.assertIn("says nothing about which frame either read", out["note_on_content"])
        w["walk"][3]["frame_sha256"] = r["addresses"][3]["frame_sha256"] = "3" * 64
        out = first_run.against(r, w)
        self.assertEqual((out["frames_not_all_zero"], out["distinct_contents"], "note_on_content" in out), (1, 2, False))

    def test_through_the_command_line(self) -> None:
        _, root, _, _, rows = the()
        v = stored_run()
        tmp = Path(scratch_dirs.mkdtemp(prefix="smb4f_"))
        (tmp / "rows.json").write_text(json.dumps(rows)); (tmp / "verdict.json").write_text(json.dumps(v))
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b4_first.py")]
        p = subprocess.run(prog + [str(tmp / "rows.json"), str(tmp / "verdict.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, first_run.against(rows, v)))
        bad = copy(v); bad["walk"][3]["frame_sha256"] = "0" * 64
        (tmp / "bad.json").write_text(json.dumps(bad))
        self.assertEqual(subprocess.run(prog + [str(tmp / "rows.json"), str(tmp / "bad.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(prog + [str(tmp / "rows.json")], capture_output=True).returncode, 2)

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1b4_first.py").read_text()
        tree = ast.parse(text)
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 3, 12, 16}, set())
        for word in ("prjxray", "part.json", "frame_count", "grade_s1b", "1ba", "400000", "800000"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib", "s1b3_top"}, set())


class TheGraderGivenBlockType1(unittest.TestCase):
    def test_a_made_up_database_that_has_what_the_chain_found(self) -> None:
        _, _, _, _, rows = the()
        g = grade_s1b3.grade(rows, database())
        self.assertEqual((g["chain"], g["differs"]), ("complete", []))
        self.assertEqual(g["agrees"], ["nothing differs within any of the 3 row(s) walked", "the rows walked are the database's rows of block type 1, in its order",
                                       f"frames of block type 1: the chain found {FRAMES}, the database's columns add up to {FRAMES}"])
        self.assertEqual(len(g["rows"]), 3)
        self.assertTrue(any("the database lists no block type after this one" in n and h(ABOVE) in n for n in g["not_compared"]), g["not_compared"])
        self.assertTrue(any("the register stood still after the last frame of 3 row(s)" in n for n in g["not_compared"]))
        self.assertEqual([[c["column"], c["walked"], c["database"]] for c in g["rows"][0]["columns"]], [[0, 70, 70], [1, 30, 30]])

    def test_the_columns_of_block_type_0_in_the_same_rows_are_not_what_it_is_held_against(self) -> None:
        _, _, _, _, rows = the()
        other = database(); other["global_clock_regions"]["top"]["rows"]["0"]["configuration_buses"]["CLB_IO_CLK"]["configuration_columns"]["0"]["frame_count"] = 70
        self.assertEqual(grade_s1b3.grade(rows, other)["differs"], [])

    def test_what_differs_is_listed(self) -> None:
        _, _, _, _, rows = the()
        longer = database([(B, [70, 31])] + ROWS[1:])
        g = grade_s1b3.grade(rows, longer)
        self.assertTrue(any("column 1: the walk found 30 frame(s), the database says 31" in d for d in g["differs"]), g["differs"])
        self.assertTrue(any(f"the chain found {FRAMES}, the database's columns add up to {FRAMES + 1}" in d for d in g["differs"]))
        fewer = grade_s1b3.grade(rows, database(ROWS[:2]))
        self.assertTrue(any(d.startswith("the rows walked are ") for d in fewer["differs"]), fewer["differs"])
        more = grade_s1b3.grade(rows, database(ROWS + [(B | BOTTOM | 1 << 17, [12])]))
        self.assertTrue(any(d.startswith("the rows walked are ") for d in more["differs"]), more["differs"])

    def test_a_chain_that_halted_is_graded_only_as_far_as_it_went(self) -> None:
        dev = device(ROWS, last="still at both", after=ABOVE)
        _, _, a = drive(dev, name="stuck for the grader")
        g = grade_s1b3.grade(copy(s1b3_rows.summarize(a, KNOWN)), database())
        self.assertEqual((g["chain"], g["differs"]), ("halted", []))
        self.assertTrue(any("the chain did not leave the envelope" in n for n in g["not_compared"]))

    def test_through_the_command_line_with_a_made_up_database(self) -> None:
        _, _, _, _, rows = the()
        tmp = Path(scratch_dirs.mkdtemp(prefix="smb4g_"))
        (tmp / "rows.json").write_text(json.dumps(rows)); (tmp / "db.json").write_text(json.dumps(database()))
        prog = [sys.executable, "-B", str(ROOT / "host" / "grade_s1b3.py")]
        p = subprocess.run(prog + [str(tmp / "rows.json"), str(tmp / "db.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, grade_s1b3.grade(rows, database())))
        (tmp / "db2.json").write_text(json.dumps(database([(B, [70, 31])] + ROWS[1:])))
        self.assertEqual(subprocess.run(prog + [str(tmp / "rows.json"), str(tmp / "db2.json")], capture_output=True).returncode, 1)


if __name__ == "__main__":
    unittest.main()

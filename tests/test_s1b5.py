"""S1b.5: the chain over block type 2 (docs/s1b_plan.md, section 62) — the set s1b5 and its bound, the chain driver
with it on the twin behind the pretended board, and the three programs that are run over the chain afterwards: the
summary over rows, the comparison with a stored run, the listing of status bits. None of them was changed for this
step, and no rule of the chain, of a judge or of the prober.

The device here is made up: rows of block type 2 whose columns have one frame, as the board showed, in numbers no
part has; and variants for each ending the proposal names beforehand. Nothing is graded and no database is read:
there is none for this block type. No number of any real part is in this file but the one address the board named
after block type 1."""
from __future__ import annotations

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
import s1a_run  # noqa: E402
import s1b2_chain as chain  # noqa: E402
import s1b3_rows  # noqa: E402
import s1b4_first as first_run  # noqa: E402
import status_seen  # noqa: E402
import test_s1a_run as fake  # noqa: E402
import test_s1b2 as row_tests  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2 import KNOWN, once  # noqa: E402
from test_s1b3 import device  # noqa: E402

STAGE = "s1b5"
B = 0x01000000                                       # named by the board after the last frame of block type 1
BOTTOM = 0x00400000
REF = 0x00000B99
ABOVE = 0x01800000                                   # the first address above the envelope
# made up: two rows of 45 and 40 columns of one frame — rows shorter than a pass — and one of two longer columns; no
# pass of 64 frames of this chain meets two of their ends. (The twin's table of successors holds TABLE entries, and a
# column of one frame takes one: that is what keeps these devices small. The pretended board refuses a longer table.)
ROWS = [(B, [1] * 45), (B | BOTTOM, [1] * 40), (B | BOTTOM | 1 << 17, [30, 25])]
TABLE, SHOWN = 96, 32                                # prober/twin_hal.c: what it reads of SM_SUCC and SM_SHOWS, and no more
FRAMES = sum(sum(sizes) for _, sizes in ROWS)
# made up: three rows of 20 columns — the first pass meets two ends
SHORT_ROWS = [(B, [1] * 20), (B | BOTTOM, [1] * 20), (B | BOTTOM | 1 << 17, [1] * 20)]
# made up: the first run ends, at the limit, on the last frame of a row; the row after it is shorter than a pass
SEAM_ROWS = [(B, [1] * 20 + [44]), (B | BOTTOM, [1] * 30), (B | BOTTOM | 1 << 17, [1] * 10)]


def h(a: int) -> str:
    return f"{a:#010x}"


def copy(x):
    return json.loads(json.dumps(x))


def base(stage: str = STAGE) -> list[int]:
    row_tests.the_set()                              # builds the image and writes the sets, once
    return [int(w, 16) for w in json.loads(s1a_run.STAGES[stage]["expected"].read_text())["params"]]


def runner(dev, seen: list | None = None, stage: str = STAGE):
    _, places, succ, shows = dev
    pl = s1a_run.PL.read_bytes()
    model = frames_for(places)

    def run(start: int, out: Path, came_from: str) -> None:
        k = int(out.name[3:])
        exp = s1a_run.with_start(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), start, came_from)
        u = fake.FakeUBoot("", far_rule="skip", succ=succ, shows=shows, frames=model)
        out.mkdir()
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s{k:07d}.bin", stage)
        if seen is not None:
            seen.append((k, start, u))
    return run


def drive(dev, name: str = "chain", bound: int | None = None):
    tmp, seen = Path(scratch_dirs.mkdtemp(prefix="smb5_")), []
    a = chain.drive(tmp / name, base(), KNOWN, runner(dev, seen), chain.BOUNDS[STAGE] if bound is None else bound, stage=STAGE)
    return tmp / name, seen, a


def the():
    """(the device, the directory, what the pretended boards saw, the assessment, the summary over rows)"""
    def make():
        dev = device(ROWS, after=ABOVE)
        root, seen, a = drive(dev)
        return dev, root, seen, a, copy(s1b3_rows.summarize(a, KNOWN))
    return once("s1b5 / three rows", make)


def halted(name: str, dev):
    return once(f"s1b5 / {name}", lambda: drive(dev, name=name.replace(" ", "_")))


def stored_run() -> dict:
    """One run of S1b.5a's set on the same made-up device: what the chain's first run is held against."""
    def make() -> dict:
        _, places, succ, shows = the()[0]
        exp = json.loads(s1a_run.STAGES["s1b5a"]["expected"].read_text())
        pl = s1a_run.PL.read_bytes()
        out = Path(scratch_dirs.mkdtemp(prefix="smb5a_")) / "run"
        out.mkdir()
        u = fake.FakeUBoot("", far_rule="skip", succ=succ, shows=shows, frames=frames_for(places))
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", "s1b5a")
        return json.loads((out / "verdict.json").read_text())
    return copy(once("s1b5 / the stored run", make))


def after_the_last_read_in_block_type_2(run_dir: Path) -> list[str]:
    kinds = [r["kind"] for r in json.loads((run_dir / "verdict.json").read_text())["records"]]
    return kinds[max(i for i, k in enumerate(kinds) if k == "target") + 1:]


class TheSet(unittest.TestCase):
    def test_it_is_the_set_of_the_one_run_word_for_word_with_the_start_given_at_run_time(self) -> None:
        self.assertEqual(base(), base("s1b5a"))
        self.assertEqual((base()[3], base()[4], base()[10], base()[12], base()[16]), (0, ABOVE - 1, 1, 64, B))
        self.assertIs(s1a_run.STAGES[STAGE]["judge"], s1a_run.STAGES["s1b4"]["judge"])
        self.assertEqual((STAGE in s1a_run.STARTS_AT_RUN_TIME, "s1b5a" in s1a_run.STARTS_AT_RUN_TIME, chain.BOUNDS[STAGE]), (True, False, 12))
        exp = s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), B | BOTTOM | 0x380, "a test")
        self.assertEqual((exp["params"][16], exp["chain"]["start"]), ("01400380", "0x01400380"))
        with self.assertRaises(ValueError):                 # nothing above block type 2 can be started at
            s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), ABOVE, "a test")
        both = [json.loads(s1a_run.STAGES[s]["expected"].read_text()) for s in (STAGE, "s1b5a")]
        self.assertEqual(both[0]["image_sha256"], both[1]["image_sha256"])
        self.assertEqual(both[0]["image_sha256"], "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")

    def test_the_chain_begins_where_the_board_pointed_and_where_the_stored_run_began(self) -> None:
        rows = json.loads((ROOT / "evidence" / "s1b4_17A6_2026-11-18" / "rows.json").read_text())
        self.assertEqual(h(base()[chain.P_START]), rows["end"]["named_after_the_last_frame"])
        stored = json.loads((ROOT / "evidence" / "s1b5a_17A6_2026-11-19" / "run" / "verdict.json").read_text())
        self.assertEqual((stored["verdict"], stored["walk"][0]["far"]), ("PASS", h(base()[chain.P_START])), "its first run reads that run's addresses again")
        self.assertTrue(all(int(a, 16) < base()[chain.P_START] for a in KNOWN["frames"]), "every frame with a known answer lies below it: the rule asks for none")

    def test_the_dry_run_of_a_run_of_the_chain(self) -> None:
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE, "--dry-run"]
        r = subprocess.run(prog + ["--start", "1400380"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        for line in ("mw.l 10100010 017fffff 1", "mw.l 10100014 00000b99 1", "mw.l 10100028 00000001 1", "mw.l 10100040 01400380 1", "mw.l 1010003c 00000200 1"):
            self.assertIn(line, r.stdout)
        r = subprocess.run(prog + ["--start", "1800000"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.startswith("REFUSED: ")), (2, True), r.stdout)
        one = subprocess.run(prog, capture_output=True, text=True).stdout
        other = subprocess.run(prog[:4] + ["s1b5a", "--dry-run"], capture_output=True, text=True).stdout
        self.assertEqual([line for line in one.splitlines() if "mw.l 101000" in line], [line for line in other.splitlines() if "mw.l 101000" in line],
                         "without a start it is the one run's set, word for word")


class TheChainOverBlockType2(unittest.TestCase):
    def test_the_devices_made_up_here_fit_the_twins_tables(self) -> None:
        text = (ROOT / "prober" / "twin_hal.c").read_text()
        self.assertIn(f"while (*s && n_succ < {TABLE})", text)
        self.assertIn(f"while (*s && n_shows < {SHOWN})", text)
        for rows in (ROWS, SHORT_ROWS, SEAM_ROWS):
            _, _, succ, shows = device(rows, after=ABOVE)
            self.assertTrue(len(succ) + 2 <= TABLE and len(shows) <= SHOWN, rows)
        many = device([(B, [1] * (TABLE + 2))], after=ABOVE)                  # one entry too many: refused, not walked as something else
        with self.assertRaises(AssertionError):
            runner(many)(B, Path(scratch_dirs.mkdtemp(prefix="smb5_")) / "run00", "a test")

    def test_rows_of_one_frame_columns_are_walked_to_the_address_named_above_the_envelope(self) -> None:
        (named, _, _, _), root, seen, a, _ = the()
        self.assertEqual((a["state"], a["named_after_the_last_frame"]), ("complete", h(ABOVE)))
        self.assertEqual(row_tests.walked(a), named)
        self.assertEqual((len(named), len(a["runs"])), (FRAMES, 3))
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on", "go on", "complete"])
        self.assertEqual([(k, start) for k, start, _ in seen], [(k, int(r["start"], 16)) for k, r in enumerate(a["runs"])])
        self.assertEqual([r["start"] for r in a["runs"]], [h(named[0]), h(named[63]), h(named[126])], "each run begins at the last frame of the one before")
        self.assertTrue(all(r["judge"] == "PASS" for r in a["runs"]))
        self.assertEqual(json.loads((root / "chain.json").read_text()), chain.brief(a))
        self.assertEqual(after_the_last_read_in_block_type_2(root / "run02"), ["final"], "the run that leaves the envelope is walked to its end")

    def test_no_address_is_written_but_the_reference_frame_and_addresses_the_device_named_in_block_type_2(self) -> None:
        (named, _, _, _), _, seen, _, _ = the()
        for k, _, u in seen:
            streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
            written = {s[i + 1] for s in streams for i in range(len(s) - 1) if s[i] == 0x30002001}
            self.assertIn(REF, written)
            self.assertTrue(written - {REF} <= set(named), k)
            self.assertTrue(all(B <= x < ABOVE for x in written - {REF}), k)

    def test_the_chain_is_complete_although_no_known_frame_was_walked(self) -> None:
        _, root, _, _, rows = the()
        self.assertEqual((rows["known_frames_walked"], rows["known_frames_not_walked"]), ([], ["0x00000b98", "0x00000b99", "0x00000b9a"]))
        # the same stored runs taken for the chain over block type 1: they are not that chain's
        b = chain.assess(root, base("s1b4"), KNOWN, chain.BOUNDS["s1b4"], "s1b4")
        self.assertEqual(b["state"], "halted")
        self.assertIn("the run record is of stage s1b5, not s1b4", b["why"][0])

    def test_the_driver_says_where_the_stored_chain_stands(self) -> None:
        _, root, _, a, _ = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b2_chain.py"), "--dir", str(root)]
        p = subprocess.run(prog + ["--stage", STAGE], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("3 run(s) stored; the chain: complete", p.stdout)
        p = subprocess.run(prog + ["--stage", "s1b4"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("the run record is of stage s1b5, not s1b4", p.stdout)
        self.assertEqual(subprocess.run(prog + ["--stage", "s1b5a"], capture_output=True).returncode, 2, "the one run's set is not a chain's")

    def test_the_bound_stops_it_where_it_stands(self) -> None:
        _, _, a = drive(device(ROWS, after=ABOVE), name="bound", bound=2)
        self.assertEqual((a["state"], len(a["runs"]), a["why"]), ("halted", 2, [f"the bound of 2 runs is reached; the last frame walked is {a['runs'][1]['last']}"]))


class TheEndingsSaidBeforehand(unittest.TestCase):
    """Section 62, endings 2 and 3: each halts the chain, is stored, and is summarised as a chain that halted."""

    def test_a_register_that_stands_still_for_good_after_the_last_frame(self) -> None:
        dev = device(ROWS, last="still at both", after=ABOVE)
        root, _, a = halted("stuck at the end", dev)
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on", "go on", "halt"]))
        self.assertTrue(any("status 0x800" in w for w in a["why"]), a["why"])
        self.assertEqual(row_tests.walked(a), dev[0][:127], "what the two runs before it walked stands")
        self.assertEqual(after_the_last_read_in_block_type_2(root / "run02"), [], "no reference read after it (section 60)")
        rows = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual((rows["chain"]["state"], rows["end"]["reached"], rows["frames_per_row"][:2]), ("halted", False, [[2, "top", 0, 45], [2, "bottom", 0, 40]]))

    def test_an_address_below_block_type_2_named_after_the_last_frame(self) -> None:
        for name, back in (("back to block type 1", 0x00800000), ("back to address 0", 0)):
            with self.subTest(name):
                named, places, succ, shows = device(ROWS, last="no place", after=back)
                root, seen, a = halted(name, (named, places + [back, back + 1], succ, shows))
                self.assertEqual((a["state"], len(a["runs"]), a["runs"][-1]["decision"]), ("halted", 3, "halt"))
                self.assertTrue(any("status 0x800" in w for w in a["why"]), a["why"])
                v = json.loads((root / "run02" / "verdict.json").read_text())
                self.assertEqual(v["passes"][0]["last_address_named"], h(back), "recorded as named")
                for _, _, u in seen:                         # and not followed
                    streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
                    written = {s[i + 1] for s in streams for i in range(len(s) - 1) if s[i] == 0x30002001}
                    self.assertTrue(all(x == REF or B <= x < ABOVE for x in written))
                self.assertEqual(after_the_last_read_in_block_type_2(root / "run02"), [])

    def test_two_row_ends_in_one_pass(self) -> None:
        root, seen, a = halted("short rows", device(SHORT_ROWS, after=ABOVE))
        self.assertEqual((a["state"], len(a["runs"]), a["runs"][0]["decision"]), ("halted", 1, "halt"))
        self.assertTrue(any("status 0x900" in w for w in a["why"]), a["why"])
        v = json.loads((root / "run00" / "verdict.json").read_text())
        self.assertEqual((v["header"]["status"], v["frames_walked"]), ("0x900", 40), "stopped at the second end, the frame there read")
        self.assertEqual(after_the_last_read_in_block_type_2(root / "run00"), [])
        rows = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual((rows["chain"]["state"], rows["frames"], rows["end"]["reached"]), ("halted", 0, False), "a run that did not pass adds nothing to the list")

    def test_a_run_that_begins_on_the_last_frame_of_a_row_and_meets_the_end_of_the_next(self) -> None:
        """A halt of the walk's making, not of the device's: every row of this device ends as the rows on the board
        did. The first run ends at the limit on the last frame of a row; the second begins there, crosses that end,
        and comes to the end of a row shorter than a pass."""
        dev = device(SEAM_ROWS, after=ABOVE)
        root, _, a = halted("a seam on a row end", dev)
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on", "halt"]))
        self.assertEqual((a["runs"][0]["frames"], a["runs"][0]["last"], a["runs"][0]["named_after_the_last"]), (64, h(dev[0][63]), h(B | BOTTOM)))
        self.assertTrue(a["runs"][0]["walk"][-1].get("stood_still"))
        self.assertTrue(any("status 0x900" in w for w in a["why"]), a["why"])
        self.assertEqual(json.loads((root / "run01" / "verdict.json").read_text())["frames_walked"], 31)
        rows = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual((rows["chain"]["state"], rows["frames_per_row"], rows["rows"][0]["walked_whole"]), ("halted", [[2, "top", 0, 64]], True))


class WhatIsMadeOfTheChain(unittest.TestCase):
    """The three programs run over the chain on the board, here over the twin's: none was changed for this step."""

    def test_the_rows_of_block_type_2_as_the_device_named_them(self) -> None:
        _, _, _, _, rows = the()
        self.assertEqual((rows["chain"]["state"], rows["frames"], rows["unexpected"]), ("complete", FRAMES, []))
        self.assertEqual(rows["frames_per_row"], [[2, "top", 0, 45], [2, "bottom", 0, 40], [2, "bottom", 1, 55]])
        self.assertEqual([r["frames_per_column"] for r in rows["rows"]], [[[c, 1] for c in range(45)], [[c, 1] for c in range(40)], [[0, 30], [1, 25]]])
        self.assertTrue(all(r["walked_whole"] and r["ended_by"] == "the register stood still" for r in rows["rows"]))
        last = [(base_address | (len(sizes) - 1) << 7) + sizes[-1] - 1 for base_address, sizes in ROWS]
        self.assertEqual(rows["standstills"], [{"after": h(last[0]), "named": h(ROWS[1][0])}, {"after": h(last[1]), "named": h(ROWS[2][0])}, {"after": h(last[2]), "named": h(ABOVE)}])
        self.assertEqual(rows["end"], {"reached": True, "last_frame": h(last[2]), "named_after_the_last_frame": h(ABOVE), "after_a_standstill": True,
                                       "that_address": {"block_type": 3, "half": "top", "row": 0, "column": 0, "minor": 0}})

    def test_the_summary_through_the_command_line(self) -> None:
        _, root, _, _, rows = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b3_rows.py"), str(root)]
        p = subprocess.run(prog + [STAGE], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, rows), p.stderr)
        p = subprocess.run(prog + ["s1b4"], capture_output=True, text=True)     # taken for the chain over block type 1, it is not one
        self.assertEqual((json.loads(p.stdout)["chain"]["state"], json.loads(p.stdout)["frames"]), ("halted", 0))
        self.assertEqual(subprocess.run(prog + ["s1b5a"], capture_output=True).returncode, 2, "not a set a chain is driven with")

    def test_the_first_run_against_the_stored_run(self) -> None:
        _, _, _, _, rows = the()
        v = stored_run()
        self.assertEqual((v["verdict"], len(v["walk"]), v["walk"][0]["far"], len(v["standstills"])), ("PASS", 64, h(B), 1))
        out = first_run.against(rows, v)
        self.assertEqual(out, {"chain": "complete", "stored_run": {"verdict": "PASS", "status": "0x1"}, "disagreements": [], "addresses_of_the_stored_run": 64,
                               "of_which_in_the_chain": 64, "same_frames": 64, "same_address_named": 64, "frames_not_all_zero": 64, "distinct_contents": 64})
        end = h(B | 44 << 7)                                 # the last frame of the made-up top row: a standstill in both
        w = copy(v); del next(s for s in w["walk"] if s["far"] == end)["stood_still"]
        self.assertEqual(first_run.against(rows, w)["disagreements"], [f"at {end} the register stood still in one of the two and not in the other"])
        r = copy(rows); r["addresses"][50]["next"] = h(ABOVE)
        self.assertEqual(len(first_run.against(r, v)["disagreements"]), 1)

    def test_frames_that_are_all_zero_are_said_to_say_nothing(self) -> None:
        _, _, _, _, rows = the()
        v = stored_run()
        r = copy(rows); [s.update(frame_sha256=first_run.ALL_ZERO) for s in r["addresses"]]
        w = copy(v); [s.update(frame_sha256=first_run.ALL_ZERO) for s in w["walk"]]
        out = first_run.against(r, w)
        self.assertEqual((out["disagreements"], out["frames_not_all_zero"], out["distinct_contents"]), ([], 0, 1))
        self.assertIn("says nothing about which frame either read", out["note_on_content"])

    def test_the_listing_of_status_bits_over_the_runs_of_a_chain(self) -> None:
        _, root, _, a, _ = the()
        files = status_seen.verdicts(root)
        self.assertEqual([f.parent.name for f in files], ["run00", "run01", "run02"])
        self.assertTrue(all(status_seen.seen(json.loads(f.read_text()))["bits"] == [] for f in files), "the twin shows nothing but the usual")
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "status_seen.py"), str(root)], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["runs"], json.loads(p.stdout)["bits"]), (0, 3, []))
        root2, _, _ = halted("stuck at the end", device(ROWS, last="still at both", after=ABOVE))    # a run that did not pass is listed too
        self.assertEqual(len(status_seen.verdicts(root2)), 3)


if __name__ == "__main__":
    unittest.main()

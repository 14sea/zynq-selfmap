"""S1b.3: the chain over block type 0 (docs/s1b_plan.md, section 38) — the chain driver with the set s1b3 on the twin
behind the pretended board, the summary over rows, the comparison of the first row with a stored one, and the grader.
The devices here are made up: three rows whose columns have lengths no part has, with ends of rows of the kind the
board showed, and variants of them. No database is read; the grader is given a made-up one."""
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
import s1b3_top  # noqa: E402
import test_s1a_run as fake  # noqa: E402
import test_s1b2 as row_tests  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2 import KNOWN, SIZES, once  # noqa: E402

STAGE = "s1b3"
BOTTOM = 0x00400000
TOP_0, BOTTOM_0, BOTTOM_1 = (0, SIZES), (BOTTOM, [30, 25, 15]), (BOTTOM | 1 << 17, [40, 26])
ROWS = [TOP_0, BOTTOM_0, BOTTOM_1]                   # 128, 70 and 66 frames: no pass of 64 frames meets two ends
BEYOND = 0x00800000                                  # the first address above the envelope: block type 1
HIDDEN = 0x7F000000                                  # places without an address of their own (the twin's SM_SHOWS)


def h(a: int) -> str:
    return f"{a:#010x}"


def device(rows=ROWS, last="two places", ends: dict[int, str] | None = None, after: int = BEYOND):
    """A made-up device: (the addresses the device names, in order; every place with a frame; successors; what the
    register shows at places without an address). After the last frame of a row: two places without an address, the
    register still at the first ("two places" — what the board showed); or the next address at once ("no place"); or
    two places with the register still at both ("still at both"). `ends[k]` chooses for row k; `last` for the last."""
    named, places, succ, shows = [], [], {}, {}
    for k, (base, sizes) in enumerate(rows):
        for c, n in enumerate(sizes):
            named += [base | c << 7 | m for m in range(n)]
            if c + 1 < len(sizes):
                succ[(base | c << 7) + n - 1] = base | (c + 1) << 7
        end, nxt = named[-1], rows[k + 1][0] if k + 1 < len(rows) else after
        kind = (ends or {}).get(k, last if k + 1 == len(rows) else "two places")
        h1, h2 = HIDDEN + 2 * k + 1, HIDDEN + 2 * k + 2
        if kind == "no place":
            succ[end] = nxt
        else:
            succ.update({end: h1, h1: h2, h2: nxt}); places += [h1, h2]
            shows.update({h1: end, h2: nxt if kind == "two places" else end})
    return named, named + places, succ, shows


def base() -> list[int]:
    row_tests.the_set()                              # builds the image and writes the sets, once
    return [int(w, 16) for w in json.loads(s1a_run.STAGES[STAGE]["expected"].read_text())["params"]]


def runner(dev, seen: list | None = None, per_run: dict | None = None):
    _, places, succ, shows = dev
    pl = s1a_run.PL.read_bytes()
    model = frames_for(places)

    def run(start: int, out: Path, came_from: str) -> None:
        k = int(out.name[3:])
        change = (per_run or {}).get(k, {})
        exp = s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), start, came_from)
        u = fake.FakeUBoot(change.get("fault", ""), far_rule="skip", succ=change.get("succ", succ), shows=change.get("shows", shows),
                           frames={**model, **change.get("frames", {})})
        out.mkdir()
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s{k:07d}.bin", STAGE)
        if seen is not None:
            seen.append((k, start, u))
    return run


def drive(dev, name: str = "chain", **kw):
    tmp, seen = Path(scratch_dirs.mkdtemp(prefix="smb3_")), []
    a = chain.drive(tmp / name, base(), KNOWN, runner(dev, seen, kw.pop("per_run", None)), chain.BOUNDS[STAGE], stage=STAGE, **kw)
    return tmp / name, seen, a


def the(name: str = "three rows", **kw):
    """(the device, the directory, what the pretended boards saw, the assessment, the summary over rows)"""
    def make():
        dev = device(**kw)
        root, seen, a = drive(dev)
        return dev, root, seen, a, s1b3_rows.summarize(a, KNOWN)
    return once(f"s1b3 / {name}", make)


def database(rows=ROWS, more_after: bool = True) -> dict:
    """A part description of the database's shape for these rows, and one row of the next block type."""
    out: dict = {"global_clock_regions": {}}
    for base_address, sizes in rows:
        half, k = ("bottom" if base_address & BOTTOM else "top"), (base_address >> 17) & 0x1F
        buses = out["global_clock_regions"].setdefault(half, {"rows": {}})["rows"].setdefault(str(k), {"configuration_buses": {}})["configuration_buses"]
        buses["CLB_IO_CLK"] = {"configuration_columns": {str(c): {"frame_count": n} for c, n in enumerate(sizes)}}
        if more_after and half == "top" and k == 0:
            buses["BLOCK_RAM"] = {"configuration_columns": {"0": {"frame_count": 9}}}
    return out


def copy(x):
    return json.loads(json.dumps(x))


class TheSetAndTheDriver(unittest.TestCase):
    def test_the_set_is_the_crossing_walks_with_the_start_given_at_run_time(self) -> None:
        p = base()
        a = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b3a"]["expected"].read_text())["params"]]
        self.assertEqual([k for k in range(32) if p[k] != a[k]], [16], "the start, and nothing else")
        self.assertEqual((p[2], p[3], p[4], p[5], p[7], p[10], p[12], p[13], p[15], p[16]), (4, 0, 0x007FFFFF, 0xB99, 2, 1, 64, 16, 2 << 8, 0))
        self.assertEqual((s1a_run.STAGES[STAGE]["judge"], STAGE in s1a_run.STARTS_AT_RUN_TIME), (s1a_run.STAGES["s1b2"]["judge"], True))
        exp = s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), 0x00400015, "a test")
        self.assertEqual((exp["params"][16], exp["chain"]["start"]), ("00400015", "0x00400015"))
        with self.assertRaises(ValueError):                 # block type 1 is outside: no run can be started there
            s1a_run.with_start(STAGE, json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()), BEYOND, "a test")
        self.assertEqual(chain.BOUNDS, {"s1b2": 48, STAGE: 96})

    def test_the_driver_says_where_a_stored_chain_stands_for_either_set(self) -> None:
        _, root, _, a, _ = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b2_chain.py"), "--dir", str(root)]
        p = subprocess.run(prog + ["--stage", STAGE], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"{len(a['runs'])} run(s) stored; the chain: complete", p.stdout)
        p = subprocess.run(prog, capture_output=True, text=True)        # taken for a chain of the row's set, it is not one
        self.assertEqual(p.returncode, 1)
        self.assertIn("the run record is of stage s1b3, not s1b2", p.stdout)
        self.assertEqual(subprocess.run(prog + ["--stage", "s1b3a"], capture_output=True).returncode, 2, "only the two sets made for a chain")


class TheChainOverSeveralRows(unittest.TestCase):
    def test_three_rows_are_walked_to_the_address_named_after_the_last(self) -> None:
        (named, places, _, _), root, seen, a, _ = the()
        self.assertEqual((a["state"], a["named_after_the_last_frame"]), ("complete", h(BEYOND)))
        self.assertEqual(row_tests.walked(a), named, "every address the device names, in order, once — and nothing else")
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on"] * 4 + ["complete"])
        self.assertEqual([r["frames"] for r in a["runs"]], [64, 64, 64, 64, len(named) - 4 * 63])
        self.assertEqual([r["problems"] for r in a["runs"]], [[]] * 5)
        still = [s["far"] for r in a["runs"] for s in r["walk"] if s.get("stood_still")]
        self.assertEqual(still, [h(named[127]), h(named[197]), h(named[263])], "the last frame of each row, each met by one run")
        self.assertEqual(json.loads((root / "chain.json").read_text()), chain.brief(a))
        # what the boards saw: no address written that the device did not name, none at or above the next block type,
        # and nothing delivered from a place without an address
        written = set()
        for _, _, u in seen:
            streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
            written |= {s[k + 1] for s in streams for k in range(len(s) - 1) if s[k] == 0x30002001}
            self.assertEqual([line for line in u.twin_lines if line.startswith("VIOLATION")], [])
        self.assertEqual(written, set(named))
        self.assertLess(max(written), BEYOND)
        frames = frames_for(places)
        hidden = {row_tests.s1b1_judge.hashlib.sha256(b"".join(row_tests.struct.pack(">I", w) for w in frames[p])).hexdigest() for p in places if p >= HIDDEN}
        self.assertEqual(len(hidden), 6)
        for d in sorted(root.glob("run??")):
            v = json.loads((d / "verdict.json").read_text())
            self.assertEqual(hidden & {x for r in v["records"] for x in r["frame_sha256"]}, set(), d.name)

    def test_a_chain_taken_up_again_is_the_chain_run_through(self) -> None:
        dev, _, _, whole, _ = the()
        root, _, a = drive(dev, max_new=2)
        self.assertEqual((a["state"], len(a["runs"]), a["next_run"]), ("go on", 2, 2))
        b = chain.drive(root, base(), KNOWN, runner(dev), chain.BOUNDS[STAGE], stage=STAGE)
        self.assertEqual(row_tests.shape(b), row_tests.shape(whole))

    def test_a_seam_that_falls_on_the_last_frame_of_a_row(self) -> None:
        sizes = list(SIZES); sizes[5] -= 1                  # 127 frames: the second run ends with the last frame of the row
        dev = device([(0, sizes), BOTTOM_0, BOTTOM_1])
        _, _, a = drive(dev)
        self.assertEqual((a["state"], row_tests.walked(a)), ("complete", dev[0]))
        self.assertEqual((a["runs"][1]["last"], a["runs"][1]["named_after_the_last"], a["runs"][1]["ended"]), (h(dev[0][126]), h(BOTTOM), chain.LIMIT))
        self.assertEqual((a["runs"][2]["first"], a["runs"][2]["walk"][0].get("stood_still"), a["runs"][2]["walk"][1]["far"]), (h(dev[0][126]), True, h(BOTTOM)))
        s = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual((s["frames_per_row"], s["unexpected"]), ([[0, "top", 0, 127], [0, "bottom", 0, 70], [0, "bottom", 1, 66]], []))

    def test_a_seam_at_which_only_one_of_the_two_runs_stood_still_halts_the_chain(self) -> None:
        """Review of 1140ce6: the seam frame is read by two runs, and they have to agree on what the register did there
        — not only on the address named. Here the seam is the last frame of the first row; the device is one thing
        for the run that ends there and another for the run that begins there. Each run passes its judge, the frame
        and the address named are the same in both, and the chain must halt all the same."""
        sizes = list(SIZES); sizes[5] -= 1                  # 127 frames: the second run ends with the last frame of the row
        rows = [(0, sizes), BOTTOM_0, BOTTOM_1]
        still, at_once = device(rows), device(rows, ends={0: "no place"})
        last = h(still[0][126])
        for name, dev, later, first_said, then_said in (("the mark disappears", still, at_once, "stood still after the pad alone", "did not stand still"),
                                                       ("the mark appears", at_once, still, "did not stand still", "stood still after the pad alone")):
            with self.subTest(case=name):
                root, _, a = drive(dev, per_run={2: {"succ": later[2], "shows": later[3]}})
                self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on", "go on", "halt"]))
                self.assertEqual(a["why"], [f"run02: seam: at {last} the register {then_said} in this run, and {first_said} in the run before"])
                # each of the two runs, by itself, is a run that passed; they agree on the frame and on the address named
                one, two = a["runs"][1], a["runs"][2]
                self.assertEqual((one["judge"], two["judge"], one["walk"][-1]["far"], two["walk"][0]["far"]), ("PASS", "PASS", last, last))
                self.assertEqual((one["walk"][-1]["next"], two["walk"][0]["next"], one["walk"][-1]["frame_sha256"]), (h(BOTTOM), h(BOTTOM), two["walk"][0]["frame_sha256"]))
                self.assertEqual((bool(one["walk"][-1].get("stood_still")), bool(two["walk"][0].get("stood_still"))), (name == "the mark disappears", name == "the mark appears"))
                # and the summary has what the accepted runs walked: the row is not said to have ended either way by a run that was set aside
                s = s1b3_rows.summarize(a, KNOWN)
                self.assertEqual((s["chain"]["state"], s["frames"], s["end"]["reached"]), ("halted", 127, False))
                again = chain.drive(root, base(), KNOWN, runner(dev), chain.BOUNDS[STAGE], stage=STAGE)
                self.assertEqual((again["state"], len(again["runs"])), ("halted", 3), "nothing is retried")
        # where both runs stood still there, or neither did, the chain goes on (the two tests beside this one)
        self.assertEqual(drive(still)[2]["state"], "complete")
        self.assertEqual(drive(at_once)[2]["state"], "complete")

    def test_the_end_of_the_block_type_without_a_standstill(self) -> None:
        dev, _, _, a, s = the("no place at the end", last="no place")
        self.assertEqual((a["state"], a["named_after_the_last_frame"], row_tests.walked(a)), ("complete", h(BEYOND), dev[0]))
        self.assertEqual((s["rows"][-1]["ended_by"], s["rows"][-1]["walked_whole"], s["end"]["after_a_standstill"], len(s["standstills"])),
                         ("the device named an address beyond the envelope", True, False, 2))

    def test_an_end_where_the_register_stands_still_for_longer_halts_the_chain(self) -> None:
        dev, _, _, a, s = the("still at both at the end", last="still at both")
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on"] * 4 + ["halt"]))
        self.assertIn("status 0x800", a["why"][-1])
        self.assertEqual((s["chain"]["state"], s["end"]["reached"], s["frames"]), ("halted", False, 4 * 63 + 1), "what the accepted runs walked, and no more")
        self.assertEqual([(r["walked_whole"], r["ended_by"]) for r in s["rows"]],
                         [(True, "the register stood still")] * 2 + [(False, "not ended")])
        self.assertEqual(s["rows"][-1]["named_after_the_last_frame"], None)

    def test_a_row_shorter_than_a_pass_halts_the_chain(self) -> None:
        dev = device([TOP_0, (BOTTOM, [6, 4]), BOTTOM_1])   # ten frames between two ends of rows
        _, _, a = drive(dev)
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on", "go on", "halt"]))
        self.assertIn("status 0x900 (the register stood still at one address more than a pass may cross)", a["why"][-1])
        s = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual((s["frames"], [r["frames"] for r in s["rows"]], s["rows"][0]["walked_whole"]), (127, [127], False), "the run that met the first end was not accepted")

    def test_what_stops_a_run_halts_the_chain_and_nothing_is_retried(self) -> None:
        dev = the()[0]
        root, seen, a = drive(dev, per_run={2: {"fault": "err@70"}})
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]], len(seen)), ("halted", ["go on", "go on", "halt"], 3))
        again = chain.drive(root, base(), KNOWN, runner(dev), chain.BOUNDS[STAGE], stage=STAGE)
        self.assertEqual((again["state"], len(again["runs"])), ("halted", 3), "the chain stands where it halted")

    def test_the_bound_on_runs(self) -> None:
        dev = the()[0]
        root, _, a = drive(dev, max_new=3)
        b = chain.assess(root, base(), KNOWN, 3, STAGE)
        self.assertEqual(b["state"], "halted")
        self.assertIn("the bound of 3 runs is reached", b["why"][0])


class TheSummaryOverRows(unittest.TestCase):
    def test_the_rows_are_where_the_register_stood_still(self) -> None:
        (named, _, _, _), _, _, a, s = the()
        self.assertEqual((s["chain"]["state"], s["frames"], s["unexpected"]), ("complete", len(named), []))
        self.assertEqual(s["frames_per_row"], [[0, "top", 0, 128], [0, "bottom", 0, 70], [0, "bottom", 1, 66]])
        self.assertEqual([(r["index"], r["first"], r["last"], r["walked_whole"], r["ended_by"], r["named_after_the_last_frame"]) for r in s["rows"]],
                         [(0, h(0), h(named[127]), True, "the register stood still", h(BOTTOM)),
                          (1, h(BOTTOM), h(named[197]), True, "the register stood still", h(BOTTOM | 1 << 17)),
                          (2, h(BOTTOM | 1 << 17), h(named[263]), True, "the register stood still", h(BEYOND))])
        self.assertEqual([r["frames_per_column"] for r in s["rows"]], [[[c, n] for c, n in enumerate(sizes)] for _, sizes in ROWS])
        for r in s["rows"]:
            self.assertTrue(all(c["walked_whole"] and c["minors_are_0_to_n_minus_1"] for c in r["columns"]))
            self.assertTrue(all(c["next_is_minor_0_of_the_column_numbered_one_higher"] for c in r["columns"][:-1]))
            self.assertEqual({(c["block_type"], c["half"], c["row"]) for c in r["columns"]}, {(r["block_type"], r["half"], r["row"])})
        self.assertEqual(s["standstills"], [{"after": h(named[127]), "named": h(BOTTOM)}, {"after": h(named[197]), "named": h(BOTTOM | 1 << 17)},
                                            {"after": h(named[263]), "named": h(BEYOND)}])
        self.assertEqual(s["end"], {"reached": True, "last_frame": h(named[263]), "named_after_the_last_frame": h(BEYOND),
                                    "that_address": {"block_type": 1, "half": "top", "row": 0, "column": 0, "minor": 0}, "after_a_standstill": True})
        self.assertEqual((s["known_frames_walked"], s["known_frames_not_walked"]), ([h(0xB98), h(0xB99), h(0xB9A)], []))
        self.assertEqual([x["far"] for x in s["addresses"]], [h(x) for x in named])
        self.assertEqual({x["run"] for x in s["addresses"]}, {f"run{k:02d}" for k in range(5)})

    def test_a_row_that_ends_without_a_standstill_is_not_cut_and_is_listed_as_unexpected(self) -> None:
        dev = device(ends={0: "no place"})                  # after the first row the device names the next at once
        _, _, a = drive(dev)
        self.assertEqual((a["state"], row_tests.walked(a)), ("complete", dev[0]), "the chain follows what the device names")
        s = s1b3_rows.summarize(a, KNOWN)
        self.assertEqual(([r["frames"] for r in s["rows"]], len(s["standstills"])), ([198, 66], 2))
        self.assertTrue(any("not in the block type, half and row of the column before it" in u for u in s["unexpected"]), s["unexpected"])
        self.assertTrue(all(u.startswith("row 0 (") for u in s["unexpected"]))

    def test_a_standstill_inside_a_row_and_a_row_met_twice_are_listed(self) -> None:
        _, _, _, a, s = the()
        inside = copy(a)                                    # a standstill after which the address named is in the same row
        step = inside["runs"][0]["walk"][20]; step["stood_still"] = True
        t = s1b3_rows.summarize(inside, KNOWN)
        self.assertEqual(len(t["rows"]), 4)
        self.assertTrue(any(f"the register stood still after {step['far']}, yet the address named then, {step['next']}, has the block type, half and row of that frame" in u
                            for u in t["unexpected"]), t["unexpected"])
        self.assertTrue(any("the block type, half and row of this row are those of row 0" in u for u in t["unexpected"]))
        back = copy(a)                                      # a list that is not a chain of names
        back["runs"][0]["walk"][5]["next"] = h(0x7)
        self.assertIn("an address in the list is not the one named after the address before it", s1b3_rows.summarize(back, KNOWN)["unexpected"])
        down = copy(a)                                      # an address that is not above the one before it
        down["runs"][0]["walk"][5]["far"] = h(0x1)
        self.assertIn("the addresses are not in rising order", s1b3_rows.summarize(down, KNOWN)["unexpected"])
        self.assertEqual(s1b3_rows.summarize(a, KNOWN)["unexpected"], [])

    def test_through_the_command_line(self) -> None:
        _, root, _, a, s = the()
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b3_rows.py")]
        p = subprocess.run(prog + [str(root)], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, copy(s)))
        self.assertEqual(subprocess.run(prog, capture_output=True).returncode, 2)


class TheFirstRowAgainstAStoredOne(unittest.TestCase):
    def stored(self) -> dict:
        """The first row as a summary closed by S1b.2b has it: the last address names itself, and the address the
        register showed afterwards is beside it."""
        s = the()[4]
        n = s["rows"][0]["frames"]
        addresses = [{k: x[k] for k in ("far", "next", "frame_sha256")} for x in copy(s["addresses"][:n])]
        addresses[-1]["next"] = addresses[-1]["far"]
        return {"addresses": addresses, "frames_per_column": copy(s["rows"][0]["frames_per_column"]),
                "end": {"reached": True, "last_frame": addresses[-1]["far"], "named_after_the_last_frame": s["rows"][0]["named_after_the_last_frame"]}}

    def test_the_same_row_twice_agrees(self) -> None:
        out = s1b3_top.against(the()[4], self.stored())
        self.assertEqual((out["disagreements"], out["chain"], out["addresses_in_both"], out["same_frames"], out["same_address_named"], out["stored_frames"]),
                         ([], "complete", 128, 128, 128, 128))
        self.assertEqual((out["frames_not_all_zero"], out["distinct_contents"], out["columns"]), (128, 128, len(SIZES)))
        self.assertEqual(out["row"], {"block_type": 0, "half": "top", "row": 0, "frames": 128, "first": h(0), "last": h(the()[0][0][127]),
                                      "walked_whole": True, "ended_by": "the register stood still"})

    def test_what_differs_is_listed(self) -> None:
        rows, stored = the()[4], self.stored()

        def said(change_rows=None, change_stored=None) -> list[str]:
            a, b = copy(rows), copy(stored)
            if change_rows:
                change_rows(a)
            if change_stored:
                change_stored(b)
            return s1b3_top.against(a, b)["disagreements"]
        self.assertEqual(said(), [])
        last = stored["addresses"][-1]["far"]
        self.assertTrue(any(d.startswith(f"the frame at {h(0x82)}: the chain delivered") for d in said(change_stored=lambda b: b["addresses"][5].update(frame_sha256="0" * 64))))
        self.assertEqual(said(change_stored=lambda b: b["addresses"][5].update(next=h(0x99))), [f"after {h(0x82)} the chain was told {h(0x83)}, the stored row has {h(0x99)}"])
        self.assertEqual(said(lambda a: a["addresses"][5].update(stood_still=True)), [f"the chain stood still at {h(0x82)}, where the stored row has no end"])
        self.assertTrue(any("the chain did not stand still there" in d for d in said(lambda a: a["addresses"][127].pop("stood_still"))))
        self.assertEqual(said(change_stored=lambda b: b["end"].update(named_after_the_last_frame=h(BOTTOM + 1))),
                         [f"after the standstill at {last} the chain went on to {h(BOTTOM)}; the stored row has {h(BOTTOM + 1)} named after it"])
        self.assertEqual(said(change_stored=lambda b: b["frames_per_column"][3].__setitem__(1, 99)), ["the columns do not have the same numbers of frames in the two summaries"])
        fewer = said(change_stored=lambda b: b.update(addresses=b["addresses"][:100]))
        self.assertTrue(any(d.startswith("the addresses differ: the chain's row has 128, the stored row 100; the first place they differ is 100") for d in fewer), fewer)
        other = said(change_stored=lambda b: b["addresses"][40].update(far=h(0x7777)))
        self.assertTrue(any("the first place they differ is 40" in d for d in other), other)
        self.assertTrue(any("did not walk its first row whole" in d for d in said(lambda a: a["rows"][0].update(walked_whole=False, ended_by="not ended"))))
        self.assertEqual(said(lambda a: a.update(rows=[])), ["one of the two summaries lists no row"])
        self.assertEqual(said(change_stored=lambda b: b.update(addresses=[])), ["one of the two summaries lists no row"])

    def test_how_much_the_frames_say(self) -> None:
        rows, stored = copy(the()[4]), self.stored()
        zero = s1b3_top.ALL_ZERO
        for x in rows["addresses"][:100] + stored["addresses"][:100]:
            x["frame_sha256"] = zero
        out = s1b3_top.against(rows, stored)
        self.assertEqual((out["disagreements"], out["frames_not_all_zero"], out["distinct_contents"]), ([], 28, 29))
        self.assertEqual(zero, row_tests.s1b1_judge.hashlib.sha256(bytes(404)).hexdigest())

    def test_through_the_command_line(self) -> None:
        _, root, _, _, s = the()
        (root / "rows.json").write_text(json.dumps(s)); (root / "stored.json").write_text(json.dumps(self.stored()))
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b3_top.py")]
        p = subprocess.run(prog + [str(root / "rows.json"), str(root / "stored.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, s1b3_top.against(copy(s), self.stored())))
        bad = self.stored(); bad["addresses"][3]["frame_sha256"] = "0" * 64
        (root / "bad.json").write_text(json.dumps(bad))
        self.assertEqual(subprocess.run(prog + [str(root / "rows.json"), str(root / "bad.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(prog + [str(root / "rows.json")], capture_output=True).returncode, 2)


class TheGrader(unittest.TestCase):
    def test_it_agrees_where_the_database_says_the_same(self) -> None:
        g = grade_s1b3.grade(the()[4], database())
        self.assertEqual((g["chain"], g["differs"]), ("complete", []))
        self.assertEqual(g["agrees"], ["nothing differs within any of the 3 row(s) walked",
                                       "the rows walked are the database's rows of block type 0, in its order",
                                       "frames of block type 0: the chain found 264, the database's columns add up to 264",
                                       f"the address named after the last frame of block type 0 is {h(BEYOND)}; the first frame of block type 1 in the database's order (top half, row 0) is {h(BEYOND)}"])
        self.assertEqual(len(g["not_compared"]), 1)
        self.assertTrue(g["not_compared"][0].startswith("the register stood still after the last frame of 3 row(s) ("))
        self.assertEqual([(r["frames"], r["walked_whole"], r["differs"]) for r in g["rows"]], [(128, True, []), (70, True, []), (66, True, [])])
        self.assertIn("each of the 26 column(s) walked whole has the number of frames the database gives it", g["rows"][0]["agrees"])
        self.assertTrue(any(a.startswith(f"the address named after the last frame of the row is {h(BOTTOM)}") for a in g["rows"][0]["agrees"]))
        self.assertTrue(any(a.startswith(f"the address named after the last frame of the row is {h(BOTTOM | 1 << 17)}") for a in g["rows"][1]["agrees"]))
        self.assertTrue(any("the database has no row after this one in its order" in n for n in g["rows"][2]["not_compared"]))

    def test_it_says_where_the_database_differs(self) -> None:
        s = the()[4]
        g = grade_s1b3.grade(s, database([TOP_0, (BOTTOM, [30, 25, 16]), BOTTOM_1]))
        self.assertIn("row 1 (block type 0, bottom half, row 0): column 2: the walk found 15 frame(s), the database says 16", g["differs"])
        self.assertIn("frames of block type 0: the chain found 264, the database's columns add up to 265", g["differs"])
        self.assertNotIn("nothing differs within any of the 3 row(s) walked", g["agrees"])
        g = grade_s1b3.grade(s, database(ROWS + [(BOTTOM | 2 << 17, [5])]))      # a row more in the database
        self.assertTrue(any(d.startswith("the rows walked are [(0, 'top', 0), (0, 'bottom', 0), (0, 'bottom', 1)]; the database's rows of block type 0 are") for d in g["differs"]), g["differs"])
        g = grade_s1b3.grade(s, database([TOP_0, BOTTOM_0]))                     # a row fewer
        self.assertTrue(any(d.startswith("the rows walked are") for d in g["differs"]))
        g = grade_s1b3.grade(s, database([TOP_0, BOTTOM_1, BOTTOM_0]))           # the same rows; the database's order is by row number
        self.assertEqual(g["differs"], [])
        g = grade_s1b3.grade(s, database(more_after=False))                      # no block type after this one in the database
        self.assertEqual(g["differs"], [])
        self.assertIn(f"the address named after the last frame is {h(BEYOND)}; the database lists no block type after this one", g["not_compared"])
        other = copy(s); other["end"]["named_after_the_last_frame"] = h(BEYOND + 0x80)
        self.assertTrue(any(d.startswith(f"the address named after the last frame of block type 0 is {h(BEYOND + 0x80)}") for d in grade_s1b3.grade(other, database())["differs"]))
        self.assertEqual(grade_s1b3.grade({"rows": []}, database())["not_compared"], ["the summary lists no row"])

    def test_a_chain_that_halted_is_graded_only_as_far_as_it_went(self) -> None:
        _, _, _, _, s = the("still at both at the end", last="still at both")
        g = grade_s1b3.grade(s, database())
        self.assertEqual((g["chain"], g["differs"]), ("halted", []))
        self.assertIn("the rows walked are the database's first 3 row(s) of block type 0, in its order", g["agrees"])
        self.assertTrue(any(n.startswith("the chain did not leave the envelope: the database's 1 further row(s)") for n in g["not_compared"]), g["not_compared"])
        self.assertFalse(any("frames of block type 0" in x for x in g["agrees"] + g["differs"]))
        self.assertTrue(any("the chain stopped in it after" in x for x in g["rows"][2]["agrees"]))

    def test_through_the_command_line(self) -> None:
        _, root, _, _, s = the()
        (root / "rows.json").write_text(json.dumps(s)); (root / "db.json").write_text(json.dumps(database()))
        prog = [sys.executable, "-B", str(ROOT / "host" / "grade_s1b3.py")]
        p = subprocess.run(prog + [str(root / "rows.json"), str(root / "db.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, grade_s1b3.grade(copy(s), database())))
        (root / "db2.json").write_text(json.dumps(database([TOP_0, BOTTOM_0])))
        self.assertEqual(subprocess.run(prog + [str(root / "rows.json"), str(root / "db2.json")], capture_output=True).returncode, 1)


class NothingButTheGraderNamesTheDatabase(unittest.TestCase):
    def test_the_programs_hold_no_answer(self) -> None:
        for name, allowed in (("s1b3_rows.py", {0, 1, 2, 3, 16}), ("s1b3_top.py", {0, 1, 2, 3, 4, 12, 101})):
            text = (ROOT / "host" / name).read_text()
            tree = ast.parse(text)
            numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
            self.assertEqual(numbers - allowed, set(), name)
            for word in ("prjxray", "part.json", "frame_count", "grade_s1b", "1ba", "400000", "800000"):
                self.assertNotIn(word, text.lower(), name)
        tree = ast.parse((ROOT / "host" / "grade_s1b3.py").read_text())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib", "grade_s1b2"}, set(), "the grader uses nothing of the chain's but the summary file")
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 16}, set(), "and holds no number of rows, columns or frames itself")


if __name__ == "__main__":
    unittest.main()

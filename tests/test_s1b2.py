"""S1b.2: the walk of a row as a chain of runs (docs/s1b_plan.md, section 25) — the chain's rules, the row summary and
the grader, on the twin behind the pretended board. The model rows here are made up: their columns have lengths no
part has, so that nothing passes because a number was known."""
from __future__ import annotations

import ast
import re
import json
import shutil
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
import s1b1_judge  # noqa: E402
import grade_s1b2  # noqa: E402
import s1b2_chain as chain  # noqa: E402
import s1b2_row as row_summary  # noqa: E402
import test_s1a_run as fake  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
SIZES = [3, 5, 4, 6, 2, 7, 3, 4, 5, 2, 6, 3, 4, 5, 3, 2, 4, 6, 3, 5, 4, 2, 3, 28, 5, 4]     # columns 0..25; column 23 holds the known frames
OUTSIDE = 0x00020000                                 # the first address above the envelope of the set


def row(sizes=SIZES, after=OUTSIDE, jump: dict[int, int] | None = None) -> tuple[list[int], dict[int, int]]:
    """A model row: the addresses of its frames in order, and where the device's successor is not simply the next
    number — after the last frame of each column, minor 0 of the next (or what `jump` says for that column); after
    the last frame of the row, `after`."""
    addresses, succ = [], {}
    for c, n in enumerate(sizes):
        addresses += [c << 7 | m for m in range(n)]
        succ[(c << 7) + n - 1] = (jump or {}).get(c, (c + 1) << 7) if c + 1 < len(sizes) else after
    return addresses, succ


_MADE: dict = {}


def once(name: str, make):
    """What several tests look at, made when the first of them asks and kept for the rest — in a test, not in
    setUpClass: if it cannot be made (a prober that does not build, a chain that does not run), every test that needs
    it fails, and none is kept from being run."""
    if name not in _MADE:
        try:
            _MADE[name] = (make(), None)
        except Exception as e:                           # kept as well: the tests after it fail the same way, at once
            _MADE[name] = (None, e)
    value, error = _MADE[name]
    if error is not None:
        raise error
    return value


def the_set() -> dict:
    """The parameter set s1b2 as the image's tests write it (they are run here, so that it is there to be read)."""
    def make() -> dict:
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        return json.loads(s1a_run.STAGES["s1b2"]["expected"].read_text())
    return once("set", make)


def base() -> list[int]:
    return [int(w, 16) for w in the_set()["params"]]


def runner(addresses: list[int], succ: dict[int, int], per_run: dict[int, dict] | None = None, seen: list | None = None):
    """One run of the chain on the pretended board. `per_run[k]` changes what the board is for run k: "fault" (the
    twin's), "frames" (contents that differ from the model's), "succ" (successors that differ)."""
    pl = s1a_run.PL.read_bytes()
    model = frames_for(addresses)

    def run(start: int, out: Path, came_from: str) -> None:
        k = int(out.name[3:])
        change = (per_run or {}).get(k, {})
        if change.get("nothing"):
            return
        exp = s1a_run.with_start("s1b2", json.loads(s1a_run.STAGES["s1b2"]["expected"].read_text()), start, came_from)
        u = fake.FakeUBoot(change.get("fault", ""), far_rule="skip", succ={**succ, **change.get("succ", {})}, frames={**model, **change.get("frames", {})},
                           **change.get("quirks", {}))
        out.mkdir()
        s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s{k:07d}.bin", "s1b2")
        if seen is not None:
            seen.append((k, start, came_from, u))
    return run


def shape(a: dict) -> dict:
    """An assessment without what differs between two chains that did the same: the hashes of the results (a result
    holds an address on the prober's stack, and the twin's stack moves from process to process)."""
    b = chain.brief(a)
    return {**{k: v for k, v in b.items() if k != "next_start_from"}, "runs": [{k: v for k, v in r.items() if k != "result_sha256"} for r in b["runs"]]}


def walked(a: dict) -> list[int]:
    """The addresses of the chain in order, the seam frames once."""
    out: list[int] = []
    for k, r in enumerate(a["runs"]):
        if r["decision"] != "halt":
            out += [int(s["far"], 16) for s in r["walk"][(1 if k else 0):]]
    return out


class TheChain(unittest.TestCase):
    def setUp(self) -> None:
        self.base = base()
        self.addresses, self.succ = row()

        def make() -> tuple:
            tmp, seen = Path(scratch_dirs.mkdtemp(prefix="smchain_")), []
            return tmp, seen, chain.drive(tmp / "whole", self.base, KNOWN, runner(self.addresses, self.succ, seen=seen))
        self.tmp, self.seen, self.done = once("the chain", make)

    def test_the_set_is_the_quiet_walk_with_the_row_as_its_envelope(self) -> None:
        quiet = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b1r"]["expected"].read_text())["params"]]
        self.assertEqual([k for k in range(32) if quiet[k] != self.base[k]], [3, 4, 16], "the envelope and the start, nothing else")
        self.assertEqual((self.base[3], self.base[4], self.base[16], quiet[16]), (0, 0x1FFFF, 0, 0xB80))
        self.assertEqual((self.base[5], self.base[7], self.base[12], self.base[13], self.base[15]), (0xB99, 2, 64, 16, 2 << 8))
        self.assertEqual({a >> 17 for a in range(self.base[3], self.base[4] + 1, 0x80)}, {0}, "every address of the envelope has block type, half and row zero")
        self.assertEqual((self.base[4] + 1) >> 17, 1, "and the first address above it has not")

    def test_a_row_is_walked_from_its_first_address_to_the_address_named_after_its_last(self) -> None:
        a = self.done
        self.assertEqual((a["state"], a["named_after_the_last_frame"]), ("complete", f"{OUTSIDE:#010x}"))
        self.assertEqual(walked(a), self.addresses, "every frame of the model row, in order, once")
        n = len(self.addresses)
        self.assertEqual([r["frames"] for r in a["runs"]], [64, 64, n - 126], "64 frames a run, 63 of them new after the first")
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on", "go on", "complete"])
        self.assertEqual([r["problems"] for r in a["runs"]], [[], [], []])
        self.assertEqual([r["start"] for r in a["runs"]], ["0x00000000", a["runs"][0]["last"], a["runs"][1]["last"]])
        self.assertEqual(json.loads((self.tmp / "whole" / "chain.json").read_text()), chain.brief(a))
        self.assertNotIn("walk", json.dumps(chain.brief(a)))

    def test_every_run_but_the_first_begins_at_the_last_frame_of_the_one_before_and_says_so(self) -> None:
        a = self.done
        self.assertEqual([(k, start) for k, start, _, _ in self.seen], [(0, 0), (1, self.addresses[63]), (2, self.addresses[126])])
        self.assertEqual(self.seen[0][2], "the first address of the set")
        for k in (1, 2):
            rec = json.loads((self.tmp / "whole" / f"run{k:02d}" / "run.json").read_text())
            want = f"the last frame walked by run{k - 1:02d} (result sha256 {a['runs'][k - 1]['result_sha256']})"
            self.assertEqual((rec["chain"], self.seen[k][2]), ({"start": f"{self.seen[k][1]:#010x}", "from": want}, want))
            self.assertEqual(a["runs"][k]["result_sha256"], __import__("hashlib").sha256((self.tmp / "whole" / f"run{k:02d}" / "result.bin").read_bytes()).hexdigest())
            self.assertEqual(a["runs"][k]["walk"][0], a["runs"][k - 1]["walk"][-1], "the seam frame: the same address, content and successor in both runs")
            # and the board was given that block and no other: the set's, with the starting address in its one word
            board = [self.seen[k][3].rd(0x10100000 + 4 * i) for i in range(32)]
            self.assertEqual(board, chain.planned(self.base, self.seen[k][1]))
            self.assertEqual([i for i in range(32) if board[i] != self.base[i]], [16])

    def test_a_chain_taken_up_again_is_the_same_chain(self) -> None:
        root = self.tmp / "in_steps"
        run = runner(self.addresses, self.succ)
        a = chain.drive(root, self.base, KNOWN, run, max_new=1)
        self.assertEqual((a["state"], a["next_run"], a["next_start"], len(a["runs"])), ("go on", 1, f"{self.addresses[63]:#010x}", 1))
        a = chain.drive(root, self.base, KNOWN, run, max_new=1)
        self.assertEqual((a["state"], a["next_run"], len(a["runs"])), ("go on", 2, 2))
        a = chain.drive(root, self.base, KNOWN, run)
        self.assertEqual(shape(a), shape(self.done))
        self.assertEqual(chain.brief(chain.drive(root, self.base, KNOWN, run)), chain.brief(a), "a complete chain is left as it is")
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["chain.json", "run00", "run01", "run02"])
        self.assertEqual(chain.brief(chain.assess(root, self.base, KNOWN)), chain.brief(a), "and looking at it runs nothing")

    def test_a_run_that_does_not_pass_halts_the_chain_and_nothing_is_run_after_it(self) -> None:
        for name, change, why in (("an overflow", {1: {"fault": "err@40"}}, "the run script's verdict is FAIL"),
                                  ("a frame that differs between two reads", {1: {"fault": "flip@77"}}, "the judge says FAIL"),
                                  ("a run that left nothing behind", {1: {"nothing": True}}, "there is no run record"),
                                  ("a card copy that is not the result", {1: {"quirks": {"card_corrupt": True}}}, "the card copy was not verified"),
                                  ("the first run itself", {0: {"fault": "padnz@2"}}, "run00")):
            with self.subTest(name):
                root, seen = self.tmp / name.replace(" ", "_"), []
                a = chain.drive(root, self.base, KNOWN, runner(self.addresses, self.succ, change, seen))
                k = min(change)
                self.assertEqual((a["state"], len(a["runs"]), a["runs"][-1]["decision"]), ("halted", k + 1, "halt"))
                self.assertTrue(any(why in w for w in a["why"]), a["why"])
                self.assertEqual(sorted(p.name for p in root.iterdir() if p.is_dir()), [f"run{i:02d}" for i in range(k + 1)])
                again = chain.drive(root, self.base, KNOWN, runner(self.addresses, self.succ, seen=seen))      # a board that would now pass
                self.assertEqual((again["state"], len(again["runs"])), ("halted", k + 1), "nothing is retried")
                self.assertEqual(len(seen), k + (0 if change[k].get("nothing") else 1))

    def test_a_seam_that_does_not_match_halts_the_chain(self) -> None:
        seam = self.addresses[63]
        self.assertEqual(self.succ[seam], self.addresses[64], "the seam of this model row is the last frame of a column")
        other = dict(frames_for([seam + 0x4000]))[seam + 0x4000]
        for name, change, why in (("its content", {1: {"frames": {seam: other}}}, f"seam: the frame at {seam:#010x} is not the frame the run before read there"),
                                  ("the address named after it", {1: {"succ": {seam: self.addresses[65]}}},
                                   f"seam: after {seam:#010x} this run was told {self.addresses[65]:#010x}, the run before {self.addresses[64]:#010x}")):
            with self.subTest(name):
                a = chain.drive(self.tmp / ("seam_" + name.replace(" ", "_")), self.base, KNOWN, runner(self.addresses, self.succ, change))
                self.assertEqual((a["state"], len(a["runs"]), a["runs"][1]["judge"]), ("halted", 2, "PASS"), "the run passes by itself; it is the seam that does not")
                self.assertEqual(a["why"], ["run01: " + why])

    def test_the_stored_runs_are_what_the_chain_stands_on(self) -> None:
        def copy(name: str) -> Path:
            shutil.copytree(self.tmp / "whole", self.tmp / name); return self.tmp / name
        root = copy("flipped")                               # one word of a stored result
        raw = bytearray((root / "run00" / "result.bin").read_bytes()); raw[4 * 3000] ^= 1
        (root / "run00" / "result.bin").write_bytes(bytes(raw))
        a = chain.assess(root, self.base, KNOWN)
        self.assertEqual((a["state"], len(a["runs"])), ("halted", 1))
        self.assertEqual(a["why"], ["run00: the stored result is not the one whose checksum the board gave", "run00: the run directories after it were not looked at: ['run01', 'run02']"])
        rec = json.loads((root / "run00" / "run.json").read_text())      # ... and the record made to agree with it: the judge still does not
        rec["board_crc32"] = f"{zlib.crc32(bytes(raw)) & 0xFFFFFFFF:08x}"
        (root / "run00" / "run.json").write_text(json.dumps(rec))
        a = chain.assess(root, self.base, KNOWN)
        self.assertEqual((a["state"], a["runs"][0]["judge"]), ("halted", "FAIL"))
        for name, edit, why in (("started_elsewhere", lambda rec: rec["chain"].__setitem__("start", "0x00000700"), "the run was started at 0x00000700; the chain plans"),
                                ("stopped", lambda rec: rec.__setitem__("stop", "no prompt"), "the run script stopped: no prompt"),
                                ("not_passed", lambda rec: rec.__setitem__("verdict", "FAIL"), "the run script's verdict is FAIL"),
                                ("card", lambda rec: rec.__setitem__("card_verified", False), "the card copy was not verified"),
                                ("never_went", lambda rec: rec.__setitem__("went", False), "the prober was not started"),
                                ("another_stage", lambda rec: rec.__setitem__("stage", "s1b1r"), "the run record is of stage s1b1r")):
            with self.subTest(name):
                root = copy(name)
                rec = json.loads((root / "run01" / "run.json").read_text()); edit(rec)
                (root / "run01" / "run.json").write_text(json.dumps(rec))
                a = chain.assess(root, self.base, KNOWN)
                self.assertEqual((a["state"], len(a["runs"])), ("halted", 2))
                self.assertTrue(a["why"][0].startswith("run01: " + why), a["why"])
        root = copy("gap"); (root / "run01").rename(root / "run01_set_aside")
        a = chain.assess(root, self.base, KNOWN)
        self.assertEqual((a["state"], a["runs"], a["set_aside"]), ("halted", [], ["run01_set_aside"]))
        self.assertIn("not run00, run01, ... without a gap", a["why"][0])
        root = copy("moved"); (root / "run02").rename(root / "run02_set_aside")     # the last run moved aside: the chain stands before it
        a = chain.assess(root, self.base, KNOWN)
        self.assertEqual((a["state"], a["next_run"], a["next_start"], a["set_aside"]), ("go on", 2, f"{self.addresses[126]:#010x}", ["run02_set_aside"]))
        root = copy("more"); shutil.copytree(root / "run02", root / "run03")
        a = chain.assess(root, self.base, KNOWN)
        self.assertEqual((a["state"], a["why"]), ("halted", ["run02 left the envelope, yet there are run directories after it: ['run03']"]))
        result = (self.tmp / "whole" / "run01" / "result.bin").read_bytes()         # a run judged against another start is not that run
        words = list(struct.unpack("<%dI" % (len(result) // 4), result))
        import s1b2_judge
        self.assertEqual(s1b2_judge.judge(words, KNOWN, chain.planned(self.base, self.addresses[63]))["verdict"], "PASS")
        self.assertNotEqual(s1b2_judge.judge(words, KNOWN, chain.planned(self.base, self.addresses[62]))["verdict"], "PASS")

    def test_the_bound_on_the_number_of_runs(self) -> None:
        a = chain.drive(self.tmp / "bound", self.base, KNOWN, runner(self.addresses, self.succ), max_runs=2)
        self.assertEqual((a["state"], len(a["runs"]), [r["decision"] for r in a["runs"]]), ("halted", 2, ["go on", "go on"]))
        self.assertEqual(a["why"], [f"the bound of 2 runs is reached; the last frame walked is {self.addresses[126]:#010x}"])
        self.assertEqual(chain.MAX_RUNS, 48)
        self.assertEqual(chain.assess(self.tmp / "bound", self.base, KNOWN)["state"], "go on", "the same runs under the bound of 48")

    def test_the_decisions_on_runs_that_the_twin_cannot_be_made_to_produce(self) -> None:
        """The rules as code: runs as the judge would describe them, put in place of the stored ones."""
        def run(first: int, n: int, ended=chain.LIMIT, named=None, passes=None) -> dict:
            walk = [{"far": f"{first + i:#010x}", "next": f"{first + i + 1:#010x}", "frame_sha256": f"h{first + i}"} for i in range(n)]
            one = {"frames": n, "ended": ended, "last_address_named": named or walk[-1]["next"]}
            return {"problems": [], "judge": "PASS", "result_sha256": "x", "walk": walk, "passes": passes or [one, dict(one)]}
        saved = chain.read_run

        in_them = {"frames": {"0x00000005": {}, "0x00000080": {}}}        # known frames that lie in these made-up walks: in run 0 and in run 2

        def assess(*runs: dict, max_runs: int = 48, known: dict = in_them) -> dict:
            root = Path(scratch_dirs.mkdtemp(prefix="smsynth_"))
            for k in range(len(runs)):
                (root / f"run{k:02d}").mkdir()
            chain.read_run = lambda d, base, start, known, stage="s1b2": {"dir": d.name, "start": f"{start:#010x}", **json.loads(json.dumps(runs[int(d.name[3:])]))}
            try:
                return chain.assess(root, self.base, known, max_runs)
            finally:
                chain.read_run = saved
        three = (run(0, 64), run(63, 64), run(126, 5, chain.LEFT, "0x00020000"))
        good = assess(*three)
        self.assertEqual((good["state"], good["named_after_the_last_frame"], [r["decision"] for r in good["runs"]]), ("complete", "0x00020000", ["go on", "go on", "complete"]))
        # the chain's own count of the known frames, whatever the judges of the runs said: every one in the envelope walked by some run
        for name, frames, missed in (("none of them walked", KNOWN["frames"], "0x00000b98, 0x00000b99, 0x00000b9a"),
                                     ("one of three not walked", {"0x00000005": {}, "0x00000080": {}, "0x00000090": {}}, "0x00000090"),
                                     ("the frame above the last one walked", {"0x00000005": {}, "0x00000083": {}}, "0x00000083")):
            with self.subTest(name):
                a = assess(*three, known={"frames": frames})
                self.assertEqual((a["state"], a["why"], [r["decision"] for r in a["runs"]]),
                                 ("halted", [f"run02 left the envelope, but no run of the chain walked the known frame(s) {missed}"], ["go on", "go on", "halt"]))
                self.assertNotIn("named_after_the_last_frame", a)
        outside = assess(*three, known={"frames": {"0x00000005": {}, "0x00020005": {}, "0x00400b98": {}}})
        self.assertEqual(outside["state"], "complete", "a known frame outside the envelope is not asked of a chain that may not read there")
        self.assertEqual(assess(*three[:2], known=KNOWN)["state"], "go on", "and while the row has not been left, nothing is asked yet")
        self.assertEqual(assess(run(0, 64), run(63, 64))["next_start"], "0x0000007e")
        one_pass = run(0, 64); one_pass["passes"] = one_pass["passes"][:1]
        longer = run(0, 64); longer["passes"][1]["frames"] = 63
        told = run(0, 64); told["passes"][1]["last_address_named"] = "0x00000041"
        mixed = run(0, 64); mixed["passes"][1]["ended"] = chain.LEFT
        short = run(0, 64); short["walk"] = short["walk"][:-1]
        for name, runs, why in (("one pass where two were asked for", (one_pass,), "the passes did not end alike"),
                                ("passes of different length", (longer,), "the passes did not end alike"),
                                ("passes told different addresses", (told,), "the passes did not end alike"),
                                ("one pass at the limit, the other outside", (mixed,), "the passes did not end alike"),
                                ("a walk shorter than its passes say", (short,), "the passes count 64 frames, the walk lists 63"),
                                ("passes that did not end", (run(0, 64, s1b1_judge.END[0]),), "the passes ended with \"not ended\" after 64 frame(s)"),
                                ("the limit after one frame", (run(0, 1),), "after 1 frame(s): nothing to go on from"),
                                ("a seam at another address", (run(0, 64), run(62, 64)), "seam: this run begins at 0x0000003e, the run before ended at 0x0000003f"),
                                ("a run after the row was left", (run(0, 5, chain.LEFT, "0x00020000"), run(4, 3)), "left the envelope, yet there are run directories after it")):
            with self.subTest(name):
                a = assess(*runs)
                self.assertEqual(a["state"], "halted")
                self.assertTrue(any(why in w for w in a["why"]), a["why"])
                self.assertNotIn("next_start", a)


class TheEndOfARow(unittest.TestCase):
    """What the device names after the last frame is the question; each answer is provided for."""
    def setUp(self) -> None:
        self.base = base()
        self.tmp = once("the end of a row", lambda: Path(scratch_dirs.mkdtemp(prefix="smrowend_")))

    def test_an_address_not_above_the_last_frame_stops_the_prober_and_halts_the_chain(self) -> None:
        for after in (0x0, None):
            with self.subTest(after=after):
                addresses, succ = row()
                succ[addresses[-1]] = addresses[-1] if after is None else after
                a = chain.drive(self.tmp / f"back_{after}", self.base, KNOWN, runner(addresses, succ))
                self.assertEqual((a["state"], len(a["runs"]), a["runs"][2]["judge"]), ("halted", 3, "FAIL"))
                rec = json.loads((self.tmp / f"back_{after}" / "run02" / "run.json").read_text())
                self.assertEqual(rec["console"][-1].split()[2], "status=00000800", "the prober's own stop: the address named is not above the current one")
                self.assertEqual(walked(a), addresses[:127], "what the two runs before it walked stands")

    def test_a_row_that_ends_where_a_run_reaches_its_limit(self) -> None:
        addresses, succ = row(SIZES[:-1] + [3])              # 127 frames: the second run's 64th frame is the last of the row
        self.assertEqual(len(addresses), 127)
        a = chain.drive(self.tmp / "exact", self.base, KNOWN, runner(addresses, succ))
        self.assertEqual((a["state"], [r["frames"] for r in a["runs"]], [r["ended"] for r in a["runs"]]), ("complete", [64, 64], [chain.LIMIT, chain.LEFT]))
        self.assertEqual(walked(a), addresses)

    def test_a_row_shorter_than_one_run(self) -> None:
        addresses, succ = row([0] * 23 + [28])               # nothing but the column of the known frames
        addresses, succ = [a for a in addresses], {k: v for k, v in succ.items() if k >= 0xB80}
        base_at = chain.planned(self.base, 0xB80)            # a chain may begin anywhere in the envelope: the set's start is its first run's
        a = chain.drive(self.tmp / "short", base_at, KNOWN, runner(addresses, succ))
        self.assertEqual((a["state"], len(a["runs"]), a["runs"][0]["frames"], a["named_after_the_last_frame"]), ("complete", 1, 28, f"{OUTSIDE:#010x}"))

    def test_a_row_whose_known_frames_are_passed_over_is_not_a_row_walked(self) -> None:
        """Found in review of 7f63553: a run led past the known frames that ends at its limit, not outside the envelope,
        used to pass; the run after it begins above them and is not asked for them; the chain was 'complete' with none
        of the known frames walked."""
        import s1b2_judge
        addresses, succ = row(sizes=SIZES + [20] * 6, jump={22: 24 << 7})      # after column 22 the device names column 24
        a = chain.drive(self.tmp / "over", self.base, KNOWN, runner(addresses, succ))
        went_past = "the walk went past the known frame(s) 0x00000b98, 0x00000b99, 0x00000b9a without reading them"
        self.assertEqual((a["state"], [r["decision"] for r in a["runs"]]), ("halted", ["go on", "halt"]))
        self.assertTrue(any("run01: the judge says FAIL" in w and went_past in w for w in a["why"]), a["why"])
        self.assertEqual(row_summary.summarize(a, KNOWN)["known_frames_walked"], [])
        raw = (self.tmp / "over" / "run01" / "result.bin").read_bytes()
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        block = chain.planned(self.base, int(a["runs"][0]["last"], 16))
        for judge in (s1b2_judge.judge, s1b1_judge.judge):                   # the run itself: it ended at the limit, above them
            v = judge(words, KNOWN, block)
            self.assertEqual((v["verdict"], v["problems"], v["passes"][0]["ended"], v["frames_walked"]), ("FAIL", [went_past], chain.LIMIT, 64))
        self.assertLess(int(v["walk"][0]["far"], 16), 0xB98); self.assertGreater(int(v["walk"][-1]["far"], 16), 0xB9A)
        # Run from where that run ended, the rest of this row passes run by run: nothing after it notices. Until section
        # 49 the chain's own count halted such a chain ("begun above the known frames, it cannot be complete"). Since
        # then a chain is asked for the known frames at or above the address its set begins at, and this one — a set
        # made up here, beginning above them — is complete. What keeps the row above from counting as walked is the
        # judge of the run that went past; the chain's own count is shown on written-out runs, here and in test_s1b4.
        rest = list(self.base); rest[chain.P_START] = int(v["walk"][-1]["far"], 16)
        b = chain.drive(self.tmp / "over_rest", rest, KNOWN, runner(addresses, succ))
        self.assertEqual(([r["judge"] for r in b["runs"]], [r["decision"] for r in b["runs"]]), (["PASS"] * len(b["runs"]), ["go on"] * (len(b["runs"]) - 1) + ["complete"]))
        self.assertEqual((b["state"], b["runs"][-1]["ended"], row_summary.summarize(b, KNOWN)["known_frames_walked"]), ("complete", chain.LEFT, []))

    def test_a_chain_is_asked_for_the_known_frames_from_its_first_address_on(self) -> None:
        """Section 49. A chain begun above the known frames is not asked for them (until then it could not be complete);
        one begun at or below a known frame is asked for that frame and every one above it."""
        addresses, succ = row()
        above = list(self.base); above[chain.P_START] = 24 << 7               # the model's column 24: the known frames are in column 23
        a = chain.drive(self.tmp / "above", above, KNOWN, runner(addresses, succ))
        self.assertEqual((a["state"], [(r["judge"], r["decision"], r["frames"], r["ended"]) for r in a["runs"]]), ("complete", [("PASS", "complete", 9, chain.LEFT)]))
        self.assertEqual(chain.drive(self.tmp / "above", above, KNOWN, runner(addresses, succ))["state"], "complete", "and nothing more is run")
        self.assertEqual(len(list((self.tmp / "above").glob("run*/run.json"))), 1)
        at_the_last = list(self.base); at_the_last[chain.P_START] = 0xB9A     # the last of the three: asked for, and walked as the first frame
        b = chain.drive(self.tmp / "at_the_last", at_the_last, KNOWN, runner(addresses, succ))
        self.assertEqual((b["state"], b["runs"][0]["first"], row_summary.summarize(b, KNOWN)["known_frames_walked"]), ("complete", "0x00000b9a", ["0x00000b9a"]))
        # the same stored runs taken for a chain that was to begin lower: the two frames below its first run are missed
        lower = list(self.base); lower[chain.P_START] = 0xB98
        c = chain.assess(self.tmp / "at_the_last", lower, KNOWN)
        self.assertEqual(c["state"], "halted")
        self.assertIn("the run was started at 0x00000b9a; the chain plans 0x00000b98 for it", c["why"][0])

    def test_an_address_inside_the_envelope_is_followed_whatever_its_shape(self) -> None:
        jump = {5: 7 << 7 | 2}                               # after column 5: not column 6, and not minor 0
        addresses, succ = row(jump=jump)
        expected = [a for a in addresses if not (a >> 7 == 6 or (a >> 7 == 7 and a & 0x7F < 2))]
        a = chain.drive(self.tmp / "jump", self.base, KNOWN, runner(addresses, succ))
        self.assertEqual((a["state"], walked(a)), ("complete", expected))


def database(top: dict[int, list[int]], bottom: dict[int, list[int]] | None = None) -> dict:
    """A part description of the database's shape: for each half, row -> the frame counts of its columns 0, 1, ..."""
    def rows(r):
        return {"rows": {str(k): {"configuration_buses": {"CLB_IO_CLK": {"configuration_columns": {str(c): {"frame_count": n} for c, n in enumerate(v)}}}} for k, v in r.items()}}
    return {"global_clock_regions": {"top": rows(top), **({"bottom": rows(bottom)} if bottom is not None else {})}}


class TheRowSummaryAndTheGrader(unittest.TestCase):
    def setUp(self) -> None:
        self.base = base()
        self.addresses, self.succ = row()
        self.tmp = once("the row: where", lambda: Path(scratch_dirs.mkdtemp(prefix="smrow_")))
        self.whole = once("the row: whole", lambda: chain.drive(self.tmp / "whole", self.base, KNOWN, runner(self.addresses, self.succ)))

        def walk_of_s1b1() -> dict:                      # S1b.1's walk of the model's column 23, judged by S1b.1's judge
            from test_prober_s1b1 import Run as Walk
            column = [0xB80 + m for m in range(SIZES[23])]
            w = Walk(rule="skip", succ={column[-1]: 0xC00}, frames=frames_for(column))
            v = s1b1_judge.judge(w.words, KNOWN, w.params)
            assert v["verdict"] == "PASS" and v["frames_walked"] == SIZES[23], v["problems"]
            return v
        self.s1b1 = once("the row: the walk of S1b.1", walk_of_s1b1)

    def a_chain(self, name: str) -> dict:
        """The other chains these tests look at, each made when first asked for."""
        how = {"halted": lambda: runner(self.addresses, self.succ, {1: {"fault": "err@40"}}),
               "jumped": lambda: runner(*row(jump={5: 7 << 7 | 2})),            # after column 5: not column 6, and not minor 0
               "odd": lambda: runner(*row(jump={5: 7 << 7, 24: 25 << 7 | 1}))}   # a column passed over; the last column entered at minor 1
        return once("the row: " + name, lambda: chain.drive(self.tmp / name, self.base, KNOWN, how[name]()))

    @property
    def halted(self) -> dict:
        return self.a_chain("halted")

    @property
    def jumped(self) -> dict:
        return self.a_chain("jumped")

    def test_the_row_as_the_device_named_it(self) -> None:
        r = row_summary.summarize(self.whole, KNOWN, self.s1b1)
        self.assertEqual((r["chain"], r["frames"], r["unexpected"]), ({"state": "complete", "runs": 3, "runs_that_passed": ["run00", "run01", "run02"]}, 128, []))
        self.assertEqual([int(a["far"], 16) for a in r["addresses"]], self.addresses)
        self.assertEqual([int(a["next"], 16) for a in r["addresses"]], self.addresses[1:] + [OUTSIDE])
        self.assertEqual([a["run"] for a in r["addresses"]], ["run00"] * 64 + ["run01"] * 63 + ["run02"], "each frame under the run that first walked it")
        self.assertEqual(len({a["frame_sha256"] for a in r["addresses"]}), 128)
        self.assertEqual(r["frames_per_column"], [[c, n] for c, n in enumerate(SIZES)])
        for c in r["columns"]:
            self.assertEqual((c["block_type"], c["half"], c["row"], c["walked_whole"], c["minors_are_0_to_n_minus_1"]), (0, "top", 0, True, True))
            self.assertEqual((int(c["first"], 16), int(c["last"], 16)), (c["column"] << 7, (c["column"] << 7) + c["frames"] - 1))
            self.assertEqual(c["next_is_minor_0_of_the_column_numbered_one_higher"], c["column"] != 25, "all but the last, after which the device left the row")
        self.assertEqual(r["end"], {"reached": True, "last_frame": f"{self.addresses[-1]:#010x}", "named_after_the_last_frame": "0x00020000",
                                    "that_address": {"block_type": 0, "half": "top", "row": 1, "column": 0, "minor": 0}})
        self.assertEqual((r["known_frames_walked"], r["known_frames_not_walked"]), (["0x00000b98", "0x00000b99", "0x00000b9a"], []))
        self.assertEqual(r["column_of_s1b1"], {"frames_there": 28, "of_which_walked_here": 28, "same_frames": True, "same_addresses_named": True, "the_same_column": True})
        self.assertNotIn("_place", json.dumps(r)); self.assertNotIn("minors\"", json.dumps(r))

    def test_the_fields_of_the_address_word(self) -> None:
        self.assertEqual(row_summary.fields(0xB98), {"block_type": 0, "half": "top", "row": 0, "column": 0x17, "minor": 0x18})
        self.assertEqual(row_summary.fields(0x00C20080), {"block_type": 1, "half": "bottom", "row": 1, "column": 1, "minor": 0})
        self.assertEqual(row_summary.fields(0x0001FFFF), {"block_type": 0, "half": "top", "row": 0, "column": 0x3FF, "minor": 0x7F})
        self.assertEqual(grade_s1b2.address(1, "bottom", 1, 1, 0), 0x00C20080)
        self.assertEqual({row_summary.place(a) for a in (0xB80, 0xB98, 0xBFF)}, {(0, "top", 0, 23)})

    def test_held_against_another_walk_of_the_column(self) -> None:
        other = json.loads(json.dumps(self.s1b1)); other["walk"][5]["frame_sha256"] = "0" * 64
        self.assertEqual(row_summary.summarize(self.whole, KNOWN, other)["column_of_s1b1"],
                         {"frames_there": 28, "of_which_walked_here": 28, "same_frames": False, "same_addresses_named": True, "the_same_column": True})
        other = json.loads(json.dumps(self.s1b1)); other["walk"][-1]["next"] = "0x00000c80"
        self.assertEqual(row_summary.summarize(self.whole, KNOWN, other)["column_of_s1b1"]["same_addresses_named"], False)
        longer = json.loads(json.dumps(self.s1b1)); longer["walk"].append({"far": "0x00000b9c", "next": "0x00000c00", "frame_sha256": "1" * 64})
        c = row_summary.summarize(self.whole, KNOWN, longer)["column_of_s1b1"]
        self.assertEqual((c["frames_there"], c["of_which_walked_here"], c["the_same_column"]), (29, 28, False), "a column of another length is not the same column")
        shorter = json.loads(json.dumps(self.s1b1)); shorter["walk"] = shorter["walk"][:-1]
        self.assertEqual(row_summary.summarize(self.whole, KNOWN, shorter)["column_of_s1b1"]["the_same_column"], False)
        self.assertNotIn("column_of_s1b1", row_summary.summarize(self.whole, KNOWN))
        self.assertEqual(row_summary.summarize(self.whole, KNOWN, {"walk": []})["column_of_s1b1"]["the_same_column"], False, "a walk that lists nothing is not a column")
        self.assertEqual(row_summary.summarize(self.halted, KNOWN, self.s1b1)["column_of_s1b1"],
                         {"frames_there": 28, "of_which_walked_here": 0, "same_frames": True, "same_addresses_named": True, "the_same_column": False}, "not reached: nothing to say")

    def test_a_chain_that_halted_is_summarized_as_far_as_it_went(self) -> None:
        r = row_summary.summarize(self.halted, KNOWN)
        self.assertEqual((r["chain"]["state"], r["chain"]["runs"], r["chain"]["runs_that_passed"], r["frames"]), ("halted", 2, ["run00"], 64))
        self.assertTrue(r["chain"]["why"])
        self.assertEqual([int(a["far"], 16) for a in r["addresses"]], self.addresses[:64])
        self.assertEqual((r["end"]["reached"], r["end"]["last_frame_walked"]), (False, f"{self.addresses[63]:#010x}"))
        self.assertEqual([c["walked_whole"] for c in r["columns"]], [True] * 15 + [False], "the last column listed may go on")
        self.assertEqual((r["unexpected"], r["known_frames_walked"]), ([], []))
        empty = row_summary.summarize(chain.drive(self.tmp / "none", self.base, KNOWN, runner(self.addresses, self.succ, {0: {"fault": "err@3"}})), KNOWN, self.s1b1)
        self.assertEqual((empty["frames"], empty["columns"], empty["end"]["last_frame_walked"]), (0, [], None))

    def test_a_shape_that_was_not_expected_is_listed_not_refused(self) -> None:
        r = row_summary.summarize(self.jumped, KNOWN)
        self.assertEqual((r["chain"]["state"], r["end"]["reached"]), ("complete", True))
        self.assertEqual(r["unexpected"], ["column 5 (0x00000280..0x00000286): after its last frame the device named 0x00000382, not minor 0 of column 6",
                                           "column 7 (0x00000382..0x00000383): the minors walked are [2, 3], not 0..1"])
        self.assertEqual([c for c, _ in r["frames_per_column"]], [0, 1, 2, 3, 4, 5] + list(range(7, 26)))
        into = chain.drive(self.tmp / "into", self.base, KNOWN, runner(*row(jump={5: 6 << 7 | 1})))      # the next column, but not its minor 0
        r = row_summary.summarize(into, KNOWN)
        self.assertEqual(r["unexpected"], ["column 5 (0x00000280..0x00000286): after its last frame the device named 0x00000301, not minor 0 of column 6",
                                           "column 6 (0x00000301..0x00000302): the minors walked are [1, 2], not 0..1"])
        r = row_summary.summarize(self.a_chain("odd"), KNOWN)
        self.assertEqual(r["unexpected"], ["column 5 (0x00000280..0x00000286): after its last frame the device named 0x00000380, not minor 0 of column 6",
                                           "column 24 (0x00000c00..0x00000c04): after its last frame the device named 0x00000c81, not minor 0 of column 25",
                                           "column 25 (0x00000c81..0x00000c83): the minors walked are [1, 2, 3], not 0..2"])
        self.assertEqual((r["end"]["reached"], r["columns"][-1]["next_is_minor_0_of_the_column_numbered_one_higher"]), (True, False), "the last column's exit is the row's end, not a remark")
        halves = json.loads(json.dumps(self.whole))          # the same list with an address of another row in it
        for run in halves["runs"]:
            for step in run["walk"]:
                if int(step["far"], 16) >> 7 == 25:
                    step["far"] = f"{int(step['far'], 16) | 1 << 17:#010x}"
        r = row_summary.summarize(halves, KNOWN)
        self.assertTrue(any("not in the block type, half and row of the column before it" in u for u in r["unexpected"]), r["unexpected"])
        back = json.loads(json.dumps(self.whole)); back["runs"][0]["walk"][10], back["runs"][0]["walk"][11] = back["runs"][0]["walk"][11], back["runs"][0]["walk"][10]
        r = row_summary.summarize(back, KNOWN)
        self.assertIn("the addresses are not in rising order", r["unexpected"])
        self.assertIn("an address in the list is not the one named after the address before it", r["unexpected"])

    def test_the_summary_from_the_command_line_is_made_from_the_stored_runs(self) -> None:
        (self.tmp / "s1b1.json").write_text(json.dumps(self.s1b1))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_row.py"), str(self.tmp / "whole"), str(self.tmp / "s1b1.json")], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), row_summary.summarize(self.whole, KNOWN, self.s1b1))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_chain.py"), "--dir", str(self.tmp / "whole")], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.splitlines()[-1]), (0, "3 run(s) stored; the chain: complete"))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1b2_chain.py"), "--dir", str(self.tmp / "halted")], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.splitlines()[-1]), (1, "2 run(s) stored; the chain: halted"))

    # ---- the grader
    def test_the_grader_agrees_where_the_database_says_the_same(self) -> None:
        r = row_summary.summarize(self.whole, KNOWN, self.s1b1)
        g = grade_s1b2.grade(r, database({0: SIZES, 1: [9, 9]}))
        self.assertEqual((g["differs"], g["not_compared"], g["chain"], g["row_walked"]), ([], [], "complete", {"block_type": 0, "half": "top", "row": 0}))
        self.assertEqual(g["agrees"], ["each of the 26 column(s) walked whole has the number of frames the database gives it",
                                       "the columns walked are the database's columns 0..25 of this row, in order",
                                       "frames in the row: the walk found 128, the database's columns add up to 128",
                                       "the address named after the last frame of the row is 0x00020000; the first frame of the row next in the database's order, "
                                       "row 1 of the top half, is 0x00020000"])
        self.assertEqual(g["columns"], [{"column": c, "walked": n, "database": n, "walked_whole": True} for c, n in enumerate(SIZES)])

    def test_the_grader_says_where_the_database_differs(self) -> None:
        r = row_summary.summarize(self.whole, KNOWN)
        one = list(SIZES); one[7] += 1
        g = grade_s1b2.grade(r, database({0: one, 1: [9]}))
        self.assertEqual([d for d in g["differs"] if "column 7" in d], ["column 7: the walk found 4 frame(s), the database says 5"])
        self.assertTrue(any("frames in the row: the walk found 128, the database's columns add up to 129" in d for d in g["differs"]))
        self.assertFalse(any("each of the" in x for x in g["agrees"]))
        g = grade_s1b2.grade(r, database({0: SIZES + [6], 1: [9]}))            # a column more in the database
        self.assertTrue(any(d.startswith("the columns walked are [0, 1,") for d in g["differs"]), g["differs"])
        g = grade_s1b2.grade(r, database({0: SIZES[:-1], 1: [9]}))             # a column fewer
        self.assertIn("column 25: the walk found 4 frame(s), the database says None", g["differs"])
        g = grade_s1b2.grade(r, database({0: SIZES}, {0: [9]}))                # no further row in the top half: the bottom half is next
        self.assertEqual([d for d in g["differs"] if "named after" in d],
                         ["the address named after the last frame of the row is 0x00020000; the first frame of the row next in the database's order, "
                          "row 0 of the bottom half (this is the last row of the top half in the database), is 0x00400000"])
        g = grade_s1b2.grade(r, database({0: SIZES}))                          # no row after it at all
        self.assertEqual((g["differs"], g["not_compared"]), ([], ["the address named after the last frame is 0x00020000; the database has no row after this one in its order"]))
        g = grade_s1b2.grade(r, database({1: SIZES}))
        self.assertEqual((g["agrees"], g["differs"]), ([], []))
        self.assertIn("the database has no entry for this row", g["not_compared"][0])
        self.assertEqual(grade_s1b2.grade({"columns": []}, database({0: SIZES}))["not_compared"], ["the summary lists no column"])
        mixed = json.loads(json.dumps(r)); mixed["columns"][-1]["row"] = 1          # a column of another row in the list
        self.assertIn("the columns walked are not all in one block type, half and row", grade_s1b2.grade(mixed, database({0: SIZES, 1: [9]}))["differs"])
        self.assertNotIn("the columns walked are not all in one block type, half and row", grade_s1b2.grade(r, database({0: SIZES, 1: [9]}))["differs"])

    def test_the_grader_compares_only_what_was_walked_whole(self) -> None:
        r = row_summary.summarize(self.halted, KNOWN)
        g = grade_s1b2.grade(r, database({0: SIZES, 1: [9]}))
        self.assertEqual((g["chain"], g["differs"]), ("halted", []))
        self.assertEqual(g["agrees"], ["column 15: the chain stopped in it after 2 frame(s); the database gives it 2",
                                       "each of the 15 column(s) walked whole has the number of frames the database gives it",
                                       "the columns walked are the database's columns 0..15 of this row, in order"])
        self.assertEqual(g["not_compared"], ["the chain did not leave the row: the database's 11 further column(s) and what follows the row were not compared"])
        fewer = list(SIZES); fewer[15] = 1
        self.assertIn("column 15: the chain stopped in it after 2 frame(s); the database gives it 1", grade_s1b2.grade(r, database({0: fewer}))["differs"])
        g = grade_s1b2.grade(row_summary.summarize(self.jumped, KNOWN), database({0: SIZES, 1: [9]}))
        self.assertTrue(g["not_compared"][0].startswith("the summary lists 2 thing(s) as unexpected"))
        self.assertTrue(any(d.startswith("column 7: the walk found 2 frame(s), the database says 4") for d in g["differs"]))
        self.assertTrue(any(d.startswith("the columns walked are [0, 1, 2, 3, 4, 5, 7,") for d in g["differs"]))

    def test_nothing_but_the_graders_names_the_database(self) -> None:
        """The closed-book rule, as far as a test can hold it, for the new files: the chain, the row summary, the
        judge of a run and the run script do not name the database, carry no frame count, and import no grader."""
        # every file the prober is built from, the Makefile and the linker script among them (review of S1b, finding F3):
        # the directory holds these and no other, and the Makefile's rules name no source but these
        built_from = {"Makefile", "link.ld", "sm.h", "sm_board.c", "sm_core.c", "twin_hal.c"}
        self.assertEqual({p.name for p in (ROOT / "prober").iterdir()}, built_from)
        makefile = (ROOT / "prober" / "Makefile").read_text()
        self.assertEqual(set(re.findall(r"[\w./-]+\.(?:c|h|ld|S|s|o|a|json|db|ll|bit)\b", makefile)), {"sm_core.c", "twin_hal.c", "sm_board.c", "sm.h", "link.ld"})
        self.assertNotRegex(makefile, r"(?m)^\s*-?include\b|\$\(shell|wildcard|curl|wget|git ")
        self.assertNotRegex((ROOT / "prober" / "link.ld").read_text(), r"INCLUDE|INPUT|GROUP")
        self.assertFalse(re.findall(r'#\s*include\s*"(?!sm\.h")[^"]*"', "".join((ROOT / "prober" / n).read_text() for n in ("sm.h", "sm_board.c", "sm_core.c", "twin_hal.c"))),
                         "the sources include no file of the project's but sm.h")
        for path in list((ROOT / "host").glob("*.py")) + list((ROOT / "prober").iterdir()):
            text = path.read_text()
            if path.name in ("grade_s1b1.py", "grade_s1b2.py", "grade_s1b3.py"):
                continue
            for word in ("prjxray", "grade_s1b", "frame_count", "part.json"):
                self.assertNotIn(word, text.lower(), path.name)
        tree = ast.parse((ROOT / "host" / "grade_s1b2.py").read_text())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib"}, set(), "and the grader uses nothing of the chain's but the summary file")
        for name in ("s1b2_chain.py", "s1b2_row.py"):        # and neither holds a number of columns or of frames of any part
            numbers = {n.value for n in ast.walk(ast.parse((ROOT / "host" / name).read_text())) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
            self.assertEqual(numbers - {0, 1, 2, 3, 4, 7, 8, 10, 12, 16, 17, 22, 23, 40, 48, 96, 0x1F, 0x7F, 0x3FF, 0xFFFFFFFF}, set(), name)


class TheRunScriptAndTheJudgeOfARun(unittest.TestCase):
    def setUp(self) -> None:
        self.base = base()
        self.exp = json.loads(json.dumps(the_set()))     # a copy: a test that changed it would change it for the others

    def test_the_starting_address_is_the_one_word_given_at_run_time(self) -> None:
        e = s1a_run.with_start("s1b2", self.exp, 0x781, "somewhere")
        self.assertEqual(([k for k in range(32) if e["params"][k] != self.exp["params"][k]], e["params"][16], e["chain"]), ([16], "00000781", {"start": "0x00000781", "from": "somewhere"}))
        self.assertEqual({k: v for k, v in e.items() if k not in ("params", "chain")}, {k: v for k, v in self.exp.items() if k != "params"})
        self.assertEqual(self.exp["params"][16], "00000000", "and the set itself is not changed by it")
        for start in (0x20000, 0xFFFFFFFF, 0x400000):
            with self.assertRaises(ValueError):
                s1a_run.with_start("s1b2", self.exp, start, "x")
        self.assertEqual(s1a_run.with_start("s1b2", self.exp, 0x1FFFF, "x")["params"][16], "0001ffff")
        for stage in ("s1b1", "s1b1r", "s1a", "dxw0r"):
            with self.assertRaises(ValueError):
                s1a_run.with_start(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), 0xB80, "x")
        self.assertEqual(s1a_run.STARTS_AT_RUN_TIME, ("s1b2", "s1b3", "s1b4", "s1b5"))

    def test_the_command_line(self) -> None:
        def plan(*args):
            r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), *args, "--dry-run"], capture_output=True, text=True)
            return r.returncode, r.stdout, [line.split("#")[0].split(".", 1)[1].strip() for line in r.stdout.splitlines() if "#" in line and line.strip()[0].isdigit()]
        rc, text, first = plan("--stage", "s1b2")
        rc2, text2, later = plan("--stage", "s1b2", "--start", "781", "--start-from", "a test")
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual([c for c in later if c not in first], ["mw.l 10100040 00000781 1"], "one word more is written: the start (zero in the first run, and so not written)")
        self.assertEqual([c for c in first if c not in later], [])
        self.assertIn("stage s1b2, starting at 0x00000781 (a test)", text2)
        self.assertIn("mw.l 1010000c", "".join(plan("--stage", "s1b1r")[2]))
        self.assertNotIn("mw.l 1010000c", "".join(first), "the envelope begins at address 0")
        self.assertIn("mw.l 10100010 0001ffff 1", first)
        for args, why in ((("--stage", "s1b2", "--start", "20000"), "REFUSED: 0x00020000 is outside the envelope 0x00000000..0x0001ffff of s1b2"),
                          (("--stage", "s1b1r", "--start", "b80"), "REFUSED: the starting address of s1b1r is fixed")):
            rc, text, _ = plan(*args)
            self.assertEqual((rc, text.strip()), (2, why))

    def test_a_run_of_the_chain_is_not_failed_for_known_frames_it_began_beyond(self) -> None:
        """The one point in which the judge of a run differs from the judge of S1b.1 (which is left as it was)."""
        from test_prober_s1b1 import Run as Walk
        import s1b2_judge
        self.assertEqual((s1b2_judge.HDR, s1b2_judge.REC, s1b2_judge.MAX_RECORDS, s1b2_judge.END), (s1b1_judge.HDR, s1b1_judge.REC, s1b1_judge.MAX_RECORDS, s1b1_judge.END))
        self.assertIs(s1a_run.STAGES["s1b2"]["judge"], s1b2_judge)
        beyond = Walk(start=0xB9B)                           # begins above the three known frames and walks out of the envelope
        v1, v2 = s1b1_judge.judge(beyond.words, KNOWN, beyond.params), s1b2_judge.judge(beyond.words, KNOWN, beyond.params)
        self.assertEqual((v1["verdict"], v2["verdict"], v2["problems"]), ("FAIL", "PASS", []))
        self.assertEqual(v1["problems"], ["the walk left the envelope without passing the known frame(s) 0x00000b98, 0x00000b99, 0x00000b9a"])
        self.assertEqual(v2["known_frames_not_reached"], ["0x00000b98", "0x00000b99", "0x00000b9a"], "listed all the same")
        self.assertEqual({k: v for k, v in v1.items() if k not in ("verdict", "problems")}, {k: v for k, v in v2.items() if k not in ("verdict", "problems")})
        between = Walk(start=0xB99)                          # begins on the second: the first lies below, the other two are passed
        self.assertEqual((s1b1_judge.judge(between.words, KNOWN, between.params)["verdict"], s1b2_judge.judge(between.words, KNOWN, between.params)["verdict"]), ("FAIL", "PASS"))
        addresses = [0xB80, 0xB81, 0xB82, 0xB83, 0xBF0, 0xBF1]                     # begins below them and is led past them
        skipped = Walk(succ={0xB83: 0xBF0, 0xBF1: 0x1000}, frames=frames_for(addresses + [0xB99]))
        for judge in (s1b1_judge.judge, s1b2_judge.judge):
            v = judge(skipped.words, KNOWN, skipped.params)
            self.assertEqual((v["verdict"], v["problems"]), ("FAIL", ["the walk left the envelope without passing the known frame(s) 0x00000b98, 0x00000b99, 0x00000b9a"]))
        whole = Walk()
        self.assertEqual(s1b2_judge.judge(whole.words, KNOWN, whole.params), s1b1_judge.judge(whole.words, KNOWN, whole.params), "a walk through them: the same verdict, word for word")
        # led past them and ended by the limit instead: failed all the same, by either judge — the next run of a chain would not be asked
        at_limit = Walk(succ={0xB83: 0xBF0}, frames=frames_for(addresses + [0xBF2, 0xB99]), limit=6)
        some = Walk(succ={0xB98: 0xB9A, 0xB9A: 0xBF0}, frames=frames_for([0xB80 + m for m in range(0x19)] + [0xB99, 0xB9A, 0xBF0, 0xBF1, 0xBF2]), limit=28)
        for judge in (s1b1_judge.judge, s1b2_judge.judge):
            v = judge(at_limit.words, KNOWN, at_limit.params)
            self.assertEqual((v["verdict"], v["problems"], v["passes"][0]["ended"], [s["far"] for s in v["walk"]]),
                             ("FAIL", ["the walk went past the known frame(s) 0x00000b98, 0x00000b99, 0x00000b9a without reading them"], chain.LIMIT, [f"{a:#010x}" for a in addresses]))
            v = judge(some.words, KNOWN, some.params)
            self.assertEqual((v["verdict"], v["problems"], v["frames_walked"]), ("FAIL", ["the walk went past the known frame(s) 0x00000b99 without reading them"], 28))
        short = Walk(limit=5)                                # ended by the limit below them: nothing was passed over, nothing is asked
        up_to = Walk(limit=0x19)                             # ended by the limit on the first of them: the two above it were not passed over
        beyond_at_limit = Walk(start=0xB9B, limit=4)         # begun above them, ended by the limit: they lie below what was read
        for w, last in ((short, 0xB84), (up_to, 0xB98), (beyond_at_limit, 0xB9E)):
            for judge in (s1b1_judge.judge, s1b2_judge.judge):
                v = judge(w.words, KNOWN, w.params)
                self.assertEqual((v["verdict"], v["problems"], v["passes"][0]["ended"], v["walk"][-1]["far"]), ("PASS", [], chain.LIMIT, f"{last:#010x}"))
        flipped = Walk("flip@5", start=0xB9B)                # and beyond them a frame that differs between two reads still fails
        self.assertEqual(s1b2_judge.judge(flipped.words, KNOWN, flipped.params)["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()

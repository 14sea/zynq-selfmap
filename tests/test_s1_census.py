"""S1: the frame census as one document (docs/s1b_plan.md, section 68) — host/s1_census.py on chains the twin walked.

The devices are the made-up ones of the tests of the chains over block types 1 and 2: rows and columns in numbers no
part has, every frame with a content of its own, so that a reading laid at the wrong address shows. No database is
read and nothing is graded. The census of the board's own chains is held in tests/test_board_evidence.py."""
from __future__ import annotations

import ast
import copy
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1_census as census  # noqa: E402
import test_s1b4 as b4  # noqa: E402
import test_s1b5 as b5  # noqa: E402
import test_s1b6a as b6  # noqa: E402
from test_s1b2 import KNOWN, once  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "frame_census_v1.schema.json").read_text())
NOT_SHOWN = "its record does not show the declared image \\(crc32 84f107a1\\) in RAM just before the prober was started and again after it returned"


def h(a: int) -> str:
    return f"{a:#010x}"


def part(which: str) -> dict:
    """A complete chain of the twin as the census takes it: block type 1 (three rows, 256 addresses) or block type 2
    (three rows, 140 addresses, most columns of one frame)."""
    made = {"s1b4": b4.the, "s1b5": b5.the}[which]
    return copy.deepcopy(once(f"census / {which}", lambda: census.chain_part(which, made()[1], KNOWN)))


def both() -> dict:
    return copy.deepcopy(once("census / both", lambda: census.build([part("s1b4"), part("s1b5")])))


class TheEntries(unittest.TestCase):
    def test_every_address_the_chains_walked_is_an_entry_and_no_other(self) -> None:
        c = both()
        named = b4.the()[0][0] + b5.the()[0][0]
        self.assertEqual([e["far"] for e in c["entries"]], [h(a) for a in sorted(named)])
        self.assertEqual((c["totals"]["addresses"], c["totals"]["by_block_type"]), (b4.FRAMES + b5.FRAMES, [[1, b4.FRAMES], [2, b5.FRAMES]]))
        self.assertEqual((c["problems"], c["seen_not_walked"], c["totals"]["not_stable"]), ([], [], 0))
        jsonschema.Draft202012Validator(SCHEMA).validate(c)
        e = c["entries"][71]                                 # made-up block type 1: its second column begins after 70 frames
        self.assertEqual({k: e[k] for k in ("far", "block_type", "half", "row", "column", "minor", "state", "named_next")},
                         {"far": h(b4.B | 1 << 7 | 1), "block_type": 1, "half": "top", "row": 0, "column": 1, "minor": 1, "state": "walked", "named_next": h(b4.B | 1 << 7 | 2)})
        for chain_set, addresses in (("s1b4", b4.the()[0][0]), ("s1b5", b5.the()[0][0])):
            mine = [e for e in c["entries"] if e["evidence"]["chain"] == chain_set]
            self.assertEqual([e["named_next"] for e in mine[:-1]], [e["far"] for e in mine[1:]], "each entry names the next")
            self.assertEqual(len(mine), len(addresses))

    def test_the_rows_and_the_binding(self) -> None:
        c = both()
        self.assertEqual([(r["chain"], r["block_type"], r["half"], r["row"], r["frames"], r["ended_by"]) for r in c["rows"]],
                         [("s1b4", 1, "top", 0, 100, "the register stood still"), ("s1b4", 1, "top", 1, 66, "the register stood still"),
                          ("s1b4", 1, "bottom", 0, 90, "the register stood still"), ("s1b5", 2, "top", 0, 45, "the register stood still"),
                          ("s1b5", 2, "bottom", 0, 40, "the register stood still"), ("s1b5", 2, "bottom", 1, 55, "the register stood still")])
        self.assertEqual((c["rows"][0]["columns"], c["rows"][5]["columns"]), ([[0, 70], [1, 30]], [[0, 30], [1, 25]]))
        self.assertEqual([e["far"] for e in c["entries"] if e.get("stood_still")], [r["last"] for r in c["rows"]], "a row's last frame is where the register stood still")
        chains = c["binding"]["chains"]
        self.assertEqual([(x["set"], x["state"], x["addresses"], x["first"], x["named_after_the_last_frame"]) for x in chains],
                         [("s1b4", "complete", b4.FRAMES, h(b4.B), h(b4.ABOVE)), ("s1b5", "complete", b5.FRAMES, h(b5.B), h(b5.ABOVE))])
        self.assertEqual((c["binding"]["prober_image_sha256"], c["binding"]["prober_image_crc32"]), ("fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452", "84f107a1"))
        self.assertEqual((c["totals"]["stretches"], c["stretches"]),
                         (1, [{"first": h(b4.B), "last": c["entries"][-1]["far"], "addresses": b4.FRAMES + b5.FRAMES, "named_after_the_last": h(b5.ABOVE)}]),
                         "the first chain named, after its last frame, the address the second began at: one stretch")
        self.assertEqual(c["label"], "closed-book")
        self.assertEqual([n["far"] for n in c["named_not_read"]], [h(b5.ABOVE)], "what the first chain named after its last frame the second one walked; what the second named, nothing read")

    def test_every_reading_is_counted_and_laid_at_its_address(self) -> None:
        c, p = both(), part("s1b5")
        delivered = sum(len(r["frame_sha256"]) for q in (part("s1b4"), p) for run in q["runs"] for r in run["verdict"]["records"] if r["kind"] == "target")
        self.assertEqual((c["totals"]["readings"], c["totals"]["fewest_readings_of_an_address"]), (delivered, 3))
        # the twin gives every address a content of its own: had a reading been laid one address off, two contents would show there
        self.assertTrue(all(e["stable"] and e["distinct_contents"] == 1 for e in c["entries"]))
        self.assertEqual(len({e["frame_sha256"] for e in c["entries"]}), len(c["entries"]))
        self.assertEqual((c["totals"]["all_zero"], c["totals"]["distinct_contents_that_are_not_zero"]), (0, len(c["entries"])))
        seams = {run["verdict"]["walk"][0]["far"] for run in p["runs"][1:]}
        mine = [e for e in c["entries"] if e["evidence"]["chain"] == "s1b5"]
        self.assertEqual({e["far"] for e in mine if e["readings"] == 6}, seams, "a frame at a seam was read by two runs: twice in each pass and in a read of several")
        # two passes and one read of several frames; the last read of several in a stretch reaches back over a frame
        # already read that way, so that it is a read of as many frames as the others: such a frame has four
        self.assertEqual({e["readings"] for e in mine if e["far"] not in seams}, {3, 4})
        four = [e for e in mine if e["readings"] == 4]
        self.assertTrue(four and all(len({(r[0], r[1]) for r in e["evidence"]["reads"]}) == 4 for e in four), "four readings are four records")
        e = next(e for e in mine if e["far"] in seams)
        self.assertEqual(sorted({r[0] for r in e["evidence"]["reads"]}), ["run00", "run01"])
        self.assertTrue(any(r[2] > 0 for e in mine for r in e["evidence"]["reads"]), "readings from within a read of several frames are among them")

    def test_a_reading_that_differs_is_shown_at_the_address_it_was_read_at(self) -> None:
        p = part("s1b4")
        v = p["runs"][0]["verdict"]
        i, r = next((i, r) for i, r in enumerate(v["records"]) if r["kind"] == "target" and len(r["frame_sha256"]) == 3)
        second = next(s["next"] for s in v["walk"] if s["far"] == r["far"])
        r["frame_sha256"][1] = "f" * 64                      # the second frame of a read of three
        c = census.build([p])
        bad = [e for e in c["entries"] if not e["stable"]]
        self.assertEqual([(e["far"], e["distinct_contents"], e["readings"], len(e["frame_sha256"])) for e in bad], [(second, 2, 3, 2)])
        self.assertIn(["run00", i, 1], bad[0]["evidence"]["reads"])
        self.assertEqual((c["totals"]["not_stable"], c["problems"]), (1, [f"1 address(es) were not read alike every time; the first is {second}"]))
        jsonschema.Draft202012Validator(SCHEMA).validate(c)

    def test_a_read_of_several_frames_is_not_laid_across_a_standstill_or_beyond_the_walk(self) -> None:
        p = part("s1b4")
        v = p["runs"][0]["verdict"]
        r = next(r for r in v["records"] if r["kind"] == "target" and len(r["frame_sha256"]) == 3)
        next(s for s in v["walk"] if s["far"] == r["far"])["stood_still"] = True
        with self.assertRaisesRegex(census.Refused, "runs on past .* where the register stood still"):
            census.build([p])
        p = part("s1b4")
        v = p["runs"][0]["verdict"]
        v["records"][2]["far"] = h(0x00900000)
        with self.assertRaisesRegex(census.Refused, "which the walk of that run does not list"):
            census.build([p])


class WhereTheEntriesHangTogether(unittest.TestCase):
    """Review of f465f17, finding 2: the entries are sorted, and the document must say where each is the address named
    after the one before — and where not."""

    def test_a_chain_left_out_leaves_two_stretches_and_the_document_says_so(self) -> None:
        first, third = part("s1b4"), part("s1b5")
        gap = h(0x00C80000)                                  # as if a chain lay between them: the first names an address the other does not begin at
        first["rows"]["addresses"][-1]["next"] = gap
        c = census.build([first, third])
        self.assertEqual(c["totals"]["stretches"], 2)
        self.assertEqual(c["stretches"], [{"first": h(b4.B), "last": first["rows"]["addresses"][-1]["far"], "addresses": b4.FRAMES, "named_after_the_last": gap},
                                          {"first": h(b5.B), "last": c["entries"][-1]["far"], "addresses": b5.FRAMES, "named_after_the_last": h(b5.ABOVE)}])
        self.assertEqual(sum(s["addresses"] for s in c["stretches"]), c["totals"]["addresses"])
        jsonschema.Draft202012Validator(SCHEMA).validate(c)

    def test_within_a_stretch_every_entry_is_named_by_the_one_before(self) -> None:
        c = both()
        by = {e["far"]: e for e in c["entries"]}
        for s in c["stretches"]:
            at, n = s["first"], 1
            while at != s["last"]:
                at, n = by[at]["named_next"], n + 1
            self.assertEqual((n, by[at]["named_next"]), (s["addresses"], s["named_after_the_last"]))
        one = census.build([part("s1b5")])
        self.assertEqual((one["totals"]["stretches"], one["stretches"][0]["first"], one["stretches"][0]["addresses"]), (1, h(b5.B), b5.FRAMES))


class WhatWasLoaded(unittest.TestCase):
    """Review of f465f17, finding 3: the binding is what the chain's own files show, not what the set says of itself."""

    def copy_of(self, with_kept_files: bool = True) -> Path:
        root = Path(scratch_dirs.mkdtemp(prefix="smcensus_")) / "chain"
        shutil.copytree(b5.the()[1], root)
        if with_kept_files:
            shutil.copy(census.ROOT / "build" / "prober" / "prober.bin", root / "prober.bin")
            shutil.copy(census.ROOT / "build" / "prober" / "expected_s1b5.json", root / "expected_s1b5.json")
        return root

    def test_the_binding_is_taken_from_the_runs(self) -> None:
        for kept in (True, False):
            p = census.chain_part("s1b5", self.copy_of(kept), KNOWN)
            self.assertEqual(p["loaded"], part("s1b5")["loaded"])
        b = p["loaded"]
        image = (census.ROOT / "build" / "prober" / "prober.bin").read_bytes()
        design = (census.ROOT / "build" / "pl" / "carrier.bit").read_bytes()
        import hashlib, zlib
        self.assertEqual(b, {"prober_image_sha256": hashlib.sha256(image).hexdigest(), "prober_image_crc32": f"{zlib.crc32(image) & 0xFFFFFFFF:08x}",
                             "pl_design_sha256": hashlib.sha256(design).hexdigest(), "pl_design_bytes": len(design),
                             "pl_design_crc32_in_ram": f"{zlib.crc32(design) & 0xFFFFFFFF:08x}", "pl_design_sha256_held_against_the_file": True})

    def test_a_declaration_the_kept_image_does_not_bear_out_is_refused(self) -> None:
        for key, value in (("image_sha256", "0" * 64), ("image_crc32", "00000000"), ("image_bytes", 11969)):
            with self.subTest(key):
                root = self.copy_of()
                exp = json.loads((root / "expected_s1b5.json").read_text()); exp[key] = value
                (root / "expected_s1b5.json").write_text(json.dumps(exp))
                with self.assertRaisesRegex(census.Refused, "the image kept with the runs is not the image the set declares"):
                    census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # another image kept with the runs
        image = (root / "prober.bin").read_bytes()
        (root / "prober.bin").write_bytes(image[:-1] + bytes([image[-1] ^ 1]))
        with self.assertRaisesRegex(census.Refused, "the image kept with the runs is not the image the set declares"):
            census.chain_part("s1b5", root, KNOWN)

    def change_reply(self, root: Path, run: str, address: str, which: int, new: str) -> None:
        f = root / run / "run.json"
        rec = json.loads(f.read_text())
        steps = [s for s in rec["steps"] if s.get("cmd", "").startswith(f"crc32 {address} ")]
        was = steps[which]["reply"]
        steps[which]["reply"] = re.sub(r"==> [0-9a-f]{8}", "==> " + new, was)
        self.assertNotEqual(steps[which]["reply"], was)
        f.write_text(json.dumps(rec))

    def test_a_run_whose_record_shows_another_image_or_design_in_ram_is_refused(self) -> None:
        for which, why in ((0, "before the prober was started"), (1, "after it returned")):
            with self.subTest(why):
                root = self.copy_of()
                self.change_reply(root, "run01", "02000000", which, "deadbeef")
                with self.assertRaisesRegex(census.Refused, "chain/run01: " + NOT_SHOWN):
                    census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # one run with another design in RAM
        self.change_reply(root, "run02", "04000000", 0, "0badf00d")
        with self.assertRaisesRegex(census.Refused, "its runs were not all made with one design in RAM"):
            census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # every run with a design that is not the declared file
        for run in ("run00", "run01", "run02"):
            self.change_reply(root, run, "04000000", 0, "0badf00d")
        with self.assertRaisesRegex(census.Refused, "the design the set declares is not the design its runs had in RAM"):
            census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # a record without the checksums
        f = root / "run00" / "run.json"
        rec = json.loads(f.read_text()); rec["steps"] = [s for s in rec["steps"] if not s.get("cmd", "").startswith(("crc32 0", "go ", "fpga "))]
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "chain/run00: its record does not show one load of the design and, after it, one start of the prober"):
            census.chain_part("s1b5", root, KNOWN)
        for address, keep, why in (("02000000", 1, NOT_SHOWN[len("its record "):]), ("04000000", 0, "does not show one checksum of a design")):
            root = self.copy_of()                            # the image's checksum once only; the design's not at all
            f = root / "run01" / "run.json"
            rec = json.loads(f.read_text())
            mine = [s for s in rec["steps"] if s.get("cmd", "").startswith(f"crc32 {address} ")]
            rec["steps"] = [s for s in rec["steps"] if s not in mine[keep:]]
            f.write_text(json.dumps(rec))
            with self.assertRaisesRegex(census.Refused, "chain/run01: its record " + why):
                census.chain_part("s1b5", root, KNOWN)

    def steps_of(self, root: Path, run: str):
        f = root / run / "run.json"
        rec = json.loads(f.read_text())
        at = lambda prefix: [i for i, s in enumerate(rec["steps"]) if s.get("cmd", "").startswith(prefix)]     # noqa: E731
        return f, rec, at

    def test_a_checksum_on_the_wrong_side_of_the_start_does_not_stand_for_one_on_the_other(self) -> None:
        """Review of the correction, one finding: the checksums of a run's record were taken together and two alike
        were enough, wherever they stood. The reviewer's case: the one after the run taken away, the one before it
        there twice."""
        root = self.copy_of()
        f, rec, at = self.steps_of(root, "run01")
        before, after = at("crc32 02000000 ")
        self.assertTrue(before < at("go ")[0] < after)
        del rec["steps"][after]; rec["steps"].insert(before, dict(rec["steps"][before]))
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "chain/run01: " + NOT_SHOWN + r": before \['84f107a1', '84f107a1'\], after \[\]"):
            census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # the other way: none before the start, two after the return
        f, rec, at = self.steps_of(root, "run01")
        before, after = at("crc32 02000000 ")
        rec["steps"].append(rec["steps"].pop(before))
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "chain/run01: " + NOT_SHOWN + r": before \[\], after \['84f107a1', '84f107a1'\]"):
            census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # before the start, but not the step just before it: something came between
        f, rec, at = self.steps_of(root, "run01")
        before = at("crc32 02000000 ")[0]
        rec["steps"].insert(before + 1, {"n": 0, "what": "something else", "cmd": "mw.l 02000000 0 1", "reply": "Zynq> "})
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "chain/run01: " + NOT_SHOWN):
            census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # a reply that is not whole, asked for again: the second counts, as on the board
        f, rec, at = self.steps_of(root, "run01")
        before = at("crc32 02000000 ")[0]
        rec["steps"].insert(before, dict(rec["steps"][before], reply="crc32 02000000 2ec2\r\ncrc32 for 02000000 ... 020"))
        f.write_text(json.dumps(rec))
        self.assertEqual(census.chain_part("s1b5", root, KNOWN)["loaded"], part("s1b5")["loaded"])

    def test_the_designs_checksum_stands_just_before_its_load(self) -> None:
        root = self.copy_of()                                # taken after the load: it does not say what was loaded
        f, rec, at = self.steps_of(root, "run00")
        crc, load = at("crc32 04000000 ")[0], at("fpga loadb ")[0]
        self.assertEqual(load, crc + 1)
        rec["steps"][crc], rec["steps"][load] = rec["steps"][load], rec["steps"][crc]
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "chain/run00: its record does not show one checksum of a design of [0-9]+ bytes in RAM just before it was loaded"):
            census.chain_part("s1b5", root, KNOWN)
        for prefix, why in (("go ", "two starts"), ("fpga loadb ", "two loads")):
            with self.subTest(why):
                root = self.copy_of()
                f, rec, at = self.steps_of(root, "run00")
                rec["steps"].append(dict(rec["steps"][at(prefix)[0]]))
                f.write_text(json.dumps(rec))
                with self.assertRaisesRegex(census.Refused, "chain/run00: its record does not show one load of the design and, after it, one start of the prober"):
                    census.chain_part("s1b5", root, KNOWN)
        root = self.copy_of()                                # the start before the load
        f, rec, at = self.steps_of(root, "run00")
        rec["steps"].insert(0, rec["steps"].pop(at("go ")[0]))
        f.write_text(json.dumps(rec))
        with self.assertRaisesRegex(census.Refused, "one load of the design and, after it, one start of the prober"):
            census.chain_part("s1b5", root, KNOWN)

    def test_the_reviewers_case(self) -> None:
        """The declared hash made all zero, the kept image and the results as they were: it was taken, and the census
        bound to a hash of zeros."""
        root = self.copy_of()
        exp = json.loads((root / "expected_s1b5.json").read_text()); exp["image_sha256"] = "0" * 64
        (root / "expected_s1b5.json").write_text(json.dumps(exp))
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1_census.py"), "--chain", f"s1b5={root}"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.strip()), (2, "REFUSED: chain: the image kept with the runs is not the image the set declares"))


class WhatIsRefused(unittest.TestCase):
    def test_a_chain_that_is_not_complete(self) -> None:
        root, _, a = b5.halted("stuck at the end", b5.device(b5.ROWS, last="still at both", after=b5.ABOVE))
        self.assertEqual(a["state"], "halted")
        with self.assertRaisesRegex(census.Refused, "is not complete"):
            census.chain_part("s1b5", root, KNOWN)
        with self.assertRaisesRegex(census.Refused, "is not a set a chain is driven with"):
            census.chain_part("s1b5a", b5.the()[1], KNOWN)
        with self.assertRaisesRegex(census.Refused, "is not complete"):              # a chain taken for another set's is no chain of that set
            census.chain_part("s1b4", b5.the()[1], KNOWN)

    def test_a_summary_that_lists_something_unexpected(self) -> None:
        saved = census.s1b3_rows.summarize
        census.s1b3_rows.summarize = lambda a, known: {**saved(a, known), "unexpected": ["the addresses are not in rising order"]}
        try:
            with self.assertRaisesRegex(census.Refused, "lists something unexpected"):
                census.chain_part("s1b5", b5.the()[1], KNOWN)
        finally:
            census.s1b3_rows.summarize = saved

    def test_two_chains_over_the_same_addresses_or_of_different_designs(self) -> None:
        with self.assertRaisesRegex(census.Refused, "is walked by two of the chains given"):
            census.build([part("s1b5"), part("s1b5")])
        for key, value in (("prober_image_sha256", "0" * 64), ("pl_design_crc32_in_ram", "11111111"), ("pl_design_sha256", "1" * 64)):
            other = part("s1b4"); other["loaded"][key] = value
            with self.assertRaisesRegex(census.Refused, "not all run with one design and one image"):
                census.build([other, part("s1b5")])

    def test_a_list_whose_frame_no_reading_is(self) -> None:
        p = part("s1b5"); p["rows"]["addresses"][9]["frame_sha256"] = "9" * 64
        with self.assertRaisesRegex(census.Refused, "has a frame that none of its readings is"):
            census.build([p])


class RunsThatAreNotPartOfAChain(unittest.TestCase):
    def stopped(self) -> list:
        """A run the walk stopped at the second row end of its first pass: 40 addresses read once each."""
        root, _, _ = b5.halted("short rows", b5.device(b5.SHORT_ROWS, after=b5.ABOVE))
        return census.stored_verdicts(root / "run00")

    def test_what_such_a_run_read_and_no_chain_walked_is_listed_apart(self) -> None:
        verdicts = self.stopped()
        self.assertEqual([(name, v["verdict"], v["header"]["status"]) for name, v in verdicts], [("run00", "FAIL", "0x900")])
        c = census.build([part("s1b4")], seen=[("short", verdicts)])
        rows = b5.SHORT_ROWS
        self.assertEqual([e["far"] for e in c["seen_not_walked"]], [h(base | col << 7) for base, sizes in rows[:2] for col in range(len(sizes))])
        self.assertEqual({(e["state"], e["readings"], e["block_type"]) for e in c["seen_not_walked"]}, {("seen", 1, 2)})
        self.assertEqual(c["seen_not_walked"][0]["evidence"], {"name": "short", "run": "run00", "verdict": "FAIL", "status": "0x900", "records": [2]})
        self.assertEqual(c["seen_runs"], [{"name": "short", "run": "run00", "verdict": "FAIL", "status": "0x900", "records_used": 80, "records_not_used": []}])
        self.assertEqual([(n["far"], n["state"]) for n in c["named_not_read"]], [(h(rows[2][0]), "named")], "where the register stood when the run was stopped")
        self.assertIn("in the address register after record", c["named_not_read"][0]["seen"])
        self.assertEqual((c["totals"]["addresses"], c["totals"]["seen_not_walked"], c["totals"]["named_not_read"], c["problems"]), (b4.FRAMES, 40, 1, []))
        self.assertTrue(all(e["state"] == "walked" for e in c["entries"]), "nothing seen is an entry")
        jsonschema.Draft202012Validator(SCHEMA).validate(c)

    def test_a_read_that_did_not_succeed_gives_neither_a_frame_nor_an_address(self) -> None:
        """Review of f465f17, finding 1. A short read leaves words of the buffer as they were filled beforehand; a read
        the interface failed leaves the read-back of the address register undone, and the record holds 0 there."""
        B = b6.B
        _, v, _, _ = b6.go("it goes on", "short@13")         # the sixth frame read short
        self.assertEqual((v["header"]["status"], v["records"][12]["code"], v["records"][12]["survivors"] > 0), ("0x710", "0x10", True))
        c = census.build([part("s1b4")], seen=[("short", [("run", v)])])
        self.assertEqual([e["far"] for e in c["seen_not_walked"]], [h(B + k) for k in range(5)], "the sixth is not seen: what came back is not its frame")
        self.assertEqual([n["far"] for n in c["named_not_read"]], [h(b4.ABOVE), h(B + 5), h(B + 6)], "it was named, and stays named and not read")
        self.assertEqual(c["seen_runs"], [{"name": "short", "run": "run", "verdict": "FAIL", "status": "0x710", "records_used": 11, "records_not_used": [[12, h(B + 5), "0x10"]]}])
        _, v, _, _ = b6.go("it goes on", "err@13")           # the first frame read with an error bit
        self.assertEqual((v["header"]["status"], v["records"][2]["code"], v["records"][2]["far_read_back"]), ("0x221", "0x21", "0x00000000"))
        c = census.build([part("s1b4")], seen=[("err", [("run", v)])])
        self.assertEqual((c["seen_not_walked"], [n["far"] for n in c["named_not_read"]]), ([], [h(b4.ABOVE), h(B + 1)]), "no frame from it, and address 0 is not called named")
        self.assertEqual(c["seen_runs"][0]["records_not_used"], [[2, h(B), "0x21"]])
        _, v, _, _ = b6.go("it goes on", "padnz@8")          # a pad that is not zero
        bad = next(i for i, r in enumerate(v["records"]) if r["kind"] == "target" and not r["pad_all_zero"])
        c = census.build([part("s1b4")], seen=[("pad", [("run", v)])])
        self.assertEqual([x[0] for x in c["seen_runs"][0]["records_not_used"]], [bad])
        self.assertNotIn(bad, [i for e in c["seen_not_walked"] for i in e["evidence"]["records"]])
        jsonschema.Draft202012Validator(SCHEMA).validate(c)

    def test_a_read_that_did_not_succeed_in_a_run_of_a_chain_is_refused(self) -> None:
        for change in ({"code": "0x10"}, {"survivors": 3}, {"pad_all_zero": False}):
            p = part("s1b5")
            r = next(r for r in p["runs"][1]["verdict"]["records"] if r["kind"] == "target" and r["frames"])
            r.update(change)
            with self.assertRaisesRegex(census.Refused, "a read that did not succeed"):
                census.build([p])

    def test_an_address_a_chain_walked_is_not_listed_as_seen_or_as_named(self) -> None:
        c = census.build([part("s1b4"), part("s1b5")], seen=[("short", self.stopped())])
        self.assertEqual((c["seen_not_walked"], [n["far"] for n in c["named_not_read"]]), ([], [h(b5.ABOVE)]))

    def test_a_run_with_reads_of_several_frames_is_not_taken_as_seen(self) -> None:
        with self.assertRaisesRegex(census.Refused, "is a read of several frames"):
            census.build([part("s1b4")], seen=[("stored", [("run", b5.stored_run())])])

    def test_the_same_addresses_on_another_occasion(self) -> None:
        stored = b5.stored_run()
        c = census.build([part("s1b5")], also=[("the stored run", [("run", stored)])])
        self.assertEqual(c["other_occasions"], [{"name": "the stored run", "runs_used": 1, "runs_not_used": [], "addresses": 64, "readings_alike": 64, "different": []}])
        changed = copy.deepcopy(stored); changed["walk"][5]["frame_sha256"] = "5" * 64
        failed = copy.deepcopy(stored); failed["verdict"] = "FAIL"; failed["walk"][6]["frame_sha256"] = "6" * 64
        c = census.build([part("s1b5")], also=[("again", [("a", changed), ("b", failed)])])
        o = c["other_occasions"][0]
        self.assertEqual((o["runs_used"], o["runs_not_used"], o["readings_alike"], [(d["far"], d["run"], d["there"]) for d in o["different"]]),
                         (1, ["b"], 63, [(stored["walk"][5]["far"], "a", "5" * 64)]))
        self.assertEqual(c["problems"], ["again: 1 reading(s) of another occasion differ from the census"])
        tmp = Path(scratch_dirs.mkdtemp(prefix="smcensus_"))                          # runs kept under names of their own
        for name, v in (("first_try", changed), ("second_try", stored)):
            (tmp / name).mkdir(); (tmp / name / "verdict.json").write_text(json.dumps(v))
        self.assertEqual([name for name, _ in census.stored_verdicts(tmp)], ["first_try", "second_try"])
        self.assertEqual([name for name, _ in census.stored_verdicts(b5.the()[1])], ["run00", "run01", "run02"])
        c = census.build([part("s1b4")], also=[("elsewhere", [("run", stored)])])     # a run that walked none of the census's addresses
        self.assertEqual((c["other_occasions"][0]["addresses"], c["problems"]), (0, []))

    def test_a_status_bit_that_is_neither_an_error_nor_usual_is_listed(self) -> None:
        self.assertEqual(both()["status_bits"], [], "the twin shows nothing but the usual")
        p = part("s1b5")
        v = p["runs"][1]["verdict"]
        first = next(i for i, r in enumerate(v["records"]) if r["kind"] == "target" and r["frames"])
        for r in v["records"][first:]:
            r["int_sts"] = [f"{int(x, 16) | 1 << 9:08x}" for x in r["int_sts"]]
        c = census.build([p])
        self.assertEqual(c["status_bits"], [{"bit": 9, "name": None, "chain": "s1b5", "runs": ["run01"], "first_shown_at": [["run01", first, v["records"][first]["far"]]]}])
        self.assertEqual(c["problems"], [], "seen, not judged")


class TheProgram(unittest.TestCase):
    def test_the_document_as_text(self) -> None:
        c = both()
        text = census.dump(c)
        self.assertEqual(json.loads(text), c)
        lines = text.splitlines()
        self.assertEqual(sum(1 for x in lines if x.startswith('  {"far": ')), len(c["entries"]) + len(c["named_not_read"]), "one address a line")
        empty = census.dump({**c, "named_not_read": [], "rows": []})
        self.assertEqual(json.loads(empty)["named_not_read"], [])

    def test_through_the_command_line(self) -> None:
        root4, root5 = b4.the()[1], b5.the()[1]
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1_census.py")]
        p = subprocess.run(prog + ["--chain", f"s1b4={root4}", "--chain", f"s1b5={root5}"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, census.dump(both())), p.stderr)
        tmp = Path(scratch_dirs.mkdtemp(prefix="smcensus_"))
        changed = b5.stored_run(); changed["walk"][5]["frame_sha256"] = "5" * 64
        (tmp / "verdict.json").write_text(json.dumps(changed))
        p = subprocess.run(prog + ["--chain", f"s1b5={root5}", "--also", f"again={tmp}"], capture_output=True, text=True)
        self.assertEqual((p.returncode, len(json.loads(p.stdout)["problems"])), (1, 1), "something differs: the document all the same, and exit 1")
        halted, _, _ = b5.halted("stuck at the end", b5.device(b5.ROWS, last="still at both", after=b5.ABOVE))
        for args, why in ((["--chain", f"s1b5={halted}"], "is not complete"), (["--chain", f"s1b5a={root5}"], "is not a set a chain is driven with"),
                          ([], "at least one --chain"), (["--chain", f"s1b5={root5}", "--seen", str(tmp)], "every argument as NAME=PATH"),
                          (["--chain", f"s1b5={root5}", "--also", f"x={tmp / 'nothing'}"], "no verdict found")):
            p = subprocess.run(prog + args, capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout.startswith("REFUSED: "), why in p.stdout), (2, True, True), (args, p.stdout[:200], p.stderr[-300:]))

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1_census.py").read_text()
        tree = ast.parse(text)
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 3, 4, 16, 0xFFFFFFFF}, set(), "no number of rows, columns or frames of any part")
        for word in ("prjxray", "part.json", "frame_count", "grade_s1b", "1ba", "400000", "800000", "evidence/"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "argparse", "hashlib", "json", "struct", "sys", "pathlib", "s1a_run", "s1b2_chain", "s1b2_judge", "s1b2_row", "s1b3_rows",
                                     "status_seen", "s1b3_top", "zlib"}, set())


if __name__ == "__main__":
    unittest.main()

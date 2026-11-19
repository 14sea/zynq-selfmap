"""S1: the frame census as one document (docs/s1b_plan.md, section 68) — host/s1_census.py on chains the twin walked.

The devices are the made-up ones of the tests of the chains over block types 1 and 2: rows and columns in numbers no
part has, every frame with a content of its own, so that a reading laid at the wrong address shows. No database is
read and nothing is graded. The census of the board's own chains is held in tests/test_board_evidence.py."""
from __future__ import annotations

import ast
import copy
import json
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
from test_s1b2 import KNOWN, once  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "frame_census_v1.schema.json").read_text())


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
        self.assertEqual(c["binding"]["prober_image_sha256"], "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
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
        for key, value in (("image_sha256", "0" * 64), ("pl_design", {"sha256": "1" * 64})):
            other = part("s1b4"); other["expected"][key] = value
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
        self.assertEqual([(n["far"], n["state"]) for n in c["named_not_read"]], [(h(rows[2][0]), "named")], "where the register stood when the run was stopped")
        self.assertIn("in the address register after record", c["named_not_read"][0]["seen"])
        self.assertEqual((c["totals"]["addresses"], c["totals"]["seen_not_walked"], c["totals"]["named_not_read"], c["problems"]), (b4.FRAMES, 40, 1, []))
        self.assertTrue(all(e["state"] == "walked" for e in c["entries"]), "nothing seen is an entry")
        jsonschema.Draft202012Validator(SCHEMA).validate(c)

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
        self.assertEqual(numbers - {0, 1, 2, 3, 4, 16}, set(), "no number of rows, columns or frames of any part")
        for word in ("prjxray", "part.json", "frame_count", "grade_s1b", "1ba", "400000", "800000", "evidence/"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "argparse", "hashlib", "json", "struct", "sys", "pathlib", "s1a_run", "s1b2_chain", "s1b2_judge", "s1b2_row", "s1b3_rows",
                                     "status_seen", "s1b3_top"}, set())


if __name__ == "__main__":
    unittest.main()

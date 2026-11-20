"""S1b.4a: one run of the walk into block type 1 (docs/s1b_plan.md, section 46) — the parameter set, the run through
the run script on the twin behind the pretended board, and the program that lays such a run out.

Nothing is known of block type 1 on the device. The shapes the twin is given here are invented for the tests: columns
of ten and five frames, a row that ends after fifteen. No number of any real part is in this file but the one address
the board itself named after the last frame of block type 0."""
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
import s1a_run  # noqa: E402
import s1b2_judge  # noqa: E402
import s1b4a_layout as lay  # noqa: E402
import test_s1a_run as fake  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2_end import once, the_set as sets_made  # noqa: E402

KNOWN = fake.KNOWN
STAGE = "s1b4a"
B = 0x00800000                                       # named by the board after 0x00401ba9 (S1b.3, run 61)
REF = 0x00000B99
ABOVE = 0x01000000                                   # the first address above the envelope
H1, H2 = 0x7F000001, 0x7F000002                      # places without an address of their own (the twin's SM_SHOWS)
COL0, COL1 = list(range(B, B + 10)), list(range(B + 0x80, B + 0x85))        # invented: columns of ten and of five frames
LAST = COL1[-1]
NEXT_ROW = B + 0x20000
TWO_COLUMNS = {COL0[-1]: COL1[0]}
# name: which place follows which, what the register shows at a place that is not its own number, the frames there are
MODELS = {
    "a stretch without an end": ({}, {}, list(range(B, B + 80))),
    "every frame all zero": ({}, {}, []),
    "three columns": ({**TWO_COLUMNS, LAST: B + 0x100}, {}, COL0 + COL1 + list(range(B + 0x100, B + 0x140))),
    "a row that ends as the board's rows did": ({**TWO_COLUMNS, LAST: H1, H1: H2, H2: NEXT_ROW}, {H1: LAST, H2: NEXT_ROW},
                                                COL0 + COL1 + [H1, H2] + list(range(NEXT_ROW, NEXT_ROW + 0x40))),
    "the end of the block type after a standstill": ({**TWO_COLUMNS, LAST: H1, H1: H2, H2: ABOVE}, {H1: LAST, H2: ABOVE}, COL0 + COL1 + [H1, H2, ABOVE]),
    "the end of the block type without one": ({**TWO_COLUMNS, LAST: ABOVE}, {}, COL0 + COL1 + [ABOVE]),
    "an address of block type 0 is named": ({B + 5: 0x100}, {}, list(range(B, B + 10)) + [0x100, 0x101]),
    "an address names itself for good": ({B + 5: H1, H1: H2, H2: B + 6}, {H1: B + 5, H2: B + 5}, list(range(B, B + 10)) + [H1, H2]),
}
LIMIT, LEFT = "the limit of frames was reached", "the device named an address outside the envelope"


def h(a: int) -> str:
    return f"{a:#010x}"


def the_set() -> dict:
    sets_made("s1b2")                                # builds the image and writes the sets, once
    return json.loads(s1a_run.STAGES[STAGE]["expected"].read_text())


def go(model: str, fault: str = ""):
    """One run of the set through the run script on the pretended board. Returns the run record, the verdict, the
    addresses written to the address register, and the directory."""
    succ, shows, there = MODELS[model]
    exp = the_set()
    pl = s1a_run.PL.read_bytes()
    u = fake.FakeUBoot(fault, far_rule="skip", succ=succ, shows=shows, frames=frames_for(there))
    out = Path(scratch_dirs.mkdtemp(prefix="sm4a_")) / "run"
    out.mkdir()
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", STAGE)
    verdict = json.loads((out / "verdict.json").read_text())
    streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
    written = {s[k + 1] for s in streams for k in range(len(s) - 1) if s[k] == 0x30002001}
    return rec, verdict, written, out


def the(model: str):
    return once(f"s1b4a / {model}", lambda: go(model))


class TheSet(unittest.TestCase):
    def test_it_is_the_set_of_the_chain_over_block_type_0_with_two_words_changed(self) -> None:
        p = [int(w, 16) for w in the_set()["params"]]
        q = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b3"]["expected"].read_text())["params"]]
        self.assertEqual([k for k in range(32) if p[k] != q[k]], [4, 16], "the envelope's upper end and the start")
        self.assertEqual((p[3], p[4], p[16]), (0, 0x00FFFFFF, B))
        self.assertEqual((p[2], p[5], p[7], p[8], p[10], p[12], p[13], p[15]), (4, REF, 2, 0, 1, 64, 16, 2 << 8),
                         "the walk, the reference frame, two passes, one standstill a pass, 64 frames, the wait that touches no memory")
        self.assertEqual((p[4] >> 23, (p[4] + 1) >> 23, p[4] + 1), (1, 2, ABOVE), "block type 1 to its last address and nothing above it")
        self.assertTrue(p[3] <= p[5] <= p[4], "the prober wants the reference frame inside the envelope")
        self.assertIs(s1a_run.STAGES[STAGE]["judge"], s1b2_judge)

    def test_the_start_is_the_address_the_board_named_after_block_type_0(self) -> None:
        rows = json.loads((ROOT / "evidence" / "s1b3_17A6_2026-11-17" / "rows.json").read_text())
        self.assertEqual((rows["chain"]["state"], rows["end"]["reached"]), ("complete", True))
        self.assertEqual(the_set()["params"][16], rows["end"]["named_after_the_last_frame"][2:])
        self.assertNotIn(rows["end"]["named_after_the_last_frame"], {s["far"] for s in rows["addresses"]}, "named there, and not read")

    def test_the_image_that_ran_is_the_one_that_had_been_on_the_board(self) -> None:
        """Until 2026-11-20 this held the set's own image to that hash: the step was made with the image as it was. S2.0
        brought a new image (docs/s2_plan.md, section 13), so the set as it is built today names another. What stays
        true, and is held here, is what ran: the image kept beside this step's run is the one kept with the chain
        before it, and the run's record shows that image in RAM."""
        import hashlib
        ran = (ROOT / "evidence" / "s1b4a_17A6_2026-11-18" / "prober.bin").read_bytes()
        kept = (ROOT / "evidence" / "s1b3_17A6_2026-11-17" / "prober.bin").read_bytes()
        self.assertEqual(hashlib.sha256(ran).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        self.assertEqual(ran, kept)
        self.assertEqual((the_set()["image_bytes"], the_set()["image_crc32"]),
                         (len(s1a_run.IMAGE.read_bytes()), f"{zlib.crc32(s1a_run.IMAGE.read_bytes()) & 0xFFFFFFFF:08x}"), "the set names the image as it is built now")

    def test_nothing_of_it_is_given_at_run_time(self) -> None:
        with self.assertRaises(ValueError):
            s1a_run.with_start(STAGE, the_set(), B, "x")
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE]
        r = subprocess.run(prog + ["--start", "800000", "--dry-run"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, "REFUSED: the starting address of s1b4a is fixed"))
        r = subprocess.run(prog + ["--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        for line in ("mw.l 10100010 00ffffff 1", "mw.l 10100014 00000b99 1", "mw.l 10100028 00000001 1", "mw.l 10100040 00800000 1", "mw.l 1010003c 00000200 1"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("mw.l 1010000c", r.stdout, "the envelope begins at 0: that word is left as the zeroing made it")


class TheRun(unittest.TestCase):
    def test_a_stretch_of_frames_is_walked_as_any_other(self) -> None:
        rec, v, written, _ = the("a stretch without an end")
        self.assertEqual((rec["verdict"], rec["problems"], v["header"]["status"], v["header"]["anomalies"]), ("PASS", [], "0x1", 0))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], list(range(B, B + 64)))
        self.assertEqual(v["passes"], [{"frames": 64, "ended": LIMIT, "last_address_named": h(B + 64)}] * 2)
        self.assertEqual(v["frames_without_a_second_path"], [])

    def test_no_address_is_written_but_the_reference_frame_and_what_the_device_named(self) -> None:
        for model in MODELS:
            with self.subTest(model):
                _, v, written, _ = the(model)
                named = {B} | {int(s["next"], 16) for s in v["walk"]}
                self.assertIn(REF, written)
                self.assertTrue(written - {REF} <= named, sorted(h(a) for a in written - {REF} - named))
                self.assertTrue(all(B <= a < ABOVE for a in written - {REF}), "nothing of block type 0 but the reference frame, and nothing above block type 1")

    def test_columns_are_followed_by_the_names_the_device_gives(self) -> None:
        rec, v, _, _ = the("three columns")
        self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
        want = COL0 + COL1 + list(range(B + 0x100, B + 0x100 + 49))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], want)
        self.assertEqual([int(s["next"], 16) for s in v["walk"]], want[1:] + [B + 0x100 + 49])

    def test_an_end_of_a_row_like_those_of_block_type_0_is_crossed(self) -> None:
        rec, v, _, _ = the("a row that ends as the board's rows did")
        self.assertEqual((rec["verdict"], rec["problems"], v["pieces"]), ("PASS", [], [15, 49]))
        self.assertEqual(v["standstills"], [{"at": h(LAST), "register_after_the_pad_alone": h(LAST), "register_after_the_frame": h(NEXT_ROW)}])
        self.assertEqual(v["passes"], [{"frames": 64, "ended": LIMIT, "last_address_named": h(NEXT_ROW + 49)}] * 2)

    def test_what_the_device_names_above_block_type_1_is_not_read(self) -> None:
        for model, stood in (("the end of the block type after a standstill", True), ("the end of the block type without one", False)):
            with self.subTest(model):
                rec, v, written, _ = the(model)
                self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []), "a run that begins above the known frames is not failed for not passing them")
                self.assertEqual(v["passes"], [{"frames": 15, "ended": LEFT, "last_address_named": h(ABOVE)}] * 2)
                self.assertEqual((max(written), bool(v["walk"][-1].get("stood_still"))), (LAST, stood))

    def test_a_name_that_leads_back_into_block_type_0_stops_the_run(self) -> None:
        """The envelope begins at 0, because the reference frame has to lie in it. That gives the walk nothing below
        its start: an address named that is not above the one before is not followed."""
        rec, v, written, _ = the("an address of block type 0 is named")
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "0x800", 6))
        self.assertEqual(v["passes"][0]["last_address_named"], h(0x100))
        self.assertEqual(sorted(written), [REF] + list(range(B, B + 6)))
        self.assertTrue((the("an address of block type 0 is named")[3] / "result.bin").exists(), "stored whole all the same")

    def test_an_address_that_names_itself_for_good_stops_the_run(self) -> None:
        rec, v, _, _ = the("an address names itself for good")
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], v["passes"][0]["last_address_named"]), ("FAIL", "0x800", 6, h(B + 5)))

    def test_what_the_walk_does_not_expect_stops_it_there_and_is_stored(self) -> None:
        for fault, status, walked in (("padnz@8", "0x711", 3), ("short@12", "0x710", 5), ("flip@9", "0x712", 64), ("err@9", "0x221", 0), ("timeout@11", "0x222", 0),
                                      ("drop@9", "0x223", 0), ("farflip@10", "0x800", 5)):
            with self.subTest(fault=fault):
                rec, v, written, out = go("a stretch without an end", fault)
                self.assertEqual((rec["verdict"], v["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "FAIL", status, walked))
                self.assertTrue(all(a == REF or B <= a < B + 64 for a in written), sorted(h(a) for a in written))
                self.assertEqual((rec.get("stop"), rec["card_verified"], (out / "result.bin").exists()), (None, True, True))

    def test_the_result_is_not_one_of_the_chain_over_block_type_0(self) -> None:
        _, _, _, out = the("a stretch without an end")
        raw = (out / "result.bin").read_bytes()
        import struct
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        mine = [int(w, 16) for w in the_set()["params"]]
        self.assertEqual(s1b2_judge.judge(words, KNOWN, mine)["verdict"], "PASS")
        other = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b3"]["expected"].read_text())["params"]]
        other[16] = B
        self.assertNotEqual(s1b2_judge.judge(words, KNOWN, other)["verdict"], "PASS", "the envelope the prober echoed is not that set's")


class TheLayout(unittest.TestCase):
    def test_a_run_that_ended_at_the_limit(self) -> None:
        _, v, _, _ = the("a stretch without an end")
        out = lay.layout(v)
        self.assertEqual((out["run"], out.get("note")), ({"verdict": "PASS", "status": "0x1", "problems": []}, None))
        self.assertEqual((out["frames"], out["first"], out["last"], out["block_types"], out["frames_per_row"]), (64, h(B), h(B + 63), [1], [[1, "top", 0, 64]]))
        self.assertEqual((out["end"]["reached"], out["end"]["last_frame_walked"], out["standstills"], out["unexpected"]), (False, h(B + 63), [], []))
        self.assertEqual((out["rows"][0]["walked_whole"], out["rows"][0]["ended_by"], out["rows"][0]["frames_per_column"]), (False, "not ended", [[0, 64]]))
        self.assertEqual(out["content"], {"frames_not_all_zero": 64, "distinct_contents": 64})
        self.assertEqual(out["passes"], v["passes"])

    def test_columns_and_rows_as_the_device_named_them(self) -> None:
        out = lay.layout(the("three columns")[1])
        self.assertEqual((out["rows"][0]["frames_per_column"], out["unexpected"]), ([[0, 10], [1, 5], [2, 49]], []))
        self.assertTrue(all(c["walked_whole"] and c["minors_are_0_to_n_minus_1"] for c in out["rows"][0]["columns"][:2]))
        out = lay.layout(the("a row that ends as the board's rows did")[1])
        self.assertEqual((out["frames_per_row"], out["standstills"], out["unexpected"]),
                         ([[1, "top", 0, 15], [1, "top", 1, 49]], [{"after": h(LAST), "named": h(NEXT_ROW)}], []))
        self.assertEqual([(r["walked_whole"], r["ended_by"]) for r in out["rows"]], [(True, "the register stood still"), (False, "not ended")])

    def test_an_end_is_one_only_if_both_passes_left_the_envelope_in_a_run_that_passed(self) -> None:
        for model, stood in (("the end of the block type after a standstill", True), ("the end of the block type without one", False)):
            with self.subTest(model):
                v = the(model)[1]
                out = lay.layout(v)
                self.assertEqual(out["end"], {"reached": True, "last_frame": h(LAST), "named_after_the_last_frame": h(ABOVE), "after_a_standstill": stood,
                                              "that_address": {"block_type": 2, "half": "top", "row": 0, "column": 0, "minor": 0}})
                self.assertEqual((out["rows"][-1]["walked_whole"], out["frames_per_row"]), (True, [[1, "top", 0, 15]]))
                failed = json.loads(json.dumps(v)); failed["verdict"] = "FAIL"
                self.assertEqual((lay.layout(failed)["end"]["reached"], "note" in lay.layout(failed)), (False, True))
                one = json.loads(json.dumps(v)); one["passes"][1]["ended"] = LIMIT
                self.assertFalse(lay.layout(one)["end"]["reached"])
        self.assertFalse(lay.layout(the("a stretch without an end")[1])["end"]["reached"])

    def test_frames_that_are_all_alike_are_said_to_be(self) -> None:
        rec, v, _, _ = the("every frame all zero")
        self.assertEqual(rec["verdict"], "PASS")
        out = lay.layout(v)
        self.assertEqual((out["content"]["frames_not_all_zero"], out["content"]["distinct_contents"]), (0, 1))
        self.assertIn("says nothing about which frame either read", out["content"]["note"])
        one = json.loads(json.dumps(v)); one["walk"][7]["frame_sha256"] = "5" * 64
        self.assertEqual(lay.layout(one)["content"], {"frames_not_all_zero": 1, "distinct_contents": 2})

    def test_a_run_that_did_not_pass_is_laid_out_and_called_that(self) -> None:
        _, v, _, _ = the("an address of block type 0 is named")
        out = lay.layout(v)
        self.assertEqual((out["run"]["verdict"], out["run"]["status"], out["frames"], out["frames_per_row"], out["end"]["reached"]), ("FAIL", "0x800", 6, [[1, "top", 0, 6]], False))
        self.assertIn("is not a finding", out["note"])
        self.assertTrue(out["run"]["problems"])
        nothing = lay.layout({"verdict": "INVALID", "problems": ["x"]})
        self.assertEqual((nothing["frames"], nothing["passes"], "rows" in nothing, "note" in nothing), (0, [], False, True))

    def test_what_is_not_in_order_is_listed(self) -> None:
        v = json.loads(json.dumps(the("a stretch without an end")[1]))
        v["walk"][4], v["walk"][5] = v["walk"][5], v["walk"][4]
        self.assertEqual(sorted(lay.layout(v)["unexpected"])[0], "an address in the list is not the one named after the address before it")

    def test_through_the_command_line(self) -> None:
        _, v, _, out = the("a stretch without an end")
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b4a_layout.py")]
        p = subprocess.run(prog + [str(out / "verdict.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, lay.layout(v)))
        failed = json.loads(json.dumps(v)); failed["verdict"] = "FAIL"
        (out / "failed.json").write_text(json.dumps(failed))
        self.assertEqual(subprocess.run(prog + [str(out / "failed.json")], capture_output=True).returncode, 1)
        odd = json.loads(json.dumps(v)); odd["walk"][4], odd["walk"][5] = odd["walk"][5], odd["walk"][4]
        (out / "odd.json").write_text(json.dumps(odd))
        self.assertEqual(subprocess.run(prog + [str(out / "odd.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(prog, capture_output=True).returncode, 2)

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1b4a_layout.py").read_text()
        tree = ast.parse(text)
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 16}, set())
        for word in ("prjxray", "part.json", "frame_count", "grade_s1b", "1ba", "400000", "800000"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib", "s1b2_row", "s1b3_rows", "s1b1_judge", "s1b3_top"}, set())


if __name__ == "__main__":
    unittest.main()

"""S1b.5a: one run of the walk into block type 2 (docs/s1b_plan.md, section 58) — the parameter set and the run
through the run script on the twin behind the pretended board; the layout and the listing of status bits over it.

Nothing is known of block type 2 on the device. The shapes the twin is given here are invented for the tests, one
for each outcome the proposal names beforehand. No number of any real part is in this file but the one address the
board itself named after the last frame of block type 1."""
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
import s1b2_judge  # noqa: E402
import s1b4a_layout as lay  # noqa: E402
import status_seen  # noqa: E402
import test_s1a_run as fake  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2_end import once, the_set as sets_made  # noqa: E402

KNOWN = fake.KNOWN
STAGE = "s1b5a"
B = 0x01000000                                       # named by the board after 0x00c0027f (S1b.4, run 20)
REF = 0x00000B99
ABOVE = 0x01800000                                   # the first address above the envelope
H1, H2 = 0x7F000001, 0x7F000002                      # places without an address of their own (the twin's SM_SHOWS)
SHORT = list(range(B, B + 3))                        # invented: three frames and no more
# name: which place follows which, what the register shows at a place that is not its own number, the frames there are
MODELS = {
    "it goes on": ({}, {}, list(range(B, B + 80))),
    "every frame all zero": ({}, {}, []),
    "a few frames and then above the envelope": ({SHORT[-1]: ABOVE}, {}, SHORT + [ABOVE]),
    "a few frames, a standstill, and then above the envelope": ({SHORT[-1]: H1, H1: H2, H2: ABOVE}, {H1: SHORT[-1], H2: ABOVE}, SHORT + [H1, H2, ABOVE]),
    "the first address names the one above the envelope": ({B: ABOVE}, {}, [B, ABOVE]),
    "the register does not move at the first address": ({B: H1, H1: H2, H2: B + 1}, {H1: B, H2: B}, [B, H1, H2, B + 1]),
    "an address of block type 1 is named": ({B + 2: 0x00800000}, {}, list(range(B, B + 10)) + [0x00800000, 0x00800001]),
    "the first address names address 0": ({B: 0}, {}, [B, 0, 1]),
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
    out = Path(scratch_dirs.mkdtemp(prefix="sm5a_")) / "run"
    out.mkdir()
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", STAGE)
    verdict = json.loads((out / "verdict.json").read_text())
    streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
    written = {s[k + 1] for s in streams for k in range(len(s) - 1) if s[k] == 0x30002001}
    return rec, verdict, written, out


def the(model: str):
    return once(f"s1b5a / {model}", lambda: go(model))


class TheSet(unittest.TestCase):
    def test_it_is_the_set_of_the_run_into_block_type_1_with_two_words_changed(self) -> None:
        p = [int(w, 16) for w in the_set()["params"]]
        q = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b4a"]["expected"].read_text())["params"]]
        self.assertEqual([k for k in range(32) if p[k] != q[k]], [4, 16], "the envelope's upper end and the start")
        self.assertEqual((p[3], p[4], p[16]), (0, 0x017FFFFF, 0x01000000))
        self.assertEqual((p[2], p[5], p[7], p[8], p[10], p[12], p[13], p[15]), (4, REF, 2, 0, 1, 64, 16, 2 << 8),
                         "the walk, the reference frame, two passes, one standstill a pass, 64 frames, the wait that touches no memory")
        self.assertEqual((p[16] >> 23, p[4] >> 23, (p[4] + 1) >> 23, p[4] + 1), (2, 2, 3, ABOVE), "block type 2 from its first address to its last and nothing above it")
        self.assertTrue(p[3] <= p[5] <= p[4], "the prober wants the reference frame inside the envelope")
        self.assertIs(s1a_run.STAGES[STAGE]["judge"], s1b2_judge)

    def test_the_start_is_the_address_the_board_named_after_block_type_1(self) -> None:
        rows = json.loads((ROOT / "evidence" / "s1b4_17A6_2026-11-18" / "rows.json").read_text())
        self.assertEqual((rows["chain"]["state"], rows["end"]["reached"]), ("complete", True))
        self.assertEqual(the_set()["params"][16], rows["end"]["named_after_the_last_frame"][2:])
        self.assertNotIn(rows["end"]["named_after_the_last_frame"], {s["far"] for s in rows["addresses"]}, "named there, and not read")

    def test_the_image_that_ran_is_the_one_that_had_been_on_the_board(self) -> None:
        """Until 2026-11-20 this held the set's own image to that hash: the step was made with the image as it was. S2.0
        brought a new image (docs/s2_plan.md, section 13), so the set as it is built today names another. What stays
        true, and is held here, is what ran: the image kept beside this step's run is the one kept with the chain
        before it, and the run's record shows that image in RAM."""
        import hashlib
        ran = (ROOT / "evidence" / "s1b5a_17A6_2026-11-19" / "prober.bin").read_bytes()
        kept = (ROOT / "evidence" / "s1b4_17A6_2026-11-18" / "prober.bin").read_bytes()
        self.assertEqual(hashlib.sha256(ran).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        self.assertEqual(ran, kept)
        self.assertEqual((the_set()["image_bytes"], the_set()["image_crc32"]),
                         (len(s1a_run.IMAGE.read_bytes()), f"{zlib.crc32(s1a_run.IMAGE.read_bytes()) & 0xFFFFFFFF:08x}"), "the set names the image as it is built now")

    def test_nothing_of_it_is_given_at_run_time(self) -> None:
        with self.assertRaises(ValueError):
            s1a_run.with_start(STAGE, the_set(), B, "x")
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE]
        r = subprocess.run(prog + ["--start", "1000000", "--dry-run"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, "REFUSED: the starting address of s1b5a is fixed"))
        r = subprocess.run(prog + ["--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        for line in ("mw.l 10100010 017fffff 1", "mw.l 10100014 00000b99 1", "mw.l 10100028 00000001 1", "mw.l 10100040 01000000 1", "mw.l 1010003c 00000200 1"):
            self.assertIn(line, r.stdout)
        self.assertNotIn("mw.l 1010000c", r.stdout, "the envelope begins at 0: that word is left as the zeroing made it")
        other = subprocess.run(prog[:-1] + ["s1b4a", "--dry-run"], capture_output=True, text=True).stdout
        self.assertEqual([(a, b) for a, b in zip(r.stdout.splitlines(), other.splitlines()) if a != b and "mw.l 101000" in a],
                         [(a, b) for a, b in zip(r.stdout.splitlines(), other.splitlines()) if "mw.l 10100010" in a or "mw.l 10100040" in a],
                         "of the words written for the prober, only those two differ from the run into block type 1")


class TheRun(unittest.TestCase):
    def test_a_stretch_of_frames_is_walked_as_any_other(self) -> None:
        rec, v, written, _ = the("it goes on")
        self.assertEqual((rec["verdict"], rec["problems"], v["header"]["status"], v["header"]["anomalies"]), ("PASS", [], "0x1", 0))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], list(range(B, B + 64)))
        self.assertEqual(v["passes"], [{"frames": 64, "ended": LIMIT, "last_address_named": h(B + 64)}] * 2)
        self.assertEqual((v["frames_without_a_second_path"], v["standstills"]), ([], []))

    def test_no_address_is_written_but_the_reference_frame_and_what_the_device_named(self) -> None:
        for model in MODELS:
            with self.subTest(model):
                _, v, written, _ = the(model)
                named = {B} | {int(s["next"], 16) for s in v["walk"]}
                self.assertIn(REF, written)
                self.assertTrue(written - {REF} <= named, sorted(h(a) for a in written - {REF} - named))
                self.assertTrue(all(B <= a < ABOVE for a in written - {REF}), "nothing below block type 2 but the reference frame, and nothing above it")

    def test_a_block_type_of_a_few_frames_is_an_answer(self) -> None:
        for model, stood in (("a few frames and then above the envelope", False), ("a few frames, a standstill, and then above the envelope", True)):
            with self.subTest(model):
                rec, v, written, _ = the(model)
                self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
                self.assertEqual(v["passes"], [{"frames": 3, "ended": LEFT, "last_address_named": h(ABOVE)}] * 2)
                self.assertEqual((max(written), bool(v["walk"][-1].get("stood_still")), len(v["standstills"])), (SHORT[-1], stood, int(stood)))

    def test_one_frame_and_then_above_the_envelope(self) -> None:
        rec, v, written, _ = the("the first address names the one above the envelope")
        self.assertEqual((rec["verdict"], rec["problems"], v["frames_walked"]), ("PASS", [], 1))
        self.assertEqual(v["passes"], [{"frames": 1, "ended": LEFT, "last_address_named": h(ABOVE)}] * 2)
        self.assertEqual(sorted(written), [REF, B], "what was named above the envelope is not read")

    def test_a_register_that_does_not_move_stops_the_run_at_the_first_address(self) -> None:
        rec, v, written, out = the("the register does not move at the first address")
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], v["passes"][0]["last_address_named"]), ("FAIL", "0x800", 1, h(B)))
        self.assertEqual(sorted(written), [REF, B])
        self.assertEqual((rec.get("stop"), rec["card_verified"], (out / "result.bin").exists()), (None, True, True), "stored whole all the same")

    def test_a_name_that_leads_back_below_block_type_2_stops_the_run(self) -> None:
        """The envelope begins at 0, because the reference frame has to lie in it: block types 0 and 1 are inside it.
        The walk is given nothing below its start all the same — an address that is not above the one before is not
        followed."""
        rec, v, written, _ = the("an address of block type 1 is named")
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], v["passes"][0]["last_address_named"]), ("FAIL", "0x800", 3, h(0x00800000)))
        self.assertEqual(sorted(written), [REF] + list(range(B, B + 3)))
        rec, v, written, _ = the("the first address names address 0")
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], sorted(written)), ("FAIL", "0x800", 1, [REF, B]))

    def test_what_the_walk_does_not_expect_stops_it_there_and_is_stored(self) -> None:
        for fault, status, walked in (("padnz@8", "0x711", 3), ("short@12", "0x710", 5), ("flip@9", "0x712", 64), ("err@9", "0x221", 0), ("timeout@11", "0x222", 0),
                                      ("drop@9", "0x223", 0), ("farflip@10", "0x800", 5)):
            with self.subTest(fault=fault):
                rec, v, written, out = go("it goes on", fault)
                self.assertEqual((rec["verdict"], v["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "FAIL", status, walked))
                self.assertTrue(all(a == REF or B <= a < B + 64 for a in written), sorted(h(a) for a in written))
                self.assertEqual((rec.get("stop"), rec["card_verified"], (out / "result.bin").exists()), (None, True, True))

    def test_which_endings_have_the_reference_frame_read_after_the_last_read_in_block_type_2(self) -> None:
        """Not all of them (plan section 60). A run that is walked to its end reads the reference frame last. One that
        the walk stops for something that is not a failure of the interface reads it once more and stops. One stopped
        because the register does not go on, or by a failure of the interface, ends on the read in block type 2: such a
        result does not show that block type 0 could still be read afterwards."""
        def after(v) -> list[str]:
            kinds = [r["kind"] for r in v["records"]]
            last = max(i for i, k in enumerate(kinds) if k == "target")
            return kinds[last + 1:]
        for model in ("it goes on", "a few frames and then above the envelope", "the first address names the one above the envelope"):
            v = the(model)[1]
            self.assertEqual((v["verdict"], after(v)), ("PASS", ["final"]), model)
        for model in ("the register does not move at the first address", "the first address names address 0"):
            v = the(model)[1]
            self.assertEqual((v["header"]["status"], after(v), [r["kind"] for r in v["records"]]), ("0x800", [], ["baseline", "target", "target"]), model)
        for fault, status in (("err@9", "0x221"), ("err@17", "0x221"), ("timeout@11", "0x222"), ("drop@9", "0x223")):
            v = go("it goes on", fault)[1]
            self.assertEqual((v["header"]["status"], after(v)), (status, []), fault)
            self.assertEqual([r["kind"] for r in v["records"]].count("baseline"), 1)
        for fault, status in (("padnz@8", "0x711"), ("short@12", "0x710"), ("flip@9", "0x712")):
            v = go("it goes on", fault)[1]
            self.assertEqual((v["header"]["status"], after(v)), (status, ["health"]), fault)

    def test_the_result_is_not_one_of_the_run_into_block_type_1(self) -> None:
        _, _, _, out = the("it goes on")
        raw = (out / "result.bin").read_bytes()
        import struct
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        mine = [int(w, 16) for w in the_set()["params"]]
        self.assertEqual(s1b2_judge.judge(words, KNOWN, mine)["verdict"], "PASS")
        other = [int(w, 16) for w in json.loads(s1a_run.STAGES["s1b4a"]["expected"].read_text())["params"]]
        self.assertNotEqual(s1b2_judge.judge(words, KNOWN, other)["verdict"], "PASS", "neither the start nor the envelope the prober echoed is that set's")
        other[16] = B
        self.assertNotEqual(s1b2_judge.judge(words, KNOWN, other)["verdict"], "PASS", "with the start made the same, the envelope still is not")


class WhatIsMadeOfTheRun(unittest.TestCase):
    """The two programs run over the result on the board, here over the twin's: neither was changed for this step."""

    def test_the_layout_names_block_type_2(self) -> None:
        out = lay.layout(the("it goes on")[1])
        self.assertEqual((out["run"]["verdict"], out["frames"], out["first"], out["last"], out["block_types"], out["frames_per_row"]),
                         ("PASS", 64, h(B), h(B + 63), [2], [[2, "top", 0, 64]]))
        self.assertEqual((out["end"]["reached"], out["standstills"], out["unexpected"], out["rows"][0]["ended_by"]), (False, [], [], "not ended"))

    def test_the_layout_of_a_block_type_of_a_few_frames(self) -> None:
        out = lay.layout(the("a few frames, a standstill, and then above the envelope")[1])
        self.assertEqual(out["end"], {"reached": True, "last_frame": h(SHORT[-1]), "named_after_the_last_frame": h(ABOVE), "after_a_standstill": True,
                                      "that_address": {"block_type": 3, "half": "top", "row": 0, "column": 0, "minor": 0}})
        self.assertEqual((out["frames_per_row"], out["rows"][0]["walked_whole"], out["unexpected"]), ([[2, "top", 0, 3]], True, []))
        one = lay.layout(the("the first address names the one above the envelope")[1])
        self.assertEqual((one["frames"], one["end"]["reached"], one["end"]["named_after_the_last_frame"], one["frames_per_row"]), (1, True, h(ABOVE), [[2, "top", 0, 1]]))

    def test_the_layout_of_a_run_that_stopped_is_called_that(self) -> None:
        out = lay.layout(the("the register does not move at the first address")[1])
        self.assertEqual((out["run"]["verdict"], out["run"]["status"], out["frames"], out["end"]["reached"]), ("FAIL", "0x800", 1, False))
        self.assertIn("is not a finding", out["note"])

    def test_frames_that_are_all_alike_are_said_to_be(self) -> None:
        rec, v, _, _ = the("every frame all zero")
        out = lay.layout(v)
        self.assertEqual((rec["verdict"], out["content"]["frames_not_all_zero"], out["content"]["distinct_contents"]), ("PASS", 0, 1))
        self.assertIn("says nothing about which frame either read", out["content"]["note"])

    def test_the_listing_of_status_bits_reads_such_a_run(self) -> None:
        _, v, _, out = the("it goes on")
        s = status_seen.seen(v)
        self.assertEqual((s["bits"], s["status_words"]), ([], 2 + sum(len(r["int_sts"]) for r in v["records"])), "the twin shows nothing but the usual")
        marked = json.loads(json.dumps(v))                                       # as if a bit had shown at the first read of a frame there
        first = next(i for i, r in enumerate(marked["records"]) if r["kind"] == "target" and r["frames"])
        for r in marked["records"][first:]:
            r["int_sts"] = [f"{int(x, 16) | 1 << 9:08x}" for x in r["int_sts"]]
        marked["records"][first]["int_sts"][0] = v["records"][first]["int_sts"][0]
        marked["header"]["int_sts_final"] = f"{int(v['header']['int_sts_final'], 16) | 1 << 9:08x}"
        (b,) = status_seen.seen(marked)["bits"]
        self.assertEqual((b["bit"], b["name"], b["first"]["record"], b["first"]["far"], b["stayed_once_it_showed"], b["in_the_last_word"]),
                         (9, None, first, h(B), True, True), "a bit the program has no name for, listed from the first read of a frame on")
        p = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "status_seen.py"), str(out)], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["bits"], json.loads(p.stdout)["runs"]), (0, [], 1))


if __name__ == "__main__":
    unittest.main()

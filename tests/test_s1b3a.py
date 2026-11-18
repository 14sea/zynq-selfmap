"""S1b.3a: a walk that crosses the end of a row (docs/s1b_plan.md, section 35) — the prober's walk with a standstill
allowed, through the run script on the twin behind the pretended board; its judge; and the program that holds such a
run against the stored row. The twin's ends of a row are those of S1b.2b's tests; which of them a device has is not
assumed here, and no number of any real part is in this file but the addresses the board itself named."""
from __future__ import annotations

import ast
import hashlib
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
import s1a_run  # noqa: E402
import s1b1_judge  # noqa: E402
import s1b2_closed  # noqa: E402
import s1b2_judge  # noqa: E402
import s1b3a_seam as seam  # noqa: E402
import test_s1a_run as fake  # noqa: E402
import test_s1b2_closed as closed_tests  # noqa: E402
import test_s1b2_end as at  # noqa: E402
from test_prober_s1b1 import frames_for  # noqa: E402
from test_s1b2_end import BOTH, COLUMN, ENDS, H1, H2, LAST, NEXT_ROW, NONE, ONE, TWO, h, once  # noqa: E402

KNOWN = at.KNOWN
HDR, REC, FARBLK = s1b1_judge.HDR, s1b1_judge.REC, 68
BEYOND = list(range(NEXT_ROW, NEXT_ROW + 30))
MODEL = COLUMN + [H1, H2] + BEYOND
H3, H4, H5, H6 = 0x7F000003, 0x7F000004, 0x7F000005, 0x7F000006
# three ends of rows close together, each as the board's was (two places, the register still at the first): after
# 0x1ba9, after the first address beyond it, and after the third — pieces of 4, 1, 2 and the rest from 0x1ba6
SEVERAL = ({LAST: H1, H1: H2, H2: NEXT_ROW, NEXT_ROW: H3, H3: H4, H4: NEXT_ROW + 1, NEXT_ROW + 2: H5, H5: H6, H6: NEXT_ROW + 3},
           {H1: LAST, H2: NEXT_ROW, H3: NEXT_ROW, H4: NEXT_ROW + 1, H5: NEXT_ROW + 2, H6: NEXT_ROW + 3})


def sha(words: list[int]) -> str:
    return hashlib.sha256(b"".join(struct.pack(">I", w) for w in words)).hexdigest()


def the_set() -> dict:
    at.the_set("s1b2")                               # builds the image and writes the sets, once
    return json.loads(s1a_run.STAGES["s1b3a"]["expected"].read_text())


def go(end=TWO, fault: str = "", frames: dict | None = None, **words):
    """One run of the set through the run script on the pretended board; `words` replaces words of the parameter
    block (w10=2, w4=0x1ffff, ...). Returns the run record, the verdict, the board, the directory and the block."""
    succ, shows = ENDS[end] if isinstance(end, str) else end
    exp = the_set()
    params = [int(w, 16) for w in exp["params"]]
    for key, value in words.items():
        params[int(key[1:])] = value
    exp["params"] = [f"{w:08x}" for w in params]
    pl = s1a_run.PL.read_bytes()
    u = fake.FakeUBoot(fault, far_rule="skip", succ=succ, shows=shows, frames=frames_for(MODEL + [H3, H4, H5, H6]) if frames is None else frames)
    out = Path(scratch_dirs.mkdtemp(prefix="sm3a_")) / "run"
    out.mkdir()
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), KNOWN, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000001.bin", "s1b3a")
    verdict = json.loads((out / "verdict.json").read_text()) if (out / "verdict.json").exists() else None
    return rec, verdict, u, out, params


def the(end: str = TWO):
    return once(f"s1b3a / {end}", lambda: go(end))


def written(u) -> set[int]:
    """Every address a stream of this run wrote to the address register."""
    streams = [[int(x, 16) for x in line.split()[1:]] for line in u.twin_lines if line.startswith("STREAM")]
    return {s[k + 1] for s in streams for k in range(len(s) - 1) if s[k] == 0x30002001}


def delivered(v: dict) -> set[str]:
    return {x for r in v["records"] for x in r["frame_sha256"]}


def groups(sizes: list[int]) -> list[tuple[int, int]]:
    """(place in the list, frames) of every read of several frames, the list cut into pieces of these sizes."""
    out, first = [], 0
    for n in sizes:
        for k in range(0, n, 3):
            if n - k >= 3:
                out.append((first + k, 3))
            elif n >= 3:
                out.append((first + n - 3, 3))
            elif n == 2:
                out.append((first, 2))
        first += n
    return out


class TheSet(unittest.TestCase):
    def test_it_is_the_walks_set_with_the_three_differences_that_were_proposed(self) -> None:
        p, row = [int(w, 16) for w in the_set()["params"]], [int(w, 16) for w in at.the_set("s1b2")["params"]]
        self.assertEqual([k for k in range(32) if p[k] != row[k]], [4, 10, 16], "the envelope's upper end, the allowance, the start")
        self.assertEqual((p[3], p[4], p[10], p[16]), (0, 0x007FFFFF, 1, 0x1B80))
        self.assertEqual((p[2], p[5], p[7], p[8], p[12], p[13], p[15]), (4, 0xB99, 2, 0, 64, 16, 2 << 8), "the walk, two passes, 64 frames, the wait that touches no memory")
        self.assertEqual(p[4] >> 23, 0, "block type 0 and nothing above it")
        self.assertEqual((p[4] + 1) >> 23, 1)
        self.assertIs(s1a_run.STAGES["s1b3a"]["judge"], s1b2_judge)
        with self.assertRaises(ValueError):
            s1a_run.with_start("s1b3a", the_set(), 0x1B80, "x")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s1b3a", "--start", "1b80", "--dry-run"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, "REFUSED: the starting address of s1b3a is fixed"))
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", "s1b3a", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        for line in ("mw.l 10100010 007fffff 1", "mw.l 10100028 00000001 1", "mw.l 10100040 00001b80 1", "mw.l 1010003c 00000200 1"):
            self.assertIn(line, r.stdout)

    def test_every_other_set_asks_for_no_standstill(self) -> None:
        the_set()
        for name, entry in s1a_run.STAGES.items():
            p = [int(w, 16) for w in json.loads(entry["expected"].read_text())["params"]]
            if p[2] == 4 and name not in ("s1b3a", "s1b3", "s1b4a", "s1b4"):
                self.assertEqual(p[10], 0, name)


class TheWalkAcrossAnEnd(unittest.TestCase):
    def test_the_end_the_board_showed_is_crossed(self) -> None:
        for end in (TWO, ONE):                       # two places, the register still at the first (the board's registers); and one place
            with self.subTest(end=end):
                rec, v, u, _, _ = the(end)
                self.assertEqual((rec["verdict"], rec["problems"], v["header"]["status"], v["header"]["anomalies"]), ("PASS", [], "0x1", 0))
                want = COLUMN + BEYOND[:22]
                self.assertEqual([int(s["far"], 16) for s in v["walk"]], want, "the 42 frames of the column, then 22 by the names the device gave")
                self.assertEqual([int(s["next"], 16) for s in v["walk"]], want[1:] + [NEXT_ROW + 22])
                self.assertEqual([s["far"] for s in v["walk"] if s.get("stood_still")], [h(LAST)])
                self.assertEqual(v["standstills"], [{"at": h(LAST), "register_after_the_pad_alone": h(LAST), "register_after_the_frame": h(NEXT_ROW)}])
                self.assertEqual((v["pieces"], v["params"]["standstills_a_pass_may_cross"]), ([42, 22], 1))
                self.assertEqual(v["passes"], [{"frames": 64, "ended": "the limit of frames was reached", "last_address_named": h(NEXT_ROW + 22)}] * 2)
                self.assertEqual(v["frames_without_a_second_path"], [])
                # the reads of several frames: within each piece, none across the place where the register stood still
                several = [(int(r["far"], 16), r["frames"]) for r in v["records"] if r["read"] == "read of several frames"]
                self.assertEqual(several, [(want[k], n) for k, n in groups([42, 22])])
                self.assertEqual(len(several), 14 + 8)
                # nothing was delivered from a place the device did not name, and nothing written that it did not name
                frames = frames_for(MODEL)
                self.assertEqual(delivered(v) & {sha(frames[H1]), sha(frames[H2])}, set())
                self.assertEqual(delivered(v), {sha(frames[a]) for a in want} | {sha(KNOWN_FRAME)})
                self.assertEqual(written(u), set(want) | {0xB99})
                self.assertEqual([line for line in u.twin_lines if line.startswith("VIOLATION")], [])
                self.assertGreater(v["register_cross_checks"], 2 * 62)

    def test_what_follows_the_first_address_of_the_next_row_is_whatever_the_device_names(self) -> None:
        # the two ends give the same registers at the end of the row and differ in nothing the walk reads afterwards;
        # an end where the first address beyond is itself one at which the register stands still is the next test
        a, b = the(TWO)[1], the(ONE)[1]
        self.assertEqual([(s["far"], s["next"]) for s in a["walk"]], [(s["far"], s["next"]) for s in b["walk"]])
        self.assertEqual(a["walk"][42], {"far": h(NEXT_ROW), "next": h(NEXT_ROW + 1), "register_after_the_frame": h(NEXT_ROW + 2), "frame_sha256": sha(frames_for(MODEL)[NEXT_ROW])})

    def test_an_end_where_the_register_stands_still_for_longer_halts_as_before(self) -> None:
        rec, v, u, _, _ = the(BOTH)
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "0x800", 42))
        self.assertTrue(any("the run did not complete: status 0x800" in p for p in v["problems"]))
        self.assertEqual((v["standstills"], v["walk"][-1]["next"]), ([], h(LAST)), "no standstill was accepted: the register was not above after the frame")
        self.assertLessEqual(max(written(u) - {0xB99}), LAST)

    def test_an_end_without_a_standstill_is_walked_straight_on(self) -> None:
        rec, v, _, _, _ = the(NONE)
        self.assertEqual((rec["verdict"], v["standstills"], v["pieces"], len(v["walk"])), ("PASS", [], [64], 64))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], COLUMN + BEYOND[:22])
        self.assertNotIn("stood_still", json.dumps(v["walk"]))

    def test_without_the_allowance_the_walk_stops_where_it_always_did(self) -> None:
        rec, v, u, _, _ = go(TWO, w10=0)
        stored = json.loads((ROOT / "evidence" / "s1b2_17A6_2026-11-15" / "run30" / "verdict.json").read_text())
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "0x800", 42))
        self.assertEqual([(r["far"], r["frames"], r["far_read_back"]) for r in v["records"][-6:]], [(r["far"], r["frames"], r["far_read_back"]) for r in stored["records"][-6:]])
        self.assertEqual(v["problems"], stored["problems"])
        self.assertEqual(sorted(k for k in v if k not in stored), [], "nothing is said that was not said before")
        self.assertNotIn("standstills_a_pass_may_cross", v["params"])

    def test_one_standstill_more_than_allowed_stops_the_run(self) -> None:
        rec, v, u, _, _ = go(SEVERAL, w16=0x1BA6, w12=16)                        # allowance 1; the second standstill is at the first address beyond
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"]), ("FAIL", "0x900", 5))
        self.assertEqual(v["problems"], [f"after the frame at {h(NEXT_ROW)} the register held {h(NEXT_ROW + 1)}, but the device names {h(NEXT_ROW)} after {h(NEXT_ROW)}",
                                         "the run did not complete: status 0x900 (the register stood still at one address more than a pass may cross)"],
                         "the header and the records agree on that stop; the other thing said is what is said of every stop at an address that names itself")
        self.assertEqual(v["passes"][0], {"frames": 5, "ended": "not ended", "last_address_named": h(NEXT_ROW)})
        self.assertEqual((v["standstills"], v["walk"][-1]["next"]), ([{"at": h(LAST), "register_after_the_pad_alone": h(LAST), "register_after_the_frame": h(NEXT_ROW)}], h(NEXT_ROW)))
        self.assertEqual(int(v["header"]["stop_record"], 16), [r["index"] for r in v["records"] if r["far"] == h(NEXT_ROW) and r["read"] == "successor read"][0])
        self.assertEqual(max(written(u)), NEXT_ROW, "nothing above the address it stopped at was written")

    def test_several_ends_and_the_pieces_the_list_falls_into(self) -> None:
        rec, v, u, _, _ = go(SEVERAL, w16=0x1BA6, w12=16, w10=3)
        self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
        want = [0x1BA6, 0x1BA7, 0x1BA8, LAST, NEXT_ROW, NEXT_ROW + 1, NEXT_ROW + 2] + list(range(NEXT_ROW + 3, NEXT_ROW + 12))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], want)
        self.assertEqual(([s["far"] for s in v["walk"] if s.get("stood_still")], v["pieces"]), ([h(LAST), h(NEXT_ROW), h(NEXT_ROW + 2)], [4, 1, 2, 9]))
        several = [(int(r["far"], 16), r["frames"]) for r in v["records"] if r["read"] == "read of several frames"]
        self.assertEqual(several, [(0x1BA6, 3), (0x1BA7, 3), (NEXT_ROW + 1, 2), (NEXT_ROW + 3, 3), (NEXT_ROW + 6, 3), (NEXT_ROW + 9, 3)],
                         "four: three and the last three again; one: none; two: both; nine: three threes")
        self.assertEqual(several, [(want[k], n) for k, n in groups([4, 1, 2, 9])])
        self.assertEqual(v["frames_without_a_second_path"], [h(NEXT_ROW)], "a piece of one frame has no second path, and the judge lists it")
        frames = frames_for(MODEL + [H3, H4, H5, H6])
        self.assertEqual(delivered(v) & {sha(frames[x]) for x in (H1, H2, H3, H4, H5, H6)}, set())
        rec, v, _, _, _ = go(SEVERAL, w16=0x1BA6, w12=16, w10=2)
        self.assertEqual((rec["verdict"], v["header"]["status"], v["frames_walked"], len(v["standstills"])), ("FAIL", "0x900", 7, 2))

    def test_a_standstill_that_leaves_the_envelope_ends_the_pass_as_left(self) -> None:
        rec, v, u, _, _ = go(TWO, w4=0x0001FFFF)                                 # the row as the envelope, as S1b.2 had it
        self.assertEqual((rec["verdict"], rec["problems"]), ("PASS", []))
        self.assertEqual(v["passes"], [{"frames": 42, "ended": "the device named an address outside the envelope", "last_address_named": h(NEXT_ROW)}] * 2)
        self.assertEqual((v["pieces"], len(v["standstills"]), v["walk"][-1]["next"], v["walk"][-1]["stood_still"]), ([42], 1, h(NEXT_ROW), True))
        self.assertEqual(max(written(u)), LAST, "the address beyond the envelope is named, not written")

    def test_a_standstill_at_the_limit(self) -> None:
        rec, v, _, _, _ = go(TWO, w12=42)
        self.assertEqual((rec["verdict"], v["pieces"]), ("PASS", [42]))
        self.assertEqual(v["passes"], [{"frames": 42, "ended": "the limit of frames was reached", "last_address_named": h(NEXT_ROW)}] * 2)

    def test_more_standstills_than_the_prober_takes_is_refused(self) -> None:
        rec, v, u, _, _ = go(TWO, w10=5)
        self.assertEqual((rec["verdict"], v["header"]["status"]), ("FAIL", "0x500"))
        self.assertEqual(written(u), set(), "nothing was sent to the device")

    def test_faults_stop_such_a_run_as_they_stop_any_walk(self) -> None:
        for fault, status in (("err@90", "0x221"), ("flip@95", "0x712")):
            with self.subTest(fault=fault):
                rec, v, _, _, _ = go(TWO, fault=fault)
                self.assertEqual((rec["verdict"], v["header"]["status"]), ("FAIL", status))


KNOWN_FRAME = [int(w, 16) for w in KNOWN["frames"]["0x00000b99"]["words"]]


class TheJudgeOfSuchARun(unittest.TestCase):
    def words(self, end: str = TWO) -> tuple[list[int], list[int]]:
        _, _, _, out, params = the(end)
        raw = (out / "result.bin").read_bytes()
        return list(struct.unpack("<%dI" % (len(raw) // 4), raw)), list(params)

    def record(self, words: list[int], far: int, op: int, repeat: int = 0) -> int:
        n = words[3]
        return [i for i in range(n) if (words[HDR + i * REC], words[HDR + i * REC + 15], words[HDR + i * REC + 12], words[HDR + i * REC + 1]) == (far, op, repeat, 0)][0]

    def test_the_stored_verdict_is_what_the_judge_gives(self) -> None:
        words, params = self.words()
        v = s1b2_judge.judge(words, KNOWN, params)
        self.assertEqual((json.loads(json.dumps(v)), v["verdict"]), (the(TWO)[1], "PASS"))

    def test_a_result_relabelled_as_one_without_the_allowance_is_not_a_walk_that_passed(self) -> None:
        words, params = self.words()
        words[32 + 10] = params[10] = 0
        v = s1b2_judge.judge(words, KNOWN, params)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("the header's status is 0x1; the records imply 0x800", v["problems"])
        words, params = self.words()
        params2 = list(params); params2[10] = 0                                 # the plan had no allowance; the prober was given one
        self.assertTrue(any("the parameters the prober echoed are not the planned ones (word(s) [10])" in p for p in s1b2_judge.judge(words, KNOWN, params2)["problems"]))

    def test_the_standstill_is_rederived_from_the_two_records(self) -> None:
        words, params = self.words()
        s0, c0 = self.record(words, LAST, s1b1_judge.SUCC), self.record(words, LAST, s1b1_judge.CONTENT)
        self.assertEqual((words[HDR + s0 * REC + FARBLK + 4], words[HDR + c0 * REC + FARBLK + 4]), (LAST, NEXT_ROW))
        moved = list(words); moved[HDR + c0 * REC + FARBLK + 4] = LAST          # after the frame the register is not above: no end of a row
        v = s1b2_judge.judge(moved, KNOWN, params)
        self.assertIn("the header's status is 0x1; the records imply 0x800", v["problems"])
        named = list(words); named[HDR + s0 * REC + FARBLK + 4] = LAST + 1      # after the pad alone it names the next number: no standstill
        v = s1b2_judge.judge(named, KNOWN, params)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any(f"expected the target successor read of {h(LAST + 1)}" in p for p in v["problems"]), v["problems"][:3])
        other = list(words); other[HDR + c0 * REC + FARBLK + 4] = NEXT_ROW + 7  # another address above: the walk would have gone there
        v = s1b2_judge.judge(other, KNOWN, params)
        self.assertTrue(any(f"expected the target successor read of {h(NEXT_ROW + 7)}" in p for p in v["problems"]), v["problems"][:3])

    def test_the_second_pass_has_to_stand_still_where_the_first_did(self) -> None:
        words, params = self.words()
        c1 = self.record(words, LAST, s1b1_judge.CONTENT, repeat=1)
        other = list(words); other[HDR + c1 * REC + FARBLK + 4] = NEXT_ROW + 1
        v = s1b2_judge.judge(other, KNOWN, params)
        self.assertIn(f"record {c1}: code 0x0, but its raw words say 0x13", v["problems"])

    def test_the_register_after_a_read_that_ends_at_the_standstill(self) -> None:
        words, params = self.words()
        t = self.record(words, LAST - 2, s1b1_judge.TRIPLE, repeat=2)
        self.assertEqual(words[HDR + t * REC + FARBLK + 4], NEXT_ROW, "the three frames up to the last of the row: the register as after the single read of the last")
        other = list(words); other[HDR + t * REC + FARBLK + 4] = NEXT_ROW + 1
        v = s1b2_judge.judge(other, KNOWN, params)
        self.assertEqual(v["problems"], [f"after the 3 frames from {h(LAST - 2)} the register held {h(NEXT_ROW + 1)}, but {h(NEXT_ROW)} after the single read of their last, {h(LAST)}"])
        s = self.record(words, LAST - 1, s1b1_judge.CONTENT)                    # the frame before the last: the register is one step short, as the board showed
        self.assertEqual(words[HDR + s * REC + FARBLK + 4], LAST)
        other = list(words); other[HDR + s * REC + FARBLK + 4] = NEXT_ROW
        v = s1b2_judge.judge(other, KNOWN, params)
        self.assertIn(f"after the frame at {h(LAST - 1)} the register held {h(NEXT_ROW)}, but the device names {h(LAST)} after {h(LAST)}", v["problems"])

    def test_a_read_of_several_frames_across_the_standstill_is_not_the_schedule(self) -> None:
        words, params = self.words()
        t = self.record(words, LAST - 2, s1b1_judge.TRIPLE, repeat=2)
        across = list(words); across[HDR + t * REC] = LAST - 1                  # relabelled: three frames from the last but one
        v = s1b2_judge.judge(across, KNOWN, params)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(any(f"record {t}: expected the target read of several frames of {h(LAST - 2)} x3" in p for p in v["problems"]), v["problems"][:3])

    def test_one_word_changed_anywhere_in_the_walk_does_not_pass(self) -> None:
        words, params = self.words()
        for at_word in (HDR + 5 * REC + 100, HDR + 150 * REC + 90, 19, 21):
            other = list(words); other[at_word] ^= 1
            self.assertNotEqual(s1b2_judge.judge(other, KNOWN, params)["verdict"], "PASS", at_word)


class TheRunAgainstTheStoredRow(unittest.TestCase):
    def row(self, end: str = TWO) -> dict:
        return once(f"closed / {end}", lambda: s1b2_closed.close(*closed_tests.parts(end)))

    def test_the_run_and_the_stored_row_agree(self) -> None:
        for end in (TWO, ONE):
            with self.subTest(end=end):
                row, v = self.row(end), the(end)[1]
                self.assertNotIn("refused", row)
                out = seam.against(v, row)
                self.assertEqual((out["run"]["verdict"], out["disagreements"], out["begins_at"]), ("PASS", [], h(0x1B80)))
                self.assertEqual((out["addresses_in_both"], out["same_frames"], out["distinct_contents_among_them"], "note_on_content" in out), (42, 42, 42, False))
                self.assertEqual(out["standstill"], {"at": h(LAST), "after_the_pad_alone": h(LAST), "stored_one_step_beyond": h(LAST),
                                                     "after_the_frame": h(NEXT_ROW), "stored_two_steps_beyond": h(NEXT_ROW)})
                self.assertEqual(out["addresses_the_stored_row_does_not_have"], {"count": 22, "first": h(NEXT_ROW), "last": h(NEXT_ROW + 21), "standstills_among_them": []})

    def test_what_does_not_agree_is_listed(self) -> None:
        row, v = self.row(), the(TWO)[1]
        copy = lambda x: json.loads(json.dumps(x))  # noqa: E731

        def said(change_v=None, change_row=None) -> list[str]:
            a, b = copy(v), copy(row)
            if change_v:
                change_v(a)
            if change_row:
                change_row(b)
            return seam.against(a, b)["disagreements"]
        self.assertEqual(said(), [])
        self.assertTrue(any(d.startswith(f"the frame at {h(0x1B87)}: the run delivered") for d in said(lambda a: a["walk"][7].update(frame_sha256="0" * 64))))
        self.assertEqual(said(lambda a: a["walk"][7].update(next=h(0x1B89))), [f"after {h(0x1B87)} the run was told {h(0x1B89)}, the stored row has {h(0x1B88)}"])
        self.assertEqual(said(lambda a: a["walk"][7].update(stood_still=True)), [f"the run stood still at {h(0x1B87)}, where the stored row has no end"])
        self.assertTrue(any("the run did not stand still there" in d for d in said(lambda a: a["walk"][41].pop("stood_still"))))
        self.assertEqual(said(lambda a: a["walk"][41].update(next=h(NEXT_ROW + 1))), [f"after the standstill at {h(LAST)} the run went on to {h(NEXT_ROW + 1)}; the stored row has {h(NEXT_ROW)} named after it"])
        self.assertTrue(any("one step beyond, the stored row has" in d for d in said(lambda a: a["standstills"][0].update(register_after_the_pad_alone=h(LAST - 1)))))
        self.assertTrue(any("two steps beyond, the stored row has" in d for d in said(lambda a: a["standstills"][0].update(register_after_the_frame=h(NEXT_ROW + 1)))))
        self.assertTrue(any("the run's judge lists 0 standstill(s)" in d for d in said(lambda a: a.update(standstills=[]))))
        self.assertTrue(any("there is no seam" in d for d in said(change_row=lambda b: b.update(addresses=b["addresses"][:5] + b["addresses"][6:]))))
        self.assertEqual(said(lambda a: a.update(walk=[])), ["the run walked nothing"])
        gap = said(lambda a: a.update(walk=a["walk"][:20] + a["walk"][42:], standstills=[]))
        self.assertTrue(any("does not follow the last frame of the stored row" in d for d in gap), gap)
        # a run that did not pass is laid out and said to be no finding; a run that stopped short of the end says so
        failed = copy(v); failed["verdict"] = "FAIL"
        self.assertIn("the judge did not pass this run", seam.against(failed, row)["note"])
        short = copy(v); short["walk"] = short["walk"][:10]; short["standstills"] = []
        out = seam.against(short, row)
        self.assertEqual((out["disagreements"], out["note_on_the_end"], out["addresses_the_stored_row_does_not_have"]["count"]), ([], "the run did not reach the last frame of the stored row", 0))
        same = copy(v); [s.update(frame_sha256="1" * 64) for s in same["walk"]]
        zero = copy(row); [s.update(frame_sha256="1" * 64) for s in zero["addresses"]]
        self.assertIn("says nothing about which frame either read", seam.against(same, zero)["note_on_content"])

    def test_through_the_command_line(self) -> None:
        row, (_, v, _, out, _) = self.row(), the(TWO)
        (out / "row_closed.json").write_text(json.dumps(row))
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b3a_seam.py")]
        p = subprocess.run(prog + [str(out / "verdict.json"), str(out / "row_closed.json")], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, seam.against(v, row)))
        bad = json.loads(json.dumps(v)); bad["walk"][3]["frame_sha256"] = "0" * 64
        (out / "bad.json").write_text(json.dumps(bad))
        self.assertEqual(subprocess.run(prog + [str(out / "bad.json"), str(out / "row_closed.json")], capture_output=True).returncode, 1)
        failed = json.loads(json.dumps(v)); failed["verdict"] = "FAIL"
        (out / "failed.json").write_text(json.dumps(failed))
        self.assertEqual(subprocess.run(prog + [str(out / "failed.json"), str(out / "row_closed.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(prog + [str(out / "verdict.json")], capture_output=True).returncode, 2)

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1b3a_seam.py").read_text()
        tree = ast.parse(text)
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 3, 12}, set())
        for word in ("prjxray", "part.json", "frame_count", "1ba", "400000"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib"}, set())


if __name__ == "__main__":
    unittest.main()

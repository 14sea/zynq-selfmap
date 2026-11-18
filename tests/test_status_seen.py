#!/usr/bin/env python3
"""The listing of status bits that are neither an error nor usual (docs/s1b_plan.md, section 54): host only."""
from __future__ import annotations

import json, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import status_seen  # noqa: E402

U, B5 = 0x50033004, 0x50033024


def run(*records, first=0x50021004, last=None) -> dict:
    """A verdict as far as this program reads one: the header's two readings and the status words of each record."""
    recs = [{"kind": "target", "far": f"{0x00800100 + i:#010x}", "frames": 1, "int_sts": [f"{w:08x}" for w in ws]} for i, ws in enumerate(records)]
    return {"header": {"int_sts_initial": f"{first:08x}", "int_sts_final": f"{(records[-1][-1] if last is None else last):08x}"}, "records": recs}


class TheBitsListed(unittest.TestCase):
    def test_a_run_within_the_usual_lists_nothing(self) -> None:
        s = status_seen.seen(run([U, U, U], [U, U]))
        self.assertEqual((s["bits"], s["status_words"]), ([], 7), "five words of the records and the header's two")

    def test_what_the_masks_are_is_written_here_and_not_taken_from_the_program(self) -> None:
        self.assertEqual((status_seen.USUAL, status_seen.ERR_MASK), (0x50033004, 0x00F4C840))
        self.assertEqual(status_seen.USUAL & status_seen.ERR_MASK, 0)

    def test_a_bit_that_is_an_error_is_the_judges_business_and_is_not_listed(self) -> None:
        for bit in (6, 11, 14, 15, 18, 20, 21, 22, 23):
            self.assertEqual(status_seen.seen(run([U, U | 1 << bit]))["bits"], [], bit)

    def test_every_other_bit_is_listed_whichever_it_is(self) -> None:
        other = [b for b in range(32) if not (0x50033004 | 0x00F4C840) >> b & 1]
        self.assertEqual(len(other), 16)
        for bit in other:
            s = status_seen.seen(run([U, U], [U, U | 1 << bit, U | 1 << bit]))
            self.assertEqual([b["bit"] for b in s["bits"]], [bit])
        s = status_seen.seen(run([U | 1 << 0 | 1 << 31, U | 1 << 5]))
        self.assertEqual([b["bit"] for b in s["bits"]], [0, 5, 31], "each by itself, in order")

    def test_where_it_first_showed_and_whether_it_stayed(self) -> None:
        s = status_seen.seen(run([U, U], [U, B5, B5], [B5, B5]))
        (b,) = s["bits"]
        self.assertEqual((b["bit"], b["first"]["record"], b["first"]["far"], b["first"]["kind"], b["first"]["frames"]), (5, 1, "0x00800101", "target", 1))
        self.assertEqual(b["first"]["status_words"], ["50033004", "50033024", "50033024"])
        self.assertEqual((b["words_with_it"], b["words"], b["stayed_once_it_showed"], b["in_the_last_word"]), (5, 9, True, True))
        self.assertIn("PCFG_SEU_ERR", b["name"])
        gone = status_seen.seen(run([U, B5], [U, U]))["bits"][0]                 # it showed and was gone again
        self.assertEqual((gone["words_with_it"], gone["stayed_once_it_showed"], gone["in_the_last_word"]), (1, False, False))
        back = status_seen.seen(run([U, B5], [U, B5]))["bits"][0]                # gone and back: it did not stay, and it is there at the end
        self.assertEqual((back["words_with_it"], back["stayed_once_it_showed"], back["in_the_last_word"]), (3, False, True))
        self.assertIsNone(status_seen.seen(run([U, U | 1 << 9]))["bits"][0]["name"], "a bit this program has no name for is listed all the same")

    def test_the_headers_readings_count_too(self) -> None:
        at_first = status_seen.seen(run([U, U], first=0x50021024))["bits"][0]
        self.assertEqual((at_first["first"], at_first["stayed_once_it_showed"]), ({"where": "the header's first reading"}, False))
        at_last = status_seen.seen(run([U, U], last=B5))["bits"][0]
        self.assertEqual((at_last["first"], at_last["words_with_it"], at_last["in_the_last_word"]), ({"where": "the header's last reading"}, 1, True))

    def test_a_verdict_with_little_in_it_is_still_answered(self) -> None:
        self.assertEqual(status_seen.seen({}), {"status_words": 0, "bits": []})
        self.assertEqual(status_seen.seen({"header": None, "records": [{"int_sts": ["50033024"]}]})["bits"][0]["first"],
                         {"where": "a record", "record": 0, "status_words": ["50033024"]})


class OverTheStoredRuns(unittest.TestCase):
    def test_before_s1b4_no_stored_run_has_such_a_bit(self) -> None:
        files = sorted(p for p in (ROOT / "evidence").rglob("verdict.json") if "s1b4_17A6_2026-11-18" not in p.parts)
        self.assertEqual(len(files), 158)
        self.assertEqual([str(f) for f in files if status_seen.seen(json.loads(f.read_text()))["bits"]], [])

    def test_the_chain_over_block_type_1(self) -> None:
        d = ROOT / "evidence" / "s1b4_17A6_2026-11-18"
        got = {f.parent.name: status_seen.seen(json.loads(f.read_text())) for f in status_seen.verdicts(d)}
        self.assertEqual(len(got), 21)
        self.assertEqual(sorted(k for k, s in got.items() if s["bits"]), [f"run{k:02d}" for k in (4, 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20)])
        for k, s in got.items():
            for b in s["bits"]:
                self.assertEqual((b["bit"], b["stayed_once_it_showed"], b["in_the_last_word"], b["first"]["kind"], b["first"]["frames"]), (5, True, True, "target", 1), k)
        self.assertEqual((got["run04"]["bits"][0]["first"]["far"], got["run14"]["bits"][0]["first"]["far"]), ("0x00800100", "0x00c00100"))


class ThroughTheCommandLine(unittest.TestCase):
    def test_files_and_directories(self) -> None:
        prog = [sys.executable, "-B", str(ROOT / "host" / "status_seen.py")]
        tmp = Path(scratch_dirs.mkdtemp(prefix="smseen_"))
        for name, v in (("run00", run([U, U])), ("run01", run([U, B5])), ("run02", run([U, U])), ("other", run([U, B5]))):
            (tmp / name).mkdir(); (tmp / name / "verdict.json").write_text(json.dumps(v))
        p = subprocess.run(prog + [str(tmp)], capture_output=True, text=True)
        d = json.loads(p.stdout)
        self.assertEqual((p.returncode, d["runs"], d["bits"], d["runs_with_such_a_bit"]), (0, 3, [5], [str(tmp / "run01")]), "the runNN of a directory, in order, and nothing else in it")
        self.assertEqual((d["error_mask"], d["usual"], [r["run"] for r in d["by_run"]]), ("0x00f4c840", "0x50033004", [str(tmp / f"run0{k}") for k in range(3)]))
        p = subprocess.run(prog + [str(tmp / "other"), str(tmp / "run00" / "verdict.json")], capture_output=True, text=True)
        d = json.loads(p.stdout)
        self.assertEqual((p.returncode, d["runs"], d["runs_with_such_a_bit"]), (0, 2, [str(tmp / "other")]), "a directory with a verdict of its own; a file")
        for bad in ([], [str(tmp / "missing")], [str(tmp), str(tmp / "missing")]):
            p = subprocess.run(prog + bad, capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stderr), (2, ""), bad)
        (tmp / "empty").mkdir()
        self.assertEqual(subprocess.run(prog + [str(tmp / "empty")], capture_output=True).returncode, 2, "a directory with no verdict in it")


if __name__ == "__main__":
    unittest.main()

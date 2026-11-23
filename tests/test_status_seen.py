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
    READ_COLUMNS_2_TO_4 = ("s1b4_17A6_2026-11-18", "sbit_17A6_2026-11-19")      # the directories whose runs read such frames of block type 1
    S2_2_RUN = "s2_2_17A6_2026-11-22/run03"                                     # and the one run of S2.2 that has such a bit and read none of them
    S2_3_SINGLES = [f"s2_3_17A6_2026-11-23/run{k:02d}" for k in (1, 2, 3, 4)]   # and the four runs of the singles of S2.3 (2026-11-23); its code run has none
    S2_4_PART_2 = [f"s2_4b_17A6_2026-11-23/run{k:02d}" for k in range(4)]       # and the four runs of S2.4, part 2 (2026-11-23); no run of part 1 has one

    def test_no_other_stored_run_has_such_a_bit(self) -> None:
        files = sorted(p for p in (ROOT / "evidence").rglob("verdict.json") if not set(self.READ_COLUMNS_2_TO_4) & set(p.parts))
        self.assertGreaterEqual(len(files), 158, "the 158 verdicts stored before S1b.4, and whatever was stored since elsewhere")
        self.assertEqual([str(f.relative_to(ROOT / "evidence")) for f in files if status_seen.seen(json.loads(f.read_text()))["bits"]],
                         [d + "/verdict.json" for d in [self.S2_2_RUN] + self.S2_3_SINGLES + self.S2_4_PART_2])

    def test_the_one_run_of_block_type_0_that_has_it(self) -> None:
        """S2.2 on 2026-11-22, the run of share 3: bit 5 after two reads next to each other, the same two in each of the
        three states, and nowhere else in the chain's eight runs. Stage 8 clears the bit after such a read, so it does
        not stay. Until then the bit had been seen only when frames of block type 1 were read, under another design."""
        v = json.loads((ROOT / "evidence" / self.S2_2_RUN / "verdict.json").read_text())
        (b,) = status_seen.seen(v)["bits"]
        self.assertEqual((b["bit"], b["words_with_it"], b["stayed_once_it_showed"], b["in_the_last_word"]), (5, 24, False, False))
        self.assertEqual((b["first"]["record"], b["first"]["far"], b["first"]["frames"]), (46, "0x0000181e", 3))
        with_it = [r for r in v["records"] if any(int(w, 16) & 0x20 for w in r["int_sts"])]
        self.assertEqual([(r["index"], r["far"], r["state"]) for r in with_it],
                         [(46 + 176 * k + i, far, k) for k in range(3) for i, far in enumerate(("0x0000181e", "0x00001821"))])
        for r in with_it:
            self.assertEqual((r["int_sts"][0], r["int_sts_after"], r["int_sts_after_clearing_bit_5"], r["code"]), ("50033004", "50033024", "50033004", "0x0"))
        d = ROOT / "evidence" / "s2_2_17A6_2026-11-22"
        others = [f for f in status_seen.verdicts(d) if f.parent.name != "run03"]
        self.assertEqual((len(others), [f for f in others if status_seen.seen(json.loads(f.read_text()))["bits"]]), (7, []))

    def test_the_singles_of_s2_3_show_it_exactly_where_the_one_set_cell_is_read(self) -> None:
        """S2.3 on 2026-11-23 (docs/s2_plan.md, section 36). In a state with one cell of the RAM set, bit 5 shows after
        the read that delivers the frame in which that cell's bit lies, and not after the other read: 256 states, 512
        reads, no exception. With no cell set (the base states) it does not show; nor anywhere in the code run, whose
        states have none, 32 or 64 cells set in a frame. It is cleared each time and does not come back by itself."""
        d = ROOT / "evidence" / "s2_3_17A6_2026-11-23"
        frame = {e["cell"]: int(e["address"].split("/")[0], 16) for e in json.loads((d / "ram_map.json").read_text())["entries"]}
        shown = lambda r: bool(int(r["int_sts_after"], 16) & 0x20)
        with_it = without = 0
        for k in (1, 2, 3, 4):
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            names = v["run"]["states"]
            self.assertEqual((names[0], names[-1], names[1:-1]), ("base", "base", [f"single {n}" for n in range(64 * (k - 1), 64 * k)]))
            for r in v["records"]:
                if r["far"] not in ("0x0040121e", "0x00401221"):             # the reference frame and CTL0
                    self.assertFalse(shown(r), (k, r["index"])); continue
                self.assertEqual(r["frames"], 3)
                if names[r["state"]] == "base":
                    self.assertFalse(shown(r), (k, r["index"])); continue
                cell = int(names[r["state"]].split()[1])
                delivers = int(r["far"], 16) <= frame[cell] < int(r["far"], 16) + 3
                self.assertEqual(shown(r), delivers, (k, r["index"], cell))
                with_it += delivers; without += not delivers
                if delivers:
                    self.assertEqual((r["int_sts"][0], r["int_sts_after"], r["int_sts_after_clearing_bit_5"], r["code"]), ("50033004", "50033024", "50033004", "0x0"))
            (b,) = status_seen.seen(v)["bits"]
            self.assertEqual((b["bit"], b["stayed_once_it_showed"], b["in_the_last_word"]), (5, False, False))
        self.assertEqual((with_it, without), (256, 256))
        code = json.loads((d / "run00" / "verdict.json").read_text())
        self.assertEqual((len(code["records"]), [r["index"] for r in code["records"] if shown(r)], status_seen.seen(code)["bits"]), (220, [], []))

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

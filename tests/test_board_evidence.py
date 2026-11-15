"""The results brought back from the board, judged again by the judges as they are now.

A judge that is tightened later must still pass what the board really returned, and a stored
result that was edited must not: each file is also held by its hash.
"""
import hashlib, json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1a_judge, s1b0_judge, s1b0b_judge, s1b1_judge  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
RUNS = [
    (s1a_judge, "s1a_17A6_2026-11-13", "expected.json", "b5cb491a8c4e3be07b4b0a03fb6afd35e491b938b15792cf06bd792ee7813c33"),
    (s1b0_judge, "s1b0_17A6_2026-11-14", "expected_s1b0.json", "46a5b5b6f643064befe63d36f2824ea45ec21e9c51b11ee9830de1ab46e2da6d"),    (s1b0b_judge, "s1b0b_17A6_2026-11-14", "expected_s1b0b.json", "9b94fe3aea6484e53c49d4e5e2dfe4a7368e7162c2700dc4788151ffb4008411"),
]

QUIET_SUMMARY_SHA256 = "2dba58285bf98c3a0f0d8314c7b65a194dc492fa631e0fab412daa22a9787520"
DX_SUMMARY_SHA256 = "1cd834ae90ae1cb104bf3497a22abedfe5d1638f64dbe4fd52155c5766c8ad38"


def load(run: str, expected: str) -> tuple[bytes, list[int]]:
    d = ROOT / "evidence" / run
    return (d / "run1" / "result.bin").read_bytes(), [int(w, 16) for w in json.loads((d / expected).read_text())["params"]]


class StoredBoardResults(unittest.TestCase):
    def test_each_stored_result_is_the_file_that_came_back(self) -> None:
        for _, run, expected, sha in RUNS:
            with self.subTest(run=run):
                self.assertEqual(hashlib.sha256(load(run, expected)[0]).hexdigest(), sha)

    def test_each_stored_result_still_passes_its_judge(self) -> None:
        for judge, run, expected, _ in RUNS:
            with self.subTest(run=run):
                raw, planned = load(run, expected)
                result = judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
                self.assertEqual((result["verdict"], result["problems"]), ("PASS", []))

    def test_the_address_rule_seen_on_the_board(self) -> None:
        raw, planned = load("s1b0_17A6_2026-11-14", "expected_s1b0.json")
        result = s1b0_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
        self.assertEqual(result["far_deltas"], {"1": list(range(11))})
        self.assertEqual(sorted({(r["far"], r["frames"], r["far_read_back"]) for r in result["records"]}),
                         [("0x00000b98", 1, "0x00000b9a"), ("0x00000b98", 3, "0x00000b9c"), ("0x00000b99", 1, "0x00000b9b")])

    def test_what_the_register_held_after_each_kind_of_read_on_the_board(self) -> None:
        raw, planned = load("s1b0b_17A6_2026-11-14", "expected_s1b0b.json")
        result = s1b0b_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
        self.assertEqual(result["steps_by_words"], {"0": [0], "101": [1], "202": [2], "303": [3]})
        self.assertIs(result["one_step_per_frame_of_words"], True)
        self.assertEqual(result["reads_without_a_clean_far_value"], [])
        self.assertEqual({(row["far"], row["read"]): row["far_read_back"] for row in result["far_after"] if row["read"] == "the pad alone"},
                         {("0x00000b98", "the pad alone"): "0x00000b99", ("0x00000b99", "the pad alone"): "0x00000b9a",
                          ("0x00000b9a", "the pad alone"): "0x00000b9b"})

    def test_the_two_stopped_walks_are_judged_as_what_they_were(self) -> None:
        """S1b.1, 2026-11-14: both runs stopped by the prober on a receive-FIFO overflow. The stored results must keep
        failing for exactly that reason, whatever is later changed in the judge."""
        import s1b1_judge
        for run, sha, frames, record, far in (("run1_recovered", "efd5bbe6cb809b2520b12a03ad9260abebc759da83fbf1c9f2ac1e17684e538d", 26, 55, "0x00000b9a"),
                                              ("run2_recovered", "868048b6ba389bbb6152c0e508ab4bfee39154ed82f6cce0ca3b62b844a5fe3d", 7, 16, "0x00000b87")):
            with self.subTest(run=run):
                d = ROOT / "evidence" / "s1b1_17A6_2026-11-14"
                raw = (d / run / "result.bin").read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
                planned = [int(w, 16) for w in json.loads((d / "expected_s1b1.json").read_text())["params"]]
                v = s1b1_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
                self.assertEqual((v["verdict"], v["problems"]), ("FAIL", ["the run did not complete: status 0x221", "1 anomalous read(s)"]))
                self.assertEqual((v["frames_walked"], v["passes"][0]["ended"]), (frames, "not ended"))
                last = v["records"][record]
                self.assertEqual((last["far"], last["read"], last["code"], last["int_sts"][1], last["survivors"]), (far, "content read", "0x21", "50070004", 10))
                self.assertEqual([(int(s["far"], 16), int(s["next"], 16)) for s in v["walk"]], [(0xB80 + k, 0xB81 + k) for k in range(frames)])

    def test_the_diagnostic_series_of_2026_11_15_is_what_its_summary_says(self) -> None:
        """18 runs: the summary is made again from the stored results (each judged again, each held by its hash in the
        summary), and the finding is read from it — overflows only where the polling variable lay at 24 modulo 32."""
        import importlib.util
        d = ROOT / "evidence" / "dx_17A6_2026-11-15"
        spec = importlib.util.spec_from_file_location("dx_summarize", d / "summarize.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        made, stored = mod.summary(), json.loads((d / "summary.json").read_text())
        self.assertEqual(made, stored)
        self.assertEqual(hashlib.sha256((d / "summary.json").read_bytes()).hexdigest(), DX_SUMMARY_SHA256)
        runs = {r["run"]: r for r in stored["runs"]}
        self.assertEqual(len(runs), 18)
        self.assertTrue(all(r["problems_other_than_expected"] == [] and r["card_verified"] for r in runs.values()))
        self.assertEqual({name: "".join("o" if runs[f"{name}_run{k:02d}"]["stopped"] else "." for k in (1, 2, 3)) for name in mod.SETS},
                         {"dxw0": "oo.", "dxs0": "...", "dxs18": "oo.", "dxs10": "ooo", "dxw6": "...", "dxw8": ".oo"})
        self.assertEqual([runs[f"dxw6_run{k:02d}"]["verdict"] for k in (1, 2, 3)], ["PASS"] * 3)
        self.assertTrue(all(r["stopped"]["code"] == "0x21" and r["stopped"]["int_sts"][1] == "50070004" for r in runs.values() if r["stopped"]))
        self.assertEqual({k: (v["reads"], v["overflows"]) for k, v in stored["by_address_mod_32"].items()}, {"24": (728, 9), "0": (504, 0)})

    def test_the_series_of_the_three_waits_is_what_its_summary_says(self) -> None:
        """18 runs, 2026-11-15: the summary is made again from the stored results, and the finding is read from it — at
        the stack positions that had overflowed, the original wait overflows and the two that store nothing do not."""
        import importlib.util
        d = ROOT / "evidence" / "quiet_17A6_2026-11-15"
        spec = importlib.util.spec_from_file_location("quiet_summarize", d / "summarize.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        made, stored = mod.summary(), json.loads((d / "summary.json").read_text())
        self.assertEqual(made, stored)
        self.assertEqual(hashlib.sha256((d / "summary.json").read_bytes()).hexdigest(), QUIET_SUMMARY_SHA256)
        runs = {r["run"]: r for r in stored["runs"]}
        self.assertEqual(len(runs), 18)
        self.assertTrue(all(r["problems_other_than_expected"] == [] and r["card_verified"] for r in runs.values()))
        self.assertEqual({name: "".join("o" if runs[f"{name}_run{k:02d}"]["stopped"] else "." for k in (1, 2, 3)) for name in mod.SETS},
                         {"dxs10": "o..", "dxs10n": "...", "dxs10r": "...", "dxw0": "ooo", "dxw0n": "...", "dxw0r": "..."})
        self.assertEqual([runs[f"{name}_run{k:02d}"]["verdict"] for name in ("dxw0n", "dxw0r") for k in (1, 2, 3)], ["PASS"] * 6)
        self.assertEqual({(r["run"][:-6], r["wait"]) for r in runs.values()},
                         {("dxs10", "as before"), ("dxs10n", "no stores"), ("dxs10r", "no stack"), ("dxw0", "as before"), ("dxw0n", "no stores"), ("dxw0r", "no stack")})
        self.assertEqual({w: (v["24"]["reads"], v["24"]["overflows"]) for w, v in stored["by_wait_and_address_mod_32"].items()},
                         {"as before": (297, 4), "no stores": (510, 0), "no stack": (510, 0)})

    def test_the_walk_of_the_column_with_the_quiet_wait(self) -> None:
        """S1b.1, 2026-11-15: the stored result is the file that came back, the judge as it is now passes it and finds
        the column the board named; the grader's stored word is what it says of that verdict's own content."""
        d = ROOT / "evidence" / "s1b1r_17A6_2026-11-15"
        raw = (d / "run1" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "08e7f4eb7bc599e73b779a62b90bbe98ad86b5a40ad839305f8279dae9e83366")
        planned = [int(w, 16) for w in json.loads((d / "expected_s1b1r.json").read_text())["params"]]
        self.assertEqual(planned[15], 2 << 8)
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        v = s1b1_judge.judge(words, KNOWN, planned)
        self.assertEqual((v["verdict"], v["problems"], v["frames_walked"], len(v["records"])), ("PASS", [], 36, 164))
        self.assertEqual(v["passes"], [{"frames": 36, "ended": "the device named an address outside the envelope", "last_address_named": "0x00000c00"}] * 2)
        self.assertEqual([(int(s["far"], 16), int(s["next"], 16)) for s in v["walk"]], [(0xB80 + k, 0xB81 + k) for k in range(35)] + [(0xBA3, 0xC00)])
        self.assertEqual((v["frames_without_a_second_path"], v["known_frames_not_reached"], len({s["frame_sha256"] for s in v["walk"]})), ([], [], 36))
        self.assertEqual(v["params"]["polling_loop"], s1b1_judge.POLLING[2])
        self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()))
        self.assertEqual(v, json.loads((d / "run1" / "verdict.json").read_text()), "the verdict stored with the run is the one the judge gives now")
        g = json.loads((d / "grade.json").read_text())
        self.assertEqual((g["judge_verdict"], g["differs"], g["not_compared"], len(g["agrees"]), g["database_frame_count"]), ("PASS", [], [], 3, 36))
        self.assertEqual(g["column_walked"], {"block_type": 0, "half": "top", "row": 0, "column": 23})
        words[len(words) // 2] ^= 1
        self.assertNotEqual(s1b1_judge.judge(words, KNOWN, planned)["verdict"], "PASS")

    def test_a_stored_result_with_one_word_changed_does_not_pass(self) -> None:
        for judge, run, expected, _ in RUNS:
            with self.subTest(run=run):
                raw, planned = load(run, expected)
                words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
                words[len(words) // 2] ^= 1
                self.assertNotEqual(judge.judge(words, KNOWN, planned)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()

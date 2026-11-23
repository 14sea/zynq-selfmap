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

    def test_the_chain_along_the_row_as_it_was_stored(self) -> None:
        """S1b.2, 2026-11-15: the 31 stored runs, each judged again from its raw words by the chain as it is now. Thirty
        are accepted; the 31st was stopped by the prober at the end of the row and the chain is halted there. The
        summary and the chain's state stored with the runs are what the programs give now."""
        import s1b2_chain, s1b2_row
        d = ROOT / "evidence" / "s1b2_17A6_2026-11-15"
        base = [int(w, 16) for w in json.loads((d / "expected_s1b2.json").read_text())["params"]]
        self.assertEqual((base[3], base[4], base[5], base[12], base[15], base[16]), (0, 0x1FFFF, 0xB99, 64, 2 << 8, 0))
        a = s1b2_chain.assess(d, base, KNOWN)
        self.assertEqual((a["state"], len(a["runs"]), [r["decision"] for r in a["runs"]]), ("halted", 31, ["go on"] * 30 + ["halt"]))
        self.assertEqual(s1b2_chain.brief(a), json.loads((d / "chain.json").read_text()))
        self.assertEqual(len(a["why"]), 2)
        self.assertIn("after the frame at 0x00001ba9 the register held 0x00400000, but the device names 0x00001ba9 after 0x00001ba9", a["why"][1])
        self.assertIn("status 0x800", a["why"][1])
        self.assertEqual([(r["frames"], r["ended"]) for r in a["runs"][:30]], [(64, s1b2_chain.LIMIT)] * 30)
        self.assertEqual((a["runs"][0]["first"], a["runs"][29]["last"], a["runs"][29]["named_after_the_last"]), ("0x00000000", "0x00001b80", "0x00001b81"))
        row = s1b2_row.summarize(a, KNOWN, json.loads((ROOT / "evidence" / "s1b1r_17A6_2026-11-15" / "run1" / "verdict.json").read_text()))
        self.assertEqual(row, json.loads((d / "row.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "row.json").read_bytes()).hexdigest(), "60074f0c3fec866cc86ffb91f6217f1949107bf4814a15c5d1f920ecaa0a85bd")
        self.assertEqual((row["frames"], row["unexpected"], row["end"]["reached"], row["known_frames_not_walked"]), (1891, [], False, []))
        whole = [c for c in row["columns"] if c["walked_whole"]]
        self.assertEqual(([c["column"] for c in whole], sum(c["frames"] for c in whole)), (list(range(55)), 1890))
        self.assertTrue(all(c["minors_are_0_to_n_minus_1"] and c["next_is_minor_0_of_the_column_numbered_one_higher"] for c in whole))
        self.assertEqual(row["columns"][-1]["column"], 55); self.assertFalse(row["columns"][-1]["walked_whole"])
        self.assertEqual(row["column_of_s1b1"], {"frames_there": 36, "of_which_walked_here": 36, "same_frames": True, "same_addresses_named": True, "the_same_column": True})
        # the run that was stopped: what its records say about the end of the row
        last = json.loads((d / "run30" / "verdict.json").read_text())
        self.assertEqual((last["verdict"], last["header"]["status"], last["header"]["anomalies"], last["frames_walked"]), ("FAIL", "0x800", 0, 42))
        self.assertEqual([(r["far"], r["frames"], r["far_read_back"]) for r in last["records"][-4:]],
                         [("0x00001ba8", 0, "0x00001ba9"), ("0x00001ba8", 1, "0x00001ba9"), ("0x00001ba9", 0, "0x00001ba9"), ("0x00001ba9", 1, "0x00400000")])
        for k in range(31):                                  # no overflow and no interface failure anywhere in the chain
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()), k)
        self.assertFalse((d / "grade.json").exists(), "the chain halted: the grader was not run")

    def test_the_two_runs_at_the_end_of_the_row(self) -> None:
        """S1b.2b, 2026-11-16: the two stored runs judged again from their raw words, and the layout made again of
        them and of the stored walk of run 30. Beyond the last address of the row the register stood still once at
        that address and once at 0x00400000; two frames were delivered from beyond, as the owner allowed, and no more."""
        import s1b2_end, s1b2e_judge
        d = ROOT / "evidence" / "s1b2b_17A6_2026-11-16"
        again = {}
        for name, sha, records, frames in (("s1b2e", "f76eda60fddb9b5d0c5dd88e46b336269af69839f8ff991c9e3827b5bd3c8658", 50, 72),
                                           ("s1b2c", "8de52d701dd77006a8a4530242ec43744dc6a04896b7d66abc82f56c2a8d3f82", 30, 84)):
            with self.subTest(run=name):
                raw = (d / name / "result.bin").read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
                planned = [int(w, 16) for w in json.loads((d / f"expected_{name}.json").read_text())["params"]]
                self.assertEqual((planned[2], planned[3], planned[4], planned[5], planned[8], planned[15]), (5, 0, 0x1FFFF, 0xB99, 0, 2 << 8))
                words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
                v = json.loads(json.dumps(s1b2e_judge.judge(words, KNOWN, planned)))
                self.assertEqual(v, json.loads((d / name / "verdict.json").read_text()))
                self.assertEqual((v["verdict"], v["problems"], v["header"]["records"], v["header"]["anomalies"], v["frames_delivered_without_a_known_answer"]),
                                 ("PASS", [], records, 0, frames))
                self.assertTrue(all(r["code"] == "0x0" for r in v["records"]))
                self.assertTrue(all(not q["interface_failures"] for q in v["polling_variable"].values()))
                words[len(words) // 2] ^= 1
                self.assertNotEqual(s1b2e_judge.judge(words, KNOWN, planned)["verdict"], "PASS")
                again[name] = v
        walk = json.loads((ROOT / "evidence" / "s1b2_17A6_2026-11-15" / "run30" / "verdict.json").read_text())
        out = {"the_end": s1b2_end.end(again["s1b2e"]), "the_column_again": s1b2_end.column(again["s1b2c"], walk, again["s1b2e"])}
        self.assertEqual(out, json.loads((d / "end.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "end.json").read_bytes()).hexdigest(), "2fe7c13fcdd09f65e2e4e79a812bac062767e7f6644a05ad78feceb236b1c7d2")
        end, col = out["the_end"], out["the_column_again"]
        self.assertEqual((end["disagreements"], col["disagreements"]), ([], []))
        self.assertEqual((end["starting_addresses"], end["starting_addresses_one_step_apart"]),
                         (["0x00001ba6", "0x00001ba7", "0x00001ba8", "0x00001ba9"], True))
        self.assertEqual([(q["position"], q["register"], len(q["reached_by"])) for q in end["positions"][1:]],
                         [(1, ["0x00001ba7"], 1), (2, ["0x00001ba8"], 2), (3, ["0x00001ba9"], 3), (4, ["0x00001ba9"], 4),
                          (5, ["0x00400000"], 3), (6, ["0x00400000"], 2), (7, ["0x00400001"], 1)])
        self.assertEqual(end["beyond"]["steps_at_which_the_register_did_not_change"], [1, 3])
        self.assertEqual([(f["steps_beyond"], f["all_zero"], f["ways"]) for f in end["beyond"]["frames_delivered_from_beyond"]], [(1, True, 3), (2, True, 1)])
        self.assertEqual((end["distinct_contents_delivered"], "note_on_content" in end), (1, True))
        self.assertEqual((col["frames_the_walk_delivered"], col["frames_compared"], col["same"], col["addresses_of_the_walk_not_read_again"],
                          col["frames_at_places_the_walk_did_not_reach"], col["distinct_contents"]), (42, 42, 42, [], [], 1))
        self.assertEqual([r["as_the_walk_says"] for r in col["register"]], [True] * 13 + [None])
        self.assertEqual((col["register"][-1]["at"], col["register"][-1]["register_afterwards"]), ("0x00001ba7", ["0x00400000"]))
        self.assertEqual(col["reads_also_made_at_the_end"], [{"at": "0x00001ba7", "steps": 4}])

    def test_the_row_as_closed_from_the_stored_results(self) -> None:
        """Section 32: what s1b2_closed.py makes of the stored summary of the chain, the stored walk of run 30 and the
        two stored runs of S1b.2b. No database is read. The chain's 55 columns are as they were; the 56th has the 42
        frames of the walk, each read again by the second path; the address after the row is the first the register
        showed other than the last frame's own."""
        import s1b2_closed
        a, b = ROOT / "evidence" / "s1b2_17A6_2026-11-15", ROOT / "evidence" / "s1b2b_17A6_2026-11-16"
        row = json.loads((a / "row.json").read_text())
        given = [row] + [json.loads(f.read_text()) for f in (a / "run30" / "verdict.json", b / "s1b2c" / "verdict.json", b / "s1b2e" / "verdict.json")]
        out = s1b2_closed.close(*given)
        self.assertNotIn("refused", out)
        self.assertEqual(out["closed"]["rules"], {"1a": True, "1b": True, "1c": True, "2": True, "3": True, "4": True})
        self.assertEqual((out["chain"], out["columns"][:55], out["addresses"][:1891], out["unexpected"]), (row["chain"], row["columns"][:55], row["addresses"], []))
        self.assertEqual((out["frames"], len(out["columns"]), out["frames_per_column"][55], all(c["walked_whole"] for c in out["columns"])), (1932, 56, [55, 42], True))
        self.assertEqual((out["columns"][55]["first"], out["columns"][55]["last"], out["columns"][55]["minors_are_0_to_n_minus_1"]), ("0x00001b80", "0x00001ba9", True))
        self.assertEqual((out["end"]["reached"], out["end"]["last_frame"], out["end"]["named_after_the_last_frame"]), (True, "0x00001ba9", "0x00400000"))
        self.assertEqual((out["end"]["the_register_stood_still"]["steps_before_that_address"], out["end"]["the_register_stood_still"]["at_steps_beyond_the_last_frame"]), (1, [1, 3]))
        self.assertEqual(out["end"]["frames_delivered_from_beyond_the_last_frame"], [{"steps_beyond": 1, "all_zero": True}, {"steps_beyond": 2, "all_zero": True}])
        self.assertEqual((out["closed"]["frames_added"], out["closed"]["frames_read_again"], out["closed"]["of_which_the_same"], out["closed"]["distinct_contents_among_them"]), (41, 42, 42, 1))
        stored = b / "row_closed.json"                       # written and committed before the grader was run; held here as it was
        self.assertEqual(out, json.loads(stored.read_text()))
        self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), "d8457ed86e16648eeb5b042021f71dbcde8af8273f644c3e23652b9cf4c7de59")
        swapped = s1b2_closed.close(given[0], given[1], given[3], given[2])       # the two runs of S1b.2b given in each other's place
        self.assertIn("refused", swapped)
        # the grader's stored word (run once, after row_closed.json was committed) is about that summary: the database is not read here
        g = json.loads((b / "grade.json").read_text())
        self.assertEqual(hashlib.sha256((b / "grade.json").read_bytes()).hexdigest(), "6ecfc55f220827eda8403785321b57f0ec6a6e7970585b4ebb59bf0f49b59887")
        self.assertEqual((g["chain"], g["differs"], len(g["agrees"]), len(g["not_compared"]), g["row_walked"]), ("halted", [], 4, 2, {"block_type": 0, "half": "top", "row": 0}))
        self.assertIn("the chain itself halted", g["summary_closed_by"])
        self.assertEqual([[c["column"], c["walked"]] for c in g["columns"]], out["frames_per_column"])
        self.assertTrue(all(c["walked"] == c["database"] and c["walked_whole"] for c in g["columns"]))
        self.assertFalse((a / "grade.json").exists(), "the chain's own summary, halted, was never graded")

    def test_the_run_across_the_end_of_the_row(self) -> None:
        """S1b.3a, 2026-11-17: the stored run judged again from its raw words, and held again against the stored row.
        With one standstill allowed the walk crossed the end of the row at 0x1ba9 and went on at 0x00400000, where the
        pad alone names the next number; 22 frames of the bottom half, each read twice and in a read of three."""
        import s1b2_judge, s1b3a_seam
        d = ROOT / "evidence" / "s1b3a_17A6_2026-11-17"
        raw = (d / "run" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "e35a57e1f4c9c997b71ef4ef079a7eb0e27e20bc7044236b7a70cce88faf5dda")
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        planned = [int(w, 16) for w in json.loads((d / "expected_s1b3a.json").read_text())["params"]]
        self.assertEqual((planned[2], planned[3], planned[4], planned[5], planned[7], planned[10], planned[12], planned[15], planned[16]),
                         (4, 0, 0x007FFFFF, 0xB99, 2, 1, 64, 2 << 8, 0x1B80))
        words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        v = json.loads(json.dumps(s1b2_judge.judge(words, KNOWN, planned)))
        self.assertEqual(v, json.loads((d / "run" / "verdict.json").read_text()))
        self.assertEqual((v["verdict"], v["problems"], v["header"]["status"], v["header"]["records"], v["header"]["anomalies"]), ("PASS", [], "0x1", 292, 0))
        self.assertEqual(v["passes"], [{"frames": 64, "ended": "the limit of frames was reached", "last_address_named": "0x00400016"}] * 2)
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], list(range(0x1B80, 0x1BAA)) + list(range(0x00400000, 0x00400016)))
        self.assertEqual([int(s["next"], 16) for s in v["walk"]], list(range(0x1B81, 0x1BAA)) + list(range(0x00400000, 0x00400017)))
        self.assertEqual(v["standstills"], [{"at": "0x00001ba9", "register_after_the_pad_alone": "0x00001ba9", "register_after_the_frame": "0x00400000"}])
        self.assertEqual((v["pieces"], v["frames_without_a_second_path"], [s["far"] for s in v["walk"] if s.get("stood_still")]), ([42, 22], [], ["0x00001ba9"]))
        self.assertEqual(v["walk"][42], {"far": "0x00400000", "next": "0x00400001", "register_after_the_frame": "0x00400002", "frame_sha256": v["walk"][0]["frame_sha256"]})
        self.assertEqual(len({s["frame_sha256"] for s in v["walk"]}), 1, "every one of the 64 frames is the same content (all zero)")
        self.assertTrue(all(not q["interface_failures"] for q in v["polling_variable"].values()))
        several = [(r["far"], r["frames"], r["far_read_back"]) for r in v["records"] if r["read"] == "read of several frames"]
        self.assertEqual((len(several), several[13], several[14]), (22, ("0x00001ba7", 3, "0x00400000"), ("0x00400000", 3, "0x00400004")))
        words[len(words) // 2] ^= 1
        self.assertNotEqual(s1b2_judge.judge(words, KNOWN, planned)["verdict"], "PASS")
        # held against the stored row
        row = json.loads((ROOT / "evidence" / "s1b2b_17A6_2026-11-16" / "row_closed.json").read_text())
        out = s1b3a_seam.against(v, row)
        self.assertEqual(out, json.loads((d / "seam.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "seam.json").read_bytes()).hexdigest(), "222162b8dfa0b5f2f6383a994effea6b1a30221d12c1236e062ada873dd8bb0e")
        self.assertEqual((out["disagreements"], out["addresses_in_both"], out["same_frames"]), ([], 42, 42))
        self.assertEqual(out["addresses_the_stored_row_does_not_have"], {"count": 22, "first": "0x00400000", "last": "0x00400015", "standstills_among_them": []})
        self.assertFalse((d / "grade.json").exists(), "the grader is not run in this step")

    def test_the_chain_over_block_type_0_as_it_was_stored(self) -> None:
        """S1b.3. 2026-11-17: 51 runs accepted; the 52nd ran on the board and reported done, but its result header came
        back over the console with characters missing, nothing of it was stored, and the chain halted there.
        2026-11-18, with the owner's word: what the halt left — that run's directory, the driver's file for it, the
        chain's state, the summary over rows and the comparison of the first row — was moved as it was into
        `halted_at_run51`, which the chain lists as set aside. The chain stands at 51 accepted runs, each judged again
        here from its raw words, and plans its 52nd from the last frame of run 50."""
        import s1b2_chain, s1b3_rows, s1b3_top
        d = ROOT / "evidence" / "s1b3_17A6_2026-11-17"
        h = d / "halted_at_run51"
        base = [int(w, 16) for w in json.loads((d / "expected_s1b3.json").read_text())["params"]]
        self.assertEqual((base[3], base[4], base[5], base[10], base[12], base[15], base[16]), (0, 0x007FFFFF, 0xB99, 1, 64, 2 << 8, 0))
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        a = s1b2_chain.assess(d, base, KNOWN, s1b2_chain.BOUNDS["s1b3"], "s1b3")
        first = a["runs"][:51]                               # the runs of 2026-11-17; what was added later is not looked at in this test
        self.assertEqual(([r["decision"] for r in first], a["set_aside"]), (["go on"] * 51, ["halted_at_run51"]))
        self.assertEqual([(r["frames"], r["ended"]) for r in first], [(64, s1b2_chain.LIMIT)] * 51)
        self.assertEqual((first[30]["first"], first[30]["last"], first[50]["last"], first[50]["named_after_the_last"]),
                         ("0x00001b80", "0x00400015", "0x00401283", "0x00401284"))
        self.assertEqual([s["far"] for r in first for s in r["walk"] if s.get("stood_still")], ["0x00001ba9"], "one standstill, met by one run")
        for k in range(51):                                  # no overflow and no interface failure anywhere in these runs
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()), k)
        # ---- the halt, as it was stored then and is kept now
        was = json.loads((h / "chain.json").read_text())
        self.assertEqual(hashlib.sha256((h / "chain.json").read_bytes()).hexdigest(), "e2466a595f432ca0e4e971aa67ce2864cf8e016ae80c05041a02604d30cadcf2")
        self.assertEqual((was["state"], len(was["runs"]), was["set_aside"]), ("halted", 52, []))
        self.assertEqual(was["why"], ["run51: the run script stopped: the result header could not be read",
                                      "run51: the run script's verdict is FAIL: ['the result header could not be read']",
                                      "run51: the card copy was not verified", "run51: there is no stored result"])
        self.assertEqual(was["runs"][:51], s1b2_chain.brief(a)["runs"][:51], "the 51 runs accepted then are the 51 as they are judged now")
        rec = json.loads((h / "run51" / "run.json").read_text())   # its console lines say the prober finished; no result was stored
        self.assertEqual((rec["went"], rec["return_code"], rec["console"][1], rec["stop"]),
                         (True, "0x0", "SM4 end status=00000001 records=00000124 anomalies=00000000 words=000223c0", "the result header could not be read"))
        self.assertEqual(sorted(p.name for p in (h / "run51").iterdir()), ["console.log", "header.bin", "run.json"])
        # the summary over rows made at the halt: what the programs give now for those 51 runs, but for the chain's state
        halted = dict(a, runs=first + [was["runs"][51]], state="halted", why=was["why"], set_aside=[])
        rows = json.loads(json.dumps(s1b3_rows.summarize(halted, KNOWN)))
        self.assertEqual(rows, json.loads((h / "rows.json").read_text()))
        self.assertEqual(hashlib.sha256((h / "rows.json").read_bytes()).hexdigest(), "dcf466c618757d318e419b539812350ce5b1e19607680b07522ad595697c873c")
        self.assertEqual((rows["frames"], rows["unexpected"], rows["frames_per_row"], rows["end"]["reached"], rows["known_frames_not_walked"]),
                         (3214, [], [[0, "top", 0, 1932], [0, "bottom", 0, 1282]], False, []))
        self.assertEqual([(r["walked_whole"], r["ended_by"], len(r["columns"])) for r in rows["rows"]], [(True, "the register stood still", 56), (False, "not ended", 38)])
        self.assertEqual(rows["standstills"], [{"after": "0x00001ba9", "named": "0x00400000"}])
        self.assertEqual((rows["rows"][1]["frames_per_column"][-1], all(c["walked_whole"] for c in rows["rows"][1]["columns"][:-1])), ([37, 4], True))
        # the first row against the row stored before
        stored = json.loads((ROOT / "evidence" / "s1b2b_17A6_2026-11-16" / "row_closed.json").read_text())
        top = s1b3_top.against(rows, stored)
        self.assertEqual(top, json.loads((h / "top.json").read_text()))
        self.assertEqual(hashlib.sha256((h / "top.json").read_bytes()).hexdigest(), "5b9e07ba997e2040951b909d08cb88208ea652cce7cd12d2c5942d4659d51939")
        self.assertEqual((top["disagreements"], top["addresses_in_both"], top["same_frames"], top["same_address_named"], top["frames_not_all_zero"], top["columns"]),
                         ([], 1932, 1932, 1932, 178, 56))
        self.assertFalse((h / "grade.json").exists(), "the chain halted: nothing was graded then")

    def test_the_chain_over_block_type_0_as_it_stands(self) -> None:
        """2026-11-18: taken up again from `0x00401283` with the run script that asks again for a reply that is not whole
        (it never had to). Eleven more runs; the 62nd stood still at `0x00401ba9` and was then told `0x00800000`,
        which is outside the envelope: the chain is complete. Every run is judged again here from its raw words."""
        import s1b2_chain
        d = ROOT / "evidence" / "s1b3_17A6_2026-11-17"
        base = [int(w, 16) for w in json.loads((d / "expected_s1b3.json").read_text())["params"]]
        a = s1b2_chain.assess(d, base, KNOWN, s1b2_chain.BOUNDS["s1b3"], "s1b3")
        self.assertEqual((a["state"], len(a["runs"]), a["named_after_the_last_frame"], a["set_aside"]), ("complete", 62, "0x00800000", ["halted_at_run51"]))
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on"] * 61 + ["complete"])
        self.assertEqual(s1b2_chain.brief(a), json.loads((d / "chain.json").read_text()))
        self.assertEqual((a["runs"][51]["first"], a["runs"][61]["frames"], a["runs"][61]["last"]), ("0x00401283", 21, "0x00401ba9"))
        self.assertEqual([(r["dir"], s["far"], s["next"]) for r in a["runs"] for s in r["walk"] if s.get("stood_still")],
                         [("run30", "0x00001ba9", "0x00400000"), ("run61", "0x00401ba9", "0x00800000")], "two standstills, each met by one run")
        for k in range(51, 62):                              # the runs of this day: nothing asked twice but pieces, no overflow, no interface failure
            rec = json.loads((d / f"run{k:02d}" / "run.json").read_text())
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], v["header"]["anomalies"]), ("PASS", [], [], 0), k)
            self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()), k)
        # ---- the summary over rows: what the program gives now, and the file committed before anything was compared
        import s1b3_rows, s1b3_top
        rows = json.loads(json.dumps(s1b3_rows.summarize(a, KNOWN)))
        self.assertEqual(rows, json.loads((d / "rows.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "rows.json").read_bytes()).hexdigest(), "16c1d2391a8f93e4ae5a32e2c52a70985dea82684d9f1da3503f6ecbceabc823")
        self.assertEqual((rows["frames"], rows["unexpected"], rows["frames_per_row"], rows["known_frames_not_walked"]),
                         (3864, [], [[0, "top", 0, 1932], [0, "bottom", 0, 1932]], []))
        self.assertEqual([(r["walked_whole"], r["ended_by"], len(r["columns"]), r["first"], r["last"], r["named_after_the_last_frame"]) for r in rows["rows"]],
                         [(True, "the register stood still", 56, "0x00000000", "0x00001ba9", "0x00400000"),
                          (True, "the register stood still", 56, "0x00400000", "0x00401ba9", "0x00800000")])
        self.assertEqual([n for _, n in rows["rows"][0]["frames_per_column"]], [n for _, n in rows["rows"][1]["frames_per_column"]], "column for column the two rows are as long")
        self.assertTrue(all(c["walked_whole"] and c["minors_are_0_to_n_minus_1"] for r in rows["rows"] for c in r["columns"]))
        self.assertEqual(rows["standstills"], [{"after": "0x00001ba9", "named": "0x00400000"}, {"after": "0x00401ba9", "named": "0x00800000"}])
        self.assertEqual((rows["end"]["reached"], rows["end"]["last_frame"], rows["end"]["named_after_the_last_frame"], rows["end"]["after_a_standstill"]),
                         (True, "0x00401ba9", "0x00800000", True))
        zero = hashlib.sha256(bytes(404)).hexdigest()        # a frame of 101 words, all zero
        not_zero = [sum(1 for s in rows["addresses"] if int(r["first"], 16) <= int(s["far"], 16) <= int(r["last"], 16) and s["frame_sha256"] != zero) for r in rows["rows"]]
        self.assertEqual(not_zero, [178, 250])
        # ---- the first row against the row stored before
        stored = json.loads((ROOT / "evidence" / "s1b2b_17A6_2026-11-16" / "row_closed.json").read_text())
        top = s1b3_top.against(rows, stored)
        self.assertEqual(top, json.loads((d / "top.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "top.json").read_bytes()).hexdigest(), "e71a717ef7708655db164113fad7aedd015bd918427d4655d36491b831db37ec")
        self.assertEqual((top["chain"], top["disagreements"], top["addresses_in_both"], top["same_frames"], top["same_address_named"], top["columns"]),
                         ("complete", [], 1932, 1932, 1932, 56))
        # ---- the grader's stored word (run once, after rows.json and top.json were committed): the database is not read here
        g = json.loads((d / "grade.json").read_text())
        self.assertEqual(hashlib.sha256((d / "grade.json").read_bytes()).hexdigest(), "732c389a4ae138e6a1a8b8dc2d2aa9ce7afac58c7bc969c3fe8ab3471b297148")
        self.assertEqual((g["chain"], g["differs"], len(g["agrees"]), len(g["not_compared"]), len(g["rows"])), ("complete", [], 4, 1, 2))
        self.assertEqual([(r["frames"], r["walked_whole"], r["differs"], len(r["columns"])) for r in g["rows"]], [(1932, True, [], 56)] * 2)
        self.assertIn("the chain found 3864, the database's columns add up to 3864", g["agrees"][2])
        self.assertIn("0x00800000", g["agrees"][3])

    def test_the_run_into_block_type_1(self) -> None:
        """S1b.4a, 2026-11-18: one run of the walk from `0x00800000`, the address the device named after the last frame
        of block type 0. Judged again here from its raw words against the set kept with it; the layout is what the
        program gives now."""
        import s1b2_judge, s1b4a_layout
        d = ROOT / "evidence" / "s1b4a_17A6_2026-11-18"
        raw = (d / "run" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "77fde8f5ff02ae2af329ac5d698d7a96e305a44139b983c9c290aba1f0c3df51")
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        planned = [int(w, 16) for w in json.loads((d / "expected_s1b4a.json").read_text())["params"]]
        self.assertEqual((planned[3], planned[4], planned[5], planned[10], planned[12], planned[16]), (0, 0x00FFFFFF, 0xB99, 1, 64, 0x00800000))
        v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
        self.assertEqual(v, json.loads((d / "run" / "verdict.json").read_text()))
        self.assertEqual((v["verdict"], v["problems"], v["header"]["status"], v["header"]["records"], v["header"]["anomalies"]), ("PASS", [], "0x1", 292, 0))
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], list(range(0x00800000, 0x00800040)), "64 addresses, each the one named after the one before")
        self.assertEqual(v["passes"], [{"frames": 64, "ended": "the limit of frames was reached", "last_address_named": "0x00800040"}] * 2)
        self.assertEqual((v["standstills"], v["frames_without_a_second_path"]), ([], []))
        self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()))
        rec = json.loads((d / "run" / "run.json").read_text())
        self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"]), ("PASS", [], [], True, "50033004"))
        out = s1b4a_layout.layout(v)
        self.assertEqual(out, json.loads((d / "layout.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "layout.json").read_bytes()).hexdigest(), "f57d487ab143ec8dc2b5abb83321fd8ab79eb36b39b74fa36c8e841386de64cc")
        self.assertEqual((out["block_types"], out["frames_per_row"], out["rows"][0]["frames_per_column"], out["unexpected"], out["end"]["reached"]),
                         ([1], [[1, "top", 0, 64]], [[0, 64]], [], False))
        self.assertEqual((out["content"]["frames_not_all_zero"], out["content"]["distinct_contents"]), (0, 1), "every frame all zero: the list rests on the register")
        self.assertFalse((d / "grade.json").exists(), "one run is not a list: nothing was graded")

    def test_the_chain_over_block_type_1(self) -> None:
        """S1b.4, 2026-11-18: 21 runs from `0x00800000`; the 21st stood still at `0x00c0027f` and was then told
        `0x01000000`, which is outside the envelope: the chain is complete. Every run is judged again here from its raw
        words against the set kept with the runs; the summary and the comparison are what the programs give now."""
        import s1b2_chain, s1b3_rows, s1b4_first
        d = ROOT / "evidence" / "s1b4_17A6_2026-11-18"
        expected = json.loads((d / "expected_s1b4.json").read_text())
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), expected["image_sha256"])
        base = [int(w, 16) for w in expected["params"]]
        a = s1b2_chain.assess(d, base, KNOWN, s1b2_chain.BOUNDS["s1b4"], "s1b4")
        self.assertEqual((a["state"], len(a["runs"]), a["named_after_the_last_frame"], a["set_aside"]), ("complete", 21, "0x01000000", []))
        self.assertEqual([r["decision"] for r in a["runs"]], ["go on"] * 20 + ["complete"])
        self.assertEqual(s1b2_chain.brief(a), json.loads((d / "chain.json").read_text()))
        self.assertEqual((a["runs"][0]["first"], a["runs"][20]["frames"], a["runs"][20]["last"]), ("0x00800000", 20, "0x00c0027f"))
        self.assertEqual([(r["dir"], s["far"], s["next"]) for r in a["runs"] for s in r["walk"] if s.get("stood_still")],
                         [("run10", "0x0080027f", "0x00c00000"), ("run20", "0x00c0027f", "0x01000000")], "two standstills, each met by one run")
        # ---- the summary over rows, and the file committed before anything was compared
        rows = json.loads(json.dumps(s1b3_rows.summarize(a, KNOWN)))
        self.assertEqual(rows, json.loads((d / "rows.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "rows.json").read_bytes()).hexdigest(), "d02a372bb120c33254e0f2deab96db24b7a8745f8b36d13383b21430530b222f")
        self.assertEqual((rows["frames"], rows["unexpected"], rows["frames_per_row"]), (1280, [], [[1, "top", 0, 640], [1, "bottom", 0, 640]]))
        self.assertEqual([(r["walked_whole"], r["ended_by"], r["first"], r["last"], r["named_after_the_last_frame"], [n for _, n in r["frames_per_column"]]) for r in rows["rows"]],
                         [(True, "the register stood still", "0x00800000", "0x0080027f", "0x00c00000", [128] * 5),
                          (True, "the register stood still", "0x00c00000", "0x00c0027f", "0x01000000", [128] * 5)])
        self.assertTrue(all(c["walked_whole"] and c["minors_are_0_to_n_minus_1"] for r in rows["rows"] for c in r["columns"]))
        self.assertEqual((rows["end"]["reached"], rows["end"]["named_after_the_last_frame"], rows["end"]["that_address"]["block_type"]), (True, "0x01000000", 2))
        self.assertEqual(rows["known_frames_walked"], [], "the frames with a known answer lie below the set's first address")
        # ---- the stored run of S1b.4a against the chain's list
        first = s1b4_first.against(rows, json.loads((ROOT / "evidence" / "s1b4a_17A6_2026-11-18" / "run" / "verdict.json").read_text()))
        self.assertEqual(first, json.loads((d / "first_run_against_s1b4a.json").read_text()))
        self.assertEqual((first["disagreements"], first["of_which_in_the_chain"], first["same_frames"], first["same_address_named"]), ([], 64, 64, 64))
        # ---- seen and not explained (RESULT.md): the content of columns 2 to 4, and bit 5 of the status register
        zero = hashlib.sha256(bytes(404)).hexdigest()
        ten = hashlib.sha256(b"".join(struct.pack(">I", 0x00020000 if k in (4, 14, 24, 34, 44, 55, 65, 75, 85, 95) else 0) for k in range(101))).hexdigest()
        column = lambda far: int(far, 16) >> 7 & 0x3FF     # noqa: E731  (UG470: bits 16..7 of the address word)
        self.assertEqual({(column(s["far"]) >= 2, s["frame_sha256"]) for s in rows["addresses"]}, {(False, zero), (True, ten)})
        self.assertEqual(sum(1 for s in rows["addresses"] if s["frame_sha256"] == ten), 768)
        for k in range(21):
            rec = json.loads((d / f"run{k:02d}" / "run.json").read_text())
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], v["header"]["anomalies"]), ("PASS", [], [], 0), k)
            self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()), k)
            # the status words of each record, in order: bit 5 shows from the first read of a frame in columns 2 to 4 on, never before
            seen, reached = False, False
            for r in v["records"]:
                words = [int(x, 16) for x in r["int_sts"]]
                if r["kind"] == "target" and r["frames"] and column(r["far"]) >= 2 and int(r["far"], 16) >> 23 == 1:
                    reached = True
                self.assertTrue(reached or not any(w & 0x20 for w in words), (k, r["far"]))
                seen = seen or any(w & 0x20 for w in words)
                if reached:
                    self.assertTrue(words[-1] & 0x20, (k, r["far"]))
            self.assertEqual((seen, rec["int_sts_afterwards"]), (reached, "50033024" if reached else "50033004"), k)
            self.assertEqual(int(v["header"]["ctrl"], 16) & 0x100, 0, "SEU_EN is clear: the PS takes no action on that bit")
        self.assertEqual([k for k in range(21) if json.loads((d / f"run{k:02d}" / "run.json").read_text())["int_sts_afterwards"] == "50033024"],
                         [4, 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20])
        # ---- the grader's stored word (run once, after the record of the chain was committed): the database is not read here
        g = json.loads((d / "grade.json").read_text())
        self.assertEqual(hashlib.sha256((d / "grade.json").read_bytes()).hexdigest(), "3e70bb861bce222fc270585918f994cc14330a7d156f9a29c56e19a2a92c9892")
        self.assertEqual((g["chain"], g["differs"], len(g["agrees"]), len(g["not_compared"]), len(g["rows"])), ("complete", [], 3, 2, 2))
        self.assertEqual([(r["frames"], r["walked_whole"], r["differs"], len(r["columns"])) for r in g["rows"]], [(640, True, [], 5)] * 2)
        self.assertIn("the chain found 1280, the database's columns add up to 1280", g["agrees"][2])

    def test_the_look_at_ps_registers(self) -> None:
        """2026-11-19: ps_look.py once. The board had been started anew, so the status had neither PCFG_DONE nor bit 5
        and nothing was written; the dumps were read. What the record says of the values is held here."""
        import ps_look
        d = ROOT / "evidence" / "pslook_17A6_2026-11-19"
        rec = json.loads((d / "look.json").read_text())
        self.assertEqual((rec["sent"], rec["clear_sent"], rec["status_before"], rec["status_after"], rec["replies_not_whole"]),
                         ([c for c, _ in ps_look.LOOK] + [ps_look.STATUS], False, "a802000b", [], []))
        self.assertEqual(rec["stopped"], "the status has not both PCFG_DONE and bit 5 set: nothing was written")
        log = (d / "console.log").read_bytes()
        self.assertEqual((log.count(b"<<TX"), log.count(b"<<TX b'md.l "), log.count(b"mw")), (9, 8, 0), "the interrupt and eight dumps; nothing written")
        r = {k: int(v, 16) for k, v in rec["registers"].items()}
        self.assertEqual(len(r), 23)
        self.assertEqual(r["l2cpl310.reg1_control"] & 1, 0, "the level-2 cache is off")
        self.assertEqual({r[f"ddrc.axi_priority_wr_port{k}"] for k in range(4)}, {0x000803FF})
        self.assertEqual({r[f"ddrc.axi_priority_rd_port{k}"] for k in range(4)}, {0x000003FF})
        self.assertEqual((r["slcr.PCAP_CLK_CTRL"] >> 8 & 0x3F, r["slcr.PCAP_CLK_CTRL"] >> 4 & 3, r["slcr.PCAP_CLK_CTRL"] & 1), (8, 0, 1))
        self.assertEqual([r[f"slcr.{n}_PLL_CTRL"] >> 12 & 0x7F for n in ("IO", "ARM", "DDR")], [48, 40, 32])
        self.assertEqual((r["slcr.ARM_CLK_CTRL"] >> 8 & 0x3F, r["slcr.DDR_CLK_CTRL"] >> 26, r["slcr.DDR_CLK_CTRL"] >> 20 & 0x3F), (2, 3, 2))
        self.assertEqual((r["devcfg.CFG"] >> 10 & 3, r["devcfg.CFG"] >> 8 & 3, r["devcfg.CTRL"] >> 8 & 1, r["devcfg.INT_STS"] & 0x24), (1, 1, 0, 0))
        self.assertEqual((r["devcfg.CTRL"], r["devcfg.MCTRL"]), (0x4E00E07F, 0x30800100), "as in the result headers of S1b.4")

    def test_bit_5_of_the_status_cleared_after_a_run(self) -> None:
        """2026-11-19: one run of the set s1b4 from `0x0080013b`, where run 5 of the stored chain began; then, with no
        reset between, ps_look.py: the status with bit 5, the one write, three reads without it."""
        import ps_look, s1a_run, s1b2_judge, status_seen
        d = ROOT / "evidence" / "sbit_17A6_2026-11-19"
        chain = ROOT / "evidence" / "s1b4_17A6_2026-11-18"
        raw = (d / "run" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "1c4f715e24ff8b9b0a4268445a77616c30c2498ce174550588c312e724174a25")
        exp = s1a_run.with_start("s1b4", json.loads((chain / "expected_s1b4.json").read_text()), 0x0080013B, "the first frame of run05")
        v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, [int(w, 16) for w in exp["params"]])
        self.assertEqual(v, json.loads((d / "run" / "verdict.json").read_text()))
        self.assertEqual((v["verdict"], v["problems"], v["header"]["records"], v["header"]["anomalies"]), ("PASS", [], 292, 0))
        # ---- the same run as run 5 of the chain: every record, but for how many times a transfer was polled
        was = json.loads((chain / "run05" / "verdict.json").read_text())
        self.assertEqual({k for k in v if v[k] != was[k]}, {"records"})
        self.assertEqual({k for a, b in zip(v["records"], was["records"]) for k in a if a[k] != b[k]}, {"polls"})
        rec = json.loads((d / "run" / "run.json").read_text())
        self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"]), ("PASS", [], [], True, "50033024"))
        # ---- the bit, as the listing has it: from the first read of a frame, to the end
        seen = status_seen.seen(v)
        self.assertEqual(json.loads((d / "status_seen.json").read_text())["by_run"][0]["bits"], seen["bits"])
        (b,) = seen["bits"]
        self.assertEqual((b["bit"], b["first"]["record"], b["first"]["far"], b["first"]["frames"], b["stayed_once_it_showed"], b["in_the_last_word"]),
                         (5, 2, "0x0080013b", 1, True, True))
        # ---- the look straight after it
        look = json.loads((d / "look" / "look.json").read_text())
        self.assertEqual((look["sent"], look["stopped"], look["replies_not_whole"]), (ps_look.commands(), None, []))
        self.assertEqual((look["status_before"], look["clear_sent"], look["status_after"]), ("50033024", True, ["50033004"] * 3))
        log = (d / "look" / "console.log").read_bytes()
        self.assertEqual((log.count(b"<<TX"), log.count(b"<<TX b'mw.l f800700c 00000020\\r'>>"), log.count(b"<<TX b'mw")), (13, 1, 1), "one write, the one meant")
        before = json.loads((ROOT / "evidence" / "pslook_17A6_2026-11-19" / "look.json").read_text())["registers"]
        self.assertEqual({k for k in before if before[k] != look["registers"][k]}, {"devcfg.INT_STS", "devcfg.STATUS"}, "the PL is configured now; nothing else differs")
        import calendar, time
        at = lambda r: calendar.timegm(time.strptime(r["started"], "%Y-%m-%dT%H:%M:%S+0000"))     # noqa: E731
        self.assertLess(at(look) - at(rec), 300, "the look began within five minutes of the run's beginning")

    def test_the_run_into_block_type_2(self) -> None:
        """S1b.5a, 2026-11-19: one run of the walk from `0x01000000`, the address the device named after the last frame
        of block type 1. Judged again here from its raw words against the set kept with it; the layout and the listing
        of status bits are what the programs give now. Nothing was graded: there is nothing to grade against."""
        import s1b2_judge, s1b4a_layout, status_seen
        d = ROOT / "evidence" / "s1b5a_17A6_2026-11-19"
        raw = (d / "run" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "817a2ada61f5ee7d560519e9fab0bd20f98333f95fc2a4e00e02c60f09c75343")
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        planned = [int(w, 16) for w in json.loads((d / "expected_s1b5a.json").read_text())["params"]]
        self.assertEqual((planned[3], planned[4], planned[5], planned[10], planned[12], planned[16]), (0, 0x017FFFFF, 0xB99, 1, 64, 0x01000000))
        v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
        self.assertEqual(v, json.loads((d / "run" / "verdict.json").read_text()))
        self.assertEqual((v["verdict"], v["problems"], v["header"]["status"], v["header"]["records"], v["header"]["anomalies"]), ("PASS", [], "0x1", 292, 0))
        # ---- the addresses: 56 columns of one frame in the top half, a standstill, 8 in the bottom half, the limit
        top, bottom = [0x01000000 + (c << 7) for c in range(56)], [0x01400000 + (c << 7) for c in range(8)]
        self.assertEqual([int(s["far"], 16) for s in v["walk"]], top + bottom)
        self.assertEqual([int(s["next"], 16) for s in v["walk"]], (top + bottom)[1:] + [0x01400400], "each address is the one named after the one before")
        self.assertEqual(v["passes"], [{"frames": 64, "ended": "the limit of frames was reached", "last_address_named": "0x01400400"}] * 2)
        self.assertEqual(v["standstills"], [{"at": "0x01001b80", "register_after_the_pad_alone": "0x01001b80", "register_after_the_frame": "0x01400000"}])
        self.assertEqual((v["frames_without_a_second_path"], v["most_frames_between_reference_reads"]), ([], 16))
        self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()))
        # ---- the records: what was read, and the reference frame as known to the end
        kinds = [(r["kind"], r["frames"]) for r in v["records"]]
        self.assertEqual([kinds.count(k) for k in (("target", 0), ("target", 1), ("target", 3))], [128, 128, 22])
        ref = [r for r in v["records"] if r["kind"] != "target"]
        self.assertEqual(([r["kind"] for r in ref], {r["far"] for r in ref}, len({r["frame_sha256"][0] for r in ref})),
                         (["baseline"] + ["health"] * 12 + ["final"], {"0x00000b99"}, 1))
        self.assertIs(v["records"][-1], ref[-1], "the last record is a reference read, after the last read in block type 2")
        self.assertEqual(max(int(r["far"], 16) for r in v["records"] if r["kind"] == "target"), 0x01400380, "nothing asked for above the last address walked")
        self.assertEqual({h for r in v["records"] if r["kind"] == "target" for h in r["frame_sha256"]}, {hashlib.sha256(bytes(404)).hexdigest()}, "every frame all zero")
        self.assertEqual(sum(len(r["frame_sha256"]) for r in v["records"] if r["kind"] == "target"), 194)
        rec = json.loads((d / "run" / "run.json").read_text())
        self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"]), ("PASS", [], [], True, "50033004"))
        self.assertEqual((rec["board_crc32"], len(rec["pull"]["repeated"]), rec["pull"]["pieces"]), (rec["host_crc32"], 2, 69))
        # ---- the layout
        out = s1b4a_layout.layout(v)
        self.assertEqual(out, json.loads((d / "layout.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "layout.json").read_bytes()).hexdigest(), "64ab6d9d6f334c9791a47dd169b1821ee0354644326251b0056905123d7be7d8")
        self.assertEqual((out["block_types"], out["frames_per_row"], out["unexpected"], out["end"]["reached"]), ([2], [[2, "top", 0, 56], [2, "bottom", 0, 8]], [], False))
        self.assertEqual([(r["walked_whole"], r["ended_by"], r["named_after_the_last_frame"], [(c["column"], c["frames"]) for c in r["columns"]]) for r in out["rows"]],
                         [(True, "the register stood still", "0x01400000", [(c, 1) for c in range(56)]), (False, "not ended", None, [(c, 1) for c in range(8)])])
        self.assertEqual((out["content"]["frames_not_all_zero"], out["content"]["distinct_contents"]), (0, 1), "every frame all zero: the list rests on the register")
        # ---- the status: no bit that is neither an error nor usual; bit 5 did not show
        seen = status_seen.seen(v)
        self.assertEqual((seen["status_words"], seen["bits"]), (1462, []))
        self.assertEqual(json.loads((d / "status_seen.json").read_text())["by_run"][0]["bits"], [])
        self.assertEqual(int(v["header"]["ctrl"], 16) & 0x100, 0, "SEU_EN is clear")
        self.assertFalse((d / "grade.json").exists(), "nothing to grade against: nothing was graded")
        # ---- the board was sent nothing but what the run script sends: one console log, the pre-check's, beside the run's
        self.assertEqual(sorted(p.name for p in d.rglob("console.log")) + sorted(p.name for p in d.glob("*console.log")), ["console.log", "precheck_console.log"])

    def test_the_chain_over_block_type_2(self) -> None:
        """S1b.5, 2026-11-19: two runs from `0x01000000`; the second stood still at `0x01401b80` and was then told
        `0x01800000`, which is outside the envelope: the chain is complete. Both runs are judged again here from their
        raw words against the set kept with them; the summary, the comparison and the listing of status bits are what
        the programs give now. Nothing was graded: there is nothing to grade against."""
        import s1b2_chain, s1b3_rows, s1b4_first, status_seen
        d = ROOT / "evidence" / "s1b5_17A6_2026-11-19"
        expected = json.loads((d / "expected_s1b5.json").read_text())
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), expected["image_sha256"])
        self.assertEqual(expected["image_sha256"], "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        base = [int(w, 16) for w in expected["params"]]
        self.assertEqual((base[3], base[4], base[5], base[10], base[12], base[16]), (0, 0x017FFFFF, 0xB99, 1, 64, 0x01000000))
        self.assertEqual([hashlib.sha256((d / f"run{k:02d}" / "result.bin").read_bytes()).hexdigest() for k in range(2)],
                         ["747952c43eee9e2754b83c309ab8bbfbc83021ffb7d00f6babb63baf0ce0552d", "49aafd335ce75257fec6af91ea50d1b9e65fe830b3b5f1e5267e4e38d26d670a"])
        a = s1b2_chain.assess(d, base, KNOWN, s1b2_chain.BOUNDS["s1b5"], "s1b5")
        self.assertEqual((a["state"], len(a["runs"]), a["named_after_the_last_frame"], a["set_aside"]), ("complete", 2, "0x01800000", []))
        self.assertEqual([(r["decision"], r["start"], r["frames"], r["last"]) for r in a["runs"]],
                         [("go on", "0x01000000", 64, "0x01400380"), ("complete", "0x01400380", 49, "0x01401b80")])
        self.assertEqual(s1b2_chain.brief(a), json.loads((d / "chain.json").read_text()))
        # ---- the summary over rows, and the file committed before anything else was made of the chain
        rows = json.loads(json.dumps(s1b3_rows.summarize(a, KNOWN)))
        self.assertEqual(rows, json.loads((d / "rows.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "rows.json").read_bytes()).hexdigest(), "4d1f2fbe02bd8432724a95e222970eeb8ca86af653720cdca1cd094b9451816d")
        self.assertEqual((rows["frames"], rows["unexpected"], rows["frames_per_row"]), (112, [], [[2, "top", 0, 56], [2, "bottom", 0, 56]]))
        self.assertEqual([(r["walked_whole"], r["ended_by"], r["first"], r["last"], r["named_after_the_last_frame"], r["frames_per_column"]) for r in rows["rows"]],
                         [(True, "the register stood still", "0x01000000", "0x01001b80", "0x01400000", [[c, 1] for c in range(56)]),
                          (True, "the register stood still", "0x01400000", "0x01401b80", "0x01800000", [[c, 1] for c in range(56)])])
        self.assertEqual([int(s["far"], 16) for s in rows["addresses"]], [half | c << 7 for half in (0x01000000, 0x01400000) for c in range(56)])
        self.assertEqual(rows["standstills"], [{"after": "0x01001b80", "named": "0x01400000"}, {"after": "0x01401b80", "named": "0x01800000"}])
        self.assertEqual((rows["end"]["reached"], rows["end"]["named_after_the_last_frame"], rows["end"]["after_a_standstill"], rows["end"]["that_address"]["block_type"]),
                         (True, "0x01800000", True, 3))
        self.assertEqual({s["frame_sha256"] for s in rows["addresses"]}, {hashlib.sha256(bytes(404)).hexdigest()}, "every frame all zero: the list rests on the register")
        self.assertEqual(rows["known_frames_walked"], [], "the frames with a known answer lie below the set's first address")
        # ---- the two runs: what was read, the reference frame to the end, nothing asked for above the last address
        records = 0
        for k, (n, frames, pieces) in enumerate(((292, 194, 69), (224, 149, 53))):
            rec = json.loads((d / f"run{k:02d}" / "run.json").read_text())
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"]), ("PASS", [], [], True, "50033004"), k)
            self.assertEqual((rec["board_crc32"], rec["pull"]["pieces"], len(rec["pull"]["repeated"])), (rec["host_crc32"], pieces, 1), k)
            self.assertEqual((v["header"]["records"], v["header"]["anomalies"], v["frames_without_a_second_path"], v["most_frames_between_reference_reads"]), (n, 0, [], 16), k)
            self.assertTrue(all(not p["interface_failures"] for p in v["polling_variable"].values()), k)
            ref = [r for r in v["records"] if r["kind"] != "target"]
            self.assertEqual(({r["far"] for r in ref}, len({r["frame_sha256"][0] for r in ref}), v["records"][-1]["kind"]), ({"0x00000b99"}, 1, "final"), k)
            self.assertEqual(sum(len(r["frame_sha256"]) for r in v["records"] if r["kind"] == "target"), frames, k)
            self.assertLessEqual(max(int(r["far"], 16) for r in v["records"]), 0x01401B80, "the address named above the envelope was never asked for")
            self.assertEqual(int(v["header"]["ctrl"], 16) & 0x100, 0, "SEU_EN is clear")
            records += len(v["records"])
        self.assertEqual(records, 516)
        log = (d / "resets_console.log").read_bytes()
        self.assertEqual(log.count(b"<<TX b'reset\\r'>>"), 2, "a reset before each run, and none after the last")
        # ---- the stored run of S1b.5a against the chain's list
        stored = json.loads((ROOT / "evidence" / "s1b5a_17A6_2026-11-19" / "run" / "verdict.json").read_text())
        first = s1b4_first.against(rows, stored)
        self.assertEqual(first, json.loads((d / "first_run_against_s1b5a.json").read_text()))
        self.assertEqual((first["disagreements"], first["of_which_in_the_chain"], first["same_frames"], first["same_address_named"], first["frames_not_all_zero"]), ([], 64, 64, 64, 0))
        # the chain's first run is that run over again: every record, but for how many times a transfer was polled
        again = json.loads((d / "run00" / "verdict.json").read_text())
        self.assertEqual({k for k in again if again[k] != stored[k]}, {"records"})
        self.assertEqual({k for x, y in zip(again["records"], stored["records"]) for k in x if x[k] != y[k]}, {"polls"})
        # ---- the status: no bit that is neither an error nor usual, in either run
        files = status_seen.verdicts(d)
        self.assertEqual([f.parent.name for f in files], ["run00", "run01"])
        seen = [status_seen.seen(json.loads(f.read_text())) for f in files]
        self.assertEqual([(s["status_words"], s["bits"]) for s in seen], [(1462, []), (1122, [])])
        listed = json.loads((d / "status_seen.json").read_text())
        self.assertEqual(([{k: r[k] for k in ("status_words", "bits")} for r in listed["by_run"]], listed["bits"]), (seen, []))
        self.assertFalse((d / "grade.json").exists(), "nothing to grade against: nothing was graded")

    def test_the_run_at_the_address_named_after_block_type_2(self) -> None:
        """S1b.6a, 2026-11-19: one run of the walk from `0x01800000`. It was stopped by the walk at the second
        standstill of its first pass (`0x900`) and is a failed run by its judge. Judged again here from its raw words
        against the set kept with it; what the record says of its 21 records is held here."""
        import s1b2_judge, s1b4a_layout, status_seen
        d = ROOT / "evidence" / "s1b6a_17A6_2026-11-19"
        raw = (d / "run" / "result.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "e7e73c4e4f901bcb72589436007f5a3b9cf86c33892d15e247b788a04ec8f668")
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452")
        planned = [int(w, 16) for w in json.loads((d / "expected_s1b6a.json").read_text())["params"]]
        self.assertEqual((planned[3], planned[4], planned[5], planned[10], planned[12], planned[16]), (0, 0x01FFFFFF, 0xB99, 1, 64, 0x01800000))
        v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), KNOWN, planned)
        self.assertEqual(v, json.loads((d / "run" / "verdict.json").read_text()))
        self.assertEqual((v["verdict"], v["header"]["status"], v["header"]["records"], v["header"]["anomalies"], v["header"]["stop_record"]), ("FAIL", "0x900", 21, 0, "0x13"))
        self.assertEqual(len(v["problems"]), 2, "the second standstill, said twice: by the register and by the prober's status")
        self.assertIn("status 0x900", v["problems"][1])
        # ---- the records: the reference frame once, then the pad alone and the pad with a frame at ten addresses
        top, bottom = [0x01800000 + (c << 7) for c in range(5)], [0x01C00000 + (c << 7) for c in range(5)]
        recs = v["records"]
        self.assertEqual([(r["kind"], int(r["far"], 16), r["frames"], r["pass"]) for r in recs],
                         [("baseline", 0xB99, 1, 0)] + [("target", a, n, 0) for a in top + bottom for n in (0, 1)])
        after = [int(r["far_read_back"], 16) for r in recs[1:]]
        self.assertEqual(after[0::2], top[1:] + [top[-1]] + bottom[1:] + [bottom[-1]], "after the pad alone: the next column, and at a row's last frame no step")
        self.assertEqual(after[1::2], top[2:] + [top[-1], 0x01C00000] + bottom[2:] + [bottom[-1], 0x02000000], "after the frame: one step more")
        self.assertEqual(max(int(r["far"], 16) for r in recs), 0x01C00200, "0x02000000 was read in the register and never asked for")
        self.assertEqual({h for r in recs[1:] for h in r["frame_sha256"]}, {hashlib.sha256(bytes(404)).hexdigest()}, "every frame all zero")
        self.assertTrue(all(r["pad_all_zero"] and r["code"] == "0x0" for r in recs))
        self.assertEqual([r["kind"] for r in recs].count("baseline") + [r["kind"] for r in recs].count("health") + [r["kind"] for r in recs].count("final"), 1,
                         "no reference read after the first: the run does not show block type 0 readable afterwards")
        self.assertEqual(v["standstills"], [{"at": "0x01800200", "register_after_the_pad_alone": "0x01800200", "register_after_the_frame": "0x01c00000"}])
        self.assertEqual(v["passes"][0], {"frames": 10, "ended": "not ended", "last_address_named": "0x01c00200"})
        rec = json.loads((d / "run" / "run.json").read_text())
        self.assertEqual((rec["verdict"], rec.get("stop"), rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"], rec["return_code"]),
                         ("FAIL", None, [], True, "50033004", "0x900"))
        self.assertEqual((rec["board_crc32"], rec["pull"]["pieces"], rec["pull"]["repeated"]), (rec["host_crc32"], 5, []))
        # ---- the layout, which says of itself that it is not a finding
        out = s1b4a_layout.layout(v)
        self.assertEqual(out, json.loads((d / "layout.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "layout.json").read_bytes()).hexdigest(), "d2ca3c829b9dec70222cdbe91c763a5acd1ee256b48dddfcb0beabc6fe531a03")
        self.assertIn("is not a finding", out["note"])
        self.assertEqual((out["block_types"], out["frames_per_row"], out["unexpected"], out["end"]["reached"]), ([3], [[3, "top", 0, 5], [3, "bottom", 0, 5]], [], False))
        self.assertEqual([(r["walked_whole"], r["frames_per_column"]) for r in out["rows"]], [(True, [[c, 1] for c in range(5)]), (False, [[c, 1] for c in range(5)])])
        # ---- the status: no bit that is neither an error nor usual
        seen = status_seen.seen(v)
        self.assertEqual((seen["status_words"], seen["bits"]), (107, []))
        self.assertEqual(json.loads((d / "status_seen.json").read_text())["by_run"][0]["bits"], [])
        self.assertFalse((d / "grade.json").exists(), "nothing to grade against: nothing was graded")

    def test_the_frame_census(self) -> None:
        """2026-11-19: the census as one document (census/frame_census_17A6.json), made by host/s1_census.py from the
        three complete chains, the run at `0x01800000`, and every other stored run with a passing walk. The stored
        document is what the program gives now, from the raw words of the chains; and what census/README.md says of
        it is held here. Nothing in it is graded."""
        import jsonschema, s1_census, stage_designs
        stage_designs.stage()                           # the document says the design's hash was held against the file: the file has to be staged (section 24 of the S2 plan)
        e = ROOT / "evidence"
        parts = [s1_census.chain_part(s, e / d, KNOWN) for s, d in (("s1b3", "s1b3_17A6_2026-11-17"), ("s1b4", "s1b4_17A6_2026-11-18"), ("s1b5", "s1b5_17A6_2026-11-19"))]
        also = [(n, s1_census.stored_verdicts(e / d)) for n, d in (("s1b1r", "s1b1r_17A6_2026-11-15"), ("dx", "dx_17A6_2026-11-15"), ("quiet", "quiet_17A6_2026-11-15"),
                                                                 ("s1b2", "s1b2_17A6_2026-11-15"), ("s1b3a", "s1b3a_17A6_2026-11-17"), ("s1b4a", "s1b4a_17A6_2026-11-18"),
                                                                 ("sbit", "sbit_17A6_2026-11-19"), ("s1b5a", "s1b5a_17A6_2026-11-19"))]
        c = s1_census.build(parts, seen=[("s1b6a", s1_census.stored_verdicts(e / "s1b6a_17A6_2026-11-19"))], also=also)
        stored = ROOT / "census" / "frame_census_17A6.json"
        self.assertEqual(s1_census.dump(c), stored.read_text())
        self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), "dbc6d4a16f5972fbfb354d983150143a3b83d0396729e96f5e6d64fb0b24a208")
        jsonschema.Draft202012Validator(json.loads((ROOT / "schemas" / "frame_census_v1.schema.json").read_text())).validate(c)
        self.assertEqual((c["label"], c["problems"]), ("closed-book", []))
        self.assertEqual(c["totals"], {"addresses": 5256, "stretches": 1, "by_block_type": [[0, 3864], [1, 1280], [2, 112]], "readings": 16181, "fewest_readings_of_an_address": 3,
                                       "not_stable": 0, "all_zero": 4060, "distinct_contents_that_are_not_zero": 425, "seen_not_walked": 10, "named_not_read": 1})
        self.assertEqual((c["binding"]["pl_design_sha256"][:8], c["binding"]["prober_image_sha256"][:8], [(x["set"], x["runs"], x["addresses"]) for x in c["binding"]["chains"]]),
                         ("8c3369e8", "fdc4f07f", [("s1b3", 62, 3864), ("s1b4", 21, 1280), ("s1b5", 2, 112)]))
        # what each chain's own files show was loaded (review of f465f17): the image kept beside the runs, and U-Boot's checksums in all 85 run records
        self.assertEqual({k: v for k, v in c["binding"].items() if k != "chains"},
                         {"prober_image_sha256": "fdc4f07fa71db7ff23d6e64f8a3168bc055ca7ee402c37709d34fd69270e9452", "prober_image_crc32": "84f107a1",
                          "pl_design_sha256": "8c3369e8e4755da5aceeb7844690d5e132b2e65647004c0a46c0e868e34f0b8a", "pl_design_bytes": 2083863,
                          "pl_design_crc32_in_ram": "72887bf4", "pl_design_sha256_held_against_the_file": True})
        self.assertTrue(all((e / x["directory"] / "prober.bin").is_file() and (e / x["directory"] / f"expected_{x['set']}.json").is_file() for x in c["binding"]["chains"]),
                        "each chain has its image and its set kept with its runs")
        self.assertEqual(c["stretches"], [{"first": "0x00000000", "last": "0x01401b80", "addresses": 5256, "named_after_the_last": "0x01800000"}], "one stretch: no chain left out")
        self.assertEqual(c["seen_runs"], [{"name": "s1b6a", "run": "s1b6a_17A6_2026-11-19", "verdict": "FAIL", "status": "0x900", "records_used": 20, "records_not_used": []}])
        two = s1_census.build([parts[0], parts[2]])        # the reviewer's case: the chain over block type 1 left out
        self.assertEqual([(s["first"], s["last"], s["named_after_the_last"]) for s in two["stretches"]],
                         [("0x00000000", "0x00401ba9", "0x00800000"), ("0x01000000", "0x01401b80", "0x01800000")])
        # ---- the entries: rising, each chain's list linked by the address named, the next chain beginning where the one before pointed
        fars = [int(x["far"], 16) for x in c["entries"]]
        self.assertEqual(fars, sorted(set(fars)))
        self.assertTrue(all(a["named_next"] == b["far"] for a, b in zip(c["entries"], c["entries"][1:])), "5,256 addresses in one line, each named by the one before")
        self.assertEqual(c["entries"][-1]["named_next"], c["seen_not_walked"][0]["far"])
        self.assertEqual([sum(1 for x in c["entries"] if x["readings"] == n) for n in (3, 4, 6)], [5007, 167, 82])
        self.assertEqual(sum(len(x["runs"]) for x in parts) - len(parts), 82, "the frames with six readings are the seams of the chains")
        self.assertEqual([len({x["frame_sha256"] for x in c["entries"] if x["block_type"] == t and not x["all_zero"]}) for t in (0, 1, 2)], [424, 1, 0])
        self.assertEqual([x["far"] for x in c["entries"] if x.get("stood_still")], [r["last"] for r in c["rows"]])
        self.assertEqual([(r["block_type"], r["half"], r["row"], r["frames"], len(r["columns"])) for r in c["rows"]],
                         [(0, "top", 0, 1932, 56), (0, "bottom", 0, 1932, 56), (1, "top", 0, 640, 5), (1, "bottom", 0, 640, 5), (2, "top", 0, 56, 56), (2, "bottom", 0, 56, 56)])
        zero = {t: sum(1 for x in c["entries"] if x["block_type"] == t and x["all_zero"]) for t in (0, 1, 2)}
        self.assertEqual(zero, {0: 3864 - 428, 1: 512, 2: 112})
        # ---- seen and not walked, named and not read
        self.assertEqual([x["far"] for x in c["seen_not_walked"]], [f"{half | col << 7:#010x}" for half in (0x01800000, 0x01C00000) for col in range(5)])
        self.assertEqual({(x["state"], x["readings"], x["all_zero"], x["evidence"]["verdict"], x["evidence"]["status"]) for x in c["seen_not_walked"]}, {("seen", 1, True, "FAIL", "0x900")})
        self.assertEqual([(x["far"], x["block_type"], x["state"]) for x in c["named_not_read"]], [("0x02000000", 4, "named")])
        # ---- the status bit of block type 1, as the chain's test has it
        (bit,) = c["status_bits"]
        self.assertEqual((bit["bit"], bit["chain"], bit["runs"]), (5, "s1b4", [f"run{k:02d}" for k in (4, 5, 6, 7, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20)]))
        self.assertEqual(bit["first_shown_at"][0], ["run04", 10, "0x00800100"])
        # ---- other occasions: every stored run with a passing walk outside the three chains, and nothing in them differs
        outside = set()
        for f in e.rglob("verdict.json"):
            v = json.loads(f.read_text())
            if v.get("verdict") == "PASS" and v.get("walk") and not any(f.is_relative_to(e / x["directory"]) for x in c["binding"]["chains"]):
                outside.add(f.relative_to(e).parts[0])
        self.assertEqual(outside, {"s1b1r_17A6_2026-11-15", "dx_17A6_2026-11-15", "quiet_17A6_2026-11-15", "s1b2_17A6_2026-11-15", "s1b3a_17A6_2026-11-17",
                                   "s1b4a_17A6_2026-11-18", "sbit_17A6_2026-11-19", "s1b5a_17A6_2026-11-19"}, "none left out, none more")
        self.assertEqual([(o["name"], o["runs_used"], o["addresses"], o["readings_alike"], o["different"]) for o in c["other_occasions"]],
                         [("s1b1r", 1, 36, 36, []), ("dx", 5, 26, 130, []), ("quiet", 6, 26, 156, []), ("s1b2", 30, 1891, 1920, []), ("s1b3a", 1, 64, 64, []),
                          ("s1b4a", 1, 64, 64, []), ("sbit", 1, 64, 64, []), ("s1b5a", 1, 64, 64, [])])
        self.assertEqual((sum(o["runs_used"] for o in c["other_occasions"]), sum(o["readings_alike"] for o in c["other_occasions"])), (46, 2498))
        again = set()
        for _, verdicts in also:
            again |= {s["far"] for _, v in verdicts if v.get("verdict") == "PASS" for s in v.get("walk") or []}
        self.assertEqual(len(again & {x["far"] for x in c["entries"]}), 2146, "addresses of the census walked on more than one occasion")

    def test_the_chain_over_the_three_states_of_the_ram(self) -> None:
        """S2.2, 2026-11-22: eight runs, one of each share of block type 0, each in the three states of the design's RAM.
        The chain is assessed again here from the raw words of its results, against the set and the image kept with
        the runs: complete, 256 candidates — as many as the RAM has cells — in four frames next to each other, every
        other bit still, the RAM as written after every pass. The run that stopped at the first try of share 1 lies
        set aside and is no part of it. Nothing was graded."""
        import s1a_run, s2_2_chain, status_seen
        d = ROOT / "evidence" / "s2_2_17A6_2026-11-22"
        base = json.loads((d / "expected_s2_2.json").read_text())
        self.assertEqual(hashlib.sha256((d / "prober.bin").read_bytes()).hexdigest(), base["image_sha256"])
        self.assertEqual(base["image_sha256"], "94ad860cf80b4f1f3d41bba7e03d475450846416fc0740789e9dd528aae86f50")
        self.assertEqual([hashlib.sha256((d / f"run{k:02d}" / "result.bin").read_bytes()).hexdigest() for k in range(8)],
                         ["0294171583108ed3f9302505e3433c6b254c96b9e9e81e768b8e7aac5244f8b1", "e89bb4bd8c7c089e43f397a30453366397036e2b67e62e264e3f4ac309da5aa9",
                          "c90f7f6f80bbf99db7d9be8e1ce7ed20aa5139c2b74ba5f609f1debdcf3f9349", "2e11cbb23c113fe7982482cd95f6d048dd2f127bf72b7759fd9289714f38d433",
                          "9eafb9fc8cab687b0a4afb3b7ee7c5f696cf622850adb777c074e2b2c69cc69a", "0cb3e7984f635d465434a02f2070ed29ef6ff3d66fb346e8532d710a98781220",
                          "7a48e6cc9337771f0727f41673311b8595e0824edd63d294ced323c7a89c234b", "ecae47d0038ffede621051da91b348635b509068898efef951007bde5b46526b"])
        known = s1a_run.known_for("s2_2")
        import stage_designs
        stage_designs.stage()                           # the chain holds the staged design to the set: in a copy fresh from git nothing has staged it yet (review of 5936a8e)
        a = s2_2_chain.assess(d, base, known)
        self.assertEqual((a["state"], len(a["runs"]), a["set_aside"]), ("complete", 8, ["halted_at_run01"]))
        self.assertEqual([(r["share"], r["decision"], r["reads"], r["frames"], len(r["candidates"]), r["restless"], r["ctl0"]) for r in a["runs"]],
                         [(k, "complete" if k == 7 else "go on", reads, frames, 256 if k == 6 else 0, 0, "0x00000501")
                          for k, (reads, frames) in enumerate(((174, 516), (174, 516), (174, 520), (176, 524), (172, 508), (176, 524), (172, 512), (82, 244)))])
        c = a["closing"]
        self.assertEqual((c["problems"], c["addresses_read"], c["cells_in_the_design"], c["candidates"], c["candidates_inverted"], c["outcome"][:2]), ([], 3864, 256, 256, 0, "1:"))
        self.assertEqual(c["frames_with_candidates"], {f"0x{f:08x}": 64 for f in range(0x00401220, 0x00401224)})
        self.assertEqual([(x["far"], x["word"], x["bit"], x["inverted"], x["run"]) for x in c["found"]],
                         [(f"0x{f:08x}", w, b, False, "run06") for f in range(0x00401220, 0x00401224) for w in (61, 62) for b in range(32)])
        self.assertEqual((c["bit_5"], c["bit_5_still_set_after_clearing"]), ({"run03": [46, 47, 222, 223, 398, 399]}, {}))
        # ---- what was written beside the runs when the chain closed is what the programs give now
        self.assertEqual(s2_2_chain.brief(a), json.loads((d / "chain.json").read_text()))
        self.assertEqual(json.loads(json.dumps(s2_2_chain.candidates_file(a, known))), json.loads((d / "candidates.json").read_text()))
        self.assertEqual(hashlib.sha256((d / "candidates.json").read_bytes()).hexdigest(), "9b2103c50985429cdc15839618e756f975bd10f2effc71cbb64e007c78f600f0")
        # ---- the eight runs: whole, saved, pulled; the reference frame the same before and after; the design as it was built
        still = pieces_again = 0
        for k in range(8):
            rec = json.loads((d / f"run{k:02d}" / "run.json").read_text())
            v = json.loads((d / f"run{k:02d}" / "verdict.json").read_text())
            self.assertEqual((rec["verdict"], rec["problems"], rec["replies_not_whole"], rec["card_verified"], rec["int_sts_afterwards"], rec["return_code"]),
                             ("PASS", [], [], True, "50033004", "0x0"), k)
            self.assertEqual(rec["board_crc32"], rec["host_crc32"], k)
            self.assertEqual((v["header"]["anomalies"], v["finding"]["states_read_whole"], v["finding"]["bits"]["restless"]), (0, 3, 0), k)
            self.assertEqual((v["pl"]["code"], v["pl"]["passes_the_ram_held_through"], v["pl"]["writes_counted"]["shifts"], v["pl"]["id"]), ("0x0", 3, 0, "0x53324131"), k)
            self.assertEqual(v["pl"]["shift_registers_hold"], ["0xa5c30f69", "0x0f1e2d3c", "0x13579bdf", "0xfedcba98"], k)
            ref = [r for r in v["records"] if r["kind"] != "target"]
            self.assertEqual(([r["kind"] for r in ref], {r["far"] for r in ref}, len({r["frame_sha256"][0] for r in ref}), v["records"][-1]["kind"]),
                             (["baseline", "final"], {"0x00000b99"}, 1, "final"), k)
            self.assertEqual(int(v["header"]["ctrl"], 16) & 0x100, 0, "SEU_EN is clear")
            still += v["finding"]["bits"]["still"]
            pieces_again += len(rec["pull"]["repeated"])
        self.assertEqual((still + 256, pieces_again), (3864 * 101 * 32, 10), "every bit of every frame of block type 0 is still or a candidate")
        # ---- a reset before each run and none after the last: the eight, and the one that was set aside
        self.assertEqual((d / "resets_console.log").read_bytes().count(b"<<TX b'reset\\r'>>"), 9)
        halted = json.loads((d / "halted_at_run01" / "run01" / "run.json").read_text())
        self.assertEqual((halted["share"]["index"], halted["stop"], halted["verdict"], sorted(p.name for p in (d / "halted_at_run01" / "run01").iterdir())),
                         (1, "no prompt after 'md.l 10000000 40'", "FAIL", ["console.log", "list.bin", "run.json"]))
        self.assertEqual(json.loads((d / "halted_at_run01" / "chain.json").read_text())["state"], "halted")
        # ---- the status: one run with a bit that is neither an error nor usual
        files = status_seen.verdicts(d)
        seen = [status_seen.seen(json.loads(f.read_text())) for f in files]
        self.assertEqual([f.parent.name for f, s in zip(files, seen) if s["bits"]], ["run03"])
        listed = json.loads((d / "status_seen.json").read_text())
        self.assertEqual(([{k: r[k] for k in ("status_words", "bits")} for r in listed["by_run"]], listed["bits"], sum(s["status_words"] for s in seen)), (seen, [5], 19676))
        self.assertFalse((d / "grade.json").exists(), "nothing was graded")

    def test_the_replies_the_board_gave_by_the_rule_for_a_whole_reply(self) -> None:
        """The run script asks again for a dump of a few words or a checksum whose reply is not whole (2026-11-18). The
        rule for "whole" is held here against every such reply stored from the board so far, as the run records have
        them: all are whole, and say what the run took from them — but two. The header dump of run 51 of the chain over
        block type 0 lost a stretch of characters and stopped that run, before the rule was there. The header dump of
        the second run of S2.2 (2026-11-22) lost stretches too, and most of the prompt after it: no prompt is not a
        reply to ask again for, and that run stopped as the rule has it."""
        import s1a_run
        seen = {"md.l": 0, "crc32": 0}
        not_whole, headers = [], 0
        for record in sorted((ROOT / "evidence").rglob("run.json")):
            rec = json.loads(record.read_text())
            for step in rec.get("steps", []):
                word = step["cmd"].split()[0]
                if word not in seen or " … " in step["reply"]:           # a long reply is stored shortened: a piece of a result
                    continue
                seen[word] += 1
                got = s1a_run.whole(step["cmd"], step["reply"])
                if got is None:
                    not_whole.append((str(record.relative_to(ROOT / "evidence")), step["cmd"]))
                elif step["cmd"] == "md.l 10000000 40" and step["what"] == "the result header":
                    headers += 1
                    self.assertEqual(b"".join(struct.pack("<I", x) for x in got), (record.parent / "header.bin").read_bytes(), record)
                elif step["what"] == "the result checksum on the board":
                    self.assertEqual(got, rec["board_crc32"], record)
                elif step["what"] == "status afterwards":
                    self.assertEqual(f"{got[0]:08x}", rec["int_sts_afterwards"], record)
        self.assertEqual(not_whole, [("s1b3_17A6_2026-11-17/halted_at_run51/run51/run.json", "md.l 10000000 40"),
                                     ("s2_2_17A6_2026-11-22/halted_at_run01/run01/run.json", "md.l 10000000 40")])
        self.assertGreater(seen["crc32"], 7000)
        self.assertGreater(seen["md.l"], 700)
        self.assertGreaterEqual(headers, 145)

    def test_a_stored_result_with_one_word_changed_does_not_pass(self) -> None:
        for judge, run, expected, _ in RUNS:
            with self.subTest(run=run):
                raw, planned = load(run, expected)
                words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
                words[len(words) // 2] ^= 1
                self.assertNotEqual(judge.judge(words, KNOWN, planned)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()

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

    def test_the_replies_the_board_gave_by_the_rule_for_a_whole_reply(self) -> None:
        """The run script asks again for a dump of a few words or a checksum whose reply is not whole (2026-11-18). The
        rule for "whole" is held here against every such reply stored from the board so far, as the run records have
        them: all are whole, and say what the run took from them — but one, the header dump of run 51 of the chain over
        block type 0, which lost a stretch of characters and stopped that run."""
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
        self.assertEqual(not_whole, [("s1b3_17A6_2026-11-17/halted_at_run51/run51/run.json", "md.l 10000000 40")])
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

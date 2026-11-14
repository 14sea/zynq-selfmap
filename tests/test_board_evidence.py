"""The results brought back from the board, judged again by the judges as they are now.

A judge that is tightened later must still pass what the board really returned, and a stored
result that was edited must not: each file is also held by its hash.
"""
import hashlib, json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1a_judge, s1b0_judge, s1b0b_judge  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
RUNS = [
    (s1a_judge, "s1a_17A6_2026-11-13", "expected.json", "b5cb491a8c4e3be07b4b0a03fb6afd35e491b938b15792cf06bd792ee7813c33"),
    (s1b0_judge, "s1b0_17A6_2026-11-14", "expected_s1b0.json", "46a5b5b6f643064befe63d36f2824ea45ec21e9c51b11ee9830de1ab46e2da6d"),    (s1b0b_judge, "s1b0b_17A6_2026-11-14", "expected_s1b0b.json", "9b94fe3aea6484e53c49d4e5e2dfe4a7368e7162c2700dc4788151ffb4008411"),
]


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

    def test_a_stored_result_with_one_word_changed_does_not_pass(self) -> None:
        for judge, run, expected, _ in RUNS:
            with self.subTest(run=run):
                raw, planned = load(run, expected)
                words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
                words[len(words) // 2] ^= 1
                self.assertNotEqual(judge.judge(words, KNOWN, planned)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()

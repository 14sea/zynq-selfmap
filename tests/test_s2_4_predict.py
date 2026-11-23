#!/usr/bin/env python3
"""S2.4, part 0: the prediction made from stored results (docs/s2_plan.md, section 37): host only."""
from __future__ import annotations

import hashlib, json, struct, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s2_4_predict as P  # noqa: E402

WORDS = [0xA5C30F69, 0x0F1E2D3C, 0x13579BDF, 0xFEDCBA98]
RULE = [(2 + (a & 1) - 2 * (a >> 3 & 1), 15 - ((a >> 1 & 1) + 2 * (a >> 2 & 1) + 4 * (a >> 4 & 1) + 8 * (a >> 5 & 1))) for a in range(64)]


def description(rule=None, change=None) -> dict:
    """A description as S2.3 writes one, as far as the rule is read from it: four memories under one rule."""
    rule = RULE if rule is None else rule
    entries = [{"memory": m, "ram_address": a, "address": f"{0x00401220 + f:#010x}/{62 if m in (0, 3) else 61}/{(16 if m in (0, 2) else 0) + b}"}
               for m in range(4) for a, (f, b) in enumerate(rule)]
    for i, address in (change or {}).items():
        entries[i]["address"] = address
    return {"entries": entries}


def planted(word: int, where: list[tuple[int, int]], far: int = 0x100, w: int = 7, half: int = 16, frames: int = 4) -> dict:
    """Frames that read zero but for one memory's worth of places, in the four frames from `far`: `where` says which
    address holds which bit (or its opposite, a negative number: -1 - j) of the word. Four frames and no more, unless
    a test asks: with a fifth the same bits can be named a second way (see the test of that)."""
    out = {far + f: [0] * P.FRAME for f in range(frames)}
    for a, j in where:
        f, b = RULE[a]
        bit = 1 - ((word >> (-1 - j)) & 1) if j < 0 else (word >> j) & 1
        out[far + f][w] |= bit << (half + b)
    return {k: tuple(v) for k, v in out.items()}


def result(records: list[tuple], status: int = 1) -> bytes:
    """A stored result as far as this program reads one: (far, kind, state, how many frames, op, the frames)."""
    words = [0] * 64
    words[2], words[3], words[6], words[7] = status, len(records), P.REC, 64
    for far, kind, state, m, op, frames in records:
        r = [0] * P.REC
        r[0], r[1], r[12], r[14], r[15] = far, kind, state, m, op
        for j, frame in enumerate(frames):
            r[P.DATA + P.FRAME * (j + 1): P.DATA + P.FRAME * (j + 2)] = frame
        words += r
    return struct.pack("<%dI" % len(words), *words)


def stored(*runs: bytes) -> Path:
    root = Path(scratch_dirs.mkdtemp(prefix="smpredict_"))
    for k, raw in enumerate(runs):
        (root / f"run{k:02d}").mkdir()
        (root / f"run{k:02d}" / "result.bin").write_bytes(raw)
    return root


def frame(x: int) -> list[int]:
    return [x + i for i in range(P.FRAME)]


class TheRule(unittest.TestCase):
    def test_the_rule_of_the_stored_description_is_six_moves(self) -> None:
        """Address bit 0 one frame up, bit 3 two frames down, bits 1, 2, 4 and 5 one, two, four and eight bits down
        the half word — written here, not taken from the program."""
        self.assertEqual(P.rule(json.loads(P.RAM_MAP.read_text())), RULE)
        self.assertEqual(P.rule(description()), RULE)
        self.assertEqual((RULE[0], RULE[1], RULE[8], RULE[2], RULE[63]), ((2, 15), (3, 15), (0, 15), (2, 14), (1, 0)))

    def test_a_description_that_is_not_of_that_form_gives_no_rule(self) -> None:
        other = list(RULE); other[0], other[1] = other[1], other[0]
        one_memory_otherwise = description()
        for a, (f, b) in enumerate(other):
            one_memory_otherwise["entries"][64 + a]["address"] = f"{0x00401220 + f:#010x}/61/{b}"
        self.assertRaisesRegex(ValueError, "do not obey one rule", P.rule, one_memory_otherwise)
        self.assertRaisesRegex(ValueError, "not 64 places in one word", P.rule, description(change={5: "0x00401222/60/29"}))
        short = description(); del short["entries"][70]
        self.assertRaisesRegex(ValueError, "not 64 places in one word", P.rule, short)
        twice = [RULE[0]] + RULE[:-1]
        self.assertRaisesRegex(ValueError, "does not fill four frames by sixteen bits", P.rule, description(rule=twice))
        self.assertRaisesRegex(ValueError, "do not obey one rule", P.rule, {"entries": []})


class TheArrangements(unittest.TestCase):
    def test_there_are_twenty_four_and_each_is_what_its_name_says(self) -> None:
        arr = dict(P.arrangements())
        self.assertEqual((len(P.arrangements()), len(arr)), (24, 24))
        self.assertEqual(sorted({len(v) for v in arr.values()}), [32, 64])
        self.assertEqual(arr["the odd addresses, in order, as it is"], [(2 * j + 1, j, 0) for j in range(32)])
        self.assertEqual(arr["the even addresses, reversed, inverted"], [(2 * j, 31 - j, 1) for j in range(32)])
        self.assertEqual(arr["the even and the odd addresses, in order, as it is"], [(a, j, 0) for j in range(32) for a in (2 * j, 2 * j + 1)])
        self.assertEqual(arr["the lower 32 addresses, in order, inverted"], [(j, j, 1) for j in range(32)])
        self.assertEqual(arr["the upper 32 addresses, reversed, as it is"], [(32 + j, 31 - j, 0) for j in range(32)])
        self.assertEqual(arr["the lower and the upper 32 addresses, in order, as it is"], [(a, j, 0) for j in range(32) for a in (j, 32 + j)])

    def test_the_pattern_of_a_word(self) -> None:
        arr = dict(P.arrangements())
        self.assertEqual(P.pattern(0x80000001, arr["the lower 32 addresses, in order, as it is"]), (0xFFFFFFFF, 0x80000001))
        self.assertEqual(P.pattern(0x80000001, arr["the upper 32 addresses, in order, inverted"]), (0xFFFFFFFF << 32, 0x7FFFFFFE << 32))
        self.assertEqual(P.pattern(0x00000001, arr["the lower 32 addresses, reversed, as it is"]), (0xFFFFFFFF, 0x80000000))
        self.assertEqual(P.pattern(0x00000003, arr["the odd addresses, in order, as it is"]), (0xAAAAAAAAAAAAAAAA, 0xA))
        self.assertEqual(P.pattern(0x00000001, arr["the even and the odd addresses, in order, as it is"]), (2 ** 64 - 1, 0x3))


class TheSearch(unittest.TestCase):
    def hits(self, frames: dict) -> list[tuple]:
        return [(h["shift_register"], h["frames"][0], h["word"], h["bits"], h["arrangement"]) for h in P.search(frames, RULE, WORDS)[1]]

    def test_a_word_is_found_where_it_was_put_and_as_it_was_put(self) -> None:
        at = ("0x00000100", 7, "31 down to 16")
        self.assertEqual(self.hits(planted(WORDS[2], [(2 * j + 1, j) for j in range(32)])), [(2, *at, "the odd addresses, in order, as it is")])
        self.assertEqual(self.hits(planted(WORDS[0], [(2 * j, 31 - j) for j in range(32)])), [(0, *at, "the even addresses, reversed, as it is")])
        self.assertEqual(self.hits(planted(WORDS[3], [(32 + j, -1 - j) for j in range(32)])), [(3, *at, "the upper 32 addresses, in order, inverted")])
        self.assertEqual(self.hits(planted(WORDS[1], [(j, -1 - (31 - j)) for j in range(32)], half=0, w=100)),
                         [(1, "0x00000100", 100, "15 down to 0", "the lower 32 addresses, reversed, inverted")])
        both = self.hits(planted(WORDS[1], [(a, j) for j in range(32) for a in (2 * j, 2 * j + 1)]))
        self.assertEqual(sorted(h[4] for h in both), sorted(f"the {w} addresses, in order, as it is" for w in ("even", "odd", "even and the odd")), "which holds all three")

    def test_what_is_not_one_of_the_words_or_not_so_arranged_is_not_found(self) -> None:
        self.assertEqual(P.search(planted(0, [], frames=6), RULE, WORDS), (3 * 101 * 2, []), "frames that read zero: three groups of four among six frames")
        self.assertEqual(self.hits(planted(WORDS[0] ^ 1, [(2 * j + 1, j) for j in range(32)])), [], "one bit off")
        self.assertEqual(self.hits(planted(WORDS[0], [(2 * j + 1, (j + 1) % 32) for j in range(32)])), [], "moved by one")
        self.assertEqual(self.hits(planted(WORDS[0], [(j, j) for j in range(16)] + [(48 + j, 16 + j) for j in range(16)])), [], "in two halves of its own")

    def test_four_frames_that_are_not_next_to_each_other_are_no_group(self) -> None:
        frames = planted(WORDS[2], [(2 * j + 1, j) for j in range(32)], frames=6)
        gap = {(far if far < 0x103 else far + 1): f for far, f in frames.items()}      # the same six frames, one address left out in their middle
        self.assertEqual((sorted(gap), P.search(gap, RULE, WORDS)), ([0x100, 0x101, 0x102, 0x104, 0x105, 0x106], (0, [])), "three and three: no four")
        self.assertEqual(P.search({far: f for far, f in frames.items() if far >= 0x101}, RULE, WORDS)[0], 2 * 101 * 2, "five frames: two groups")

    def test_with_a_fifth_frame_the_same_bits_have_a_second_name(self) -> None:
        """The odd addresses of the four frames from F are the even addresses of the four from F + 1: the rule moves
        one frame up for address bit 0. So where a fifth frame follows and reads zero at that word, a word at the odd
        addresses is found twice, under two names for the same bits. On the device the four frames of the prediction
        are the last of their column — as the RAM's four are of theirs — and there is no fifth."""
        five = planted(WORDS[2], [(2 * j + 1, j) for j in range(32)], frames=5)
        self.assertEqual(self.hits(five), [(2, "0x00000100", 7, "31 down to 16", "the odd addresses, in order, as it is"),
                                           (2, "0x00000101", 7, "31 down to 16", "the even addresses, in order, as it is")])
        frames = P.frames_as_loaded()
        self.assertEqual([far in frames for far in (0x181F, 0x1823, 0x1824, 0x0040121F, 0x00401223, 0x00401224)], [True, True, False, True, True, False])

    def test_what_the_search_is_said_to_have_found(self) -> None:
        hit = lambda k, far=0x1820, arr="x": {"shift_register": k, "frames": [f"{far:#010x}"], "arrangement": arr}
        self.assertEqual(P.says([], 4), "not found")
        self.assertTrue(P.says([hit(k) for k in range(4)], 4).startswith("found: each of the loaded words once"))
        for hits in ([hit(k) for k in range(3)], [hit(k) for k in range(4)] + [hit(0)], [hit(0), hit(1), hit(2), hit(3, far=0x1900)],
                     [hit(0), hit(1), hit(2), hit(3, arr="y")], [hit(0)]):
            self.assertEqual(P.says(hits, 4), "found, and not that simply: see the hits")


class TheFramesAsLoaded(unittest.TestCase):
    def test_the_first_state_s_frames_where_the_third_read_the_same(self) -> None:
        a, b, c = frame(100), frame(200), frame(300)
        root = stored(result([(0x10, 0, 0, 2, 0, [a, b]), (0x10, 0, 1, 2, 0, [c, c]), (0x10, 0, 2, 2, 0, [a, b])]),
                      result([(0x20, 0, 0, 1, 0, [c]), (0x20, 0, 1, 1, 0, [a]), (0x20, 0, 2, 1, 0, [c])]))
        self.assertEqual(P.frames_as_loaded(root), {0x10: tuple(a), 0x11: tuple(b), 0x20: tuple(c)})

    def test_a_frame_that_read_otherwise_the_third_time_is_left_out(self) -> None:
        a, b, c = frame(100), frame(200), frame(300)
        root = stored(result([(0x10, 0, 0, 2, 0, [a, b]), (0x10, 0, 1, 2, 0, [a, b]), (0x10, 0, 2, 2, 0, [a, c])]))
        self.assertEqual(P.frames_as_loaded(root), {0x10: tuple(a)})

    def test_records_that_are_not_reads_of_the_list_are_passed_by(self) -> None:
        a, b = frame(100), frame(200)
        root = stored(result([(0x99, 1, 0, 1, 0xFFFFFFFF, [b]), (0x99, 0, 0, P.NONE, P.OP_CTL0, []), (0x10, 0, 0, 1, 0, [a]), (0x10, 0, 2, 1, 0, [a]),
                              (0x99, 0, 3, P.NONE, P.OP_CTL0, []), (0x99, 3, 3, 1, 0xFFFFFFFF, [b])]))
        self.assertEqual(P.frames_as_loaded(root), {0x10: tuple(a)})
        # each of the three signs alone is enough: a kind that is not a read of the list, an operation that is not one of the list, no frame
        for other in ((0x98, 1, 0, 1, 0, [b]), (0x98, 0, 0, 1, P.OP_CTL0, [b]), (0x98, 0, 0, P.NONE, 0, [])):
            in_the_third_state = (other[0], other[1], 2, *other[3:])
            root = stored(result([other, (0x10, 0, 0, 1, 1, [a]), in_the_third_state, (0x10, 0, 2, 1, 1, [a])]))
            self.assertEqual(P.frames_as_loaded(root), {0x10: tuple(a)}, other)

    def test_what_is_not_whole_or_not_plain_gives_nothing(self) -> None:
        a = frame(100)
        good = [(0x10, 0, 0, 1, 0, [a]), (0x10, 0, 2, 1, 0, [a])]
        self.assertRaisesRegex(ValueError, "no stored run", P.frames_as_loaded, stored())
        self.assertRaisesRegex(ValueError, "not the whole result", P.frames_as_loaded, stored(result(good, status=0x221)))
        self.assertRaisesRegex(ValueError, "not the whole result", P.frames_as_loaded, stored(result(good)[:-4]))
        self.assertRaisesRegex(ValueError, "read twice in one state", P.frames_as_loaded, stored(result(good + [(0x10, 0, 0, 1, 1, [a])])))
        self.assertRaisesRegex(ValueError, "did not read the same frames", P.frames_as_loaded, stored(result(good[:1])))

    def test_the_frames_s2_2_stored(self) -> None:
        frames = P.frames_as_loaded()
        census = json.loads((ROOT / "census" / "frame_census_17A6.json").read_text())
        self.assertEqual(len(frames), 3864)
        self.assertEqual({len(f) for f in frames.values()}, {101})
        self.assertTrue(all(frames[far][w] == 0 for far in range(0x00401220, 0x00401224) for w in (61, 62)), "the RAM as loaded: all zero")
        self.assertEqual(sum(1 for far in frames if all(far + f in frames for f in range(4))) * 101 * 2, 712656)
        self.assertGreater(len(census["entries"]), len(frames), "the census has the other block types too")


class ThePredictionAsStored(unittest.TestCase):
    D = ROOT / "evidence" / "s2_4_prediction_2026-11-23"

    def test_it_is_what_the_program_says_now(self) -> None:
        now = json.loads(json.dumps(P.predict()))
        self.assertEqual(now, json.loads((self.D / "prediction.json").read_text()))
        self.assertEqual(hashlib.sha256((self.D / "prediction.json").read_bytes()).hexdigest(), "3a03fecf3beaa2e3db94341f3c554dfc33c3addb9ade6fa643e513748cfb4f7e")

    def test_what_it_says(self) -> None:
        """Written here from the note beside it: four hits, one for each loaded word, in words 40 and 41 of four frames
        next to each other, the word at the odd addresses in order. Nothing else in 712,656 places."""
        p = json.loads((self.D / "prediction.json").read_text())
        self.assertEqual((p["label"], p["says"], p["places_looked_at"], p["frames_as_loaded"], len(p["arrangements"]), p["chance_hits_expected"]),
                         ("closed-book", "found: each of the loaded words once, all in one group of four frames and in one arrangement", 712656, 3864, 24, 0.0159))
        self.assertEqual([(h["shift_register"], h["loaded_word"], h["frames"], h["word"], h["bits"], h["arrangement"]) for h in p["hits"]],
                         [(k, f"{WORDS[k]:#010x}", [f"{0x1820 + f:#010x}" for f in range(4)], 40 + k // 2, "31 down to 16" if k % 2 else "15 down to 0",
                           "the odd addresses, in order, as it is") for k in range(4)])
        self.assertEqual([(r["address"], r["frame_above_the_lowest"], r["bit_of_the_half_word"]) for r in p["rule"]], [(a, f, b) for a, (f, b) in enumerate(RULE)])
        design = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
        self.assertEqual([int(design["srl"]["cells"][str(k)]["init"], 16) for k in range(4)], WORDS)

    def test_what_the_note_adds_was_seen_in_the_same_frames(self) -> None:
        """The two things the note says were seen afterwards (README.md): the even addresses hold the opposite of the
        word moved up by one, with a one at address 0; and the reads after which S2.2 saw bit 5 are the two that
        deliver these four frames. Every other word of the four frames reads zero."""
        frames = P.frames_as_loaded()
        for k, (w, half) in enumerate(((40, 0), (40, 16), (41, 0), (41, 16))):
            held = [(frames[0x1820 + f][w] >> (half + b)) & 1 for f, b in RULE]
            self.assertEqual([held[2 * j + 1] for j in range(32)], [(WORDS[k] >> j) & 1 for j in range(32)], k)
            self.assertEqual([held[2 * j] for j in range(32)], [1] + [1 - ((WORDS[k] >> (j - 1)) & 1) for j in range(1, 32)], k)
        self.assertEqual([w for f in range(4) for w in range(101) if frames[0x1820 + f][w] and w not in (40, 41)], [])
        v = json.loads((ROOT / "evidence" / "s2_2_17A6_2026-11-22" / "run03" / "verdict.json").read_text())
        with_it = {(r["far"], r["frames"]) for r in v["records"] if any(int(x, 16) & 0x20 for x in r["int_sts"])}
        self.assertEqual(with_it, {("0x0000181e", 3), ("0x00001821", 3)})
        self.assertEqual(sorted(int(far, 16) + j for far, n in with_it for j in range(n))[-4:], [0x1820, 0x1821, 0x1822, 0x1823])


if __name__ == "__main__":
    unittest.main()

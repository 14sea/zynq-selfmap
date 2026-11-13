"""The stream generator and the guard, before anything else is built on them."""
from __future__ import annotations

import random
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import packets  # noqa: E402

TWIN = ROOT / "build" / "prober" / "twin"
# imported/psmap/s0_derived_sequence.md section 3, written out here by hand
PINNED = [0xFFFFFFFF, 0xAA995566, 0x20000000, 0x20000000, 0x30008001, 0x00000004, 0x20000000,
          0x30002001, 0x00000B99, 0x28006000, 0x480000CA] + [0x20000000] * 32
PINNED_CLEANUP = [0x20000000, 0x30008001, 0x0000000D, 0x20000000, 0x20000000]
LO, HI, MAXR = 0x00000B98, 0x00000B9A, 202


def build() -> None:
    subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)


def gen(far: int) -> tuple[list[int], list[int]]:
    out = subprocess.run([str(TWIN), "gen", f"{far:x}"], check=True, capture_output=True, text=True).stdout.splitlines()
    return [int(w, 16) for w in out[0].split()], [int(w, 16) for w in out[1].split()]


def guard(words: list[int], lo: int = LO, hi: int = HI, maxr: int = MAXR) -> int:
    out = subprocess.run([str(TWIN), "guard", f"{lo:x}", f"{hi:x}", f"{maxr:x}", *[f"{w:x}" for w in words]],
                         check=True, capture_output=True, text=True).stdout
    return int(out, 16)


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build()

    def test_the_stream_for_the_pinned_far_is_the_imported_one_word_for_word(self) -> None:
        stream, cleanup = gen(0xB99)
        self.assertEqual(stream, PINNED)
        self.assertEqual(cleanup, PINNED_CLEANUP)
        self.assertEqual((len(stream), len(cleanup)), (43, 5))

    def test_the_imported_document_carries_those_words(self) -> None:
        text = (ROOT / "imported/psmap/s0_derived_sequence.md").read_text()
        for word in ("FFFFFFFF", "AA995566", "30008001", "00000004", "30002001", "00000B99", "28006000", "480000CA"):
            self.assertIn(word, text)
        self.assertIn("`0x0000000D`", text)

    def test_only_the_frame_address_varies(self) -> None:
        base, cleanup = gen(0xB99)
        rng = random.Random(1)
        for far in [0, 1, 0x00400A20, 0xFFFFFFFF] + [rng.getrandbits(32) for _ in range(40)]:
            stream, clean = gen(far)
            self.assertEqual([i for i in range(43) if stream[i] != base[i]], [] if far == 0xB99 else [8])
            self.assertEqual(stream[8], far)
            self.assertEqual(clean, cleanup)

    def test_both_readers_accept_what_the_generator_makes_inside_the_envelope_and_only_there(self) -> None:
        rng = random.Random(2)
        for far in [LO, 0xB99, HI, LO - 1, HI + 1, 0, 0xFFFFFFFF] + [rng.getrandbits(32) for _ in range(60)]:
            stream, clean = gen(far)
            inside = LO <= far <= HI
            self.assertEqual(guard(stream) == 0, inside, f"{far:#x}")
            self.assertEqual(packets.readonly_problems(stream, LO, HI, MAXR) == [], inside, f"{far:#x}")
            self.assertEqual(guard(clean), 0)
            self.assertEqual(packets.readonly_problems(clean, LO, HI, MAXR), [])


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build()
        cls.stream, cls.cleanup = gen(0xB99)

    def refused_by_both(self, words: list[int], what: str) -> None:
        self.assertNotEqual(guard(words), 0, f"the C guard accepts {what}")
        self.assertTrue(packets.readonly_problems(words, LO, HI, MAXR), f"the Python reader accepts {what}")

    def test_every_forbidden_command_is_refused(self) -> None:
        for value, name in packets.CMD.items():
            if name in ("RCFG", "DESYNC"):
                continue
            s = list(self.stream); s[5] = value
            self.refused_by_both(s, f"CMD = {name}")
            c = list(self.cleanup); c[2] = value
            self.refused_by_both(c, f"CMD = {name} in the cleanup")

    def test_writes_to_any_other_register_are_refused(self) -> None:
        for reg in range(32):
            if reg in (1, 4):
                continue
            s = list(self.stream); s[7] = 0x30000001 | (reg << 13)
            self.refused_by_both(s, f"a write to register {reg}")
        s = list(self.stream); s[9:11] = [0x30004000, 0x500000CA]            # FDRI header, type-2 write
        self.refused_by_both(s, "a type-2 FDRI write")
        s = list(self.stream); s[7] = 0x30004065                             # FDRI, 101 words: swallows what follows
        self.refused_by_both(s, "a type-1 FDRI write")

    def test_reads_of_anything_but_fdro_and_over_long_reads_are_refused(self) -> None:
        for reg in range(32):
            if reg == 3:
                continue
            s = list(self.stream); s[9] = 0x28000000 | (reg << 13)
            self.refused_by_both(s, f"a read of register {reg}")
        s = list(self.stream); s[10] = 0x48000000 | 203
        self.refused_by_both(s, "a 203-word read")
        s = list(self.stream); s[10] = 0x48000000
        self.refused_by_both(s, "a zero-word type-2 read")
        s = list(self.stream); s[9] = 0x28006001
        self.refused_by_both(s, "a type-1 FDRO read with a count")

    def test_order_and_shape(self) -> None:
        s = list(self.stream); s[4:7] = [0x20000000] * 3
        self.refused_by_both(s, "a read without RCFG")
        s = list(self.stream); s[7:9] = [0x20000000] * 2
        self.refused_by_both(s, "a read without a FAR")
        self.refused_by_both(self.stream[:10], "a stream ending on the read header")
        self.refused_by_both(self.stream[:8], "a FAR write with no value")
        self.refused_by_both([0xFFFFFFFF, 0xFFFFFFFF], "dummies without a sync")
        self.refused_by_both([], "an empty stream")
        self.refused_by_both([0x12345678], "an unknown word")

    def test_the_c_guard_never_accepts_what_the_python_reader_refuses(self) -> None:
        """Random single- and double-word damage to valid streams: the guard may be stricter, never laxer."""
        rng = random.Random(3)
        interesting = [0x30008001, 0x30002001, 0x28006000, 0x480000CA, 0x30004000, 0x500000CA, 0x30000001, 0x30018001,
                       0x20000000, 0xAA995566, 0xFFFFFFFF, 0, 1, 2, 4, 5, 7, 0xA, 0xB, 0xC, 0xD, 0xF, 0xB98, 0xB99, 0xB9B]
        accepted = 0
        for _ in range(1500):
            words = list(self.stream if rng.random() < 0.8 else self.cleanup)
            for _ in range(rng.choice((1, 1, 2))):
                at = rng.randrange(min(len(words), 12))
                words[at] = rng.choice(interesting) if rng.random() < 0.7 else rng.getrandbits(32)
            if guard(words) == 0:
                accepted += 1
                self.assertEqual(packets.readonly_problems(words, LO, HI, MAXR), [], " ".join(f"{w:08x}" for w in words))
        self.assertGreater(accepted, 20, "the damage never produced an acceptable stream: the test is not exercising the guard")


if __name__ == "__main__":
    unittest.main()

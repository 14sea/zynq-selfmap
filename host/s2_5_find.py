#!/usr/bin/env python3
"""S2.5, part 1: whose memory a place is — the search for the words the memories are loaded with (docs/s2_plan.md,
sections 45 and 46).

Every memory of the design s2b is loaded with a word of its own, 64 bits, no two alike. A run of part 1 reads its
share of block type 0 first as loaded, before anything is written. Here those frames are searched for every one of
the 440 words: at every group of four frames next to each other, every word of the frame, both halves — the 64 bits
there, taken in the order of the six moves of S2.3 (which bit of the four frames by sixteen bits is which address of
a memory), are held against every word, as it is and inverted. A hit says: here lies a memory laid out by the six
moves, and it is the one the design loaded with this word — memory k of site s by the design's own record.

The search knows no prediction and no site's name: it is given frames, the rule and the words. With 64 bits a word, a
hit by chance is not to be expected in any number of places a device has (`chance`).

Nothing here reads a database, and nothing is graded."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

DATA, FRAME, REC = 76, 101, 480                        # where a record's data begin; words of a frame; of a record (the judges' numbers)
GROUP, HALF, DEPTH = 4, 16, 64
OP_CTL0, NONE = 0x100, 0xF


def frames_in_state(words: list[int], state: int = 0) -> dict[int, tuple[int, ...]]:
    """Every frame a run read in one of its states (the first: as loaded), from the raw words of a result the judge
    has passed."""
    hdr, n = words[7], words[3]
    out: dict[int, tuple[int, ...]] = {}
    for i in range(n):
        r = words[hdr + i * REC: hdr + (i + 1) * REC]
        far, kind, st, m, op = r[0], r[1], r[12], r[14], r[15]
        if kind != 0 or st != state or op >= OP_CTL0 or m == NONE:   # the reference frame, CTL0: not reads of the list
            continue
        for j in range(m):
            if far + j in out:
                raise ValueError(f"frame {far + j:#010x} is read twice in one state")
            out[far + j] = tuple(r[DATA + FRAME * (j + 1): DATA + FRAME * (j + 2)])
    return out


def check_rule(the_rule: list[tuple[int, int]]) -> None:
    if sorted(the_rule) != [(f, b) for f in range(GROUP) for b in range(HALF)]:
        raise ValueError("the rule does not give each of 64 addresses a place of its own in four frames by sixteen bits")


def search(frames: dict[int, tuple[int, ...]], the_rule: list[tuple[int, int]], loaded: list[list[int]]) -> tuple[int, list[dict]]:
    """(how many places were looked at, the hits). A place: four frames next to each other, a word, a half. `loaded`:
    for each site its words, as the design's record has them."""
    check_rule(the_rule)
    wanted: dict[int, list[tuple[int, int, bool]]] = {}
    mask = (1 << DEPTH) - 1
    for s, its in enumerate(loaded):
        for k, word in enumerate(its):
            wanted.setdefault(word, []).append((s, k, False))
            wanted.setdefault(word ^ mask, []).append((s, k, True))
    spread = [[0] * (1 << HALF) for _ in range(GROUP)]   # frame of the four -> its sixteen bits -> the addresses they are, as a mask
    for f in range(GROUP):
        bits = [(b, a) for a, (ff, b) in enumerate(the_rule) if ff == f]
        for v in range(1 << HALF):
            spread[f][v] = sum(1 << a for b, a in bits if v >> b & 1)
    looked, hits = 0, []
    for far in sorted(frames):
        if not all(far + f in frames for f in range(GROUP)):
            continue
        four = [frames[far + f] for f in range(GROUP)]
        for w in range(FRAME):
            for half in (0, HALF):
                looked += 1
                held = 0
                for f in range(GROUP):
                    held |= spread[f][four[f][w] >> half & 0xFFFF]
                for s, k, inverted in wanted.get(held, ()):
                    hits.append({"site": s, "memory": k, "loaded_word": f"{loaded[s][k]:#018x}", "frames": [f"{far + f:#010x}" for f in range(GROUP)],
                                 "word": w, "bits": f"{half + HALF - 1} down to {half}", "inverted": inverted})
    return looked, hits


def places_of(hit: dict, the_rule: list[tuple[int, int]]) -> dict[tuple[int, int, int], int]:
    """The 64 places of a memory that was found: (frame address, word, bit) -> the address of the memory."""
    low, half = int(hit["frames"][0], 16), int(hit["bits"].split()[-1])
    return {(low + f, hit["word"], half + b): a for a, (f, b) in enumerate(the_rule)}


def chance(looked: int, n_words: int) -> float:
    """How many hits chance would give in that many places: each holds one of 2^64 contents, and 2 n of them hit."""
    return looked * 2 * n_words / 2 ** DEPTH

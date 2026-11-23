#!/usr/bin/env python3
"""S2.4, part 0: a prediction made on the host alone — docs/s2_plan.md, section 37.

    s2_4_predict.py            print the prediction (JSON); reads stored results only, touches no serial port

The design's four shift registers were loaded with four known words and have never been shifted. S2.3 found that a
memory of the design's RAM is a half word in each of four frames next to each other, its 64 places ordered by six
moves (the rule, taken here from the stored description, evidence/s2_3_17A6_2026-11-23/ram_map.json). If a shift
register is laid out the same way, its loaded word is already in the frames S2.2 stored when it read all of block
type 0 with nothing written. This program looks for it.

For every four frames next to each other, every word of a frame and both halves of the word, it takes the 64 bits
the rule would make a memory of, and asks whether one of the four loaded words is in them in one of 24 arrangements,
fixed in section 37 before the search was made:

    where     the 32 bits at the even addresses, at the odd ones, at both; in the lower 32 addresses, in the upper, in both
    order     bit j of the word at the j-th of those places, or at the (31 - j)-th
    polarity  as it is, or inverted

"Address" is the address of the RAM as S2.3 numbered it; nothing says a shift register's stages are numbered so. The
family is a guess and a small one. What comes out — found, found and not simply, not found — decides nothing: part 1
reads all of block type 0 whatever this says, and the prediction is then held against what the board showed.

No database is read and nothing is graded. Nothing here is general knowledge of the device family: the rule is
S2.3's, the frames are S2.2's, the words are the design's."""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S2_2 = ROOT / "evidence" / "s2_2_17A6_2026-11-22"      # the eight runs that read all of block type 0, the RAM all zero / all one / all zero
RAM_MAP = ROOT / "evidence" / "s2_3_17A6_2026-11-23" / "ram_map.json"
DESIGN = ROOT / "pl" / "s2a" / "design.json"
FRAME, REC, DATA = 101, 480, 76                        # words of a frame; of a record; where a record's data begin (the judges' numbers)
OP_CTL0, NONE = 0x100, 0xF                             # a record that is a read of CTL0; one that reads no frame
GROUP, HALF, DEPTH, WORD = 4, 16, 64, 32               # frames a memory lies in; bits of a half word; places of a memory; bits of a loaded word
WHERE = {"the even addresses": lambda j: [2 * j], "the odd addresses": lambda j: [2 * j + 1], "the even and the odd addresses": lambda j: [2 * j, 2 * j + 1],
         "the lower 32 addresses": lambda j: [j], "the upper 32 addresses": lambda j: [32 + j], "the lower and the upper 32 addresses": lambda j: [j, 32 + j]}
ORDER = {"in order": lambda j: j, "reversed": lambda j: WORD - 1 - j}
POLARITY = {"as it is": 0, "inverted": 1}


def rule(ram_map: dict) -> list[tuple[int, int]]:
    """What S2.3 found, as a rule: for each address of a memory, (how many frames above the lowest of its four the
    place lies, which bit of its half word). Taken from the stored description; every memory there must obey the one
    rule, lie in one word and one half of it, and fill four frames by sixteen bits exactly."""
    by_memory: dict[int, dict[int, tuple[int, int, int]]] = {}
    for e in ram_map["entries"]:
        far, word, bit = (int(x, 0) for x in e["address"].split("/"))
        by_memory.setdefault(e["memory"], {})[e["ram_address"]] = (far, word, bit)
    rules = []
    for memory, places in sorted(by_memory.items()):
        if sorted(places) != list(range(DEPTH)) or len({w for _, w, _ in places.values()}) != 1:
            raise ValueError(f"memory {memory} of the description is not 64 places in one word of its frames")
        low, half = min(f for f, _, _ in places.values()), min(b for _, _, b in places.values()) // HALF * HALF
        rules.append([(places[a][0] - low, places[a][2] - half) for a in range(DEPTH)])
    if not rules or any(r != rules[0] for r in rules):
        raise ValueError("the memories of the description do not obey one rule")
    if sorted(rules[0]) != [(f, b) for f in range(GROUP) for b in range(HALF)]:
        raise ValueError("the rule of the description does not fill four frames by sixteen bits")
    return rules[0]


def frames_as_loaded(root: Path = S2_2) -> dict[int, tuple[int, ...]]:
    """Every frame the runs stored under `root` read, as it read in the first state — from the raw words of their
    results. In S2.2 the first and the third state are the RAM all zero, which is how it is loaded: a frame is taken
    only if it read the same in both.

    Only from a chain that stands by its own files (review of 633875e: a copy with one run of the eight, or with a
    result that was not the one the board gave, was read as if it were the whole): chain.json says the chain is
    complete; candidates.json names its runs and the sha256 of each result; the runs stored are those and no other;
    each result has that sha256 and the crc32 its own record says the board gave; and as many frames are read in the
    first state as the chain's closing says addresses were read."""
    out: dict[int, tuple[int, ...]] = {}
    again: dict[int, tuple[int, ...]] = {}
    try:
        chain = json.loads((root / "chain.json").read_text())
        named = {r["dir"]: r["result_sha256"] for r in json.loads((root / "candidates.json").read_text())["runs"]}
        read = chain["closing"]["addresses_read"] if chain.get("state") == "complete" else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"no chain that says what its runs are and what they read under {root}: {type(e).__name__}: {e}")
    if read is None:
        raise ValueError(f"the chain under {root} is not a complete chain")
    runs = sorted(d for d in root.glob("run[0-9][0-9]") if (d / "result.bin").is_file())
    if sorted(d.name for d in runs) != sorted(named) or not runs:
        raise ValueError(f"the runs stored under {root} are not the runs its chain names: {[d.name for d in runs]} for {sorted(named)}")
    for d in runs:
        raw = (d / "result.bin").read_bytes()
        try:
            board = json.loads((d / "run.json").read_text()).get("board_crc32")
        except (OSError, ValueError, AttributeError):
            board = None
        if hashlib.sha256(raw).hexdigest() != named[d.name] or f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" != board:
            raise ValueError(f"{d.name}: the stored result is not the one the chain names, or not the one whose checksum the board gave")
        words = struct.unpack("<%dI" % (len(raw) // 4), raw)
        status, n, rec_words, hdr = words[2], words[3], words[6], words[7]
        if status != 1 or rec_words != REC or len(words) != hdr + n * REC:
            raise ValueError(f"{d.name}: not the whole result of a run that went through")
        for i in range(n):
            r = words[hdr + i * REC: hdr + (i + 1) * REC]
            far, kind, state, m, op = r[0], r[1], r[12], r[14], r[15]
            if kind != 0 or op >= OP_CTL0 or m == NONE:         # the reference frame, CTL0: not reads of the list
                continue
            for j in range(m):
                frame = tuple(r[DATA + FRAME * (j + 1): DATA + FRAME * (j + 2)])
                where = out if state == 0 else again if state == 2 else None
                if where is not None:
                    if far + j in where:
                        raise ValueError(f"{d.name}: frame {far + j:#010x} is read twice in one state")
                    where[far + j] = frame
    if sorted(out) != sorted(again):
        raise ValueError("the first and the third state did not read the same frames")
    if len(out) != read:
        raise ValueError(f"{len(out)} frames were read in the first state; the chain's closing says {read} addresses were read")
    return {far: frame for far, frame in out.items() if again[far] == frame}


def arrangements() -> list[tuple[str, list[tuple[int, int, int]]]]:
    """The 24 arrangements: (its name, for each place it uses (address, which bit of the word, inverted?))."""
    out = []
    for where, places in WHERE.items():
        for order, at in ORDER.items():
            for polarity, inverted in POLARITY.items():
                out.append((f"{where}, {order}, {polarity}", [(a, at(j), inverted) for j in range(WORD) for a in places(j)]))
    return out


def pattern(word: int, arrangement: list[tuple[int, int, int]]) -> tuple[int, int]:
    """(which of the 64 addresses the arrangement speaks of, what they must hold for the word), as two masks."""
    mask = value = 0
    for a, j, inverted in arrangement:
        mask |= 1 << a
        value |= (((word >> j) & 1) ^ inverted) << a
    return mask, value


def search(frames: dict[int, tuple[int, ...]], the_rule: list[tuple[int, int]], words: list[int]) -> tuple[int, list[dict]]:
    """(how many places were looked at, the hits). A place: four frames next to each other, a word, a half."""
    spread = [[0] * (1 << HALF) for _ in range(GROUP)]   # frame of the four -> its sixteen bits -> the addresses they are, as a mask
    for f in range(GROUP):
        bits = [(b, a) for a, (ff, b) in enumerate(the_rule) if ff == f]
        for v in range(1 << HALF):
            spread[f][v] = sum(1 << a for b, a in bits if v >> b & 1)
    wanted: dict[int, dict[int, list[tuple[int, str]]]] = {}
    for name, arrangement in arrangements():
        for k, word in enumerate(words):
            mask, value = pattern(word, arrangement)
            wanted.setdefault(mask, {}).setdefault(value, []).append((k, name))
    places, hits = 0, []
    for far in sorted(frames):
        if not all(far + f in frames for f in range(GROUP)):
            continue
        four = [frames[far + f] for f in range(GROUP)]
        for w in range(FRAME):
            for half in (0, HALF):
                places += 1
                held = 0
                for f in range(GROUP):
                    held |= spread[f][four[f][w] >> half & 0xFFFF]
                for mask, values in wanted.items():
                    for k, name in values.get(held & mask, ()):
                        hits.append({"shift_register": k, "loaded_word": f"{words[k]:#010x}", "frames": [f"{far + f:#010x}" for f in range(GROUP)],
                                     "word": w, "bits": f"{half + HALF - 1} down to {half}", "arrangement": name})
    return places, hits


def places(prediction: dict) -> dict[tuple[int, int, int], tuple[int, int, bool]]:
    """The prediction as places: (frame address, word, bit) -> (shift register, which bit of its loaded word — which
    is the output of that number, as the design's record has it — inverted?). From the stored prediction alone."""
    the_rule = [(r["frame_above_the_lowest"], r["bit_of_the_half_word"]) for r in prediction["rule"]]
    named = dict(arrangements())
    out: dict[tuple[int, int, int], tuple[int, int, bool]] = {}
    for h in prediction["hits"]:
        low, half = int(h["frames"][0], 16), int(h["bits"].split()[-1])
        for a, j, inverted in named[h["arrangement"]]:
            f, b = the_rule[a]
            out[(low + f, h["word"], half + b)] = (h["shift_register"], j, bool(inverted))
    return out


def says(hits: list[dict], n_words: int) -> str:
    if not hits:
        return "not found"
    by = [[h for h in hits if h["shift_register"] == k] for k in range(n_words)]
    if all(len(b) == 1 for b in by) and len({(tuple(h["frames"]), h["arrangement"]) for h in hits}) == 1:
        return "found: each of the loaded words once, all in one group of four frames and in one arrangement"
    return "found, and not that simply: see the hits"


def predict(root: Path = S2_2, ram_map: Path = RAM_MAP, design: Path = DESIGN) -> dict:
    cells = json.loads(design.read_text())["srl"]["cells"]
    words = [int(cells[str(k)]["init"], 16) for k in range(len(cells))]
    the_rule = rule(json.loads(ram_map.read_text()))
    frames = frames_as_loaded(root)
    places, hits = search(frames, the_rule, words)
    names = [name for name, _ in arrangements()]
    return {"schema": "s2_4_prediction", "schema_version": 1, "label": "closed-book",
            "what": "where the loaded words of the probe design's four shift registers would be in the frames S2.2 stored, if a shift register "
                    "were laid out as S2.3 found a memory of the RAM to be (docs/s2_plan.md, section 37, part 0). A prediction made before "
                    "the board was asked; it decides nothing.",
            "from": {"frames": str(root.relative_to(ROOT)), "rule": str(ram_map.relative_to(ROOT)), "words": str(design.relative_to(ROOT))},
            "loaded_words": [f"{w:#010x}" for w in words],
            "rule": [{"address": a, "frame_above_the_lowest": f, "bit_of_the_half_word": b} for a, (f, b) in enumerate(the_rule)],
            "arrangements": names, "frames_as_loaded": len(frames), "places_looked_at": places,
            "chance_hits_expected": round(places * len(names) * len(words) / 2 ** WORD, 4),
            "hits": hits, "says": says(hits, len(words))}


def main(argv: list[str]) -> int:
    print(json.dumps(predict(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

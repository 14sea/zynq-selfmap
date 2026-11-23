#!/usr/bin/env python3
"""S2.5, part 0: where the memories of the design s2b will be, said before the board is asked — docs/s2_plan.md,
sections 45 and 46.

    s2_5_predict.py            print the prediction (JSON); reads stored results and records only, touches no serial port

Two sites are known: the RAM of s2a at SLICE_X16Y30 (S2.3) and its shift registers at SLICE_X34Y70 (S2.4). From their
two descriptions, the census, and the builds' own records of which LUT position each memory was put on, three rules
are read — and each is checked here against both known sites before it is used, so that a rule that does not hold
of what it was read from predicts nothing:

    the column    block type 0 has, in each half, a number of columns of 36 frames. Counted among those alone, the
                  column of a site lies (site column) / 2 further on for every two numbers of site columns: the two
                  known sites fix the line. A memory is in the last four frames of its column.
    the half      rows 0 to 49 are the half the RAM was found in, rows 50 to 99 the one the shift registers were
    and the word  found in; a row has two words of the frame, and between the rows the two sites lie in (20 and 30
                  of their halves) there is one word more than twice the rows. WHERE that one word lies two points
                  cannot say: this program carries every form — the word skipped after row 20, 21, ... or 29 — and
                  names the one in the middle (after row 24) first.
    the position  the LUT position the build put a memory on gives the word of the two and the half of it: A the
                  lower word's lower half, B its upper half, C the upper word's lower half, D its upper half.

Within its half word a memory is laid out by the six moves of S2.3 (s2_4_predict.rule).

What comes out, for each of the 440 memories of s2b: the four frames, the half word, and by the six moves the place of
each of its 64 cells — under the form named first, and for the rows where the forms differ, under each. It decides
nothing: part 1 reads all of block type 0 and looks for every memory's loaded word everywhere, and what the board
shows is then held against this.

No database is read and nothing is graded. Nothing here is general knowledge of the device family: the rules are
read from this project's own results, and the sentence above says how much of each is a guess."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_4_predict  # noqa: E402

CENSUS = ROOT / "census" / "frame_census_17A6.json"
RAM_MAP = ROOT / "evidence" / "s2_3_17A6_2026-11-23" / "ram_map.json"          # the RAM of s2a: SLICE_X16Y30
SRL_MAP = ROOT / "evidence" / "s2_4b_17A6_2026-11-23" / "srl_map.json"         # its shift registers: SLICE_X34Y70
S2A, S2B = ROOT / "pl" / "s2a", ROOT / "pl" / "s2b"
ROWS_A_HALF, COLUMN_FRAMES, GROUP = 50, 36, 4
POSITIONS = {"A6LUT": (0, 0), "B6LUT": (0, 16), "C6LUT": (1, 0), "D6LUT": (1, 16)}   # LUT position -> (which of the row's two words, the half's lowest bit)
FORMS = list(range(20, 30))                              # the one word more lies after this row of the half
NAMED = 24                                               # the form named first: after row 24, the middle of fifty


def site_xy(name: str) -> tuple[int, int]:
    m = re.fullmatch(r"SLICE_X(\d+)Y(\d+)", name)
    if not m:
        raise ValueError(f"{name!r} is no name of a site")
    return int(m.group(1)), int(m.group(2))


def columns_of_36(census: dict) -> dict[str, list[int]]:
    """For each half, the first frame address of every column of block type 0 that has 36 frames, in the census's order."""
    by: dict[tuple[str, int], list[int]] = {}
    for e in census["entries"]:
        if e["block_type"] == 0:
            by.setdefault((e["half"], e["column"]), []).append(int(e["far"], 16))
    out: dict[str, list[int]] = {}
    for (half, _), fars in by.items():
        if len(fars) == COLUMN_FRAMES and fars == list(range(fars[0], fars[0] + COLUMN_FRAMES)):
            out.setdefault(half, []).append(fars[0])
    return {half: sorted(firsts) for half, firsts in out.items()}


def known_sites() -> list[dict]:
    """The two sites this project has measured, each as the rules need it: its name, the frames its memories lie in,
    and for each memory its LUT position by the build, its word and its half."""
    ram = json.loads(RAM_MAP.read_text())["entries"]
    srl = json.loads(SRL_MAP.read_text())["entries"]
    d = json.loads((S2A / "design.json").read_text())
    built = json.loads((S2A / "build.json").read_text())["memory_primitives"]
    out = []
    for name, entries, key, cells in ((d["ram"]["site"], ram, "memory", d["ram"]["cells"]), (d["srl"]["site"], srl, "register", d["srl"]["cells"])):
        frames = sorted({int(e["address"].split("/")[0], 16) for e in entries})
        memories = []
        for k in sorted(cells, key=int):
            its = [e for e in entries if e[key] == int(k)]
            words = {int(e["address"].split("/")[1]) for e in its}
            bits = [int(e["address"].split("/")[2]) for e in its]
            if len(words) != 1 or max(bits) - min(bits) != 15 or min(bits) % 16:
                raise ValueError(f"{name}, memory {k}: not a half word of one word")
            memories.append({"position": built[cells[k]["cell"]]["bel"], "word": words.pop(), "half": min(bits)})
        out.append({"name": name, "frames": frames, "memories": memories})
    return out


def rules(census: dict, known: list[dict]) -> dict:
    """The three rules, read from the two known sites and held against both. Raises ValueError where the sites do not
    make a rule of the kind section 45 describes."""
    cols = columns_of_36(census)
    halves, at = {}, {}
    for s in known:
        x, y = site_xy(s["name"])
        frames = s["frames"]
        if frames != list(range(frames[0], frames[0] + GROUP)):
            raise ValueError(f"{s['name']}: its memories do not lie in four frames next to each other")
        half = next((h for h, firsts in cols.items() if frames[0] - (COLUMN_FRAMES - GROUP) in firsts), None)
        if half is None:
            raise ValueError(f"{s['name']}: its four frames are not the last four of a column of 36 frames")
        words = sorted({m["word"] for m in s["memories"]})
        if len(words) != 2 or words[1] != words[0] + 1:
            raise ValueError(f"{s['name']}: its memories are not in two words next to each other")
        for m in s["memories"]:
            if POSITIONS.get(m["position"]) != (m["word"] - words[0], m["half"]):
                raise ValueError(f"{s['name']}: the memory on {m['position']} is in word {m['word']}, half {m['half']}: not as the rule of the positions has it")
        halves[y // ROWS_A_HALF] = half
        at[s["name"]] = {"x": x, "row": y % ROWS_A_HALF, "half": half, "place": cols[half].index(frames[0] - (COLUMN_FRAMES - GROUP)), "word": words[0]}
    (a, b) = sorted(at.values(), key=lambda v: v["x"])
    if len(halves) != 2 or len(set(halves.values())) != 2:
        raise ValueError("the two known sites do not lie in two halves, one for rows 0 to 49 and one for rows 50 to 99")
    if (b["place"] - a["place"]) * 2 != b["x"] - a["x"]:
        raise ValueError("the two known sites do not lie two numbers of site columns to a column of frames")
    first = a["place"] - a["x"] // 2                    # where site column 0 would lie
    (lo, hi) = sorted(at.values(), key=lambda v: v["row"])
    if (lo["word"], hi["word"]) != (2 * lo["row"], 2 * hi["row"] + 1) or not lo["row"] <= FORMS[0] <= FORMS[-1] < hi["row"]:
        raise ValueError("the two known sites do not have two words a row and one word more between them")
    return {"columns_of_36_frames_a_half": {h: len(v) for h, v in sorted(cols.items())}, "the_column": {"of_site_column_0": first, "site_columns_a_column": 2},
            "the_half": {"rows 0 to 49": halves[0], "rows 50 to 99": halves[1]}, "the_word": {"words_a_row": 2, "one_word_more_after_row": FORMS, "named_first": NAMED},
            "the_position": {k: {"word_of_the_row": w, "half": h} for k, (w, h) in POSITIONS.items()}, "read_from": at}


def word_of(row: int, form: int) -> int:
    """The lower of the two words of a row of its half, if the one word more lies after row `form`."""
    return 2 * row + (1 if row > form else 0)


def predict(design: Path = S2B / "design.json", build: Path = S2B / "build.json", census: Path = CENSUS) -> dict:
    c = json.loads(census.read_text())
    known = known_sites()
    r = rules(c, known)
    cols = columns_of_36(c)
    moves = s2_4_predict.rule(json.loads(RAM_MAP.read_text()))
    d = json.loads(design.read_text())
    built = json.loads(build.read_text())["memory_primitives"]
    sites = []
    for s in d["ram"]["sites"]:
        x, y = site_xy(s["name"])
        half = r["the_half"]["rows 0 to 49" if y < ROWS_A_HALF else "rows 50 to 99"]
        place = r["the_column"]["of_site_column_0"] + x // 2
        if x % 2 or not 0 <= place < len(cols[half]):
            raise ValueError(f"{s['name']}: the rule of the column gives it no column of frames")
        first = cols[half][place] + COLUMN_FRAMES - GROUP
        row = y % ROWS_A_HALF
        forms = sorted({word_of(row, f) for f in FORMS})
        memories = []
        for k, cell in enumerate(s["cells"]):
            w, h = POSITIONS[built[cell]["bel"]]
            memories.append({"memory": k, "position": built[cell]["bel"], "loaded_word": s["init"][k], "word": word_of(row, NAMED) + w,
                             "bits": f"{h + 15} down to {h}", "word_under_the_other_forms": sorted({f + w for f in forms} - {word_of(row, NAMED) + w})})
        sites.append({"site": s["site"], "name": s["name"], "half": half, "row_of_its_half": row, "column_of_36_frames": place,
                      "frames": [f"{first + f:#010x}" for f in range(GROUP)], "memories": memories})
    return {"schema": "s2_5_prediction", "schema_version": 1, "label": "closed-book",
            "what": "where the memories of the probe design s2b would lie in configuration memory, if the three rules read from the two sites "
                    "measured so far hold at other sites (docs/s2_plan.md, section 45, part 0). A prediction made before the board was asked; "
                    "it decides nothing.",
            "from": {"the_ram_of_s2a": str(RAM_MAP.relative_to(ROOT)), "its_shift_registers": str(SRL_MAP.relative_to(ROOT)), "census": str(census.relative_to(ROOT)),
                     "design": str(design.relative_to(ROOT)), "build": str(build.relative_to(ROOT))},
            "rules": r, "the_six_moves": [{"address": a, "frame_above_the_lowest": f, "bit_of_the_half_word": b} for a, (f, b) in enumerate(moves)],
            "sites": sites, "memories": sum(len(s["memories"]) for s in sites),
            "sites_whose_word_depends_on_the_form": [s["name"] for s in sites if s["memories"][0]["word_under_the_other_forms"]]}


def memory_places(prediction: dict, form: int | None = None) -> dict[tuple[int, int], dict[tuple[int, int, int], int]]:
    """The prediction a memory at a time: (site, memory) -> its 64 places, each (frame address, word, bit) with the
    address of the memory it is said to be — under one form of the word rule (the one named first, if none is given).
    From the stored prediction alone."""
    form = prediction["rules"]["the_word"]["named_first"] if form is None else form
    moves = [(m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in prediction["the_six_moves"]]
    out: dict[tuple[int, int], dict[tuple[int, int, int], int]] = {}
    for s in prediction["sites"]:
        low = int(s["frames"][0], 16)
        for m in s["memories"]:
            w, h = POSITIONS[m["position"]]
            word = word_of(s["row_of_its_half"], form) + w
            out[(s["site"], m["memory"])] = {(low + f, word, h + b): a for a, (f, b) in enumerate(moves)}
    return out


def places(prediction: dict, form: int | None = None) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """The prediction as places: (frame address, word, bit) -> (site, memory, address of the memory). Where a
    prediction names one place for two memories this has the later; who needs each memory's own asks memory_places."""
    return {place: (s, k, a) for (s, k), its in memory_places(prediction, form).items() for place, a in its.items()}


def main(argv: list[str]) -> int:
    print(json.dumps(predict(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

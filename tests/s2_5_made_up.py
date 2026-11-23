"""What the tests of S2.5 share: the made-up device, the design s2b on the twin and on the pretend board.

The made-up device is the one of the stage-8 tests (test_prober_s2_2): 55 frames of block type 0 in six columns. The
design's 440 memories are put where a test says. By default as the six moves of S2.3 have a memory — a half word in
four frames next to each other — with the four of a site in two words next to each other, the way the build's record
of positions has them (memory 0 the upper word's upper half, 1 the lower word's lower half, 2 its upper half, 3 the
upper word's lower half), fifty sites to a group of four frames, in three groups of the column of 30 frames. Nothing
here says the device is so; the tests give the model other answers too."""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_5_judge  # noqa: E402
import s2_5_states as st  # noqa: E402
import test_prober_s2_2 as T8  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402
import test_s2_2_host as H8  # noqa: E402
import test_s2_3_host as H9  # noqa: E402

DESIGN = json.loads((ROOT / "pl" / "s2b" / "design.json").read_text())
BUILD = json.loads((ROOT / "pl" / "s2b" / "build.json").read_text())
ID = int(DESIGN["id"], 16)
LOADED = st.loaded(DESIGN)
WORDS = [w for site in LOADED for w in site]
RULE = [(2 + (a & 1) - 2 * (a >> 3 & 1), 15 - ((a >> 1 & 1) + 2 * (a >> 2 & 1) + 4 * (a >> 4 & 1) + 8 * (a >> 5 & 1))) for a in range(64)]
GROUPS = (0xB84, 0xB88, 0xB8C)                            # the lowest frame of each group of four the memories show in
POSITION = ((1, 16), (0, 0), (0, 16), (1, 0))             # memory k: (which of the site's two words, the half's lowest bit)
CTL0 = "0x00000501"
SITES = len(LOADED)


def at(s: int, k: int, a: int) -> tuple[int, int, int]:
    """Where cell (memory k, address a) of site s shows in the made-up device."""
    f, b = RULE[a]
    return GROUPS[s // 50] + f, 2 * (s % 50) + POSITION[k][0], POSITION[k][1] + b


def b_map(sites=range(SITES), moved: dict | None = None, inverted=()) -> list[tuple[int, int, int, int, int, int, int]]:
    """Where cells show: (site, address, memory, frame address, word, bit, inverted). `moved`: {(site, memory, address):
    place} for cells put elsewhere; `inverted`: the (site, memory, address) shown inverted."""
    moved = moved or {}
    return [(s, a, k, *moved.get((s, k, a), at(s, k, a)), int((s, k, a) in inverted)) for s in sites for k in range(4) for a in range(64)]


def swap(s: int, k: int, alike: bool = False) -> dict:
    """Two cells of memory k of site s in each other's places — the first two addresses whose loaded bits differ (by
    the six moves the memory then holds another word than it was loaded with) or, if asked, are alike (the word is
    still found, and the places are not the cells the moves say)."""
    w = LOADED[s][k]
    a, b = next((a, b) for a in range(64) for b in range(a + 1, 64) if ((w >> a ^ w >> b) & 1 == 0) == alike)
    return {(s, k, a): at(s, k, b), (s, k, b): at(s, k, a)}


def where(cells) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    return {(far, word, bit): (s, k, a) for s, a, k, far, word, bit, _ in cells}


def known_for(reads_a_run: int | None = 10, **more) -> dict:
    """What is known of the made-up device. With ten reads a run it has three shares: 7, 10 and 3 reads."""
    known = dict(DESIGN, census=T8.census(), ctl0_in_s2_2=CTL0, rule=RULE, **more)
    return known if reads_a_run is None else dict(known, reads_a_run=reads_a_run)


KNOWN = known_for()
SHARES = st.shares(KNOWN["census"], KNOWN)


def twin(kind: str = "find", share: int | None = 1, cells=None, known: dict | None = None, words=None, **over) -> tuple[dict, T.Run]:
    """One run of the step on the twin: the plan made as the host makes it, and what the prober did with it."""
    known = KNOWN if known is None else known
    p = st.plan(kind, share, known, known["census"], known.get("candidates"))
    over.setdefault("w26", ID)
    return p, T.Run(states=p["states"], reads=p["reads"], entries=p["entries"], w19=p["may_write"], cells=[],
                    design_b=(WORDS if words is None else words, b_map() if cells is None else cells), **over)


def planned(p: dict, r: T.Run) -> list[int]:
    return s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN)


def judged(p: dict, r: T.Run, known: dict | None = None, words=None) -> dict:
    return s2_5_judge.judge(r.words if words is None else words, KNOWN if known is None else known, planned(p, r))


def alike(test, got, want, what: str = "") -> None:
    """Two large things held to be the same, without the line-by-line difference unittest makes of them when they
    are not — which, of tens of thousands of lines that all differ, takes longer than a suite may (2026-11-24: a
    mutant that moved every place of every table was not killed but timed out)."""
    if got == want:
        return
    if isinstance(got, dict) and isinstance(want, dict):
        keys = [k for k in want if k not in got or got[k] != want[k]] + [k for k in got if k not in want]
        test.fail(f"{what}: not the same — {len(keys)} key(s) differ or are on one side only, the first {keys[0]!r}: "
                  f"{str(got.get(keys[0], 'not there'))[:120]} for {str(want.get(keys[0], 'not there'))[:120]}")
    test.fail(f"{what}: not the same ({type(got).__name__} of {len(got)} for {type(want).__name__} of {len(want)})")


_memo: dict = {}


def once(name, make):
    """What several tests look at, made when the first of them asks and kept — in a test, not in setUpClass."""
    if name not in _memo:
        try:
            _memo[name] = (make(), None)
        except Exception as e:                           # kept as well: the tests after it fail the same way, at once
            _memo[name] = (None, e)
    value, error = _memo[name]
    if error is not None:
        raise error
    return value


def run5(stage: str, share: int | None, known: dict | None = None, out: Path | None = None, cells=None, words=None, fault: str = "", env: dict | None = None, **quirks):
    """A run of a set of the step through the run script, on the pretend board, over the made-up device."""
    H9.prepared()
    known = KNOWN if known is None else known
    exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), share, known)
    reads = [(int(w, 16) & 0x0FFFFFFF, int(w, 16) >> 28) for w in exp["list"]]
    out = Path(scratch_dirs.mkdtemp(prefix="smout5_")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "list.bin").write_bytes(s1a_run.list_bytes(exp))
    (out / "acc.bin").write_bytes(s1a_run.acc_bytes(exp))
    exp = dict(exp, list_file=str(out / "list.bin"), acc_file=str(out / "acc.bin"))
    pl = s1a_run.pl_file(exp).read_bytes()
    tmp = Path(scratch_dirs.mkdtemp(prefix="smb_"))
    (tmp / "binit.txt").write_text("".join(f"{w:x}\n" for w in (WORDS if words is None else words)))
    (tmp / "bmap.txt").write_text("".join("%d %d %d %x %d %d %d\n" % c for c in (b_map() if cells is None else cells)))
    quirks.setdefault("pl_id", ID)
    u = H9.Board9(fault, far_rule="skip", cells=[], env=dict({"SM_DESIGN": "s2b", "SM_BINIT": str(tmp / "binit.txt"), "SM_BMAP": str(tmp / "bmap.txt")}, **(env or {})),
                  **H8.device(known["census"], reads), **quirks)
    if not quirks.get("card_is_empty"):
        u.card["s2b.bit"] = pl
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), known, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}",
                          f"s5{stage[-1]}0000{0 if share is None else share:x}.bin", stage)
    return rec, u, out

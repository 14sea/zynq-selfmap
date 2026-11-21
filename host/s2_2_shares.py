#!/usr/bin/env python3
"""S2.2: what is read, and in which run — docs/s2_plan.md, section 19.

    s2_2_shares.py [census.json]        prints the shares: how many, and for each its reads, frames, first and last address

Everything here comes from the census (census/frame_census_17A6.json): the addresses the device named, in the order
in which it named them, and where its address register stood still. Nothing is taken from a document or a database,
and nothing is computed from an address but which column of the census it lies in.

  * `layout`: the places the address register passes through — every address of the census in order, and after the
    last address of a row one place more that has no address of its own: there the register still shows the address
    it showed before (S1b.2, the end of the row). After a read of n frames the register is n + 1 places on from the
    address the read began at: the pad counts as a place. This is the rule every one of the 25,230 stored records of
    the chains obeys (tests/test_s2_2_host.py holds it against them).
  * `reads_of`: a column read in reads of three frames from its first address; the last read takes what is left.
  * `shares`: block type 0 cut into runs. Whole columns, in the census's order, as many as a run's list holds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "census" / "frame_census_17A6.json"
LIST_MAX = 178                                        # reads in one run's list (prober/sm.h)
FRAMES_A_READ = 3


def layout(census: dict) -> dict:
    """`shows`: what the register reads at each place, in order. `place`: where an address is. `column`: which column
    of the census an address lies in — (block type, half, row, column). `block0`: the addresses of block type 0."""
    still = {int(r["last"], 16) for r in census["rows"] if r["ended_by"] == "the register stood still"}
    shows: list[int] = []
    place: dict[int, int] = {}
    column: dict[int, tuple] = {}
    for e in census["entries"]:
        far = int(e["far"], 16)
        place[far] = len(shows)
        shows.append(far)
        column[far] = (e["block_type"], e["half"], e["row"], e["column"])
        if far in still:
            shows.append(far)                           # the place after a row's last frame: the register has not moved
    return {"shows": shows, "place": place, "column": column,
            "block0": [int(e["far"], 16) for e in census["entries"] if e["block_type"] == 0]}


def register_after(lay: dict, far: int, frames: int) -> int | None:
    """What the address register reads after the pad and `frames` frames were read from `far`; None where the census
    does not say (an address it does not have, or a read that runs past its last place)."""
    if far not in lay["place"]:
        return None
    at = lay["place"][far] + frames + 1
    return lay["shows"][at] if at < len(lay["shows"]) else None


def columns(lay: dict) -> list[list[int]]:
    """The columns of block type 0, each the list of its addresses, in the census's order."""
    out: list[list[int]] = []
    for far in lay["block0"]:
        if out and lay["column"][out[-1][0]] == lay["column"][far]:
            out[-1].append(far)
        else:
            out.append([far])
    return out


def reads_of(col: list[int]) -> list[tuple[int, int]]:
    return [(col[k], min(FRAMES_A_READ, len(col) - k)) for k in range(0, len(col), FRAMES_A_READ)]


def shares(census: dict, limit: int = LIST_MAX) -> list[list[tuple[int, int]]]:
    """The reads of each run: (address, frames). Every address of block type 0 is in exactly one read of one share."""
    out: list[list[tuple[int, int]]] = [[]]
    for col in columns(layout(census)):
        reads = reads_of(col)
        if len(reads) > limit:
            raise ValueError(f"a column of {len(col)} frames needs {len(reads)} reads; a run's list holds {limit}")
        if len(out[-1]) + len(reads) > limit:
            out.append([])
        out[-1] += reads
    return [s for s in out if s]


def list_words(reads: list[tuple[int, int]]) -> list[int]:
    """The list as the prober takes it: one word a read, the address in the low 28 bits, the number of frames above."""
    for far, n in reads:
        if far >> 28 or not 1 <= n <= FRAMES_A_READ:
            raise ValueError(f"({far:#x}, {n}) is not a read the list can hold")
    return [n << 28 | far for far, n in reads]


def list_problems(lay: dict, reads: list[tuple[int, int]]) -> list[str]:
    """Why a list is not one made from the census: every address it reads must be one the device named in block type
    0, every read must lie in one column, and no address may be read twice."""
    problems: list[str] = []
    seen: set[int] = set()
    for k, (far, n) in enumerate(reads):
        fars = [far + j for j in range(n)]
        if not 1 <= n <= FRAMES_A_READ:
            problems.append(f"read {k}: {n} frames"); continue
        if any(f not in lay["column"] or lay["column"][f][0] != 0 for f in fars):
            problems.append(f"read {k}: {far:#010x} x{n} reads an address the census does not have in block type 0"); continue
        if len({lay["column"][f] for f in fars}) != 1 or any(lay["place"][f] != lay["place"][far] + j for j, f in enumerate(fars)):
            problems.append(f"read {k}: {far:#010x} x{n} does not lie in one column"); continue
        if seen & set(fars):
            problems.append(f"read {k}: {far:#010x} x{n} reads an address the list has already read")
        seen |= set(fars)
    return problems


def main(argv: list[str]) -> int:
    census = json.loads(Path(argv[1] if len(argv) > 1 else CENSUS).read_text())
    all_shares = shares(census)
    print(f"{len(all_shares)} shares of block type 0, {sum(len(s) for s in all_shares)} reads, {sum(n for s in all_shares for _, n in s)} frames")
    for k, s in enumerate(all_shares):
        print(f"  share {k}: {len(s):3d} reads, {sum(n for _, n in s):3d} frames, {s[0][0]:#010x} .. {s[-1][0] + s[-1][1] - 1:#010x}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

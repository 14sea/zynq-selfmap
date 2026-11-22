#!/usr/bin/env python3
"""S2.3: the states of the probe design's RAM, and the two lists a run is given — docs/s2_plan.md, section 29.

    s2_3_states.py                 prints the runs of the step: states, accesses, reads, and how large each result is

**The numbering.** A cell of the RAM is named from the design's side and from nowhere else: memory k (0 to 3 — the
bit of the data register it is written by) and address a (0 to 63 — what the address register held). Its number is
n = 64 k + a. Nothing here says which LUT of a slice memory k is, or which pin carries which bit of the address.

**The states.** A state is the content of the whole RAM: 64 values of four bits, the value at an address having
bit k for memory k.

  * the base: all zero;
  * code state j (0 to 7): every cell holds bit j of its number; its complement: the opposite;
  * single n: cell n holds one and every other cell zero.

**The runs.** The code run: the base, each code state followed by its complement, the base — eighteen states. A run
of singles, r = 0 to 3: the base, the singles of the cells 64 r to 64 r + 63, the base — sixty-six states.

**The list of accesses** (prober/sm.h, stage 9) is made here and by nothing else, and the prober makes it entry by
entry. (In this program an entry names its register by its address; the list the prober takes has the register's
offset in the design, `acc_words`.) For each state: the RAM written (the first state of a run whole, a later one at the addresses where it
differs from the state before); the RAM read back, every address, each reading held to the state; the counter read;
the mark at which the frames are read; then the RAM read back again, every address — **it must still hold the
state** —, the counter, the design's count of writes held to the writes made, and the shift registers' outputs,
every address, held to the words the design loads them with. Before the first state the shift registers are read
the same way. No entry writes the shift registers' data: that write is a shift.

**The list of reads** comes from the census and from what S2.2 found: the column of block type 0 in which the
candidates lie, read in threes from its first address as S2.2's shares read it (`column_reads`); and, for the
singles, those of these reads that deliver a frame with a candidate (`candidate_reads`). Nothing is computed from
an address but which column of the census it lies in.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402

DESIGN = ROOT / "pl" / "s2a" / "design.json"
CANDIDATES = ROOT / "evidence" / "s2_2_17A6_2026-11-22" / "candidates.json"   # what S2.2 found, as its chain wrote it
MEMORIES, DEPTH = 4, 64
CELLS = MEMORIES * DEPTH                               # 256
CODE_BITS = 8                                          # a cell's number has eight bits
SINGLE_RUNS, SINGLES_A_RUN = 4, 64
SRL_DEPTH = 32
A_READ, A_WRITE, A_EXPECT, A_MARK = 0, 1, 2, 3         # the kinds of an entry (prober/sm.h)
MARK_FRAMES, MARK_END = 0, 1
ACC_MAX = 32768                                        # entries a list may have (prober/sm.h)
REC, FIXED_BLOCK = 480, 16                             # words of a record; of the PL block before its log
RESULT_MAX_WORDS = 0x40000


def number(k: int, a: int) -> int:
    return DEPTH * k + a


def base() -> list[int]:
    return [0] * DEPTH


def code(j: int, complement: bool = False) -> list[int]:
    """Code state j: at address a, bit k of the value is bit j of the number of cell (k, a) — or its opposite."""
    return [sum((((number(k, a) >> j) & 1) ^ int(complement)) << k for k in range(MEMORIES)) for a in range(DEPTH)]


def single(n: int) -> list[int]:
    return [(1 << (n // DEPTH)) if a == n % DEPTH else 0 for a in range(DEPTH)]


def cell(state: list[int], n: int) -> int:
    """What cell n holds in a state."""
    return (state[n % DEPTH] >> (n // DEPTH)) & 1


def code_run() -> list[dict]:
    """The eighteen states of the code run, each with what it is."""
    out = [{"name": "base", "kind": "base", "ram": base()}]
    for j in range(CODE_BITS):
        out.append({"name": f"code {j}", "kind": "code", "bit": j, "complement": False, "ram": code(j)})
        out.append({"name": f"code {j} complement", "kind": "code", "bit": j, "complement": True, "ram": code(j, True)})
    return out + [{"name": "base", "kind": "base", "ram": base()}]


def single_run(r: int) -> list[dict]:
    """The sixty-six states of run r of the singles."""
    if not 0 <= r < SINGLE_RUNS:
        raise ValueError(f"there is no run {r} of the singles")
    cells = range(SINGLES_A_RUN * r, SINGLES_A_RUN * (r + 1))
    return ([{"name": "base", "kind": "base", "ram": base()}]
            + [{"name": f"single {n}", "kind": "single", "cell": n, "ram": single(n)} for n in cells]
            + [{"name": "base", "kind": "base", "ram": base()}])


def registers(design: dict) -> dict:
    """The design's registers by name, as addresses: from the design's own record and nothing else."""
    at = int(design["base"], 16)
    return {name: at + int(r["offset"], 16) for name, r in design["registers"].items()}


def srl_words(design: dict) -> list[int]:
    """What the shift registers' outputs read at each address before any shift: bit k from shift register k, bit a
    of the word it is loaded with."""
    init = [int(design["srl"]["cells"][str(k)]["init"], 16) for k in range(MEMORIES)]
    return [sum(((init[k] >> a) & 1) << k for k in range(MEMORIES)) for a in range(SRL_DEPTH)]


def accesses(states: list[dict], design: dict) -> list[tuple[int, int, int]]:
    """The list of accesses of a run: (kind, address, value) an entry, the marks with address 0."""
    reg = registers(design)
    srl = srl_words(design)
    out: list[tuple[int, int, int]] = []

    def ram_back(ram: list[int]) -> None:
        for a in range(DEPTH):
            out.append((A_WRITE, reg["RAM_ADDR"], a))
            out.append((A_EXPECT, reg["RAM_DATA"], ram[a]))

    def srl_back() -> None:
        for a in range(SRL_DEPTH):
            out.append((A_WRITE, reg["SRL_ADDR"], a))
            out.append((A_EXPECT, reg["SRL_DATA"], srl[a]))

    writes, before = 0, None
    for i, state in enumerate(states):
        ram = state["ram"]
        if i == 0:
            srl_back()
        for a in range(DEPTH):
            if before is None or ram[a] != before[a]:
                out.append((A_WRITE, reg["RAM_ADDR"], a))
                out.append((A_WRITE, reg["RAM_DATA"], ram[a]))
                writes += 1
        ram_back(ram)
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_MARK, 0, MARK_FRAMES))
        ram_back(ram)
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_EXPECT, reg["WRITES"], writes))  # the low half: writes to the RAM; the high half: shifts, none
        srl_back()
        out.append((A_MARK, 0, MARK_END))
        before = ram
    if len(out) > ACC_MAX:
        raise ValueError(f"{len(out)} entries; a list holds {ACC_MAX}")
    return out


def acc_words(entries: list[tuple[int, int, int]], design: dict) -> list[int]:
    """The list as the prober takes it: two words an entry — the register's offset in the design with the kind in its
    two low bits, and the value. A mark has no register: its offset is zero."""
    at = int(design["base"], 16)
    words: list[int] = []
    for kind, addr, value in entries:
        if addr & 3 or not 0 <= kind <= 3 or not 0 <= value < 2 ** 32 or not 0 <= addr < 2 ** 32:
            raise ValueError(f"({kind}, {addr:#x}, {value:#x}) is not an entry the list can hold")
        words += [(0 if kind == A_MARK and addr == 0 else (addr - at) % 2 ** 32) | kind, value]
    return words


def may_write(entries: list[tuple[int, int, int]], design: dict) -> int:
    """The registers a list writes, one bit for each offset: what the parameter block says the run may write."""
    at = int(design["base"], 16)
    return sum({1 << (addr - at) for kind, addr, _ in entries if kind == A_WRITE})


def planned_log(entries: list[tuple[int, int, int]], design: dict) -> list[tuple[int, bool, int | None]]:
    """What the log of a run that went through must be, access by access: (address, a write?, the value — None
    where the list only records what was read). The first is the prober's own: the identification register."""
    reg = registers(design)
    return ([(reg["ID"], False, int(design["id"], 16))]
            + [(addr, kind == A_WRITE, None if kind == A_READ else value) for kind, addr, value in entries if kind != A_MARK])


def candidate_frames(candidates: dict) -> list[int]:
    return sorted(int(f, 16) for f in candidates["frames_with_candidates"])


def column_reads(census: dict, candidates: dict) -> list[tuple[int, int]]:
    """The reads of the column in which S2.2's candidates lie. All of them must lie in one column of block type 0."""
    lay = s2_2_shares.layout(census)
    frames = candidate_frames(candidates)
    if not frames:
        raise ValueError("S2.2 has no candidate: there is no column to read")
    cols = [c for c in s2_2_shares.columns(lay) if set(c) & set(frames)]
    if len(cols) != 1 or not set(frames) <= set(cols[0]):
        raise ValueError("the frames with candidates do not lie in one column of block type 0 of the census")
    return s2_2_shares.reads_of(cols[0])


def candidate_reads(census: dict, candidates: dict) -> list[tuple[int, int]]:
    """Those reads of the column that deliver a frame with a candidate."""
    frames = set(candidate_frames(candidates))
    return [(far, n) for far, n in column_reads(census, candidates) if frames & {far + j for j in range(n)}]


def result_words(n_states: int, n_reads: int, n_log: int) -> int:
    """How many words the result of a run that went through has: the header, the PL block with its log, the records."""
    return 64 + FIXED_BLOCK + 2 * n_log + (4 + n_states * n_reads) * REC


def plan(kind: str, share: int | None, design: dict, census: dict, candidates: dict) -> dict:
    """Everything a run is given and held to: its states, the list of accesses, the list of reads."""
    if kind == "code":
        states, reads = code_run(), column_reads(census, candidates)
    elif kind == "singles":
        if share is None:
            raise ValueError("a run of singles is one of four: which?")
        states, reads = single_run(share), candidate_reads(census, candidates)
    else:
        raise ValueError(f"no run of the kind {kind!r}")
    entries = accesses(states, design)
    log = planned_log(entries, design)
    words = result_words(len(states), len(reads), len(log))
    if words > RESULT_MAX_WORDS:
        raise ValueError(f"the result would have {words} words; its area holds {RESULT_MAX_WORDS}")
    return {"kind": kind, "share": share, "states": states, "reads": reads, "entries": entries, "log": log,
            "may_write": may_write(entries, design), "result_words": words}


def main(argv: list[str]) -> int:
    design = json.loads(DESIGN.read_text())
    census = json.loads(s2_2_shares.CENSUS.read_text())
    candidates = json.loads(CANDIDATES.read_text())
    for kind, share in [("code", None)] + [("singles", r) for r in range(SINGLE_RUNS)]:
        p = plan(kind, share, design, census, candidates)
        name = "the code run" if kind == "code" else f"singles, run {share}"
        print(f"{name}: {len(p['states'])} states, {len(p['entries'])} entries ({len(p['log'])} accesses), "
              f"{len(p['reads'])} reads a state ({p['reads'][0][0]:#010x} .. {p['reads'][-1][0] + p['reads'][-1][1] - 1:#010x}), "
              f"may write {p['may_write']:#010x}, result {p['result_words']} words ({4 * p['result_words']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

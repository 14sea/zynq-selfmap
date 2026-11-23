#!/usr/bin/env python3
"""S2.4: the states of the design's shift registers, and both lists of a run — docs/s2_plan.md, sections 37 and 38.

    s2_4_states.py            print what each run of the step would be given (no board, no result)

The design has four shift registers of 32 behind two registers (pl/s2a/design.json): a write to SRL_DATA shifts all
four by one, bit k of the word into register k; SRL_ADDR chooses which of the 32 outputs SRL_DATA reads — address a,
the bit shifted in a + 1 shifts ago. So any content is given to all four by 32 writes, the word for output 31 first.

A state is what the four hold: 32 words, the word at address a having bit k from register k — the form in which the
design's own record gives what they are loaded with (s2_3_states.srl_words). Cell 32 k + a is output a of register k:
128 cells, a number of seven bits. "Output a" is what the design's address register chooses; which stage of the
primitive that is inside the device is claimed nowhere.

The runs (section 37):

    find, share 0 to 7   one share of the census's addresses of block type 0 (S2.2's shares, as they are), in three
                         states: all zero, all one, all zero
    code                 seventeen states over the column the candidates lie in: as loaded, with nothing shifted;
                         all zero; the seven code states, each followed by its complement (in code state j, cell n
                         holds bit j of n); and the loaded words shifted in again. The all-zero state is what tells a
                         bit that follows a cell from one that follows another cell inverted: over the code states
                         and their complements alone, cell n inverted reads as cell 127 - n does, and what the cells
                         are loaded with does not part them all
    singles, run 0 or 1  66 states over the reads that deliver the frames with candidates: the loaded content,
                         shifted in; then with each of 64 cells alone the other way; then the loaded content again
    pairs                six states over the same reads, for bit 5 of the status alone (section 38, point 5): the
                         loaded content, shifted in; then with two, two, three and four cells the other way (PAIRS);
                         then the loaded content again. Which frames those cells' bits lie in is not known here: the
                         chain sets it down from the table afterwards

Only the code run has a state in which nothing has been shifted yet, and it is its first. A place of a register may
read otherwise then than after shifts (s2_4_judge; section 42); in the code run every cell changes over the shifted
states, so such a place still follows its cell there and is told from one that follows nothing. In a run of the
singles half the cells never change, and a place of one of those that read otherwise before any shift would be a bit
that moves and follows nothing: so those runs begin with the loaded content shifted in.

Every state but the first of the code run, "as loaded", is made by 32 shifts, whatever the four held before. In every state all 32
outputs are read back and held to the state before the frames are read and again after; the counter is read on both
sides; the design's count of writes must be the shifts made so far and no write to the RAM. The RAM, which this step
never writes, is read at all 64 addresses before the first state's frames and after the last state's, and must read
zero.

The prober takes all of it as a list of accesses and knows no state (stage 9, as S2.3 left it). Nothing here reads a
result."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402
import s2_3_states as st9  # noqa: E402
from s2_3_states import A_EXPECT, A_MARK, A_READ, A_WRITE, ACC_MAX, MARK_END, MARK_FRAMES, RESULT_MAX_WORDS  # noqa: E402,F401

DESIGN = ROOT / "pl" / "s2a" / "design.json"
PART_1 = ROOT / "evidence" / "s2_4_17A6_2026-11-23"   # the chain of part 1, as it was stored
CANDIDATES = PART_1 / "candidates.json"                # what part 1 found, as its chain wrote it
CHAIN_OF_PART_1 = PART_1 / "chain.json"                # and that chain's own file: its closing has what CTL0 read in its runs
PAIRS = ((0, 1), (0, 4), (0, 1, 2), (0, 1, 2, 3))      # the cells turned the other way together in the states of the pairs
REGISTERS, DEPTH = 4, 32
CELLS = REGISTERS * DEPTH                              # 128
CODE_BITS = 7                                          # a cell's number has seven bits
SINGLE_RUNS, SINGLES_A_RUN = 2, 64
FIND_SHARES = 8                                        # the shares of the device's census, as S2.2 made them: what main prints, and what a test holds
RAM_DEPTH = 64
MAX_STATES = 80                                        # what the stage takes (prober/sm.h)


def number(k: int, a: int) -> int:
    return DEPTH * k + a


def cell(state: list[int], n: int) -> int:
    """What cell n holds in a state."""
    return (state[n % DEPTH] >> (n // DEPTH)) & 1


def uniform(bit: int) -> list[int]:
    return [0xF if bit else 0] * DEPTH


def code(j: int, complement: bool = False) -> list[int]:
    """Code state j: output a of register k holds bit j of the number of cell (k, a) — or its opposite."""
    return [sum((((number(k, a) >> j) & 1) ^ int(complement)) << k for k in range(REGISTERS)) for a in range(DEPTH)]


def single(loaded: list[int], n: int) -> list[int]:
    """The loaded content with cell n alone the other way."""
    return [w ^ (1 << (n // DEPTH)) if a == n % DEPTH else w for a, w in enumerate(loaded)]


def shifts(state: list[int]) -> list[int]:
    """The 32 words that, written to SRL_DATA one after the other, leave the four holding `state`: what is written
    first ends at output 31."""
    return [state[a] for a in range(DEPTH - 1, -1, -1)]


def shifted(before: list[int], word: int) -> list[int]:
    """What the four hold after one shift of `word`: the model of the design's shift, used to check `shifts` and by
    the judge to work a state out again from the log."""
    return [word & 0xF] + before[:-1]


def shares(census: dict, design: dict) -> list[list[tuple[int, int]]]:
    """The shares of the census's addresses of block type 0, a run of part 1 for each: S2.2's shares, as s2_2_shares
    makes them. `design` is what is known of the device; a test gives its made-up device, which is small, fewer reads
    a run ("reads_a_run") so that it has more shares than one. On the device nothing gives that, and the limit is the
    stage's."""
    return s2_2_shares.shares(census, design.get("reads_a_run", s2_2_shares.LIST_MAX))


def find_run() -> list[dict]:
    return [{"name": "all zero", "kind": "uniform", "bit": 0, "srl": uniform(0), "shifted": True},
            {"name": "all one", "kind": "uniform", "bit": 1, "srl": uniform(1), "shifted": True},
            {"name": "all zero", "kind": "uniform", "bit": 0, "srl": uniform(0), "shifted": True}]


def code_run(loaded: list[int]) -> list[dict]:
    """The seventeen states of the code run, each with what it is."""
    out = [{"name": "as loaded", "kind": "loaded", "srl": list(loaded), "shifted": False},
           {"name": "all zero", "kind": "uniform", "bit": 0, "srl": uniform(0), "shifted": True}]
    for j in range(CODE_BITS):
        out.append({"name": f"code {j}", "kind": "code", "bit": j, "complement": False, "srl": code(j), "shifted": True})
        out.append({"name": f"code {j} complement", "kind": "code", "bit": j, "complement": True, "srl": code(j, True), "shifted": True})
    return out + [{"name": "loaded again", "kind": "loaded", "srl": list(loaded), "shifted": True}]


def single_run(loaded: list[int], r: int) -> list[dict]:
    """The sixty-six states of run r of the singles."""
    if not 0 <= r < SINGLE_RUNS:
        raise ValueError(f"there is no run {r} of the singles")
    cells = range(SINGLES_A_RUN * r, SINGLES_A_RUN * (r + 1))
    return ([{"name": "loaded", "kind": "loaded", "srl": list(loaded), "shifted": True}]
            + [{"name": f"single {n}", "kind": "single", "cell": n, "srl": single(loaded, n), "shifted": True} for n in cells]
            + [{"name": "loaded again", "kind": "loaded", "srl": list(loaded), "shifted": True}])


def several(loaded: list[int], cells: tuple[int, ...]) -> list[int]:
    """The loaded content with those cells the other way."""
    out = list(loaded)
    for n in cells:
        out = single(out, n)
    return out


def pairs_run(loaded: list[int]) -> list[dict]:
    """The six states of the run of the pairs."""
    return ([{"name": "loaded", "kind": "loaded", "srl": list(loaded), "shifted": True}]
            + [{"name": "cells " + ", ".join(str(n) for n in cells), "kind": "several", "cells": list(cells), "srl": several(loaded, cells), "shifted": True} for cells in PAIRS]
            + [{"name": "loaded again", "kind": "loaded", "srl": list(loaded), "shifted": True}])


def accesses(states: list[dict], design: dict) -> list[tuple[int, int, int]]:
    """The list of accesses of a run: (kind, address, value) an entry, the marks with address 0."""
    reg = st9.registers(design)
    out: list[tuple[int, int, int]] = []

    def srl_back(srl: list[int]) -> None:
        for a in range(DEPTH):
            out.append((A_WRITE, reg["SRL_ADDR"], a))
            out.append((A_EXPECT, reg["SRL_DATA"], srl[a]))

    def ram_back() -> None:                              # the RAM is never written in this step: it reads as loaded, all zero
        for a in range(RAM_DEPTH):
            out.append((A_WRITE, reg["RAM_ADDR"], a))
            out.append((A_EXPECT, reg["RAM_DATA"], 0))

    made = 0
    for i, state in enumerate(states):
        if state["shifted"]:
            for word in shifts(state["srl"]):
                out.append((A_WRITE, reg["SRL_DATA"], word))
            made += DEPTH
        srl_back(state["srl"])
        if i == 0:
            ram_back()
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_MARK, 0, MARK_FRAMES))
        srl_back(state["srl"])
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_EXPECT, reg["WRITES"], made << 16))  # the high half: shifts; the low half: writes to the RAM, none
        if i == len(states) - 1:
            ram_back()
        out.append((A_MARK, 0, MARK_END))
    if len(out) > ACC_MAX:
        raise ValueError(f"{len(out)} entries; a list holds {ACC_MAX}")
    return out


def plan(kind: str, share: int | None, design: dict, census: dict, candidates: dict | None = None) -> dict:
    """Everything a run is given and held to: its states, the list of accesses, the list of reads. `candidates`: what
    part 1 found, in the form S2.2's chain wrote its own — needed by the code run and the singles, not by a run of
    part 1."""
    loaded = st9.srl_words(design)
    if kind == "find":
        every = shares(census, design)
        if share is None or not 0 <= share < len(every):
            raise ValueError(f"a run of part 1 is of one share of {len(every)}: which?")
        states, reads = find_run(), every[share]
    elif kind in ("code", "singles", "pairs"):
        if candidates is None:
            raise ValueError("what part 1 found is not given: there is nothing to read the states over")
        if kind == "code":
            if share is not None:
                raise ValueError("the code run is one run")
            states, reads = code_run(loaded), st9.column_reads(census, candidates)
        elif kind == "pairs":
            if share is not None:
                raise ValueError("the run of the pairs is one run")
            states, reads = pairs_run(loaded), st9.candidate_reads(census, candidates)
        else:
            if share is None:
                raise ValueError("a run of singles is one of two: which?")
            states, reads = single_run(loaded, share), st9.candidate_reads(census, candidates)
    else:
        raise ValueError(f"no run of the kind {kind!r}")
    if len(states) > MAX_STATES:
        raise ValueError(f"{len(states)} states; the stage takes {MAX_STATES}")
    entries = accesses(states, design)
    log = st9.planned_log(entries, design)
    words = st9.result_words(len(states), len(reads), len(log))
    if words > RESULT_MAX_WORDS:
        raise ValueError(f"the result would have {words} words; its area holds {RESULT_MAX_WORDS}")
    return {"kind": kind, "share": share, "states": states, "reads": reads, "entries": entries, "log": log,
            "may_write": st9.may_write(entries, design), "result_words": words}


def main(argv: list[str]) -> int:
    design = json.loads(DESIGN.read_text())
    census = json.loads(s2_2_shares.CENSUS.read_text())
    for share in range(FIND_SHARES):
        p = plan("find", share, design, census)
        print(f"part 1, share {share}: {len(p['states'])} states, {len(p['entries'])} entries ({len(p['log'])} accesses), {len(p['reads'])} reads a state "
              f"({p['reads'][0][0]:#010x} .. {p['reads'][-1][0] + p['reads'][-1][1] - 1:#010x}), may write {p['may_write']:#010x}, "
              f"result {p['result_words']} words ({4 * p['result_words']} bytes)")
    candidates = json.loads(CANDIDATES.read_text())
    for kind, share in [("code", None)] + [("singles", r) for r in range(SINGLE_RUNS)] + [("pairs", None)]:
        p = plan(kind, share, design, census, candidates)
        name = {"code": "the code run", "singles": f"singles, run {share}", "pairs": "the pairs"}[kind]
        print(f"part 2, {name}: {len(p['states'])} states, {len(p['entries'])} entries ({len(p['log'])} accesses), {len(p['reads'])} reads a state "
              f"({p['reads'][0][0]:#010x} .. {p['reads'][-1][0] + p['reads'][-1][1] - 1:#010x}), may write {p['may_write']:#010x}, "
              f"result {p['result_words']} words ({4 * p['result_words']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

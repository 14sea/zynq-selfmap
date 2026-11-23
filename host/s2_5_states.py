#!/usr/bin/env python3
"""S2.5: the states of the design s2b, and both lists of a run — docs/s2_plan.md, sections 45 and 46.

    s2_5_states.py            print what each run of the step would be given (no board, no result)

The design has LUT RAM at 110 sites, four memories of 64 at each, behind eight registers (pl/s2b/design.json). A cell
of a site is named as in S2.3: memory k (the bit of the data register it is written by) and address a; its number is
n = 64 k + a. Every site has the same 256 numbers.

**Every write of this step goes to every site at once** (the site register's bit 8), so after a write all 110 sites
hold alike. A state is what every site holds: 64 values of four bits — or, for the one state in which nothing has
been written yet, "as loaded": each memory with the word of its own the design loads it with.

The runs (section 45):

    find, share 0 to 7     one share of the census's addresses of block type 0 (S2.2's shares, as they are), in three
                           states: as loaded, all one, all zero
    code                   eighteen states over the reads that deliver the frames with candidates: all zero; the
                           eight code states, each followed by its complement (in code state j every cell holds bit j
                           of its number); all zero
    singles, run 0 to 15   eighteen states over the same reads: all zero; then, for each of sixteen cells, that cell
                           one at every site and every other cell zero; all zero

**What holds a state.** The design gives one reading over all sites (CHECK): at the address set and for each memory,
whether a site holds a one, whether every site does, and the parity of what they hold. In every state it is read at
all 64 addresses before the frames and again after, each reading held to the state: for a state that was written,
"a site holds a one" and "every site does" must both be the value written; for the state as loaded, all three are
what the words the design loads give. So "every one of the 110 sites holds this state" is 64 readings, and it is
asked on both sides of the frames. The counter is read on both sides; the count of writes must be the writes made;
the site register must still say "every site" when the state ends. **No run of this step writes or reads one site
alone**: which site a place belongs to is found from the words the memories are loaded with (part 1), not through
the site register.

The prober takes all of it as a list of accesses and knows no state (stage 9, the image as S2.3 left it). Nothing
here reads a result."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402
import s2_3_states as st9  # noqa: E402
from s2_3_states import A_EXPECT, A_MARK, A_READ, A_WRITE, ACC_MAX, MARK_END, MARK_FRAMES, RESULT_MAX_WORDS, base, cell, code, number, single  # noqa: E402,F401

DESIGN = ROOT / "pl" / "s2b" / "design.json"
PART_1 = ROOT / "evidence" / "s2_5_17A6"               # the chain of part 1, where it will be stored
CANDIDATES = PART_1 / "candidates.json"                # what part 1 found, as its chain writes it
CHAIN_OF_PART_1 = PART_1 / "chain.json"
MEMORIES, DEPTH = 4, 64
CELLS = MEMORIES * DEPTH                               # 256, at every site
CODE_BITS = 8
SINGLE_RUNS, SINGLES_A_RUN = 16, 16
FIND_SHARES = 8                                        # the shares of the device's census, as S2.2 made them
EVERY = 0x100                                          # the site register: a write goes to every site
MAX_STATES = 80                                        # what the stage takes (prober/sm.h)


def loaded(design: dict) -> list[list[int]]:
    """What the design loads: for each site its four words of 64 bits, bit a the content of address a."""
    sites = design["ram"]["sites"]
    if [s["site"] for s in sites] != list(range(len(sites))) or any(len(s["init"]) != MEMORIES for s in sites):
        raise ValueError("the design's record does not list its sites in order with four words each")
    return [[int(w, 16) for w in s["init"]] for s in sites]


def check_of(values: list[int]) -> int:
    """What CHECK reads where the sites hold these values (four bits a site): bit k, a site holds a one in memory k;
    bit 4 + k, every site does; bit 8 + k, the parity."""
    any_, all_, par = 0, 0xF, 0
    for v in values:
        any_ |= v; all_ &= v; par ^= v
    return any_ | all_ << 4 | par << 8


def checks(ram: list[int] | None, design: dict) -> list[int]:
    """What CHECK reads at each of the 64 addresses in a state: `ram` the 64 values every site holds, or None for the
    state as loaded."""
    words = loaded(design)
    if ram is None:
        return [check_of([sum(((w[k] >> a) & 1) << k for k in range(MEMORIES)) for w in words]) for a in range(DEPTH)]
    return [check_of([ram[a]] * len(words)) for a in range(DEPTH)]


def find_run() -> list[dict]:
    return [{"name": "as loaded", "kind": "loaded", "ram": None},
            {"name": "all one", "kind": "uniform", "bit": 1, "ram": [0xF] * DEPTH},
            {"name": "all zero", "kind": "uniform", "bit": 0, "ram": [0] * DEPTH}]


def code_run() -> list[dict]:
    """The eighteen states of the code run: S2.3's, written to every site."""
    return [dict(s) for s in st9.code_run()]


def single_run(r: int) -> list[dict]:
    """The eighteen states of run r of the singles."""
    if not 0 <= r < SINGLE_RUNS:
        raise ValueError(f"there is no run {r} of the singles")
    cells = range(SINGLES_A_RUN * r, SINGLES_A_RUN * (r + 1))
    return ([{"name": "base", "kind": "base", "ram": base()}]
            + [{"name": f"single {n}", "kind": "single", "cell": n, "ram": single(n)} for n in cells]
            + [{"name": "base", "kind": "base", "ram": base()}])


def accesses(states: list[dict], design: dict) -> list[tuple[int, int, int]]:
    """The list of accesses of a run: (kind, address, value) an entry, the marks with address 0."""
    reg = st9.registers(design)
    out: list[tuple[int, int, int]] = [(A_WRITE, reg["SITE"], EVERY), (A_EXPECT, reg["SITE"], EVERY)]

    def back(ram: list[int] | None) -> None:
        for a, value in enumerate(checks(ram, design)):
            out.append((A_WRITE, reg["RAM_ADDR"], a))
            out.append((A_EXPECT, reg["CHECK"], value))

    writes = 0
    before: list[int | None] = [None] * DEPTH              # what every site holds at each address; None: what it was loaded with
    for i, state in enumerate(states):
        ram = state["ram"]
        if ram is None:
            if i:
                raise ValueError("the state as loaded can only be a run's first: nothing puts the loaded words back")
        else:
            for a in range(DEPTH):
                if before[a] != ram[a]:
                    out.append((A_WRITE, reg["RAM_ADDR"], a))
                    out.append((A_WRITE, reg["RAM_DATA"], ram[a]))
                    writes += 1
            before = list(ram)
        back(ram)
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_MARK, 0, MARK_FRAMES))
        back(ram)
        out.append((A_READ, reg["COUNT"], 0))
        out.append((A_EXPECT, reg["WRITES"], writes))
        out.append((A_EXPECT, reg["SITE"], EVERY))
        out.append((A_MARK, 0, MARK_END))
    if len(out) > ACC_MAX:
        raise ValueError(f"{len(out)} entries; a list holds {ACC_MAX}")
    return out


def shares(census: dict, design: dict) -> list[list[tuple[int, int]]]:
    """The shares of the census's addresses of block type 0, a run of part 1 for each: S2.2's shares. A test gives
    its made-up device, which is small, fewer reads a run ("reads_a_run")."""
    return s2_2_shares.shares(census, design.get("reads_a_run", s2_2_shares.LIST_MAX))


def candidate_reads(census: dict, candidates: dict) -> list[tuple[int, int]]:
    """The reads that deliver a frame with a candidate: of every column of block type 0 that has one, read in threes
    from its first address as the shares read it, those reads that hold one. In the census's order."""
    frames = {int(f, 16) for f in candidates["frames_with_candidates"]}
    if not frames:
        raise ValueError("part 1 has no candidate: there is nothing to read the states over")
    lay = s2_2_shares.layout(census)
    reads = [(far, n) for col in s2_2_shares.columns(lay) for far, n in s2_2_shares.reads_of(col) if frames & {far + j for j in range(n)}]
    if frames - {far + j for far, n in reads for j in range(n)}:
        raise ValueError("a frame with candidates is no address of block type 0 of the census")
    return reads


def plan(kind: str, share: int | None, design: dict, census: dict, candidates: dict | None = None) -> dict:
    """Everything a run is given and held to: its states, the list of accesses, the list of reads. `candidates`: what
    part 1 found, as its chain wrote it — needed by the runs of part 2, not by a run of part 1."""
    if kind == "find":
        every = shares(census, design)
        if share is None or not 0 <= share < len(every):
            raise ValueError(f"a run of part 1 is of one share of {len(every)}: which?")
        states, reads = find_run(), every[share]
    elif kind in ("code", "singles"):
        if candidates is None:
            raise ValueError("what part 1 found is not given: there is nothing to read the states over")
        if kind == "code":
            if share is not None:
                raise ValueError("the code run is one run")
            states = code_run()
        else:
            if share is None:
                raise ValueError(f"a run of singles is one of {SINGLE_RUNS}: which?")
            states = single_run(share)
        reads = candidate_reads(census, candidates)
    else:
        raise ValueError(f"no run of the kind {kind!r}")
    if len(states) > MAX_STATES:
        raise ValueError(f"{len(states)} states; the stage takes {MAX_STATES}")
    if len(reads) > s2_2_shares.LIST_MAX:
        raise ValueError(f"{len(reads)} reads; a run's list holds {s2_2_shares.LIST_MAX}")
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
    if not CANDIDATES.is_file():
        print("part 2: its reads are made from what part 1 finds, and part 1 has not been stored")
        return 0
    candidates = json.loads(CANDIDATES.read_text())
    for kind, share in [("code", None)] + [("singles", r) for r in range(SINGLE_RUNS)]:
        p = plan(kind, share, design, census, candidates)
        name = "the code run" if kind == "code" else f"singles, run {share}"
        print(f"part 2, {name}: {len(p['states'])} states, {len(p['entries'])} entries ({len(p['log'])} accesses), {len(p['reads'])} reads a state, "
              f"may write {p['may_write']:#010x}, result {p['result_words']} words ({4 * p['result_words']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

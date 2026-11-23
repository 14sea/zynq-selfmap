#!/usr/bin/env python3
"""Judge the result of a run of S2.5 — docs/s2_plan.md, sections 45 and 46.

    s2_5_judge.py <result.bin> find <share>       a run of part 1: one share of block type 0 in three states
    s2_5_judge.py <result.bin> code               the code run
    s2_5_judge.py <result.bin> singles <run>      a run of the singles

A run of S2.5 is a run of stage 9, and everything a run of that stage is held to whatever its states are is judged by
the judge of S2.3 (s2_3_judge.judge, which this one calls): the header, the gates, every record from its raw words,
the streams, the status after every read and the clearing of bit 5, the log of accesses against the list, the
schedule and what it implies for the header.

What is judged here is the design's side — the design s2b, RAM at 110 sites — from the log and from nothing else:

  * What every site holds is worked out again from the log: at each address, what the design loads there until a
    write to every site has been made at it, and after that the value last written. It is never taken from the plan.
    A write that does not go to every site is a fault: no run of this step makes one.
  * Every reading over all sites (CHECK) is held to that. In every state whose frames were read it was read at all
    64 addresses before the frames and after them, and no write lies between: reading configuration memory did not
    disturb a memory at any site — as far as that reading shows, which for a state as loaded is the parity over the
    sites of each memory at each address.
  * The counter went on over every state's frames. The design's count of writes is the writes the log has. The site
    register read "every site" when each state ended.
  * Which run of the step it is, is found by the states so worked out and read back — of part 1, of the code run, of
    a run of the singles — and both lists and the word of what the run may write are held to the plan of that run.

The finding: every bit of every frame read, by its readings over the states. What a bit follows is asked over the
states that were written (in part 1: all one, all zero), where every site holds alike. A bit is still; or it follows a
cell — it reads as that cell holds in every written state — as it is or inverted; or it is irregular, and the run
fails. In a run of part 1 every cell holds the same in a written state, so no cell is named: the bits that follow are
the candidates, and with each is set down what it read in the state as loaded — from which the chain, not this judge,
finds whose memory it is. A cell here is a number of 256 that every site has: which site a place belongs to no run of
part 2 can say.

The bits that follow are written a word of a frame at a time: its bits that follow, lowest first; beside each the
cell (part 2) or what it read as loaded (part 1); and those of them that follow inverted.

No database is read and nothing is graded. Nothing here is general knowledge of the device family."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_3_judge  # noqa: E402
import s2_3_states as st9  # noqa: E402
import s2_5_states as st  # noqa: E402
from s2_3_judge import CTL0_BITS, ERR_MASK, FIXED, FRAME, HDR0, PCFG_DONE, PL_BASE, PL_CODES, REC, RESULT_MAX_WORDS, STAGE  # noqa: E402,F401

SETS = {"find": "s2_5f", "code": "s2_5c", "singles": "s2_5s"}   # the kinds of run, each with its set in the run script
TAKES_A_SHARE = ("find", "singles")                    # of which these are one run of several


def runs_of_the_step() -> list[tuple[str, int | None, list[dict]]]:
    """Every run the step has, by its states: (kind, which run of that kind — None where the states do not say, the
    states). A run of part 1 has the same states whichever share it reads."""
    return [("find", None, st.find_run()), ("code", None, st.code_run())] + [("singles", r, st.single_run(r)) for r in range(st.SINGLE_RUNS)]


def design_side(c: dict) -> dict:
    """The rest of the judging, given what the stage's judge found (s2_3_judge.judge, `rest`)."""
    out, known, par, log, cuts, recs = c["out"], c["known"], c["par"], c["log"], c["cuts"], c["recs"]
    status, anomalies, plb, reads, entries = c["status"], c["anomalies"], c["plb"], c["reads"], c["entries"]
    passes_made, n_states, n_list = c["passes_made"], c["n_states"], c["n_list"]
    bad = out["problems"].append

    # ---- what the design said of itself, from the log and only as far as it goes
    reg = words = None
    try:
        if known and "registers" in known and "ram" in known:
            reg, words = st9.registers(known), st.loaded(known)
            as_loaded = st.checks(None, known)
            for name in ("SITE", "COUNT", "RAM_ADDR", "RAM_DATA", "CHECK", "WRITES"):
                reg[name]
    except (ValueError, KeyError, TypeError) as e:
        reg = None
        bad(f"the design's record is not one of a design with RAM at sites behind these registers: {type(e).__name__}: {e}")
    pl: dict = {"accesses": len(log), "code": f"{plb[2]:#x}", "says": PL_CODES.get(plb[2], "unknown"), "passes_the_sites_held_through": 0}
    if log:
        pl["id"] = f"{log[0][1]:#010x}"
    states: list[list[int | None]] = []                  # for every state whose two stretches were walked whole: what every site holds at each address
    if reg is None:
        if not any("the design's record" in p for p in out["problems"]):
            bad("the design's registers and what it loads into its memories were not given: what the log says of them cannot be read")
    else:
        n_sites = len(words)
        held: list[int | None] = [None] * st.DEPTH         # the model: None, what the design loaded there; a value, what every site was written with
        site_reg, ram_at, writes = 0, None, 0              # the design comes up with site 0 named and a write going to it alone
        counters: list[str] = []
        for s in range(min(passes_made, n_states)):
            seen: list[dict[int, int]] = [{}, {}]        # before the frames, after them: address -> what CHECK read
            count: list[list[int]] = [[], []]
            said: list[list[int]] = [[], []]
            counted: list[int] = []
            ok = True
            for side, (b, e) in enumerate((cuts[2 * s], cuts[2 * s + 1])):
                for at in range(b, e):
                    word, value = log[at]
                    addr, write = word & ~3, bool(word & 1)
                    if addr == reg["SITE"]:
                        if write:
                            site_reg = value & 0x17F
                        elif value != site_reg:
                            bad(f"PL access {at}: the site register read {value:#x}; by the log it was last written {site_reg:#x}"); ok = False
                        else:
                            said[side].append(value)
                    elif addr == reg["RAM_ADDR"] and write:
                        ram_at = value
                    elif addr == reg["RAM_DATA"] and write:
                        writes += 1
                        if side:
                            bad(f"PL access {at}: a write after the frames of state {s} were read and before its end"); ok = False
                        if site_reg != st.EVERY:
                            bad(f"PL access {at}: a write with the site register at {site_reg:#x}: not to every site, and no run of this step makes one"); ok = False
                        elif ram_at is None or ram_at >= st.DEPTH:
                            bad(f"PL access {at}: a write at no address of the memories"); ok = False
                        else:
                            held[ram_at] = value & 0xF
                    elif addr == reg["RAM_DATA"]:
                        bad(f"PL access {at}: a reading of one site alone; no run of this step makes one"); ok = False
                    elif addr == reg["CHECK"] and not write:
                        if ram_at is None or ram_at >= st.DEPTH:
                            bad(f"PL access {at}: the reading over all sites made at no address of the memories"); ok = False
                            continue
                        gives = as_loaded[ram_at] if held[ram_at] is None else st.check_of([held[ram_at]] * n_sites)
                        if value != gives:
                            bad(f"PL access {at}: at address {ram_at} the reading over all sites is {value:#05x}; by the log the sites hold what gives {gives:#05x}"); ok = False
                        else:
                            seen[side][ram_at] = value
                    elif addr == reg["COUNT"] and not write:
                        count[side].append(value)
                    elif addr == reg["WRITES"] and not write:
                        counted.append(value)
            if not ok:
                break
            if sorted(seen[0]) != list(range(st.DEPTH)) or sorted(seen[1]) != list(range(st.DEPTH)):
                bad(f"state {s}: the reading over all sites was not made at every address before the frames and after them"); break
            if not count[0] or not count[1]:
                bad(f"state {s}: the counter was not read before the frames and after them")
            else:
                counters += [f"{count[0][-1]:#010x}", f"{count[1][0]:#010x}"]
                if count[0][-1] == count[1][0]:
                    bad(f"state {s}: the counter read {count[0][-1]:#010x} before the frames and after them: the design's clock did not go on")
            if not counted:
                bad(f"state {s}: the design's count of writes was not read after the frames")
            elif counted[-1] != writes:
                bad(f"state {s}: the design counted {counted[-1]} write(s); the log has {writes}")
            else:
                pl["writes_counted"] = counted[-1]
            if st.EVERY not in said[1]:
                bad(f"state {s}: the site register was not read as naming every site after the frames")
            states.append(list(held))
        pl["passes_the_sites_held_through"] = len(states)
        pl["sites"] = n_sites
        pl["addresses_as_loaded"] = [sum(1 for v in x if v is None) for x in states]
        pl["counter"] = counters
    out["pl"] = pl

    # ---- CTL0: the same before and after
    ctl0_seen = c["ctl0_seen"]
    ctl0: dict = {"values": {f"{v:#010x}": where for v, where in sorted(ctl0_seen.items())}}
    if len(ctl0_seen) > 1:
        bad("CTL0 does not read the same before and after: " + ", ".join(f"{v:#010x} in record(s) {where}" for v, where in sorted(ctl0_seen.items())))
    if len(ctl0_seen) == 1:
        v = next(iter(ctl0_seen))
        ctl0["value"] = f"{v:#010x}"
        ctl0["bits_set"] = [f"{b} {CTL0_BITS.get(b, 'not in table 5-27')}" for b in range(31, -1, -1) if v >> b & 1]
    out["registers"] = {"CTL0": ctl0}

    # ---- which run of the step this is: by its states, and both lists held to what the plan makes for it
    run: dict = {"kind": None, "share": None}
    whole = status == 1 and passes_made == n_states and len(states) == n_states and len(recs) == 4 + n_states * n_list and all(r["code"] == 0 for r in recs)
    named = None
    if whole:
        for kind, which, its_states in runs_of_the_step():
            if states == [x["ram"] if x["ram"] is not None else [None] * st.DEPTH for x in its_states]:
                run, named = {"kind": kind, "share": which}, its_states
        if named is None:
            bad("the states the sites were written to and read back as are not those of a run of part 1, of the code run or of a run of the singles")
        elif not known or "census" not in known:
            bad("the census was not given: the lists cannot be held to the plan of the run")
        else:
            try:
                if run["kind"] == "find":                # which share: the one whose reads these are
                    every = st.shares(known["census"], known)
                    run["share"] = every.index(reads) if reads in every else None
                    if run["share"] is None:
                        raise ValueError("the list of reads is no share of the census's addresses of block type 0")
                p = st.plan(run["kind"], run["share"], known, known["census"], known.get("candidates"))
            except (ValueError, KeyError) as e:          # what is known does not make a plan, or lacks what a plan is made from
                p = None
                bad(f"no plan can be made for the run: {e}")
            if p is not None:
                if reads != p["reads"]:
                    bad("the list of reads is not the one the plan makes for this run")
                if entries != [(kind, addr - PL_BASE if kind != st.A_MARK else 0, value) for kind, addr, value in p["entries"]]:
                    bad("the list of accesses is not the one the plan makes for this run")
                if par[19] != p["may_write"]:
                    bad(f"the run's word of what it may write is {par[19]:#010x}; the plan's lists write {p['may_write']:#010x}")
        run["states"] = [x["name"] for x in named] if named else None
    out["run"] = run

    # ---- the finding: every bit of every frame read, by its readings over the states
    finding: dict = {"states_read_whole": len(states), "frames": 0, "bits": {"still": 0, "follow": 0, "follow_inverted": 0, "irregular": 0},
                     "follows": [], "irregular": [], "cells_not_told_apart": [], "cells_not_told_from_another_inverted": []}
    if whole and named is not None:
        made = [i for i, x in enumerate(named) if x["ram"] is not None]   # the states that were written: every site holds alike
        before = [i for i, x in enumerate(named) if x["ram"] is None]     # the state as loaded
        find = run["kind"] == "find"
        rows: dict[tuple, list[int]] = {}                # a row of values over the written states -> the cells that have it
        for cell in range(st.CELLS):
            row = tuple(st.cell(states[i], cell) for i in made)
            if len(set(row)) > 1:
                rows.setdefault(row, []).append(cell)
        if not find:                                     # in part 1 no cell is told from another, and none is meant to be
            finding["cells_not_told_apart"] = sorted(cells for cells in rows.values() if len(cells) > 1)
            if finding["cells_not_told_apart"]:
                bad(f"the states do not tell {len(finding['cells_not_told_apart'])} group(s) of cells apart: a bit could not be said to follow one of them")
        mirrored = sorted(cells[0] for row, cells in rows.items() if tuple(1 - v for v in row) in rows)
        finding["cells_not_told_from_another_inverted"] = mirrored
        if mirrored:                                     # a bit with such readings would follow one cell as it is and another inverted, alike
            bad(f"the states do not tell {len(mirrored)} cell(s) from another cell shown inverted")
        readings: dict[int, list[list[int]]] = {}        # address -> one frame for each state
        for s in range(n_states):
            for k, (far, m) in enumerate(reads):
                for j, frame in enumerate(recs[2 + s * n_list + k]["frames"]):
                    readings.setdefault(far + j, []).append(frame)
        for far in sorted(readings):
            frames = readings[far]
            if len(frames) != n_states:
                bad(f"{far:#010x} has {len(frames)} reading(s) for {n_states} state(s)"); continue
            finding["frames"] += 1
            for w in range(FRAME):
                ws = [frame[w] for frame in frames]
                moved = 0
                for x in ws[1:]:
                    moved |= x ^ ws[0]
                finding["bits"]["still"] += 32 - bin(moved).count("1")
                if not moved:
                    continue
                entry: dict = {"far": f"{far:#010x}", "word": w, "bits": [], "inverted": []}
                beside: list[int] = []                   # for each bit that follows: its cell, or in part 1 what it read as loaded
                for b in range(32):
                    if not moved >> b & 1:
                        continue
                    every = tuple(x >> b & 1 for x in ws)
                    row = tuple(every[i] for i in made)
                    for inverted, key in ((False, row), (True, tuple(1 - v for v in row))):
                        cells = rows.get(key, [])
                        if len(cells) == 1 or (cells and find):
                            finding["bits"]["follow_inverted" if inverted else "follow"] += 1
                            entry["bits"].append(b)
                            beside.append(every[before[0]] if find else cells[0])
                            if inverted:
                                entry["inverted"].append(b)
                            break
                    else:
                        finding["bits"]["irregular"] += 1
                        finding["irregular"].append({"far": f"{far:#010x}", "word": w, "bit": b, "readings": "".join(str(v) for v in every)})
                if entry["bits"]:
                    entry["as_loaded" if find else "cells"] = beside
                    finding["follows"].append(entry)
        if finding["bits"]["irregular"]:
            bad(f"{finding['bits']['irregular']} bit(s) changed and follow no cell of the memories: irregular")
    out["finding"] = finding

    if status != 1:
        bad(f"the run did not complete: status {status:#x}" + (f" ({PL_CODES[status & 0xFF]})" if status & 0xF00 == 0xA00 and status & 0xFF in PL_CODES else ""))
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def places(follows: list[dict]) -> dict[tuple[int, int, int], tuple[int, bool]]:
    """The bits that follow, a place at a time: (frame address, word, bit) -> (what stands beside it — its cell, or in
    part 1 what it read as loaded —, inverted?)."""
    out: dict[tuple[int, int, int], tuple[int, bool]] = {}
    for e in follows:
        beside = e["cells"] if "cells" in e else e["as_loaded"]
        for b, x in zip(e["bits"], beside):
            out[(int(e["far"], 16), e["word"], b)] = (x, b in e["inverted"])
    return out


def judge(words: list[int], known: dict | None, planned: list[int]) -> dict:
    """`planned`: the 32 words of the parameter block, after them the words of the list of reads, after them the words
    of the list of accesses. `known`: the facts of the probe design s2b and, under "census", the census; for a run of
    part 2 also, under "candidates", what part 1 found."""
    return s2_3_judge.judge(words, known, planned, rest=design_side)


def layout_hdr(kind: str) -> int:
    """Where the records begin in the result of a run of that kind: the header, the PL block, and a log with room for
    the identification and every access of the run's list. The list's length depends on the states and the design's
    registers alone, so every run of a kind has the same."""
    design = json.loads(st.DESIGN.read_text())
    states = {"find": st.find_run, "code": st.code_run, "singles": lambda: st.single_run(0)}[kind]()
    return HDR0 + FIXED + 2 * len(st9.planned_log(st.accesses(states, design), design))


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[2] not in SETS or len(argv) != (4 if argv[2] in TAKES_A_SHARE else 3) or not all(x.isdigit() for x in argv[3:]):
        print(__doc__); return 2
    import s1a_run
    stage = SETS[argv[2]]
    try:
        exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), int(argv[3]) if len(argv) == 4 else None)
    except ValueError as e:
        print(f"no plan for that run: {e}"); return 2
    words = s2_3_judge.load(Path(argv[1]))
    if words is None:
        print("the result is not a whole number of words"); return 2
    verdict = judge(words, s1a_run.known_for(stage), s1a_run.planned_words(exp))
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

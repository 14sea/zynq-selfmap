#!/usr/bin/env python3
"""Judge the result of a run of S2.4 — docs/s2_plan.md, sections 37 and 38.

    s2_4_judge.py <result.bin> find <share>       a run of part 1: one share of block type 0 in three states
    s2_4_judge.py <result.bin> code               the code run
    s2_4_judge.py <result.bin> singles <run>      a run of the singles
    s2_4_judge.py <result.bin> pairs              the run of the pairs

A run of S2.4 is a run of stage 9, the stage S2.3 was made with, and everything a run of that stage is held to
whatever its states are is judged by the judge of S2.3 (s2_3_judge.judge, which this one calls): the header, the
gates, every record from its raw words, the streams, the status after every read and the clearing of bit 5, the log
of accesses against the list, the schedule and what it implies for the header. One thing of that judge does not hold
here and is left out there for a step that shifts: a write to the shift registers' data is no fault.

What is judged here is the design's side of this step, from the log and from nothing else:

  * What the four shift registers hold is worked out again from the log — from what the design loads and every shift
    the log has, in order — and never taken from the plan. Every reading of an output is held to that. In every state
    whose frames were read, all 32 outputs were read before the frames and after them — and so read the same, each
    being held to what the shifts give and no shift lying between: reading configuration memory did not disturb them.
  * The RAM is never written; wherever it was read it read zero, and it was read at all 64 addresses before the first
    state's frames and after the last state's.
  * The counter went on over every state's frames. The design's count is the shifts the log has, in its high half,
    and no write to the RAM.
  * Which run of the step it is, is found by the states the registers read back as — of part 1, of the code run, of
    a run of the singles — and both lists and the word of what the run may write are held to the plan of that run.

The finding: every bit of every frame read, by its readings over the states. A bit is still; or it follows a cell —
it reads as that cell holds in every state — as it is or inverted; or it is irregular. In a run of part 1 every cell
holds the same in a state, so a bit that follows follows them all alike, and no cell is named: those bits are the
candidates. A run with an irregular bit fails.

**What a bit follows is asked over the states that were made by shifts.** A run of part 2 begins with the registers
as loaded, nothing shifted yet. The frames S2.2 stored — the registers as loaded, never shifted — have, at one place
of each register, a one whatever the register's first output was loaded with, where after shifts (part 1) that place
follows inverted (section 42). So a bit that follows a cell over every shifted state may read otherwise in the state
before any shift than that cell's loaded content gives: it is then set down ("otherwise_as_loaded") and the run does
not fail for it. Only a bit that follows a cell may: one that is the same in every shifted state and another before
any shift follows nothing, and is irregular.

No database is read and nothing is graded. Nothing here is general knowledge of the device family."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s2_2_shares  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_3_states as st9  # noqa: E402
import s2_4_states as st  # noqa: E402
from s2_3_judge import CTL0_BITS, ERR_MASK, FIXED, FRAME, HDR0, PCFG_DONE, PL_BASE, PL_CODES, REC, RESULT_MAX_WORDS, STAGE  # noqa: E402,F401

SETS = {"find": "s2_4f", "code": "s2_4c", "singles": "s2_4s", "pairs": "s2_4p"}   # the kinds of run, each with its set in the run script
TAKES_A_SHARE = ("find", "singles")                    # of which these are one run of several


def runs_of_the_step(loaded: list[int]) -> list[tuple[str, int | None, list[dict]]]:
    """Every run the step has, by its states: (kind, which run of that kind — None where the states do not say, the
    states). A run of part 1 has the same states whichever share it reads."""
    return ([("find", None, st.find_run()), ("code", None, st.code_run(loaded))]
            + [("singles", r, st.single_run(loaded, r)) for r in range(st.SINGLE_RUNS)] + [("pairs", None, st.pairs_run(loaded))])


def design_side(c: dict) -> dict:
    """The rest of the judging, given what the stage's judge found (s2_3_judge.judge, `rest`)."""
    out, known, par, log, cuts, recs = c["out"], c["known"], c["par"], c["log"], c["cuts"], c["recs"]
    status, anomalies, plb, reads, entries = c["status"], c["anomalies"], c["plb"], c["reads"], c["entries"]
    passes_made, n_states, n_list = c["passes_made"], c["n_states"], c["n_list"]
    bad = out["problems"].append

    # ---- what the design said of itself, from the log and only as far as it goes
    reg = st9.registers(known) if known and "registers" in known else None
    loaded = st9.srl_words(known) if known and "srl" in known else None
    pl: dict = {"accesses": len(log), "code": f"{plb[2]:#x}", "says": PL_CODES.get(plb[2], "unknown"), "passes_the_shift_registers_held_through": 0}
    if log:
        pl["id"] = f"{log[0][1]:#010x}"
    states: list[list[int]] = []                         # for every state whose two stretches were walked whole: what the four held, 32 words
    if reg is None or loaded is None:
        bad("the design's registers and what it loads into its shift registers were not given: what the log says of them cannot be read")
    else:
        for at, (word, _) in enumerate(log):             # wherever the run ended: no access of the whole log may be a write to the RAM
            if word & ~3 == reg["RAM_DATA"] and word & 1:
                bad(f"PL access {at}: a write to the RAM, which this step never writes")
        held = list(loaded)                              # the model: what the four hold, worked out from the log alone
        shifts = ram_read = 0
        srl_at = ram_at = None
        counters: list[str] = []
        held_words: list[list[str]] = []
        for s in range(min(passes_made, n_states)):
            seen: list[dict[int, int]] = [{}, {}]        # before the frames, after them: output -> what it read
            count: list[list[int]] = [[], []]
            ram_seen: list[set[int]] = [set(), set()]
            counted: list[int] = []
            ok = True
            for side, (b, e) in enumerate((cuts[2 * s], cuts[2 * s + 1])):
                for at in range(b, e):
                    word, value = log[at]
                    addr, write = word & ~3, bool(word & 1)
                    if addr == reg["SRL_DATA"] and write:
                        if side:
                            bad(f"PL access {at}: a shift after the frames of state {s} were read and before its end"); ok = False
                        held = st.shifted(held, value); shifts += 1
                    elif addr == reg["SRL_ADDR"] and write:
                        srl_at = value
                    elif addr == reg["SRL_DATA"]:
                        if srl_at is None or srl_at >= st.DEPTH:
                            bad(f"PL access {at}: an output of the shift registers read at no address of theirs"); ok = False
                        elif value != held[srl_at]:
                            bad(f"PL access {at}: output {srl_at} of the shift registers read {value:#x}; by the shifts of the log it holds {held[srl_at]:#x}"); ok = False
                        else:
                            seen[side][srl_at] = value
                    elif addr == reg["RAM_ADDR"] and write:
                        ram_at = value
                    elif addr == reg["RAM_DATA"]:
                        if write:
                            ok = False                   # said above, of the whole log
                        elif value != 0:
                            bad(f"PL access {at}: the RAM read {value:#x} at address {ram_at}; it was never written and is loaded with zero"); ok = False
                        elif ram_at is not None:
                            ram_seen[side].add(ram_at); ram_read += 1
                    elif addr == reg["COUNT"] and not write:
                        count[side].append(value)
                    elif addr == reg["WRITES"] and not write:
                        counted.append(value)
            if not ok:
                break
            if sorted(seen[0]) != list(range(st.DEPTH)) or sorted(seen[1]) != list(range(st.DEPTH)):
                bad(f"state {s}: the shift registers were not read at every address before the frames and after them"); break
            if not count[0] or not count[1]:
                bad(f"state {s}: the counter was not read before the frames and after them")
            else:
                counters += [f"{count[0][-1]:#010x}", f"{count[1][0]:#010x}"]
                if count[0][-1] == count[1][0]:
                    bad(f"state {s}: the counter read {count[0][-1]:#010x} before the frames and after them: the design's clock did not go on")
            if not counted:
                bad(f"state {s}: the design's count of writes was not read after the frames")
            elif counted[-1] != shifts << 16:
                bad(f"state {s}: the design counted {counted[-1] & 0xFFFF} write(s) and {counted[-1] >> 16} shift(s); the log has no write to the RAM and {shifts} shift(s)")
            else:
                pl["writes_counted"] = {"ram": counted[-1] & 0xFFFF, "shifts": counted[-1] >> 16}
            if s == 0 and ram_seen[0] != set(range(st.RAM_DEPTH)):
                bad("the RAM was not read at every address before the first state's frames")
            if s == n_states - 1 and ram_seen[1] != set(range(st.RAM_DEPTH)):
                bad("the RAM was not read at every address after the last state's frames")
            states.append([seen[0][a] for a in range(st.DEPTH)])
            held_words.append([f"{sum(((seen[0][a] >> k) & 1) << a for a in range(st.DEPTH)):#010x}" for k in range(st.REGISTERS)])
        pl["passes_the_shift_registers_held_through"] = len(states)
        pl["shift_registers_held"] = held_words
        pl["ram_readings_all_zero"] = ram_read
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
        for kind, which, its_states in runs_of_the_step(loaded):
            if states == [x["srl"] for x in its_states]:
                run, named = {"kind": kind, "share": which}, its_states
        if named is None:
            bad("the states the shift registers read back as are not those of a run of part 1, of the code run, of a run of the singles or of the pairs")
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
        made = [i for i, x in enumerate(named) if x["shifted"]]          # the states made by shifts: what a bit follows is asked over these
        before = [i for i, x in enumerate(named) if not x["shifted"]]    # the registers as loaded, nothing shifted yet
        if before:                                       # said only of a run that has such a state: the code run. A run of part 1 has none, and
            finding["otherwise_as_loaded"] = []          # its verdict is what it was when part 1 was stored
        rows: dict[tuple, list[int]] = {}                # a row of values over the shifted states -> the cells that have it
        for cell in range(st.CELLS):
            row = tuple(st.cell(states[i], cell) for i in made)
            if len(set(row)) > 1:
                rows.setdefault(row, []).append(cell)
        if run["kind"] != "find":                        # in part 1 no cell is told from another, and none is meant to be
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
                for b in range(32):
                    if not moved >> b & 1:
                        continue
                    every = tuple(x >> b & 1 for x in ws)
                    row = tuple(every[i] for i in made)
                    where = {"far": f"{far:#010x}", "word": w, "bit": b}
                    for inverted, key in ((False, row), (True, tuple(1 - v for v in row))):
                        cells = rows.get(key, [])
                        if len(cells) == 1 or (cells and run["kind"] == "find"):
                            finding["bits"]["follow_inverted" if inverted else "follow"] += 1
                            if run["kind"] == "find":
                                finding["follows"].append(dict(where, inverted=inverted))
                            else:
                                finding["follows"].append(dict(where, cell=cells[0], register=cells[0] // st.DEPTH, output=cells[0] % st.DEPTH, inverted=inverted))
                                for i in before:         # before any shift: does it read as that cell's loaded content gives?
                                    gives = st.cell(states[i], cells[0]) ^ int(inverted)
                                    if every[i] != gives:
                                        finding["otherwise_as_loaded"].append(dict(where, cell=cells[0], inverted=inverted, state=i, reads=every[i], the_cell_gives=gives))
                            break
                    else:
                        finding["bits"]["irregular"] += 1
                        finding["irregular"].append(dict(where, readings="".join(str(v) for v in every)))
        if finding["bits"]["irregular"]:
            bad(f"{finding['bits']['irregular']} bit(s) changed and follow no cell of the shift registers: irregular")
    out["finding"] = finding

    if status != 1:
        bad(f"the run did not complete: status {status:#x}" + (f" ({PL_CODES[status & 0xFF]})" if status & 0xF00 == 0xA00 and status & 0xFF in PL_CODES else ""))
    if anomalies:
        bad(f"{anomalies} anomalous read(s)")
    out["verdict"] = "PASS" if not out["problems"] else "FAIL"
    return out


def judge(words: list[int], known: dict | None, planned: list[int]) -> dict:
    """`planned`: the 32 words of the parameter block, after them the words of the list of reads, after them the words
    of the list of accesses. `known`: the facts of the probe design and, under "census", the census; for a run of part
    2 also, under "candidates", what part 1 found."""
    return s2_3_judge.judge(words, known, planned, rest=design_side)


def layout_hdr(kind: str) -> int:
    """Where the records begin in the result of a run of that kind: the header, the PL block, and a log with room for
    the identification and every access of the run's list. The list's length depends on the states and the design's
    registers alone, so every run of a kind has the same."""
    design = json.loads(st.DESIGN.read_text())
    loaded = st9.srl_words(design)
    states = {"find": st.find_run, "code": lambda: st.code_run(loaded), "singles": lambda: st.single_run(loaded, 0), "pairs": lambda: st.pairs_run(loaded)}[kind]()
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

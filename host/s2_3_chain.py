#!/usr/bin/env python3
"""S2.3: which bit is which cell, as a chain of five runs — docs/s2_plan.md, sections 29 and 30.

    s2_3_chain.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s2_3_chain.py --dir DIR --go            go on with it on the board, run after run, until it is complete, held or halted

The runs: DIR/run00 is the code run (the set s2_3c); DIR/run01 to DIR/run04 are the four runs of the singles (the
set s2_3s, --share 0 to 3). The state of the chain is the stored runs and the stored table, and nothing else. Each
run is taken from its files and judged again from its raw words, against the plan of that run, before it is relied
on; what a stored run must show of the image, the design and the lists it was made with is what the chain of S2.2
asks, and one thing more: the list of accesses.

**The code run is made alone.** When it is a passing run it is closed into the table (s2_3_table.close_code): every
cell of the RAM has exactly one bit, and the bits are the places S2.2 found. The table is written to DIR/table/ —
once; a table that is there is held to what the code run's verdict gives now, and is never written over. If there is
no table, the chain halts and says which of the outcomes the plan named it is: **no single is run**. Nor is one run
where DIR/table is there and the table is not in it as a plain file: the driver would never write it there, and the
chain halts (review of 5936a8e).

**No single is run before the code run and the table are committed to git as they stand** (DIR/run00 and DIR/table).
Until then the chain is "held", which is not a halt.

A run of the singles is held to the table (s2_3_table.hold_singles): for each of its 64 cells, with that cell alone
set, exactly the place the table has for it differs from the base. A contradiction halts the chain there; what the
other singles of that run said is in the chain's file. So does a run in which CTL0 read otherwise than in the code
run: each run's judge holds that register to itself only, and the table and its confirmations are one finding.
And the code run itself is held to what CTL0 read in the runs of S2.2 (known["ctl0_in_s2_2"], from that chain's
own file): the candidates this step is built on were found under that word, and a code run made under another
halts the chain there, before a table is taken from it (section 34). The whole word is compared, as the device
gave it; no bit of it is given a meaning here.

Anything else halts it too, and nothing is run again: a run directory that does not hold a passing run stays where it
is until someone has looked and moved it.

It is complete when all five runs are stored and every cell is confirmed. Then the description is written
(DIR/ram_map.json, schemas/ram_map_v1.schema.json): closed-book, 256 entries, each with its place, its confidence
and the records it rests on.

Nothing here knows where a cell lies, or what an address word means.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1a_run  # noqa: E402
import s2_2_chain  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_3_states  # noqa: E402
import s2_3_table  # noqa: E402
from s2_2_chain import KEPT_IMAGE, RUN_DIR, came_up_fresh, committed, crc, declared, ready  # noqa: E402,F401

CODE, SINGLES = "s2_3c", "s2_3s"
RUNS = 1 + s2_3_states.SINGLE_RUNS                    # the code run, and the runs of the singles
TABLE_DIR, TABLE = "table", "table.json"
BUILD_RECORD = ROOT / "pl" / "s2a" / "build.json"


def named(p: Path) -> bool:
    """Something has this name, whatever it is (a link that leads nowhere as well)."""
    return p.is_symlink() or p.exists()


def run_of(k: int) -> tuple[str, int | None]:
    """Which set run k of the chain is of, and which share."""
    return (CODE, None) if k == 0 else (SINGLES, k - 1)


def bound(rec: dict, d: Path, exp: dict, held: dict) -> list[str]:
    """Why a run's record does not show the run to have been made with what the set declares and the plan gives: what
    the chain of S2.2 asks — the image, the design, the list of reads — and the list of accesses the same way."""
    problems = s2_2_chain.bound(rec, d, exp, held)
    if problems == ["the run record has no list of steps"] or (problems and problems[0].startswith("the run record does not show one load")):
        return problems
    steps = rec["steps"]
    cmds = [s.get("cmd") if isinstance(s.get("cmd"), str) else "" for s in steps]
    at_start = cmds.index(f"go {s1a_run.IMG_ADDR:08x}")
    planned = s1a_run.acc_bytes(exp)
    acc_cmd = f"crc32 {s1a_run.ACC_ADDR:08x} {len(planned):x}"
    said = [x for x in (s1a_run.whole(acc_cmd, s.get("reply") if isinstance(s.get("reply"), str) else "") for s in steps if s.get("cmd") == acc_cmd) if x is not None]
    before = [x for x in (s1a_run.whole(acc_cmd, s.get("reply") if isinstance(s.get("reply"), str) else "") for s in steps[:at_start] if s.get("cmd") == acc_cmd)
              if x is not None]
    if not before or set(said) != {crc(planned)}:
        problems.append(f"the run record does not show the list of accesses planned for the run (crc32 {crc(planned)}) in RAM before the start: {said}")
    try:
        kept = (d / "acc.bin").read_bytes()
    except OSError:
        kept = None
    if kept != planned:
        problems.append("the list of accesses kept beside the run is not the list planned for it" if kept is not None else "no list of accesses is kept beside the run")
    return problems


def refusal(k: int, out: Path) -> str:
    """What the run script says if it would refuse run k of the chain into this directory, from its own dry run."""
    stage, share = run_of(k)
    r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, *([] if share is None else ["--share", str(share)]),
                        "--out", str(out), "--dry-run"], capture_output=True, text=True)
    return "" if r.returncode == 0 else ((r.stdout + r.stderr).strip().splitlines() or ["it ended with a code and said nothing"])[-1]


def read_run(d: Path, k: int, exp: dict, known: dict, held: dict) -> dict:
    """One stored run: what the run script recorded, and the result judged again from its raw words against the plan of
    run k (`exp`: its set with the plan's lists). Everything found wanting is listed in "problems"; the verdict is
    kept under "verdict" for what is made of it afterwards."""
    stage, share = run_of(k)
    out: dict = {"dir": d.name, "kind": s1a_run.PLANS_AT_RUN_TIME[stage], "share": share, "problems": []}
    bad = out["problems"].append
    try:
        rec = json.loads((d / "run.json").read_text())
    except (OSError, ValueError):
        bad("there is no run record"); return out
    if not isinstance(rec, dict):
        bad("the run record is not a record"); return out
    if rec.get("stage") != stage:
        bad(f"the run record is of stage {rec.get('stage')}, not {stage}")
    plan = rec.get("plan") if isinstance(rec.get("plan"), dict) else {}
    if (plan.get("kind"), plan.get("share")) != (out["kind"], share):
        bad(f"the run is {plan.get('kind')}, share {plan.get('share')}; the chain plans {out['kind']}, share {share} for it")
    for p in bound(rec, d, exp, held):
        bad(p)
    if rec.get("restart"):
        bad(f"a reply showed an exception or a restart: {rec['restart']}")
    if not rec.get("went"):
        bad("the prober was not started")
    if rec.get("stop"):
        bad(f"the run script stopped: {rec['stop']}")
    if rec.get("verdict") != "PASS":
        bad(f"the run script's verdict is {rec.get('verdict')}: {rec.get('problems')}")
    if not rec.get("card_verified"):
        bad("the card copy was not verified")
    try:
        raw = (d / "result.bin").read_bytes()
    except OSError:
        bad("there is no stored result"); return out
    if len(raw) % 4 or crc(raw) != rec.get("board_crc32"):
        bad("the stored result is not the one whose checksum the board gave"); return out
    out["result_sha256"] = hashlib.sha256(raw).hexdigest()
    v = json.loads(json.dumps(s2_3_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1a_run.planned_words(exp))))
    out["judge"] = v["verdict"]
    if v["verdict"] != "PASS":
        bad(f"the judge says {v['verdict']}: {v['problems'][:3]}")
    try:
        stored = json.loads((d / "verdict.json").read_text())
    except (OSError, ValueError):
        stored = None
    if stored != v:
        bad("the verdict stored beside the result is not what the judge says of the stored result")
    run = v.get("run") or {}
    if v["verdict"] == "PASS" and (run.get("kind"), run.get("share")) != (out["kind"], share):
        bad(f"the result is of {run.get('kind')}, share {run.get('share')}: not the run the chain plans here")
    f = v.get("finding", {})
    out.update(states=exp["plan"]["states"], reads=exp["plan"]["reads"], frames=f.get("frames"), bits=f.get("bits"),
               ctl0=(v.get("registers", {}).get("CTL0", {}) or {}).get("value"),
               bit_5_shown_after_records=(v.get("bit_5") or {}).get("shown_after_records", []),
               bit_5_still_set_after_clearing=(v.get("bit_5") or {}).get("still_set_after_clearing", []))
    out["verdict"] = v
    return out


def table_file(closing: dict, run: dict, known: dict) -> dict:
    """The table as it is written out when the code run is closed: confidence 1, from the code states alone."""
    return {"schema": "s2_3_table", "schema_version": 1, "label": "closed-book",
            "what": "which bit of configuration memory follows which cell of the probe design's RAM, decoded from the code run of S2.3 "
                    "(docs/s2_plan.md, section 29) and from nothing else: no single has confirmed any of it. cell = 64 x memory + address, "
                    "from the design's side.",
            "design": known.get("name"), "outcome": closing["outcome"], "cells": closing["cells"], "inverted": closing["inverted"],
            "code_run": {"dir": run["dir"], "result_sha256": run["result_sha256"]}, "table": closing["table"]}


def assess(root: Path, bases: dict, known: dict) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the next run), "complete", "halted" (with the reasons). `bases`: the two sets as the tests
    wrote them, by name."""
    there = sorted(root.iterdir()) if root.is_dir() else []
    names = sorted(p.name for p in there if p.is_dir() and not p.is_symlink() and RUN_DIR.match(p.name))
    out: dict = {"step": "s2_3", "runs_planned": RUNS, "runs": [],
                 "set_aside": sorted(p.name for p in there if p.is_dir() and not RUN_DIR.match(p.name) and p.name != TABLE_DIR)}

    def halted(*why: str) -> dict:
        out.update(state="halted", why=list(why)); return out

    if root.is_dir() and (root / "ram_map.json").exists():
        out["ram_map_file"] = "there"                    # the driver writes it when the chain is complete and takes it away when it is not
    taken = [p.name for p in there if RUN_DIR.match(p.name) and p.name not in names]
    if taken:
        return halted(f"what has the name of a run and is not a directory: {taken}")
    if names != [f"run{k:02d}" for k in range(len(names))]:
        return halted(f"the run directories are not run00, run01, ... without a gap: {names}")
    if len(names) > RUNS:
        return halted(f"{len(names)} run directories for {RUNS} runs")
    if bases[CODE].get("image_sha256") != bases[SINGLES].get("image_sha256") or bases[CODE].get("pl_design") != bases[SINGLES].get("pl_design"):
        return halted("the two sets of the step do not declare the same image and the same design")
    held = declared(root, bases[CODE])
    if held["problems"]:
        return halted(*held["problems"])
    out["made_with"] = {k: v for k, v in held.items() if k != "problems"}
    table = None
    stored_table = root / TABLE_DIR / TABLE
    if named(root / TABLE_DIR) and ((root / TABLE_DIR).is_symlink() or not (root / TABLE_DIR).is_dir()):
        # asked whenever the chain is looked at, also when it is complete: git is asked only before a single (review of ce77a49)
        return halted(f"what has the name {TABLE_DIR} is not a directory of the chain's own (a link, or a file)")
    if named(root / TABLE_DIR) and not names:
        return halted("a table is stored and no code run")
    for k, name in enumerate(names):
        stage, share = run_of(k)
        try:
            exp = s1a_run.with_plan(stage, bases[stage], share, known)
        except ValueError as e:
            return halted(f"no plan can be made for {name}: {e}")
        r = read_run(root / name, k, exp, known, held)
        v = r.pop("verdict", None)
        out["runs"].append(r)
        if not r["problems"] and k == 0 and (not known.get("ctl0_in_s2_2") or r.get("ctl0") != known["ctl0_in_s2_2"]):
            # asked before the code run is closed: no table is taken from a run made under another CTL0 than S2.2's (section 34)
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in the code run and {known.get('ctl0_in_s2_2')} in the runs of S2.2, in which the candidates were found")
        if not r["problems"] and k == 0:                 # the code run, closed
            closing = s2_3_table.close_code(v, known["candidates"])
            out["closing_of_the_code_run"] = {key: val for key, val in closing.items() if key != "table"}
            if closing["table"] is None:
                r["problems"] += [f"closed without a table — {closing['outcome']}"] + closing["problems"]
            else:
                table = closing["table"]
                out["table"] = table_file(closing, r, known)
                if stored_table.is_file() and not stored_table.is_symlink():
                    try:
                        same = json.loads(stored_table.read_text()) == json.loads(json.dumps(out["table"]))
                    except (OSError, ValueError):
                        same = False
                    if not same:
                        r["problems"].append("the table stored with the chain is not the table the code run's verdict gives")
                elif named(root / TABLE_DIR):            # the driver writes the table only where nothing has that name: it would never come
                    r["problems"].append(f"{TABLE_DIR}/ is stored and the table ({TABLE}) is not in it")
                elif names[1:]:
                    r["problems"].append("singles are stored and no table is")
        if not r["problems"] and k > 0:                  # a run of the singles, held to the table
            hold = s2_3_table.hold_singles(v, table)
            r["confirmed"], r["contradictions"] = hold["confirmed"], hold["contradictions"]
            r["problems"] += hold["problems"]
            r["_for_the_map"] = {"dir": name, "share": share, "result_sha256": r["result_sha256"], "held": hold}
        if not r["problems"] and k > 0 and r.get("ctl0") != out["runs"][0].get("ctl0"):
            # each run's judge holds CTL0 to itself, before and after; that the runs were made under one CTL0 is asked here
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in this run and {out['runs'][0].get('ctl0')} in the code run")
        if r["problems"]:
            r["decision"] = "halt"
            if names[k + 1:]:
                r["problems"].append(f"the run directories after it were not looked at: {names[k + 1:]}")
            return halted(*[f"{name}: {p}" for p in r["problems"]])
        r["decision"] = "go on" if k + 1 < RUNS else "complete"
    if len(names) < RUNS:
        out.update(state="go on", next_run=len(names))
        return out
    confirmed = sorted(n for r in out["runs"][1:] for n in r["confirmed"])
    out["closing"] = {"cells": s2_3_states.CELLS, "confirmed": len(confirmed), "contradictions": 0,
                      "outcome": "1 and 9: the table of the code run, and every cell confirmed by its single",
                      "ctl0": sorted({r["ctl0"] for r in out["runs"] if r.get("ctl0")}), "ctl0_in_s2_2": known.get("ctl0_in_s2_2"),
                      "bit_5": {r["dir"]: r["bit_5_shown_after_records"] for r in out["runs"] if r.get("bit_5_shown_after_records")}}
    if confirmed != list(range(s2_3_states.CELLS)):
        return halted(f"the singles confirm {len(confirmed)} cell(s), not every cell once")
    out["state"] = "complete"
    return out


def brief(a: dict) -> dict:
    """The assessment as it is written beside the runs as chain.json: without the table (which has its own file) and
    without what is kept only to write the description."""
    b = {k: v for k, v in a.items() if k != "table"}
    b["runs"] = [{k: v for k, v in r.items() if k != "_for_the_map"} for r in a["runs"]]
    if "table" in a:
        b["table_sha256"] = hashlib.sha256((json.dumps(a["table"], indent=1) + "\n").encode()).hexdigest()
    return b


def ram_map_file(a: dict, bases: dict, known: dict) -> dict:
    """What a complete chain found, as it is written out."""
    plans = [s2_3_states.plan(s1a_run.PLANS_AT_RUN_TIME[run_of(k)[0]], run_of(k)[1], known, known["census"], known["candidates"]) for k in range(RUNS)]
    code = {"dir": a["runs"][0]["dir"], "result_sha256": a["runs"][0]["result_sha256"], "reads": plans[0]["reads"], "states": plans[0]["states"]}
    singles = [dict(r["_for_the_map"], reads=plans[k]["reads"], states=plans[k]["states"]) for k, r in enumerate(a["runs"]) if k > 0]
    try:
        build = json.loads(BUILD_RECORD.read_text()) if known.get("name") == "s2a" else None
    except (OSError, ValueError):
        build = None
    return s2_3_table.ram_map(known, a["table"]["table"], code, singles, build)


def drive(root: Path, bases: dict, known: dict, runner, max_new: int | None = None, say=lambda *_: None, committed=committed,
          refuses=lambda k, out: "") -> dict:
    """Go on with the chain until it is complete or halts (or `max_new` runs have been added). `runner(k, out)` makes
    run k and leaves its files in the directory `out`. After every run the whole chain is assessed again from what is
    stored. The code run is made alone: a single is started only when `committed` finds nothing wanting in the code
    run's directory and in the table's; and no run at all unless the image the run script will load is the one the
    chain is made with and `refuses(k, out)` — on the board the run script's own dry run — has nothing to say against
    it. Until then the chain is "held", which is not a halt; "blocked" beside it says that a run could not be started."""
    root.mkdir(parents=True, exist_ok=True)
    added = 0
    while True:
        a = assess(root, bases, known)
        if "table" in a and not named(root / TABLE_DIR):         # the code run closed into a table: written once, never over
            (root / TABLE_DIR).mkdir()
            (root / TABLE_DIR / TABLE).write_text(json.dumps(a["table"], indent=1) + "\n")
            say(f"the table written: {TABLE_DIR}/{TABLE}")
        if a["state"] == "complete":
            (root / "ram_map.json").write_text(json.dumps(ram_map_file(a, bases, known), indent=1) + "\n")
            a["ram_map_file"] = "there"
        elif a.pop("ram_map_file", None):                # of an earlier look at these runs, which no longer stands
            (root / "ram_map.json").unlink()
            say("ram_map.json taken away: the chain is not complete as it is stored now")
        (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
        if a["runs"]:
            last = a["runs"][-1]
            bits = last.get("bits") or {}
            say(f"{last['dir']}: {last['kind']}" + ("" if last["share"] is None else f" {last['share']}")
                + f", {bits.get('follow', '?')} bit(s) follow a cell, {bits.get('follow_inverted', '?')} inverted, {bits.get('irregular', '?')} irregular"
                + (f", {len(last['confirmed'])} cell(s) confirmed" if "confirmed" in last else "") + f" — {last['decision']}")
        if a["state"] != "go on" or (max_new is not None and added >= max_new):
            return a
        k = a["next_run"]
        out = root / f"run{k:02d}"
        why, blocked = ready(root, bases[CODE]) or refuses(k, out), True
        if why:
            why = f"nothing was sent: {why}"
        elif a["runs"]:
            why, blocked = committed(root / "run00") or committed(root / TABLE_DIR), False
            if why:
                why = f"no single before the code run and its table are committed: {why}"
        if not why:
            if not a["runs"] and not (root / KEPT_IMAGE).exists():   # the image every run of this chain is to be made with, kept with them
                (root / KEPT_IMAGE).write_bytes(s1a_run.IMAGE.read_bytes())
            try:
                runner(k, out)
            except RuntimeError as e:                    # the runner could not begin (the board did not come up fresh): nothing was run
                why, blocked = str(e), True
        if why:
            a["held"] = why
            if blocked:
                a["blocked"] = True
            (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
            return a
        out.mkdir(exist_ok=True)                         # a run that left nothing behind is a run directory without a record: a halt
        added += 1


def board_runner(root: Path):
    """One run on the board: a U-Boot `reset` (as before every run so far), then the run script."""
    import os
    os.environ["SELFMAP_CONSOLE_LOG"] = str(root / "resets_console.log")
    from uboot_console import UB

    def run(k: int, out: Path) -> None:
        stage, share = run_of(k)
        came_up_fresh(UB, out.name)                      # the reset before the run, as S2.2's chain makes it
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, *([] if share is None else ["--share", str(share)]),
                            "--go", "--out", str(out)], capture_output=True, text=True)
        (root / f"{out.name}.out").write_text(r.stdout + r.stderr)
    return run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-new", type=int, help="add at most this many runs, then stop where the chain stands")
    a = ap.parse_args()
    bases = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in (CODE, SINGLES)}
    known = s1a_run.known_for(CODE)
    if not a.go:
        state = assess(a.dir, bases, known)
    else:
        state = drive(a.dir, bases, known, board_runner(a.dir), max_new=a.max_new, say=lambda line: print(line, flush=True),
                      refuses=lambda k, out: (lambda why: f"the run script refuses the run ({why})" if why else "")(refusal(k, out)))
    print(json.dumps({k: v for k, v in brief(state).items() if k != "runs"}, indent=1))
    if state["state"] != "complete" and state.get("ram_map_file"):
        print("NOTE: a ram_map.json lies beside these runs, and the chain is not complete as it is stored now: it does not stand")
    if state.get("held"):
        print(f"HELD: {state['held']}")
    print(f"{len(state['runs'])} run(s) stored of {state['runs_planned']}; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") and not state.get("blocked") else 1


if __name__ == "__main__":
    sys.exit(main())

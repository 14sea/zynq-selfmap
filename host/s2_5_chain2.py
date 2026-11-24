#!/usr/bin/env python3
"""S2.5, part 2: which place is which cell at every site, as a chain of seventeen runs — docs/s2_plan.md, sections 45
and 46.

    s2_5_chain2.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s2_5_chain2.py --dir DIR --go            go on with it on the board, run after run, until it is complete, held or halted

The runs: DIR/run00 is the code run (the set s2_5c); DIR/run01 to DIR/run16 are the sixteen runs of the singles
(s2_5s, --share 0 to 15). The state of the chain is the stored runs and the stored tables, and nothing else. Each run
is taken from its files and judged again from its raw words, against the plan of that run, before it is relied on;
what a stored run must show of the image, the design and both lists it was made with is what the chain of S2.3 asks.

**What part 1 found is taken the same way.** Part 2 reads two files of part 1's chain — its candidates, with the
memory and the site of each, and its chain.json — and cannot test whose memory a place is, since it writes every site
alike. Before either is used, every stored run of part 1 is judged again from its raw words and both files are held to
what that gives — and what part 2 is then given is what was held, not the files opened a second time
(s2_5_chain.taken_again, asked by the run script of every run and by this command); where they are not, nothing is run
and nothing is assessed. The description names the runs of part 1 as what the site of an entry rests on.

**"Go on" is said only where the next run can be planned.** Each state reads every frame in which part 1 found a
candidate, and the result has room for so many reads; where the next run has no plan the chain is halted and says why,
also when no run is stored yet and it is only asked where it stands.

**The code run is made alone, and held to the CTL0 of part 1's runs**: the candidates it is read over were found under
that word. When it is a passing run it is closed into a table for every site (s2_5_table.close_code): what part 1 says
of a place — whose memory, by the word it was loaded with — and what the code run says — which cell — held against
each other. The tables are written to DIR/table/ — once; tables that are there are held to what the code run's
verdict gives now, and are never written over. If a site has no table the chain halts and says which: **no single is
run**. Nor is one run where DIR/table is there and the tables are not in it as a plain file.

**No single is run before the code run and the tables are committed to git as they stand** (DIR/run00 and DIR/table).
Until then the chain is "held", which is not a halt.

A run of the singles is held to the tables (s2_5_table.hold_singles): for each of its sixteen cells, with that cell
alone set at every site, exactly the places the tables have for it — one at every site — differ from the base. A
contradiction halts the chain there. So does a run in which CTL0 read otherwise than in the code run.

When all seventeen are stored and every cell is confirmed the chain is complete and writes DIR/ram_map.json, the
description (schemas/ram_map_v2.schema.json), and DIR/rule.json, the rule the probed sites obey (s2_5_rule). Anything
else halts it, and nothing is run again: a run directory that does not hold a passing run stays where it is until the
owner has it set aside. No database is read and nothing is graded."""
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
import s2_5_judge  # noqa: E402
import s2_5_rule  # noqa: E402
import s2_5_states  # noqa: E402
import s2_5_table  # noqa: E402
from s2_2_chain import KEPT_IMAGE, RUN_DIR, came_up_fresh, committed, crc, declared, ready  # noqa: E402,F401
from s2_3_chain import bound, named  # noqa: E402,F401

CODE, SINGLES = "s2_5c", "s2_5s"
RUNS = 1 + s2_5_states.SINGLE_RUNS                    # the code run, and the runs of the singles
TABLE_DIR, TABLE = "table", "table.json"
BUILD_RECORD = ROOT / "pl" / "s2b" / "build.json"
ALL_SITES = ROOT / "pl" / "s2a" / "slicem_sites.txt"  # the sites of the kind the memories lie on, as Vivado listed them for the part


def run_of(k: int) -> tuple[str, int | None]:
    """Which set run k of the chain is of, and which share."""
    return (CODE, None) if k == 0 else (SINGLES, k - 1)


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
    v = json.loads(json.dumps(s2_5_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1a_run.planned_words(exp))))
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


def assess(root: Path, bases: dict, known: dict) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the next run), "complete", "halted" (with the reasons). `bases`: the two sets as the tests
    wrote them, by stage."""
    there = sorted(root.iterdir()) if root.is_dir() else []
    names = sorted(p.name for p in there if p.is_dir() and not p.is_symlink() and RUN_DIR.match(p.name))
    out: dict = {"step": "s2_5, part 2", "runs_planned": RUNS, "runs": [],
                 "set_aside": sorted(p.name for p in there if p.is_dir() and not RUN_DIR.match(p.name) and p.name != TABLE_DIR)}

    def halted(*why: str) -> dict:
        out.update(state="halted", why=list(why)); return out

    if root.is_dir() and ((root / "ram_map.json").exists() or (root / "rule.json").exists()):
        out["ram_map_file"] = "there"                    # the driver writes both when the chain is complete and takes them away when it is not
    taken = [p.name for p in there if RUN_DIR.match(p.name) and p.name not in names]
    if taken:
        return halted(f"what has the name of a run and is not a directory: {taken}")
    if names != [f"run{k:02d}" for k in range(len(names))]:
        return halted(f"the run directories are not run00, run01, ... without a gap: {names}")
    if len(names) > RUNS:
        return halted(f"{len(names)} run directories for {RUNS} runs")
    if len({(b.get("image_sha256"), json.dumps(b.get("pl_design"), sort_keys=True)) for b in bases.values()}) != 1 or sorted(bases) != sorted((CODE, SINGLES)):
        return halted("the two sets of the step do not declare the same image and the same design")
    held = declared(root, bases[CODE])
    if held["problems"]:
        return halted(*held["problems"])
    out["made_with"] = {k: v for k, v in held.items() if k != "problems"}
    tables = None
    stored_table = root / TABLE_DIR / TABLE
    if named(root / TABLE_DIR) and ((root / TABLE_DIR).is_symlink() or not (root / TABLE_DIR).is_dir()):
        return halted(f"what has the name {TABLE_DIR} is not a directory of the chain's own (a link, or a file)")
    if named(root / TABLE_DIR) and not names:
        return halted("tables are stored and no code run")
    for k, name in enumerate(names):
        stage, share = run_of(k)
        try:
            exp = s1a_run.with_plan(stage, bases[stage], share, known)
        except ValueError as e:
            return halted(f"no plan can be made for {name}: {e}")
        r = read_run(root / name, k, exp, known, held)
        v = r.pop("verdict", None)
        out["runs"].append(r)
        if not r["problems"] and k == 0 and (not known.get("ctl0_in_part_1") or r.get("ctl0") != known["ctl0_in_part_1"]):
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in the code run and {known.get('ctl0_in_part_1')} in the runs of part 1, in which the candidates were found")
        if not r["problems"] and k > 0 and r.get("ctl0") != out["runs"][0].get("ctl0"):
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in this run and {out['runs'][0].get('ctl0')} in the code run")
        if not r["problems"] and k == 0:                 # the code run, closed
            closing = s2_5_table.close_code(v, known["candidates"], known)
            out["closing_of_the_code_run"] = {key: val for key, val in closing.items() if key != "tables"}
            if closing["tables"] is None:
                r["problems"] += [f"closed without a table for every site — {closing['outcome']}"] + closing["problems"]
            else:
                tables = closing["tables"]
                out["table"] = s2_5_table.table_file(closing, r, known)
                if stored_table.is_file() and not stored_table.is_symlink():
                    try:
                        same = json.loads(stored_table.read_text()) == json.loads(json.dumps(out["table"]))
                    except (OSError, ValueError):
                        same = False
                    if not same:
                        r["problems"].append("the tables stored with the chain are not the tables the code run's verdict gives")
                elif named(root / TABLE_DIR):
                    r["problems"].append(f"{TABLE_DIR}/ is stored and the tables ({TABLE}) are not in it")
                elif names[1:]:
                    r["problems"].append("singles are stored and no table is")
        if not r["problems"] and k > 0:                  # a run of the singles, held to the tables
            hold = s2_5_table.hold_singles(v, tables)
            r["confirmed"], r["contradictions"] = hold["confirmed"], hold["contradictions"]
            r["problems"] += hold["problems"]
            r["_for_the_map"] = {"dir": name, "share": share, "result_sha256": r["result_sha256"], "held": hold}
        if r["problems"]:
            r["decision"] = "halt"
            if names[k + 1:]:
                r["problems"].append(f"the run directories after it were not looked at: {names[k + 1:]}")
            return halted(*[f"{name}: {p}" for p in r["problems"]])
        r["decision"] = "go on" if k + 1 < RUNS else "complete"
    if len(names) < RUNS:                            # "go on" is said only of a chain whose next run can be planned (review of b8f014a: over
        stage, share = run_of(len(names))            # frames that leave the result no room, the chain with no run stored said "go on")
        try:
            s1a_run.with_plan(stage, bases[stage], share, known)
        except ValueError as e:
            return halted(f"no plan can be made for the next run, run{len(names):02d}: {e}")
        out.update(state="go on", next_run=len(names))
        return out
    confirmed = sorted(n for r in out["runs"][1:] for n in r["confirmed"])
    out["closing"] = {"sites": len(tables), "cells_a_site": s2_5_states.CELLS, "places": len(tables) * s2_5_states.CELLS, "cells_confirmed_at_every_site": len(confirmed),
                      "contradictions": 0, "outcome": "7 and 9: a table for every site, and every cell confirmed at every site by its single",
                      "ctl0": sorted({r["ctl0"] for r in out["runs"] if r.get("ctl0")}), "ctl0_in_part_1": known.get("ctl0_in_part_1"),
                      "bit_5": {r["dir"]: r["bit_5_shown_after_records"] for r in out["runs"] if r.get("bit_5_shown_after_records")}}
    if confirmed != list(range(s2_5_states.CELLS)):
        return halted(f"the singles confirm {len(confirmed)} cell(s), not every cell once")
    out["state"] = "complete"
    return out


def brief(a: dict) -> dict:
    """The assessment as it is written beside the runs as chain.json: without the tables (which have their own file)
    and without what is kept only to write the description."""
    b = {k: v for k, v in a.items() if k != "table"}
    b["runs"] = [{k: v for k, v in r.items() if k != "_for_the_map"} for r in a["runs"]]
    if "table" in a:
        b["table_sha256"] = hashlib.sha256((json.dumps(a["table"], indent=1) + "\n").encode()).hexdigest()
    return b


def ram_map_file(a: dict, bases: dict, known: dict) -> dict:
    """What a complete chain found, as it is written out."""
    plans = [s2_5_states.plan(s1a_run.PLANS_AT_RUN_TIME[run_of(k)[0]], run_of(k)[1], known, known["census"], known["candidates"]) for k in range(RUNS)]
    code = {"dir": a["runs"][0]["dir"], "result_sha256": a["runs"][0]["result_sha256"], "reads": plans[0]["reads"], "states": plans[0]["states"]}
    singles = [dict(r["_for_the_map"], reads=plans[k]["reads"], states=plans[k]["states"]) for k, r in enumerate(a["runs"]) if k > 0]
    return s2_5_table.ram_map(known, s2_5_table.tables_of(a["table"]), code, singles, known["candidates"]["runs"])


def rule_file(a: dict, known: dict, build: dict, all_sites: list[str] | None) -> dict:
    return s2_5_rule.rule(s2_5_table.tables_of(a["table"]), known, build, known["census"], all_sites)


def drive(root: Path, bases: dict, known: dict, runner, max_new: int | None = None, say=lambda *_: None, committed=committed,
          refuses=lambda k, out: "", build: dict | None = None, all_sites: list[str] | None = None) -> dict:
    """Go on with the chain until it is complete or halts (or `max_new` runs have been added). `runner(k, out)` makes
    run k and leaves its files in the directory `out`. After every run the whole chain is assessed again from what is
    stored. The code run is made alone: a single is started only when `committed` finds nothing wanting in the code
    run's directory and in the tables'; and no run at all unless the image the run script will load is the one the
    chain is made with and `refuses(k, out)` — on the board the run script's own dry run — has nothing to say against
    it. Until then the chain is "held", which is not a halt; "blocked" beside it says that a run could not be started.
    `build`: the build's record of the design, for the rule; `all_sites`: the sites of the memories' kind."""
    root.mkdir(parents=True, exist_ok=True)
    added = 0
    while True:
        a = assess(root, bases, known)
        if "table" in a and not named(root / TABLE_DIR):         # the code run closed into tables: written once, never over
            (root / TABLE_DIR).mkdir()
            (root / TABLE_DIR / TABLE).write_text(json.dumps(a["table"], indent=1) + "\n")
            say(f"the tables written: {TABLE_DIR}/{TABLE}")
        if a["state"] == "complete":
            (root / "ram_map.json").write_text(s2_5_table.dump(ram_map_file(a, bases, known)))
            if build is not None:
                (root / "rule.json").write_text(json.dumps(rule_file(a, known, build, all_sites), indent=1) + "\n")
            a["ram_map_file"] = "there"
        elif a.pop("ram_map_file", None):                # of an earlier look at these runs, which no longer stands
            for name in ("ram_map.json", "rule.json"):
                if (root / name).exists():
                    (root / name).unlink()
            say("ram_map.json and rule.json taken away: the chain is not complete as it is stored now")
        (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
        if a["runs"]:
            last = a["runs"][-1]
            bits = last.get("bits") or {}
            say(f"{last['dir']}: {last['kind']}" + ("" if last["share"] is None else f" {last['share']}")
                + f", {bits.get('follow', '?')} bit(s) follow a cell as they are, {bits.get('follow_inverted', '?')} inverted, {bits.get('irregular', '?')} irregular"
                + (f", {len(last['confirmed'])} cell(s) confirmed at every site" if "confirmed" in last else "") + f" — {last['decision']}")
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
                why = f"no single before the code run and its tables are committed: {why}"
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
        came_up_fresh(UB, out.name)
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, *([] if share is None else ["--share", str(share)]),
                            "--go", "--out", str(out)], capture_output=True, text=True)
        (root / f"{out.name}.out").write_text(r.stdout + r.stderr)
    return run


def sites_of_the_kind() -> list[str]:
    return [ln.strip() for ln in ALL_SITES.read_text().splitlines() if ln.startswith("SLICE_")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-new", type=int, help="add at most this many runs, then stop where the chain stands")
    a = ap.parse_args()
    bases = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in (CODE, SINGLES)}
    try:
        known = s1a_run.known_for(CODE)
    except ValueError as e:
        print(f"REFUSED: {e}"); return 2
    if not a.go:
        state = assess(a.dir, bases, known)
    else:
        state = drive(a.dir, bases, known, board_runner(a.dir), max_new=a.max_new, say=lambda line: print(line, flush=True),
                      refuses=lambda k, out: (lambda why: f"the run script refuses the run ({why})" if why else "")(refusal(k, out)),
                      build=json.loads(BUILD_RECORD.read_text()), all_sites=sites_of_the_kind())
    print(json.dumps({k: v for k, v in brief(state).items() if k != "runs"}, indent=1))
    if state["state"] != "complete" and state.get("ram_map_file"):
        print("NOTE: a ram_map.json or rule.json lies beside these runs, and the chain is not complete as it is stored now: it does not stand")
    if state.get("held"):
        print(f"HELD: {state['held']}")
    print(f"{len(state['runs'])} run(s) stored of {state['runs_planned']}; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") and not state.get("blocked") else 1


if __name__ == "__main__":
    sys.exit(main())

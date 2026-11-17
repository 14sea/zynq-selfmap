#!/usr/bin/env python3
"""S1b.2: the walk of a row as a chain of runs (docs/s1b_plan.md, section 25).

    s1b2_chain.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s1b2_chain.py --dir DIR --go            go on with it on the board, run after run, until it is complete or halts
    s1b2_chain.py --stage s1b3 ...          the same for the chain over block type 0 (section 38): the set s1b3

One run is the walk of S1b.1 (the parameter set s1b2: the row as the envelope, at most 64 frames a pass; judged by
s1b2_judge, which is the walk's judge but for one rule about the known frames), started at an address this program gives it. The first run starts at the first address of the set; every
later run starts at the last frame the run before walked, so that every seam is read by two runs.

The state of a chain is the stored runs and nothing else: DIR/run00, DIR/run01, ... Each is taken from its files and
judged again from its raw words, against the parameter block this program plans for it, before it is relied on. The
chain goes on after a run only if
  1. the run script reports no stop and a passing run, and the stored result is the one whose checksum the board gave;
  2. the judge passes it;
  3. both passes ended at the limit, after the same frames, having been told the same address;
  4. (every run but the first) its first frame is the last frame of the run before, with the same content, the
     address named after it is the one named there, and the register stood still there in both runs or in neither.
It is complete when a run satisfies 1, 2 and 4, both of its passes ended because the device named an address
outside the envelope, and every frame with a known answer in the envelope was walked by some run of the chain.
Anything else halts it, and so does a bound on the number of runs. Nothing is retried: a run
directory that does not hold a passing run stays where it is and the chain stands there until someone moves it.

This program knows the layout of nothing: not of the address word, not of a row. It follows the judge's account of
what the device named.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_judge  # noqa: E402

STAGE = "s1b2"
MAX_RUNS = 48                                        # a bound on unattended board time, not a statement about the row
# S1b.3 (section 38): the same chain with the set s1b3 — block type 0 whole as the envelope, one standstill a pass
# allowed. Nothing in the rules below differs; the bound is its own.
BOUNDS = {"s1b2": MAX_RUNS, "s1b3": 96}
P_LO, P_HI, P_PASSES, P_START = 3, 4, 7, 16          # words of the parameter block: the envelope, the passes, the start
LEFT, LIMIT = s1b2_judge.END[1], s1b2_judge.END[2]
RUN_DIR = re.compile(r"^run(\d\d)$")


def planned(base: list[int], start: int) -> list[int]:
    """The parameter block of a run: the set's, with the starting address in its one word."""
    block = list(base)
    block[P_START] = start
    return block


def read_run(d: Path, base: list[int], start: int, known: dict, stage: str = STAGE) -> dict:
    """One stored run: what the run script recorded, and the result judged again from its raw words against the block
    planned for a run starting at `start`. Everything found wanting is listed in "problems"."""
    out: dict = {"dir": d.name, "start": f"{start:#010x}", "problems": []}
    bad = out["problems"].append
    try:
        rec = json.loads((d / "run.json").read_text())
    except (OSError, ValueError):
        bad("there is no run record"); return out
    if rec.get("stage") != stage:
        bad(f"the run record is of stage {rec.get('stage')}, not {stage}")
    if not rec.get("went"):
        bad("the prober was not started")
    if rec.get("stop"):
        bad(f"the run script stopped: {rec['stop']}")
    if rec.get("verdict") != "PASS":
        bad(f"the run script's verdict is {rec.get('verdict')}: {rec.get('problems')}")
    if not rec.get("card_verified"):
        bad("the card copy was not verified")
    if (rec.get("chain") or {}).get("start") != f"{start:#010x}":
        bad(f"the run was started at {(rec.get('chain') or {}).get('start')}; the chain plans {start:#010x} for it")
    try:
        raw = (d / "result.bin").read_bytes()
    except OSError:
        bad("there is no stored result"); return out
    if len(raw) % 4 or f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" != rec.get("board_crc32"):
        bad("the stored result is not the one whose checksum the board gave"); return out
    out["result_sha256"] = hashlib.sha256(raw).hexdigest()
    v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, planned(base, start))
    out["judge"] = v["verdict"]
    if v["verdict"] != "PASS":
        bad(f"the judge says {v['verdict']}: {v['problems'][:3]}")
    out["passes"] = v.get("passes", [])
    out["walk"] = [{"far": s["far"], "next": s["next"], "frame_sha256": s["frame_sha256"], **({"stood_still": True} if s.get("stood_still") else {})}
                   for s in v.get("walk", [])]                 # a step at which the register stood still says so (a set that allows it)
    return out


def assess(root: Path, base: list[int], known: dict, max_runs: int = MAX_RUNS, stage: str = STAGE) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the number and the starting address of the next run), "complete" (with the address the
    device named after the last frame), "halted" (with the reasons)."""
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and RUN_DIR.match(p.name)) if root.is_dir() else []
    out: dict = {"runs": [], "set_aside": sorted(p.name for p in root.iterdir() if p.is_dir() and not RUN_DIR.match(p.name)) if root.is_dir() else []}

    def halted(*why: str) -> dict:
        out.update(state="halted", why=list(why)); return out

    if names != [f"run{k:02d}" for k in range(len(names))]:
        return halted(f"the run directories are not run00, run01, ... without a gap: {names}")
    start, prev = base[P_START], None
    for k, name in enumerate(names):
        r = read_run(root / name, base, start, known, stage)
        out["runs"].append(r)
        bad = r["problems"].append
        ends: list[tuple] = []
        if not r["problems"]:
            ends = [(p["ended"], p["frames"], p["last_address_named"]) for p in r["passes"]]
            if len(ends) != base[P_PASSES] or len(set(ends)) != 1:
                bad(f"the passes did not end alike: {ends}")
            elif ends[0][1] != len(r["walk"]) or not r["walk"]:
                bad(f"the passes count {ends[0][1]} frames, the walk lists {len(r['walk'])}")
        if not r["problems"] and prev is not None:       # the seam: one frame read by two runs
            a, b = prev["walk"][-1], r["walk"][0]
            if b["far"] != a["far"]:
                bad(f"seam: this run begins at {b['far']}, the run before ended at {a['far']}")
            elif b["frame_sha256"] != a["frame_sha256"]:
                bad(f"seam: the frame at {b['far']} is not the frame the run before read there")
            elif b["next"] != a["next"]:
                bad(f"seam: after {b['far']} this run was told {b['next']}, the run before {a['next']}")
            elif bool(b.get("stood_still")) != bool(a.get("stood_still")):
                # the same address named in both runs, but reached differently: in one the register stood still
                # after the pad alone and showed that address only after the frame was read, in the other at once
                said = lambda s: "stood still after the pad alone" if s.get("stood_still") else "did not stand still"  # noqa: E731
                bad(f"seam: at {b['far']} the register {said(b)} in this run, and {said(a)} in the run before")
        if r["problems"]:
            r["decision"] = "halt"
            if names[k + 1:]:
                r["problems"].append(f"the run directories after it were not looked at: {names[k + 1:]}")
            return halted(*[f"{name}: {p}" for p in r["problems"]])
        ended, frames, named = ends[0]
        r.update(frames=frames, first=r["walk"][0]["far"], last=r["walk"][-1]["far"], named_after_the_last=named, ended=ended)
        if ended == LEFT:
            if names[k + 1:]:
                r["decision"] = "complete"
                return halted(f"{name} left the envelope, yet there are run directories after it: {names[k + 1:]}")
            # the chain's own count, whatever the judges of the runs let pass: every frame with a known answer that
            # lies in the envelope was walked by some run before the envelope was left
            walked = {s["far"] for run in out["runs"] for s in run["walk"]}
            not_walked = [f"{f:#010x}" for f in sorted(int(a, 16) for a in known["frames"]) if base[P_LO] <= f <= base[P_HI] and f"{f:#010x}" not in walked]
            if not_walked:
                r["decision"] = "halt"
                return halted(f"{name} left the envelope, but no run of the chain walked the known frame(s) {', '.join(not_walked)}")
            r["decision"] = "complete"
            out.update(state="complete", named_after_the_last_frame=named)
            return out
        if ended != LIMIT or frames < 2:                 # a run that ends at the limit after one frame would begin where it began
            r["decision"] = "halt"
            return halted(f"{name}: the passes ended with \"{ended}\" after {frames} frame(s): nothing to go on from")
        r["decision"] = "go on"
        start, prev = int(r["walk"][-1]["far"], 16), r
    if len(names) >= max_runs:
        return halted(f"the bound of {max_runs} runs is reached; the last frame walked is {start:#010x}")
    out.update(state="go on", next_run=len(names), next_start=f"{start:#010x}",
               next_start_from=(f"the last frame walked by {prev['dir']} (result sha256 {prev['result_sha256']})" if prev else "the first address of the set"))
    return out


def brief(a: dict) -> dict:
    """The assessment without the lists of frames: what is written beside the runs as chain.json."""
    return {**a, "runs": [{k: v for k, v in r.items() if k not in ("walk", "passes")} for r in a["runs"]]}


def drive(root: Path, base: list[int], known: dict, runner, max_runs: int = MAX_RUNS, max_new: int | None = None, say=lambda *_: None,
          stage: str = STAGE) -> dict:
    """Go on with the chain until it is complete or halts (or `max_new` runs have been added). `runner(start, out,
    came_from)` makes one run starting at `start` and leaves its files in the directory `out`. After every run the
    whole chain is assessed again from what is stored."""
    root.mkdir(parents=True, exist_ok=True)
    added = 0
    while True:
        a = assess(root, base, known, max_runs, stage)
        (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
        if a["runs"]:
            last = a["runs"][-1]
            say(f"{last['dir']}: start {last['start']}, {last.get('frames', '?')} frames, last {last.get('last')}, then {last.get('named_after_the_last')} — {last['decision']}")
        if a["state"] != "go on" or (max_new is not None and added >= max_new):
            return a
        out = root / f"run{a['next_run']:02d}"
        runner(int(a["next_start"], 16), out, a["next_start_from"])
        out.mkdir(exist_ok=True)                         # a run that left nothing behind is a run directory without a record: a halt
        added += 1


def board_runner(root: Path, stage: str = STAGE):
    """One run on the board: a U-Boot `reset` (as before every run so far), then the run script."""
    import os
    os.environ["SELFMAP_CONSOLE_LOG"] = str(root / "resets_console.log")
    from uboot_console import UB

    def run(start: int, out: Path, came_from: str) -> None:
        u = UB()
        _, ok = u.interrupt()
        reply, ok2 = u.cmd("reset", 40) if ok else (b"", False)
        sts, ok3 = u.cmd("md.l f800700c 1", 10) if ok2 else (b"", False)
        u.s.close(); u.log.close()
        if not (ok and ok2 and ok3) or b"Ebang EBAZ4203" not in reply or b"a802000" not in sts:
            raise RuntimeError(f"before {out.name}: reset did not give the usual fresh prompt; nothing was run")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--start", f"{start:x}", "--start-from", came_from,
                            "--go", "--out", str(out)], capture_output=True, text=True)
        (root / f"{out.name}.out").write_text(r.stdout + r.stderr)
    return run


def main() -> int:
    import s1a_run
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-new", type=int, help="add at most this many runs, then stop where the chain stands")
    ap.add_argument("--stage", choices=sorted(BOUNDS), default=STAGE, help="the parameter set the chain drives (s1b2: the row; s1b3: block type 0)")
    a = ap.parse_args()
    base = [int(w, 16) for w in json.loads(s1a_run.STAGES[a.stage]["expected"].read_text())["params"]]
    known = json.loads(s1a_run.KNOWN.read_text())
    if not a.go:
        state = assess(a.dir, base, known, BOUNDS[a.stage], a.stage)
    else:
        try:
            state = drive(a.dir, base, known, board_runner(a.dir, a.stage), BOUNDS[a.stage], max_new=a.max_new, say=lambda line: print(line, flush=True),
                          stage=a.stage)
        except RuntimeError as e:
            print(f"HALT {e}"); return 1
    print(json.dumps({k: v for k, v in brief(state).items() if k != "runs"}, indent=1))
    print(f"{len(state['runs'])} run(s) stored; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") else 1


if __name__ == "__main__":
    sys.exit(main())

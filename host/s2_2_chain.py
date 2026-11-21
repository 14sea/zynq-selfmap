#!/usr/bin/env python3
"""S2.2: block type 0 in three states of the design's RAM, as a chain of runs — docs/s2_plan.md, section 19.

    s2_2_chain.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s2_2_chain.py --dir DIR --go            go on with it on the board, run after run, until it is complete or halts

One run is of one share of the census's addresses (the parameter set s2_2, s1a_run.py --share k): run k of the chain
is of share k. The state of the chain is the stored runs and nothing else: DIR/run00, DIR/run01, ... Each is taken
from its files and judged again from its raw words, against the parameter block and the list planned for its share,
before it is relied on. The chain goes on after a run only if

  1. the run script reports no stop and a passing run of that share, and the stored result is the one whose checksum
     the board gave;
  2. the judge passes it, and the verdict stored beside it is what the judge says of the stored result.

Anything else halts it. Nothing is run again: a run directory that does not hold a passing run stays where it is and
the chain stands there until someone has looked and moved it. (A reply that showed a restart, a result that could not
be pulled, a judge that fails the run — all of them are a run that is not a passing run.)

It is complete when every share has its run. Then the step is closed, here and by nothing else: every address of
block type 0 the census has was read in every state; the candidates of all runs together are the answer, and their
number is held against the number of cells the design's RAM has — which is the design's own fact (pl/s2a/design.json),
not the device's. What came of it is said as one of the outcomes the plan named beforehand, and the candidates are
written out (DIR/candidates.json), each as an address, a word and a bit.

Nothing here knows where a cell lies, or what an address word means.
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
import s1a_run  # noqa: E402
import s2_2_judge  # noqa: E402
import s2_2_shares  # noqa: E402

STAGE = "s2_2"
RUN_DIR = re.compile(r"^run(\d\d)$")


def read_run(d: Path, exp: dict, share: int, known: dict) -> dict:
    """One stored run: what the run script recorded, and the result judged again from its raw words against what is
    planned for that share (`exp`: the set with the share's list). Everything found wanting is listed in "problems"."""
    out: dict = {"dir": d.name, "share": share, "problems": []}
    bad = out["problems"].append
    try:
        rec = json.loads((d / "run.json").read_text())
    except (OSError, ValueError):
        bad("there is no run record"); return out
    if rec.get("stage") != STAGE:
        bad(f"the run record is of stage {rec.get('stage')}, not {STAGE}")
    if (rec.get("share") or {}).get("index") != share:
        bad(f"the run is of share {(rec.get('share') or {}).get('index')}; the chain plans share {share} for it")
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
    if len(raw) % 4 or f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" != rec.get("board_crc32"):
        bad("the stored result is not the one whose checksum the board gave"); return out
    out["result_sha256"] = hashlib.sha256(raw).hexdigest()
    v = json.loads(json.dumps(s2_2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1a_run.planned_words(exp))))
    out["judge"] = v["verdict"]
    if v["verdict"] != "PASS":
        bad(f"the judge says {v['verdict']}: {v['problems'][:3]}")
    try:
        stored = json.loads((d / "verdict.json").read_text())
    except (OSError, ValueError):
        stored = None
    if stored != v:
        bad("the verdict stored beside the result is not what the judge says of the stored result")
    f = v.get("finding", {})
    out.update(reads=exp["share"]["reads"], frames=f.get("frames"), first=exp["share"]["first"], last=exp["share"]["last"],
               candidates=f.get("candidates", []), restless=len(f.get("restless", [])),
               ctl0=(v.get("registers", {}).get("CTL0", {}) or {}).get("value"),
               bit_5_shown_after_records=(v.get("bit_5") or {}).get("shown_after_records", []),
               bit_5_still_set_after_clearing=(v.get("bit_5") or {}).get("still_set_after_clearing", []))
    return out


def close(runs: list[dict], census: dict, cells: int) -> dict:
    """What all runs together say. `cells`: how many cells the design's RAM has."""
    lay = s2_2_shares.layout(census)
    problems: list[str] = []
    frames = sum(r["frames"] or 0 for r in runs)
    if frames != len(lay["block0"]):
        problems.append(f"the runs read {frames} addresses; block type 0 has {len(lay['block0'])} in the census")
    found = [dict(c, run=r["dir"]) for r in runs for c in r["candidates"]]
    places = [(c["far"], c["word"], c["bit"]) for c in found]
    if len(set(places)) != len(places):
        problems.append("a place is a candidate in two runs: the shares are not apart")
    ctl0 = sorted({r["ctl0"] for r in runs})
    if len(ctl0) != 1:
        problems.append(f"CTL0 did not read the same in every run: {ctl0}")
    inverted = sum(1 for c in found if c["inverted"])
    n = len(found)
    if n == cells:
        outcome = ("1: as many candidates as the RAM has cells; every other bit still; the RAM held its state through every pass"
                   + (f" — {inverted} of them inverted (5)" if inverted else ""))
    elif n == 0:
        outcome = "2: no candidate"
    elif n < cells:
        outcome = f"3: fewer candidates ({n}) than the RAM has cells ({cells})"
    else:
        outcome = f"4: more candidates ({n}) than the RAM has cells ({cells})"
    by_frame: dict[str, int] = {}
    for c in found:
        by_frame[c["far"]] = by_frame.get(c["far"], 0) + 1
    return {"problems": problems, "addresses_read": frames, "cells_in_the_design": cells, "candidates": n, "candidates_inverted": inverted,
            "outcome": outcome, "ctl0": ctl0, "frames_with_candidates": dict(sorted(by_frame.items())),
            "bit_5": {r["dir"]: r["bit_5_shown_after_records"] for r in runs if r["bit_5_shown_after_records"]},
            "bit_5_still_set_after_clearing": {r["dir"]: r["bit_5_still_set_after_clearing"] for r in runs if r["bit_5_still_set_after_clearing"]},
            "found": found}


def assess(root: Path, base: dict, known: dict, limit: int = s2_2_shares.LIST_MAX) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the share of the next run), "complete" (with what all runs together say), "halted" (with the
    reasons). `base`: the set as the tests wrote it, without a share."""
    census = known["census"]
    every = s2_2_shares.shares(census, limit)
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and RUN_DIR.match(p.name)) if root.is_dir() else []
    out: dict = {"stage": STAGE, "shares": len(every), "runs": [],
                 "set_aside": sorted(p.name for p in root.iterdir() if p.is_dir() and not RUN_DIR.match(p.name)) if root.is_dir() else []}

    def halted(*why: str) -> dict:
        out.update(state="halted", why=list(why)); return out

    if names != [f"run{k:02d}" for k in range(len(names))]:
        return halted(f"the run directories are not run00, run01, ... without a gap: {names}")
    if len(names) > len(every):
        return halted(f"{len(names)} run directories for {len(every)} shares")
    for k, name in enumerate(names):
        r = read_run(root / name, s1a_run.with_share(STAGE, base, k, census, limit), k, known)
        out["runs"].append(r)
        if r["problems"]:
            r["decision"] = "halt"
            if names[k + 1:]:
                r["problems"].append(f"the run directories after it were not looked at: {names[k + 1:]}")
            return halted(*[f"{name}: {p}" for p in r["problems"]])
        r["decision"] = "go on" if k + 1 < len(every) else "complete"
    if len(names) < len(every):
        out.update(state="go on", next_run=len(names), next_share=len(names))
        return out
    closing = close(out["runs"], census, len(known["ram"]["cells"]) * known["ram"]["depth"])
    out["closing"] = closing
    if closing["problems"]:
        return halted(*closing["problems"])
    out["state"] = "complete"
    return out


def brief(a: dict) -> dict:
    """The assessment without the lists of candidates: what is written beside the runs as chain.json."""
    b = {**a, "runs": [{k: v for k, v in r.items() if k != "candidates"} | {"candidates": len(r.get("candidates", []))} for r in a["runs"]]}
    if "closing" in a:
        b["closing"] = {k: v for k, v in a["closing"].items() if k != "found"}
    return b


def candidates_file(a: dict, known: dict) -> dict:
    """What a complete chain found, as it is written out: closed-book, the places and nothing about what they are."""
    c = a["closing"]
    return {"schema": "s2_2_candidates", "schema_version": 1, "label": "closed-book",
            "what": "bits of configuration memory that followed the probe design's RAM through the states all zero, all one, all zero "
                    "(docs/s2_plan.md, section 19). A place is an address the device named, a word of the frame read there (0 the first), "
                    "and a bit of that word (0 the least significant). Which cell of the RAM a place is, is not known from this.",
            "design": known.get("name"), "cells_in_the_design": c["cells_in_the_design"], "candidates": c["candidates"],
            "candidates_inverted": c["candidates_inverted"], "outcome": c["outcome"],
            "runs": [{"dir": r["dir"], "share": r["share"], "result_sha256": r["result_sha256"]} for r in a["runs"]],
            "frames_with_candidates": c["frames_with_candidates"], "places": c["found"]}


def drive(root: Path, base: dict, known: dict, runner, max_new: int | None = None, say=lambda *_: None, limit: int = s2_2_shares.LIST_MAX) -> dict:
    """Go on with the chain until it is complete or halts (or `max_new` runs have been added). `runner(share, out)`
    makes the run of that share and leaves its files in the directory `out`. After every run the whole chain is
    assessed again from what is stored."""
    root.mkdir(parents=True, exist_ok=True)
    added = 0
    while True:
        a = assess(root, base, known, limit)
        (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
        if a["runs"]:
            last = a["runs"][-1]
            say(f"{last['dir']}: share {last['share']}, {last.get('frames', '?')} addresses, {len(last.get('candidates', []))} candidate(s) — {last['decision']}")
        if a["state"] == "complete":
            (root / "candidates.json").write_text(json.dumps(candidates_file(a, known), indent=1) + "\n")
        if a["state"] != "go on" or (max_new is not None and added >= max_new):
            return a
        out = root / f"run{a['next_run']:02d}"
        runner(a["next_share"], out)
        out.mkdir(exist_ok=True)                         # a run that left nothing behind is a run directory without a record: a halt
        added += 1


def board_runner(root: Path):
    """One run on the board: a U-Boot `reset` (as before every run so far), then the run script."""
    import os
    os.environ["SELFMAP_CONSOLE_LOG"] = str(root / "resets_console.log")
    from uboot_console import UB

    def run(share: int, out: Path) -> None:
        u = UB()
        _, ok = u.interrupt()
        reply, ok2 = u.cmd("reset", 40) if ok else (b"", False)
        sts, ok3 = u.cmd("md.l f800700c 1", 10) if ok2 else (b"", False)
        u.s.close(); u.log.close()
        if not (ok and ok2 and ok3) or b"Ebang EBAZ4203" not in reply or b"a802000" not in sts:
            raise RuntimeError(f"before {out.name}: reset did not give the usual fresh prompt; nothing was run")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE, "--share", str(share), "--go", "--out", str(out)],
                           capture_output=True, text=True)
        (root / f"{out.name}.out").write_text(r.stdout + r.stderr)
    return run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-new", type=int, help="add at most this many runs, then stop where the chain stands")
    a = ap.parse_args()
    base = json.loads(s1a_run.STAGES[STAGE]["expected"].read_text())
    known = s1a_run.known_for(STAGE)
    if not a.go:
        state = assess(a.dir, base, known)
    else:
        try:
            state = drive(a.dir, base, known, board_runner(a.dir), max_new=a.max_new, say=lambda line: print(line, flush=True))
        except RuntimeError as e:
            print(f"HALT {e}"); return 1
    print(json.dumps({k: v for k, v in brief(state).items() if k != "runs"}, indent=1))
    print(f"{len(state['runs'])} run(s) stored of {state['shares']}; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") else 1


if __name__ == "__main__":
    sys.exit(main())

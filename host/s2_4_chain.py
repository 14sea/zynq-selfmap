#!/usr/bin/env python3
"""S2.4, part 1: where the shift registers' bits are, as a chain of runs — docs/s2_plan.md, sections 37 and 38.

    s2_4_chain.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s2_4_chain.py --dir DIR --go            go on with it on the board, run after run, until it is complete, held or halted

The runs: DIR/run00 to DIR/run07, one for each share of the census's addresses of block type 0 (S2.2's shares, as they
are), each in the three states of the design's shift registers all zero, all one, all zero (the set s2_4f, --share).
The state of the chain is the stored runs and nothing else. Each run is taken from its files and judged again from its
raw words, against the plan of that run, before it is relied on; what a stored run must show of the image, the design
and both lists it was made with is what the chain of S2.3 asks.

**The first run is made alone**, and no second before the first is committed to git as it stands. Until then the chain
is "held", which is not a halt.

**The first run is held to the CTL0 of S2.2's runs** (section 34's rule, for the same reason: what this step is
compared with — the frames S2.2 stored, and the prediction made from them — was read under that word). A run under
another halts the chain there; so does a later run that reads another than the first.

When all runs are stored the chain is closed (`close`): the bits that followed the states are the candidates, as they
are or inverted, each a place of its own. What the closing names, by the numbers section 37 gave beforehand:

    1   as many bits follow as they are as the registers have outputs, and none inverted
    2   more follow: as many as they are as there are outputs, and others inverted, or more as they are
    3   fewer follow as they are than there are outputs: reported, and the owner decides whether part 2 is made on it
    4   nothing follows: the chain halts
    5   a candidate is one of the RAM's places: the chain halts

and, beside the outcome and failing nothing: where a frame read in the first all-zero state otherwise than S2.2 stored
it and the place is no candidate (7); after which records bit 5 showed (8); and whether the prediction made before the
board was asked (s2_4_predict) was a hit — every place it names a candidate that follows as it is — or a miss.

A complete chain writes DIR/candidates.json: the places, closed-book, and nothing about which output a place is. That
is part 2. Anything that is not as planned halts the chain, and nothing is run again: a run directory that does not
hold a passing run stays where it is until the owner has it set aside. No database is read and nothing is graded."""
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
import s2_2_shares  # noqa: E402
import s2_3_chain  # noqa: E402
import s2_4_judge  # noqa: E402
import s2_4_predict  # noqa: E402
import s2_4_states  # noqa: E402
from s2_2_chain import KEPT_IMAGE, RUN_DIR, came_up_fresh, committed, crc, declared, ready  # noqa: E402,F401
from s2_3_chain import bound  # noqa: E402,F401

STAGE = "s2_4f"
PREDICTION = ROOT / "evidence" / "s2_4_prediction_2026-11-23" / "prediction.json"
DATA, FRAME, REC = 76, 101, 480                        # where a record's data begin; words of a frame; of a record (the judges' numbers)


def refusal(share: int, out: Path) -> str:
    """What the run script says if it would refuse the run of this share into this directory, from its own dry run,
    which sends nothing and makes nothing."""
    r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE, "--share", str(share), "--out", str(out), "--dry-run"],
                       capture_output=True, text=True)
    return "" if r.returncode == 0 else ((r.stdout + r.stderr).strip().splitlines() or ["it ended with a code and said nothing"])[-1]


def elsewhere(words: list[int], follows: list[dict], before: dict) -> list[dict]:
    """Where the frames a run read in its first state — the shift registers all zero — read otherwise than `before`
    has them (the frames S2.2 stored, with the shift registers as loaded), at a place that is no candidate of this run.
    From the raw words of a result the judge has passed."""
    hdr, n = words[7], words[3]
    mine = {(int(f["far"], 16), f["word"], f["bit"]) for f in follows}
    out: list[dict] = []
    for i in range(n):
        r = words[hdr + i * REC: hdr + (i + 1) * REC]
        far, kind, state, m, op = r[0], r[1], r[12], r[14], r[15]
        if kind != 0 or state != 0 or op >= 0x100 or m == 0xF:
            continue
        for j in range(m):
            was = before.get(far + j)
            if was is None:
                out.append({"far": f"{far + j:#010x}", "word": None, "bit": None, "what": "a frame S2.2 did not store"}); continue
            now = r[DATA + FRAME * (j + 1): DATA + FRAME * (j + 2)]
            for w in range(FRAME):
                x = now[w] ^ was[w]
                for b in range(32):
                    if x >> b & 1 and (far + j, w, b) not in mine:
                        out.append({"far": f"{far + j:#010x}", "word": w, "bit": b, "what": "reads otherwise than S2.2 stored it, and follows nothing"})
    return out


def read_run(d: Path, share: int, exp: dict, known: dict, held: dict) -> dict:
    """One stored run: what the run script recorded, and the result judged again from its raw words against the plan
    of that share (`exp`: the set with the plan's lists). Everything found wanting is listed in "problems"."""
    out: dict = {"dir": d.name, "kind": "find", "share": share, "problems": []}
    bad = out["problems"].append
    try:
        rec = json.loads((d / "run.json").read_text())
    except (OSError, ValueError):
        bad("there is no run record"); return out
    if not isinstance(rec, dict):
        bad("the run record is not a record"); return out
    if rec.get("stage") != STAGE:
        bad(f"the run record is of stage {rec.get('stage')}, not {STAGE}")
    plan = rec.get("plan") if isinstance(rec.get("plan"), dict) else {}
    if (plan.get("kind"), plan.get("share")) != ("find", share):
        bad(f"the run is {plan.get('kind')}, share {plan.get('share')}; the chain plans part 1, share {share} for it")
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
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    v = json.loads(json.dumps(s2_4_judge.judge(words, known, s1a_run.planned_words(exp))))
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
    if v["verdict"] == "PASS" and (run.get("kind"), run.get("share")) != ("find", share):
        bad(f"the result is of {run.get('kind')}, share {run.get('share')}: not the run the chain plans here")
    f = v.get("finding", {})
    out.update(reads=exp["plan"]["reads"], frames=f.get("frames"), first=exp["plan"]["first"], last=exp["plan"]["last"], bits=f.get("bits"),
               candidates=f.get("follows", []), ctl0=(v.get("registers", {}).get("CTL0", {}) or {}).get("value"),
               bit_5_shown_after_records=(v.get("bit_5") or {}).get("shown_after_records", []),
               bit_5_still_set_after_clearing=(v.get("bit_5") or {}).get("still_set_after_clearing", []))
    if v["verdict"] == "PASS" and "frames_before" in known:
        out["elsewhere"] = elsewhere(words, out["candidates"], known["frames_before"])
    return out


def close(runs: list[dict], known: dict) -> dict:
    """What all runs together say."""
    lay = s2_2_shares.layout(known["census"])
    cells = len(known["srl"]["cells"]) * known["srl"]["depth"]
    problems: list[str] = []
    frames = sum(r["frames"] or 0 for r in runs)
    if frames != len(lay["block0"]):
        problems.append(f"the runs read {frames} addresses; block type 0 has {len(lay['block0'])} in the census")
    found = [dict(c, run=r["dir"]) for r in runs for c in r["candidates"]]
    places = [(c["far"], c["word"], c["bit"]) for c in found]
    if len(set(places)) != len(places):
        problems.append("a place is a candidate in two runs: the shares are not apart")
    as_they_are, inverted = sum(1 for c in found if not c["inverted"]), sum(1 for c in found if c["inverted"])
    ram = {(p["far"], p["word"], p["bit"]) for p in (known.get("ram_places") or {}).get("places", [])}
    if "ram_places" not in known:
        problems.append("where the RAM's cells are was not given: the candidates cannot be held apart from them")
    among = sorted(set(places) & ram)
    if not found:
        outcome = "4: nothing follows the states of the shift registers"
        problems.append(outcome)
    elif among:
        outcome = f"5: {len(among)} candidate(s) lie among the places of the RAM's cells"
        problems.append(outcome + f": {among[:3]}")
    elif as_they_are == cells and not inverted:
        outcome = "1: as many bits follow as the shift registers have outputs, none inverted; every other bit still; the registers held every state"
    elif as_they_are >= cells:
        outcome = (f"2: more bits follow than the shift registers have outputs ({cells}): {as_they_are} as they are, {inverted} inverted; "
                   "every other bit still; the registers held every state")
    else:
        outcome = f"3: fewer bits follow as they are ({as_they_are}) than the shift registers have outputs ({cells}); {inverted} follow inverted"
    by_frame: dict[str, int] = {}
    for c in found:
        by_frame[c["far"]] = by_frame.get(c["far"], 0) + 1
    out = {"problems": problems, "addresses_read": frames, "outputs_in_the_design": cells, "candidates": len(found),
           "candidates_as_they_are": as_they_are, "candidates_inverted": inverted, "outcome": outcome,
           "ctl0": sorted({r["ctl0"] for r in runs if r.get("ctl0")}), "ctl0_in_s2_2": known.get("ctl0_in_s2_2"),
           "frames_with_candidates": dict(sorted(by_frame.items())),
           "bit_5": {r["dir"]: r["bit_5_shown_after_records"] for r in runs if r["bit_5_shown_after_records"]},
           "bit_5_still_set_after_clearing": {r["dir"]: r["bit_5_still_set_after_clearing"] for r in runs if r["bit_5_still_set_after_clearing"]},
           "found": found}
    if all("elsewhere" in r for r in runs):
        out["frames_that_read_otherwise_than_in_s2_2_elsewhere"] = [dict(x, run=r["dir"]) for r in runs for x in r["elsewhere"]]
    else:
        out["frames_that_read_otherwise_than_in_s2_2_elsewhere"] = "not compared: the frames S2.2 stored were not given"
    if "prediction" in known:
        said = s2_4_predict.places(known["prediction"])
        got = {(int(c["far"], 16), c["word"], c["bit"]): c["inverted"] for c in found}
        missed = sorted(p for p in said if got.get(p) is not False or said[p][2])
        out["prediction"] = {"places_named": len(said), "candidates_as_they_are_among_them": len(said) - len(missed),
                             "says": ("hit: every place the prediction names is a candidate that follows as it is" if said and not missed
                                      else "the prediction names no place" if not said else f"miss: {len(missed)} place(s) it names are not such candidates"),
                             "not_such": [f"{f:#010x}/{w}/{b}" for f, w, b in missed[:16]]}
    return out


def assess(root: Path, base: dict, known: dict) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the share of the next run), "complete" (with what all runs together say), "halted" (with the
    reasons). `base`: the set as the tests wrote it, without a plan."""
    every = s2_4_states.shares(known["census"], known)
    there = sorted(root.iterdir()) if root.is_dir() else []
    names = sorted(p.name for p in there if p.is_dir() and not p.is_symlink() and RUN_DIR.match(p.name))
    out: dict = {"step": "s2_4, part 1", "shares": len(every), "runs": [],
                 "set_aside": sorted(p.name for p in there if p.is_dir() and not RUN_DIR.match(p.name))}

    def halted(*why: str) -> dict:
        out.update(state="halted", why=list(why)); return out

    if root.is_dir() and (root / "candidates.json").exists():
        out["candidates_file"] = "there"                 # the driver writes it when the chain is complete and takes it away when it is not
    taken = [p.name for p in there if RUN_DIR.match(p.name) and p.name not in names]
    if taken:
        return halted(f"what has the name of a run and is not a directory: {taken}")
    if names != [f"run{k:02d}" for k in range(len(names))]:
        return halted(f"the run directories are not run00, run01, ... without a gap: {names}")
    if len(names) > len(every):
        return halted(f"{len(names)} run directories for {len(every)} shares")
    held = declared(root, base)
    if held["problems"]:
        return halted(*held["problems"])
    out["made_with"] = {k: v for k, v in held.items() if k != "problems"}
    for k, name in enumerate(names):
        try:
            exp = s1a_run.with_plan(STAGE, base, k, known)
        except ValueError as e:
            return halted(f"no plan can be made for {name}: {e}")
        r = read_run(root / name, k, exp, known, held)
        out["runs"].append(r)
        if not r["problems"] and k == 0 and (not known.get("ctl0_in_s2_2") or r.get("ctl0") != known["ctl0_in_s2_2"]):
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in the first run and {known.get('ctl0_in_s2_2')} in the runs of S2.2, whose frames this step is held against")
        if not r["problems"] and k > 0 and r.get("ctl0") != out["runs"][0].get("ctl0"):
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in this run and {out['runs'][0].get('ctl0')} in the first run")
        if r["problems"]:
            r["decision"] = "halt"
            if names[k + 1:]:
                r["problems"].append(f"the run directories after it were not looked at: {names[k + 1:]}")
            return halted(*[f"{name}: {p}" for p in r["problems"]])
        r["decision"] = "go on" if k + 1 < len(every) else "complete"
    if len(names) < len(every):
        out.update(state="go on", next_run=len(names), next_share=len(names))
        return out
    closing = close(out["runs"], known)
    out["closing"] = closing
    if closing["problems"]:
        return halted(*closing["problems"])
    out["state"] = "complete"
    return out


def brief(a: dict) -> dict:
    """The assessment without the lists of places: what is written beside the runs as chain.json."""
    b = {**a, "runs": [{k: v for k, v in r.items() if k not in ("candidates", "elsewhere")}
                       | {"candidates": len(r.get("candidates", []))} | ({"elsewhere": len(r["elsewhere"])} if "elsewhere" in r else {}) for r in a["runs"]]}
    if "closing" in a:
        b["closing"] = {k: v for k, v in a["closing"].items() if k != "found"}
    return b


def candidates_file(a: dict, known: dict) -> dict:
    """What a complete chain found, as it is written out: closed-book, the places and nothing about what they are."""
    c = a["closing"]
    return {"schema": "s2_4_candidates", "schema_version": 1, "label": "closed-book",
            "what": "bits of configuration memory that followed the probe design's shift registers through the states all zero, all one, all "
                    "zero, as they are or inverted (docs/s2_plan.md, section 37, part 1). A place is an address the device named, a word of the "
                    "frame read there (0 the first), and a bit of that word (0 the least significant). Which output of which register a place "
                    "is, is not known from this.",
            "design": known.get("name"), "outputs_in_the_design": c["outputs_in_the_design"], "candidates": c["candidates"],
            "candidates_as_they_are": c["candidates_as_they_are"], "candidates_inverted": c["candidates_inverted"], "outcome": c["outcome"],
            "runs": [{"dir": r["dir"], "share": r["share"], "result_sha256": r["result_sha256"]} for r in a["runs"]],
            "frames_with_candidates": c["frames_with_candidates"], "places": c["found"]}


def drive(root: Path, base: dict, known: dict, runner, max_new: int | None = None, say=lambda *_: None, committed=committed,
          refuses=lambda share, out: "") -> dict:
    """Go on with the chain until it is complete or halts (or `max_new` runs have been added). `runner(share, out)`
    makes the run of that share and leaves its files in the directory `out`. After every run the whole chain is
    assessed again from what is stored. The first run is made alone: a second is started only when `committed` finds
    nothing wanting in the first run's directory; and no run at all unless the image the run script will load is the
    one the chain is made with and `refuses(share, out)` — on the board the run script's own dry run — has nothing to
    say against it. Until then the chain is "held", which is not a halt; "blocked" beside it says that a run could not
    be started."""
    root.mkdir(parents=True, exist_ok=True)
    added = 0
    while True:
        a = assess(root, base, known)
        if a["state"] == "complete":
            (root / "candidates.json").write_text(json.dumps(candidates_file(a, known), indent=1) + "\n")
            a["candidates_file"] = "there"
        elif a.pop("candidates_file", None):              # of an earlier look at these runs, which no longer stands
            (root / "candidates.json").unlink()
            say("candidates.json taken away: the chain is not complete as it is stored now")
        (root / "chain.json").write_text(json.dumps(brief(a), indent=1) + "\n")
        if a["runs"]:
            last = a["runs"][-1]
            bits = last.get("bits") or {}
            say(f"{last['dir']}: share {last['share']}, {last.get('frames', '?')} addresses, {bits.get('follow', '?')} bit(s) follow, "
                f"{bits.get('follow_inverted', '?')} inverted, {bits.get('irregular', '?')} irregular — {last['decision']}")
        if a["state"] != "go on" or (max_new is not None and added >= max_new):
            return a
        out = root / f"run{a['next_run']:02d}"
        why, blocked = ready(root, base) or refuses(a["next_share"], out), True
        if why:
            why = f"nothing was sent: {why}"
        elif a["runs"]:
            why, blocked = committed(root / "run00"), False
            if why:
                why = f"no second run before the first is committed: {why}"
        if not why:
            if not a["runs"] and not (root / KEPT_IMAGE).exists():   # the image every run of this chain is to be made with, kept with them
                (root / KEPT_IMAGE).write_bytes(s1a_run.IMAGE.read_bytes())
            try:
                runner(a["next_share"], out)
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

    def run(share: int, out: Path) -> None:
        came_up_fresh(UB, out.name)
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE, "--share", str(share), "--go", "--out", str(out)],
                           capture_output=True, text=True)
        (root / f"{out.name}.out").write_text(r.stdout + r.stderr)
    return run


def known_of_the_device() -> dict:
    """What the chain is held to on the device: what the run script gives the judge of the set, and with it the frames
    S2.2 stored and the prediction made from them — both read from what is stored, neither needed to judge a run."""
    return dict(s1a_run.known_for(STAGE), frames_before=s2_4_predict.frames_as_loaded(), prediction=json.loads(PREDICTION.read_text()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--max-new", type=int, help="add at most this many runs, then stop where the chain stands")
    a = ap.parse_args()
    base = json.loads(s1a_run.STAGES[STAGE]["expected"].read_text())
    known = known_of_the_device()
    if not a.go:
        state = assess(a.dir, base, known)
    else:
        state = drive(a.dir, base, known, board_runner(a.dir), max_new=a.max_new, say=lambda line: print(line, flush=True),
                      refuses=lambda share, out: (lambda why: f"the run script refuses the run ({why})" if why else "")(refusal(share, out)))
    print(json.dumps({k: v for k, v in brief(state).items() if k != "runs"}, indent=1))
    if state["state"] != "complete" and state.get("candidates_file"):
        print("NOTE: a candidates.json lies beside these runs, and the chain is not complete as it is stored now: it does not stand")
    if state.get("held"):
        print(f"HELD: {state['held']}")
    print(f"{len(state['runs'])} run(s) stored of {state['shares']}; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") and not state.get("blocked") else 1


if __name__ == "__main__":
    sys.exit(main())

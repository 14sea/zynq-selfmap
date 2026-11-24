#!/usr/bin/env python3
"""S2.5, part 1: where the memories of the design s2b are, as a chain of runs — docs/s2_plan.md, sections 45 and 46.

    s2_5_chain.py --dir DIR                 say where the chain stored in DIR stands; touches no serial port, writes nothing
    s2_5_chain.py --dir DIR --go            go on with it on the board, run after run, until it is complete, held or halted

The runs: DIR/run00 to DIR/run07, one for each share of the census's addresses of block type 0 (S2.2's shares, as they
are), each in the three states as loaded, all one, all zero (the set s2_5f, --share). The state of the chain is the
stored runs and nothing else. Each run is taken from its files and judged again from its raw words, against the plan
of that run, before it is relied on; what a stored run must show of the image, the design and both lists it was made
with is what the chain of S2.3 asks.

**The first run is made alone**, and no second before the first is committed to git as it stands. Until then the chain
is "held", which is not a halt.

**The first run is held to the CTL0 of S2.2's runs** (section 34's rule: the census and the shares this step reads by
were made under that word, and so were the two descriptions its prediction was read from). A run under another halts
the chain there; so does a later run that reads another than the first.

From each stored run two things are taken. The bits that followed the two written states — all one, all zero — are
the candidates. And the frames it read as loaded are searched for the words the design loads its memories with
(s2_5_find): every group of four frames, every word, both halves, by the six moves of S2.3, without the prediction.

When all runs are stored the chain is closed (`close`). What the closing names, by the numbers section 45 gave
beforehand:

    1   as many bits follow as the design has cells, each memory's word is found once, the 64 places of each are
        candidates and there is no other candidate — and every memory is where the prediction said, under one form
        of its word rule
    2   the same, and some memories are not where the prediction said: which, and where they are, is the finding
    3   a memory's word is not found: at that site a memory is not laid out by the six moves. Reported
    4   fewer or more bits follow than the design has cells, or a bit follows that is of no memory found: reported
    5   nothing follows: the chain halts

Under 3 and 4 the chain is complete and says so; whether part 2 is made on it is the owner's decision. Beside the
outcome and failing nothing: after which records bit 5 showed.

A complete chain writes DIR/candidates.json: the places and, for each memory found, which memory of which site it is
— closed-book; a site's name there is the design's own record of where the build placed what it loaded with that
word. Which cell of its memory a place is, is said by the six moves the search assumed and tested by part 2.

Beside the outcome the closing says whether the runs of part 2 can be made over the frames with candidates as the
stage is (`room_for_part_2`): each state of part 2 reads those frames, and its records and its log of accesses lie in
one result area. Where they do not fit, part 1 stands as it is and part 2 has no run: for the owner.

**Part 2 is built on candidates.json and on chain.json, and on nothing else of part 1** — and whose memory a place is,
is said by part 1 alone, since part 2 writes every site alike and cannot tell one site from another. So before part 2
takes either file, every stored run of this chain is taken again from its raw words and both files are held to what
that gives; and part 2 is given what was held, not the files to open again (`taken_again`; the run script asks it of
every run of part 2, and so does part 2's chain).

Anything that is not as planned halts the chain, and nothing is run again: a run directory that does not hold a
passing run stays where it is until the owner has it set aside. No database is read and nothing is graded."""
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
import s2_4_predict  # noqa: E402
import s2_5_find  # noqa: E402
import s2_5_judge  # noqa: E402
import s2_5_predict  # noqa: E402
import s2_5_states  # noqa: E402
from s2_2_chain import KEPT_IMAGE, RUN_DIR, came_up_fresh, committed, crc, declared, ready  # noqa: E402,F401
from s2_3_chain import bound  # noqa: E402,F401

STAGE = "s2_5f"
PREDICTION = ROOT / "evidence" / "s2_5_prediction_2026-11-23" / "prediction.json"


def refusal(share: int, out: Path) -> str:
    """What the run script says if it would refuse the run of this share into this directory, from its own dry run,
    which sends nothing and makes nothing."""
    r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", STAGE, "--share", str(share), "--out", str(out), "--dry-run"],
                       capture_output=True, text=True)
    return "" if r.returncode == 0 else ((r.stdout + r.stderr).strip().splitlines() or ["it ended with a code and said nothing"])[-1]


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
    v = json.loads(json.dumps(s2_5_judge.judge(words, known, s1a_run.planned_words(exp))))
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
    if v["verdict"] == "PASS" and not out["problems"]:   # the frames as loaded, searched for the words the memories are loaded with
        try:
            if "rule" not in known:
                raise ValueError("the six moves of S2.3 were not given")
            looked, hits = s2_5_find.search(s2_5_find.frames_in_state(words, 0), known["rule"], s2_5_states.loaded(known))
            out.update(places_looked_at=looked, memories=hits)
        except (ValueError, KeyError) as e:
            bad(f"the frames as loaded could not be searched: {e}")
    return out


def held_to_the_prediction(prediction: dict, found: dict[tuple[int, int], dict], the_rule: list) -> dict:
    """The memories found, held against the prediction made before the board was asked: under each form of its word
    rule, which memories lie exactly where it said — all 64 places, each the address it named."""
    forms = prediction["rules"]["the_word"]["one_word_more_after_row"]
    got: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for (s, k), hit in found.items():
        if not hit["inverted"]:
            for place, a in s2_5_find.places_of(hit, the_rule).items():
                got[place] = (s, k, a)
    memories = [(s["site"], m["memory"]) for s in prediction["sites"] for m in s["memories"]]
    hit_under: dict[int, set] = {}
    for form in forms:                                   # a memory at a time: a prediction may name one place for two memories, and both are asked
        hit_under[form] = {(s, k) for (s, k), its in s2_5_predict.memory_places(prediction, form).items()
                           if all(got.get(place) == (s, k, a) for place, a in its.items())}
    best = max(forms, key=lambda f: (len(hit_under[f]), f == prediction["rules"]["the_word"]["named_first"]))
    whole = [f for f in forms if len(hit_under[f]) == len(memories)]
    name = {s["site"]: s["name"] for s in prediction["sites"]}
    said = {(s["site"], m["memory"]): (s["frames"], m) for s in prediction["sites"] for m in s["memories"]}
    not_there = []
    for s, k in sorted(set(memories) - hit_under[best]):
        frames, m = said[(s, k)]
        hit = found.get((s, k))
        not_there.append({"site": s, "name": name[s], "memory": k,
                          "said": {"frames": frames, "word_under_the_form": s2_5_predict.word_of(next(x["row_of_its_half"] for x in prediction["sites"] if x["site"] == s), best)
                                   + s2_5_predict.POSITIONS[m["position"]][0], "bits": m["bits"]},
                          "found": None if hit is None else {"frames": hit["frames"], "word": hit["word"], "bits": hit["bits"], "inverted": hit["inverted"]}})
    return {"memories_named": len(memories), "forms": {str(f): len(hit_under[f]) for f in forms},
            "forms_under_which_every_memory_is_where_it_said": whole, "the_form_it_named_first": prediction["rules"]["the_word"]["named_first"],
            "says": (f"hit: every memory is where the prediction said, under the form with the one word more after row {', '.join(str(f) for f in whole)}" if whole
                     else f"miss: under its best form (after row {best}) {len(memories) - len(hit_under[best])} of {len(memories)} memories are not where it said"),
            "best_form": best, "not_where_it_said": not_there}


def room_for_part_2(known: dict, frames: list[str]) -> dict:
    """Whether the runs of part 2 can be made over these frames with candidates, as the stage is: how many reads a
    state would have, and how many words the result of the code run and of a run of the singles (they are all of one
    size). Each state of part 2 reads every frame with a candidate, and the records lie with the log of accesses in
    one result area; memories that lie in more columns than were reckoned with can be found, every one, by part 1 and
    still leave part 2 without a plan. That does not touch what part 1 found."""
    out: dict = {"frames_with_candidates": len(frames), "the_result_area_holds": s2_5_states.RESULT_MAX_WORDS, "a_list_holds": s2_2_shares.LIST_MAX}
    if not frames:
        return dict(out, can_be_planned=False, why="there is no candidate to read a state over")
    found = {"frames_with_candidates": frames}
    try:
        out["reads_a_state"] = len(s2_5_states.candidate_reads(known["census"], found))
        out["result_words"] = {kind: s2_5_states.plan(kind, share, known, known["census"], found)["result_words"] for kind, share in (("code", None), ("singles", 0))}
    except ValueError as e:
        return dict(out, can_be_planned=False, why=str(e))
    return dict(out, can_be_planned=True)


def close(runs: list[dict], known: dict) -> dict:
    """What all runs together say."""
    lay = s2_2_shares.layout(known["census"])
    words = s2_5_states.loaded(known)
    cells = len(words) * s2_5_states.CELLS
    problems: list[str] = []
    frames = sum(r["frames"] or 0 for r in runs)
    if frames != len(lay["block0"]):
        problems.append(f"the runs read {frames} addresses; block type 0 has {len(lay['block0'])} in the census")
    follows: dict[tuple[int, int, int], tuple[int, bool]] = {}
    n_follow = 0
    for r in runs:
        its = s2_5_judge.places(r["candidates"])
        n_follow += len(its)
        follows.update(its)
    if len(follows) != n_follow:
        problems.append("a place is a candidate in two runs: the shares are not apart")
    as_they_are, inverted = sum(1 for _, inv in follows.values() if not inv), sum(1 for _, inv in follows.values() if inv)
    hits = [dict(h, run=r["dir"]) for r in runs for h in r.get("memories", [])]
    by_memory: dict[tuple[int, int], list[dict]] = {}
    for h in hits:
        by_memory.setdefault((h["site"], h["memory"]), []).append(h)
    every = [(s, k) for s in range(len(words)) for k in range(s2_5_states.MEMORIES)]
    not_found = [m for m in every if m not in by_memory]
    twice = [m for m in every if len(by_memory.get(m, [])) > 1]
    found = {m: by_memory[m][0] for m in every if len(by_memory.get(m, [])) == 1}
    the_rule = known.get("rule")
    covered: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    not_candidates: list[dict] = []                      # a memory found whose places are not all candidates that follow the way it was found
    overlap = 0
    for (s, k), h in sorted(found.items()):
        its = s2_5_find.places_of(h, the_rule)
        wrong = [p for p in its if p not in follows or follows[p][1] != h["inverted"]]
        if wrong:
            not_candidates.append({"site": s, "memory": k, "places_that_are_no_such_candidate": len(wrong)})
        for p, a in its.items():
            overlap += p in covered
            covered[p] = (s, k, a)
    if overlap:
        problems.append(f"{overlap} place(s) lie in two memories found: the words are not apart")
    of_none = sorted(p for p in follows if p not in covered)
    names = {s["site"]: s["name"] for s in known["ram"]["sites"]}
    simple = not not_found and not twice and not not_candidates and not of_none and len(follows) == cells and not inverted
    out: dict = {"problems": problems, "addresses_read": frames, "sites": len(words), "memories_in_the_design": len(every), "cells_in_the_design": cells,
                 "candidates": len(follows), "candidates_as_they_are": as_they_are, "candidates_inverted": inverted,
                 "places_looked_at": sum(r.get("places_looked_at", 0) for r in runs),
                 "hits_chance_would_give": s2_5_find.chance(sum(r.get("places_looked_at", 0) for r in runs), len(every)),
                 "memories_found_once": len(found), "memories_found_inverted": sum(1 for h in found.values() if h["inverted"]),
                 "memories_not_found": [{"site": s, "name": names[s], "memory": k} for s, k in not_found],
                 "memories_found_more_than_once": [{"site": s, "name": names[s], "memory": k, "times": len(by_memory[(s, k)])} for s, k in twice],
                 "memories_found_whose_places_are_not_all_candidates": not_candidates,
                 "candidates_of_no_memory_found": len(of_none), "candidates_of_no_memory_found_first": [f"{f:#010x}/{w}/{b}" for f, w, b in of_none[:16]]}
    if "prediction" in known and the_rule is not None:
        out["prediction"] = held_to_the_prediction(known["prediction"], found, the_rule)
    if not follows:
        outcome = "5: nothing follows the states written to the memories"
        problems.append(outcome)
    elif simple:
        said = out.get("prediction")
        if said is None:
            outcome = "1 or 2: every memory's word is found once, its 64 places are candidates and there is no other candidate; the prediction was not given"
        elif said["forms_under_which_every_memory_is_where_it_said"]:
            outcome = ("1: as many bits follow as the design has cells, each memory's word is found once and its 64 places are the candidates; every memory is "
                       f"where the prediction said, under the form with the one word more after row "
                       f"{', '.join(str(f) for f in said['forms_under_which_every_memory_is_where_it_said'])}")
        else:
            outcome = (f"2: as many bits follow as the design has cells, each memory's word is found once and its 64 places are the candidates; "
                       f"{len(said['not_where_it_said'])} memories are not where the prediction said under its best form")
    elif not_found or twice:
        outcome = (f"3: {len(not_found)} memory word(s) are not found" + (f" and {len(twice)} found more than once" if twice else "")
                   + f"; {len(follows)} bit(s) follow for {cells} cells, {len(of_none)} of them of no memory found")
    else:
        outcome = (f"4: {len(follows)} bit(s) follow ({inverted} inverted) for {cells} cells; {len(of_none)} of no memory found; "
                   f"{len(not_candidates)} memories found whose places are not all candidates")
    by_frame: dict[str, int] = {}
    for far, _, _ in follows:
        by_frame[f"{far:#010x}"] = by_frame.get(f"{far:#010x}", 0) + 1
    out.update(outcome=outcome, ctl0=sorted({r["ctl0"] for r in runs if r.get("ctl0")}), ctl0_in_s2_2=known.get("ctl0_in_s2_2"),
               frames_with_candidates=dict(sorted(by_frame.items())), part_2=room_for_part_2(known, sorted(by_frame)),
               bit_5={r["dir"]: r["bit_5_shown_after_records"] for r in runs if r["bit_5_shown_after_records"]},
               bit_5_still_set_after_clearing={r["dir"]: r["bit_5_still_set_after_clearing"] for r in runs if r["bit_5_still_set_after_clearing"]},
               found=[dict(e, run=r["dir"]) for r in runs for e in r["candidates"]],
               memories=[dict(found[m], name=names[m[0]]) for m in sorted(found)])
    return out


def assess(root: Path, base: dict, known: dict) -> dict:
    """Where the chain stored under `root` stands: every run in order, each with the decision taken after it, and then
    one of — "go on" (with the share of the next run), "complete" (with what all runs together say), "halted" (with the
    reasons). `base`: the set as the tests wrote it, without a plan."""
    every = s2_5_states.shares(known["census"], known)
    there = sorted(root.iterdir()) if root.is_dir() else []
    names = sorted(p.name for p in there if p.is_dir() and not p.is_symlink() and RUN_DIR.match(p.name))
    out: dict = {"step": "s2_5, part 1", "shares": len(every), "runs": [],
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
            r["problems"].append(f"CTL0 read {r.get('ctl0')} in the first run and {known.get('ctl0_in_s2_2')} in the runs of S2.2, under which the census's shares were read")
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
    b = {**a, "runs": [{k: v for k, v in r.items() if k not in ("candidates", "memories")}
                       | {"candidates": sum(len(e["bits"]) for e in r.get("candidates", []))} | ({"memories": len(r["memories"])} if "memories" in r else {})
                       for r in a["runs"]]}
    if "closing" in a:
        b["closing"] = {k: v for k, v in a["closing"].items() if k not in ("found", "memories")}
    return b


def candidates_file(a: dict, known: dict) -> dict:
    """What a complete chain found, as it is written out: closed-book."""
    c = a["closing"]
    return {"schema": "s2_5_candidates", "schema_version": 1, "label": "closed-book",
            "what": "bits of configuration memory that followed the memories of the probe design s2b through the states all one, all zero, written "
                    "to every site at once; and, for each memory whose loaded word was found in the frames read before anything was written, where "
                    "it lies and which memory of which site it is by the design's record of what it loaded where (docs/s2_plan.md, section 45, "
                    "part 1). A place is an address the device named, a word of the frame read there (0 the first), and a bit of that word (0 the "
                    "least significant). Which cell of its memory a place is, is said here only by the six moves of S2.3, which the search "
                    "assumed; part 2 tests it.",
            "design": known.get("name"), "sites": c["sites"], "cells_in_the_design": c["cells_in_the_design"], "candidates": c["candidates"],
            "candidates_as_they_are": c["candidates_as_they_are"], "candidates_inverted": c["candidates_inverted"], "outcome": c["outcome"],
            "runs": [{"dir": r["dir"], "share": r["share"], "result_sha256": r["result_sha256"]} for r in a["runs"]],
            "the_six_moves": [{"address": n, "frame_above_the_lowest": f, "bit_of_the_half_word": b} for n, (f, b) in enumerate(known["rule"])],
            "frames_with_candidates": c["frames_with_candidates"], "memories": c["memories"],
            "memories_not_found": c["memories_not_found"], "candidates_of_no_memory_found": c["candidates_of_no_memory_found"], "places": c["found"]}


def taken_again(root: Path, candidates: Path | None = None, chain: Path | None = None, base: dict | None = None, known: dict | None = None) -> dict:
    """What part 2 may build on of the part 1 stored under `root`: {"why": "", "candidates", "chain"} — or "why" alone,
    with the reason, where it may build on nothing. Part 2 uses two things this chain wrote — the candidates with the
    memory and the site of each, and chain.json for the CTL0 of the runs — and part 2 cannot test whose memory a
    place is: it writes every site alike. So both are held here to the stored runs themselves: every run taken again
    from its raw words as `assess` takes it, the chain complete, and each file what the driver would write of it now.
    (External review of 66e4ac4: with two sites' names changed for each other in candidates.json and nothing else
    touched, part 2 closed with 512 places of the wrong site, every one confirmed.)

    **What is given back is what was held, not a file to be opened again**: the candidates and the chain as the runs
    give them here, which each file was found to be. (External review of b8f014a: the files were held to the runs
    and then read a second time; changed by another program in between, they were taken as they then were.)
    `candidates`, `chain`: the files part 2 is given, if they are not the two in `root`."""
    base = json.loads(s1a_run.STAGES[STAGE]["expected"].read_text()) if base is None else base
    known = known_of_the_device() if known is None else known
    a = assess(root, base, known)
    if a["state"] != "complete":
        return {"why": f"the chain of part 1 stored there is {a['state']}, not complete, when its {len(a['runs'])} stored run(s) are taken again"
                       + (f": {a['why'][0]}" if a.get("why") else "")}
    given: dict = {"why": ""}
    for path, now, name in ((root / "candidates.json" if candidates is None else candidates, candidates_file(a, known), "candidates.json"),
                            (root / "chain.json" if chain is None else chain, brief(dict(a, candidates_file="there")), "chain.json")):
        now = json.loads(json.dumps(now))
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            return {"why": f"{name} of part 1 is not there as a file that can be read"}
        if stored != now:
            return {"why": f"{name} of part 1 is not what its stored runs give when they are taken again"}
        given[name[:-len(".json")]] = now
    return given


def not_as_its_runs_give(root: Path, candidates: Path | None = None, chain: Path | None = None, base: dict | None = None, known: dict | None = None) -> str:
    """Why part 2 may not be built on what is stored of part 1 under `root`, or "" if it may (`taken_again`)."""
    return taken_again(root, candidates, chain, base, known)["why"]


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
                f"{bits.get('follow_inverted', '?')} inverted, {bits.get('irregular', '?')} irregular, {len(last.get('memories', []))} memory word(s) found — {last['decision']}")
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
    """What the chain is held to on the device: what the run script gives the judge of the set, and with it the six
    moves of S2.3, as its stored description has them, and the prediction made before the board was asked — neither
    needed to judge a run."""
    return dict(s1a_run.known_for(STAGE), rule=s2_4_predict.rule(json.loads(s2_5_predict.RAM_MAP.read_text())), prediction=json.loads(PREDICTION.read_text()))


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
    room = (state.get("closing") or {}).get("part_2")
    if room is not None and not room["can_be_planned"]:
        print(f"NOTE: the runs of part 2 cannot be planned over these frames as the stage is ({room['why']}): what part 1 found stands, and part 2 has no run")
    if state.get("held"):
        print(f"HELD: {state['held']}")
    print(f"{len(state['runs'])} run(s) stored of {state['shares']}; the chain: {state['state']}")
    return 0 if state["state"] in ("complete", "go on") and not state.get("blocked") else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""S1: the frame census as one document (proposal, section 4; docs/s1b_plan.md, section 68).

    s1_census.py --chain SET=DIR [--chain SET=DIR ...] [--seen NAME=PATH ...] [--also NAME=PATH ...]

prints the census as JSON (schemas/frame_census_v1.schema.json). Exit 0; 1 if an address was not read alike every
time, here or on another occasion; 2 if the census cannot be made from what it was given.

--chain  a complete chain of runs (s1b2_chain) and the set it was driven with. Every run is taken from its raw words
         and judged again. Each address the chain walked becomes an entry: the fields of its address word, the address
         named after it, every reading of its frame — in both passes and in the reads of several frames, in every run
         that read it — and whether those readings are all alike. A chain that is not complete, or whose summary over
         rows lists something unexpected, is refused: the census is made of lists that are whole.
--seen   a run that is not part of a chain (PATH: its verdict.json as its judge wrote it, or a directory holding
         one). The addresses it read that no chain walked are listed apart, as seen and not walked, with what the run
         was. An address the register showed and nothing read is listed as named and not read.
--also   other stored runs that walked addresses of the census on another occasion (PATH as for --seen, or a
         directory of runNN, or one whose directories each hold a verdict). Only runs their judges passed are used. Each is held against the entries: the same
         content or not.

What an entry stands behind is said in the document itself: that the device named the address and that its frame
read the same every time. Not what the frame holds. Nothing here is graded and no database is read; the program
knows the layout of the address word (UG470, through s1b2_row) and nothing about any part.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import s1b2_chain  # noqa: E402
import s1b2_judge  # noqa: E402
import s1b2_row  # noqa: E402
import s1b3_rows  # noqa: E402
import status_seen  # noqa: E402
from s1b3_top import ALL_ZERO  # noqa: E402

NOTES = [
    "an entry says that the device named this address after the one before it and that a frame read there came back the same at every reading listed; it does not say what the frame holds",
    "the content is the content with the design named in the binding loaded; where frames are alike (most are all zero) agreement between readings cannot tell one frame from another, and the entry rests on the address register, read after every read",
    "addresses were only ever read where the device pointed: nothing here says what a read at an address the device does not name gives",
    "nothing in this document was graded; grading is kept apart (proposal, section 3)",
]


class Refused(Exception):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def readings(verdict: dict) -> dict[str, list[tuple[int, int, str]]]:
    """Every reading of a frame in one run, by address: (record, position in that read, sha256 of the frame). A read of
    several frames is laid along the walk: its second frame is the frame of the address named after its first."""
    walk = {s["far"]: s for s in verdict["walk"]}
    out: dict[str, list[tuple[int, int, str]]] = {}
    for i, r in enumerate(verdict["records"]):
        if r["kind"] != "target":
            continue
        at = r["far"]
        for k, digest in enumerate(r["frame_sha256"]):
            if at not in walk:
                raise Refused(f"record {i}: a frame was read at {at}, which the walk of that run does not list")
            out.setdefault(at, []).append((i, k, digest))
            if k + 1 < len(r["frame_sha256"]):
                if walk[at].get("stood_still"):
                    raise Refused(f"record {i}: a read of several frames runs on past {at}, where the register stood still")
                at = walk[at]["next"]
    return out


def chain_part(stage: str, root: Path, known: dict) -> dict:
    """One complete chain: its assessment, its summary over rows, and the readings of every run."""
    import s1a_run
    if stage not in s1b2_chain.BOUNDS:
        raise Refused(f"{stage} is not a set a chain is driven with")
    stored = root / f"expected_{stage}.json"             # the set as it was when the chain was run, if it was kept with the runs
    expected = json.loads((stored if stored.exists() else s1a_run.STAGES[stage]["expected"]).read_text())
    base = [int(w, 16) for w in expected["params"]]
    a = s1b2_chain.assess(root, base, known, s1b2_chain.BOUNDS[stage], stage)
    if a["state"] != "complete":
        raise Refused(f"the chain in {root.name} is not complete ({a['state']}: {a.get('why', a.get('next_start'))})")
    rows = json.loads(json.dumps(s1b3_rows.summarize(a, known)))
    if rows["unexpected"]:
        raise Refused(f"the summary over rows of {root.name} lists something unexpected: {rows['unexpected'][:2]}")
    runs = []
    for r in a["runs"]:
        raw = (root / r["dir"] / "result.bin").read_bytes()
        v = s1b2_judge.judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1b2_chain.planned(base, int(r["start"], 16)))
        runs.append({"dir": r["dir"], "result_sha256": r["result_sha256"], "verdict": v})
    return {"set": stage, "directory": root.name, "expected": expected, "assessment": a, "rows": rows, "runs": runs}


def stored_verdicts(path: Path) -> list[tuple[str, dict]]:
    files = [path / "run" / "verdict.json"] if (path / "run" / "verdict.json").is_file() else status_seen.verdicts(path)
    if not files and path.is_dir():                      # a directory of runs under names of their own
        files = sorted(path.glob("*/verdict.json"))
    if not files:
        raise Refused(f"no verdict found at {path}")
    return [(f.parent.name if f.parent.name != "run" else f.parent.parent.name, json.loads(f.read_text())) for f in files]


def build(parts: list[dict], seen: list[tuple[str, list]] = (), also: list[tuple[str, list]] = ()) -> dict:
    """The census of the chains in `parts` (chain_part), with the runs of `seen` and `also` (name, stored_verdicts)."""
    entries: dict[str, dict] = {}
    chains, rows_out, bits, problems = [], [], [], []
    designs = {(p["expected"].get("pl_design") or {}).get("sha256") for p in parts}
    images = {p["expected"].get("image_sha256") for p in parts}
    if len(designs) != 1 or len(images) != 1 or None in designs | images:
        raise Refused(f"the chains were not all run with one design and one image: {sorted(map(str, designs))}, {sorted(map(str, images))}")
    for p in parts:
        a, rows = p["assessment"], p["rows"]
        per_run = {r["dir"]: readings(r["verdict"]) for r in p["runs"]}
        for s in rows["addresses"]:
            far = s["far"]
            if far in entries:
                raise Refused(f"{far} is walked by two of the chains given ({entries[far]['evidence']['chain']} and {p['set']})")
            reads = [[run, i, k, digest] for run, by_address in per_run.items() for i, k, digest in by_address.get(far, [])]
            contents = sorted({x[3] for x in reads})
            entry = {"far": far, **s1b2_row.fields(int(far, 16)), "state": "walked", "named_next": s["next"]}
            if s.get("stood_still"):
                entry["stood_still"] = True
            entry.update(readings=len(reads), distinct_contents=len(contents), stable=len(contents) == 1, all_zero=contents == [ALL_ZERO],
                         frame_sha256=contents[0] if len(contents) == 1 else contents,
                         evidence={"chain": p["set"], "reads": [x[:3] for x in reads]})
            if s["frame_sha256"] not in contents:
                raise Refused(f"{far}: the chain's list has a frame that none of its readings is")
            entries[far] = entry
        chains.append({"set": p["set"], "directory": p["directory"], "state": a["state"], "runs": len(a["runs"]), "addresses": rows["frames"],
                       "first": rows["addresses"][0]["far"], "last": rows["end"]["last_frame"], "named_after_the_last_frame": rows["end"]["named_after_the_last_frame"],
                       "known_frames_walked": rows["known_frames_walked"],
                       "results_sha256": hashlib.sha256("".join(r["result_sha256"] for r in p["runs"]).encode()).hexdigest()})
        rows_out += [{"chain": p["set"], **{k: r[k] for k in ("block_type", "half", "row", "first", "last", "frames", "ended_by", "named_after_the_last_frame")},
                      "columns": r["frames_per_column"]} for r in rows["rows"]]
        shown: dict[int, dict] = {}
        for r in p["runs"]:                              # status bits that are neither an error nor usual, as status_seen lists them
            for b in status_seen.seen(r["verdict"])["bits"]:
                one = shown.setdefault(b["bit"], {"bit": b["bit"], "name": b["name"], "chain": p["set"], "runs": [], "first_shown_at": []})
                one["runs"].append(r["dir"])
                one["first_shown_at"].append([r["dir"], b["first"].get("record"), b["first"].get("far")])
        bits += [shown[b] for b in sorted(shown)]
    ordered = sorted(entries.values(), key=lambda e: int(e["far"], 16))

    # ---- runs that are not part of a chain: what they read that no chain walked, and what the register showed
    seen_out, register_showed = [], {}
    for p in parts:
        register_showed[p["rows"]["end"]["named_after_the_last_frame"]] = f"named after {p['rows']['end']['last_frame']}, the last frame of the chain {p['set']}"
    for name, verdicts in seen:
        for run, v in verdicts:
            what = {"name": name, "run": run, "verdict": v.get("verdict"), "status": (v.get("header") or {}).get("status")}
            got: dict[str, list] = {}
            for i, r in enumerate(v.get("records") or []):
                if r["kind"] != "target":
                    continue
                if len(r["frame_sha256"]) > 1:
                    raise Refused(f"{name}: record {i} is a read of several frames; a run listed as seen is taken frame by frame only")
                for digest in r["frame_sha256"]:
                    got.setdefault(r["far"], []).append([i, digest])
                register_showed.setdefault(r["far_read_back"], f"in the address register after record {i} of {name} (a read at {r['far']})")
            for far, reads in got.items():
                if far in entries:
                    continue
                contents = sorted({d for _, d in reads})
                seen_out.append({"far": far, **s1b2_row.fields(int(far, 16)), "state": "seen", "readings": len(reads), "distinct_contents": len(contents),
                                 "all_zero": contents == [ALL_ZERO], "frame_sha256": contents[0] if len(contents) == 1 else contents,
                                 "evidence": {**what, "records": [i for i, _ in reads]}})
    read = set(entries) | {e["far"] for e in seen_out}
    named = [{"far": far, **s1b2_row.fields(int(far, 16)), "state": "named", "seen": how}
             for far, how in sorted(register_showed.items(), key=lambda x: int(x[0], 16)) if far not in read]

    # ---- the same addresses on other occasions
    also_out = []
    for name, verdicts in also:
        used, not_used, same, different, addresses = [], [], 0, [], set()
        for run, v in verdicts:
            if v.get("verdict") != "PASS":
                not_used.append(run); continue
            used.append(run)
            for s in v.get("walk") or []:
                e = entries.get(s["far"])
                if e is None:
                    continue
                addresses.add(s["far"])
                if s["frame_sha256"] == e["frame_sha256"]:
                    same += 1
                else:
                    different.append({"far": s["far"], "run": run, "there": s["frame_sha256"], "census": e["frame_sha256"]})
        also_out.append({"name": name, "runs_used": len(used), "runs_not_used": not_used, "addresses": len(addresses), "readings_alike": same, "different": different})
        if different:
            problems.append(f"{name}: {len(different)} reading(s) of another occasion differ from the census")

    not_stable = [e["far"] for e in ordered if not e["stable"]]
    if not_stable:
        problems.append(f"{len(not_stable)} address(es) were not read alike every time; the first is {not_stable[0]}")
    by_type: dict[int, int] = {}
    for e in ordered:
        by_type[e["block_type"]] = by_type.get(e["block_type"], 0) + 1
    return {
        "schema": "frame_census", "schema_version": "1.0.0", "label": "closed-book",
        "binding": {"pl_design_sha256": designs.pop(), "prober_image_sha256": images.pop(), "chains": chains},
        "address_word": "UG470, table 5-24: block type bits 25..23, half bit 22 (0 top, 1 bottom), row bits 21..17, column bits 16..7, minor bits 6..0",
        "totals": {"addresses": len(ordered), "by_block_type": [[t, by_type[t]] for t in sorted(by_type)], "readings": sum(e["readings"] for e in ordered),
                   "fewest_readings_of_an_address": min((e["readings"] for e in ordered), default=0), "not_stable": len(not_stable),
                   "all_zero": sum(1 for e in ordered if e["all_zero"]), "distinct_contents_that_are_not_zero": len({e["frame_sha256"] for e in ordered if e["stable"] and not e["all_zero"]}),
                   "seen_not_walked": len(seen_out), "named_not_read": len(named)},
        "rows": rows_out, "status_bits": bits, "other_occasions": also_out, "problems": problems, "notes": NOTES,
        "entries": ordered, "seen_not_walked": seen_out, "named_not_read": named,
    }


def dump(census: dict) -> str:
    """The document as text: the lists of addresses one entry a line, the rest indented."""
    long = ("entries", "seen_not_walked", "named_not_read", "rows")
    head = json.dumps({k: v for k, v in census.items() if k not in long}, indent=1)
    parts = [head[:-2]]
    for k in long:
        lines = ",\n".join("  " + json.dumps(e) for e in census[k])
        parts.append(f' "{k}": [\n{lines}\n ]' if census[k] else f' "{k}": []')
    return ",\n".join(parts) + "\n}\n"


def main(argv: list[str] | None = None) -> int:
    import s1a_run
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", action="append", default=[], metavar="SET=DIR")
    ap.add_argument("--seen", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--also", action="append", default=[], metavar="NAME=PATH")
    a = ap.parse_args(argv)
    known = json.loads(s1a_run.KNOWN.read_text())
    try:
        if not a.chain or not all("=" in x for x in a.chain + a.seen + a.also):
            raise Refused("at least one --chain SET=DIR; every argument as NAME=PATH")
        split = lambda xs: [(x.split("=", 1)[0], Path(x.split("=", 1)[1])) for x in xs]     # noqa: E731
        parts = [chain_part(stage, root, known) for stage, root in split(a.chain)]
        census = build(parts, [(n, stored_verdicts(p)) for n, p in split(a.seen)], [(n, stored_verdicts(p)) for n, p in split(a.also)])
    except Refused as e:
        print(f"REFUSED: {e}"); return 2
    sys.stdout.write(dump(census))
    return 1 if census["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""S1b.2b: what the reads at the end of the row say (docs/s1b_plan.md, section 29).

    s1b2_end.py <verdict.json of s1b2e> [<verdict.json of s1b2c> <verdict.json of the walk that stopped in that column>]

It takes verdicts as the judges wrote them (s1b2e_judge for the two table runs; s1b2_judge for the walk) and lays
them out. Nothing is read from a board and nothing from a database.

The end (s1b2e). Each read starts at an address written to the register and clocks out the pad and some frames; the
register is read afterwards. "Steps" below is the number of frames of words clocked out, the pad included.

  - Are the starting addresses one step apart, by the device's own word (after the pad alone at one, the register
    holds the next)? If so they are positions 0, 1, 2, ... of a line, and a read that starts at position i and moves
    the register k steps ends at position i + k, whichever start it came from.
  - The register at each position, from every read that ends there — and whether they agree.
  - What was delivered at each position (a read of n frames from position i delivers positions i .. i + n - 1), from
    every read that delivered it — and whether they agree; whether it is all zero.
  - Beyond the last address written: the values the register showed, step by step, and at which steps it did not
    change.

The column again (s1b2c), if given: every frame its reads of three delivered, held against the frame the walk
delivered at that address. Which address a frame of such a read belongs to is taken from the walk's own account of
what follows what, not from arithmetic.

There is no expected value in this program for anything the register shows or a read delivers. What it requires is
that two ways to the same position agree; a disagreement is listed under "disagreements" and the exit code is 1.
Where every frame delivered is the same, agreement about content says nothing about which position was read, and
the output says so.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FRAME_WORDS = 101
ALL_ZERO = hashlib.sha256(bytes(4 * FRAME_WORDS)).hexdigest()


def target_reads(verdict: dict) -> dict:
    """(address, steps) -> what every repeat of that read left: the register values, and the frames delivered."""
    out: dict = {}
    for r in verdict.get("records", []):
        if r["kind"] != "target" or not r["words"]:      # an operation that reads nothing moves nothing
            continue
        e = out.setdefault((int(r["far"], 16), r["words"] // FRAME_WORDS), {"register": [], "frames": [], "codes": []})
        e["register"].append(r["far_read_back"]); e["frames"].append(r["frame_sha256"]); e["codes"].append(r["code"])
    return out


def of_run(verdict: dict) -> dict:
    return {"verdict": verdict.get("verdict"), "status": verdict.get("header", {}).get("status"), "problems": verdict.get("problems", []),
            "polling_loop": verdict.get("params", {}).get("diagnostic", {}).get("polling_loop")}


def end(verdict: dict) -> dict:
    out: dict = {"run": of_run(verdict), "disagreements": []}
    odd = out["disagreements"].append
    if verdict.get("verdict") != "PASS":
        out["note"] = "the judge did not pass this run: what follows is laid out from its records all the same, and is not a finding"
    reads = target_reads(verdict)
    for (far, steps), e in sorted(reads.items()):        # the judge requires it of a passing run; said again for one that did not pass
        if len(set(e["register"])) != 1 or len({tuple(f) for f in e["frames"]}) != 1:
            odd(f"the read of {steps} step(s) at {far:#010x} did not leave the same thing every time")
    starts = sorted({far for far, _ in reads})
    out["starting_addresses"] = [f"{a:#010x}" for a in starts]
    out["reads"] = [{"at": f"{far:#010x}", "steps": steps, "frames_delivered": steps - 1, "times": len(e["register"]), "register_afterwards": sorted(set(e["register"]))}
                    for (far, steps), e in sorted(reads.items())]
    # ---- are the starting addresses a line, one step apart by the device's own word?
    apart = [reads.get((a, 1), {}).get("register", [None])[0] == f"{b:#010x}" for a, b in zip(starts, starts[1:])]
    out["starting_addresses_one_step_apart"] = bool(starts) and all(apart)
    if not out["starting_addresses_one_step_apart"]:
        out["note_on_positions"] = "the starting addresses are not shown to be one step apart: no positions are derived"
        return out
    index = {a: i for i, a in enumerate(starts)}
    last = len(starts) - 1
    # ---- the register at each position
    at: dict[int, dict[str, list]] = {}
    for (far, steps), e in sorted(reads.items()):
        for value in sorted(set(e["register"])):
            at.setdefault(index[far] + steps, {}).setdefault(value, []).append([f"{far:#010x}", steps])
    positions = []
    for p in range(max(at) + 1 if at else 0):
        values = at.get(p, {})
        row = {"position": p, "beyond_the_last_address_written": max(0, p - last), "address_written": f"{starts[p]:#010x}" if p <= last else None,
               "register": sorted(values), "reached_by": sorted(w for ways in values.values() for w in ways), "agree": len(values) <= 1}
        if len(values) > 1:
            odd(f"position {p}: the register read " + ", ".join(f"{v} after {ways}" for v, ways in sorted(values.items())))
        if p <= last and values and sorted(values) != [f"{starts[p]:#010x}"]:
            odd(f"position {p} is the address written {starts[p]:#010x}, yet the register read {sorted(values)} on arriving there")
        positions.append(row)
    out["positions"] = positions
    # ---- what was delivered at each position
    got: dict[int, dict[str, list]] = {}
    for (far, steps), e in sorted(reads.items()):
        for digests in {tuple(f) for f in e["frames"]}:
            for j, h in enumerate(digests):
                got.setdefault(index[far] + j, {}).setdefault(h, []).append([f"{far:#010x}", steps])
    delivered = []
    for p in sorted(got):
        hashes = got[p]
        delivered.append({"position": p, "beyond_the_last_address_written": max(0, p - last), "address_written": f"{starts[p]:#010x}" if p <= last else None,
                          "frame_sha256": sorted(hashes), "all_zero": sorted(hashes) == [ALL_ZERO], "delivered_by": sorted(w for ways in hashes.values() for w in ways),
                          "ways": sum(len(ways) for ways in hashes.values()), "agree": len(hashes) == 1})
        if len(hashes) > 1:
            odd(f"position {p}: the frames delivered there differ: " + ", ".join(f"{h[:12]}… by {ways}" for h, ways in sorted(hashes.items())))
    out["delivered"] = delivered
    distinct = {h for d in delivered for h in d["frame_sha256"]}
    out["distinct_contents_delivered"] = len(distinct)
    if len(distinct) <= 1 and delivered:
        out["note_on_content"] = ("every frame delivered is the same" + (" (all zero)" if distinct == {ALL_ZERO} else "") +
                                  ": that two reads delivered the same content says nothing about which position either of them read")
    # ---- beyond the last address written
    shown = [(p["position"], p["register"]) for p in positions if p["position"] >= last and p["register"]]
    beyond = {"last_address_written": f"{starts[last]:#010x}",
              "register_step_by_step": [{"steps_beyond": p - last, "register": v[0] if len(v) == 1 else v} for p, v in shown if p > last],
              "frames_delivered_from_beyond": [{"steps_beyond": d["position"] - last, "frame_sha256": d["frame_sha256"], "all_zero": d["all_zero"], "ways": d["ways"]}
                                               for d in delivered if d["position"] > last]}
    line = [f"{starts[last]:#010x}"] + [v[0] if len(v) == 1 else None for p, v in shown if p > last]
    beyond["steps_at_which_the_register_did_not_change"] = [k for k in range(1, len(line)) if line[k] is not None and line[k] == line[k - 1]]
    out["beyond"] = beyond
    return out


def column(again: dict, walk: dict, end_verdict: dict | None = None) -> dict:
    out: dict = {"run": of_run(again), "walk": {"verdict": walk.get("verdict"), "status": walk.get("header", {}).get("status")}, "disagreements": []}
    odd = out["disagreements"].append
    if again.get("verdict") != "PASS":
        out["note"] = "the judge did not pass this run: what follows is laid out from its records all the same, and is not a finding"
    walked = {s["far"]: s for s in walk.get("walk", [])}
    reads = target_reads(again)
    compared, same, seen, not_walked, register = 0, 0, set(), [], []
    for (far, steps), e in sorted(reads.items()):
        if len(set(e["register"])) != 1 or len({tuple(f) for f in e["frames"]}) != 1:
            odd(f"the read of {steps} step(s) at {far:#010x} did not leave the same thing every time")
        where = f"{far:#010x}"                           # the address of each frame of the read: the walk's own account of what follows what
        for h in e["frames"][0]:
            s = walked.get(where)
            if s is None:
                not_walked.append({"read_at": f"{far:#010x}", "frame_sha256": h}); break
            compared += 1; seen.add(where)
            if s["frame_sha256"] == h:
                same += 1
            else:
                odd(f"the frame at {where}: the read of {steps - 1} frames from {far:#010x} delivered {h[:12]}…, the walk {s['frame_sha256'][:12]}…")
            where = s["next"] if s["next"] != where else None      # an address that names itself: the walk says nothing of what follows it
        # the register afterwards, held against the walk's successors where they reach that far
        where, reaches = f"{far:#010x}", True
        for _ in range(steps):
            s = walked.get(where)
            if s is None or s["next"] == where:
                reaches = False; break
            where = s["next"]
        register.append({"at": f"{far:#010x}", "steps": steps, "register_afterwards": sorted(set(e["register"])),
                         "the_walk_says": where if reaches else None, "as_the_walk_says": (sorted(set(e["register"])) == [where]) if reaches else None})
        if reaches and sorted(set(e["register"])) != [where]:
            odd(f"after {steps} step(s) from {far:#010x} the register read {sorted(set(e['register']))}; by the walk's successors it is {where}")
    out.update(frames_the_walk_delivered=len(walked), frames_compared=compared, same=same,
               addresses_of_the_walk_not_read_again=sorted(set(walked) - seen), frames_at_places_the_walk_did_not_reach=not_walked, register=register)
    distinct = {s["frame_sha256"] for s in walked.values()} | {h for e in reads.values() for f in e["frames"] for h in f}
    out["distinct_contents"] = len(distinct)
    if len(distinct) <= 1 and compared:
        out["note_on_content"] = ("every frame is the same" + (" (all zero)" if distinct == {ALL_ZERO} else "") +
                                  ": that the two paths delivered the same content says nothing about which frame either of them read")
    if end_verdict is not None:                          # a read made in both table runs left the same thing in both
        theirs = target_reads(end_verdict)
        both = sorted(set(reads) & set(theirs))
        out["reads_also_made_at_the_end"] = [{"at": f"{far:#010x}", "steps": steps} for far, steps in both]
        for key in both:
            if set(reads[key]["register"]) != set(theirs[key]["register"]) or {tuple(f) for f in reads[key]["frames"]} != {tuple(f) for f in theirs[key]["frames"]}:
                odd(f"the read of {key[1]} step(s) at {key[0]:#010x} left something else in the run at the end of the row")
    return out


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4):
        print(__doc__); return 2
    first = json.loads(Path(argv[1]).read_text())
    out = {"the_end": end(first)}
    if len(argv) == 4:
        out["the_column_again"] = column(json.loads(Path(argv[2]).read_text()), json.loads(Path(argv[3]).read_text()), first)
    print(json.dumps(out, indent=1))
    return 1 if any(part["disagreements"] or part["run"]["verdict"] != "PASS" for part in out.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

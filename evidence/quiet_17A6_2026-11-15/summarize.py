#!/usr/bin/env python3
"""summary.json of the series of the three waits, 2026-11-15, from the stored results: every result.bin is judged
again (stage 4 by the walk's judge, stage 5 by the diagnostic judge) and counted by the wait that was used and by
where the polling variable lay. Kept with the evidence; `--check` compares with the stored summary instead of
writing it."""
import hashlib, json, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "host"))
import dx_judge, s1b1_judge  # noqa: E402

KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())
SETS = ("dxs10", "dxs10n", "dxs10r", "dxw0", "dxw0n", "dxw0r")
WAIT = {0: "as before", 1: "no stores", 2: "no stack"}
EXPECTED_ONLY = ("no known answer", "did not complete", "anomalous read")     # a stage-5 run reads frames nobody knows; a stopped run says so


def summary() -> dict:
    runs, places = [], {}
    for k in (1, 2, 3):
        for name in SETS:
            d = HERE / f"{name}_run{k:02d}"
            raw = (d / "result.bin").read_bytes()
            words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
            planned = [int(w, 16) for w in json.loads((HERE / f"expected_{name}.json").read_text())["params"]]
            v = (s1b1_judge if name.startswith("dxw") else dx_judge).judge(words, KNOWN, planned)
            run = json.loads((d / "run.json").read_text())
            stopped = None
            wait = WAIT[planned[15] >> 8]
            for address, s in sorted(v["polling_variable"].items()):
                p = places.setdefault(wait, {}).setdefault(address, {"address_mod_32": s["address_mod_32"], "frame_reads": 0, "pad_only_reads": 0, "overflows": 0, "in": []})
                p["frame_reads"] += s["frame_reads"]; p["pad_only_reads"] += s["pad_only_reads"]
                for i in s["interface_failures"]:
                    r = v["records"][i]
                    p["overflows"] += 1; p["in"].append(f"{name}_run{k:02d}")
                    stopped = {"record": i, "polling_variable_at": address, "far": r["far"], "frames_asked": r["frames"],
                               "code": r["code"], "int_sts": r["int_sts"]}
            runs.append({"run": f"{name}_run{k:02d}", "wait": wait, "result_sha256": hashlib.sha256(raw).hexdigest(), "status": v["header"]["status"], "records": len(v["records"]),
                         "verdict": v["verdict"], "problems_other_than_expected": [p for p in v["problems"] if not any(h in p for h in EXPECTED_ONLY)],
                         "stopped": stopped, "pieces_pulled_again": len(run["pull"]["repeated"]), "card_verified": run["card_verified"]})
    by_wait = {}
    for wait, there in places.items():
        for address, p in there.items():
            t = by_wait.setdefault(wait, {}).setdefault(str(p["address_mod_32"]), {"addresses": [], "reads": 0, "overflows": 0})
            t["addresses"].append(address); t["reads"] += p["frame_reads"] + p["pad_only_reads"]; t["overflows"] += p["overflows"]
    return {"runs": runs, "by_wait_and_polling_variable_address": {w: dict(sorted(v.items())) for w, v in places.items()}, "by_wait_and_address_mod_32": by_wait}


if __name__ == "__main__":
    s = json.dumps(summary(), indent=1) + "\n"
    if "--check" in sys.argv:
        sys.exit(0 if (HERE / "summary.json").read_text() == s else 1)
    (HERE / "summary.json").write_text(s)

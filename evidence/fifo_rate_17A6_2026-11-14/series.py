#!/usr/bin/env python3
"""The series of counting runs of 2026-11-14, as it was driven: the stages named (rate1 and rate3 by default) in turn,
a U-Boot `reset` before each.
Kept with the evidence to say how it was produced; it is not part of the instrument. The series halts at the first
thing that is not one of: a judged run (PASS, or FAIL on an interface stop), or a run whose pulls all came back damaged."""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
os.environ["SELFMAP_CONSOLE_LOG"] = str(HERE / "resets_console.log")
sys.path.insert(0, str(ROOT / "host"))
from uboot_console import UB  # noqa: E402

first, last = int(sys.argv[1]), int(sys.argv[2])
for k in range(first, last + 1):
    for stage in (sys.argv[3:] or ["rate1", "rate3"]):
        out = HERE / f"{stage}_run{k:02d}"
        if out.exists():
            continue
        u = UB()
        _, ok = u.interrupt()
        reply, ok2 = u.cmd("reset", 40) if ok else (b"", False)
        sts, ok3 = u.cmd("md.l f800700c 1", 10) if ok2 else (b"", False)
        u.s.close(); u.log.close()
        if not (ok and ok2 and ok3) or b"Ebang EBAZ4203" not in reply or b"a802000" not in sts:
            print(f"HALT before {stage} run {k}: reset did not give the usual fresh prompt", flush=True); sys.exit(1)
        t0 = time.time()
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), "--stage", stage, "--go", "--out", str(out)], capture_output=True, text=True)
        (HERE / f"{stage}_run{k:02d}.out").write_text(r.stdout + r.stderr)
        rec = json.loads((out / "run.json").read_text()) if (out / "run.json").exists() else {}
        line = {"stage": stage, "run": k, "seconds": round(time.time() - t0), "went": rec.get("went"), "console": (rec.get("console") or [None])[-1],
                "judge": rec.get("judge"), "verdict": rec.get("verdict"), "pulls": [p["is_the_boards"] for p in rec.get("pulls", [])],
                "card_verified": rec.get("card_verified"), "stop": rec.get("stop")}
        print(json.dumps(line), flush=True)
        if not rec.get("went") or (rec.get("stop") and "pulled copies" not in rec["stop"]):
            print(f"HALT after {stage} run {k}: not a run this series knows how to count", flush=True); sys.exit(1)

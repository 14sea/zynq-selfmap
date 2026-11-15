#!/usr/bin/env python3
"""The series of the three waits, 2026-11-15 (docs/s1b_plan.md, sections 20 and 21), as it was driven: rounds first..last,
in each the six sets in the order below (or those named), a U-Boot `reset` before every run.
Kept with the evidence to say how it was produced; it is not part of the instrument. The series halts at the first
run that did not go, or that the run script stopped for any reason: nothing is retried here."""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
os.environ["SELFMAP_CONSOLE_LOG"] = str(HERE / "resets_console.log")
sys.path.insert(0, str(ROOT / "host"))
from uboot_console import UB  # noqa: E402

first, last = int(sys.argv[1]), int(sys.argv[2])
for k in range(first, last + 1):
    for stage in (sys.argv[3:] or ["dxs10", "dxs10n", "dxs10r", "dxw0", "dxw0n", "dxw0r"]):
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
        pull = rec.get("pull") or {}
        line = {"stage": stage, "run": k, "seconds": round(time.time() - t0), "went": rec.get("went"), "console": (rec.get("console") or [None])[-1],
                "judge": rec.get("judge"), "verdict": rec.get("verdict"), "pieces": pull.get("pieces"), "pieces_repeated": len(pull.get("repeated", [])),
                "card_verified": rec.get("card_verified"), "int_sts_afterwards": rec.get("int_sts_afterwards"), "stop": rec.get("stop")}
        print(json.dumps(line), flush=True)
        if not rec.get("went") or rec.get("stop"):
            print(f"HALT after {stage} run {k}: the run script stopped", flush=True); sys.exit(1)

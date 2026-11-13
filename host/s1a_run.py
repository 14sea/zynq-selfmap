#!/usr/bin/env python3
"""The S1a board run: exactly what the host types into U-Boot, in order.

    s1a_run.py --dry-run          print the whole plan and exit; touches no serial port
    s1a_run.py --go --out DIR     run it (refuses unless the image on disk is the one tests fixed)

The plan is built once by plan() and both modes use it, so what is reviewed is what runs.
The run stops at the first step whose check fails; nothing is retried.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "build" / "prober" / "expected.json"
IMAGE = ROOT / "build" / "prober" / "prober.bin"
PL = ROOT / "build" / "pl" / "carrier.bit"
PL_ADDR, IMG_ADDR, RES_ADDR, PAR_ADDR = 0x04000000, 0x02000000, 0x10000000, 0x10100000


def plan(exp: dict, pl_bytes: int, pl_crc: str) -> list[dict]:
    p: list[dict] = []
    add = lambda what, cmd, check, **kw: p.append({"what": what, "cmd": cmd, "check": check, **kw})  # noqa: E731
    add("prompt", "version", "U-Boot answers")
    add("cache off (the verified run had it off; the prober refuses otherwise)", "dcache off", "prompt")
    add("cache state", "dcache", "says the data cache is OFF", expect=r"Data \(writethrough\) Cache is OFF")
    add("status before the PL load", "md.l f800700c 1", "recorded")
    add("clear the sticky PCFG_DONE bit so that the load is seen as an edge (as the verified run did)", "mw.l f800700c 00000004 1", "prompt")
    add("status after the clear", "md.l f800700c 1", "bit 2 clear", bit_clear=("f800700c", 2))
    add(f"send the PL design ({pl_bytes} bytes, sha256 {exp['pl_design']['sha256'][:8]}…) by YMODEM", f"loady {PL_ADDR:08x}", "U-Boot reports the same size", ymodem=str(PL), size=pl_bytes)
    add("the design in RAM is the file", f"crc32 {PL_ADDR:08x} {pl_bytes:x}", f"crc32 {pl_crc}", crc=pl_crc)
    add("configure the PL", f"fpga loadb 0 {PL_ADDR:08x} {pl_bytes:x}", "no error", timeout=60)
    add("status after the load", "md.l f800700c 1", "bit 2 (PCFG_DONE) set", bit_set=("f800700c", 2))
    for i, w in enumerate(exp["params"]):
        if int(w, 16) or i < 16:
            add(f"parameter word {i}", f"mw.l {PAR_ADDR + 4 * i:08x} {w} 1", "prompt")
    par_crc = f"{zlib.crc32(b''.join(struct.pack('<I', int(w, 16)) for w in exp['params'])) & 0xFFFFFFFF:08x}"
    add("zero the rest of the parameter block first", f"mw.l {PAR_ADDR:08x} 0 20", "prompt", before_params=True)
    add("the parameter block is as intended", f"crc32 {PAR_ADDR:08x} 80", f"crc32 {par_crc}", crc=par_crc)
    add("clear the result header", f"mw.l {RES_ADDR:08x} 0 40", "prompt")
    add(f"send the prober ({exp['image_bytes']} bytes) by YMODEM", f"loady {IMG_ADDR:08x}", "U-Boot reports the same size", ymodem=str(IMAGE), size=exp["image_bytes"])
    add("the prober in RAM is the checked image", f"crc32 {IMG_ADDR:08x} {exp['image_bytes']:x}", f"crc32 {exp['image_crc32']}", crc=exp["image_crc32"])
    add("RUN", f"go {IMG_ADDR:08x}", "the two console lines and rc = 0x0", go=True, timeout=30)
    add("result header", f"md.l {RES_ADDR:08x} 40", "magic, status 1", header=True)
    add("result checksum on the board", f"crc32 {RES_ADDR:08x} {exp['result_words'] * 4:x}", "recorded", result_crc=True)
    add("save the result to the card", f"fatwrite mmc 0:1 {RES_ADDR:08x} s1a_0001.bin {exp['result_words'] * 4:x}", "bytes written")
    add("pull the result over the console", f"md.l {RES_ADDR:08x} {exp['result_words']:x}", "host copy has the board's crc32", dump=True, timeout=120)
    add("status afterwards", "md.l f800700c 1", "bit 2 still set", bit_set=("f800700c", 2))
    add("U-Boot still answers", "version", "U-Boot answers")
    # the zeroing step belongs before the parameter words
    z = [s for s in p if s.get("before_params")][0]; p.remove(z)
    first = next(i for i, s in enumerate(p) if s["what"].startswith("parameter word"))
    p.insert(first, z)
    return p


def md_words(text: str) -> list[int]:
    words: list[int] = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{8}):((?: [0-9a-f]{8}){1,4})", line.strip())
        if m:
            words += [int(x, 16) for x in m.group(2).split()]
    return words


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    exp = json.loads(EXPECTED.read_text())
    img, pl = IMAGE.read_bytes(), PL.read_bytes()
    if hashlib.sha256(img).hexdigest() != exp["image_sha256"]:
        print("REFUSED: the image on disk is not the one the tests fixed in expected.json"); return 2
    if hashlib.sha256(pl).hexdigest() != exp["pl_design"]["sha256"] or len(pl) != exp["pl_design"]["bytes"]:
        print("REFUSED: the staged PL design is not the one the known frames were read with"); return 2
    steps = plan(exp, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}")
    if a.dry_run or not a.go:
        print(f"image {exp['image_sha256']}  ({exp['image_bytes']} bytes)")
        print(f"PL    {exp['pl_design']['sha256']}  ({len(pl)} bytes)\n")
        for i, s in enumerate(steps, 1):
            print(f"{i:3d}. {s['cmd']:44s} # {s['what']}  ->  {s['check']}")
        print("\nDry run: nothing was sent.")
        return 0
    if not a.out or a.out.exists():
        print("REFUSED: --out must name a directory that does not exist yet"); return 2
    a.out.mkdir(parents=True)
    os.environ["SELFMAP_CONSOLE_LOG"] = str(a.out / "console.log")
    sys.path.insert(0, str(ROOT / "host"))
    import serial
    from uboot_console import UB, DEV
    from s1a_judge import judge
    u = UB(); record: dict = {"expected": exp, "steps": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    def stop(why: str) -> int:
        record["stop"] = why; (a.out / "run.json").write_text(json.dumps(record, indent=1) + "\n")
        print("STOP:", why); return 1

    buf, ok = u.interrupt(tries=3)
    if not ok:
        return stop("no U-Boot prompt")
    board_crc = None
    for i, s in enumerate(steps, 1):
        if "ymodem" in s:
            u.s.reset_input_buffer(); u.tx(s["cmd"].encode() + b"\r")
            end = time.time() + 8; got = b""
            while time.time() < end and b"## Ready for binary (ymodem) download" not in got:
                d = u.s.read(4096); got += d; u.log.write(d)
            if b"## Ready for binary" not in got:
                return stop(f"step {i}: loady did not become ready")
            time.sleep(0.5); u.s.close()
            with open(DEV, "rb+", buffering=0) as port:
                r = subprocess.run(["sb", "-k", s["ymodem"]], stdin=port, stdout=port, stderr=subprocess.PIPE, timeout=900)
            u.s = serial.Serial(DEV, 115200, timeout=0.1)
            out, ok = u.until_prompt(20)
            m = re.search(rb"## Total Size\s+= 0x([0-9a-fA-F]+)", out)
            text = out.decode("utf-8", "replace")
            if r.returncode or not ok or not m or int(m.group(1), 16) != s["size"]:
                record["steps"].append({"n": i, **s, "reply": text[-400:]}); return stop(f"step {i}: YMODEM transfer")
        else:
            out, ok = u.cmd(s["cmd"], s.get("timeout", 10)); text = out.decode("utf-8", "replace")
        entry = {"n": i, "what": s["what"], "cmd": s["cmd"], "reply": text if len(text) < 2000 else text[:300] + " … " + text[-300:]}
        record["steps"].append(entry); print(f"[{i:3d}] {s['cmd'][:60]}")
        if not ok:
            return stop(f"step {i}: no prompt after {s['cmd']!r}")
        if "expect" in s and not re.search(s["expect"], text):
            return stop(f"step {i}: {s['check']}")
        for key, want in (("bit_set", True), ("bit_clear", False)):
            if key in s:
                w = md_words(text)
                if not w or bool(w[0] >> s[key][1] & 1) != want:
                    return stop(f"step {i}: {s['check']} (read {w[0]:08x})" if w else f"step {i}: no value read")
        if "crc" in s or s.get("result_crc"):
            m = re.search(r"==> ([0-9a-f]{8})", text)
            if not m:
                return stop(f"step {i}: no crc32 in the reply")
            if "crc" in s and m.group(1) != s["crc"]:
                return stop(f"step {i}: crc32 {m.group(1)}, expected {s['crc']}")
            if s.get("result_crc"):
                board_crc = m.group(1)
        if s.get("go"):
            lines = [ln.strip() for ln in text.splitlines()]
            entry["console_ok"] = all(c in lines for c in exp["console"]); entry["returned"] = "## Application terminated, rc = 0x0" in text
            if not entry["returned"]:
                return stop(f"step {i}: the prober did not return 0: {text[-300:]!r}")
            if not entry["console_ok"]:
                return stop(f"step {i}: console lines differ: {text[-300:]!r}")
        if s.get("header"):
            w = md_words(text)
            if len(w) < 8 or w[0] != 0x31524D53 or w[5] != exp["result_words"]:
                return stop(f"step {i}: result header unexpected: {[f'{x:08x}' for x in w[:8]]}")
        if s.get("dump"):
            w = md_words(text)
            if len(w) != exp["result_words"]:
                return stop(f"step {i}: pulled {len(w)} words, expected {exp['result_words']}")
            raw = b"".join(struct.pack("<I", x) for x in w); (a.out / "result.bin").write_bytes(raw)
            host_crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
            if host_crc != board_crc:
                return stop(f"step {i}: the pulled copy has crc32 {host_crc}, the board said {board_crc}")
            record["result_crc32"] = host_crc
            verdict = judge(w, json.loads((ROOT / "data" / "known_frames_17A6.json").read_text()))
            (a.out / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n"); record["verdict"] = verdict["verdict"]
    (a.out / "run.json").write_text(json.dumps(record, indent=1) + "\n")
    print("verdict:", record.get("verdict"))
    return 0 if record.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

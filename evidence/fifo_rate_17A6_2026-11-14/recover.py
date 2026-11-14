#!/usr/bin/env python3
"""Fetch the result of a run whose console pulls all came back damaged — read-only, from the card file the run wrote
and verified. The dump is taken in pieces, each checked against the board's own crc32 of that piece and asked for
again if it differs; the whole must then have the crc32 the board gave for the result. Kept with the evidence to say
how the recovered copies were produced; it is not part of the instrument.

    recover.py <run directory> <stage>
"""
import json, os, re, struct, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
run = Path(sys.argv[1]).resolve(); stage = sys.argv[2]
out = run.parent / (run.name + "_recovered"); out.mkdir(exist_ok=True)
os.environ["SELFMAP_CONSOLE_LOG"] = str(out / "console.log")
sys.path.insert(0, str(ROOT / "host"))
import s1a_run  # noqa: E402
from uboot_console import UB  # noqa: E402

rec = json.loads((run / "run.json").read_text())
name, total, want = rec["card_file"], rec["result_words"], rec["board_crc32"]
u = UB(); _, ok = u.interrupt(); assert ok


def cmd(c, t=30):
    o, ok = u.cmd(c, t); assert ok, c
    return o.decode("utf-8", "replace")


note = {"card_file": name, "words": total, "board_crc32": want, "pieces": []}
note["card_bytes"] = int(re.search(r"(\d+) bytes read", cmd(f"fatload mmc 0:1 11000000 {name}", 60)).group(1))
note["card_crc32"] = re.search(r"==> ([0-9a-f]{8})", cmd(f"crc32 11000000 {4 * total:x}")).group(1)
assert note["card_bytes"] == 4 * total and note["card_crc32"] == want, note
PIECE = 2048
words = []
for at in range(0, total, PIECE):
    n = min(PIECE, total - at)
    piece_crc = re.search(r"==> ([0-9a-f]{8})", cmd(f"crc32 {0x11000000 + 4 * at:08x} {4 * n:x}")).group(1)
    for attempt in range(1, 9):
        got = s1a_run.md_words(cmd(f"md.l {0x11000000 + 4 * at:08x} {n:x}", 120))
        crc = f"{zlib.crc32(b''.join(struct.pack('<I', x) for x in got)) & 0xFFFFFFFF:08x}"
        if len(got) == n and crc == piece_crc:
            break
    else:
        print("a piece could not be pulled whole in 8 attempts:", hex(at)); sys.exit(1)
    note["pieces"].append({"at": at, "words": n, "crc32": piece_crc, "attempts": attempt})
    words += got
raw = b"".join(struct.pack("<I", x) for x in words)
note["host_crc32"] = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
(out / "recover.json").write_text(json.dumps(note, indent=1) + "\n")
assert note["host_crc32"] == want and len(words) == total, note["host_crc32"]
(out / "result.bin").write_bytes(raw)
exp = json.loads(s1a_run.STAGES[stage]["expected"].read_text())
v = s1a_run.STAGES[stage]["judge"].judge(words, json.loads(s1a_run.KNOWN.read_text()), [int(w, 16) for w in exp["params"]])
(out / "verdict.json").write_text(json.dumps(v, indent=1) + "\n")
print(json.dumps({"run": run.name, "pieces": len(note["pieces"]), "extra_attempts": sum(p["attempts"] - 1 for p in note["pieces"]),
                  "host_crc32": note["host_crc32"], "judge": v["verdict"], "problems": v["problems"][:3], "records": v["header"]["records"],
                  "status": v["header"]["status"]}))

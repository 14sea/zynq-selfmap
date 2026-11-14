#!/usr/bin/env python3
"""A board run of one stage: exactly what the host types into U-Boot, in order.

    s1a_run.py [--stage s1a|s1b0|s1b0b|s1b1|rate*|dx*] --dry-run                    print the whole plan and exit; touches no serial port
    s1a_run.py [--stage s1a|s1b0|s1b0b|s1b1|rate*|dx*] --go --out DIR               run it (refuses unless the image on disk is the one tests fixed)

The stages share everything but the parameter block, the judge and the size of a record; the prober
image is the same and picks the stage from the parameter block.

Before `go` every step has a check and the first failure stops the run: nothing has been started.
After `go` the rule is the opposite — whatever the prober reported, clean or not, its result is
first sized from its own header, checksummed, saved to the card, pulled to the host and compared,
and only then judged. A run with anomalies or an interface stop is still archived whole.

The overall verdict is PASS only if the judge says PASS (which includes: the parameters the
prober echoed are the planned ones, and the gate readings fit), the card copy was confirmed and
read back with the board's checksum, the pulled copy has the board's checksum, the console line
and return code are the ones the result implies, and the live status afterwards still shows the
PL configured with no error bit.
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
sys.path.insert(0, str(ROOT / "host"))
import s1a_judge  # noqa: E402
import s1b0_judge  # noqa: E402
import s1b0b_judge  # noqa: E402
import s1b1_judge  # noqa: E402
import dx_judge  # noqa: E402

EXPECTED = ROOT / "build" / "prober" / "expected.json"
STAGES = {"s1a": {"judge": s1a_judge, "expected": EXPECTED},
          "s1b0": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_s1b0.json"},
          "s1b0b": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_s1b0b.json"},
          "s1b1": {"judge": s1b1_judge, "expected": ROOT / "build" / "prober" / "expected_s1b1.json"},
          # not stages of the prober but two parameter sets for its stage 2, to count how many frame reads go by before
          # the receive FIFO overflows: 128 reads of one frame, and 128 reads of three frames, on the known frames
          "rate1": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_rate1.json"},
          "rate3": {"judge": s1b0_judge, "expected": ROOT / "build" / "prober" / "expected_rate3.json"},
          # and one for its stage 3: 64 times the pair the walk makes at every frame — the pad alone, then the frame, at
          # the same address — because rate1 and rate3 ran clean where the walk overflowed
          "ratep": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratep.json"},
          # the same pairs at the first eight addresses the walk read (0xb80..0xb87), where it overflowed and the known
          # frames did not. Those frames have no known answer, so the judge will say so and fail the run: what is
          # wanted here is only how many records the prober gets through
          "ratew": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratew.json"},
          # ratew once through instead of eight times: after a fresh load every one of its frame reads is the first
          # read of that frame, as every read of the walk's first pass is
          "ratef": {"judge": s1b0b_judge, "expected": ROOT / "build" / "prober" / "expected_ratef.json"},
          # diagnostics: why does the walk overflow where stages 2 and 3 do not (docs/s1b_plan.md, section 17).
          # dxw*: the walk itself, kept to the 26 addresses already read, with 0, 6 or 8 more words of stack beneath its
          # reads. dxs*: the reads of the walk's first pass made by the stage-3 loop (stage 5), with 0, 10 or 18.
          **{name: {"judge": s1b1_judge, "expected": ROOT / "build" / "prober" / f"expected_{name}.json"} for name in ("dxw0", "dxw6", "dxw8")},
          **{name: {"judge": dx_judge, "expected": ROOT / "build" / "prober" / f"expected_{name}.json"} for name in ("dxs0", "dxs10", "dxs18")}}
IMAGE = ROOT / "build" / "prober" / "prober.bin"
PL = ROOT / "build" / "pl" / "carrier.bit"
KNOWN = ROOT / "data" / "known_frames_17A6.json"
PL_ADDR, IMG_ADDR, RES_ADDR, PAR_ADDR, SCRATCH_ADDR = 0x04000000, 0x02000000, 0x10000000, 0x10100000, 0x11000000
PAR_WORDS = 32
MAX_RESULT_WORDS = max(m["judge"].HDR + m["judge"].MAX_RECORDS * m["judge"].REC for m in STAGES.values())
PL_CARD_NAME = "carrier.bit"
PIECE_WORDS = 2048                                   # the result is pulled over the console in pieces of this many words
MAX_PIECE_PULLS = 5                                  # attempts at one piece


class Stop(Exception):
    pass


def before_go(exp: dict, pl_bytes: int, pl_crc: str) -> list[dict]:
    """The fixed steps up to and including `go`."""
    p: list[dict] = []
    add = lambda what, cmd, check, **kw: p.append({"what": what, "cmd": cmd, "check": check, **kw})  # noqa: E731
    add("prompt", "version", "U-Boot answers")
    add("cache off (the verified run had it off; the prober refuses otherwise)", "dcache off", "prompt")
    add("cache state", "dcache", "says the data cache is OFF", expect=r"Data \(writethrough\) Cache is OFF")
    add("status before the PL load", "md.l f800700c 1", "recorded")
    add("clear the sticky PCFG_DONE bit so that the load is seen as an edge (as the verified run did)", "mw.l f800700c 00000004 1", "prompt")
    add("status after the clear", "md.l f800700c 1", "bit 2 clear", bit=(2, False))
    add(f"the PL design ({pl_bytes} bytes, sha256 {exp['pl_design']['sha256'][:8]}…) from the card; by YMODEM if the card does not have it",
        f"fatload mmc 0:1 {PL_ADDR:08x} {PL_CARD_NAME}", "U-Boot reports the same size", card_or_ymodem=str(PL), size=pl_bytes, timeout=60)
    add("the design in RAM is the file, whichever way it came", f"crc32 {PL_ADDR:08x} {pl_bytes:x}", f"crc32 {pl_crc}", crc=pl_crc)
    add("configure the PL", f"fpga loadb 0 {PL_ADDR:08x} {pl_bytes:x}", "no error", timeout=60)
    add("status after the load", "md.l f800700c 1", "bit 2 (PCFG_DONE) set", bit=(2, True))
    add("zero the parameter block", f"mw.l {PAR_ADDR:08x} 0 {PAR_WORDS:x}", "prompt")
    for i, w in enumerate(exp["params"]):
        if int(w, 16):
            add(f"parameter word {i}", f"mw.l {PAR_ADDR + 4 * i:08x} {w} 1", "prompt")
    par_crc = f"{zlib.crc32(b''.join(struct.pack('<I', int(w, 16)) for w in exp['params'])) & 0xFFFFFFFF:08x}"
    add("the parameter block is as intended", f"crc32 {PAR_ADDR:08x} {PAR_WORDS * 4:x}", f"crc32 {par_crc}", crc=par_crc)
    add("clear the result header", f"mw.l {RES_ADDR:08x} 0 40", "prompt")
    add(f"send the prober ({exp['image_bytes']} bytes) by YMODEM", f"loady {IMG_ADDR:08x}", "U-Boot reports the same size",
        ymodem=str(IMAGE), size=exp["image_bytes"])
    add("the prober in RAM is the checked image", f"crc32 {IMG_ADDR:08x} {exp['image_bytes']:x}", f"crc32 {exp['image_crc32']}", crc=exp["image_crc32"])
    add("RUN", f"go {IMG_ADDR:08x}", "a prompt afterwards; the console lines and return code are recorded, not required", go=True, timeout=60)
    return p


AFTER_GO = [
    (f"md.l {RES_ADDR:08x} 40", "the result header", "magic and version; gives the record count N and the record size (any known layout is saved whole)"),
    (f"crc32 {RES_ADDR:08x} <4*(64+266*N)>", "the result checksum on the board", "recorded"),
    (f"fatwrite mmc 0:1 {RES_ADDR:08x} <name>.bin <bytes>", "save the result to the card under a name unique to this run", "'<bytes> bytes written'"),
    (f"fatload mmc 0:1 {0x11000000:08x} <name>.bin", "read the card copy back to a scratch address", "'<bytes> bytes read'"),
    (f"crc32 {0x11000000:08x} <bytes>", "the card copy is the result", "the board's crc32 of the result"),
    (f"crc32 / md.l {RES_ADDR:08x}+… <64+266*N>", f"pull the result over the console in pieces of {PIECE_WORDS} words: the board's crc32 of a piece, then the piece",
     "each piece has the board's crc32 of it; the whole has the board's crc32 of the result"),
    ("md.l f800700c 1", "status afterwards", "bit 2 (PCFG_DONE) set and no error bit"),
    (f"crc32 {IMG_ADDR:08x} <image bytes>", "the prober image in RAM after the run", "still the checked image"),
    ("version", "U-Boot still answers", "U-Boot answers"),
]


def md_words(text: str) -> list[int]:
    words: list[int] = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{8}):((?: [0-9a-f]{8}){1,4})", line.strip())
        if m:
            words += [int(x, 16) for x in m.group(2).split()]
    return words


def execute(con, exp: dict, out: Path, send_file, known: dict, pl_bytes: int, pl_crc: str, card_name: str, stage: str = "s1a") -> dict:
    """Run the plan on a console object (`cmd(line, timeout) -> (bytes, prompt_seen)`, `interrupt()`), sending files
    with `send_file(con, loady_command, path) -> (bytes, prompt_seen)`. Writes result files into `out`."""
    J = STAGES[stage]["judge"]
    record: dict = {"stage": stage, "steps": [], "problems": [], "card_file": card_name, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    problems = record["problems"]

    def do(cmd: str, what: str, timeout: float = 10) -> str:
        reply, ok = con.cmd(cmd, timeout)
        text = reply.decode("utf-8", "replace")
        record["steps"].append({"n": len(record["steps"]) + 1, "what": what, "cmd": cmd,
                                "reply": text if len(text) < 2000 else text[:300] + " … " + text[-300:]})
        if not ok:
            raise Stop(f"no prompt after {cmd!r}")
        return text

    try:
        _, ok = con.interrupt()
        if not ok:
            raise Stop("no U-Boot prompt")
        go_text = ""
        for s in before_go(exp, pl_bytes, pl_crc):
            if "ymodem" in s:
                reply, ok = send_file(con, s["cmd"], s["ymodem"])
                text = reply.decode("utf-8", "replace")
                record["steps"].append({"n": len(record["steps"]) + 1, "what": s["what"], "cmd": s["cmd"], "reply": text[-400:]})
                m = re.search(r"## Total Size\s+= 0x([0-9a-fA-F]+)", text)
                if not ok or not m or int(m.group(1), 16) != s["size"]:
                    raise Stop(f"the transfer for {s['cmd']!r} did not report {s['size']} bytes")
                continue
            text = do(s["cmd"], s["what"], s.get("timeout", 10))
            if "card_or_ymodem" in s:
                m = re.search(r"(\d+) bytes read", text)
                record["pl_source"] = "card"
                if not m or int(m.group(1)) != s["size"]:            # not on the card (or not this size): send it
                    record["pl_source"] = "ymodem"
                    reply, ok = send_file(con, f"loady {PL_ADDR:08x}", s["card_or_ymodem"])
                    text = reply.decode("utf-8", "replace")
                    record["steps"].append({"n": len(record["steps"]) + 1, "what": "the PL design by YMODEM", "cmd": f"loady {PL_ADDR:08x}", "reply": text[-400:]})
                    m = re.search(r"## Total Size\s+= 0x([0-9a-fA-F]+)", text)
                    if not ok or not m or int(m.group(1), 16) != s["size"]:
                        raise Stop(f"the PL design could not be loaded from the card or sent ({s['size']} bytes)")
                continue
            if "expect" in s and not re.search(s["expect"], text):
                raise Stop(f"{s['cmd']!r}: {s['check']}")
            if "bit" in s:
                w = md_words(text)
                if not w or bool(w[0] >> s["bit"][0] & 1) != s["bit"][1]:
                    raise Stop(f"{s['cmd']!r}: {s['check']}" + (f" (read {w[0]:08x})" if w else " (nothing read)"))
            if "crc" in s:
                m = re.search(r"==> ([0-9a-f]{8})", text)
                if not m or m.group(1) != s["crc"]:
                    raise Stop(f"{s['cmd']!r}: crc32 {m.group(1) if m else None}, expected {s['crc']}")
            if s.get("go"):
                go_text = text
        record["went"] = True
        m = re.search(r"## Application terminated, rc = 0x([0-9A-Fa-f]+)", go_text)
        record["return_code"] = f"0x{int(m.group(1), 16):x}" if m else None
        record["console"] = [ln.strip() for ln in go_text.splitlines() if re.match(r"SM\d ", ln.strip())]   # the prober's lines, of whichever stage ran

        # ---- from here on: save first, judge afterwards
        hdr = md_words(do(f"md.l {RES_ADDR:08x} 40", "the result header"))
        (out / "header.bin").write_bytes(b"".join(struct.pack("<I", x) for x in hdr))
        if len(hdr) < 64:
            raise Stop("the result header could not be read")
        has_header = hdr[0] == 0x31524D53 and hdr[1] == 1
        n, total = hdr[3], hdr[5]
        # How much to save does not depend on the stage that was asked for: a result that is consistent in itself is
        # saved whole and left to the judge. Only if the header fits no layout at all is the size not its own to give;
        # then everything a result could occupy is saved.
        layouts: dict[tuple[int, int], list[str]] = {}       # stages may share a layout (s1b0 and s1b0b do)
        for name, m in STAGES.items():
            layouts.setdefault((m["judge"].HDR, m["judge"].REC), []).append(name)
        having = layouts.get((hdr[7], hdr[6]), [])
        fits = stage if stage in having else having[0] if having else None
        if has_header and fits and n <= STAGES[fits]["judge"].MAX_RECORDS and total == hdr[7] + n * hdr[6]:
            record["result_layout"] = fits
            if fits != stage:
                problems.append(f"the result has the layout of stage {fits}, not of the stage that was run ({stage})")
        else:
            record["result_layout"] = None
            problems.append(("the result header's sizes fit no known layout" if has_header else "there is no result header at the result address (magic or version)")
                            + f" (records {n}, words {total}, record size {hdr[6]}); the largest possible result ({MAX_RESULT_WORDS} words) is saved instead")
            total = MAX_RESULT_WORDS
        nbytes = total * 4
        record["result_words"] = total
        m = re.search(r"==> ([0-9a-f]{8})", do(f"crc32 {RES_ADDR:08x} {nbytes:x}", "the result checksum on the board", 20))
        if not m:
            raise Stop("no crc32 of the result from the board")
        record["board_crc32"] = m.group(1)

        text = do(f"fatwrite mmc 0:1 {RES_ADDR:08x} {card_name} {nbytes:x}", "save the result to the card", 60)
        m = re.search(r"(\d+) bytes written", text)
        record["card_written"] = bool(m) and int(m.group(1)) == nbytes
        if not record["card_written"]:
            problems.append(f"the card write was not confirmed for {nbytes} bytes: {text.strip()[-120:]!r}")
        else:                                        # by content, not by U-Boot's word: read the file back and checksum it
            text = do(f"fatload mmc 0:1 {SCRATCH_ADDR:08x} {card_name}", "read the card copy back to a scratch address", 60)
            m = re.search(r"(\d+) bytes read", text)
            m2 = re.search(r"==> ([0-9a-f]{8})", do(f"crc32 {SCRATCH_ADDR:08x} {nbytes:x}", "the card copy is the result", 20))
            record["card_verified"] = bool(m) and int(m.group(1)) == nbytes and bool(m2) and m2.group(1) == record["board_crc32"]
            if not record["card_verified"]:
                problems.append("the file read back from the card is not the result (size or crc32 differs)")

        # The console is a lossy path (11 of 28 whole-result pulls came back damaged on 2026-11-14, and three attempts at
        # a large result were not always enough). So the result is pulled in pieces: for each the board is asked for its
        # own crc32 of that piece, and the piece is pulled again, a bounded number of times, until the host's copy has
        # it. Every repeat is recorded. In the end the whole must have the crc32 the board gave for the whole result —
        # that, and nothing a piece says, decides whether this is the board's copy.
        record["pull"] = {"piece_words": PIECE_WORDS, "pieces": 0, "repeated": []}
        words: list[int] = []
        for k, at in enumerate(range(0, total, PIECE_WORDS)):
            n_piece = min(PIECE_WORDS, total - at)
            addr = RES_ADDR + 4 * at
            m = re.search(r"==> ([0-9a-f]{8})", do(f"crc32 {addr:08x} {4 * n_piece:x}", f"the board's checksum of piece {k} of the result", 20))
            if not m:
                raise Stop(f"no crc32 of piece {k} of the result from the board")
            for attempt in range(1, MAX_PIECE_PULLS + 1):
                got = md_words(do(f"md.l {addr:08x} {n_piece:x}", f"pull piece {k} of the result over the console (attempt {attempt} of at most {MAX_PIECE_PULLS})", 120))
                crc = f"{zlib.crc32(b''.join(struct.pack('<I', x) for x in got)) & 0xFFFFFFFF:08x}"
                if len(got) == n_piece and crc == m.group(1):
                    break
                record["pull"]["repeated"].append({"piece": k, "attempt": attempt, "words": len(got), "crc32": crc, "board_crc32": m.group(1)})
            else:
                raise Stop(f"piece {k} of the result could not be pulled whole in {MAX_PIECE_PULLS} attempts"
                           + ("; the card file holds the result" if record.get("card_verified") else ""))
            words += got
            record["pull"]["pieces"] = k + 1
        raw = b"".join(struct.pack("<I", x) for x in words)
        host_crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        record["host_crc32"] = host_crc
        if len(words) != total or host_crc != record["board_crc32"]:        # `total` words were asked for, whichever way it was sized
            (out / "result_unverified.bin").write_bytes(raw)
            raise Stop(f"the pulled copy ({len(words)} words, crc32 {host_crc}) is not the board's ({total} words, crc32 {record['board_crc32']}), "
                       "although each piece matched the board's crc32 of that piece")
        (out / "result.bin").write_bytes(raw)

        verdict = J.judge(words, known, [int(w, 16) for w in exp["params"]])
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n")
        record["judge"] = verdict["verdict"]
        if record["return_code"] != verdict.get("expected_return_code"):
            problems.append(f"the return code was {record['return_code']}, the result implies {verdict.get('expected_return_code')}")
        if record["console"] != verdict.get("expected_console"):
            problems.append(f"the console showed {record['console']}, the result implies {verdict.get('expected_console')}")
        live = md_words(do("md.l f800700c 1", "status afterwards"))
        record["int_sts_afterwards"] = f"{live[0]:08x}" if live else None
        if not live or not live[0] & J.PCFG_DONE or live[0] & J.ERR_MASK:
            problems.append(f"the live status after the run is {record['int_sts_afterwards']}: PCFG_DONE clear or an error bit set")
        m = re.search(r"==> ([0-9a-f]{8})", do(f"crc32 {IMG_ADDR:08x} {exp['image_bytes']:x}", "the prober image in RAM after the run"))
        if not m or m.group(1) != exp["image_crc32"]:
            problems.append(f"the prober image in RAM after the run has crc32 {m.group(1) if m else None}, not {exp['image_crc32']}: what ran may not be what was checked")
        do("version", "U-Boot still answers")
    except Stop as e:
        record["stop"] = str(e)
        problems.append(str(e))
    record["verdict"] = "PASS" if record.get("judge") == "PASS" and not problems else "FAIL"
    (out / "run.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def ymodem_send(con, loady: str, path: str):
    """Send one file with `sb` over the console's serial port."""
    import serial
    from uboot_console import DEV
    con.s.reset_input_buffer(); con.tx(loady.encode() + b"\r")
    end = time.time() + 8; got = b""
    while time.time() < end and b"## Ready for binary (ymodem) download" not in got:
        d = con.s.read(4096); got += d; con.log.write(d)
    if b"## Ready for binary" not in got:
        return got, False
    time.sleep(0.5); con.s.close()
    with open(DEV, "rb+", buffering=0) as port:
        r = subprocess.run(["sb", "-k", path], stdin=port, stdout=port, stderr=subprocess.PIPE, timeout=900)
    con.s = serial.Serial(DEV, 115200, timeout=0.1)
    reply, ok = con.until_prompt(20)
    return reply, ok and r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stage", choices=sorted(STAGES), default="s1a")
    a = ap.parse_args()
    exp = json.loads(STAGES[a.stage]["expected"].read_text())
    img, pl = IMAGE.read_bytes(), PL.read_bytes()
    if hashlib.sha256(img).hexdigest() != exp["image_sha256"]:
        print("REFUSED: the image on disk is not the one the tests fixed in expected.json"); return 2
    if hashlib.sha256(pl).hexdigest() != exp["pl_design"]["sha256"] or len(pl) != exp["pl_design"]["bytes"]:
        print("REFUSED: the staged PL design is not the one the known frames were read with"); return 2
    pl_crc = f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}"
    if a.dry_run or not a.go:
        print(f"stage {a.stage}")
        print(f"image {exp['image_sha256']}  ({exp['image_bytes']} bytes)")
        print(f"PL    {exp['pl_design']['sha256']}  ({len(pl)} bytes)\n")
        steps = before_go(exp, len(pl), pl_crc)
        for i, s in enumerate(steps, 1):
            print(f"{i:3d}. {s['cmd']:44s} # {s['what']}  ->  {s['check']}")
            if "card_or_ymodem" in s:                 # the branch taken when the card has no file of that size
                branch = f"loady {PL_ADDR:08x}"
                print(f"{i:3d}a. {branch:43s} # ONLY IF step {i} did not report {s['size']} bytes read: send the PL design by YMODEM  ->  U-Boot reports the same size")
        print("     --- after go, whatever it reported: save first, judge afterwards ---")
        size = f"64+{STAGES[a.stage]['judge'].REC}*N"
        for i, (cmd, what, check) in enumerate(AFTER_GO, len(steps) + 1):
            cmd = cmd.replace("64+266*N", size)
            print(f"{i:3d}. {cmd:44s} # {what}  ->  {check}")
        print("     branches after go:")
        print(f"       - if the header fits no known layout, or there is no header: <bytes> is 4*{MAX_RESULT_WORDS}, the largest result any stage can produce")
        print("       - the card read-back (fatload and its crc32) is done only if fatwrite confirmed the size; otherwise the run fails, and the pull still happens")
        print(f"       - a piece that does not have the board's crc32 of it is pulled again, at most {MAX_PIECE_PULLS} times in all, every repeat recorded; if a piece cannot be had, or the whole does not have the board's crc32, the run stops there")
        print("\nDry run: nothing was sent.")
        return 0
    if not a.out or a.out.exists():
        print("REFUSED: --out must name a directory that does not exist yet"); return 2
    a.out.mkdir(parents=True)
    os.environ["SELFMAP_CONSOLE_LOG"] = str(a.out / "console.log")
    from uboot_console import UB
    card_name = "s%07x.bin" % (int(time.time()) & 0xFFFFFFF)
    record = execute(UB(), exp, a.out, ymodem_send, json.loads(KNOWN.read_text()), len(pl), pl_crc, card_name, a.stage)
    print("stop:", record.get("stop")); print("problems:", record["problems"]); print("verdict:", record["verdict"])
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

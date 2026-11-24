"""One session at the prompt: put build/pl/s2b.bit on the card and read it back (docs/s2_plan.md, section 46, point 8). Loads nothing into
the PL. As evidence/card_2026-11-20/save_s2a.py did for s2a; here both designs that are on the card already are read back afterwards."""
import hashlib, re, sys, zlib
sys.path.insert(0, "host")
from uboot_console import UB
from s1a_run import ymodem_send, restart_seen
PATH = "build/pl/s2b.bit"; raw = open(PATH, "rb").read()
assert hashlib.sha256(raw).hexdigest() == "7f0e1af8a340fb5fe36749447b3266fc401fa4ab3d9c13dde8a6abe29f887a12" and len(raw) == 2083859
N = len(raw); CRC = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"; print("file", N, f"{N:x}", CRC, flush=True)
u = UB()
def stop(why): print("STOP:", why, flush=True); sys.exit(1)
def do(cmd, want=None, timeout=20):
    b, ok = u.cmd(cmd, timeout); t = b.decode("utf-8", "replace")
    print("---", cmd, "|", " / ".join(x for x in t.replace("\r", "").split("\n")[1:] if x.strip())[:300], flush=True)
    if not ok: stop(f"no prompt after {cmd!r}")
    if restart_seen(cmd, t): stop(f"exception or restart at {cmd!r}")
    if want and not re.search(want, t): stop(f"{cmd!r}: wanted {want!r}")
    return t
_, ok = u.interrupt()
if not ok: stop("no prompt")
do("version", r"U-Boot 2026\.04")
before = re.search(r"f800700c: ([0-9a-f]{8})", do("md.l f800700c 1", r"f800700c: [0-9a-f]{8}")).group(1)
t = do("fatload mmc 0:1 11000000 s2b.bit")                 # a file that is not there: "Failed to load"
if re.search(r"\d+ bytes read", t): stop("the card already has a file s2b.bit")
b, ok = ymodem_send(u, "loady 04000000", PATH); t = b.decode("utf-8", "replace")
print("--- loady 04000000 |", " / ".join(x for x in t.replace("\r", "").split("\n") if x.strip())[-300:], flush=True)
if not ok: stop("no prompt after the transfer")
if restart_seen("loady 04000000", t): stop("exception or restart at the transfer")
if not re.search(rf"= {N} Bytes", t): stop("the transfer did not report the file's size")
do(f"crc32 04000000 {N:x}", rf"==> {CRC}")
do(f"fatwrite mmc 0:1 04000000 s2b.bit {N:x}", rf"{N} bytes written")
do("mmc rescan")
do("mw.l 11000000 0 1000")
do("fatload mmc 0:1 11000000 s2b.bit", rf"{N} bytes read")
do(f"crc32 11000000 {N:x}", rf"==> {CRC}")
do("fatload mmc 0:1 11000000 s2a.bit", r"2083859 bytes read")       # the two designs on the card before are still what they were
do("crc32 11000000 1fcc13", r"==> 6a1efe06")
do("fatload mmc 0:1 11000000 carrier.bit", r"2083863 bytes read")
do("crc32 11000000 1fcc17", r"==> 72887bf4")
after = re.search(r"f800700c: ([0-9a-f]{8})", do("md.l f800700c 1", r"f800700c: [0-9a-f]{8}")).group(1)
do("version", r"U-Boot 2026\.04")
print("DONE: status before", before, "after", after, flush=True)

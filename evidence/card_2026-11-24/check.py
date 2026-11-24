"""One session at the prompt, before s2b.bit is put on the card: is the board there, and what does the card hold? Read-only: nothing is
loaded, written or reset."""
import re, sys
sys.path.insert(0, "host")
from uboot_console import UB
from s1a_run import restart_seen
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
do("md.l f800700c 1", r"f800700c: [0-9a-f]{8}")
do("printenv cardid")                                         # asked as the checks before every chain ask it; it is not defined, and was not then
do("fatsize mmc 0:1 carrier.bit"); do("printenv filesize", r"filesize=1fcc17")
do("fatsize mmc 0:1 s2a.bit"); do("printenv filesize", r"filesize=1fcc13")
do("fatsize mmc 0:1 s2b.bit")                                # not there yet, by what is on record
do("version", r"U-Boot 2026\.04")
print("DONE", flush=True)

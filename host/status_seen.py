#!/usr/bin/env python3
"""Which bits of the status register showed in a run that are neither an error nor usual (docs/s1b_plan.md, section 54).

    status_seen.py <verdict.json | directory> ...        prints the list as JSON

A directory stands for the verdicts in it: its own `verdict.json`, or those of its `runNN` directories in order.

The judges hold every status word of a run against the error mask and ask that PCFG_DONE is set; a bit that is neither
passes unseen. In S1b.4 one did (bit 5, in 14 of 21 runs) and was found only by looking at the status left after the
runs. This program lists such bits from the verdicts the judges wrote, stored or new: for every run, each bit that
showed in some status word and is in neither the error mask nor USUAL, the first record at which it showed, and
whether it stayed. It judges nothing and changes no verdict: a bit listed here is something seen, not a failure.

It reads no database and knows nothing of any part. The one name it carries is from UG585's register reference.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from s1a_judge import ERR_MASK  # noqa: E402

USUAL = 0x50033004          # the status after a clean run before S1b.4; every status word of the verdicts stored till then lies in it or in the error mask
NAMES = {5: "PCFG_SEU_ERR (UG585, devcfg.INT_STS: triggers when PL detects POST_CRC or ECC error)"}


def seen(verdict: dict) -> dict:
    """The bits outside ERR_MASK and USUAL in the status words of one run, in the order the run took them."""
    header = verdict.get("header") or {}
    words: list[tuple[int, dict]] = []                   # (status word, where it was read)
    if "int_sts_initial" in header:
        words.append((int(header["int_sts_initial"], 16), {"where": "the header's first reading"}))
    for i, r in enumerate(verdict.get("records") or []):
        where = {"where": "a record", "record": i, **{k: r[k] for k in ("kind", "far", "frames") if k in r},
                 "status_words": list(r.get("int_sts") or [])}
        words += [(int(x, 16), where) for x in r.get("int_sts") or []]
    if "int_sts_final" in header:
        words.append((int(header["int_sts_final"], 16), {"where": "the header's last reading"}))
    other = 0xFFFFFFFF & ~(ERR_MASK | USUAL)
    bits = []
    for b in range(32):
        if not other >> b & 1:
            continue
        has = [bool(w >> b & 1) for w, _ in words]
        if not any(has):
            continue
        first = has.index(True)
        bits.append({"bit": b, "name": NAMES.get(b), "first": words[first][1], "words_with_it": sum(has), "words": len(has),
                     "stayed_once_it_showed": all(has[first:]), "in_the_last_word": has[-1]})
    return {"status_words": len(words), "bits": bits}


def verdicts(arg: Path) -> list[Path]:
    if arg.is_file():
        return [arg]
    if (arg / "verdict.json").is_file():
        return [arg / "verdict.json"]
    return sorted(p for p in arg.glob("run[0-9][0-9]/verdict.json"))


def main(argv: list[str]) -> int:
    files = [f for a in argv[1:] for f in verdicts(Path(a))] if len(argv) > 1 and all(Path(a).exists() for a in argv[1:]) else []
    if not files:
        print(__doc__); return 2
    runs = [{"run": str(f.parent), **seen(json.loads(f.read_text()))} for f in files]
    print(json.dumps({"error_mask": f"{ERR_MASK:#010x}", "usual": f"{USUAL:#010x}", "runs": len(runs),
                      "runs_with_such_a_bit": [r["run"] for r in runs if r["bits"]],
                      "bits": sorted({b["bit"] for r in runs for b in r["bits"]}), "by_run": runs}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

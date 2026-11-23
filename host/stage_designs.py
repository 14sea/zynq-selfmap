#!/usr/bin/env python3
"""The PL designs, put where the run script and the tests look for them — docs/s2_plan.md, section 24.

    stage_designs.py            stage what is missing in build/pl/ and say what was done

build/ is not in git, and a design cannot be built again to the same bytes (a rebuilt s2a.bit has another hash). So
each design has a copy that is in git, and a record of its hash that is not that copy:

    design        the copy in git                           the hash it is held to
    carrier.bit   imported/fabricmap/carrier.bit            imported/fabricmap/IMPORT.json
    s2a.bit       evidence/s2_1_17A6_2026-11-20/s2a.bit     pl/s2a/build.json
    s2b.bit       evidence/s2_5_build_2026-11-23/s2b.bit    pl/s2b/build.json

A design that is missing in build/pl/ is written there once its copy has the recorded hash and length; a copy that
has not is refused and nothing is written. A design that is already there is left as it is, whatever it is: the run
script and the chain hold what is staged to the set before they use it, and that is not this program's to decide.

The files are opaque here, as everywhere on the host: read whole, hashed, written. Nothing of them is looked into.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def designs(root: Path = ROOT) -> list[dict]:
    """Each design: where it is staged, its copy in git, and the hash and length its record gives."""
    imported = json.loads((root / "imported" / "fabricmap" / "IMPORT.json").read_text())["files"]["carrier.bit"]
    built = json.loads((root / "pl" / "s2a" / "build.json").read_text())["bitstream"]
    built_b = json.loads((root / "pl" / "s2b" / "build.json").read_text())["bitstream"]
    return [{"name": "carrier.bit", "staged": root / "build" / "pl" / "carrier.bit", "copy": root / "imported" / "fabricmap" / "carrier.bit",
             "sha256": imported["sha256"], "bytes": imported["bytes"], "record": "imported/fabricmap/IMPORT.json"},
            {"name": "s2a.bit", "staged": root / "build" / "pl" / "s2a.bit", "copy": root / "evidence" / "s2_1_17A6_2026-11-20" / "s2a.bit",
             "sha256": built["sha256"], "bytes": built["bytes"], "record": "pl/s2a/build.json"},
            {"name": "s2b.bit", "staged": root / "build" / "pl" / "s2b.bit", "copy": root / "evidence" / "s2_5_build_2026-11-23" / "s2b.bit",
             "sha256": built_b["sha256"], "bytes": built_b["bytes"], "record": "pl/s2b/build.json"}]


def stage(root: Path = ROOT) -> list[str]:
    """Stage every design that is missing. Returns what was done, a line a design. Raises ValueError for a copy that
    is not what its record says; nothing of that design is written then."""
    done: list[str] = []
    for d in designs(root):
        if d["staged"].exists():
            done.append(f"{d['name']}: already staged, left as it is")
            continue
        try:
            data = d["copy"].read_bytes()
        except OSError:
            raise ValueError(f"{d['name']}: the copy in git ({d['copy'].relative_to(root)}) is not there") from None
        if (hashlib.sha256(data).hexdigest(), len(data)) != (d["sha256"], d["bytes"]):
            raise ValueError(f"{d['name']}: the copy in git ({d['copy'].relative_to(root)}) is not the file {d['record']} records")
        d["staged"].parent.mkdir(parents=True, exist_ok=True)
        d["staged"].write_bytes(data)
        done.append(f"{d['name']}: staged from {d['copy'].relative_to(root)} (sha256 {d['sha256'][:8]}…, {d['bytes']} bytes)")
    return done


def main() -> int:
    try:
        for line in stage():
            print(line)
    except ValueError as e:
        print(f"REFUSED: {e}"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

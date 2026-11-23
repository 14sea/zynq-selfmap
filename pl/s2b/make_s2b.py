#!/usr/bin/env python3
"""The probe design s2b: its sites, the word each memory is loaded with, and the three files that follow from them —
docs/s2_plan.md, sections 45 and 46.

    make_s2b.py            write s2b.xdc, placed.tcl and design.json beside this file (they are kept in git; a test
                           holds them to what this makes)

The sites (section 45, the design): every site of one column of sites, SLICE_X16Y0 to SLICE_X16Y99 — site 0 to 99, by
its row — and one site in each of the ten other columns of SLICEM sites numbered 10 or above, the i-th of them at row
(7 + 37 i) mod 100 — site 100 to 109. Nothing here says where a site lies in configuration memory.

The words: memory k of site s is loaded with the word of the number n = 4 s + k + 1, by the arithmetic that
pl/s2b/s2b_regs.v has as `init_of` — 64 bits, bit a the content of address a. 440 words, no two alike."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMN, ROWS = 16, 100
OTHERS = (10, 12, 20, 24, 28, 30, 32, 34, 38, 42)
MEMORIES = 4
M64 = (1 << 64) - 1


def sites() -> list[str]:
    return [f"SLICE_X{COLUMN}Y{y}" for y in range(ROWS)] + [f"SLICE_X{x}Y{(7 + 37 * i) % 100}" for i, x in enumerate(OTHERS)]


def init_of(n: int) -> int:
    x = (0x9E3779B97F4A7C15 * n) & M64
    x ^= x >> 29
    x = (x * 0xBF58476D1CE4E5B9) & M64
    x ^= x >> 32
    return x


def word(site: int, memory: int) -> int:
    return init_of(MEMORIES * site + memory + 1)


def cell(site: int, memory: int) -> str:
    return f"regs/at[{site}].ram{memory}"


def xdc() -> str:
    lines = ["# zynq-selfmap probe design s2b — constraints. docs/s2_plan.md, sections 45 and 46. Written by make_s2b.py.",
             "#",
             "# The clock: as s2a's.",
             "create_clock -period 10.000 -name fclk0 [get_pins ps7/FCLKCLK[0]]",
             "",
             "# The LUT RAM: four memories on each of 110 SLICEM sites. Only the site is constrained; which of the site's four",
             "# LUT positions each memory gets is Vivado's to say (s2a.xdc says what was tried), and the build's record states it."]
    for s, site in enumerate(sites()):
        for k in range(MEMORIES):
            lines.append(f"set_property LOC {site} [get_cells {{{cell(s, k)}/SP}}]")
    return "\n".join(lines) + "\n"


def placed() -> str:
    lines = ["# zynq-selfmap probe design s2b — cell -> {site, LUT position}, for build_s2b.tcl. Written by make_s2b.py.", "set placed {"]
    for s, site in enumerate(sites()):
        lines.append("    " + "  ".join(f"{{{cell(s, k)}}} {{{site} any}}" for k in range(MEMORIES)))
    return "\n".join(lines + ["}"]) + "\n"


def design() -> dict:
    return {
        "schema": "probe_design", "schema_version": 1, "name": "s2b",
        "what": "the probe design of S2.5 (docs/s2_plan.md, sections 45 and 46): LUT RAM at 110 sites behind eight registers on M_AXI_GP0, "
                "every memory loaded with a word of its own",
        "base": "0x40000000", "id": "0x53324231",
        "registers": {
            "ID": {"offset": "0x00", "read": "the fixed word", "write": "ignored"},
            "SITE": {"offset": "0x04", "read": "what was last written: the site number (bits 6..0) and whether a write goes to every site (bit 8)",
                     "write": "which site a read of RAM_DATA answers for and a write of RAM_DATA goes to; bit 8: to every site"},
            "COUNT": {"offset": "0x08", "read": "a counter of FCLK0, free running", "write": "ignored"},
            "RAM_ADDR": {"offset": "0x0c", "read": "the address, six bits", "write": "the address of every memory, for reading and for writing"},
            "RAM_DATA": {"offset": "0x10", "read": "the four outputs at that address of the site SITE names, bit k from memory k",
                         "write": "one write of bit k into memory k at that address — of the site SITE names, or of every site"},
            "NONE": {"offset": "0x14", "read": "zero", "write": "ignored"},
            "CHECK": {"offset": "0x18", "read": "at that address, over all sites, for memory k: bit k — a site holds a one; bit 4+k — every site "
                                                "holds a one; bit 8+k — the parity of what the sites hold", "write": "ignored"},
            "WRITES": {"offset": "0x1c", "read": "writes of RAM_DATA since the design was loaded (bits 15..0)", "write": "ignored"}},
        "ram": {
            "primitive": "RAM64X1S", "depth": 64, "memories_a_site": MEMORIES,
            "loaded_with": "memory k of site s: init_of(4 s + k + 1) of pl/s2b/s2b_regs.v, 64 bits, bit a the content of address a",
            "sites": [{"site": s, "name": name, "cells": [f"{cell(s, k)}" for k in range(MEMORIES)],
                       "init": [f"0x{word(s, k):016x}" for k in range(MEMORIES)]} for s, name in enumerate(sites())],
            "positions": "not constrained, as in s2a: which memory is on which LUT position of its site is in the build's record (pl/s2b/build.json)"},
        "sites_chosen": "every site of the column of sites numbered 16, and one site in each other column of SLICEM sites numbered 10 or above, "
                        "at row (7 + 37 i) mod 100 for the i-th of them: a rule fixed in section 45 before anything was built. No site of a "
                        "column numbered below 10 (section 12, point 5).",
        "clock": {"source": "FCLK0 as the boot loader leaves it (50 MHz on 17A6), through a BUFG", "constrained_period_ns": 10.0}}


def main() -> int:
    (HERE / "s2b.xdc").write_text(xdc())
    (HERE / "placed.tcl").write_text(placed())
    (HERE / "design.json").write_text(json.dumps(design(), indent=1) + "\n")
    words = [word(s, k) for s in range(len(sites())) for k in range(MEMORIES)]
    print(f"{len(sites())} sites, {len(words)} memories, {len(set(words))} different words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

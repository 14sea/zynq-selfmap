"""The probe design s2b (pl/s2b) — docs/s2_plan.md, sections 45 and 46.

What can be held on the host, as for s2a: that the design simulates as its description says, behind the AXI3 front
that was copied; that the description, the source, the constraints and the build script say the same thing — all
three written by one program from the rule section 45 fixed; that the prober's image, which knows a design by its
offsets, may write what this design needs written and nothing this design takes otherwise; that the record of the
build is the record of these sources and of the staged bitstream; and that nothing in the design's directory asks
Vivado for what the closed-book rule excludes."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "host"))
import scratch_dirs  # noqa: E402
import stage_designs  # noqa: E402
from test_pl_s2a import IMPORTED, UNISIMS, bench, sha  # noqa: E402

PLD = ROOT / "pl" / "s2b"
DESIGN = json.loads((PLD / "design.json").read_text())
BUILT = json.loads((PLD / "build.json").read_text())
SITES = [f"SLICE_X16Y{y}" for y in range(100)] + ["SLICE_X10Y7", "SLICE_X12Y44", "SLICE_X20Y81", "SLICE_X24Y18", "SLICE_X28Y55",
                                                  "SLICE_X30Y92", "SLICE_X32Y29", "SLICE_X34Y66", "SLICE_X38Y3", "SLICE_X42Y40"]


def maker():
    spec = importlib.util.spec_from_file_location("make_s2b", PLD / "make_s2b.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def word(n: int) -> int:
    """The word memory number n is loaded with: written here again, from section 46."""
    mask = (1 << 64) - 1
    x = (0x9E3779B97F4A7C15 * n) & mask
    x ^= x >> 29
    x = (x * 0xBF58476D1CE4E5B9) & mask
    return x ^ (x >> 32)


class TheBench(unittest.TestCase):
    SOURCES = (PLD / "tb_s2b.v", PLD / "s2b_regs.v", IMPORTED / "carrier_axi3_lite.v", UNISIMS / "RAM64X1S.v")

    def test_the_design_behind_the_front_does_what_its_description_says(self) -> None:
        out = bench("tb_s2b", *self.SOURCES)
        self.assertRegex(out, r"S2B BENCH PASS: \d{4,} checks", out[-600:])
        self.assertNotIn("FAIL", out)

    def test_a_register_file_that_is_not_the_design_fails_the_bench_and_does_not_stall_it(self) -> None:
        """Six copies of the register file, each with one thing wrong: no write response; no read data; a write enable
        that is never raised; a write to one site that goes to every site; a write to every site that goes to one; and
        memories that are all loaded with the same word."""
        src = (PLD / "s2b_regs.v").read_text()
        tmp = Path(scratch_dirs.mkdtemp(prefix="smbroken2_"))
        for name, old, new, says in (
                ("no write response", "                s_bvalid <= 1'b1;\n", "", "no write response"),
                ("no read data", "                s_rvalid <= 1'b1;\n", "", "no read data"),
                ("no memory is ever written", "ram_d <= s_wdata[3:0]; ram_we <= 1'b1;", "ram_d <= s_wdata[3:0];", "changes one bit of the fourth"),
                ("a write to one site goes to all", "assign we[s] = ram_we && (every || site == s);", "assign we[s] = ram_we;", "and no memory of any other site"),
                ("a write to every site goes to one", "assign we[s] = ram_we && (every || site == s);", "assign we[s] = ram_we && (site == s);", "every site holds the state"),
                ("every memory has the same word", "RAM64X1S #(.INIT(init_of(4 * s + 2)))", "RAM64X1S #(.INIT(init_of(2)))", "a memory is loaded with the word of its number")):
            with self.subTest(name):
                self.assertEqual(src.count(old), 1)
                (tmp / "regs.v").write_text(src.replace(old, new))
                out = bench("tb_s2b", PLD / "tb_s2b.v", tmp / "regs.v", *self.SOURCES[2:])
                self.assertIn("S2B BENCH FAIL", out)
                self.assertIn(says, out)
                self.assertNotIn("did not come to its end", out, "every wait is bounded: the bench ends by itself")


class OneRule(unittest.TestCase):
    """Section 45 fixed the sites and section 46 the words; one program writes the constraints, the build script's
    table and the description from them, and the source computes the words by the same arithmetic."""

    def test_the_three_files_are_what_the_program_writes(self) -> None:
        m = maker()
        self.assertEqual((PLD / "s2b.xdc").read_text(), m.xdc())
        self.assertEqual((PLD / "placed.tcl").read_text(), m.placed())
        self.assertEqual(json.loads((PLD / "design.json").read_text()), json.loads(json.dumps(m.design())))

    def test_the_sites(self) -> None:
        """Every site of the column of sites numbered 16, and one in each other column of SLICEM sites numbered 10 or
        above at row (7 + 37 i) mod 100 — written out here. All of them SLICEM sites by the list Vivado gave; none in
        a column numbered below 10 (section 12, point 5)."""
        listed = [s["name"] for s in DESIGN["ram"]["sites"]]
        self.assertEqual((listed, len(set(listed)), [s["site"] for s in DESIGN["ram"]["sites"]]), (SITES, 110, list(range(110))))
        slicem = {ln.strip() for ln in (ROOT / "pl" / "s2a" / "slicem_sites.txt").read_text().splitlines() if ln.startswith("SLICE_")}
        columns = sorted({int(re.match(r"SLICE_X(\d+)Y", s).group(1)) for s in slicem})
        self.assertEqual([c for c in columns if c >= 10], [10, 12, 16, 20, 24, 28, 30, 32, 34, 38, 42], "the columns of SLICEM sites the step may use: all are used")
        for name in listed:
            self.assertIn(name, slicem)
            self.assertGreaterEqual(int(re.match(r"SLICE_X(\d+)Y\d+$", name).group(1)), 10, name)
        self.assertIn("SLICE_X16Y30", listed, "the site of s2a's RAM is one of them")

    def test_every_memory_is_loaded_with_a_word_of_its_own(self) -> None:
        words = [int(w, 16) for s in DESIGN["ram"]["sites"] for w in s["init"]]
        self.assertEqual((len(words), len(set(words))), (440, 440))
        self.assertEqual(words, [word(4 * s + k + 1) for s in range(110) for k in range(4)])
        self.assertEqual((f"{words[0]:#018x}", f"{words[-1]:#018x}"), ("0xca009717f87d8879", f"{word(440):#018x}"))
        self.assertTrue(all(20 <= bin(w).count("1") <= 44 for w in words), "none is near all zero or all one")
        regs = (PLD / "s2b_regs.v").read_text()
        for line in ("x = 64'h9E3779B97F4A7C15 * n;", "x = x ^ (x >> 29);", "x = x * 64'hBF58476D1CE4E5B9;", "x = x ^ (x >> 32);"):
            self.assertIn(line, regs)
        self.assertEqual(re.findall(r"RAM64X1S #\(\.INIT\(init_of\(4 \* s \+ (\d)\)\)\) ram(\d)", regs), [("1", "0"), ("2", "1"), ("3", "2"), ("4", "3")])

    def test_the_registers_and_what_the_image_may_write(self) -> None:
        """The prober knows a design by its offsets. Its image may write the offsets 0x04, 0x0c, 0x10, 0x14 and, where
        a set says so, 0x18 (prober/sm.h). This design takes writes at 0x04, 0x0c and 0x10, and a write to either of
        the other two does nothing."""
        header = (ROOT / "prober" / "sm.h").read_text()
        regs = (PLD / "s2b_regs.v").read_text()
        names = list(DESIGN["registers"])
        self.assertEqual(names, ["ID", "SITE", "COUNT", "RAM_ADDR", "RAM_DATA", "NONE", "CHECK", "WRITES"])
        for k, name in enumerate(names):
            self.assertEqual(int(DESIGN["registers"][name]["offset"], 16), 4 * k)
            self.assertRegex(regs, rf"R_{name} = 3'd{k}\b", name)
        self.assertEqual(int(re.search(r"#define PL_BASE\s+0x([0-9A-Fa-f]+)u", header).group(1), 16), int(DESIGN["base"], 16))
        self.assertIn("#define PL_WRITABLE9       (PL_WRITABLE | (1u << PL_SRL_DATA))", header)
        self.assertIn("#define PL_WRITABLE        ((1u << PL_SCRATCH) | (1u << PL_RAM_ADDR) | (1u << PL_RAM_DATA) | (1u << PL_SRL_ADDR))", header)
        taken = re.findall(r"^\s+R_(\w+):\s+(?:begin )?\w+\s+<=", regs.split("case (wr_sel)")[1].split("endcase")[0], re.M)
        self.assertEqual(taken, ["SITE", "RAM_ADDR", "RAM_DATA"], "the registers a write changes")
        self.assertEqual({int(DESIGN["registers"][n]["offset"], 16) for n in taken}, {0x04, 0x0C, 0x10})
        self.assertEqual((DESIGN["id"], f"parameter [31:0] ID_WORD = 32'h5332_4231" in regs), ("0x53324231", True))
        self.assertNotEqual(DESIGN["id"], json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())["id"], "the prober is told which design it must find")

    def test_the_memories_are_these_and_the_source_has_no_other(self) -> None:
        regs = (PLD / "s2b_regs.v").read_text()
        top = (PLD / "s2b_top.v").read_text()
        code = lambda text: "\n".join(ln.split("//")[0] for ln in text.splitlines())  # noqa: E731
        self.assertEqual(re.findall(r"\b(RAM\w+|SRL\w+|FIFO\w+)\s+#", code(regs)), ["RAM64X1S"] * 4, "four in the source, at every site of the generate")
        self.assertEqual(re.findall(r"\b(RAM\w+|SRL\w+|FIFO\w+)\s+#", code(top)), [])
        self.assertIn("for (s = 0; s < N_SITES; s = s + 1) begin : at", regs)
        self.assertIn("parameter integer N_SITES = 110", regs)
        for text in (code(regs), code(top)):
            self.assertFalse(re.findall(r"\b(?:reg|logic)\b[^;\n]*\]\s*\w+\s*\[", text), "an array of registers would be a memory nobody instantiated")
        body = code(regs).split("endfunction")[1]              # the function's own variable is no register of the design
        self.assertEqual([m for m in re.finditer(r"^\s*reg\b", body, re.M)], [], "every register of the register file is kept from becoming a shift register")
        self.assertIn("-no_srlextract", (PLD / "build_s2b.tcl").read_text())
        self.assertEqual(len(re.findall(r'\(\* DONT_TOUCH = "yes" \*\) RAM64X1S', regs)), 4)
        self.assertIn('(* shreg_extract = "no", DONT_TOUCH = "yes" *) reg [5:0]  ram_addr;', regs, "one address net for every memory: a site's four must share it")
        self.assertEqual(top.replace("s2b", "s2a").split("module s2a_top")[1], (ROOT / "pl" / "s2a" / "s2a_top.v").read_text().split("module s2a_top")[1],
                         "the top level is s2a's, with this register file")

    def test_the_clock(self) -> None:
        self.assertIn(f"create_clock -period {DESIGN['clock']['constrained_period_ns']:.3f} ", (PLD / "s2b.xdc").read_text())
        self.assertEqual(float(BUILT["clock_period_ns"]), DESIGN["clock"]["constrained_period_ns"])
        self.assertGreaterEqual(BUILT["setup_slack_ns"], 0)
        self.assertGreaterEqual(BUILT["hold_slack_ns"], 0)


class TheRecordOfTheBuild(unittest.TestCase):
    def test_it_is_the_record_of_these_sources(self) -> None:
        self.assertEqual(sorted(BUILT["sources"]), sorted(["pl/s2b/s2b_top.v", "pl/s2b/s2b_regs.v", "imported/fabricmap/carrier_axi3_lite.v",
                                                           "pl/s2b/s2b.xdc", "pl/s2b/placed.tcl", "pl/s2b/build_s2b.tcl"]))
        for rel, digest in BUILT["sources"].items():
            self.assertEqual(sha(ROOT / rel), digest, f"{rel} has changed since the design was built: the record and the bitstream are of another source")
        self.assertEqual((BUILT["part"], BUILT["name"], BUILT["vivado"]), ("xc7z010clg400-1", "s2b", "2025.2"))

    def test_every_memory_is_on_its_site_and_the_four_of_a_site_on_four_positions(self) -> None:
        placed = BUILT["memory_primitives"]
        self.assertEqual(len(placed), 440)
        for s, name in enumerate(SITES):
            cells = [f"regs/at[{s}].ram{k}" for k in range(4)]
            self.assertEqual(DESIGN["ram"]["sites"][s]["cells"], cells)
            self.assertEqual([(placed[c]["site"], placed[c]["leaf"], placed[c]["primitive"]) for c in cells], [(name, f"{c}/SP", "RAMS64E") for c in cells], name)
            self.assertEqual(sorted(placed[c]["bel"] for c in cells), ["A6LUT", "B6LUT", "C6LUT", "D6LUT"], name)

    def test_the_staged_bitstream_and_its_copy_in_git_are_the_one_the_record_names(self) -> None:
        d = next(x for x in stage_designs.designs() if x["name"] == "s2b.bit")
        self.assertEqual((d["sha256"], d["bytes"], d["record"]), (BUILT["bitstream"]["sha256"], BUILT["bitstream"]["bytes"], "pl/s2b/build.json"))
        self.assertEqual((sha(d["copy"]), d["copy"].stat().st_size), (d["sha256"], d["bytes"]), "the copy in git")
        stage_designs.stage()
        self.assertEqual((sha(d["staged"]), d["staged"].stat().st_size), (d["sha256"], d["bytes"]), "what is staged")
        self.assertEqual(len(stage_designs.designs()), 3)


class ClosedBook(unittest.TestCase):
    def test_the_design_s_directory_holds_these_files_and_no_other(self) -> None:
        self.assertEqual(sorted(p.name for p in PLD.iterdir() if p.name != "__pycache__"),
                         ["build.json", "build_s2b.tcl", "design.json", "make_s2b.py", "placed.tcl", "s2b.xdc", "s2b_regs.v", "s2b_top.v", "tb_s2b.v"])

    def test_vivado_is_asked_for_nothing_the_rule_excludes(self) -> None:
        text = "\n".join(ln.split("#")[0] if not ln.lstrip().startswith("puts") else ln for ln in (PLD / "build_s2b.tcl").read_text().splitlines())
        for forbidden in ("logic_location", "mask_file", "readback_file", "-bin_file", "essential", "report_", "write_checkpoint", "write_edif",
                          "write_verilog", "write_cfgmem", "get_tiles", "get_bels", "get_pips", "get_nodes", "get_wires", "get_site_pips", "get_sites", "RPM", "TILE"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertEqual(len(re.findall(r"\bwrite_bitstream\b", text)), 1)
        self.assertRegex((PLD / "build_s2b.tcl").read_text(), r"write_bitstream -force \$outdir/s2b\.bit\n")
        a, b = (PLD / "build_s2b.tcl").read_text(), (ROOT / "pl" / "s2a" / "build_s2a.tcl").read_text()
        same = lambda t: t.split("place_design\n")[1].split("write_bitstream")[0]  # noqa: E731
        self.assertEqual(same(a).replace('get_cells -hierarchical -filter [format {NAME == "%s"} [leaf_of $cell $mem]]', "get_cells [leaf_of $cell $mem]"), same(b),
                         "placement, routing and the three checks are s2a's, but for how a cell is found by a name that has brackets")

    def test_nothing_in_the_design_names_the_database_or_a_frame_address(self) -> None:
        for path in PLD.iterdir():
            if path.name == "__pycache__":
                continue
            text = path.read_text()
            for w in ("prjxray", "segbits", "tilegrid", "baseaddr", "frame address"):
                self.assertNotIn(w.lower(), text.lower(), f"{path.name}: {w}")
            self.assertFalse(re.findall(r"\bFAR\b", text), f"{path.name}: the address register's name")
            self.assertFalse(re.findall(r"0x00[048c][0-9a-f]{5}\b", text, re.I), f"{path.name}: a number shaped like a frame address")


if __name__ == "__main__":
    unittest.main()

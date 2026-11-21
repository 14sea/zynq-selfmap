"""The probe design s2a (pl/s2a) — docs/s2_plan.md, section 5 and section 12, points 4 to 6.

What can be held on the host: that the design simulates as its description says, behind the AXI3 front that was
copied; that the description, the source, the constraints, the build script, the prober's header and the twin's model
say the same thing; that the record of the build is the record of these sources and of the staged bitstream; and
that nothing in the design's directory asks Vivado for what the closed-book rule excludes."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402

PLD = ROOT / "pl" / "s2a"
IMPORTED = ROOT / "imported" / "fabricmap"
# Vivado's simulation models of the primitives the design instantiates: behaviour, no position in configuration memory
UNISIMS = Path.home() / "Xilinx" / "2025.2" / "Vivado" / "data" / "verilog" / "src" / "unisims"
DESIGN = json.loads((PLD / "design.json").read_text())
BUILT = json.loads((PLD / "build.json").read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bench(top: str, *sources: Path) -> str:
    tmp = Path(scratch_dirs.mkdtemp(prefix="smbench_"))
    c = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "b.vvp"), "-s", top, *map(str, sources)], capture_output=True, text=True)
    errors = [ln for ln in (c.stdout + c.stderr).splitlines() if "Choosing typ expression" not in ln]
    if c.returncode or errors:
        return "DID NOT COMPILE: " + " | ".join(errors[:5])
    return subprocess.run(["vvp", "-n", str(tmp / "b.vvp")], capture_output=True, text=True, timeout=600).stdout


class TheBenches(unittest.TestCase):
    def test_the_models_of_the_primitives_are_where_vivado_ships_them(self) -> None:
        for name in ("RAM64X1S.v", "SRLC32E.v"):
            self.assertTrue((UNISIMS / name).is_file(), f"{UNISIMS / name}: the benches need Vivado's own model")

    def test_the_design_behind_the_front_does_what_its_description_says(self) -> None:
        out = bench("tb_s2a", PLD / "tb_s2a.v", PLD / "s2a_regs.v", IMPORTED / "carrier_axi3_lite.v", UNISIMS / "RAM64X1S.v", UNISIMS / "SRLC32E.v")
        self.assertRegex(out, r"S2A BENCH PASS: \d{3,} checks", out[-600:])
        self.assertNotIn("FAIL", out)

    def test_the_copied_front_passes_the_bench_it_came_with(self) -> None:
        out = bench("tb_carrier_axi3", IMPORTED / "tb_carrier_axi3.v", IMPORTED / "carrier_axi3_lite.v")
        self.assertIn("tb_carrier_axi3: OK", out, out[-600:])

    def test_a_register_file_that_does_not_answer_fails_the_bench_and_does_not_stall_it(self) -> None:
        """The bench is what stands between a slave that does not answer and a power cycle. Tried on three copies of
        the register file: one that never gives a write response, one that never gives read data, one whose RAM write
        enable is never raised."""
        src = (PLD / "s2a_regs.v").read_text()
        tmp = Path(scratch_dirs.mkdtemp(prefix="smbroken_"))
        for name, old, new, says in (("no write response", "                s_bvalid <= 1'b1;\n", "", "no write response"),
                                     ("no read data", "                s_rvalid <= 1'b1;\n", "", "no read data"),
                                     ("the RAM is never written", "ram_d <= s_wdata[3:0]; ram_we <= 1'b1;", "ram_d <= s_wdata[3:0];", "the RAM reads back what the state wrote")):
            with self.subTest(name):
                self.assertEqual(src.count(old), 1)
                (tmp / "regs.v").write_text(src.replace(old, new))
                out = bench("tb_s2a", PLD / "tb_s2a.v", tmp / "regs.v", IMPORTED / "carrier_axi3_lite.v", UNISIMS / "RAM64X1S.v", UNISIMS / "SRLC32E.v")
                self.assertIn("S2A BENCH FAIL", out)
                self.assertIn(says, out)
                self.assertNotIn("did not come to its end", out, "every wait is bounded: the bench ends by itself")


class OneDescription(unittest.TestCase):
    """design.json is the description; everything else that states a fact of the design states the same."""

    def test_the_registers_in_the_prober_s_header_and_in_the_source(self) -> None:
        header = (ROOT / "prober" / "sm.h").read_text()
        regs = (PLD / "s2a_regs.v").read_text()
        self.assertEqual(int(re.search(r"#define PL_BASE\s+0x([0-9A-Fa-f]+)u", header).group(1), 16), int(DESIGN["base"], 16))
        names = list(DESIGN["registers"])
        self.assertEqual(names, ["ID", "SCRATCH", "COUNT", "RAM_ADDR", "RAM_DATA", "SRL_ADDR", "SRL_DATA", "WRITES"])
        for k, name in enumerate(names):
            off = int(DESIGN["registers"][name]["offset"], 16)
            self.assertEqual(off, 4 * k)
            self.assertEqual(int(re.search(rf"#define PL_{name}\s+0x([0-9A-Fa-f]+)u", header).group(1), 16), off, name)
            self.assertRegex(regs, rf"R_{name} = 3'd{k}\b", name)
        self.assertIn(f"parameter [31:0] ID_WORD = 32'h{DESIGN['id'][2:6]}_{DESIGN['id'][6:]}", regs)

    def test_the_twin_models_the_same_design(self) -> None:
        twin = (ROOT / "prober" / "twin_hal.c").read_text()
        self.assertIn(f"#define PL_ID_WORD {DESIGN['id']}u", twin)
        for k in range(4):
            init = DESIGN["srl"]["cells"][str(k)]["init"]
            self.assertIn(f"({init}u >> i & 1u)", twin, f"shift register {k}")
            self.assertIn(f"parameter [31:0] SRL{k}_INIT = 32'h{init[2:6]}_{init[6:]}", (PLD / "s2a_regs.v").read_text())
        self.assertEqual(DESIGN["ram"]["init"], "0x0000000000000000")
        self.assertEqual((PLD / "s2a_regs.v").read_text().count("RAM64X1S #(.INIT(64'h0))"), 4)

    def test_the_memories_are_the_eight_and_the_source_has_no_other(self) -> None:
        regs = (PLD / "s2a_regs.v").read_text()
        top = (PLD / "s2a_top.v").read_text()
        code = lambda text: "\n".join(ln.split("//")[0] for ln in text.splitlines())  # noqa: E731
        self.assertEqual(re.findall(r"\b(RAM\w+|SRL\w+|FIFO\w+)\s+#", code(regs)), ["RAM64X1S"] * 4 + ["SRLC32E"] * 4)
        self.assertEqual(re.findall(r"\b(RAM\w+|SRL\w+|FIFO\w+)\s+#", code(top)), [])
        for text in (code(regs), code(top), code((IMPORTED / "carrier_axi3_lite.v").read_text())):
            self.assertFalse(re.findall(r"\b(?:reg|wire|logic)\b[^;\n]*\]\s*\w+\s*\[", text), "an array would be a memory nobody instantiated")
        regs_declared = re.findall(r"^\s*(\(\* shreg_extract = \"no\" \*\))?\s*reg\b", code(regs), re.M)
        self.assertGreaterEqual(len(regs_declared), 7)
        declared_plain = [m for m in re.finditer(r"^\s*reg\b", code(regs), re.M)]
        self.assertEqual(declared_plain, [], "every register of the register file is kept from becoming a shift register")
        self.assertIn("-no_srlextract", (PLD / "build_s2a.tcl").read_text())
        self.assertEqual(len(re.findall(r'\(\* DONT_TOUCH = "yes" \*\)', regs)), 8)

    def test_the_sites_in_the_description_the_constraints_the_build_script_and_the_record(self) -> None:
        xdc = (PLD / "s2a.xdc").read_text()
        tcl = (PLD / "build_s2a.tcl").read_text()
        ram_site, srl_site = DESIGN["ram"]["site"], DESIGN["srl"]["site"]
        loc = dict((cell, site) for site, cell in re.findall(r"^set_property LOC (\S+)\s+\[get_cells (\S+)\]", xdc, re.M))
        bel = dict((cell, b) for b, cell in re.findall(r"^set_property BEL (\S+)\s+\[get_cells (\S+)\]", xdc, re.M))
        self.assertEqual(loc, {**{DESIGN["ram"]["cells"][str(k)]["leaf"]: ram_site for k in range(4)},
                               **{DESIGN["srl"]["cells"][str(k)]["cell"]: srl_site for k in range(4)}})
        self.assertEqual(bel, {DESIGN["srl"]["cells"][str(k)]["cell"]: DESIGN["srl"]["cells"][str(k)]["bel"] for k in range(4)},
                         "a position is constrained for the shift registers only")
        table = dict(re.findall(r"(regs/\w+) \{(\S+ \S+)\}", tcl))
        self.assertEqual(table, {**{f"regs/ram{k}": f"{ram_site} any" for k in range(4)},
                                 **{f"regs/srl{k}": f"{srl_site} {DESIGN['srl']['cells'][str(k)]['bel']}" for k in range(4)}})
        placed = BUILT["memory_primitives"]
        self.assertEqual(sorted(placed), sorted(table))
        for k in range(4):
            self.assertEqual((placed[f"regs/ram{k}"]["site"], placed[f"regs/ram{k}"]["leaf"], placed[f"regs/ram{k}"]["primitive"]),
                             (ram_site, f"regs/ram{k}/SP", "RAMS64E"))
            self.assertEqual((placed[f"regs/srl{k}"]["site"], placed[f"regs/srl{k}"]["bel"], placed[f"regs/srl{k}"]["primitive"]),
                             (srl_site, DESIGN["srl"]["cells"][str(k)]["bel"], "SRLC32E"))
        self.assertEqual(sorted(placed[f"regs/ram{k}"]["bel"] for k in range(4)), ["A6LUT", "B6LUT", "C6LUT", "D6LUT"],
                         "the four memories are on four different LUT positions; which is where is the record's to say")

    def test_the_sites_obey_the_one_rule(self) -> None:
        """Section 12, point 5: no site of a column of sites numbered below 10. And they are SLICEM sites by the list
        Vivado gave, which is the only thing asked of it about the device."""
        sites = [ln.strip() for ln in (PLD / "slicem_sites.txt").read_text().splitlines() if ln.startswith("SLICE_")]
        self.assertGreater(len(sites), 100)
        self.assertEqual(len(sites), len(set(sites)))
        for site in (DESIGN["ram"]["site"], DESIGN["srl"]["site"]):
            self.assertIn(site, sites)
            self.assertGreaterEqual(int(re.match(r"SLICE_X(\d+)Y\d+$", site).group(1)), 10, site)
        self.assertNotEqual(DESIGN["ram"]["site"], DESIGN["srl"]["site"])

    def test_the_clock(self) -> None:
        self.assertIn(f"create_clock -period {DESIGN['clock']['constrained_period_ns']:.3f} ", (PLD / "s2a.xdc").read_text())
        self.assertEqual(float(BUILT["clock_period_ns"]), DESIGN["clock"]["constrained_period_ns"])
        self.assertGreaterEqual(BUILT["setup_slack_ns"], 0)
        self.assertGreaterEqual(BUILT["hold_slack_ns"], 0)


class TheRecordOfTheBuild(unittest.TestCase):
    def test_it_is_the_record_of_these_sources(self) -> None:
        self.assertEqual(sorted(BUILT["sources"]), sorted(["pl/s2a/s2a_top.v", "pl/s2a/s2a_regs.v", "imported/fabricmap/carrier_axi3_lite.v",
                                                           "pl/s2a/s2a.xdc", "pl/s2a/build_s2a.tcl"]))
        for rel, digest in BUILT["sources"].items():
            self.assertEqual(sha(ROOT / rel), digest, f"{rel} has changed since the design was built: the record and the bitstream are of another source")
        self.assertEqual((BUILT["part"], BUILT["name"]), ("xc7z010clg400-1", DESIGN["name"]))

    def test_the_staged_bitstream_is_the_one_the_record_names(self) -> None:
        bit = ROOT / "build" / "pl" / "s2a.bit"
        self.assertTrue(bit.is_file(), "the design is not staged: build it (pl/s2a/build_s2a.tcl) and copy the bitstream and the record")
        self.assertEqual((sha(bit), bit.stat().st_size), (BUILT["bitstream"]["sha256"], BUILT["bitstream"]["bytes"]))

    def test_the_set_of_s2_1_loads_that_bitstream(self) -> None:
        subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
        exp = json.loads((ROOT / "build" / "prober" / "expected_s2_1.json").read_text())
        self.assertEqual((exp["pl_design"]["sha256"], exp["pl_design"]["bytes"], exp["pl_design"]["file"], exp["pl_design"]["card_name"]),
                         (BUILT["bitstream"]["sha256"], BUILT["bitstream"]["bytes"], "build/pl/s2a.bit", "s2a.bit"))
        self.assertEqual(int(exp["params"][26], 16), int(DESIGN["id"], 16))
        self.assertEqual((int(exp["params"][24], 16), int(exp["params"][25], 16)), (int(DESIGN["base"], 16), int(DESIGN["base"], 16) + 0x1F))
        self.assertNotIn("frames", exp, "no frame has a known content with this design")


class ClosedBook(unittest.TestCase):
    def test_the_copied_files_are_the_ones_the_import_record_names(self) -> None:
        record = json.loads((IMPORTED / "IMPORT.json").read_text())
        self.assertEqual(sorted(record["files"]), sorted(p.name for p in IMPORTED.iterdir() if p.name != "IMPORT.json"))
        for name, entry in record["files"].items():
            self.assertEqual(sha(IMPORTED / name), entry["sha256"], name)
            self.assertFalse(entry["modified"])

    def test_the_design_s_directory_holds_these_files_and_no_other(self) -> None:
        self.assertEqual(sorted(p.name for p in PLD.iterdir()),
                         ["build.json", "build_s2a.tcl", "design.json", "list_sites.tcl", "s2a.xdc", "s2a_regs.v", "s2a_top.v", "slicem_sites.txt", "tb_s2a.v"])

    def test_vivado_is_asked_for_nothing_the_rule_excludes(self) -> None:
        """No logic location file, no mask file, no readback file, no report, no checkpoint, no essential bits; and
        the two scripts ask the device model for the names of SLICEM sites and for nothing else."""
        for name in ("build_s2a.tcl", "list_sites.tcl"):
            text = "\n".join(ln.split("#")[0] if not ln.lstrip().startswith("puts") else ln for ln in (PLD / name).read_text().splitlines())
            for forbidden in ("logic_location", "mask_file", "readback_file", "-bin_file", "essential", "report_", "write_checkpoint", "write_edif",
                              "write_verilog", "write_cfgmem", "get_tiles", "get_bels", "get_pips", "get_nodes", "get_wires", "get_site_pips", "RPM", "TILE"):
                self.assertNotIn(forbidden, text, f"{name}: {forbidden}")
            self.assertEqual(len(re.findall(r"\bwrite_bitstream\b", text)), 1 if name == "build_s2a.tcl" else 0)
        self.assertEqual(re.findall(r"get_sites[^\]]*", (PLD / "list_sites.tcl").read_text().split("\nset names")[1].split("\n")[1]), ["get_sites -filter {SITE_TYPE == SLICEM}"])
        self.assertNotIn("get_sites", (PLD / "build_s2a.tcl").read_text())
        self.assertRegex((PLD / "build_s2a.tcl").read_text(), r"write_bitstream -force \$outdir/s2a\.bit\n")

    def test_nothing_in_the_design_names_the_database_or_a_frame_address(self) -> None:
        for path in [*PLD.iterdir(), *IMPORTED.iterdir()]:
            if path.name in ("slicem_sites.txt", "IMPORT.json"):      # a list of names; a record whose own sentence says "names no frame address"
                continue
            if path.name == "carrier.bit":                           # the carrier's bitstream (section 24): not a text, and nothing here reads into it
                continue
            text = path.read_text()
            for word in ("prjxray", "segbits", "tilegrid", "baseaddr", "frame address"):
                self.assertNotIn(word.lower(), text.lower(), f"{path.name}: {word}")
            self.assertFalse(re.findall(r"\bFAR\b", text), f"{path.name}: the address register's name")
            self.assertFalse(re.findall(r"0x00[048c][0-9a-f]{5}\b", text, re.I), f"{path.name}: a number shaped like a frame address")


if __name__ == "__main__":
    unittest.main()

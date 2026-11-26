"""S3.0 on the host: one word of COR0 read through PCAP — docs/s3_plan.md, sections 5 and 12.

The register is a fifth on the prober's list (FAR, IDCODE, CTL0, STAT, COR0) and on the reader's; everything else
that is not on the list stays refused, COR1 and MASK among them. The two sets are S2.0's and S2.1's with one
operation more. The device and the design here are models (prober/twin_hal.c): what COR0 holds in them is made up."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import packets  # noqa: E402
import s1a_run  # noqa: E402
import s2_judge  # noqa: E402
from test_prober_s2 import NONE, REF, TWIN, Run, params  # noqa: E402
from test_prober_packets import guard  # noqa: E402
from test_s2_host import DESIGN, has, judge6, judge7  # noqa: E402
from test_s1a_run import KNOWN  # noqa: E402

BUILD = ROOT / "build" / "prober"
FAR, IDCODE, CTL0, STAT, COR0 = range(5)
OPS6 = [(REF, 1, FAR), (REF, NONE, IDCODE), (REF, NONE, CTL0), (REF, NONE, STAT), (REF, NONE, COR0)]
OPS7 = [(REF, NONE, IDCODE), (REF, NONE, CTL0), (REF, NONE, STAT), (REF, NONE, COR0)]
# the image of S3.0: section 32's (8bf3799c…, 19,244 bytes) with the COR0 read added and nothing else
IMAGE_SHA256 = "18cd254d4915518a369bccf4ed80cecb677b4c67bfc02abff2a224c8eccf5557"
IMAGE_BYTES = 19260


def genreg(n: int) -> list[int]:
    subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
    out = subprocess.run([str(TWIN), "genreg", str(n)], check=True, capture_output=True, text=True).stdout
    return [int(x, 16) for x in out.split()]


class TheRead(unittest.TestCase):
    def test_the_stream_of_a_cor0_read_is_table_6_1_with_cor0_s_address(self) -> None:
        self.assertEqual(genreg(COR0), [0x20000000, 0x28012001, 0x20000000, 0x20000000])
        self.assertEqual(0x28012001, 0x28000001 | 9 << 13, "a type-1 read of one word of register 01001 (UG470 table 5-23)")
        self.assertEqual(packets.REG[9], "COR0")
        self.assertEqual([genreg(k)[1] for k in range(4)], [0x28002001, 0x28018001, 0x2800A001, 0x2800E001], "the four before it are as they were")

    def test_the_guard_and_the_reader_take_it_and_still_nothing_else(self) -> None:
        cor0, cor1, mask = ([0x20000000, h, 0x20000000, 0x20000000] for h in (0x28012001, 0x2801C001, 0x2800C001))
        self.assertEqual((guard(cor0, maxr=404), packets.readonly_problems(cor0, 0xB98, 0xB9A, 404)), (0, []))
        for s, name in ((cor1, "COR1"), (mask, "MASK")):
            self.assertNotEqual(guard(s, maxr=404), 0, name)
            self.assertTrue(packets.readonly_problems(s, 0xB98, 0xB9A, 404), name)
        two = [0x20000000, 0x28012002, 0x20000000, 0x20000000]
        self.assertNotEqual(guard(two, maxr=404), 0, "two words of COR0")
        write = [0x20000000, 0x30012001, 0x02003FE5, 0x20000000]
        self.assertNotEqual(guard(write, maxr=404), 0, "a write to COR0")
        self.assertIn("a write to COR0", " ".join(packets.readonly_problems(write, 0xB98, 0xB9A, 404)))

    def test_a_register_beyond_cor0_is_refused_as_a_parameter(self) -> None:
        r = Run(6, ops=OPS6[:4] + [(REF, NONE, 5)])
        self.assertEqual((r.status, r.rc, r.n_records, r.dmas), (0x500, 0x500, 0, []), "nothing is sent")
        r = Run(6, ops=OPS6)
        self.assertEqual((r.rc, r.status, r.violations), (0, 1, []))


class TheJudge(unittest.TestCase):
    def test_stage_six_reads_cor0_and_says_what_its_fields_are(self) -> None:
        v = judge6(Run(6, ops=OPS6, creg="cor0:02003fe5"))
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        reg = v["registers"]["COR0"]
        self.assertEqual((reg["value"], reg["SINGLE"], reg["start_up_clock"], reg["bits_set_the_table_does_not_name"]), ("0x02003fe5", 0, "CCLK", []))
        self.assertEqual(reg["fields"], {"PWRDWN_STAT": 0, "DONE_PIPE": 1, "DRIVE_DONE": 0, "SINGLE": 0, "OSCFSEL": 0, "SSCLKSRC": 0,
                                         "DONE_CYCLE": 3, "MATCH_CYCLE": 7, "LOCK_CYCLE": 7, "GTS_CYCLE": 4, "GWE_CYCLE": 5})
        self.assertIn("not single-shot", reg["by_the_register_s_word"])
        self.assertEqual(sorted(v["registers"]), ["COR0", "CTL0", "FAR", "IDCODE", "STAT"])

    def test_single_shot_and_another_clock_are_said(self) -> None:
        reg = judge6(Run(6, ops=OPS6, creg="cor0:10808000"))["registers"]["COR0"]
        self.assertEqual((reg["SINGLE"], reg["start_up_clock"], reg["fields"]["SSCLKSRC"], reg["bits_set_the_table_does_not_name"]), (1, "UserClk", 1, [28]))
        self.assertIn("RCAP must be sent", reg["by_the_register_s_word"])
        self.assertEqual(judge6(Run(6, ops=OPS6, creg="cor0:00010000"))["registers"]["COR0"]["start_up_clock"], "JTAGClk")

    def test_stage_seven_reads_it_with_the_design_loaded(self) -> None:
        v = judge7(Run(7, ops=OPS7, creg="cor0:02003fe5"))
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        self.assertEqual(v["registers"]["COR0"]["value"], "0x02003fe5")
        self.assertEqual(v["pl"]["says"], "nothing wrong")

    def test_a_cor0_that_moves_is_not_one_value(self) -> None:
        r = Run(6, ops=OPS6)
        words = list(r.words)
        second = 1 + 5 + 4                                       # the baseline, the first pass, then the second pass up to its COR0
        words[r.hb + second * 480 + 68 + 4] ^= 0x00800000
        v = s2_judge.judge(words, KNOWN, r.params, stage=6)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "COR0 does not read the same every time"))


class TheSetsAndTheImage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "all"], check=True)
        import test_s1b2
        test_s1b2.the_set()                                      # the image and every set of it, written as the image's tests write them

    def test_the_image_is_the_one_of_s3_0(self) -> None:
        image = (BUILD / "prober.bin").read_bytes()
        self.assertEqual((hashlib.sha256(image).hexdigest(), len(image)), (IMAGE_SHA256, IMAGE_BYTES))

    def test_s3_0_is_the_set_of_s2_0_with_cor0_as_a_fifth_operation(self) -> None:
        a, b = (json.loads((BUILD / f"expected_{n}.json").read_text()) for n in ("s3_0", "s2_0"))
        par, old = [int(w, 16) for w in a["params"]], [int(w, 16) for w in b["params"]]
        self.assertEqual(par, params(6, OPS6, w9=0x00200000))
        self.assertEqual([k for k in range(32) if par[k] != old[k]], [6, 10, 12, 20])
        self.assertEqual((a["records"], a["image_sha256"], a["frames"]), (17, IMAGE_SHA256, b["frames"]))
        self.assertIs(s1a_run.STAGES["s3_0"]["judge"], s1a_run.STAGES["s2_0"]["judge"])

    def test_s3_0b_is_the_set_of_s2_1_with_cor0_as_a_fourth(self) -> None:
        a, b = (json.loads((BUILD / f"expected_{n}.json").read_text()) for n in ("s3_0b", "s2_1"))
        par, old = [int(w, 16) for w in a["params"]], [int(w, 16) for w in b["params"]]
        self.assertEqual(par, params(7, OPS7, w9=0x00200000))
        self.assertEqual([k for k in range(32) if par[k] != old[k]], [6, 10, 12, 19])
        self.assertEqual((a["records"], a["pl_design"], a["image_sha256"]), (14, b["pl_design"], IMAGE_SHA256))
        self.assertEqual(s1a_run.known_for("s3_0b"), DESIGN)

    def test_the_twin_run_with_each_set_s_own_words_passes(self) -> None:
        for name, stage, judge in (("s3_0", 6, judge6), ("s3_0b", 7, judge7)):
            with self.subTest(name):
                exp = json.loads((BUILD / f"expected_{name}.json").read_text())
                words = {f"w{k}": int(w, 16) for k, w in enumerate(exp["params"])}
                r = Run(stage, ops=[], **words)
                v = judge(r, s1a_run.known_for(name), [int(w, 16) for w in exp["params"]])
                self.assertEqual((v["verdict"], v["problems"], r.rc), ("PASS", [], 0))
                self.assertEqual(v["expected_console"], exp["console"])
                self.assertIn("COR0", v["registers"])


if __name__ == "__main__":
    unittest.main()

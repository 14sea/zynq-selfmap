"""S2.0 and S2.1 on the host: the judge of the two stages, and the run script with the two sets — docs/s2_plan.md,
sections 6 and 7. The results judged here come from the twin; the judge is then given results that were tampered
with, since a judge that agrees with a correct prober has shown nothing yet."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_0_judge  # noqa: E402
import s2_1_judge  # noqa: E402
import s2_judge  # noqa: E402
from test_prober_s2 import ID_WORD, N6, N7, PL, PLB, REC, SLCR_WORDS, Run  # noqa: E402
from test_s1a_run import FakeUBoot, KNOWN  # noqa: E402

DESIGN = json.loads((ROOT / "pl" / "s2a" / "design.json").read_text())
LOADED = [int(DESIGN["srl"]["cells"][str(k)]["init"], 16) for k in range(4)]
# a problem of one of these kinds says the judge and the prober disagree about what the raw words mean; a run that
# merely went badly must show none of them
DISAGREE = ("but its raw words say", "the records imply", "the readings in its header", "do not add up", "not the pinned one",
            "health flag", "its log implies", "is due", "the records show", "that is not so", "ends after", "is missing",
            "after the point where the schedule ends", "outside what the prober may touch", "never came to it", "access(es) follow it")


def judge6(r: Run, known=KNOWN, planned=None) -> dict:
    return s2_0_judge.judge(r.words, known, r.params if planned is None else planned)


def judge7(r: Run, known=DESIGN, planned=None) -> dict:
    return s2_1_judge.judge(r.words, known, r.params if planned is None else planned)


def has(v: dict, text: str) -> bool:
    return any(text in p for p in v["problems"])


class Clean(unittest.TestCase):
    def test_stage_six_passes_and_says_what_the_registers_hold(self) -> None:
        v = judge6(Run(6, creg="idcode:13722093,ctl0:00000501,stat:401079fc"))
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        reg = v["registers"]
        self.assertEqual(sorted(reg), ["CTL0", "FAR", "IDCODE", "STAT"])
        self.assertEqual((reg["IDCODE"]["value"], reg["IDCODE"]["low_28_bits_as_known"]), ("0x13722093", True))
        self.assertEqual((reg["CTL0"]["value"], reg["CTL0"]["GLUTMASK_B"]), ("0x00000501", 1))
        self.assertIn("not masked", reg["CTL0"]["by_the_register_s_word"])
        self.assertEqual(reg["CTL0"]["bits_set"], ["10 ConfigFallback", "8 GLUTMASK_B", "0 GTS_USR_B"])
        self.assertEqual(reg["STAT"]["value"], "0x401079fc")
        self.assertEqual(v["registers_without_a_clean_value"], [])
        self.assertEqual(v["expected_console"], ["SM6 start", "SM6 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (N6, 64 + N6 * REC)])

    def test_the_mask_on_is_a_finding_and_not_a_failure(self) -> None:
        v = judge6(Run(6, creg="ctl0:00000401"))
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["registers"]["CTL0"]["GLUTMASK_B"], 0)
        self.assertIn("is masked", v["registers"]["CTL0"]["by_the_register_s_word"])

    def test_a_ctl0_that_fits_no_description_is_recorded_as_read(self) -> None:
        v = judge6(Run(6, creg="ctl0:00020d01"))
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["registers"]["CTL0"]["bits_set_the_table_does_not_name"], [11, 17])

    def test_the_revision_of_the_die_is_its_own(self) -> None:
        for idcode in ("03722093", "23722093", "f3722093"):
            self.assertEqual(judge6(Run(6, creg=f"idcode:{idcode}"))["verdict"], "PASS", idcode)

    def test_stage_seven_passes_and_says_what_the_design_answered(self) -> None:
        v = judge7(Run(7))
        self.assertEqual((v["verdict"], v["problems"]), ("PASS", []))
        pl = v["pl"]
        self.assertEqual((pl["accesses"], pl["code"], pl["id"], pl["ram_states_read_back"]), (1164, "0x0", "0x53324131", 4))
        self.assertEqual(pl["shift_registers_hold"], [f"{w:#010x}" for w in LOADED])
        self.assertEqual(pl["writes_counted"], {"ram": 256, "shifts": 0})
        self.assertNotEqual(pl["counter"][0], pl["counter"][1])
        self.assertEqual({k: x["read"] for k, x in v["slcr"].items()},
                         {"LVL_SHFTR_EN": "0000000f", "FPGA_RST_CTRL": "00000000", "FPGA0_CLK_CTRL": "00400800", "PLL_STATUS": "0000003f"})
        self.assertEqual(sorted(v["registers"]), ["CTL0", "FAR", "IDCODE", "STAT"])
        self.assertEqual(v["expected_console"][1], "SM7 end status=00000001 records=%08x anomalies=00000000 words=%08x" % (N7, 64 + PLB + N7 * REC))

    def test_stage_seven_holds_no_frame_to_a_known_content(self) -> None:
        self.assertEqual(s2_1_judge.judge(Run(7).words, DESIGN, Run(7).params)["verdict"], "PASS")
        changed = {"frames": {k: dict(v, words=["00000001"] * 101) for k, v in KNOWN["frames"].items()}, **DESIGN}
        self.assertEqual(judge7(Run(7), known=changed)["verdict"], "PASS", "whatever the carrier's frames were, they are not asked for")


class AKnownAnswerThatIsNotGiven(unittest.TestCase):
    def test_idcode(self) -> None:
        v = judge6(Run(6, creg="idcode:13722094"))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "IDCODE reads 0x13722094"))
        self.assertFalse(v["registers"]["IDCODE"]["low_28_bits_as_known"])

    def test_the_address_register_must_follow_the_rule_the_board_showed(self) -> None:
        v = judge6(Run(6, rule="next"))
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "the address register reads 0x00000b9a after the pad and 1 frame(s) at 0x00000b99"))
        v = judge6(Run(6, rule="skipdata"))
        self.assertEqual(v["verdict"], "PASS", "that rule differs from the board's only where the pad is read alone, which this set does not do")

    def test_a_frame_that_is_not_the_known_one(self) -> None:
        other = json.loads(json.dumps(KNOWN))
        w = other["frames"]["0x00000b99"]["words"]; w[40] = "%08x" % (int(w[40], 16) ^ 4)
        v = judge6(Run(6), known=other)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "differs from the known frame"))

    def test_the_shift_registers_must_hold_what_the_design_loads(self) -> None:
        other = json.loads(json.dumps(DESIGN)); other["srl"]["cells"]["2"]["init"] = "0x13579BDE"
        v = judge7(Run(7), known=other)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "do not hold what the design's source loads"))
        v = judge7(Run(7), known={})
        self.assertTrue(has(v, "were not given"))


class ARunThatWentBadlyIsFailedAndUnderstood(unittest.TestCase):
    """The prober stopped or met something, and the judge — from the raw words alone — comes to the same account."""

    def consistent(self, v: dict, status: int) -> None:
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(v["header"]["status"], f"{status:#x}")
        self.assertFalse([p for p in v["problems"] if any(d in p for d in DISAGREE)], v["problems"])

    def test_stage_six(self) -> None:
        for fault, status in (("statmoves", 0x400), ("farflip@7", 0x400), ("farflip@8", 0x400), ("farshort@3", 0x400), ("regdisturbs", 0x300),
                              ("err@13", 0x221), ("timeout@13", 0x222), ("drop@13", 0x223), ("padnz@2", 0x400), ("short@1", 0x610),
                              ("seu", 0x105), ("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104), ("stale", 0x620)):
            with self.subTest(fault):
                self.consistent(judge6(Run(6, fault)), status)

    def test_a_register_that_moves_is_named(self) -> None:
        v = judge6(Run(6, "statmoves"))
        self.assertTrue(has(v, "STAT does not read the same every time"))
        v = judge6(Run(6, "farflip@8"))
        self.assertTrue(has(v, "CTL0 does not read the same every time"))
        self.assertNotIn("GLUTMASK_B", v["registers"]["CTL0"], "nothing is concluded from a register that read two ways")

    def test_a_gate_stop_names_the_gate(self) -> None:
        self.assertTrue(has(judge6(Run(6, "seu")), "the run stopped at the SEU_EN gate"))
        self.assertTrue(has(judge7(Run(7, "fclk")), "the run stopped at the FPGA0_CLK_CTRL gate"))

    def test_stage_seven(self) -> None:
        for fault, status in (("plid", 0xA02), ("scratchstuck", 0xA03), ("countstuck", 0xA04), ("ramstuck", 0xA05), ("ramwild", 0xA05),
                              ("srlmoves", 0xA06), ("plcount", 0xA07), ("lvl", 0x110), ("fpgarst", 0x111), ("fclk", 0x112), ("pll", 0x113),
                              ("seu", 0x105), ("nodone", 0x103), ("statmoves", 0x400), ("err@3", 0x621), ("err@8", 0x221), ("regdisturbs", 0x300)):
            with self.subTest(fault):
                self.consistent(judge7(Run(7, fault)), status)

    def test_what_stopped_user_logic_is_said_in_words(self) -> None:
        v = judge7(Run(7, "ramstuck"))
        self.assertTrue(has(v, "status 0xa05 (the LUT RAM)"))
        self.assertEqual((v["pl"]["says"], v["pl"]["ram_states_read_back"]), ("the LUT RAM", 1))

    def test_an_envelope_the_design_does_not_fit_in(self) -> None:
        r = Run(7, w25=PL + 0x0F)
        self.consistent(judge7(r), 0xA01)
        self.assertEqual(judge7(r)["pl"]["says"], "the prober's own helper refused an address")

    def test_bad_parameters(self) -> None:
        for stage, j in ((6, judge6), (7, judge7)):
            v = j(Run(stage, w13=1))
            self.assertEqual(v["verdict"], "FAIL")
            self.assertTrue(has(v, "bad parameters"))


class TheJudgeDoesNotTakeTheBoardsWord(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.r6, cls.r7 = Run(6), Run(7)

    def tampered(self, r: Run, change, stage: int) -> dict:
        words = list(r.words)
        change(words)
        j = s2_0_judge if stage == 6 else s2_1_judge
        return j.judge(words, KNOWN if stage == 6 else DESIGN, r.params)

    def at(self, r: Run, record: int, field: int) -> int:
        return r.hb + record * REC + field

    def test_a_value_changed_under_a_clean_code(self) -> None:
        ctl0_again = 1 + 4 + 2                                    # the baseline, the first pass, then FAR, IDCODE, CTL0
        def change(w): w[self.at(self.r6, ctl0_again, 68 + 4)] ^= 0x100
        v = self.tampered(self.r6, change, 6)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, f"record {ctl0_again}: code 0x0, but its raw words say 0x13"))
        self.assertTrue(has(v, "CTL0 does not read the same every time"))

    def test_a_header_that_reads_another_register(self) -> None:
        def change(w): w[self.at(self.r6, 3, 60)] = 0x28012001   # COR0 in the place of CTL0
        v = self.tampered(self.r6, change, 6)
        self.assertTrue(has(v, "record 3: the CTL0 read stream is not the pinned one"))
        self.assertTrue(has(v, "is not read-only: word 1: a read of COR0"))

    def test_a_write_among_the_streams(self) -> None:
        def change(w): w[self.at(self.r6, 3, 60)] = 0x3000A001   # a write to CTL0
        self.assertTrue(has(self.tampered(self.r6, change, 6), "a write to CTL0"))

    def test_the_headers_claims(self) -> None:
        for name, index, value, text in (("status", 2, 0x400, "the header's status is 0x400; the records imply 0x1"),
                                         ("anomalies", 4, 1, "the header counts 1 anomalies; the records show 0"),
                                         ("stop record", 18, 3, "the header's stop record is 0x3"),
                                         ("a reserved word", 20, 1, "reserved header words are not zero"),
                                         ("SEU_EN in the control word", 8, self.r6.words[8] | 0x100, "fail the SEU_EN gate, yet the run went on"),
                                         ("the cache on", 12, self.r6.words[12] | 4, "fail the data-cache gate, yet the run went on")):
            with self.subTest(name):
                def change(w, index=index, value=value): w[index] = value
                v = self.tampered(self.r6, change, 6)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(has(v, text), v["problems"])

    def test_a_run_that_did_not_do_what_was_planned(self) -> None:
        planned = list(self.r6.params); planned[12] = 0x3120      # IDCODE and CTL0 the other way round
        v = s2_0_judge.judge(self.r6.words, KNOWN, planned)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertTrue(has(v, "not the planned ones (word(s) [12])"))

    def test_a_record_missing_or_one_too_many(self) -> None:
        r = self.r6
        short = list(r.words[:-REC]); short[3] -= 1; short[5] -= REC
        v = s2_0_judge.judge(short, KNOWN, r.params)
        self.assertTrue(has(v, "is missing"))
        longer = list(r.words) + r.words[-REC:]; longer[3] += 1; longer[5] += REC
        v = s2_0_judge.judge(longer, KNOWN, r.params)
        self.assertTrue(has(v, "after the point where the schedule ends"))

    def test_a_result_of_the_other_stage_or_of_the_wrong_length(self) -> None:
        self.assertEqual(s2_0_judge.judge(self.r7.words, KNOWN, self.r7.params)["verdict"], "INVALID")
        self.assertEqual(s2_1_judge.judge(self.r6.words, DESIGN, self.r6.params)["verdict"], "INVALID")
        self.assertEqual(s2_0_judge.judge(self.r6.words[:-1], KNOWN, self.r6.params)["verdict"], "INVALID")
        self.assertEqual(s2_0_judge.judge(self.r6.words[:10], KNOWN, self.r6.params)["verdict"], "INVALID")

    def test_sizes_that_do_not_add_up(self) -> None:
        def one_word_more(w): w[5] += 1; w.append(0)              # the buffer is as long as the header says, and that is one too many
        def records_beyond_the_most(w):
            more = s2_judge.MAX_RECORDS + 1 - w[3]
            w.extend(w[-REC:] * more); w[3] += more; w[5] += more * REC
        for stage, r in ((6, self.r6), (7, self.r7)):
            for name, change in (("the size of a record", lambda w: w.__setitem__(6, REC - 1)),
                                 ("the size of the header", lambda w: w.__setitem__(7, w[7] + 1)),
                                 ("a total that is not the header and the records", one_word_more),
                                 ("more records than a run can make", records_beyond_the_most)):
                with self.subTest(name, stage=stage):
                    v = self.tampered(r, change, stage)
                    self.assertEqual(v["verdict"], "INVALID")
                    self.assertTrue(has(v, f"sizes do not add up for a stage-{stage} result"), v["problems"][:3])
        self.assertTrue(has(s2_0_judge.judge(self.r7.words, KNOWN, self.r7.params), "sizes do not add up for a stage-6 result"))
        self.assertTrue(has(s2_1_judge.judge(self.r6.words, DESIGN, self.r6.params), "sizes do not add up for a stage-7 result"))

    def test_parameters_no_prober_would_have_run_with(self) -> None:
        """The echoed block is the one planned, word for word, and the status says done: only the judge's own reading
        of the block can say that no prober runs with it."""
        cases = ((6, 13, 1, "a reserved word"), (6, 11, 1, "another reserved word"), (6, 9, 0, "no limit to the wait"),
                 (6, 12, 0x3214, "a register that is not one of the four"), (6, 12, 0x13210, "a register for an operation that is not there"),
                 (6, 15, 0x300, "a wait that is not one of the two"), (6, 24, PL, "an envelope in the PL where no user logic is used"),
                 (6, 28, 0xF, "an SLCR word where none is read"), (6, 2, 7, "the other stage"),
                 (7, 25, PL + 0x20, "an envelope beyond the design"), (7, 24, PL - 4, "an envelope below the PL"),
                 (7, 24, PL + 0x20, "an envelope that ends before it begins"), (7, 27, 1, "a reserved word"), (7, 2, 6, "the other stage"))
        for stage, index, value, name in cases:
            with self.subTest(name, stage=stage):
                r = self.r6 if stage == 6 else self.r7
                words = list(r.words); words[32 + index] = value
                j = s2_0_judge if stage == 6 else s2_1_judge
                v = j.judge(words, KNOWN if stage == 6 else DESIGN, words[32:64])
                self.assertEqual(v["verdict"], "INVALID", v["problems"][:3])
                self.assertTrue(has(v, f"not a valid stage-{stage} parameter block"))

    # ---- the PL block
    def log_at(self, i: int) -> int:
        return 64 + 16 + 2 * i

    def test_the_log_is_walked_against_the_sequence(self) -> None:
        steps = s2_judge.pl_schedule(ID_WORD)
        ram_read = next(i for i, st in enumerate(steps) if not st["write"] and st["off"] == 0x10 and st.get("value") == 0xF)
        ram_write = next(i for i, st in enumerate(steps) if st["write"] and st["off"] == 0x10 and st["value"] == 0xF)
        cases = (
            ("a value written that is not the one due", lambda w: w.__setitem__(self.log_at(ram_write) + 1, 0xE), "0x0000000e written to offset 0x10, where 0x0000000f is due"),
            ("an answer the design must not give, under a clean code", lambda w: w.__setitem__(self.log_at(ram_read) + 1, 0xD), "its log implies 0x5 (the LUT RAM)"),
            ("and accesses after it", lambda w: w.__setitem__(self.log_at(ram_read) + 1, 0xD), "access(es) follow it"),
            ("an access that is not the one due", lambda w: w.__setitem__(self.log_at(5), PL + 0x08), "a read of offset 0x8, where a write to offset 0x4 is due"),
            ("an address outside the envelope", lambda w: w.__setitem__(self.log_at(0), PL + 0x20), "is outside what the prober may touch"),
            ("a write that shifts", lambda w: w.__setitem__(self.log_at(1), PL + 0x18 | 1), "write to 0x40000018 is outside what the prober may touch"),
            ("a code without a cause", lambda w: (w.__setitem__(64 + 2, 5), w.__setitem__(64 + 3, 1164)), "the PL block's code is 0x5 (the LUT RAM); its log implies 0x0"),
            ("the place it says it stopped at", lambda w: w.__setitem__(64 + 3, 7), "that is not so"),
            ("fewer accesses counted than logged", lambda w: w.__setitem__(64 + 1, 1163), "holds words after the last access it counts"),
            ("a log that ends with nothing to end it", lambda w: (w.__setitem__(64 + 1, 1162), [w.__setitem__(self.log_at(k) + j, 0) for k in (1162, 1163) for j in (0, 1)]), "ends after 1162 of 1164"),
            ("a reserved word", lambda w: w.__setitem__(64 + 9, 1), "reserved words of the PL block are not zero"),
            ("an SLCR word that is not the wanted one", lambda w: w.__setitem__(64 + 6, 0x00200A00), "fail the FPGA0_CLK_CTRL gate, yet the run went on"),
            ("the identification word", lambda w: w.__setitem__(self.log_at(0) + 1, 0x53324132), "its log implies 0x2 (the identification register)"),
            ("a counter that stood still", lambda w: w.__setitem__(self.log_at(10) + 1, w[self.log_at(9) + 1]), "its log implies 0x4 (the counter)"),
            ("the design's count", lambda w: w.__setitem__(self.log_at(1163) + 1, 0x00010100), "its log implies 0x7"),
        )
        for name, change, text in cases:
            with self.subTest(name):
                v = self.tampered(self.r7, change, 7)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertTrue(has(v, text), v["problems"][:4])

    def test_shift_registers_changed_alike_in_both_readings_are_still_caught(self) -> None:
        steps = s2_judge.pl_schedule(ID_WORD)
        reads = [i for i, st in enumerate(steps) if not st["write"] and st["off"] == 0x18]
        def change(w):
            for i in (reads[9], reads[32 + 9]):                   # address 9, the first reading and the second
                w[self.log_at(i) + 1] ^= 1
        v = self.tampered(self.r7, change, 7)
        self.assertTrue(has(v, "do not hold what the design's source loads"))
        self.assertFalse(has(v, "its log implies"), "the prober could not have seen it: the two readings agree")

    def test_a_pl_block_without_its_magic_or_with_too_many_accesses(self) -> None:
        self.assertEqual(self.tampered(self.r7, lambda w: w.__setitem__(64, 0), 7)["verdict"], "INVALID")
        self.assertEqual(self.tampered(self.r7, lambda w: w.__setitem__(65, 1281), 7)["verdict"], "INVALID")

    def test_an_access_to_the_design_in_a_run_that_never_came_to_it(self) -> None:
        r = Run(7, "fclk")
        def change(w): w[64 + 1] = 1; w[self.log_at(0)] = PL; w[self.log_at(0) + 1] = ID_WORD
        v = self.tampered(r, change, 7)
        self.assertTrue(has(v, "a gate stop, yet the PL block shows an access to the design"))
        r = Run(7, "seu")
        v = self.tampered(r, lambda w: w.__setitem__(64 + 4, 0xF), 7)
        self.assertTrue(has(v, "SLCR words are recorded although a gate before them fails"))
        r = Run(7, "err@3")                                       # the gates hold, the reference frame's first reading fails
        self.assertEqual((r.status, list(r.plb[1:4])), (0x621, [0, 0, 0xFFFFFFFF]))
        self.assertFalse(has(judge7(r), "never came to it"))
        for name, change in (("an access", change),
                             ("a place it stopped at", lambda w: w.__setitem__(64 + 3, 0)),
                             ("a code", lambda w: w.__setitem__(64 + 2, 5))):
            with self.subTest(name):
                self.assertTrue(has(self.tampered(r, change, 7), "an access to the design in a run that never came to it"))

    def test_user_logic_failed_and_yet_records_follow(self) -> None:
        r = Run(7, "plid")
        clean = self.r7
        words = list(r.words) + clean.words[clean.hb + REC: clean.hb + 2 * REC]
        words[3] += 1; words[5] += REC
        v = s2_1_judge.judge(words, DESIGN, r.params)
        self.assertTrue(has(v, "after the point where the schedule ends"))


class Board(FakeUBoot):
    """The pretend U-Boot of the run-script tests with what S2.1 asks at the prompt: the four SLCR words and the
    design's identification register; and a card that may hold the probe design."""
    SLCR = {0xF8000900: 0x0000000F, 0xF8000240: 0x00000000, 0xF8000170: 0x00400800, 0xF800010C: 0x0000003F}

    def __init__(self, fault: str = "", **quirks) -> None:
        super().__init__(fault, **quirks)
        if quirks.get("card_has_s2a"):
            self.card["s2a.bit"] = (ROOT / "build" / "pl" / "s2a.bit").read_bytes()

    def rd(self, a: int) -> int:
        if a in self.SLCR:
            return self.q.get("slcr", {}).get(a, self.SLCR[a])
        if a == PL:
            return self.q.get("pl_id", ID_WORD)
        return super().rd(a)

    def cmd(self, line: str, timeout: float = 10):
        if line == "md.l 40000000 1" and self.q.get("pl_does_not_answer"):
            self.commands.append(line)
            return (line + "\r\n").encode(), False                # the processor stands still: no prompt comes back
        return super().cmd(line, timeout)


def run(stage: str, fault: str = "", **quirks):
    import subprocess
    subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_prober_image"], cwd=ROOT, check=True, capture_output=True)
    exp = json.loads(s1a_run.STAGES[stage]["expected"].read_text())
    pl = s1a_run.pl_file(exp).read_bytes()
    out = Path(scratch_dirs.mkdtemp(prefix="smout2_"))
    u = Board(fault, far_rule="skip", **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), s1a_run.known_for(stage), len(pl),
                          f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", "s0000002.bin", stage)
    return rec, u, out


class ThroughTheRunScript(unittest.TestCase):
    def test_s2_0_clean(self) -> None:
        rec, u, out = run("s2_0", card_has_pl=True)
        self.assertEqual((rec["verdict"], rec["problems"], rec["judge"]), ("PASS", [], "PASS"))
        self.assertEqual((rec["result_layout"], rec["result_words"], rec["pl_source"]), ("s2_0", 64 + N6 * REC, "card"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertEqual(rec["console"][0], "SM6 start")
        v = json.loads((out / "verdict.json").read_text())
        self.assertEqual(v["registers"]["CTL0"]["GLUTMASK_B"], 1)
        self.assertIn("fatload mmc 0:1 04000000 carrier.bit", u.commands)
        self.assertFalse([c for c in u.commands if c.startswith("md.l 4000") or c.startswith("md.l f8000")], "this set asks nothing of the PL or the SLCR at the prompt")

    def test_s2_0_with_the_mask_on_passes_and_says_so(self) -> None:
        rec, u, out = run("s2_0", card_has_pl=True, env={"SM_CREG": "ctl0:00000401"})
        self.assertEqual(rec["verdict"], "PASS")
        self.assertEqual(json.loads((out / "verdict.json").read_text())["registers"]["CTL0"]["GLUTMASK_B"], 0)

    def test_s2_0_with_a_wrong_idcode_is_saved_whole_and_fails(self) -> None:
        rec, u, out = run("s2_0", card_has_pl=True, env={"SM_CREG": "idcode:ffffffff"})
        self.assertEqual((rec["verdict"], rec["judge"], rec["card_verified"]), ("FAIL", "FAIL", True))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)

    def test_s2_1_clean(self) -> None:
        rec, u, out = run("s2_1", card_has_s2a=True)
        self.assertEqual((rec["verdict"], rec["problems"], rec["judge"]), ("PASS", [], "PASS"))
        self.assertEqual((rec["result_layout"], rec["result_words"], rec["pl_source"]), ("s2_1", 64 + PLB + N7 * REC, "card"))
        self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
        self.assertEqual(json.loads((out / "verdict.json").read_text())["pl"]["accesses"], 1164)
        c = u.commands
        asked = ["md.l f8000900 1", "md.l f8000240 1", "md.l f8000170 1", "md.l f800010c 1", "md.l 40000000 1"]
        where = [c.index(x) for x in asked]
        self.assertEqual(where, sorted(where), "the four SLCR words, then the design, in that order")
        load = next(i for i, x in enumerate(c) if x.startswith("fpga loadb"))
        go = next(i for i, x in enumerate(c) if x.startswith("go "))
        self.assertTrue(load < where[0] and where[-1] < go, "after the design is loaded and before the prober is started")
        self.assertEqual([x for x in c if x.startswith("md.l 4")], ["md.l 40000000 1"], "one read of the PL at the prompt, and no write")
        self.assertFalse([x for x in c if x.startswith("mw.l 4") or x.startswith("mw.l f8000")])
        self.assertIn("fatload mmc 0:1 04000000 s2a.bit", c)

    def test_s2_1_sends_the_design_when_the_card_does_not_have_it(self) -> None:
        rec, u, out = run("s2_1")
        self.assertEqual((rec["verdict"], rec["pl_source"]), ("PASS", "ymodem"))
        self.assertEqual(u.blobs[0x04000000], (ROOT / "build" / "pl" / "s2a.bit").read_bytes())

    def not_started(self, rec: dict, u: Board, out: Path, why: str) -> None:
        self.assertEqual(rec["verdict"], "FAIL")
        self.assertIn(why, rec["stop"])
        self.assertNotIn("went", rec)
        self.assertFalse([c for c in u.commands if c.startswith("go ")], "the prober was not started")
        self.assertTrue((out / "run.json").is_file())

    def test_s2_1_a_design_that_answers_with_another_word_is_not_given_the_prober(self) -> None:
        rec, u, out = run("s2_1", card_has_s2a=True, pl_id=0x00000000)
        self.not_started(rec, u, out, "'md.l 40000000 1': reads 53324131 (read 00000000)")

    def test_s2_1_a_design_that_does_not_answer_stops_the_run_there(self) -> None:
        rec, u, out = run("s2_1", card_has_s2a=True, pl_does_not_answer=True)
        self.not_started(rec, u, out, "no prompt after 'md.l 40000000 1'")
        self.assertEqual(u.commands[-1], "md.l 40000000 1", "nothing is sent after it")

    def test_s2_1_an_slcr_word_that_is_not_the_board_s_stops_before_the_pl_is_touched(self) -> None:
        for addr, cmd in ((0xF8000900, "md.l f8000900 1"), (0xF8000170, "md.l f8000170 1")):
            with self.subTest(cmd):
                rec, u, out = run("s2_1", card_has_s2a=True, slcr={addr: 0x00200A00})
                self.not_started(rec, u, out, repr(cmd))
                self.assertNotIn("md.l 40000000 1", u.commands)

    def test_s2_1_user_logic_failing_under_the_prober_is_saved_whole_and_fails(self) -> None:
        for fault, status in (("ramstuck", "0xa05"), ("fclk", "0x112"), ("srlmoves", "0xa06")):
            with self.subTest(fault):
                rec, u, out = run("s2_1", fault, card_has_s2a=True)
                self.assertEqual((rec["verdict"], rec["judge"], rec["card_verified"], rec["return_code"]), ("FAIL", "FAIL", True, status))
                self.assertEqual((out / "result.bin").read_bytes(), u.twin_result)
                self.assertFalse([p for p in rec["problems"] if "console showed" in p or "return code" in p], "the console and the return code are what the result implies")

    def test_what_each_set_is_judged_against(self) -> None:
        self.assertIn("frames", s1a_run.known_for("s2_0"))
        self.assertEqual(s1a_run.known_for("s2_1")["name"], "s2a")
        self.assertEqual(s1a_run.known_for("s1b0b"), KNOWN)


class TheCommandLine(unittest.TestCase):
    def main(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["s1a_run.py", *argv]), contextlib.redirect_stdout(buf):
            rc = s1a_run.main()
        return rc, buf.getvalue()

    def test_the_plan_of_s2_1_shows_the_first_access_and_where_it_stands(self) -> None:
        rc, text = self.main("--stage", "s2_1", "--dry-run")
        self.assertEqual(rc, 0)
        lines = text.splitlines()
        first = next(i for i, ln in enumerate(lines) if "md.l 40000000 1" in ln)
        self.assertIn("THE FIRST ACCESS TO USER LOGIC", lines[first])
        self.assertLess(next(i for i, ln in enumerate(lines) if "fpga loadb" in ln), first)
        self.assertLess(first, next(i for i, ln in enumerate(lines) if " go 02000000" in ln))
        self.assertIn("s2a.bit", text)
        self.assertIn("Dry run: nothing was sent.", text)

    def test_the_plan_of_s2_0_is_the_plan_of_every_run_with_the_carrier(self) -> None:
        rc, text = self.main("--stage", "s2_0", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("carrier.bit", text)
        self.assertNotIn("40000000", text)

    def test_a_staged_design_that_is_not_the_set_s_is_refused(self) -> None:
        exp = json.loads(s1a_run.STAGES["s2_1"]["expected"].read_text())
        tmp = Path(scratch_dirs.mkdtemp(prefix="smexp_"))
        for name, change in (("another hash", {"sha256": "0" * 64}), ("another size", {"bytes": exp["pl_design"]["bytes"] + 1}),
                             ("a file that is not there", {"file": "build/pl/no_such.bit"})):
            with self.subTest(name):
                (tmp / "e.json").write_text(json.dumps(dict(exp, pl_design=dict(exp["pl_design"], **change))))
                with mock.patch.dict(s1a_run.STAGES["s2_1"], {"expected": tmp / "e.json"}):
                    rc, text = self.main("--stage", "s2_1", "--dry-run")
                self.assertEqual(rc, 2)
                self.assertIn("REFUSED", text)


if __name__ == "__main__":
    unittest.main()

"""Stage 2 (S1b.0) on the host twin: several frames in one read, and the FAR register read back.
The model's FAR register follows one of two rules; the board has not said which, so both are run."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import packets  # noqa: E402

TWIN = ROOT / "build" / "prober" / "twin"
KNOWN = json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())["frames"]
FRAMES = {int(k, 16): [int(w, 16) for w in v["words"]] for k, v in KNOWN.items()}

CTRL, INT_STS, STATUS, SRC, DST, SLEN, DLEN, MCTRL = (0xF8007000, 0xF800700C, 0xF8007014, 0xF8007018, 0xF800701C,
                                                      0xF8007020, 0xF8007024, 0xF8007080)
CMD_BUF, DST_BUF, PCAP = 0x10200000, 0x10300000, 0xFFFFFFFF
HDR, REC, FARBLK, DATA = 64, 480, 68, 76
LO, HI, REF = 0xB98, 0xB9A, 0xB99
OPS = [(0xB98, 1), (0xB99, 1), (0xB98, 3)]
DEFAULT = {"magic": 0x31504D53, "version": 1, "stage": 2, "lo": LO, "hi": HI, "ref": REF, "ops": OPS,
           "repeats": 3, "budget": 4, "poll_limit": 1000}


def params(**over) -> list[int]:
    p = {**DEFAULT, **over}
    w = [0] * 32
    w[0:10] = [p["magic"], p["version"], p["stage"], p["lo"], p["hi"], p["ref"], p.get("n_ops", len(p["ops"])),
               p["repeats"], p["budget"], p["poll_limit"]]
    for k, (far, n) in enumerate(p["ops"]):
        w[16 + k] = far
        w[10 + k // 8] |= n << (4 * (k % 8))
    w[14], w[15] = p.get("seq", 0), p.get("extra", 0)       # stage 5: a generated sequence; more stack beneath each target read
    return w


class Run:
    def __init__(self, fault: str = "", rule: str = "next", **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(tempfile.mkdtemp(prefix="smtwin2_"))
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in FRAMES.items()) + "\n")
        self.params = params(**over)
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in self.params) + "\n")
        env = dict(os.environ); env.pop("SM_FAULT", None); env["SM_FAR_RULE"] = rule
        if fault:
            env["SM_FAULT"] = fault
        out = subprocess.run([str(TWIN), "run", str(tmp / "frames.txt"), str(tmp / "params.txt"), str(tmp / "result.bin")],
                             check=True, capture_output=True, text=True, env=env).stdout
        self.lines = [line.split() for line in out.splitlines()]
        raw = (tmp / "result.bin").read_bytes()
        self.words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        self.rc = int([e for e in self.lines if e[0] == "RC"][0][1], 16)
        self.uart = bytes(int(x, 16) for x in [e for e in self.lines if e[0] == "UART"][0][1:]).decode()
        self.violations = [" ".join(e) for e in self.lines if e[0] == "VIOLATION"]
        self.accesses = [(e[0], int(e[1], 16), int(e[2], 16)) for e in self.lines if e[0] in ("R", "W")]
        self.dmas = [(int(e[2][4:], 16), int(e[3][4:], 16), int(e[4][5:]), int(e[5][5:])) for e in self.lines if e[0] == "DMA"]
        self.streams = [[int(x, 16) for x in e[1:]] for e in self.lines if e[0] == "STREAM"]
        h = self.words
        self.status, self.n_records, self.n_anomalies, self.total, self.stop_record = h[2], h[3], h[4], h[5], h[18]

    def record(self, i: int) -> dict:
        r = self.words[HDR + i * REC: HDR + (i + 1) * REC]
        n = r[14]
        return {"far": r[0], "kind": r[1], "code": r[2], "sts": (r[3], r[5], r[7]), "polls": (r[4], r[6], r[8]), "survivors": r[9],
                "ref_equal": r[10], "repeat": r[12], "guard": r[13], "n": n, "op": r[15],
                "stream": r[16:59], "farrd": r[59:63], "cleanup": r[63:68],
                "far_sts": (r[FARBLK], r[FARBLK + 2]), "far_polls": (r[FARBLK + 1], r[FARBLK + 3]), "far_value": r[FARBLK + 4],
                "far_unread": r[FARBLK + 5], "pad": r[DATA:DATA + 101], "frames": [r[DATA + 101 * (j + 1):DATA + 101 * (j + 2)] for j in range(n)],
                "tail": r[DATA + 101 * (n + 1):]}


class Normal(unittest.TestCase):
    def test_it_completes_under_either_rule_and_reports_what_the_register_said(self) -> None:
        for rule, extra in (("next", 0), ("skip", 1)):
            with self.subTest(rule):
                r = Run(rule=rule)
                self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
                self.assertEqual(r.n_records, 1 + 3 * 3 + 1)
                self.assertEqual((r.total, len(r.words)), (HDR + 11 * REC, HDR + 11 * REC))
                self.assertEqual(r.uart, "SM2 start\r\nSM2 end status=00000001 records=0000000b anomalies=00000000 words=%08x\r\n" % r.total)
                for i in range(r.n_records):
                    rec = r.record(i)
                    self.assertEqual(rec["far_value"], rec["far"] + rec["n"] + extra, f"record {i}")
                    self.assertEqual((rec["code"], rec["survivors"], rec["guard"], rec["far_unread"]), (0, 0, 0, 0))

    def test_the_schedule_and_the_data(self) -> None:
        r = Run()
        self.assertEqual([r.record(i)["kind"] for i in range(11)], [2] + [0] * 9 + [3])
        self.assertEqual([(r.record(i)["far"], r.record(i)["n"]) for i in range(11)], [(REF, 1)] + OPS * 3 + [(REF, 1)])
        self.assertEqual([r.record(i)["op"] for i in range(11)], [0xFFFFFFFF] + [0, 1, 2] * 3 + [0xFFFFFFFF])
        for i in range(11):
            rec = r.record(i)
            self.assertEqual(rec["pad"], [0] * 101)
            for j, frame in enumerate(rec["frames"]):
                self.assertEqual(frame, FRAMES[rec["far"] + j], f"record {i}, frame {j}")
            self.assertFalse(any(rec["tail"]), "words after the data of a shorter read must stay zero")
        self.assertEqual(r.record(10)["ref_equal"], 1)

    def test_the_only_registers_touched_and_the_clear_never_touches_pcfg_done(self) -> None:
        r = Run()
        self.assertEqual({a for k, a, _ in r.accesses if k == "W"}, {INT_STS, SRC, DST, SLEN, DLEN})
        self.assertEqual({a for k, a, _ in r.accesses if k == "R"}, {CTRL, MCTRL, INT_STS, STATUS})
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})

    def test_five_commands_per_operation_each_cleared_verified_ordered_and_waited_for(self) -> None:
        r = Run()
        self.assertEqual(len(r.dmas), 5 * r.n_records)
        for i in range(r.n_records):
            n = r.record(i)["n"]
            self.assertEqual(r.dmas[5 * i:5 * i + 5], [(CMD_BUF | 1, PCAP, 43, 0), (PCAP, DST_BUF | 1, 0, 101 * (n + 1)),
                                                      (CMD_BUF | 1, PCAP, 4, 0), (PCAP, DST_BUF | 1, 0, 1), (CMD_BUF | 1, PCAP, 5, 0)])
            self.assertEqual(r.record(i)["polls"] + r.record(i)["far_polls"], (2, 2, 2, 2, 2))
        seq = [(k, a) for k, a, _ in r.accesses]
        starts = [i for i, e in enumerate(seq) if e == ("W", INT_STS)]
        self.assertEqual(len(starts), len(r.dmas))
        for i in starts:
            self.assertEqual(seq[i:i + 7], [("W", INT_STS), ("R", INT_STS), ("W", SRC), ("W", DST), ("W", SLEN), ("W", DLEN), ("R", INT_STS)])

    def test_everything_sent_is_read_only_inside_the_envelope_and_is_what_the_record_says(self) -> None:
        r = Run()
        self.assertEqual(len(r.streams), 3 * r.n_records)
        for i in range(r.n_records):
            rec = r.record(i)
            self.assertEqual(r.streams[3 * i:3 * i + 3], [rec["stream"], rec["farrd"], rec["cleanup"]])
            for s in (rec["stream"], rec["farrd"], rec["cleanup"]):
                self.assertEqual(packets.readonly_problems(s, LO, HI, 404), [])
            self.assertEqual((rec["stream"][8], rec["stream"][10]), (rec["far"], 0x48000000 | 101 * (rec["n"] + 1)))

    def test_stage_one_parameters_still_run_stage_one(self) -> None:
        sys.path.insert(0, str(ROOT / "tests"))
        from test_prober_twin import Run as Run1
        self.assertTrue(Run1().uart.startswith("SM1 start"))


class GatesAndParameters(unittest.TestCase):
    def test_a_failed_gate_sends_nothing(self) -> None:
        for fault, status in (("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.rc, r.status, r.n_records, r.dmas, [e for e in r.accesses if e[0] == "W"]), (status, status, 0, [], []))

    def test_bad_parameters_touch_no_register(self) -> None:
        for name, over in (("version", {"version": 2}), ("lo above hi", {"lo": 0xB9B}), ("an operation outside", {"ops": [(0xB97, 1)]}),
                           ("an operation running past the envelope", {"ops": [(0xB9A, 2)]}), ("three frames from the middle", {"ops": [(0xB99, 3)]}),
                           ("an operation whose end wraps past the top of the address space", {"lo": 0xFFFFFFFE, "hi": 0xFFFFFFFF, "ref": 0xFFFFFFFF, "ops": [(0xFFFFFFFF, 3)]}),
                           ("zero frames", {"ops": [(0xB98, 0)]}), ("four frames", {"ops": [(0xB98, 4)], "hi": 0xBA0}),
                           ("no operations", {"ops": [], "n_ops": 0}), ("too many", {"n_ops": 17}), ("no repeats", {"repeats": 0}),
                           ("the reference outside", {"ref": 0xB9B}), ("no poll limit", {"poll_limit": 0})):
            with self.subTest(name):
                r = Run(**over)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(r.uart, "SM2 start\r\nSM2 end status=00000500\r\n")


class Interface(unittest.TestCase):
    def test_any_interface_failure_stops_at_that_command(self) -> None:
        """Commands 6..10 are the five of the first target operation."""
        for fault, code, count in (("err@6", 0x21, 6), ("err@7", 0x21, 7), ("err@8", 0x21, 8), ("err@9", 0x21, 9), ("err@10", 0x21, 10),
                                   ("timeout@8", 0x22, 8), ("timeout@9", 0x22, 9), ("drop@7", 0x23, 7), ("drop@9", 0x23, 9),
                                   ("dropafter@8", 0x23, 8)):
            with self.subTest(fault):
                r = Run(fault, poll_limit=30)
                self.assertEqual((r.status, r.n_records, r.stop_record, len(r.dmas)), (0x200 | code, 2, 1, count))
                self.assertEqual(r.record(1)["code"], code)

    def test_a_failure_in_the_baseline_is_reported_as_such(self) -> None:
        for fault in ("stale", "err@1", "err@4", "timeout@3"):
            with self.subTest(fault):
                r = Run(fault, poll_limit=30)
                self.assertEqual((r.status >> 8, r.n_records), (6, 1))


class Data(unittest.TestCase):
    def test_data_anomalies_are_recorded_and_skipped_while_the_reference_holds(self) -> None:
        for fault, at, code in (("short@2", 1, 0x10), ("padnz@3", 2, 0x11), ("flip@5", 4, 0x12), ("farflip@5", 4, 0x13), ("farshort@3", 2, 0x14)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.status, r.rc, r.n_anomalies, r.n_records), (1, 0, 1, 12))
                self.assertEqual(r.record(at)["code"], code)
                health = r.record(at + 1)
                self.assertEqual((health["kind"], health["far"], health["n"], health["code"], health["ref_equal"]), (1, REF, 1, 0, 1))

    def test_a_difference_in_a_later_frame_of_a_multi_frame_repeat_is_noticed(self) -> None:
        r = Run("flip3@7")                                   # the three-frame read of the second repeat: its third frame differs
        rec = r.record(6)
        self.assertEqual((rec["far"], rec["n"], rec["repeat"], rec["code"]), (0xB98, 3, 1, 0x12))
        self.assertEqual((r.status, r.n_anomalies), (1, 1))

    def test_a_far_value_that_differs_on_the_reference_read_is_a_health_failure(self) -> None:
        r = Run("short@2,farflip@3")                         # the health read's frame is fine, its FAR value is not
        self.assertEqual((r.status, r.n_records, r.record(2)["ref_equal"]), (0x300, 3, 0))
        r = Run("farflip@11")                                # the final reference read
        self.assertEqual((r.status, r.record(10)["ref_equal"]), (0x300, 0))

    def test_a_changed_reference_frame_or_an_exhausted_budget_stops_the_run(self) -> None:
        r = Run("short@2,flip@3")
        self.assertEqual((r.status, r.n_records, r.stop_record), (0x300, 3, 2))
        r = Run("short@2", budget=0)
        self.assertEqual((r.status, r.n_anomalies, r.n_records), (0x400, 1, 3))

    def test_no_fault_makes_the_model_see_a_forbidden_operation(self) -> None:
        for fault in ("stale", "err@7", "timeout@9", "drop@6", "short@2", "padnz@3", "flip@5", "farflip@5", "farshort@3", "short@2,flip@3"):
            with self.subTest(fault):
                self.assertEqual(Run(fault, poll_limit=30).violations, [])


if __name__ == "__main__":
    unittest.main()

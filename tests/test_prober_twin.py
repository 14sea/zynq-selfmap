"""Stage S1a on the host twin: what the prober does to the device, word by word, and what it does when
the device misbehaves. The device here is a model (prober/twin_hal.c); these tests are about the prober."""
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
HDR, REC, STREAM_AT, DATA_AT = 64, 266, 16, 16 + 43 + 5
LO, HI, REF = 0xB98, 0xB9A, 0xB99
DEFAULT = {"magic": 0x31504D53, "version": 1, "stage": 1, "lo": LO, "hi": HI, "ref": REF, "fars": [0xB98, 0xB99, 0xB9A],
           "repeats": 3, "budget": 4, "poll_limit": 1000}


def params(**over) -> list[int]:
    p = {**DEFAULT, **over}
    w = [0] * 32
    w[0:10] = [p["magic"], p["version"], p["stage"], p["lo"], p["hi"], p["ref"], p.get("n_fars", len(p["fars"])),
               p["repeats"], p["budget"], p["poll_limit"]]
    w[16:16 + len(p["fars"])] = p["fars"]
    return w


class Run:
    def __init__(self, fault: str = "", **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(tempfile.mkdtemp(prefix="smtwin_"))
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in FRAMES.items()) + "\n")
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in params(**over)) + "\n")
        env = dict(os.environ); env.pop("SM_FAULT", None)
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
        self.dmas = [tuple(int(x.split("=")[1], 16 if x[0] in "sd" and "len" not in x else 10) for x in e[2:]) for e in self.lines if e[0] == "DMA"]
        self.streams = [[int(x, 16) for x in e[1:]] for e in self.lines if e[0] == "STREAM"]
        h = self.words
        self.status, self.n_records, self.n_anomalies, self.total, self.stop_record = h[2], h[3], h[4], h[5], h[18]

    def record(self, i: int) -> dict:
        r = self.words[HDR + i * REC: HDR + (i + 1) * REC]
        return {"far": r[0], "kind": r[1], "code": r[2], "sts": (r[3], r[5], r[7]), "polls": (r[4], r[6], r[8]), "survivors": r[9],
                "ref_equal": r[10], "repeat": r[12], "guard": r[13], "stream": r[STREAM_AT:STREAM_AT + 43],
                "cleanup": r[STREAM_AT + 43:DATA_AT], "pad": r[DATA_AT:DATA_AT + 101], "frame": r[DATA_AT + 101:DATA_AT + 202]}


class Normal(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_ = Run()

    def test_it_completes_with_nothing_unusual(self) -> None:
        r = self.run_
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations), (0, 1, 0, []))
        self.assertEqual(r.n_records, 1 + 3 * 3 + 1)
        self.assertEqual(r.total, HDR + r.n_records * REC)
        self.assertEqual(len(r.words), r.total)
        self.assertEqual(r.uart, "SM1 start\r\nSM1 end status=00000001 records=0000000b anomalies=00000000 words=%08x\r\n" % r.total)

    def test_every_record_holds_the_known_frame_behind_a_zero_pad(self) -> None:
        r = self.run_
        kinds = [r.record(i)["kind"] for i in range(r.n_records)]
        self.assertEqual(kinds, [2] + [0] * 9 + [3])
        self.assertEqual([r.record(i)["far"] for i in range(r.n_records)], [REF] + [0xB98, 0xB99, 0xB9A] * 3 + [REF])
        for i in range(r.n_records):
            rec = r.record(i)
            self.assertEqual((rec["code"], rec["survivors"], rec["guard"]), (0, 0, 0))
            self.assertEqual(rec["pad"], [0] * 101)
            self.assertEqual(rec["frame"], FRAMES[rec["far"]])
        self.assertEqual(r.record(r.n_records - 1)["ref_equal"], 1)

    def test_the_only_registers_touched(self) -> None:
        r = self.run_
        self.assertEqual({a for k, a, _ in r.accesses if k == "W"}, {INT_STS, SRC, DST, SLEN, DLEN})
        self.assertEqual({a for k, a, _ in r.accesses if k == "R"}, {CTRL, MCTRL, INT_STS, STATUS})
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})
        self.assertFalse([v for k, a, v in r.accesses if k == "W" and a == INT_STS and v & 0x4], "PCFG_DONE was written")

    def test_every_dma_command_is_clear_verify_program_in_order_wait(self) -> None:
        r = self.run_
        seq = [(k, a) for k, a, _ in r.accesses]
        starts = [i for i, e in enumerate(seq) if e == ("W", INT_STS)]
        self.assertEqual(len(starts), len(r.dmas))
        for i in starts:
            self.assertEqual(seq[i:i + 6], [("W", INT_STS), ("R", INT_STS), ("W", SRC), ("W", DST), ("W", SLEN), ("W", DLEN)])
            self.assertEqual(seq[i + 6], ("R", INT_STS), "no wait on the status after queuing")
        self.assertEqual(len([e for e in seq if e == ("W", DLEN)]), len(starts), "a command was queued without the clear before it")

    def test_three_commands_per_read_in_the_pinned_shapes(self) -> None:
        r = self.run_
        self.assertEqual(len(r.dmas), 3 * r.n_records)
        for i in range(r.n_records):
            self.assertEqual(r.dmas[3 * i:3 * i + 3], [(CMD_BUF | 1, PCAP, 43, 0), (PCAP, DST_BUF | 1, 0, 202), (CMD_BUF | 1, PCAP, 5, 0)])
            self.assertEqual(r.record(i)["polls"], (2, 2, 2), "the model shows DMA_DONE one read before D_P_DONE; a wait on DMA_DONE would stop at 1")
            self.assertEqual([x & 0x3000 for x in r.record(i)["sts"]], [0x3000] * 3)

    def test_everything_sent_is_read_only_inside_the_envelope_and_is_what_the_record_says(self) -> None:
        r = self.run_
        self.assertEqual(len(r.streams), 2 * r.n_records)
        for i in range(r.n_records):
            rec = r.record(i)
            self.assertEqual(r.streams[2 * i], rec["stream"])
            self.assertEqual(r.streams[2 * i + 1], rec["cleanup"])
            for s in (rec["stream"], rec["cleanup"]):
                self.assertEqual(packets.readonly_problems(s, LO, HI, 202), [])
            self.assertEqual(rec["stream"][8], rec["far"])


class Gates(unittest.TestCase):
    def test_a_failed_gate_sends_nothing_and_writes_no_register(self) -> None:
        for fault, status in (("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.rc, r.status, r.n_records), (status, status, 0))
                self.assertEqual((r.dmas, r.streams, [e for e in r.accesses if e[0] == "W"], r.violations), ([], [], [], []))

    def test_bad_parameters_touch_no_register_at_all(self) -> None:
        for name, over in (("magic", {"magic": 0}), ("version", {"version": 2}), ("stage", {"stage": 2}), ("lo above hi", {"lo": 0xB9B}),
                           ("a far outside", {"fars": [0xB98, 0xB9B]}), ("the reference outside", {"ref": 0xB97}),
                           ("no fars", {"fars": [], "n_fars": 0}), ("too many fars", {"n_fars": 17}), ("no repeats", {"repeats": 0}),
                           ("too many repeats", {"repeats": 9}), ("no poll limit", {"poll_limit": 0})):
            with self.subTest(name):
                r = Run(**over)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))


class Interface(unittest.TestCase):
    """Anything wrong with the configuration interface itself stops the run where it is."""

    def test_a_stale_status_bit_stops_before_anything_is_queued(self) -> None:
        r = Run("stale")
        self.assertEqual((r.status, r.n_records, r.dmas), (0x600 | 0x20, 1, []))

    def test_an_error_bit_stops_the_run_and_nothing_follows(self) -> None:
        r = Run("err@5")                                   # the read command of the first target read
        self.assertEqual((r.status, r.rc, r.n_records, r.stop_record, r.n_anomalies), (0x200 | 0x21, 0x221, 2, 1, 1))
        self.assertEqual(len(r.dmas), 5)
        self.assertEqual(r.record(1)["code"], 0x21)

    def test_a_command_that_never_completes_times_out_at_the_poll_limit(self) -> None:
        r = Run("timeout@4", poll_limit=37)
        self.assertEqual((r.status, r.n_records, len(r.dmas)), (0x200 | 0x22, 2, 4))
        self.assertEqual(r.record(1)["polls"][0], 37)

    def test_pcfg_done_dropping_stops_the_run(self) -> None:
        r = Run("drop@6")
        self.assertEqual((r.status, r.n_records, len(r.dmas)), (0x200 | 0x23, 2, 6))

    def test_a_failure_on_the_very_first_read_is_reported_as_the_baseline(self) -> None:
        r = Run("err@1")
        self.assertEqual((r.status, r.n_records), (0x600 | 0x21, 1))


class Data(unittest.TestCase):
    """A data anomaly is recorded and skipped while the reference frame still reads the same."""

    def test_a_short_read_is_recorded_and_the_run_goes_on(self) -> None:
        r = Run("short@2")                                 # the first target read delivers 150 of 202 words
        self.assertEqual((r.status, r.rc, r.n_anomalies, r.n_records), (1, 0, 1, 12))
        bad, health = r.record(1), r.record(2)
        self.assertEqual((bad["code"], bad["survivors"], bad["kind"]), (0x10, 52, 0))
        self.assertEqual((health["kind"], health["far"], health["code"], health["ref_equal"]), (1, REF, 0, 1))

    def test_a_nonzero_pad_is_recorded_and_the_run_goes_on(self) -> None:
        r = Run("padnz@3")
        self.assertEqual((r.status, r.n_anomalies, r.record(2)["code"]), (1, 1, 0x11))

    def test_a_repeat_that_differs_is_recorded_and_the_run_goes_on(self) -> None:
        r = Run("flip@5")                                  # the second reading of 0xb98
        self.assertEqual((r.status, r.n_anomalies), (1, 1))
        rec = r.record(4)
        self.assertEqual((rec["far"], rec["repeat"], rec["code"]), (0xB98, 1, 0x12))

    def test_if_the_reference_frame_changed_the_run_stops(self) -> None:
        r = Run("short@2,flip@3")                          # the health read after the anomaly comes back different
        self.assertEqual((r.status, r.n_records, r.stop_record), (0x300, 3, 2))
        self.assertEqual(r.record(2)["ref_equal"], 0)
        self.assertEqual(len(r.dmas), 9)

    def test_the_anomaly_budget_stops_the_run(self) -> None:
        r = Run("short@2", budget=0)
        self.assertEqual((r.status, r.n_anomalies, r.n_records), (0x400, 1, 3))

    def test_the_final_reference_read_must_match(self) -> None:
        r = Run("flip@11")                                 # the last read of the run
        self.assertEqual((r.status, r.record(r.n_records - 1)["ref_equal"]), (0x300, 0))

    def test_no_fault_makes_the_model_see_a_forbidden_operation(self) -> None:
        for fault in ("stale", "err@5", "timeout@4", "drop@6", "short@2", "padnz@3", "flip@5", "short@2,flip@3"):
            with self.subTest(fault):
                self.assertEqual(Run(fault).violations, [])


if __name__ == "__main__":
    unittest.main()

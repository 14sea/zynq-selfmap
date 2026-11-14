"""Stage 4 (S1b.1) on the host twin: the walk of one column by the addresses the device names.
The model is given a column — which address follows which — by the test; the prober is not told.
Several shapes are run, because what the device does at the end of a column is not known."""
from __future__ import annotations

import json
import os
import random
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
KNOWN = {int(k, 16): [int(w, 16) for w in v["words"]] for k, v in json.loads((ROOT / "data" / "known_frames_17A6.json").read_text())["frames"].items()}
CTRL, INT_STS, STATUS, SRC, DST, SLEN, DLEN, MCTRL = (0xF8007000, 0xF800700C, 0xF8007014, 0xF8007018, 0xF800701C,
                                                      0xF8007020, 0xF8007024, 0xF8007080)
CMD_BUF, DST_BUF, PCAP = 0x10200000, 0x10300000, 0xFFFFFFFF
HDR, REC, FARBLK, DATA, H_WALK = 64, 480, 68, 76, 19
LO, HI, REF, START = 0xB80, 0xBFF, 0xB99, 0xB80
SUCC, CONTENT, TRIPLE, NO_OP = 0, 1, 2, 0xFFFFFFFF
END_LEFT, END_LIMIT = 1, 2
DEFAULT = {"magic": 0x31504D53, "version": 1, "stage": 4, "lo": LO, "hi": HI, "ref": REF, "n_fars": 1, "passes": 2, "budget": 0,
           "poll_limit": 1000, "limit": 64, "every": 16, "start": START}


def column(n: int = 36, first: int = START, after: int = 0xC00) -> dict[int, int]:
    """A column of n frames from `first`: where the last one's successor is not simply the next number."""
    return {first + n - 1: after}


def frames_for(addresses) -> dict[int, list[int]]:
    """The known frames where they are known, and for every other address a frame of its own."""
    out = {}
    for far in addresses:
        rng = random.Random(far)
        out[far] = KNOWN.get(far) or [rng.getrandbits(32) for _ in range(101)]
    return out


def params(**over) -> list[int]:
    p = {**DEFAULT, **over}
    w = [0] * 32
    w[0:10] = [p["magic"], p["version"], p["stage"], p["lo"], p["hi"], p["ref"], p["n_fars"], p["passes"], p["budget"], p["poll_limit"]]
    w[12], w[13], w[16] = p["limit"], p["every"], p["start"]
    return w


class Run:
    def __init__(self, fault: str = "", rule: str = "skip", succ: dict[int, int] | None = None, frames: dict[int, list[int]] | None = None, **over) -> None:
        subprocess.run(["make", "-s", "-C", str(ROOT / "prober"), "twin"], check=True)
        tmp = Path(tempfile.mkdtemp(prefix="smtwin4_"))
        self.succ = column() if succ is None else succ
        self.frames = frames_for(range(0xB80, 0xBA4)) if frames is None else frames
        (tmp / "frames.txt").write_text("\n".join(" ".join(f"{x:x}" for x in [far] + words) for far, words in self.frames.items()) + "\n")
        self.params = params(**over)
        (tmp / "params.txt").write_text("\n".join(f"{x:x}" for x in self.params) + "\n")
        env = dict(os.environ); env.pop("SM_FAULT", None); env["SM_FAR_RULE"] = rule
        env["SM_SUCC"] = ",".join(f"{a:x}:{b:x}" for a, b in self.succ.items())
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
        self.walk = [tuple(h[H_WALK + 3 * p:H_WALK + 3 * p + 3]) for p in range(2)]

    def rec(self, i: int) -> dict:
        r = self.words[HDR + i * REC: HDR + (i + 1) * REC]
        n = r[14]; nw = 101 * (n + 1)
        return {"far": r[0], "kind": r[1], "code": r[2], "survivors": r[9], "ref_equal": r[10], "repeat": r[12], "guard": r[13], "n": n, "op": r[15],
                "stream": r[16:59], "farrd": r[59:63], "cleanup": r[63:68], "far_value": r[FARBLK + 4],
                "pad": r[DATA:DATA + 101], "frames": [r[DATA + 101 * (j + 1):DATA + 101 * (j + 2)] for j in range(n)], "tail": r[DATA + nw:]}

    def recs(self) -> list[dict]:
        return [self.rec(i) for i in range(self.n_records)]


def schedule(addresses: list[int], passes: int = 2, every: int = 16, end_left: bool = True) -> list[tuple]:
    """(kind, far, frames, operation, pass) of every record of a clean run over these addresses."""
    out = [(2, REF, 1, NO_OP, 0)]
    for p in range(passes):
        for k, far in enumerate(addresses, 1):
            out += [(0, far, 0, SUCC, p), (0, far, 1, CONTENT, p)]
            if k % every == 0 and k < len(addresses):
                out.append((1, REF, 1, NO_OP, p))
    out += [(0, addresses[k], 3, TRIPLE, passes) for k in range(0, len(addresses) - 2, 3)]
    return out + [(3, REF, 1, NO_OP, passes)]


COLUMN = list(range(0xB80, 0xBA4))                           # the model's default column: 36 frames, then 0xc00


class Normal(unittest.TestCase):
    def test_it_walks_the_column_twice_and_stops_where_the_device_names_an_address_outside(self) -> None:
        r = Run()
        self.assertEqual((r.rc, r.status, r.n_anomalies, r.violations, r.stop_record), (0, 1, 0, [], 0xFFFFFFFF))
        self.assertEqual(r.walk, [(36, END_LEFT, 0xC00)] * 2)
        self.assertEqual([(x["kind"], x["far"], x["n"], x["op"], x["repeat"]) for x in r.recs()], schedule(COLUMN))
        self.assertEqual((r.n_records, r.total, len(r.words)), (162, HDR + 162 * REC, HDR + 162 * REC))
        self.assertEqual(r.uart, "SM4 start\r\nSM4 end status=00000001 records=000000a2 anomalies=00000000 words=%08x\r\n" % r.total)
        for x in r.recs():
            self.assertEqual((x["code"], x["survivors"], x["guard"], x["pad"]), (0, 0, 0, [0] * 101))
            self.assertFalse(any(x["tail"]))

    def test_every_address_read_at_was_named_by_the_device_and_nothing_outside_the_column_is_read(self) -> None:
        r = Run()
        named = {x["far_value"] for x in r.recs() if x["op"] == SUCC}
        written = {s[8] for s in r.streams if len(s) == 43}
        self.assertEqual(written - named, {START}, "the start is the only address the device did not name")
        self.assertEqual(max(written), 0xBA3)
        self.assertNotIn(0xC00, written, "the address named at the end is recorded, not read")
        for s in r.streams:
            self.assertEqual(packets.readonly_problems(s, LO, HI, 404), [])

    def test_the_frames_delivered_are_the_model_s_by_every_path(self) -> None:
        r = Run()
        for x in r.recs():
            for j, frame in enumerate(x["frames"]):
                self.assertEqual(frame, r.frames[x["far"] + j], f"{x['far']:#x} frame {j}")

    def test_the_only_registers_touched(self) -> None:
        r = Run()
        self.assertEqual({a for k, a, _ in r.accesses if k == "W"}, {INT_STS, SRC, DST, SLEN, DLEN})
        self.assertEqual({a for k, a, _ in r.accesses if k == "R"}, {CTRL, MCTRL, INT_STS, STATUS})
        self.assertEqual({v for k, a, v in r.accesses if k == "W" and a == INT_STS}, {0x00F4F840})
        self.assertEqual(len(r.dmas), 5 * r.n_records)


class Shapes(unittest.TestCase):
    """What the device does at a column end is not known. The prober has to follow whatever it is told."""

    def test_columns_of_other_lengths(self) -> None:
        for n in (1, 2, 3, 4, 17, 48):
            with self.subTest(n=n):
                r = Run(succ=column(n), frames=frames_for(range(0xB80, 0xB80 + n)), ref=0xB80, every=16)
                self.assertEqual((r.status, r.walk, r.violations), (1, [(n, END_LEFT, 0xC00)] * 2, []))
                self.assertEqual([(x["kind"], x["far"], x["n"], x["op"], x["repeat"]) for x in r.recs()],
                                 [(k, 0xB80 if k else f, m, o, p) for k, f, m, o, p in schedule(list(range(0xB80, 0xB80 + n)))])

    def test_a_column_end_that_names_an_address_inside_the_envelope_is_followed_there(self) -> None:
        addresses = [0xB80, 0xB81, 0xB82, 0xB83, 0xBF0, 0xBF1]
        r = Run(succ={0xB83: 0xBF0, 0xBF1: 0x1000}, frames=frames_for(addresses + [REF]))
        self.assertEqual((r.status, r.walk), (1, [(6, END_LEFT, 0x1000)] * 2))
        self.assertEqual([(x["far"], x["n"]) for x in r.recs() if x["op"] == TRIPLE], [(0xB80, 3), (0xB83, 3)])
        triple = [x for x in r.recs() if x["op"] == TRIPLE][1]
        self.assertEqual(triple["frames"], [r.frames[a] for a in (0xB83, 0xBF0, 0xBF1)], "the device goes on by its own successor, and that is what is compared")

    def test_a_column_that_does_not_end_inside_the_limit(self) -> None:
        r = Run(succ={}, frames=frames_for(range(0xB80, 0xC00)))
        self.assertEqual((r.status, r.walk, r.violations), (1, [(64, END_LIMIT, 0xBC0)] * 2, []))
        self.assertEqual(max(s[8] for s in r.streams if len(s) == 43), 0xBBF)
        r = Run(limit=5)
        self.assertEqual((r.status, r.walk, r.n_records), (1, [(5, END_LIMIT, 0xB85)] * 2, 1 + 2 * 10 + 1 + 1))

    def test_an_address_that_is_not_above_the_one_asked_about_stops_the_run(self) -> None:
        for what, succ in (("names itself", {0xB85: 0xB85}), ("a step back", {0xB85: 0xB82}), ("the start again", {0xB85: 0xB80})):
            with self.subTest(what):
                r = Run(succ=succ)
                self.assertEqual((r.status, r.rc, r.n_records, r.stop_record, r.violations), (0x800, 0x800, 13, 11, []))
                self.assertEqual(r.walk[0][0], 6)
        for rule in ("next", "skipdata"):                    # a register that does not move after the pad alone: stuck at the first frame
            with self.subTest(rule):
                r = Run(rule=rule)
                self.assertEqual((r.status, r.n_records, r.stop_record), (0x800, 3, 1))

    def test_one_pass(self) -> None:
        r = Run(passes=1)
        self.assertEqual((r.status, r.walk, r.n_records), (1, [(36, END_LEFT, 0xC00), (0, 0, 0)], 1 + 74 + 12 + 1))


class GatesAndParameters(unittest.TestCase):
    def test_a_failed_gate_sends_nothing(self) -> None:
        for fault, status in (("ctrl", 0x101), ("lpbk", 0x102), ("nodone", 0x103), ("dcache", 0x104)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.rc, r.status, r.n_records, r.dmas, [e for e in r.accesses if e[0] == "W"]), (status, status, 0, [], []))

    def test_bad_parameters_touch_no_register(self) -> None:
        for name, over in (("version", {"version": 2}), ("lo above hi", {"lo": 0xC00}), ("the start below", {"start": 0xB7F}), ("the start above", {"start": 0xC00}),
                           ("the reference outside", {"ref": 0xC00}), ("two starting addresses", {"n_fars": 2}), ("no start counted", {"n_fars": 0}),
                           ("no pass", {"passes": 0}), ("three passes", {"passes": 3}), ("no limit", {"limit": 0}), ("a limit above 64", {"limit": 65}),
                           ("never a reference read", {"every": 0}), ("an anomaly budget", {"budget": 1}), ("no poll limit", {"poll_limit": 0})):
            with self.subTest(name):
                r = Run(**over)
                self.assertEqual((r.status, r.n_records, r.accesses, r.dmas), (0x500, 0, [], []))
                self.assertEqual(r.uart, "SM4 start\r\nSM4 end status=00000500\r\n")

    def test_the_other_stages_still_run_from_this_image(self) -> None:
        sys.path.insert(0, str(ROOT / "tests"))
        from test_prober_twin import Run as Run1
        from test_prober_s1b0 import Run as Run2
        from test_prober_s1b0b import Run as Run3
        self.assertEqual([r.uart[:9] for r in (Run1(), Run2(), Run3())], ["SM1 start", "SM2 start", "SM3 start"])


class Stops(unittest.TestCase):
    """DMA commands: 1..5 the baseline, 6..10 the successor read at the start, 11..15 its content read, five per record.
    Frame reads and FAR reads: one of each per record, so record k (from 0) has number k + 1."""

    def test_any_anomaly_ends_the_walk_after_one_reference_read(self) -> None:
        for fault, at, code in (("padnz@2", 1, 0x11), ("short@3", 2, 0x10), ("farshort@2", 1, 0x14), ("farshort@7", 6, 0x14),
                                ("flip@77", 76, 0x12), ("farflip@77", 76, 0x13), ("farflip@76", 75, 0x13), ("flip3@150", 149, 0x12), ("flip@155", 154, 0x12)):
            with self.subTest(fault):
                r = Run(fault)
                self.assertEqual((r.status, r.rc, r.n_anomalies, r.n_records, r.stop_record), (0x700 | code, 0x700 | code, 1, at + 2, at))
                self.assertEqual(r.rec(at)["code"], code)
                health = r.rec(at + 1)
                self.assertEqual((health["kind"], health["far"], health["n"], health["code"], health["ref_equal"]), (1, REF, 1, 0, 1))
                self.assertEqual(r.violations, [])

    def test_an_interface_failure_stops_at_that_command(self) -> None:
        for fault, code, count, record in (("err@6", 0x21, 6, 1), ("err@9", 0x21, 9, 1), ("timeout@12", 0x22, 12, 2), ("drop@14", 0x23, 14, 2),
                                           ("err@381", 0x21, 381, 76), ("err@747", 0x21, 747, 149)):
            with self.subTest(fault):
                r = Run(fault, poll_limit=30)
                self.assertEqual((r.status, r.n_records, r.stop_record, len(r.dmas)), (0x200 | code, record + 1, record, count))

    def test_a_failure_in_the_baseline_is_reported_as_such(self) -> None:
        for fault in ("stale", "err@1", "err@4", "short@1", "farshort@1"):
            with self.subTest(fault):
                self.assertEqual((Run(fault, poll_limit=30).status >> 8, Run(fault, poll_limit=30).n_records), (6, 1))

    def test_a_changed_reference_frame_stops_the_run(self) -> None:
        r = Run("flip@34", every=16)                         # records 1..32 are the first sixteen frames; record 33 is the reference read
        self.assertEqual((r.rec(33)["kind"], r.status, r.n_records, r.stop_record, r.rec(33)["ref_equal"]), (1, 0x300, 34, 33, 0))
        r = Run("padnz@2,flip@3")                            # an anomaly, and then the reference read after it differs too
        self.assertEqual((r.status, r.n_records, r.stop_record), (0x300, 3, 2))
        r = Run("flip@162")                                  # the final reference read
        self.assertEqual((r.status, r.n_records, r.rec(161)["ref_equal"]), (0x300, 162, 0))
        r = Run("farflip@162")
        self.assertEqual((r.status, r.rec(161)["ref_equal"]), (0x300, 0))

    def test_the_reference_is_read_as_often_as_asked(self) -> None:
        for every, want in ((1, 35), (4, 8), (16, 2), (36, 0), (100, 0)):
            with self.subTest(every=every):
                r = Run(every=every, passes=1)
                self.assertEqual(sum(1 for x in r.recs() if x["kind"] == 1), want)
                self.assertEqual([(x["kind"], x["far"], x["n"], x["op"], x["repeat"]) for x in r.recs()], schedule(COLUMN, passes=1, every=every))


if __name__ == "__main__":
    unittest.main()

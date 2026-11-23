#!/usr/bin/env python3
"""S2.4, part 2 (docs/s2_plan.md, sections 37 to 42): the table, the holding of the singles, the description, the sets
in the run script and the chain of four runs — on the twin and on the pretend board, over a made-up device. No board
is touched.

The made-up device shows the shift registers' outputs as part 1 found the real ones to follow the uniform states, with
one answer, made up, to what part 1 could not say: output a as it is at the place of address 2 a + 1; output a
inverted at the place of address 2 a + 2, for a up to 30; and at address 0, inverted, output 0 once more. So 120
cells have one place as it is and one inverted, four have two inverted, four have none inverted. The tests give the
model other answers too."""
from __future__ import annotations

import hashlib, json, os, subprocess, sys, unittest, zlib
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_3_judge  # noqa: E402
import s2_4_chain2  # noqa: E402
import s2_4_judge  # noqa: E402
import s2_4_states as st  # noqa: E402
import s2_4_table  # noqa: E402
import test_prober_s2_3 as T  # noqa: E402
import test_s2_2_host as H8  # noqa: E402
import test_s2_3_host as H9  # noqa: E402
import test_s2_4_host as H4  # noqa: E402
from test_s2_4_host import CTL0, DESIGN, LOW, RAM_CELLS, place  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "srl_map_v1.schema.json").read_text())


def srl_map(zero: int | None = 0, inverted: bool = True) -> list[tuple[int, int, int, int, int, int]]:
    """Where outputs of the shift registers show: (output, register, frame address, word, bit, inverted). `zero`:
    which output the place of address 0 shows, inverted — or None, where it shows none — or "last": what was last
    shifted into the register, inverted, and a one as long as nothing has been shifted in (the twin's registers 4 to
    7), which is what the frames S2.2 stored and part 1 together suggest of the device."""
    out = [(a, k, *place(k, 2 * a + 1), 0) for k in range(4) for a in range(32)]
    if inverted:
        out += [(a, k, *place(k, 2 * a + 2), 1) for k in range(4) for a in range(31)]
    if zero == "last":
        out += [(0, k + 4, *place(k, 0), 1) for k in range(4)]
    elif zero is not None:
        out += [(zero, k, *place(k, 0), 1) for k in range(4)]
    return out


def as_part_1_saw(cells) -> list:
    """The same places as the made-up device's part 1 would have had them: a place of the twin's registers 4 to 7
    follows the uniform states as a place of output 0 does."""
    return [(a, k % 4, far, word, bit, inv) for a, k, far, word, bit, inv in cells]


def candidates_of(cells) -> dict:
    """What part 1 would have written of a device whose outputs show at these places."""
    return {"frames_with_candidates": {f"{far:#010x}": 0 for far in sorted({c[2] for c in cells})},
            "places": [{"far": f"{far:#010x}", "word": word, "bit": bit, "inverted": bool(inv), "run": "run01"} for _, _, far, word, bit, inv in cells]}


def known_for(cells=None, **more) -> dict:
    return dict(H4.KNOWN, candidates=candidates_of(srl_map() if cells is None else cells), ctl0_in_part_1=CTL0, **more)


KNOWN = known_for()


def where(cells) -> dict:
    """cell -> {place: inverted}"""
    out: dict = {}
    for a, k, far, word, bit, inv in cells:
        out.setdefault(32 * k + a, {})[(f"{far:#010x}", word, bit)] = bool(inv)
    return out


def twin(kind: str, share: int | None = None, cells=None, known: dict | None = None, **over):
    cells = srl_map() if cells is None else cells
    known = known_for(cells) if known is None else known
    p = st.plan(kind, share, known, known["census"], known["candidates"])
    r = T.Run(states=p["states"], reads=p["reads"], entries=p["entries"], shifts=True, w19=p["may_write"], srl_cells=cells, **over)
    return p, r, s2_4_judge.judge(r.words, known, s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))


_memo: dict = {}


def clean(kind: str, share: int | None = None):
    if (kind, share) not in _memo:
        _memo[(kind, share)] = twin(kind, share)
    return _memo[(kind, share)]


class TheTable(unittest.TestCase):
    def test_a_code_run_closed_into_the_table(self) -> None:
        p, r, v = clean("code")
        c = s2_4_table.close_code(v, KNOWN["candidates"])
        self.assertEqual((v["verdict"], c["problems"], c["bits_that_follow"], c["as_they_are"], c["inverted"], c["candidates_of_part_1"]), ("PASS", [], 256, 128, 128, 256))
        self.assertEqual(c["cells_by_their_places"], {"1 as it is, 0 inverted": 4, "1 as it is, 1 inverted": 120, "1 as it is, 2 inverted": 4})
        self.assertTrue(c["outcome"].startswith("10: every candidate of part 1 follows exactly one cell, as it is or inverted, and every cell has a bit as it is — "), c["outcome"])
        self.assertEqual({row["cell"]: {(x["far"], x["word"], x["bit"]): x["inverted"] for x in row["places"]} for row in c["table"]}, where(srl_map()))
        self.assertEqual([(row["cell"], row["register"], row["output"]) for row in c["table"]], [(n, n // 32, n % 32) for n in range(128)])
        self.assertTrue(all(not row["places"][0]["inverted"] for row in c["table"]), "the place as it is comes first")
        self.assertEqual((c["shapes"]["1 as it is, 2 inverted"], c["shapes"]["1 as it is, 0 inverted"]), ([0, 32, 64, 96], [31, 63, 95, 127]))

    def test_one_bit_a_cell_and_none_inverted_is_a_table_too(self) -> None:
        cells = srl_map(zero=None, inverted=False)
        p, r, v = twin("code", cells=cells)
        c = s2_4_table.close_code(v, candidates_of(cells))
        self.assertEqual((c["problems"], c["cells_by_their_places"], len(c["table"])), ([], {"1 as it is, 0 inverted": 128}, 128))

    def test_what_is_no_table(self) -> None:
        p, r, v = clean("code")
        self.assertEqual(s2_4_table.close_code(clean("singles", 0)[2], KNOWN["candidates"])["problems"], ["the verdict is not of the code run"])
        self.assertEqual(s2_4_table.close_code(dict(v, verdict="FAIL"), KNOWN["candidates"])["problems"], ["the code run is not a passing run"])
        # a cell shown inverted only
        cells = [c for c in srl_map() if not (c[0] == 7 and c[1] == 2 and not c[5])]
        c = s2_4_table.close_code(twin("code", cells=cells)[2], candidates_of(cells))
        self.assertEqual((c["table"], c["problems"], c["cells_without_a_bit_as_it_is"], c["outcome"][:3]), (None, ["1 cell(s) have no bit that follows them as it is"], [71], "11:"))
        # a candidate of part 1 that follows no cell here, and a place part 1 did not have
        more = candidates_of(srl_map())
        more["places"].append({"far": f"{LOW:#010x}", "word": 7, "bit": 3, "inverted": False, "run": "run01"})
        c = s2_4_table.close_code(v, more)
        self.assertEqual((c["table"], c["problems"], c["candidates_of_part_1_that_follow_no_cell"]), (None, ["1 candidate(s) of part 1 follow no cell"], [[f"{LOW:#010x}", 7, 3]]))
        fewer = candidates_of(srl_map()); gone = fewer["places"].pop(5)
        c = s2_4_table.close_code(v, fewer)
        self.assertEqual((c["table"], c["problems"], c["places_part_1_did_not_have"]), (None, ["1 bit(s) follow a cell at a place part 1 did not find"], [[gone["far"], gone["word"], gone["bit"]]]))
        # a place that follows its cell the other way than it followed the uniform states in part 1
        other = candidates_of(srl_map()); other["places"][9]["inverted"] = not other["places"][9]["inverted"]
        c = s2_4_table.close_code(v, other)
        self.assertEqual((c["table"], c["problems"]), (None, ["1 place(s) follow a cell the other way than they followed the uniform states in part 1"]))
        twice = json.loads(json.dumps(v)); twice["finding"]["follows"].append(dict(twice["finding"]["follows"][0], cell=5, register=0, output=5))
        self.assertIn("a place is said to follow two cells", s2_4_table.close_code(twice, KNOWN["candidates"])["problems"])

    def test_the_command_closes_a_stored_verdict(self) -> None:
        p, r, v = clean("code")
        d = Path(scratch_dirs.mkdtemp(prefix="smtable4_"))
        (d / "v.json").write_text(json.dumps(v)); (d / "c.json").write_text(json.dumps(KNOWN["candidates"]))
        out = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_table.py"), str(d / "v.json"), str(d / "c.json")], capture_output=True, text=True)
        self.assertEqual((out.returncode, json.loads(out.stdout)["cells_by_their_places"]["1 as it is, 1 inverted"]), (0, 120), out.stderr)
        self.assertNotIn("table", json.loads(out.stdout))
        (d / "c.json").write_text(json.dumps(dict(KNOWN["candidates"], places=KNOWN["candidates"]["places"][:-1])))
        self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_table.py"), str(d / "v.json"), str(d / "c.json")], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_table.py")], capture_output=True).returncode, 2)


class BeforeAnyShift(unittest.TestCase):
    """A place that follows a cell over every state made by shifts and reads otherwise before any shift than that
    cell's loaded content gives (section 42): set down, in the table all the same, and no failure. The made-up device
    here has, at address 0 of each register, what was last shifted in, inverted, and a one before any shift. The
    registers are loaded with words whose first bits are 1, 0, 1, 0: so before any shift the places of registers 0 and
    2 read otherwise than output 0 inverted would, and those of registers 1 and 3 do not."""
    CELLS = srl_map(zero="last")

    def known(self) -> dict:
        return known_for(as_part_1_saw(self.CELLS))

    def test_the_code_run_passes_and_the_table_has_the_place(self) -> None:
        p, r, v = twin("code", cells=self.CELLS, known=self.known())
        self.assertEqual((v["verdict"], v["problems"], v["finding"]["bits"]["irregular"]), ("PASS", [], 0))
        at = {k: (f"{place(k, 0)[0]:#010x}", place(k, 0)[1], place(k, 0)[2]) for k in range(4)}
        self.assertEqual([(x["far"], x["word"], x["bit"], x["cell"], x["inverted"], x["state"], x["reads"], x["the_cell_gives"]) for x in v["finding"]["otherwise_as_loaded"]],
                         sorted([(*at[0], 0, True, 0, 1, 0), (*at[2], 64, True, 0, 1, 0)]))
        c = s2_4_table.close_code(v, self.known()["candidates"])
        self.assertEqual((c["problems"], c["cells_by_their_places"]), ([], {"1 as it is, 0 inverted": 4, "1 as it is, 1 inverted": 120, "1 as it is, 2 inverted": 4}))
        self.assertEqual([(x["far"], x["word"], x["bit"], x["cell"], x["inverted"], x["state"], x["reads"], x["the_cell_gives"]) for x in c["places_that_read_otherwise_as_loaded"]],
                         sorted([(*at[0], 0, True, 0, 1, 0), (*at[2], 64, True, 0, 1, 0)]))
        self.assertEqual({(x["far"], x["word"], x["bit"]) for row in c["table"] if row["cell"] % 32 == 0 for x in row["places"] if x["inverted"]} >= set(at.values()), True)

    def test_the_description_rests_on_the_shifted_states_and_says_what_such_a_place_read_before(self) -> None:
        """Review of 07abf08: the description named the state before any shift as evidence for the two places that read
        otherwise in it — a record that reads one beside an entry that says a one in the output reads zero. An entry's
        evidence is of the states made by shifts; what the place read before any shift is said beside it."""
        pc, rc, vc = twin("code", cells=self.CELLS, known=self.known())
        closing = s2_4_table.close_code(vc, self.known()["candidates"])
        singles = []
        for run in (0, 1):
            p, r, v = twin("singles", run, cells=self.CELLS, known=self.known())
            singles.append({"dir": f"run{run + 1:02d}", "share": run, "result_sha256": f"{run + 1}" * 64, "reads": p["reads"], "states": p["states"],
                            "held": s2_4_table.hold_singles(v, closing["table"])})
        doc = s2_4_table.srl_map(DESIGN, closing["table"], {"dir": "run00", "result_sha256": "0" * 64, "reads": pc["reads"], "states": pc["states"]}, singles,
                                 closing["places_that_read_otherwise_as_loaded"])
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["counts"], doc["places_that_read_otherwise_before_any_shift"]), ({"confirmed": 256, "decoded": 0, "contradiction": 0}, 2))
        apart = [e for e in doc["entries"] if "before_any_shift" in e]
        self.assertEqual([(e["address"], e["cell"], e["inverted"], e["before_any_shift"]["state"], e["before_any_shift"]["reads"], e["before_any_shift"]["the_output_as_loaded_would_give"])
                          for e in apart], [(f"{place(k, 0)[0]:#010x}/{place(k, 0)[1]}/{place(k, 0)[2]}", 32 * k, True, 0, 1, 0) for k in (0, 2)])
        for e in doc["entries"]:                         # every record an entry names as evidence shows what the entry says: none is of the state before any shift
            far, word, bit = (int(x, 0) for x in e["address"].split("/"))
            self.assertNotIn(0, e["evidence"]["code_states"], e["address"])
            for record in e["evidence"]["code_records"]:
                rec = rc.rec(record)
                self.assertEqual(((rec["frames"][far - rec["far"]][word] >> bit) & 1, rec["state"] > 0), (e["observed_transition"]["output_1"], True), (e["address"], record))
        for e in apart:                                  # and the record named for the state before any shift reads what the entry says it read
            far, word, bit = (int(x, 0) for x in e["address"].split("/"))
            rec = rc.rec(e["before_any_shift"]["record"])
            self.assertEqual(((rec["frames"][far - rec["far"]][word] >> bit) & 1, rec["state"]), (1, 0))
        plain = s2_4_table.srl_map(DESIGN, closing["table"], {"dir": "run00", "result_sha256": "0" * 64, "reads": pc["reads"], "states": pc["states"]}, singles)
        self.assertEqual((plain["places_that_read_otherwise_before_any_shift"], [e for e in plain["entries"] if "before_any_shift" in e]), (0, []))

    def test_the_singles_confirm_and_set_the_same_down(self) -> None:
        table = s2_4_table.close_code(twin("code", cells=self.CELLS, known=self.known())[2], self.known()["candidates"])["table"]
        for run, cell in ((0, 0), (1, 64)):
            p, r, v = twin("singles", run, cells=self.CELLS, known=self.known())
            self.assertEqual((v["verdict"], v["problems"], "otherwise_as_loaded" in v["finding"]), ("PASS", [], False), f"no state of the singles is before any shift ({cell})")
            h = s2_4_table.hold_singles(v, table)
            self.assertEqual((h["problems"], len(h["confirmed"])), ([], 64))

    def test_part_1_sees_such_a_place_follow_inverted_like_any_other(self) -> None:
        p, r = H4.twin("find", 1, cells=self.CELLS)
        v = H4.judged(p, r)
        self.assertEqual((v["verdict"], v["finding"]["bits"]["follow"], v["finding"]["bits"]["follow_inverted"], "otherwise_as_loaded" in v["finding"]), ("PASS", 128, 128, False))

    def test_a_bit_that_only_differs_before_any_shift_follows_nothing_and_fails_the_run(self) -> None:
        p, r, v = twin("code", cells=self.CELLS, known=self.known())
        at = r.hb + 2 * T.REC + T.DATA + T.FRAME + 7                         # the first read of the list in the first state, a word that is still
        w = list(r.words); w[at] ^= 0x10
        bad = s2_4_judge.judge(w, self.known(), s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))
        self.assertEqual((bad["verdict"], bad["finding"]["bits"]["irregular"], [x["readings"][:3] for x in bad["finding"]["irregular"]]), ("FAIL", 1, ["100"]))
        w = list(r.words); w[r.hb + (2 + 5 * len(p["reads"])) * T.REC + T.DATA + T.FRAME + 7] ^= 0x10   # and in a state made by shifts
        bad = s2_4_judge.judge(w, self.known(), s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))
        self.assertEqual((bad["verdict"], bad["finding"]["bits"]["irregular"]), ("FAIL", 1))


class TheSingles(unittest.TestCase):
    def table(self) -> list[dict]:
        return s2_4_table.close_code(clean("code")[2], KNOWN["candidates"])["table"]

    def test_each_single_changes_all_the_places_of_its_cell_and_no_other(self) -> None:
        for run in (0, 1):
            h = s2_4_table.hold_singles(clean("singles", run)[2], self.table())
            self.assertEqual((h["problems"], h["contradictions"], h["confirmed"]), ([], [], list(range(64 * run, 64 * run + 64))))

    def test_a_table_that_is_not_what_the_singles_show(self) -> None:
        v = clean("singles", 0)[2]
        table = json.loads(json.dumps(self.table()))
        table[3]["places"], table[4]["places"] = table[4]["places"], table[3]["places"]          # two cells' places exchanged
        h = s2_4_table.hold_singles(v, table)
        self.assertEqual((sorted(c["cell"] for c in h["contradictions"]), len(h["confirmed"]), len(h["problems"])), ([3, 4], 62, 2))
        table = json.loads(json.dumps(self.table())); del table[9]["places"][1]                   # one of a cell's two places is missing in the table
        h = s2_4_table.hold_singles(v, table)
        self.assertEqual(([c["cell"] for c in h["contradictions"]], h["problems"]),
                         ([9], ["cell 9: its single changes 2 bit(s), the table has 1 place(s) for it, and they are not the same places shown the same way"]))
        table = json.loads(json.dumps(self.table())); table[9]["places"][1]["inverted"] = False     # the same place, shown the other way
        self.assertEqual([c["cell"] for c in s2_4_table.hold_singles(v, table)["contradictions"]], [9])
        self.assertEqual(s2_4_table.hold_singles(v, self.table()[:-1])["problems"], ["the table is not one of every cell"])
        self.assertEqual(s2_4_table.hold_singles(clean("code")[2], self.table())["problems"], ["not a passing run of the singles"])
        self.assertEqual(s2_4_table.hold_singles(dict(v, verdict="FAIL"), self.table())["problems"], ["not a passing run of the singles"])
        stray = json.loads(json.dumps(v)); stray["finding"]["follows"].append(dict(stray["finding"]["follows"][0], cell=100, register=3, output=4))
        self.assertIn("a bit follows cell 100, which is not a cell of this run", s2_4_table.hold_singles(stray, self.table())["problems"])

    def test_a_device_that_shows_a_cell_elsewhere_than_in_the_code_run(self) -> None:
        cells = srl_map()
        i = next(k for k, c in enumerate(cells) if c[0] == 5 and c[1] == 0 and c[5])
        cells[i] = (5, 0, LOW, 44, 9, 1)                                                          # the inverted place of cell 5 is another place now
        p, r, v = twin("singles", 0, cells=cells, known=KNOWN)
        self.assertEqual(v["verdict"], "PASS", "the run passes as a run")
        h = s2_4_table.hold_singles(v, self.table())
        self.assertEqual(([c["cell"] for c in h["contradictions"]], len(h["confirmed"])), ([5], 63))


class TheDescription(unittest.TestCase):
    def description(self, upto: int = 2):
        code = clean("code"); table = s2_4_table.close_code(code[2], KNOWN["candidates"])["table"]
        singles = []
        for run in range(upto):
            p, r, v = clean("singles", run)
            singles.append({"dir": f"run{run + 1:02d}", "share": run, "result_sha256": f"{run + 1}" * 64, "reads": p["reads"], "states": p["states"],
                            "held": s2_4_table.hold_singles(v, table), "run": r})
        doc = s2_4_table.srl_map(DESIGN, table, {"dir": "run00", "result_sha256": "0" * 64, "reads": code[0]["reads"], "states": code[0]["states"]},
                                 [{k: x for k, x in s.items() if k != "run"} for s in singles])
        return doc, singles

    def test_the_description_written_out(self) -> None:
        doc, singles = self.description()
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["schema"], doc["label"], doc["design"], doc["cells"], doc["places"], len(doc["entries"])), ("srl_map", "closed-book", "s2a", 128, 256, 256))
        self.assertEqual(doc["counts"], {"confirmed": 256, "decoded": 0, "contradiction": 0})
        want = where(srl_map())
        for e in doc["entries"]:
            far, word, bit = e["address"].split("/")
            self.assertEqual(want[e["cell"]][(far, int(word), int(bit))], e["inverted"])
            self.assertEqual((e["register"], e["output"], e["confidence"], e["state"]), (*divmod(e["cell"], 32), 2, "confirmed"))
            self.assertEqual(e["observed_transition"], {"output_0": int(e["inverted"]), "output_1": 1 - int(e["inverted"])})
        self.assertEqual(doc["as_the_build_placed_them"]["registers"], {"0": "A6LUT", "1": "B6LUT", "2": "C6LUT", "3": "D6LUT"})
        self.assertEqual(doc["as_the_build_placed_them"]["site"], "SLICE_X34Y70")
        self.assertNotIn("lut_init", json.dumps(doc))

    def test_the_records_an_entry_names_are_the_records_that_show_it(self) -> None:
        doc, singles = self.description()
        code_run = clean("code")[1]
        loaded = [st.cell(clean("code")[0]["states"][0]["srl"], n) for n in range(128)]
        for e in doc["entries"][::13]:
            far, word, bit = (int(x, 0) for x in e["address"].split("/"))
            for record in e["evidence"]["code_records"]:
                rec = code_run.rec(record)
                self.assertEqual((rec["frames"][far - rec["far"]][word] >> bit) & 1, 1 - int(e["inverted"]), (e["cell"], record))
            s = e["evidence"]["single"]
            rec = next(x["run"] for x in singles if x["dir"] == s["run"]).rec(s["record"])
            turned = 1 - loaded[e["cell"]]
            self.assertEqual(((rec["frames"][far - rec["far"]][word] >> bit) & 1, rec["state"]), (turned ^ int(e["inverted"]), s["state"]))

    def test_a_cell_whose_single_was_not_made_is_decoded(self) -> None:
        doc, _ = self.description(upto=1)
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual(doc["counts"], {"confirmed": 128, "decoded": 128, "contradiction": 0})
        self.assertEqual({(e["state"], e["confidence"], e["evidence"]["single"] is None) for e in doc["entries"] if e["cell"] >= 64}, {("decoded", 1, True)})

    def test_a_cell_its_single_contradicts_is_said_to_be_so_in_every_one_of_its_places(self) -> None:
        code = clean("code"); table = json.loads(json.dumps(s2_4_table.close_code(code[2], KNOWN["candidates"])["table"]))
        table[3]["places"], table[4]["places"] = table[4]["places"], table[3]["places"]
        p, r, v = clean("singles", 0)
        held = s2_4_table.hold_singles(v, table)
        doc = s2_4_table.srl_map(DESIGN, table, {"dir": "run00", "result_sha256": "0" * 64, "reads": code[0]["reads"], "states": code[0]["states"]},
                                 [{"dir": "run01", "share": 0, "result_sha256": "1" * 64, "reads": p["reads"], "states": p["states"], "held": held}])
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual(doc["counts"], {"confirmed": 124, "decoded": 128, "contradiction": 4}, "two cells of two places each; 62 confirmed cells of 124 places")
        self.assertEqual(sorted({(e["cell"], e["state"], e["confidence"]) for e in doc["entries"] if e["state"] == "contradiction"}), [(3, "contradiction", 0), (4, "contradiction", 0)])
        self.assertTrue(all(e["evidence"]["single"] is not None for e in doc["entries"] if e["cell"] in (3, 4)), "the single that contradicts is named")

    def test_the_schema_refuses_what_is_not_such_a_description(self) -> None:
        doc, _ = self.description()
        ok = jsonschema.Draft202012Validator(SCHEMA)
        for change in (lambda d: d.update(label="open"), lambda d: d["entries"][0].update(confidence=1), lambda d: d["entries"][0].update(state="unknown"),
                       lambda d: d["entries"][0].update(address="0xb91/1/2"), lambda d: d["entries"][0].update(memory=0), lambda d: d.pop("places"),
                       lambda d: d["entries"][0].pop("output"), lambda d: d.update(schema="ram_map")):
            bad = json.loads(json.dumps(doc))
            change(bad)
            self.assertFalse(ok.is_valid(bad))


class ThePairs(unittest.TestCase):
    def test_the_states_and_what_the_judge_says_of_the_run(self) -> None:
        loaded = st.code_run(clean("code")[0]["states"][0]["srl"])[0]["srl"]
        states = st.pairs_run(loaded)
        self.assertEqual([x["name"] for x in states], ["loaded", "cells 0, 1", "cells 0, 4", "cells 0, 1, 2", "cells 0, 1, 2, 3", "loaded again"])
        self.assertEqual({x["shifted"] for x in states}, {True}, "every state of the pairs is made by shifts: section 42")
        for x in states[1:-1]:
            self.assertEqual([n for n in range(128) if st.cell(x["srl"], n) != st.cell(loaded, n)], x["cells"])
        self.assertEqual(st.PAIRS, ((0, 1), (0, 4), (0, 1, 2), (0, 1, 2, 3)))
        p, r, v = clean("pairs")
        self.assertEqual((v["verdict"], v["problems"], v["run"]["kind"], v["run"]["share"], len(v["run"]["states"])), ("PASS", [], "pairs", None, 6))
        self.assertEqual({x["cell"] for x in v["finding"]["follows"]}, {0, 1, 2, 3, 4})
        self.assertEqual(v["finding"]["cells_not_told_from_another_inverted"], [])

    def test_a_bit_that_moves_and_follows_no_cell_is_set_down_and_does_not_fail_this_run(self) -> None:
        """Review of 07abf08, and section 37, outcome 13: nothing the pairs show fails the run but registers that do not
        read back and what fails any run. In the code run and in a run of the singles the same bit fails the run."""
        p, r, v = clean("pairs")
        at = lambda run, plan, state: run.hb + (2 + state * len(plan["reads"])) * T.REC + T.DATA + T.FRAME + 7   # noqa: E731  a word that is still
        w = list(r.words); w[at(r, p, 1)] ^= 0x10        # in the second state, in which no cell is turned that is turned in no other
        now = s2_4_judge.judge(w, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))
        self.assertEqual((now["verdict"], now["problems"], now["finding"]["bits"]["irregular"], [x["readings"] for x in now["finding"]["irregular"]]), ("PASS", [], 1, ["010000"]))
        for kind, share, states in (("code", None, (1,)), ("singles", 0, (1, 2))):      # in the singles one state is one cell's: two states are no cell's
            p, r, v = clean(kind, share)
            w = list(r.words)
            for s in states:
                w[at(r, p, s)] ^= 0x10
            now = s2_4_judge.judge(w, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))
            self.assertEqual((now["verdict"], now["finding"]["bits"]["irregular"]), ("FAIL", 1), kind)
        p, r = twin("pairs", fault="srlmoves")[:2]       # registers that do not read back fail it as they fail any run
        self.assertEqual(s2_4_judge.judge(r.words, KNOWN, s2_3_judge.planned_words(r.params, p["reads"], p["entries"], DESIGN))["verdict"], "FAIL")

    def test_what_the_chain_sets_down_of_it(self) -> None:
        p, r, v = clean("pairs")
        table = s2_4_table.close_code(clean("code")[2], KNOWN["candidates"])["table"]
        shown = s2_4_chain2.shown_in_the_pairs(json.loads(json.dumps(v)), table, p["reads"])
        self.assertEqual([(x["state"], x["name"], x["cells"], x["bit_5_after_the_reads_at"]) for x in shown],
                         [(0, "loaded", [], []), (1, "cells 0, 1", [0, 1], []), (2, "cells 0, 4", [0, 4], []), (3, "cells 0, 1, 2", [0, 1, 2], []),
                          (4, "cells 0, 1, 2, 3", [0, 1, 2, 3], []), (5, "loaded again", [], [])])
        f = lambda k: f"{LOW + k:#010x}"   # noqa: E731
        # by the made-up device: cell 0 has three places (as it is in the fourth frame, twice inverted in the third); cells 1 and 2 one
        # in each of those two; cell 3 as it is in the fourth and inverted in the first; cell 4 as it is in the second, inverted in the first
        self.assertEqual([x["bits_changed_by_frame"] for x in shown],
                         [{}, {f(2): 3, f(3): 2}, {f(0): 1, f(1): 1, f(2): 2, f(3): 1}, {f(2): 4, f(3): 3}, {f(0): 1, f(2): 4, f(3): 4}, {}])
        w = json.loads(json.dumps(v))
        hit = [r_ for r_ in w["records"] if r_.get("state") == 2 and r_["far"] == f"{p['reads'][1][0]:#010x}"]
        hit[0]["int_sts_after"] = "50033024"
        self.assertEqual([x["bit_5_after_the_reads_at"] for x in s2_4_chain2.shown_in_the_pairs(w, table, p["reads"])], [[], [], [f"{p['reads'][1][0]:#010x}"], [], [], []])


class WithAPlan(unittest.TestCase):
    def setUp(self) -> None:
        H9.prepared()
        self.base = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in ("s2_4c", "s2_4s", "s2_4p")}

    def test_the_sets_and_their_plans_on_the_device(self) -> None:
        other = json.loads(s1a_run.STAGES["s2_3c"]["expected"].read_text())
        for stage, base in self.base.items():
            self.assertEqual((base["params"], base["image_sha256"], base["pl_design"]), (other["params"], other["image_sha256"], other["pl_design"]), stage)
        want = {"s2_4c": (None, "code", 17, 3029, 12, 36, "0x00001800", 105912), "s2_4p": (None, "pairs", 6, 1246, 2, 6, "0x0000181e", 10230)}
        for stage, (share, kind, states, entries, reads, frames, first, words) in want.items():
            exp = s1a_run.with_plan(stage, self.base[stage], share)
            par = [int(w, 16) for w in exp["params"]]
            self.assertEqual((par[7], par[16], par[18], par[19]), (states, reads, entries, 0x01101000), stage)
            self.assertEqual((exp["plan"]["kind"], exp["plan"]["share"], exp["plan"]["frames"], exp["plan"]["first"], exp["plan"]["last"], exp["result_words"]),
                             (kind, None, frames, first, "0x00001823", words), stage)
            self.assertEqual(exp["result_words"], s2_4_judge.layout_hdr(kind) + exp["records"] * 480, stage)
        for run in (0, 1):
            exp = s1a_run.with_plan("s2_4s", self.base["s2_4s"], run)
            self.assertEqual((exp["plan"]["kind"], exp["plan"]["share"], exp["plan"]["states"], exp["plan"]["entries"], exp["plan"]["reads"], exp["plan"]["first"], exp["result_words"]),
                             ("singles", run, 66, 11146, 2, "0x0000181e", 87390))

    def test_what_is_refused(self) -> None:
        self.assertRaisesRegex(ValueError, r"one of two \(--share\)", s1a_run.with_plan, "s2_4s", self.base["s2_4s"], None)
        self.assertRaisesRegex(ValueError, "the code run is one run", s1a_run.with_plan, "s2_4c", self.base["s2_4c"], 0)
        self.assertRaisesRegex(ValueError, "the run of the pairs is one run", s1a_run.with_plan, "s2_4p", self.base["s2_4p"], 0)
        self.assertRaisesRegex(ValueError, "no run 2", s1a_run.with_plan, "s2_4s", self.base["s2_4s"], 2)
        self.assertRaisesRegex(ValueError, r"one of four \(--share\)", s1a_run.with_plan, "s2_3s", json.loads(s1a_run.STAGES["s2_3s"]["expected"].read_text()), None)

    def test_what_the_run_script_gives_the_judges_of_the_sets(self) -> None:
        for stage in self.base:
            known = s1a_run.known_for(stage)
            self.assertEqual((known["name"], known["ctl0_in_part_1"], len(known["candidates"]["places"]), sorted(known["candidates"]["frames_with_candidates"])),
                             ("s2a", "0x00000501", 256, [f"0x{f:08x}" for f in range(0x1820, 0x1824)]), stage)
        self.assertEqual((st.CANDIDATES, st.CHAIN_OF_PART_1), (ROOT / "evidence" / "s2_4_17A6_2026-11-23" / "candidates.json", ROOT / "evidence" / "s2_4_17A6_2026-11-23" / "chain.json"))
        self.assertEqual(hashlib.sha256(st.CANDIDATES.read_bytes()).hexdigest(), "ddc123edce05375959232056d045124ec9c8d531b02dae17772fda3f215ebf48")
        self.assertNotIn("ctl0_in_part_1", s1a_run.known_for("s2_4f"))

    def test_the_dry_runs_of_the_run_script(self) -> None:
        run = lambda *a: subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s1a_run.py"), *a, "--dry-run"], capture_output=True, text=True)  # noqa: E731
        for args, line in ((["--stage", "s2_4c"], "stage s2_4c, the code run: 17 states, 3029 entries in the list of accesses, 12 reads a state, 0x00001800 .. 0x00001823"),
                           (["--stage", "s2_4s", "--share", "1"], "stage s2_4s, the singles, run 1: 66 states, 11146 entries in the list of accesses, 2 reads a state, 0x0000181e .. 0x00001823"),
                           (["--stage", "s2_4p"], "stage s2_4p, the run of the pairs: 6 states, 1246 entries in the list of accesses, 2 reads a state, 0x0000181e .. 0x00001823")):
            r = run(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn(line, r.stdout); self.assertIn("Dry run: nothing was sent.", r.stdout)
        for args, why in ((["--stage", "s2_4s"], "REFUSED: a run of the singles is one of two (--share)"), (["--stage", "s2_4c", "--share", "0"], "REFUSED: the code run is one run"),
                          (["--stage", "s2_4p", "--share", "0"], "REFUSED: the run of the pairs is one run"), (["--stage", "s2_4s", "--share", "2"], "REFUSED: there is no run 2 of the singles")):
            r = run(*args)
            self.assertEqual((r.returncode, r.stdout.strip()), (2, why))


def run2(k: int, known: dict | None = None, out: Path | None = None, cells=None, fault: str = "", env: dict | None = None, **quirks):
    """Run k of the chain through the run script, on the pretend board, over the made-up device."""
    H9.prepared()
    known = KNOWN if known is None else known
    stage, share = s2_4_chain2.run_of(k)
    exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), share, known)
    reads = [(int(w, 16) & 0x0FFFFFFF, int(w, 16) >> 28) for w in exp["list"]]
    out = Path(scratch_dirs.mkdtemp(prefix="smout42_")) if out is None else out
    out.mkdir(parents=True, exist_ok=True)
    (out / "list.bin").write_bytes(s1a_run.list_bytes(exp))
    (out / "acc.bin").write_bytes(s1a_run.acc_bytes(exp))
    exp = dict(exp, list_file=str(out / "list.bin"), acc_file=str(out / "acc.bin"))
    pl = s1a_run.pl_file(exp).read_bytes()
    srl = Path(scratch_dirs.mkdtemp(prefix="smsrl2_")) / "srlmap.txt"
    srl.write_text("".join("%d %d %x %d %d %d\n" % c for c in (srl_map() if cells is None else cells)))
    u = H9.Board9(fault, far_rule="skip", card_has_s2a=True, cells=RAM_CELLS, env=dict({"SM_SRLMAP": str(srl), "SM_SHIFTS": "allowed"}, **(env or {})),
                  **H8.device(known["census"], reads), **quirks)
    rec = s1a_run.execute(u, exp, out, lambda con, cmd, path: con.load(cmd, path), known, len(pl), f"{zlib.crc32(pl) & 0xFFFFFFFF:08x}", f"s420000{k}.bin", stage)
    return rec, u, out


class TheChain(unittest.TestCase):
    def setUp(self) -> None:
        H9.prepared()
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain42_")) / "chain"
        self.bases = {stage: json.loads(s1a_run.STAGES[stage]["expected"].read_text()) for stage in ("s2_4c", "s2_4s", "s2_4p")}
        self.calls: list[int] = []

    def runner(self, per_run: dict | None = None, **kw):
        def run(k: int, out: Path) -> None:
            self.calls.append(k)
            run2(k, out=out, **{**kw, **(per_run or {}).get(k, {})})
        return run

    def drive(self, known: dict = KNOWN, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")
        return s2_4_chain2.drive(self.root, self.bases, known, kw.pop("runner", self.runner()), **kw)

    def test_four_runs_and_the_step_is_closed(self) -> None:
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", [0, 1, 2, 3], ["go on"] * 3 + ["complete"]))
        c = a["closing"]
        self.assertEqual((c["confirmed"], c["contradictions"], c["places"], c["ctl0"], c["ctl0_in_part_1"], c["bit_5"]), (128, 0, 256, [CTL0], CTL0, {}))
        self.assertEqual(c["cells_by_their_places"], {"1 as it is, 0 inverted": 4, "1 as it is, 1 inverted": 120, "1 as it is, 2 inverted": 4})
        self.assertEqual([x["cells"] for x in c["the_pairs"]], [[], [0, 1], [0, 4], [0, 1, 2], [0, 1, 2, 3], []])
        self.assertEqual([r.get("confirmed") for r in a["runs"]], [None, list(range(64)), list(range(64, 128)), None])
        doc = json.loads((self.root / "srl_map.json").read_text())
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["counts"], doc["places"], doc["runs"]["code"]["dir"], [s["dir"] for s in doc["runs"]["singles"]]),
                         ({"confirmed": 256, "decoded": 0, "contradiction": 0}, 256, "run00", ["run01", "run02"]))
        self.assertEqual({(e["cell"], *e["address"].split("/")): e["inverted"] for e in doc["entries"]},
                         {(n, far, str(w), str(b)): inv for n, places in where(srl_map()).items() for (far, w, b), inv in places.items()})
        table = json.loads((self.root / "table" / "table.json").read_text())
        self.assertEqual((table["schema"], table["outcome"][:3], len(table["table"]), table["code_run"]["dir"], table["as_they_are"], table["inverted"]),
                         ("s2_4_table", "10:", 128, "run00", 128, 128))
        stored = json.loads((self.root / "chain.json").read_text())
        self.assertEqual(stored, json.loads(json.dumps(s2_4_chain2.brief(a))))
        self.assertNotIn("table", stored)
        self.assertEqual(stored["table_sha256"], hashlib.sha256((self.root / "table" / "table.json").read_bytes()).hexdigest())
        self.assertIn("the table written: table/table.json", said)
        self.assertTrue(said[-1].startswith("run03: pairs, 5 bit(s) follow a cell as they are, 6 inverted, 0 irregular — complete"), said[-1])
        self.assertTrue(said[2].startswith("run01: singles 0, 64 bit(s) follow a cell as they are, 64 inverted, 0 irregular, 64 cell(s) confirmed — go on"), said[2])
        self.assertTrue((self.root / "prober.bin").read_bytes() == s1a_run.IMAGE.read_bytes())
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["state"], "complete", "and it stands when looked at again")

    def test_looking_at_a_chain_writes_nothing_and_runs_nothing(self) -> None:
        a = s2_4_chain2.assess(self.root, self.bases, KNOWN)
        self.assertEqual((a["state"], a["next_run"], a["runs"], a["runs_planned"], self.root.exists()), ("go on", 0, [], 4, False))
        self.assertEqual([s2_4_chain2.run_of(k) for k in range(4)], [("s2_4c", None), ("s2_4s", 0), ("s2_4s", 1), ("s2_4p", None)])

    def test_no_single_is_started_before_the_code_run_and_the_table_are_committed(self) -> None:
        a = self.drive(committed=s2_4_chain2.committed)
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no single before the code run and its table are committed: run00", a["held"])
        self.assertTrue((self.root / "table" / "table.json").is_file())
        asked: list[Path] = []
        a = self.drive(committed=lambda path: asked.append(path) or ("" if path.name == "run00" else "table has files that are not in the last commit"))
        self.assertEqual((self.calls, asked), ([0], [self.root / "run00", self.root / "table"]))
        a = self.drive(max_new=1)
        self.assertEqual((self.calls, a["state"], len(a["runs"])), ([0, 1], "go on", 2))

    def test_a_code_run_that_gives_no_table_halts_the_chain_and_no_single_is_run(self) -> None:
        cells = [c for c in srl_map() if not (c[0] == 7 and c[1] == 2 and not c[5])]              # one cell shown inverted only
        a = self.drive(runner=self.runner(cells=cells), known=known_for(cells))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertTrue(a["why"][0].startswith("run00: closed without a table — 11:"), a["why"])
        self.assertIn("run00: 1 cell(s) have no bit that follows them as it is", a["why"])
        self.assertFalse((self.root / "table").exists())
        self.calls.clear()
        self.assertEqual((self.drive(known=known_for(cells))["state"], self.calls), ("halted", []))

    def test_a_code_run_under_another_ctl0_than_part_1_s_halts_the_chain_before_a_table_is_taken(self) -> None:
        other = {"SM_CREG": "ctl0:00000401"}
        a = self.drive(runner=self.runner(env=other))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertEqual(a["why"], ["run00: CTL0 read 0x00000401 in the code run and 0x00000501 in the runs of part 1, in which the candidates were found"])
        self.assertNotIn("table", a); self.assertFalse((self.root / "table").exists())
        self.setUp()
        a = self.drive(runner=self.runner(per_run={2: {"env": other}}))
        self.assertEqual((a["state"], self.calls, a["why"]), ("halted", [0, 1, 2], ["run02: CTL0 read 0x00000401 in this run and 0x00000501 in the code run"]))
        self.setUp()
        a = self.drive(runner=self.runner(per_run={3: {"env": other}}))
        self.assertEqual((a["state"], a["why"]), ("halted", ["run03: CTL0 read 0x00000401 in this run and 0x00000501 in the code run"]), "the pairs too")
        self.setUp()
        untold = {k: v for k, v in KNOWN.items() if k != "ctl0_in_part_1"}
        self.assertEqual(self.drive(known=untold)["state"], "halted")

    def test_a_single_that_contradicts_the_table_halts_the_chain_at_that_run(self) -> None:
        cells = srl_map()
        i = next(k for k, c in enumerate(cells) if c[0] == 5 and c[1] == 2 and c[5])
        cells[i] = (5, 2, LOW, 44, 9, 1)                                                          # cell 69 is shown elsewhere when the second singles are run
        a = self.drive(runner=self.runner(per_run={2: {"cells": cells}}))
        self.assertEqual((a["state"], self.calls, a["runs"][2]["judge"], [c["cell"] for c in a["runs"][2]["contradictions"]], len(a["runs"][2]["confirmed"])),
                         ("halted", [0, 1, 2], "PASS", [69], 63))
        self.assertFalse((self.root / "srl_map.json").exists())
        self.calls.clear()
        self.assertEqual((self.drive()["state"], self.calls), ("halted", []))

    def test_a_device_with_a_place_that_reads_otherwise_before_any_shift_goes_through_and_the_table_says_so(self) -> None:
        cells = srl_map(zero="last")
        known = known_for(as_part_1_saw(cells))
        a = self.drive(known=known, runner=self.runner(cells=cells, known=known))
        self.assertEqual((a["state"], a["closing"]["confirmed"], a["closing"]["bits_of_the_pairs_that_follow_no_cell"]), ("complete", 128, []))
        table = json.loads((self.root / "table" / "table.json").read_text())
        self.assertEqual([(x["far"], x["word"], x["bit"], x["cell"], x["reads"]) for x in table["places_that_read_otherwise_as_loaded"]],
                         [(f"{place(k, 0)[0]:#010x}", place(k, 0)[1], place(k, 0)[2], 32 * k, 1) for k in (0, 2)], "said in the table that is committed before the singles")
        doc = json.loads((self.root / "srl_map.json").read_text())
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["places_that_read_otherwise_before_any_shift"], sorted(e["cell"] for e in doc["entries"] if "before_any_shift" in e)), (2, [0, 64]))

    def test_a_bit_of_the_pairs_that_follows_no_cell_is_set_down_and_the_description_is_written(self) -> None:
        """Review of 07abf08: such a bit failed the run of the pairs, halted the chain, and kept back the description of
        128 cells the singles had confirmed."""
        import struct
        self.drive()
        d = self.root / "run03"
        raw = (d / "result.bin").read_bytes()
        w = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        w[w[7] + (2 + 1 * 2) * 480 + 76 + 101 + 7] ^= 0x10                    # the first read of the second state, a word that is still
        raw = struct.pack("<%dI" % len(w), *w)
        (d / "result.bin").write_bytes(raw)
        rec = json.loads((d / "run.json").read_text()); rec["board_crc32"] = rec["host_crc32"] = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        (d / "run.json").write_text(json.dumps(rec, indent=1) + "\n")
        exp = s1a_run.with_plan("s2_4p", self.bases["s2_4p"], None, KNOWN)
        v = s2_4_judge.judge(w, KNOWN, s1a_run.planned_words(exp))
        (d / "verdict.json").write_text(json.dumps(v, indent=1) + "\n")
        a = self.drive()
        self.assertEqual((a["state"], a["runs"][3]["judge"], len(a["runs"][3]["bits_that_follow_no_cell"]), len(a["closing"]["bits_of_the_pairs_that_follow_no_cell"])),
                         ("complete", "PASS", 1, 1))
        self.assertEqual(a["closing"]["bits_of_the_pairs_that_follow_no_cell"][0]["readings"], "010000")
        self.assertTrue((self.root / "srl_map.json").is_file())
        self.assertEqual(json.loads((self.root / "chain.json").read_text())["closing"]["bits_of_the_pairs_that_follow_no_cell"], a["closing"]["bits_of_the_pairs_that_follow_no_cell"])

    def test_a_run_that_fails_halts_the_chain(self) -> None:
        a = self.drive(runner=self.runner(per_run={3: {"fault": "srlmoves"}}))
        self.assertEqual((a["state"], self.calls, a["runs"][-1]["decision"]), ("halted", [0, 1, 2, 3], "halt"))
        self.assertFalse((self.root / "srl_map.json").exists())

    def test_a_stored_table_that_is_not_the_code_run_s_and_a_table_s_place_that_is_not_a_directory(self) -> None:
        self.drive(max_new=1)
        t = self.root / "table" / "table.json"
        doc = json.loads(t.read_text()); doc["table"][0]["places"] = doc["table"][0]["places"][:1]
        keep = t.read_text(); t.write_text(json.dumps(doc, indent=1) + "\n")
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"], ["run00: the table stored with the chain is not the table the code run's verdict gives"])
        t.unlink()
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"], ["run00: table/ is stored and the table (table.json) is not in it"])
        (self.root / "table").rmdir(); (self.root / "table").write_text("x")
        self.assertIn("is not a directory of the chain's own", s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"][0])
        (self.root / "table").unlink(); (self.root / "table").mkdir(); t.write_text(keep)
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["state"], "go on")
        self.setUp()
        (self.root / "table").mkdir(parents=True)
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"], ["a table is stored and no code run"])

    def test_a_chain_that_no_longer_stands_loses_its_description(self) -> None:
        self.drive()
        v = json.loads((self.root / "run03" / "verdict.json").read_text()); v["problems"] = ["x"]
        (self.root / "run03" / "verdict.json").write_text(json.dumps(v, indent=1) + "\n")
        a = self.drive()
        self.assertEqual((a["state"], (self.root / "srl_map.json").exists()), ("halted", False))
        self.assertIn("run03: the verdict stored beside the result is not what the judge says of the stored result", a["why"])

    def test_sets_that_do_not_declare_one_image_and_run_directories_that_are_not_the_chain_s(self) -> None:
        other = dict(self.bases, s2_4p=dict(self.bases["s2_4p"], image_sha256="0" * 64))
        self.assertEqual(s2_4_chain2.assess(self.root, other, KNOWN)["why"], ["the three sets of the step do not declare the same image and the same design"])
        self.drive(max_new=1)
        (self.root / "run02").mkdir()
        self.assertIn("without a gap", s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"][0])
        for k in (1, 3, 4):
            (self.root / f"run{k:02d}").mkdir()
        self.assertEqual(s2_4_chain2.assess(self.root, self.bases, KNOWN)["why"], ["5 run directories for 4 runs"])

    def test_a_console_that_fails_before_a_run_holds_the_chain_and_no_run_is_started(self) -> None:
        import serial, uboot_console

        def no_port():
            raise serial.SerialException("[Errno 2] could not open port: made up")
        keep_log = os.environ.get("SELFMAP_CONSOLE_LOG")
        self.addCleanup(setattr, uboot_console, "UB", uboot_console.UB)
        self.addCleanup(lambda: os.environ.pop("SELFMAP_CONSOLE_LOG", None) if keep_log is None else os.environ.__setitem__("SELFMAP_CONSOLE_LOG", keep_log))
        uboot_console.UB = no_port
        self.root.mkdir(parents=True)
        a = s2_4_chain2.drive(self.root, self.bases, KNOWN, s2_4_chain2.board_runner(self.root), committed=lambda path: "")
        self.assertEqual((a["state"], a.get("blocked"), a["runs"]), ("go on", True, []))
        self.assertIn("before run00: the console failed — SerialException", a["held"])
        self.assertFalse((self.root / "run00").exists())

    def test_the_command_looks_at_a_chain_and_touches_nothing(self) -> None:
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_chain2.py"), "--dir", str(self.root)], capture_output=True, text=True,
                           env=dict(os.environ, SELFMAP_NO_BOARD="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 run(s) stored of 4; the chain: go on", r.stdout)
        self.assertFalse(self.root.exists())


class RunsOfTheDeviceSPlans(unittest.TestCase):
    """The rehearsal of storing, for part 2: each kind of run made with the device's own plan on the pretend board and
    taken again as the audit of stored evidence takes a stored run."""

    def test_they_are_judged_again_as_they_were_judged(self) -> None:
        import struct
        H9.prepared()
        for k in (0, 2, 3):
            stage, share = s2_4_chain2.run_of(k)
            rec, u, out = run2(k, known=s1a_run.known_for(stage), cells=[])
            self.assertEqual((rec["verdict"], rec["problems"], rec["plan"]["kind"], rec["plan"]["share"]), ("PASS", [], s1a_run.PLANS_AT_RUN_TIME[stage], share), stage)
            stored = json.loads((out / "run.json").read_text())
            raw = (out / "result.bin").read_bytes()
            exp = s1a_run.with_plan(stored["stage"], json.loads(s1a_run.STAGES[stored["stage"]]["expected"].read_text()), (stored.get("plan") or {}).get("share"))
            now = s1a_run.STAGES[stored["stage"]]["judge"].judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), s1a_run.known_for(stored["stage"]), s1a_run.planned_words(exp))
            self.assertEqual(json.loads(json.dumps(now)), json.loads((out / "verdict.json").read_text()), stage)
            args = [s1a_run.PLANS_AT_RUN_TIME[stage]] + ([] if share is None else [str(share)])
            r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_4_judge.py"), str(out / "result.bin"), *args], capture_output=True, text=True)
            self.assertEqual((r.returncode, json.loads(r.stdout)["verdict"]), (0, "PASS"), r.stderr)
            r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / f"{stage}_judge.py"), str(out / "result.bin"), *args[1:]], capture_output=True, text=True)
            self.assertEqual((r.returncode, json.loads(r.stdout)["verdict"]), (0, "PASS"), r.stderr)


if __name__ == "__main__":
    unittest.main()

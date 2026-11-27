#!/usr/bin/env python3
"""S2.5, part 2 (docs/s2_plan.md, sections 45 to 47): the tables of the code run, the singles held to them, the
description, the rule the probed sites obey, and the chain of seventeen runs — on the twin and on the pretend board,
over a made-up device (tests/s2_5_made_up.py). No board is touched."""
from __future__ import annotations

import contextlib, copy, hashlib, io, json, shutil, struct, subprocess, sys, unittest, zlib
from unittest import mock
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import scratch_dirs  # noqa: E402
import s1a_run  # noqa: E402
import s2_2_shares  # noqa: E402
import s2_5_chain  # noqa: E402
import s2_5_chain2  # noqa: E402
import s2_5_judge  # noqa: E402
import s2_5_predict  # noqa: E402
import s2_5_rule  # noqa: E402
import s2_5_states as st  # noqa: E402
import s2_5_table  # noqa: E402
import s2_5_made_up as M  # noqa: E402
import test_s2_3_host as H9  # noqa: E402
from s2_5_made_up import BUILD, CTL0, DESIGN, KNOWN, LOADED, RULE, alike, b_map, judged, once, run5, twin  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "ram_map_v2.schema.json").read_text())
CENSUS = json.loads(s2_2_shares.CENSUS.read_text())
BASES = lambda: {s: json.loads(s1a_run.STAGES[s]["expected"].read_text()) for s in ("s2_5c", "s2_5s")}   # noqa: E731


def part_1(cells=None) -> dict:
    """What part 1's chain writes for the made-up device with its cells at these places: its three runs on the
    pretend board, once for each map a test asks with."""
    def make():
        H9.prepared()
        root = Path(scratch_dirs.mkdtemp(prefix="smp1_")) / "chain"
        a = s2_5_chain.drive(root, json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text()), KNOWN,
                             lambda share, out: run5("s2_5f", share, out=out, cells=cells), committed=lambda path: "")
        assert a["state"] == "complete", a.get("why")
        return json.loads((root / "candidates.json").read_text())
    return once(("part 1", None if cells is None else hashlib.sha256(repr(cells).encode()).hexdigest()), make)


BASE_1 = lambda: json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text())   # noqa: E731


def a_copy(root: Path) -> Path:
    to = Path(scratch_dirs.mkdtemp(prefix="smp1c_")) / "chain"
    shutil.copytree(root, to)
    return to


def chain_1() -> Path:
    """The chain of part 1 over the made-up device as it is stored: three runs, candidates.json, chain.json. Several
    tests look at it; one that changes anything takes a copy (`a_copy`)."""
    def make():
        H9.prepared()
        root = Path(scratch_dirs.mkdtemp(prefix="smp1s_")) / "chain"
        a = s2_5_chain.drive(root, BASE_1(), KNOWN, lambda share, out: run5("s2_5f", share, out=out), committed=lambda path: "")
        assert a["state"] == "complete", a.get("why")
        return root
    return once("part 1, stored", make)


def said_places() -> list[tuple]:
    """Where the stored prediction has every cell, as the twin is told where cells show."""
    said = json.loads(s2_5_chain.PREDICTION.read_text())
    return [(s, a, k, far, word, bit, 0) for (far, word, bit), (s, k, a) in sorted(s2_5_predict.places(said).items())]


def chain_1_of_the_device() -> Path:
    """The chain of part 1 with the plans of the device itself — the real census, its eight shares — on the pretend
    board, with the memories where the stored prediction has them. A rehearsal, and nothing of it is a result."""
    def make():
        H9.prepared()
        known = s2_5_chain.known_of_the_device()
        root = Path(scratch_dirs.mkdtemp(prefix="smp1d_")) / "chain"
        cells = said_places()
        a = s2_5_chain.drive(root, BASE_1(), known, lambda share, out: run5("s2_5f", share, known=known, out=out, cells=cells), committed=lambda path: "")
        assert a["state"] == "complete", a.get("why")
        return root
    return once("part 1 of the device, stored", make)


def two_sites_named_for_each_other(root: Path, one: int = 3, other: int = 8) -> None:
    """The change of the review of 66e4ac4: in candidates.json and nowhere else, the memories of two sites are said
    to be each other's."""
    c = json.loads((root / "candidates.json").read_text())
    names = {m["site"]: m["name"] for m in c["memories"]}
    for m in c["memories"]:
        if m["site"] in (one, other):
            m["site"] = other if m["site"] == one else one
            m["name"] = names[m["site"]]
    (root / "candidates.json").write_text(json.dumps(c, indent=1) + "\n")


def known2(cells=None) -> dict:
    return dict(KNOWN, candidates=part_1(cells), ctl0_in_part_1=CTL0)


def a_run(kind: str, share: int | None = None, cells=None, of=None) -> dict:
    """The verdict of a run of part 2 on the twin, over what part 1 found with the cells at `of` (or at `cells`)."""
    def make():
        known = known2(cells if of is None else of)
        p, r = twin(kind, share, cells=cells, known=known)
        return judged(p, r, known)
    return once(("verdict", kind, share, None if cells is None else hashlib.sha256(repr(cells).encode()).hexdigest(),
                 None if of is None else hashlib.sha256(repr(of).encode()).hexdigest()), make)


def tables() -> dict:
    return s2_5_table.close_code(a_run("code"), part_1(), DESIGN)["tables"]


class TheTables(unittest.TestCase):
    def test_the_code_run_closes_into_a_table_for_every_site(self) -> None:
        c = s2_5_table.close_code(a_run("code"), part_1(), DESIGN)
        self.assertEqual((c["problems"], c["sites"], c["cells_a_site"], c["bits_that_follow"], c["inverted"], c["candidates_of_part_1"], c["sites_with_a_table"],
                          c["sites_without_a_table"]), ([], 110, 256, 28160, 0, 28160, 110, []))
        self.assertTrue(c["outcome"].startswith("7: at every site every cell has exactly one bit, the bits are the candidates of part 1"))
        self.assertEqual(sorted(c["tables"]), list(range(110)))
        for s in (0, 49, 50, 109):
            self.assertTrue(c["tables"][s] == [(M.at(s, n // 64, n % 64), False) for n in range(256)], s)
        doc = s2_5_table.table_file(c, {"dir": "run00", "result_sha256": "0" * 64}, DESIGN)
        self.assertEqual((doc["schema"], doc["label"], doc["sites"], len(doc["tables"]), doc["tables"][7]["name"], doc["tables"][7]["places"][65], doc["tables"][7]["inverted"]),
                         ("s2_5_table", "closed-book", 110, 110, "SLICE_X16Y7", s2_5_table.text(M.at(7, 1, 1)), []))
        alike(self, s2_5_table.tables_of(json.loads(json.dumps(doc))), c["tables"], "the tables come back from the file as they went in")
        shown = dict(c, tables=dict(c["tables"]))         # a table with a place that shows its cell inverted (no layout of the twin gives one: made up)
        shown["tables"][5] = [(p, n == 9) for n, (p, _) in enumerate(c["tables"][5])]
        doc = s2_5_table.table_file(shown, {"dir": "run00", "result_sha256": "0" * 64}, DESIGN)
        self.assertEqual((doc["tables"][5]["inverted"], doc["tables"][4]["inverted"]), ([9], []))
        alike(self, s2_5_table.tables_of(json.loads(json.dumps(doc))), shown["tables"], "and so do tables with a place shown inverted")
        self.assertEqual(s2_5_table.place("0x00000b86/14/31"), (0xB86, 14, 31))

    def test_whose_memory_a_place_is_comes_from_part_1_alone(self) -> None:
        whose = s2_5_table.whose(part_1())
        alike(self, whose, {place: (s, k, a) for place, (s, k, a) in M.where(b_map()).items()}, "whose memory a place is")
        other = copy.deepcopy(part_1()); other["memories"][9]["inverted"] = True
        self.assertEqual(len(s2_5_table.whose(other)), 28160 - 64, "a memory found inverted says of no place whose it is: its places would have no table")
        bad = copy.deepcopy(part_1()); bad["the_six_moves"][3]["bit_of_the_half_word"] = 15
        self.assertRaisesRegex(ValueError, "does not give each of 64 addresses a place of its own", s2_5_table.whose, bad)

    def test_a_site_where_the_code_and_the_loaded_word_say_another_cell_has_no_table(self) -> None:
        """Two cells of a memory lie in each other's places and were loaded alike: part 1 finds the word, by the six
        moves; the code run says the two places are the other cells. That site has no table, and no single is run."""
        cells = b_map(moved=M.swap(31, 0, alike=True))
        cand = part_1(cells)
        self.assertEqual((len(cand["memories"]), cand["memories_not_found"]), (440, []))
        c = s2_5_table.close_code(a_run("code", cells=cells), cand, DESIGN)
        self.assertEqual((c["tables"], c["sites_with_a_table"], c["outcome"][:2]), (None, 109, "8:"))
        self.assertEqual(c["sites_without_a_table"], [{"site": 31, "name": "SLICE_X16Y31", "cells_with_no_bit": 0, "cells_with_several_bits": 0,
                                                      "places_where_the_code_and_the_loaded_word_say_another_cell": 2}])
        self.assertEqual(c["problems"], ["1 site(s) have no table: SLICE_X16Y31"])

    def test_what_else_leaves_a_site_without_a_table(self) -> None:
        v, cand = a_run("code"), part_1()

        def closed(change_v=None, change_c=None) -> dict:
            vv, cc = copy.deepcopy(v), copy.deepcopy(cand)
            if change_v:
                change_v(vv["finding"]["follows"])
            if change_c:
                change_c(cc)
            return s2_5_table.close_code(vv, cc, DESIGN)

        def drop(f): f[0]["bits"].pop(); f[0]["cells"].pop()
        c = closed(drop)                                  # a candidate of part 1 that follows no cell: its site has a cell with no bit
        self.assertEqual((c["tables"], c["candidates_of_part_1_that_follow_no_cell_n"], c["sites_without_a_table"][0]["cells_with_no_bit"]), (None, 1, 1))
        self.assertIn("1 candidate(s) of part 1 follow no cell", c["problems"])

        def twice(f): f[0]["cells"][0] = f[0]["cells"][1]
        c = closed(twice)                                 # two places of a site that follow one cell
        w = c["sites_without_a_table"][0]
        self.assertEqual((c["tables"], w["cells_with_no_bit"], w["cells_with_several_bits"], w["places_where_the_code_and_the_loaded_word_say_another_cell"]), (None, 1, 1, 1))

        def another_memory(f): f[0]["cells"][0] ^= 64
        c = closed(another_memory)                        # a place that follows the cell of the same address in another memory
        w = c["sites_without_a_table"][0]
        self.assertEqual((c["tables"], w["cells_with_no_bit"], w["cells_with_several_bits"], w["places_where_the_code_and_the_loaded_word_say_another_cell"]), (None, 1, 1, 1))

        def more(f): f.append({"far": "0x00000b80", "word": 3, "bits": [4], "inverted": [], "cells": [9]})
        c = closed(more)                                  # a bit that follows a cell where part 1 found no candidate
        self.assertEqual((c["tables"], c["places_part_1_did_not_have"], c["bits_that_follow_and_are_of_no_memory_found"]), (None, ["0x00000b80/3/4"], ["0x00000b80/3/4"]))
        self.assertEqual(c["problems"], ["1 bit(s) follow a cell at a place part 1 did not find",
                                         "1 bit(s) follow a cell and lie in no memory whose loaded word part 1 found: whose they are is not known"])

        def as_a_candidate(cc): cc["places"].append({"far": "0x00000b80", "word": 3, "bits": [4], "inverted": [], "as_loaded": [0], "run": "run01"})
        c = closed(more, as_a_candidate)                  # and one that part 1 had as a candidate of no memory found
        self.assertEqual(c["problems"], ["1 bit(s) follow a cell and lie in no memory whose loaded word part 1 found: whose they are is not known"])

        def turned(f): f[0]["inverted"].append(f[0]["bits"][0])
        c = closed(turned)
        self.assertEqual((c["tables"], c["places_shown_the_other_way_than_in_part_1_n"]), (None, 1))
        self.assertIn("1 place(s) follow a cell the other way than they followed the written states in part 1", c["problems"])

        def lost(cc): cc["memories"] = [m for m in cc["memories"] if (m["site"], m["memory"]) != (12, 3)]
        c = closed(change_c=lost)                         # a memory part 1 did not find: 64 bits follow cells and are nobody's
        self.assertEqual((c["tables"], c["bits_that_follow_and_are_of_no_memory_found_n"], c["sites_without_a_table"][0]["site"], c["sites_without_a_table"][0]["cells_with_no_bit"]),
                         (None, 64, 12, 64))
        for wrong, says in ((dict(v, verdict="FAIL"), "the code run is not a passing run"), (a_run("singles", 0), "the verdict is not of the code run")):
            c = s2_5_table.close_code(wrong, cand, DESIGN)
            self.assertEqual((c["tables"], c["problems"], c["outcome"]), (None, [says], "no table: there is no passing code run to close"))

    def test_the_command(self) -> None:
        tmp = Path(scratch_dirs.mkdtemp(prefix="smtab5_"))
        (tmp / "v.json").write_text(json.dumps(a_run("code")))
        (tmp / "c.json").write_text(json.dumps(part_1()))
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_5_table.py"), str(tmp / "v.json"), str(tmp / "c.json")], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["sites_with_a_table"], "tables" in json.loads(r.stdout)), (0, 110, False), r.stderr)
        self.assertEqual(subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_5_table.py")], capture_output=True, text=True).returncode, 2)


class TheSingles(unittest.TestCase):
    def test_a_run_of_the_singles_confirms_its_sixteen_cells_at_every_site(self) -> None:
        for r in (0, 9):
            h = s2_5_table.hold_singles(a_run("singles", r), tables())
            self.assertEqual((h["problems"], h["confirmed"], h["contradictions"]), ([], list(range(16 * r, 16 * r + 16)), []))

    def test_a_single_that_changes_other_than_the_tables_say_is_a_contradiction(self) -> None:
        v, t = a_run("singles", 2), tables()
        other = copy.deepcopy(t); other[40][35], other[40][36] = other[40][36], other[40][35]      # the tables with two cells of a site in each other's places
        h = s2_5_table.hold_singles(v, other)
        self.assertEqual((h["confirmed"], [c["cell"] for c in h["contradictions"]]), ([n for n in range(32, 48) if n not in (35, 36)], [35, 36]))
        self.assertEqual(h["contradictions"][0], {"cell": 35, "sites_whose_place_did_not_change_as_the_table_has_it": [40], "of_them": 1,
                                                  "bits_that_changed_and_are_no_site_s_place_for_it": [s2_5_table.text(M.at(40, 0, 35))], "of_those": 1})
        self.assertIn("cell 35: its single changes 110 bit(s); the tables have 110 place(s) for it, one a site; at 1 site(s) the place did not change as the table has it, "
                      "and 1 bit(s) changed that are no site's place for it", h["problems"])
        fewer = {s: rows for s, rows in t.items() if s != 3}                                        # a site the tables do not have: its place changes and is nobody's
        h = s2_5_table.hold_singles(v, fewer)
        self.assertEqual((h["confirmed"], h["contradictions"][0]["of_them"], h["contradictions"][0]["of_those"]), ([], 0, 1))
        vv = copy.deepcopy(v); gone = vv["finding"]["follows"][0]
        n, b = gone["cells"].pop(), gone["bits"].pop()    # a site whose place did not change, and nothing else amiss
        h = s2_5_table.hold_singles(vv, t)
        self.assertEqual([(c["cell"], c["of_them"], c["of_those"]) for c in h["contradictions"]], [(n, 1, 0)])
        turned = copy.deepcopy(t); turned[8][40] = (turned[8][40][0], True)                         # the tables say a place shows its cell inverted, and it does not
        h = s2_5_table.hold_singles(v, turned)
        self.assertEqual([(c["cell"], c["sites_whose_place_did_not_change_as_the_table_has_it"], c["of_those"]) for c in h["contradictions"]], [(40, [8], 0)])
        vv = copy.deepcopy(v); vv["finding"]["follows"][0]["cells"][0] = 200
        h = s2_5_table.hold_singles(vv, t)
        self.assertIn("a bit follows cell 200, which is not a cell of this run", h["problems"])
        self.assertEqual(len(h["contradictions"]), 1)
        self.assertEqual(s2_5_table.hold_singles(a_run("code"), t)["problems"], ["not a passing run of the singles"])
        self.assertEqual(s2_5_table.hold_singles(v, {})["problems"], ["the tables are not of every cell of their sites"])
        self.assertEqual(s2_5_table.hold_singles(v, {0: t[0][:255]})["problems"], ["the tables are not of every cell of their sites"])


class TheDescription(unittest.TestCase):
    def doc(self, held=None) -> dict:
        known = known2()
        plans = [st.plan("code", None, known, known["census"], known["candidates"])] + [st.plan("singles", r, known, known["census"], known["candidates"]) for r in (0, 9)]
        code = {"dir": "run00", "result_sha256": "a" * 64, "reads": plans[0]["reads"], "states": plans[0]["states"]}
        singles = [{"dir": f"run{r + 1:02d}", "share": r, "result_sha256": "b" * 64, "reads": p["reads"], "states": p["states"],
                    "held": (held or {}).get(r) or s2_5_table.hold_singles(a_run("singles", r), tables())} for r, p in zip((0, 9), plans[1:])]
        return s2_5_table.ram_map(DESIGN, tables(), code, singles, known["candidates"]["runs"])

    def test_it_is_a_ram_map_of_the_second_form(self) -> None:
        doc = self.doc()
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(json.dumps(doc)))
        self.assertEqual((doc["schema"], doc["schema_version"], doc["label"], doc["design"], len(doc["sites"]), doc["cells_a_site"], len(doc["entries"])),
                         ("ram_map", 2, "closed-book", "s2b", 110, 256, 28160))
        self.assertEqual(doc["counts"], {"confirmed": 32 * 110, "decoded": 224 * 110, "contradiction": 0}, "two runs of the singles were made here: 32 cells")
        e = doc["entries"][256 * 7 + 147]
        self.assertEqual(e, {"address": s2_5_table.text(M.at(7, 2, 19)), "site": 7, "cell": 147, "memory": 2, "ram_address": 19, "inverted": False, "confidence": 2, "state": "confirmed"})
        self.assertEqual(doc["sites"][107], {"site": 107, "name": "SLICE_X34Y66"})
        self.assertEqual(([r["dir"] for r in doc["runs"]["part_1"]], [r["share"] for r in doc["runs"]["part_1"]], doc["runs"]["part_1"], list(doc["runs"])),
                         (["run00", "run01", "run02"], [0, 1, 2], known2()["candidates"]["runs"], ["part_1", "code", "singles"]),
                         "the runs of part 1, which the site of every entry rests on")
        self.assertIn("rests on the runs of part 1 and on them alone", doc["evidence"]["the_site"])
        of = doc["evidence"]["of_a_cell"]
        self.assertEqual((of[147], of[200]), ({"cell": 147, "state": "confirmed", "code_states": [1, 3, 6, 8, 9, 12, 14, 15], "single": {"run": "run10", "state": 4}},   # 147 = 0b10010011
                                              {"cell": 200, "state": "decoded", "code_states": [2, 4, 6, 7, 10, 12, 13, 15], "single": None}))
        self.assertEqual(doc["evidence"]["reads"], [["0x00000b83", 3], ["0x00000b86", 3], ["0x00000b89", 3], ["0x00000b8c", 3], ["0x00000b8f", 3]])
        # the record its evidence names holds the frame, and there the place reads one: checked on the raw words of the run of the singles
        known = known2()
        p, r = twin("singles", 9, known=known)
        far, word, bit = M.at(7, 2, 19)
        k = next(i for i, (f, n) in enumerate(p["reads"]) if f <= far < f + n)
        rec = r.rec(2 + 4 * len(p["reads"]) + k)
        self.assertEqual((rec["far"], rec["frames"][far - rec["far"]][word] >> bit & 1, r.rec(2 + 3 * len(p["reads"]) + k)["frames"][far - rec["far"]][word] >> bit & 1),
                         (p["reads"][k][0], 1, 0))

    def test_as_it_is_written_to_a_file(self) -> None:
        doc = self.doc()
        text = s2_5_table.dump(doc)
        self.assertTrue(json.loads(text) == json.loads(json.dumps(doc)), "what is written is the description")
        lines = text.splitlines()
        self.assertEqual(sum(1 for ln in lines if ln.startswith('  {"address": ')), 28160, "an entry a line")
        self.assertLess(len(text), 5_000_000)

    def test_a_contradiction_is_confidence_0(self) -> None:
        refuted = {"problems": ["x"], "confirmed": [n for n in range(16) if n != 5], "contradictions": [{"cell": 5}]}
        doc = self.doc(held={0: refuted})
        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(json.dumps(doc)))
        self.assertEqual((doc["counts"]["contradiction"], doc["entries"][5]["confidence"], doc["entries"][5]["state"], doc["evidence"]["of_a_cell"][5]["single"]),
                         (110, 0, "contradiction", {"run": "run01", "state": 6}))

    def test_the_schema_refuses_what_is_not_one(self) -> None:
        doc = json.loads(json.dumps(self.doc()))
        for change in (lambda d: d.update(schema_version=1), lambda d: d["entries"][0].pop("site"), lambda d: d["entries"][0].update(evidence={}),
                       lambda d: d.update(label="open-book"), lambda d: d["entries"][0].update(address="b86/1/2"), lambda d: d.pop("evidence"),
                       lambda d: d["evidence"]["of_a_cell"][0].update(state="guessed"), lambda d: d["sites"][0].pop("name"),
                       lambda d: d["runs"].pop("part_1"), lambda d: d["runs"].update(part_1=[]), lambda d: d["runs"]["part_1"][0].pop("result_sha256"),
                       lambda d: d["evidence"].pop("the_site")):
            bad = copy.deepcopy(doc); change(bad)
            self.assertRaises(jsonschema.ValidationError, jsonschema.Draft202012Validator(SCHEMA).validate, bad)


class TheRule(unittest.TestCase):
    """The rule is read from tables; here the tables are made from the stored prediction's places — a layout that
    obeys a rule, on the census of the device — and from changed copies of it. Nothing of this is a result."""

    PREDICTION = json.loads(s2_5_chain.PREDICTION.read_text())

    def tables(self, form: int | None = None, change=None) -> dict:
        by: dict[int, list] = {s: [None] * 256 for s in range(110)}
        for place, (s, k, a) in s2_5_predict.places(self.PREDICTION, form).items():
            by[s][64 * k + a] = (place, False)
        if change:
            change(by)
        return by

    def rule(self, **kw) -> dict:
        return s2_5_rule.rule(self.tables(**kw), DESIGN, BUILD, CENSUS, s2_5_chain2.sites_of_the_kind())

    def test_a_layout_that_obeys_one_rule_is_read_as_that_rule(self) -> None:
        r = self.rule()
        self.assertEqual((r["schema"], r["label"], r["design"], r["sites_measured"], r["one_rule"], set(r["obeyed_by_every_site_measured"].values())),
                         ("s2_5_rule", "closed-book", "s2b", 110, True, {True}))
        self.assertEqual((r["sites_of_this_kind_not_measured"], len(r["measured_at"]), r["columns_of_sites_measured"]),
                         (1390, 110, [10, 12, 16, 20, 24, 28, 30, 32, 34, 38, 42]))
        self.assertEqual((r["rows_measured"]["16"], r["rows_measured"]["34"]), ("100 row(s), 0 to 99", "row 66"))
        self.assertEqual([(m["frame_above_the_lowest"], m["bit_of_the_half_word"]) for m in r["the_six_moves"]["moves"]], RULE)
        self.assertEqual(r["the_position"]["positions"], {"A6LUT": {"word_of_the_site_s_two": 0, "half": "15 down to 0"}, "B6LUT": {"word_of_the_site_s_two": 0, "half": "31 down to 16"},
                                                          "C6LUT": {"word_of_the_site_s_two": 1, "half": "15 down to 0"}, "D6LUT": {"word_of_the_site_s_two": 1, "half": "31 down to 16"}})
        self.assertEqual(r["the_half"]["rows"], {"0 to 49": ["bottom"], "50 to 99": ["top"]})
        c = r["the_column"]
        self.assertEqual((c["frames_of_the_column"], c["first_of_the_four"], c["of_site_column_0"], c["site_columns_a_column"], c["measured"]["16"], c["measured"]["34"]),
                         (36, 32, 19, 2, 36, 48))
        self.assertIn("only columns of sites with even numbers were measured", c["note"])
        self.assertEqual((r["the_word"]["the_one_word_more_after_row"], r["the_word"]["rows_measured"]), ([24], 50))
        self.assertIn("up to row 24, and 2 r + 1 and 2 r + 2 above it", r["the_word"]["says"])
        self.assertEqual(r["sites"][30], {"site": 30, "name": "SLICE_X16Y30", "frames": [f"{0x00401220 + f:#010x}" for f in range(4)], "words": [61, 62],
                                          "memories": [{"position": "D6LUT", "word": 62, "bits": "31 down to 16"}, {"position": "A6LUT", "word": 61, "bits": "15 down to 0"},
                                                       {"position": "B6LUT", "word": 61, "bits": "31 down to 16"}, {"position": "C6LUT", "word": 62, "bits": "15 down to 0"}]})

    def test_where_the_one_word_more_lies_is_read_from_the_rows(self) -> None:
        for form in (20, 21, 29):
            r = self.rule(form=form)
            self.assertEqual((r["the_word"]["the_one_word_more_after_row"], r["one_rule"]), ([form], True), form)

    def test_rows_that_do_not_say_where_it_lies_leave_it_open(self) -> None:
        keep = lambda s: (s < 100 and not 22 <= s % 50 <= 27) or s in (100, 101, 102, 103, 104, 105, 106, 108, 109)   # noqa: E731  without the rows 22 to 27, and without X32Y29
        r = s2_5_rule.rule({s: rows for s, rows in self.tables().items() if keep(s)}, DESIGN, BUILD, CENSUS)
        self.assertEqual((r["the_word"]["the_one_word_more_after_row"], r["one_rule"]), ([21, 22, 23, 24, 25, 26, 27], True))
        self.assertIn("where the one word more lies is not fixed by the rows measured: after row 21 to 27", r["the_word"]["says"])
        self.assertNotIn("sites_of_this_kind_not_measured", r)

    def test_what_does_not_obey_is_said_part_by_part(self) -> None:
        def a_cell_elsewhere(by): by[5][70], by[5][71] = by[5][71], by[5][70]
        def a_site_a_word_up(by): by[40] = [((f, w + 2, b), inv) for (f, w, b), inv in by[40]]
        def a_site_in_another_column(by): by[104] = [((f + 0x80, w, b), inv) for (f, w, b), inv in by[104]]
        def a_memory_in_the_other_half(by): by[9][:64] = [((f, w, b - 16), inv) for (f, w, b), inv in by[9][:64]]
        def a_site_in_the_other_half(by): by[10] = [((f & ~0x00400000, w, b), inv) for (f, w, b), inv in by[10]]   # a site of the rows 0 to 49, where the rows 50 to 99 lie
        def a_cell_inverted(by): by[77][3] = (by[77][3][0], True)
        def the_upper_rows_in_the_lower_half(by):
            for s in [*range(50, 100), 102, 104, 105, 107]:
                by[s] = [((f | 0x00400000, w, b), inv) for (f, w, b), inv in by[s]]
        def a_site_four_frames_down(by): by[9] = [((f - 4, w, b), inv) for (f, w, b), inv in by[9]]
        def a_site_with_its_words_apart(by): by[100] = [((f, 19 if w == 15 else w, b), inv) for (f, w, b), inv in by[100]]   # SLICE_X10Y7: the words 14 and 19 (review of 66e4ac4)
        for change, parts in ((the_upper_rows_in_the_lower_half, {"the_half"}), (a_site_four_frames_down, {"the_column"}),
                              (a_cell_elsewhere, {"the_six_moves"}), (a_site_a_word_up, {"the_word"}), (a_site_in_another_column, {"the_column"}),
                              (a_memory_in_the_other_half, {"the_position"}), (a_site_in_the_other_half, {"the_half"}), (a_cell_inverted, {"the_six_moves"}),
                              (a_site_with_its_words_apart, {"the_position", "the_word"})):
            with self.subTest(change.__name__):
                r = self.rule(change=change)
                self.assertEqual(({k for k, ok in r["obeyed_by_every_site_measured"].items() if not ok}, r["one_rule"]), (parts, False))
        r = self.rule(change=a_site_in_another_column)
        self.assertEqual((r["the_column"]["says"], r["the_column"]["measured"]["28"]), ("the columns of sites measured do not lie on one line among the columns of frames", ["45"]))
        r = self.rule(change=a_site_a_word_up)
        self.assertEqual((r["the_word"]["says"], r["the_word"]["rows"]["40"]), ("the rows measured do not have their words by one such rule", [[81, 82], [83, 84]]))
        r = self.rule(change=a_site_with_its_words_apart)
        self.assertEqual((DESIGN["ram"]["sites"][100]["name"], r["sites"][100]["words"], r["the_word"]["says"], r["the_word"]["rows"]["7"]),
                         ("SLICE_X10Y7", [14, 19], "the rows measured do not have their words by one such rule", [[14, 15], [14, 19]]),
                         "a row's words are both of them: the lower one alone, 14, is what the rule gives for row 7")
        alone = {s: rows for s, rows in self.tables(change=a_site_with_its_words_apart).items() if s == 100}
        r = s2_5_rule.rule(alone, DESIGN, BUILD, CENSUS)
        self.assertEqual((r["obeyed_by_every_site_measured"]["the_word"], r["the_word"]["rows"]), (False, {"7": [[14, 19]]}), "and so where no other site of the row is measured")


class TheChain(unittest.TestCase):
    """The chain of part 2 over the made-up device."""

    def setUp(self) -> None:
        H9.prepared()
        self.root = Path(scratch_dirs.mkdtemp(prefix="smchain5b_")) / "chain"
        self.bases = BASES()
        self.calls: list[int] = []

    def runner(self, known=None, per_run: dict | None = None, **kw):
        def run(k: int, out: Path) -> None:
            self.calls.append(k)
            stage, share = s2_5_chain2.run_of(k)
            run5(stage, share, known2() if known is None else known, out=out, **kw, **(per_run or {}).get(k, {}))
        return run

    def drive(self, known=None, **kw) -> dict:
        kw.setdefault("committed", lambda path: "")
        kw.setdefault("build", BUILD)
        return s2_5_chain2.drive(self.root, self.bases, known2() if known is None else known, kw.pop("runner", self.runner(known)), **kw)

    def test_the_runs_of_the_chain(self) -> None:
        self.assertEqual((s2_5_chain2.RUNS, s2_5_chain2.run_of(0), s2_5_chain2.run_of(1), s2_5_chain2.run_of(16)), (17, ("s2_5c", None), ("s2_5s", 0), ("s2_5s", 15)))

    def test_seventeen_runs_the_tables_the_description_and_the_rule(self) -> None:
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], self.calls, [r["decision"] for r in a["runs"]]), ("complete", list(range(17)), ["go on"] * 16 + ["complete"]))
        self.assertEqual(a["closing"], {"sites": 110, "cells_a_site": 256, "places": 28160, "cells_confirmed_at_every_site": 256, "contradictions": 0,
                                        "outcome": "7 and 9: a table for every site, and every cell confirmed at every site by its single",
                                        "ctl0": [CTL0], "ctl0_in_part_1": CTL0, "bit_5": {}})
        self.assertEqual(said[0], "the tables written: table/table.json")
        self.assertEqual(said[1], "run00: code, 28160 bit(s) follow a cell as they are, 0 inverted, 0 irregular — go on")
        self.assertEqual(said[-1], "run16: singles 15, 1760 bit(s) follow a cell as they are, 0 inverted, 0 irregular, 16 cell(s) confirmed at every site — complete")
        table = json.loads((self.root / "table" / "table.json").read_text())
        self.assertEqual((table["schema"], table["code_run"]["dir"], len(table["tables"])), ("s2_5_table", "run00", 110))
        doc = json.loads((self.root / "ram_map.json").read_text())
        jsonschema.Draft202012Validator(SCHEMA).validate(doc)
        self.assertEqual((doc["counts"], len(doc["runs"]["singles"]), doc["runs"]["code"]["result_sha256"]),
                         ({"confirmed": 28160, "decoded": 0, "contradiction": 0}, 16, a["runs"][0]["result_sha256"]))
        self.assertEqual(doc["runs"]["part_1"], known2()["candidates"]["runs"])
        alike(self, {(e["site"], e["cell"]): e["address"] for e in doc["entries"]},
              {(s, 64 * k + a): s2_5_table.text(place) for place, (s, k, a) in M.where(b_map()).items()}, "every cell of every site at its place")
        rule = json.loads((self.root / "rule.json").read_text())
        self.assertEqual((rule["schema"], rule["sites_measured"], rule["obeyed_by_every_site_measured"]["the_six_moves"], rule["obeyed_by_every_site_measured"]["the_position"]),
                         ("s2_5_rule", 110, True, True))
        self.assertFalse(rule["one_rule"], "the made-up device has all its sites in one column: no rule of the columns")
        chain = json.loads((self.root / "chain.json").read_text())
        self.assertEqual(chain, json.loads(json.dumps(s2_5_chain2.brief(a))))
        self.assertEqual((chain["table_sha256"], "table" in chain), (hashlib.sha256((self.root / "table" / "table.json").read_bytes()).hexdigest(), False))
        self.assertEqual(s2_5_chain2.assess(self.root, self.bases, known2())["state"], "complete", "and it stands when looked at again")

    def test_no_single_before_the_code_run_and_its_tables_are_committed(self) -> None:
        a = self.drive(committed=s2_5_chain2.committed)
        self.assertEqual((a["state"], self.calls, len(a["runs"])), ("go on", [0], 1))
        self.assertIn("no single before the code run and its tables are committed: run00", a["held"])
        self.assertTrue((self.root / "table" / "table.json").is_file())
        a = self.drive(committed=lambda path: "" if path.name == "run00" else "table is not committed")
        self.assertEqual((self.calls, a["held"]), ([0], "no single before the code run and its tables are committed: table is not committed"))
        a = self.drive(max_new=2)
        self.assertEqual((self.calls, a["state"], len(a["runs"]), a["next_run"]), ([0, 1, 2], "go on", 3, 3))

    def test_a_site_without_a_table_halts_the_chain_and_no_single_is_run(self) -> None:
        cells = b_map(moved=M.swap(31, 0, alike=True))
        known = known2(cells)
        a = self.drive(known, runner=self.runner(known, cells=cells))
        self.assertEqual((a["state"], self.calls, (self.root / "table").exists()), ("halted", [0], False))
        self.assertIn("run00: closed without a table for every site — 8:", a["why"][0])
        self.assertEqual(a["why"][1], "run00: 1 site(s) have no table: SLICE_X16Y31")
        self.assertEqual((self.drive(known, runner=self.runner(known, cells=cells))["state"], self.calls), ("halted", [0]), "driven again, it runs nothing")

    def test_a_code_run_under_another_ctl0_than_part_1_halts_and_so_does_a_single_under_another(self) -> None:
        a = self.drive(dict(known2(), ctl0_in_part_1="0x00000d01"))
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("CTL0 read 0x00000501 in the code run and 0x00000d01 in the runs of part 1", a["why"][0])
        self.root = self.root.parent / "other"; self.calls = []
        a = self.drive(runner=self.runner(per_run={2: {"env": {"SM_CREG": "ctl0:00000d01"}}}))
        self.assertEqual((a["state"], self.calls), ("halted", [0, 1, 2]))
        self.assertIn("run02: CTL0 read 0x00000d01 in this run and 0x00000501 in the code run", a["why"][0])

    def test_a_single_that_contradicts_the_tables_halts_the_chain(self) -> None:
        a = self.drive(max_new=1)
        self.assertEqual((a["state"], self.calls), ("go on", [0]))
        other = copy.deepcopy(b_map())                    # from the first run of the singles on, two cells of a site show in each other's places
        cells = b_map(moved={(40, 0, 3): M.at(40, 0, 4), (40, 0, 4): M.at(40, 0, 3)})
        a = self.drive(runner=self.runner(cells=cells))
        self.assertEqual((a["state"], self.calls, a["runs"][1]["confirmed"], [c["cell"] for c in a["runs"][1]["contradictions"]]),
                         ("halted", [0, 1], [n for n in range(16) if n not in (3, 4)], [3, 4]))
        self.assertTrue(a["why"][0].startswith("run01: cell 3: its single changes 110 bit(s)"), a["why"])
        self.assertFalse((self.root / "ram_map.json").exists())
        del other

    def test_tables_that_were_changed_are_not_written_over_and_halt_the_chain(self) -> None:
        self.drive(max_new=1)
        stored = self.root / "table" / "table.json"
        doc = json.loads(stored.read_text()); doc["tables"][0]["places"][0], doc["tables"][0]["places"][1] = doc["tables"][0]["places"][1], doc["tables"][0]["places"][0]
        stored.write_text(json.dumps(doc, indent=1) + "\n")
        before = stored.read_bytes()
        a = self.drive()
        self.assertEqual((a["state"], self.calls, stored.read_bytes() == before), ("halted", [0], True))
        self.assertIn("run00: the tables stored with the chain are not the tables the code run's verdict gives", a["why"])
        stored.unlink()
        a = self.drive()
        self.assertEqual((a["state"], self.calls), ("halted", [0]))
        self.assertIn("run00: table/ is stored and the tables (table.json) are not in it", a["why"])

    def test_a_stored_run_that_was_changed_takes_the_description_away(self) -> None:
        self.drive()
        self.assertTrue((self.root / "ram_map.json").is_file() and (self.root / "rule.json").is_file())
        raw = bytearray((self.root / "run05" / "result.bin").read_bytes()); raw[-5] ^= 1
        (self.root / "run05" / "result.bin").write_bytes(bytes(raw))
        said: list[str] = []
        a = self.drive(say=said.append)
        self.assertEqual((a["state"], len(self.calls)), ("halted", 17))
        self.assertIn("run05: the stored result is not the one whose checksum the board gave", a["why"][0])
        self.assertFalse((self.root / "ram_map.json").exists() or (self.root / "rule.json").exists())
        self.assertIn("ram_map.json and rule.json taken away: the chain is not complete as it is stored now", said)

    def test_what_is_not_a_chain(self) -> None:
        bases = dict(self.bases); bases["s2_5s"] = dict(bases["s2_5s"], image_sha256="0" * 64)
        a = s2_5_chain2.assess(self.root, bases, known2())
        self.assertEqual((a["state"], a["why"]), ("halted", ["the two sets of the step do not declare the same image and the same design"]))
        (self.root / "table").mkdir(parents=True)
        a = s2_5_chain2.assess(self.root, self.bases, known2())
        self.assertEqual((a["state"], a["why"]), ("halted", ["tables are stored and no code run"]))

    def test_the_command_says_that_part_1_is_not_stored(self) -> None:
        if st.CANDIDATES.is_file():
            self.skipTest("part 1 is stored")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "host" / "s2_5_chain2.py"), "--dir", str(self.root)], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (2, ""))
        self.assertIn("REFUSED: s2_5c is run over what the part before it found, and that is not stored", r.stdout)


class WhatPartOneFoundIsHeldToItsRuns(unittest.TestCase):
    """Part 2 is built on two files part 1's chain wrote, and whose memory a place is, is in them alone. Before they
    are used the stored runs of part 1 are taken again and the files held to them (review of 66e4ac4)."""

    NOT_CANDIDATES = "candidates.json of part 1 is not what its stored runs give when they are taken again"

    def held(self, root: Path, **kw) -> str:
        return s2_5_chain.not_as_its_runs_give(root, base=BASE_1(), known=KNOWN, **kw)

    def test_what_the_chain_wrote_is_what_its_runs_give(self) -> None:
        root = a_copy(chain_1())
        self.assertEqual(self.held(root), "")
        self.assertEqual(self.held(root, candidates=root / "candidates.json", chain=root / "chain.json"), "")

    def test_two_sites_named_for_each_other_in_the_candidates_file(self) -> None:
        root = a_copy(chain_1())
        two_sites_named_for_each_other(root)
        changed = json.loads((root / "candidates.json").read_text())
        closing = s2_5_table.close_code(a_run("code"), changed, DESIGN)
        self.assertEqual((closing["problems"], closing["tables"][3] == tables()[8], closing["tables"][8] == tables()[3], closing["tables"][4] == tables()[4]), ([], True, True, True),
                         "part 2 cannot tell: every site is written alike, and the code run closes over the changed file into a table for every site")
        self.assertEqual(self.held(root), self.NOT_CANDIDATES)
        self.assertEqual(self.held(chain_1(), candidates=root / "candidates.json"), self.NOT_CANDIDATES, "nor where the file is given from elsewhere")

    def test_a_chain_file_that_was_changed(self) -> None:
        root = a_copy(chain_1())
        c = json.loads((root / "chain.json").read_text())
        self.assertEqual(c["runs"][0]["ctl0"], CTL0)
        for r in c["runs"]:
            r["ctl0"] = "0x00000541"
        (root / "chain.json").write_text(json.dumps(c, indent=1) + "\n")
        self.assertEqual(self.held(root), "chain.json of part 1 is not what its stored runs give when they are taken again")

    def test_runs_that_are_not_a_complete_chain(self) -> None:
        root = a_copy(chain_1())
        raw = bytearray((root / "run01" / "result.bin").read_bytes())
        raw[4000] ^= 1
        (root / "run01" / "result.bin").write_bytes(bytes(raw))
        self.assertEqual(self.held(root), "the chain of part 1 stored there is halted, not complete, when its 2 stored run(s) are taken again: "
                                          "run01: the stored result is not the one whose checksum the board gave")
        root = a_copy(chain_1())
        shutil.rmtree(root / "run02")
        self.assertEqual(self.held(root), "the chain of part 1 stored there is go on, not complete, when its 2 stored run(s) are taken again")
        nothing = Path(scratch_dirs.mkdtemp(prefix="smp1n_"))
        shutil.copy(chain_1() / "candidates.json", nothing); shutil.copy(chain_1() / "chain.json", nothing)
        self.assertEqual(self.held(nothing), "the chain of part 1 stored there is go on, not complete, when its 0 stored run(s) are taken again",
                         "the two files alone, without the runs they were written from")

    def test_a_file_that_is_not_there(self) -> None:
        for name in ("candidates.json", "chain.json"):
            root = a_copy(chain_1())
            (root / name).unlink()
            self.assertEqual(self.held(root), f"{name} of part 1 is not there as a file that can be read")
            (root / name).write_text("{")
            self.assertEqual(self.held(root), f"{name} of part 1 is not there as a file that can be read")

    def of_the_device(self, root: Path):
        """The sets of part 2 with part 1 stored at `root`, for as long as the test looks."""
        kept = dict(s1a_run.STAGES)
        there = {stage: dict(kept[stage], part_1=root, candidates=root / "candidates.json", chain_of_part_1=root / "chain.json") for stage in ("s2_5c", "s2_5s")}
        return mock.patch.dict(s1a_run.STAGES, there)

    def command(self, *argv: str) -> tuple[int, str]:
        said = io.StringIO()
        with mock.patch.object(sys, "argv", ["s2_5_chain2.py", *argv]), contextlib.redirect_stdout(said):
            code = s2_5_chain2.main()
        return code, said.getvalue()

    def test_the_run_script_and_the_chain_of_part_2_ask_it_of_the_device_s_part_1(self) -> None:
        self.assertEqual((s1a_run.STAGES["s2_5c"]["part_1"], s1a_run.STAGES["s2_5s"]["part_1"], "part_1" in s1a_run.STAGES["s2_5f"]), (st.PART_1, st.PART_1, False))
        whole = chain_1_of_the_device()
        c = json.loads((whole / "chain.json").read_text())["closing"]
        self.assertEqual((c["candidates"], c["memories_found_once"], c["outcome"][:2], c["prediction"]["forms_under_which_every_memory_is_where_it_said"]), (28160, 440, "1:", [24]))
        self.assertEqual(c["part_2"], {"frames_with_candidates": 48, "the_result_area_holds": 262144, "a_list_holds": 178, "reads_a_state": 24,
                                       "result_words": {"code": 222566, "singles": 219110}, "can_be_planned": True})
        empty = Path(scratch_dirs.mkdtemp(prefix="smp2e_")) / "chain"
        with self.of_the_device(whole):
            for stage in ("s2_5c", "s2_5s"):
                known = s1a_run.known_for(stage)
                self.assertEqual((len(known["candidates"]["memories"]), len(known["candidates"]["runs"]), known["ctl0_in_part_1"]), (440, 8, CTL0))
            code, said = self.command("--dir", str(empty))
            self.assertEqual((code, "0 run(s) stored of 17; the chain: go on" in said), (0, True), said)
        root = a_copy(whole)
        two_sites_named_for_each_other(root)
        with self.of_the_device(root):
            for stage in ("s2_5c", "s2_5s"):
                self.assertRaisesRegex(ValueError, f"^{stage} is run over what part 1 found, and what is stored of part 1 does not stand \\(.*\\): {self.NOT_CANDIDATES}$",
                                       s1a_run.known_for, stage)
            code, said = self.command("--dir", str(empty))
            self.assertEqual((code, said.startswith("REFUSED: s2_5c is run over what part 1 found, and what is stored of part 1 does not stand ("),
                              said.rstrip().endswith(self.NOT_CANDIDATES), len(said.splitlines()), empty.exists()), (2, True, True, 1, False), said)
        root = a_copy(whole)
        shutil.rmtree(root / "run07")
        with self.of_the_device(root):
            self.assertRaisesRegex(ValueError, "the chain of part 1 stored there is go on, not complete, when its 7 stored run", s1a_run.known_for, "s2_5c")
        with self.of_the_device(chain_1()):
            self.assertRaisesRegex(ValueError, "does not stand", s1a_run.known_for, "s2_5c")       # a chain of another device than the census's


    def test_the_runs_are_held_to_the_set_kept_with_them_which_may_differ_from_the_build_s_in_its_image_alone(self) -> None:
        """S3.0 (docs/s3_plan.md, section 13): the build's image is no longer the one part 1 ran on. The set copied
        beside part 1's runs names theirs; it is the one they are held to, and it must be the build's set in every
        word but the three that say which image it is."""
        whole = chain_1_of_the_device()
        build = json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text())
        def with_kept(change=None, text=None) -> Path:
            root = a_copy(whole)
            kept = dict(build) if change is None else change(dict(build))
            (root / "expected_s2_5f.json").write_text(text if text is not None else json.dumps(kept, indent=1) + "\n")
            return root
        with self.of_the_device(with_kept()):
            self.assertEqual(len(s1a_run.known_for("s2_5c")["candidates"]["memories"]), 440, "the build's own set, kept: as before")
        another = lambda b: dict(b, image_sha256="0" * 64, image_crc32="00000000", image_bytes=b["image_bytes"] + 4)
        with self.of_the_device(with_kept(another)):
            self.assertRaisesRegex(ValueError, "the image kept with the runs is not the image the set declares", s1a_run.known_for, "s2_5c")
        for change, why in ((lambda b: dict(b, params=b["params"][:7] + ["00000004"] + b["params"][8:]), "in more than which image it is"),
                            (lambda b: {k: v for k, v in b.items() if k != "pl_design"}, "in more than which image it is"),
                            (lambda b: dict(b, image_bytes=None, extra=1), "in more than which image it is")):
            with self.subTest(why=why), self.of_the_device(with_kept(change)):
                self.assertRaisesRegex(ValueError, why, s1a_run.known_for, "s2_5s")
        with self.of_the_device(with_kept(text="{not json")):
            self.assertRaisesRegex(ValueError, r"the set kept with the runs of part 1 \(expected_s2_5f.json\) is not a file that can be read", s1a_run.known_for, "s2_5c")

    def test_a_kept_set_that_is_no_record_or_that_the_system_will_not_give_is_a_reason_and_no_exception(self) -> None:
        """External review of 73089a0: a kept set that reads as a list, as null or as a number was asked for its
        words (AttributeError), and one the system refuses to give was not caught (OSError). Either is a reason part 1
        does not stand, said as the others are."""
        whole = chain_1_of_the_device()
        for text in ("[]", "null", "123", '"a set"'):
            root = a_copy(whole)
            (root / "expected_s2_5f.json").write_text(text)
            with self.subTest(text=text):
                self.assertEqual(s2_5_chain.taken_again(root), {"why": "the set kept with the runs of part 1 (expected_s2_5f.json) is not a set"})
                with self.of_the_device(root):
                    self.assertRaisesRegex(ValueError, r"the set kept with the runs of part 1 \(expected_s2_5f.json\) is not a set", s1a_run.known_for, "s2_5c")
        root = a_copy(whole)
        kept = root / "expected_s2_5f.json"
        kept.write_text(s1a_run.STAGES["s2_5f"]["expected"].read_text())
        self.assertEqual(s2_5_chain.taken_again(root)["why"], "", "the build's own set, kept and readable")
        read = Path.read_text

        def not_given(path, *a, **kw):
            if path == kept:
                raise PermissionError(13, "Permission denied", str(path))
            return read(path, *a, **kw)
        with mock.patch.object(Path, "read_text", not_given):
            self.assertEqual(s2_5_chain.taken_again(root), {"why": "the set kept with the runs of part 1 (expected_s2_5f.json) is not a file that can be read"})

    def test_the_part_1_the_board_made_stands_under_the_image_of_s3_0(self) -> None:
        """What the six errors of the first suite after S3.0's image were: the stored part 1 held to the build's set."""
        stored = ROOT / "evidence" / "s2_5_17A6"
        self.assertNotEqual(json.loads((stored / "expected_s2_5f.json").read_text())["image_sha256"],
                            json.loads(s1a_run.STAGES["s2_5f"]["expected"].read_text())["image_sha256"], "the build's image is another")
        self.assertEqual(s2_5_chain.not_as_its_runs_give(stored), "")

    def test_part_2_is_given_what_was_held_to_the_runs_and_no_file_read_again(self) -> None:
        """Review of b8f014a: the files were held to the runs and then opened again. Another program that changes
        them just after they were held gave part 2 its own candidates, and seventeen untouched runs closed complete."""
        whole = chain_1_of_the_device()
        as_stored = json.loads((whole / "candidates.json").read_text())
        asked = s2_5_chain.taken_again
        for stage in ("s2_5c", "s2_5s"):
            root = a_copy(whole)

            def and_then_another_program_changes_the_files(*a, **kw):
                got = asked(*a, **kw)
                two_sites_named_for_each_other(root)
                c = json.loads((root / "chain.json").read_text())
                c["closing"]["ctl0"] = ["0x00000541"]
                (root / "chain.json").write_text(json.dumps(c, indent=1) + "\n")
                return got
            with self.of_the_device(root), mock.patch.object(s2_5_chain, "taken_again", and_then_another_program_changes_the_files):
                known = s1a_run.known_for(stage)
            self.assertTrue(known["candidates"] == as_stored, f"{stage}: the candidates part 2 is given are those that were held to the runs")
            self.assertEqual(known["ctl0_in_part_1"], CTL0)
            self.assertFalse(json.loads((root / "candidates.json").read_text()) == as_stored, "and the file was changed in between")
            with self.of_the_device(root):
                self.assertRaisesRegex(ValueError, self.NOT_CANDIDATES, s1a_run.known_for, stage)    # asked again, the changed files are found

    def test_what_is_taken_again_is_given_with_the_reason(self) -> None:
        root = a_copy(chain_1())
        got = s2_5_chain.taken_again(root, base=BASE_1(), known=KNOWN)
        self.assertEqual((got["why"], got["candidates"] == json.loads((root / "candidates.json").read_text()), got["chain"] == json.loads((root / "chain.json").read_text())),
                         ("", True, True))
        was = {name: (root / name).read_text() for name in ("candidates.json", "chain.json")}
        two_sites_named_for_each_other(root)

        class ReadOnce:
            """A file that is as it was when it is first read, and changed whenever it is read after that."""
            def __init__(self, name: str) -> None:
                self.name, self.reads = name, 0

            def read_text(self) -> str:
                self.reads += 1
                return was[self.name] if self.reads == 1 else (root / "candidates.json").read_text() if self.name == "candidates.json" else was[self.name].replace(CTL0, "0x00000541")
        files = {name: ReadOnce(name) for name in was}
        got = s2_5_chain.taken_again(chain_1(), candidates=files["candidates.json"], chain=files["chain.json"], base=BASE_1(), known=KNOWN)
        self.assertEqual((got["why"], got["candidates"] == json.loads(was["candidates.json"]), got["chain"] == json.loads(was["chain.json"]), [f.reads for f in files.values()]),
                         ("", True, True, [1, 1]), "each file is read once, and what is given is what was held")
        got = s2_5_chain.taken_again(root, base=BASE_1(), known=KNOWN)
        self.assertEqual((got["why"], sorted(got)), (self.NOT_CANDIDATES, ["why"]), "where it does not stand nothing is given to build on")
        shutil.rmtree(root / "run02")
        self.assertEqual(sorted(s2_5_chain.taken_again(root, base=BASE_1(), known=KNOWN)), ["why"])


class RoomForPartTwo(unittest.TestCase):
    """The closing of part 1 says whether part 2 can be planned over what it found (review of 66e4ac4: with three
    sites in other columns part 1 found every memory, and part 2 had 30 reads a state for a room of 28)."""

    KNOWN_D = None

    def room(self, frames: set[int]) -> dict:
        known = type(self).KNOWN_D = type(self).KNOWN_D or s2_5_chain.known_of_the_device()
        return s2_5_chain.room_for_part_2(known, [f"{f:#010x}" for f in sorted(frames)])

    def test_over_the_frames_the_prediction_names_and_over_more(self) -> None:
        said = {far for far, _, _ in s2_5_predict.places(json.loads(s2_5_chain.PREDICTION.read_text()))}
        r = self.room(said)
        self.assertEqual((r["can_be_planned"], r["reads_a_state"], r["result_words"], r["frames_with_candidates"]), (True, 24, {"code": 222566, "singles": 219110}, 48))
        others = [c for c in s2_2_shares.columns(s2_2_shares.layout(CENSUS)) if len(c) >= 6 and not said & set(c)]   # columns of the census in which it names nothing
        more = lambda n: {far for c in others[:n] for far in c[:6]}   # noqa: E731  for each such column two reads more a state
        r = self.room(said | more(2))
        self.assertEqual((r["can_be_planned"], r["reads_a_state"], r["result_words"]), (True, 28, {"code": 222566 + 4 * 18 * 480, "singles": 219110 + 4 * 18 * 480}))
        r = self.room(said | more(3))
        self.assertEqual((r["can_be_planned"], r["reads_a_state"], "result_words" in r), (False, 30, False))
        self.assertRegex(r["why"], r"^the result would have 2\d{5} words; its area holds 262144$")
        self.assertEqual(self.room(set()), {"frames_with_candidates": 0, "the_result_area_holds": 262144, "a_list_holds": 178, "can_be_planned": False,
                                            "why": "there is no candidate to read a state over"})
        r = self.room({0x00C00000})
        self.assertEqual((r["can_be_planned"], r["why"]), (False, "a frame with candidates is no address of block type 0 of the census"))

    def test_a_chain_of_part_2_whose_next_run_has_no_plan_does_not_say_go_on(self) -> None:
        """Review of b8f014a: with 30 reads a state part 1 said that part 2 cannot be planned and the dry run refused
        — and the chain of part 2, asked where it stands, said "go on" and ended with 0."""
        said = {far for far, _, _ in s2_5_predict.places(json.loads(s2_5_chain.PREDICTION.read_text()))}
        others = [c for c in s2_2_shares.columns(s2_2_shares.layout(CENSUS)) if len(c) >= 6 and not said & set(c)]
        frames = lambda n: {"frames_with_candidates": {f"{far:#010x}": 0 for far in sorted(said | {far for c in others[:n] for far in c[:6]})}}   # noqa: E731
        known = lambda n: dict(s1a_run.known_for("s2_5f"), candidates=frames(n), ctl0_in_part_1=CTL0)   # noqa: E731
        empty = Path(scratch_dirs.mkdtemp(prefix="smp2r_")) / "chain"
        a = s2_5_chain2.assess(empty, BASES(), known(2))
        self.assertEqual((a["state"], a["next_run"]), ("go on", 0), "28 reads: there is room")
        a = s2_5_chain2.assess(empty, BASES(), known(3))
        self.assertEqual((a["state"], a["runs"], "next_run" in a), ("halted", [], False))
        self.assertRegex(a["why"][0], r"^no plan can be made for the next run, run00: the result would have 2\d{5} words; its area holds 262144$")
        out = io.StringIO()
        no_room = known(3)
        with mock.patch.object(s1a_run, "known_for", lambda stage: no_room), mock.patch.object(sys, "argv", ["s2_5_chain2.py", "--dir", str(empty)]), contextlib.redirect_stdout(out):
            code = s2_5_chain2.main()
        self.assertEqual((code, "0 run(s) stored of 17; the chain: halted" in out.getvalue(), "no plan can be made for the next run, run00" in out.getvalue(), empty.exists()),
                         (1, True, True, False), out.getvalue())
        calls: list[int] = []
        a = s2_5_chain2.drive(empty, BASES(), no_room, lambda k, o: calls.append(k), committed=lambda path: "")
        self.assertEqual((a["state"], calls), ("halted", []), "and nothing is sent")

    def test_the_closing_of_the_made_up_chain_says_it_and_the_command_says_where_it_cannot(self) -> None:
        c = json.loads((chain_1() / "chain.json").read_text())["closing"]["part_2"]
        self.assertEqual((c["can_be_planned"], c["reads_a_state"], c["frames_with_candidates"]), (True, 5, 12))
        state = {"step": "s2_5, part 1", "shares": 8, "runs": [], "state": "complete", "candidates_file": "there",
                 "closing": {"outcome": "2: ...", "part_2": {"can_be_planned": False, "why": "the result would have 265766 words; its area holds 262144"}}}
        for a, note in ((state, True), (dict(state, closing=dict(state["closing"], part_2={"can_be_planned": True})), False), ({k: v for k, v in state.items() if k != "closing"}, False)):
            said = io.StringIO()
            with mock.patch.object(s2_5_chain, "assess", lambda *_: a), mock.patch.object(sys, "argv", ["s2_5_chain.py", "--dir", "nowhere"]), contextlib.redirect_stdout(said):
                s2_5_chain.main()
            self.assertEqual("NOTE: the runs of part 2 cannot be planned over these frames as the stage is (the result would have 265766 words; its area holds 262144): "
                             "what part 1 found stands, and part 2 has no run" in said.getvalue(), note, said.getvalue())


class ARunOfTheDeviceSPlan(unittest.TestCase):
    """A rehearsal of storing a run of part 2 with a plan of the device's size: the real census and design, and for
    what part 1 found the frames the prediction names — 24 reads. On the pretend board, whose made-up frames read zero
    there: nothing follows, and the run is stored, judged and judged again as the audit of stored evidence does."""

    def test_it_is_stored_and_judged_again_as_it_was_judged(self) -> None:
        H9.prepared()
        said = json.loads(s2_5_chain.PREDICTION.read_text())
        cand = {"frames_with_candidates": {f"{far:#010x}": 0 for far in sorted({k[0] for k in s2_5_predict.places(said)})}}
        known = dict(s1a_run.known_for("s2_5f"), candidates=cand, ctl0_in_part_1=CTL0)
        for stage, share, words in (("s2_5c", None, 222566), ("s2_5s", 15, 219110)):
            with self.subTest(stage):
                rec, u, out = run5(stage, share, known=known, cells=[])
                self.assertEqual((rec["verdict"], rec["problems"], rec["plan"]["share"], rec["plan"]["reads"], rec["plan"]["states"]), ("PASS", [], share, 24, 18))
                raw = (out / "result.bin").read_bytes()
                self.assertEqual((len(raw), f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"), (4 * words, rec["board_crc32"]))
                exp = s1a_run.with_plan(stage, json.loads(s1a_run.STAGES[stage]["expected"].read_text()), share, known)
                now = s1a_run.STAGES[stage]["judge"].judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1a_run.planned_words(exp))
                self.assertEqual(json.loads(json.dumps(now)), json.loads((out / "verdict.json").read_text()))
                self.assertEqual((now["verdict"], now["run"]["kind"], now["run"]["share"], now["finding"]["frames"], now["finding"]["bits"]["follow"]),
                                 ("PASS", rec["plan"]["kind"], share, 72, 0))


if __name__ == "__main__":
    unittest.main()

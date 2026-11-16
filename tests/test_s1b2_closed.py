"""The row as closed by the two runs at its end (docs/s1b_plan.md, section 32): s1b2_closed.py on the twin's ends of a
row, each of its rules broken in turn, and the grader on what it writes. The rows here are made up; nothing in this
file is a number of any real part, and no database is read."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import grade_s1b2  # noqa: E402
import s1b2_closed as closed  # noqa: E402
import s1b2_row  # noqa: E402
import test_s1b2_end as at  # noqa: E402
from test_s1b2_end import BOTH, LAST, NEXT_ROW, NONE, ONE, SHOWN, TWO, h, the  # noqa: E402

BEFORE = [(0x1A80, 0x1A81), (0x1A81, 0x1A82), (0x1A82, 0x1B00), (0x1B00, 0x1B01), (0x1B01, 0x1B80)]      # columns 53 (3 frames) and 54 (2)
STOOD = {ONE: 1, TWO: 1, BOTH: 2}                    # steps the register stands still before it shows the next row


def copy(x):
    return json.loads(json.dumps(x))


def the_row(end: str = ONE) -> dict:
    """The summary of a chain that halted like the board's: two columns walked whole, then one frame of the column
    the twin's walk goes on in — its seam frame, as the last accepted run would have had it."""
    seam = {k: the("s1b2", end)[1]["walk"][0][k] for k in ("far", "next", "frame_sha256")}
    walk = [{"far": h(a), "next": h(b), "frame_sha256": hashlib.sha256(b"%d" % a).hexdigest()} for a, b in BEFORE] + [seam]
    return s1b2_row.summarize({"state": "halted", "why": ["run01: stopped by the prober"],
                               "runs": [{"dir": "run00", "decision": "go on", "walk": walk}, {"dir": "run01", "decision": "halt", "walk": []}]}, at.KNOWN)


def parts(end: str = ONE) -> list[dict]:
    """The four things the program is given: the chain's summary, the walk it stopped on, the column again, the end."""
    return [the_row(end), copy(the("s1b2", end)[1]), copy(the("s1b2c", end)[1]), copy(the("s1b2e", end)[1])]


def targets(v: dict) -> list[dict]:
    return [r for r in v["records"] if r["kind"] == "target"]


def database(columns: dict[int, int], bottom: bool = True) -> dict:
    """A part description of the database's shape with the given columns in row 0 of the top half."""
    def half(c):
        return {"rows": {"0": {"configuration_buses": {"CLB_IO_CLK": {"configuration_columns": {str(k): {"frame_count": n} for k, n in c.items()}}}}}}
    return {"global_clock_regions": {"top": half(columns), **({"bottom": half({0: 7})} if bottom else {})}}


class TheRowClosed(unittest.TestCase):
    def test_a_row_whose_chain_halted_at_such_an_end_is_closed(self) -> None:
        for end in (ONE, TWO, BOTH):
            with self.subTest(end=end):
                row, walk, again, e = parts(end)
                self.assertEqual((row["chain"]["state"], row["end"]["reached"], row["frames_per_column"], row["columns"][-1]["walked_whole"]),
                                 ("halted", False, [[53, 3], [54, 2], [55, 1]], False), "what the chain's own summary says")
                out = closed.close(row, walk, again, e)
                self.assertNotIn("refused", out)
                self.assertEqual(out["closed"]["rules"], {"1a": True, "1b": True, "1c": True, "2": True, "3": True, "4": True})
                self.assertEqual((out["frames"], out["frames_per_column"], out["unexpected"]), (5 + 42, [[53, 3], [54, 2], [55, 42]], []))
                self.assertTrue(all(c["walked_whole"] for c in out["columns"]))
                self.assertEqual(out["columns"][:2], row["columns"][:2], "the columns the chain walked whole, as they were")
                self.assertEqual((out["columns"][2]["first"], out["columns"][2]["last"], out["columns"][2]["named_after_the_last"], out["columns"][2]["minors_are_0_to_n_minus_1"]),
                                 (h(0x1B80), h(LAST), h(LAST), True))
                self.assertEqual(out["addresses"][:6], row["addresses"])
                self.assertEqual([(s["far"], s["next"], s["frame_sha256"]) for s in out["addresses"][5:]], [(s["far"], s["next"], s["frame_sha256"]) for s in walk["walk"]])
                self.assertEqual({s["run"] for s in out["addresses"][6:]}, {closed.THE_RUN})
                self.assertEqual((out["end"]["reached"], out["end"]["last_frame"], out["end"]["named_after_the_last_frame"], out["end"]["that_address"]["half"]),
                                 (True, h(LAST), h(NEXT_ROW), "bottom"))
                still = out["end"]["the_register_stood_still"]
                self.assertEqual((still["steps_before_that_address"], still["at_steps_beyond_the_last_frame"]), (STOOD[end], SHOWN[end][1]))
                self.assertEqual(still["register_step_by_step"], [{"steps_beyond": k + 1, "register": h(a)} for k, a in enumerate(SHOWN[end][0])])
                self.assertEqual(out["end"]["frames_delivered_from_beyond_the_last_frame"], [{"steps_beyond": 1, "all_zero": False}, {"steps_beyond": 2, "all_zero": False}])
                # the chain is not made to look as if it had completed
                self.assertEqual(out["chain"], row["chain"])
                self.assertEqual((out["closed"]["frames_added"], out["closed"]["frames_read_again"], out["closed"]["of_which_the_same"], out["closed"]["chain_summary_frames"]), (41, 42, 42, 6))
                self.assertIn("the chain itself halted", out["closed"]["by"])
                self.assertEqual({k: out[k] for k in ("column_of_s1b1", "known_frames_walked", "known_frames_not_walked") if k in row},
                                 {k: row[k] for k in ("column_of_s1b1", "known_frames_walked", "known_frames_not_walked") if k in row})
                self.assertEqual(row, the_row(end), "the summary given is not altered")

    def refusal(self, name: str, row, walk, again, e) -> dict:
        out = closed.close(row, walk, again, e)
        self.assertIn("refused", out, name)
        self.assertEqual(set(out) - {"refused", "rules"}, set(), "no summary, no column, no address: nothing a grader could take for a row")
        self.assertTrue(all(why.startswith("rule ") for why in out["refused"]) or "rules" not in out)
        return out

    def test_a_summary_with_nothing_to_close_is_refused(self) -> None:
        row, walk, again, e = parts()
        for name, change in (("a chain that completed", lambda r: r["chain"].update(state="complete")), ("a row that was left", lambda r: r["end"].update(reached=True)),
                             ("no address", lambda r: r.update(addresses=[])), ("no column", lambda r: r.update(columns=[]))):
            other = copy(row); change(other)
            self.assertEqual(self.refusal(name, other, walk, again, e)["refused"], ["the summary is not that of a halted chain that did not leave its row: there is nothing to close"], name)
        nothing = copy(walk); nothing["walk"] = []
        self.assertEqual(self.refusal("an empty walk", row, nothing, again, e)["refused"], ["the run the chain stopped on walked nothing"])

    def test_rule_1a_the_walk_was_stopped_at_an_address_that_names_itself_and_for_nothing_else(self) -> None:
        row, walk, again, e = parts()
        self.assertEqual(len(walk["problems"]), 2, "the two things the judge says of such a stop")
        cases = {"another status": lambda w: w["header"].update(status="0x300"),
                 "an anomaly": lambda w: w["header"].update(anomalies=1),
                 "another problem beside the stop": lambda w: w["problems"].append("the reference frame differs from the known frame"),
                 "a cross-check that failed elsewhere": lambda w: w["problems"].append(f"after the frame at {h(0x1B90)} the register held {h(0x1B93)}, but the device names {h(0x1B92)} after {h(0x1B91)}"),
                 "a cross-check at the last address that is not the stop": lambda w: w["problems"].append(f"after the frame at {h(LAST)} the register held {h(NEXT_ROW)}, but the device names {h(0x1B92)} after {h(0x1B91)}"),
                 "a list that is not a chain of names": lambda w: w["walk"][9].update(next=h(0x1B8B)),
                 "a last address that names another": lambda w: w["walk"][-1].update(next=h(NEXT_ROW))}
        for name, change in cases.items():
            with self.subTest(case=name):
                other = copy(walk); change(other)
                out = self.refusal(name, row, other, again, e)
                self.assertFalse(out["rules"]["1a"])
                self.assertIn("rule 1a: the walk was not stopped at an address that names itself and for nothing else", out["refused"])
        # a walk that ended otherwise: the twin's row without such a place, where the walk leaves the envelope
        left = copy(the("s1b2", NONE)[1])
        self.assertNotEqual(left["header"]["status"], closed.STOPPED)
        self.assertFalse(self.refusal("a walk that left", row, left, again, e)["rules"]["1a"])
        short = copy(walk); short["walk"] = short["walk"][:-1]                   # its last address does not name itself
        self.assertFalse(self.refusal("cut short", row, short, again, e)["rules"]["1a"])

    def test_rule_1b_the_walk_begins_with_the_last_frame_of_the_last_accepted_run(self) -> None:
        row, walk, again, e = parts()
        for key, value in (("far", h(0x1B7F)), ("next", h(0x1B82)), ("frame_sha256", "0" * 64)):
            with self.subTest(differs=key):
                other = copy(row); other["addresses"][-1][key] = value
                out = self.refusal(key, other, walk, again, e)
                self.assertEqual((out["rules"]["1b"], out["rules"]["1a"], out["rules"]["1c"]), (False, True, True))

    def test_rule_1c_every_frame_of_the_walk_was_read_again_by_the_second_path(self) -> None:
        row, walk, again, e = parts()

        def fails(name: str, w=walk, a=again) -> None:
            out = self.refusal(name, row, w, a, e)
            self.assertFalse(out["rules"]["1c"], name)
            self.assertIn("rule 1c: the second path did not pass, or did not read every frame of the walk again as the walk had it", out["refused"])
        other = copy(again); other["verdict"] = "FAIL"
        fails("the second path did not pass", a=other)
        other = copy(walk); other["walk"][7]["frame_sha256"] = "0" * 64
        fails("a frame that differs", w=other)
        other = copy(again); other["records"] = [r for r in other["records"] if not (r["kind"] == "target" and r["far"] == h(0x1B86))]
        fails("three addresses of the walk not read again", a=other)
        other = copy(again); [r.update(far_read_back=h(0x1B8B)) for r in targets(other) if r["far"] == h(0x1B86)]
        fails("the register after a read is not what the walk's successors say", a=other)
        other = copy(again); [r.update(far_read_back=h(0x1B8B)) for r in targets(other) if r["far"] == h(0x1B86) and r["repeat"] == 1]
        fails("one repeat left another register", a=other)

    def test_rule_2_the_last_address_is_where_the_pad_alone_leaves_the_register_standing(self) -> None:
        row, walk, again, e = parts()

        def fails(name: str, w=walk, x=e) -> dict:
            out = self.refusal(name, row, w, again, x)
            self.assertFalse(out["rules"]["2"], name)
            self.assertTrue(any(why.startswith("rule 2: the run at the end did not pass") for why in out["refused"]))
            return out
        other = copy(e); other["verdict"] = "FAIL"
        fails("the run at the end did not pass", x=other)
        other = copy(e); [r.update(far_read_back=h(NEXT_ROW)) for r in targets(other) if (r["far"], r["frames"]) == (h(0x1BA8), 3)]
        fails("two ways to a position disagree", x=other)
        other = copy(e); [r.update(far_read_back=h(LAST)) for r in targets(other) if (r["far"], r["frames"]) == (h(0x1BA7), 0)]
        fails("the starting addresses are not one step apart", x=other)
        # the twin's row without such a place: the pad alone at the last address names the next row at once
        out = fails("the register does not stand still", x=copy(the("s1b2e", NONE)[1]))
        self.assertEqual((out["rules"]["1a"], out["rules"]["1b"]), (True, True))
        # the walk's last address is not the last address the run at the end wrote
        elsewhere = copy(walk); elsewhere["walk"] = elsewhere["walk"][:-1]; elsewhere["walk"][-1]["next"] = elsewhere["walk"][-1]["far"]
        elsewhere["problems"] = [p.replace(h(LAST), h(LAST - 1)) for p in elsewhere["problems"]]
        out = fails("another last address", w=elsewhere)
        self.assertTrue(out["rules"]["1a"], "by itself that walk is one stopped at an address that names itself")
        # the run at the end and the walk say different things of what follows a starting address
        other = copy(walk); other["walk"][-3]["next"] = h(LAST)                 # after 0x1ba7 the walk would have 0x1ba9
        self.assertFalse(closed.close(row, other, again, e)["rules"]["2"])

    def test_rule_3_the_address_named_after_the_row(self) -> None:
        row, walk, again, e = parts(TWO)
        never = copy(e)                                                         # the register still reads the last address at every step seen
        [r.update(far_read_back=h(LAST)) for r in targets(never) if int(r["far"], 16) + r["frames"] + 1 > LAST]
        out = self.refusal("the register never leaves", row, walk, again, never)
        self.assertEqual((out["rules"]["3"], out["rules"]["2"]), (False, True))
        self.assertIn("rule 3: the register was not seen to stand still and then to show an address outside the row", out["refused"])
        inside = copy(e)                                                        # what it shows then is an address of the same row
        [r.update(far_read_back=h(int(r["far_read_back"], 16) - NEXT_ROW + 0x1C00)) for r in targets(inside) if int(r["far_read_back"], 16) >= NEXT_ROW]
        out = self.refusal("an address of the same row", row, walk, again, inside)
        self.assertEqual((out["rules"]["3"], out["rules"]["2"]), (False, True))
        for name, value in (("another row", 1 << 17), ("another block type", 1 << 23), ("the other half", NEXT_ROW)):
            there, too = copy(e), copy(again)                                   # in both runs: one read was made in both
            for v in (there, too):
                [r.update(far_read_back=h(int(r["far_read_back"], 16) - NEXT_ROW + value)) for r in targets(v) if int(r["far_read_back"], 16) >= NEXT_ROW]
            out = closed.close(row, walk, too, there)
            self.assertEqual((out.get("refused"), out.get("end", {}).get("named_after_the_last_frame")), (None, h(value)), name)
            if value != NEXT_ROW:                                               # and where only one of the two runs says so, the read they share gives it away
                out = self.refusal(name, row, walk, again, there)
                self.assertEqual((out["rules"]["1c"], out["rules"]["3"]), (False, True))

    def test_rule_4_the_columns_the_chain_walked_whole_come_out_as_they_were(self) -> None:
        row, walk, again, e = parts()
        for name, change in (("a column of the chain's with another count", lambda r: r["columns"][0].update(frames=4)),
                             ("the column cut short is another column", lambda r: r["columns"][-1].update(column=56)),
                             ("the column cut short begins elsewhere", lambda r: r["columns"][-1].update(first=h(0x1B81))),
                             ("a column more in the chain's summary", lambda r: r["columns"].insert(0, dict(r["columns"][0], column=52)))):
            with self.subTest(case=name):
                other = copy(row); change(other)
                out = self.refusal(name, other, walk, again, e)
                self.assertEqual(out["rules"], {"1a": True, "1b": True, "1c": True, "2": True, "3": True, "4": False})
                self.assertEqual(out["refused"], ["rule 4: the columns the chain walked whole do not come out of the longer list as they were"])

    def test_through_the_command_line(self) -> None:
        row, walk, again, e = parts(TWO)
        out = the("s1b2e", TWO)[3]
        names = []
        for name, v in (("row", row), ("walk", walk), ("again", again), ("end", e)):
            (out / f"c_{name}.json").write_text(json.dumps(v)); names.append(str(out / f"c_{name}.json"))
        prog = [sys.executable, "-B", str(ROOT / "host" / "s1b2_closed.py")]
        p = subprocess.run(prog + names, capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, closed.close(row, walk, again, e)))
        bad = copy(walk); bad["walk"][3]["frame_sha256"] = "0" * 64
        (out / "c_bad.json").write_text(json.dumps(bad))
        p = subprocess.run(prog + [names[0], str(out / "c_bad.json")] + names[2:], capture_output=True, text=True)
        self.assertEqual((p.returncode, set(json.loads(p.stdout))), (1, {"refused", "rules"}))
        self.assertEqual(subprocess.run(prog + names[:3], capture_output=True).returncode, 2)

    def test_the_program_holds_no_answer(self) -> None:
        text = (ROOT / "host" / "s1b2_closed.py").read_text()
        tree = ast.parse(text)
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        self.assertEqual(numbers - {0, 1, 2, 3, 5, 16}, set(), "no address, no count of frames or columns, no count of steps")
        for word in ("prjxray", "part.json", "frame_count", "1ba", "400000"):
            self.assertNotIn(word, text.lower())
        imported = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported - {"__future__", "json", "sys", "pathlib", "s1b2_end", "s1b2_row"}, set())


class TheGraderOnARowClosed(unittest.TestCase):
    def closed_row(self, end: str = TWO) -> dict:
        return closed.close(*parts(end))

    def test_it_is_graded_like_any_row_and_the_grade_says_what_it_was(self) -> None:
        g = grade_s1b2.grade(self.closed_row(), database({53: 3, 54: 2, 55: 42}))
        self.assertEqual((g["differs"], g["chain"]), ([], "halted"))
        self.assertIn("the chain itself halted", g["summary_closed_by"])
        self.assertIn("each of the 3 column(s) walked whole has the number of frames the database gives it", g["agrees"])
        self.assertIn("frames in the row: the walk found 47, the database's columns add up to 47", g["agrees"])
        self.assertTrue(any(a.startswith(f"the address named after the last frame of the row is {h(NEXT_ROW)}") and a.endswith(f"is {h(NEXT_ROW)}") for a in g["agrees"]), g["agrees"])
        self.assertEqual(g["not_compared"], ["the register stood still at step(s) [1, 3] beyond the last frame of the row: the database lists frames and has nothing to hold that against",
                                             "2 frame(s) were delivered from beyond the last frame of the row: they are not graded"])
        self.assertEqual([(c["column"], c["walked"], c["database"], c["walked_whole"]) for c in g["columns"]], [(53, 3, 3, True), (54, 2, 2, True), (55, 42, 42, True)])

    def test_it_says_where_the_database_differs(self) -> None:
        row = self.closed_row()
        g = grade_s1b2.grade(row, database({53: 3, 54: 2, 55: 41}))
        self.assertIn("column 55: the walk found 42 frame(s), the database says 41", g["differs"])
        self.assertIn("frames in the row: the walk found 47, the database's columns add up to 46", g["differs"])
        g = grade_s1b2.grade(row, database({53: 3, 54: 2, 55: 42, 56: 30}))          # a column more in the database
        self.assertTrue(any(d.startswith("the columns walked are [53, 54, 55]") for d in g["differs"]), g["differs"])
        g = grade_s1b2.grade(row, database({53: 3, 54: 2, 55: 42}, bottom=False))   # no row after it in the database's order
        self.assertEqual((g["differs"], len(g["not_compared"])), ([], 3))
        self.assertIn("the register stood still at step(s) [1, 3]", g["not_compared"][0])
        other = json.loads(json.dumps(row)); other["end"]["named_after_the_last_frame"] = h(1 << 17)
        g = grade_s1b2.grade(other, database({53: 3, 54: 2, 55: 42}))
        self.assertTrue(any(d.startswith(f"the address named after the last frame of the row is {h(1 << 17)}") for d in g["differs"]))

    def test_the_chains_own_summary_is_graded_as_before(self) -> None:
        g = grade_s1b2.grade(the_row(), database({53: 3, 54: 2, 55: 42}))
        self.assertNotIn("summary_closed_by", g)
        self.assertEqual(g["differs"], [])
        self.assertIn("column 55: the chain stopped in it after 1 frame(s); the database gives it 42", g["agrees"])
        self.assertEqual(g["not_compared"], ["the chain did not leave the row: the database's 1 further column(s) and what follows the row were not compared"])
        self.assertEqual(grade_s1b2.grade({"refused": ["rule 2: …"], "rules": {}}, database({53: 3}))["not_compared"], ["the summary lists no column"], "a refusal is no row")


if __name__ == "__main__":
    unittest.main()

"""Every stored run under evidence/, taken again (docs/s1b_review.md, finding F1).

The other tests of the stored evidence hold particular runs to what their records say of them. This one leaves none
out: every run record there is, its result judged again from its raw words by the judge of its set as that judge is
now, and held against what was stored beside it. A result that was altered, a verdict that was edited, a run nobody
wrote a test for: each shows here.

What is pinned below is what the audit found when it was first made (2026-11-19), with the reason beside it. No
database is read and nothing is graded."""
from __future__ import annotations

import collections
import json
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tests"))
import s1a_run  # noqa: E402
import test_s1b2 as row_tests  # noqa: E402

EVIDENCE = ROOT / "evidence"
# Runs whose record has a stop and no result of its own. Four pulls did not give the board's checksum, or the serial
# adapter dropped off the host; each of those results was taken from the card afterwards and is kept beside the run.
# The fifth was set aside when the console lost characters before anything could be pulled: there is no result.
RECOVERED = {"fifo_rate_17A6_2026-11-14/rate1_run01", "fifo_rate_17A6_2026-11-14/ratep_run03", "s1b1_17A6_2026-11-14/run1", "s1b1_17A6_2026-11-14/run2"}
NEVER_PULLED = {"s1b3_17A6_2026-11-17/halted_at_run51/run51", "s2_2_17A6_2026-11-22/halted_at_run01/run01"}
# Stored verdicts that are the judges' words of their day: the judges were given more to say afterwards (where the
# polling variable lay and what the polling loop was, 2026-11-15; the words of a record, 2026-11-14) and the stored
# files were left as they were. Directory: how many of its runs. PASS or FAIL is the same in every one of them.
OLDER_FORM = {"dx_17A6_2026-11-15": 18, "fifo_rate_17A6_2026-11-14": 19, "s1b0_17A6_2026-11-14": 1, "s1b0b_17A6_2026-11-14": 1, "s1b1_17A6_2026-11-14": 2}
# What they may lack, and nothing else: every field a stored verdict has must be what the judge writes now.
# All of it is about the polling loop that the overflow was traced to (plan, sections 15 to 22), but for the words of a
# record, which the first judge of the address register's value did not list.
ADDED_SINCE = {"params.polling_loop", "params.diagnostic.polling_loop", "params.extra_stack_words", "polling_variable", "records[].poll_variable_at", "records[].words"}
# The one run in which today's judge lists a problem the stored verdict does not have: the run that first met the
# overflow. Its header says the reference frame changed; its records imply a failure of the interface. Failed then, failed now.
ONE_PROBLEM_MORE = {"fifo_rate_17A6_2026-11-14/s1b1_run03": "the header's status is 0x300; the records imply 0x221"}


def name(d: Path) -> str:
    return str(d.relative_to(EVIDENCE))


def difference(now, stored, at: str = "") -> tuple[list[str], list[str]]:
    """Where two verdicts are not the same: (what the stored one has and the judge now writes otherwise or not at all;
    what the judge now writes and the stored one does not have). Lists of records are gone through record by record."""
    if isinstance(now, dict) and isinstance(stored, dict):
        changed = [f"{at}.{k}".lstrip(".") + " (not written now)" for k in stored if k not in now]
        added = [f"{at}.{k}".lstrip(".") for k in now if k not in stored]
        for k in stored:
            if k in now:
                c, a = difference(now[k], stored[k], f"{at}.{k}".lstrip("."))
                changed += c; added += a
        return changed, added
    if isinstance(now, list) and isinstance(stored, list) and len(now) == len(stored) and all(isinstance(x, dict) for x in now + stored):
        changed, added = [], []
        for x, y in zip(now, stored):
            c, a = difference(x, y, at + "[]")
            changed += c; added += a
        return changed, added
    return ([] if now == stored else [at]), []


def audit() -> dict:
    """Every run record: (the run's name) -> what was found. Made once for the tests of this file."""
    def make() -> dict:
        row_tests.the_set()                              # builds the image and writes the sets, once
        out: dict[str, dict] = {}
        for rj in sorted(EVIDENCE.rglob("run.json")):
            d = rj.parent
            rec = json.loads(rj.read_text())
            stage = rec.get("stage", "s1a")              # the first run of all was recorded before runs named their set
            home = d if (d / "result.bin").is_file() else d.with_name(d.name + "_recovered")
            one = out[name(d)] = {"stage": stage, "stop": rec.get("stop"), "own_result": home == d, "result": None}
            if not (home / "result.bin").is_file():
                continue
            raw = (home / "result.bin").read_bytes()
            stored = json.loads((home / "verdict.json").read_text())
            kept = [p for p in (d.parent / f"expected_{stage}.json", d.parent / "expected.json") if p.is_file()]
            exp = json.loads((kept[0] if kept else s1a_run.STAGES[stage]["expected"]).read_text())
            if rec.get("share"):                         # a run of one share of the census: its list, and the word that counts it
                exp = s1a_run.with_share(stage, exp, rec["share"]["index"])
            params = list(exp["params"])
            if rec.get("chain"):
                params[s1a_run.P_START] = f"{int(rec['chain']['start'], 16):08x}"
            known = s1a_run.known_for(stage)             # what the run script hands the judge of this set: the known frames, or the set's own facts
            now = s1a_run.STAGES[stage]["judge"].judge(list(struct.unpack("<%dI" % (len(raw) // 4), raw)), known, s1a_run.planned_words(dict(exp, params=params)))
            now = json.loads(json.dumps(now))
            changed, added = difference(now, stored)
            one.update(result=home / "result.bin", crc_is_the_boards=len(raw) % 4 == 0 and f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" == rec.get("board_crc32"),
                       verdict_now=now.get("verdict"), verdict_stored=stored.get("verdict"), judge_in_the_record=rec.get("judge"),
                       changed=sorted(set(changed)), added=sorted(set(added)), problems_now=now.get("problems"), problems_stored=stored.get("problems"))
        return out
    return row_tests.once("the audit of the stored evidence", make)


class EveryStoredRun(unittest.TestCase):
    def test_how_many_there_are_and_which_have_no_result(self) -> None:
        a = audit()
        self.assertEqual(len(a), 189)                         # 185 at the close of S1b; S2.0, S2.1 and two runs of S2.2 since, one of them stopped
        self.assertEqual({k for k, v in a.items() if v["result"] is None}, NEVER_PULLED)
        self.assertEqual({k for k, v in a.items() if v["result"] is not None and not v["own_result"]}, RECOVERED)
        for k in RECOVERED | NEVER_PULLED:
            self.assertTrue(a[k]["stop"], f"{k}: a run without a result of its own says in its record why")
        self.assertEqual(sum(1 for v in a.values() if v["own_result"]), 183)

    def test_no_result_or_verdict_is_stored_that_the_audit_does_not_reach(self) -> None:
        a = audit()
        reached = {v["result"] for v in a.values() if v["result"] is not None}
        self.assertEqual(set(EVIDENCE.rglob("result.bin")), reached)
        self.assertEqual({p.parent for p in EVIDENCE.rglob("verdict.json")}, {p.parent for p in reached})

    def test_every_result_is_the_one_whose_checksum_the_board_gave(self) -> None:
        for k, v in audit().items():
            if v["result"] is not None:
                self.assertTrue(v["crc_is_the_boards"], k)

    def test_no_run_is_judged_otherwise_now_than_it_was(self) -> None:
        a = audit()
        for k, v in a.items():
            if v["result"] is None:
                continue
            self.assertEqual(v["verdict_now"], v["verdict_stored"], k)
            self.assertIn(v["verdict_now"], ("PASS", "FAIL"), k)
            if v["own_result"] and v["judge_in_the_record"] is not None:
                self.assertEqual(v["judge_in_the_record"], v["verdict_now"], f"{k}: what the run script recorded of the judge")
        self.assertEqual(collections.Counter(v["verdict_now"] for v in a.values() if v["result"] is not None), {"PASS": 143, "FAIL": 44})

    def test_the_stored_verdict_is_the_judges_word_as_it_is_now_or_an_older_form_of_it(self) -> None:
        """An older form lacks fields and has nothing else: whatever a stored verdict says, the judge says now."""
        a = audit()
        older = collections.Counter()
        for k, v in a.items():
            if v["result"] is None:
                continue
            if k in ONE_PROBLEM_MORE:                        # the one exception, and only in its list of problems
                self.assertEqual(v["changed"], ["problems"], k)
                self.assertEqual([p for p in v["problems_now"] if p not in v["problems_stored"]], [ONE_PROBLEM_MORE[k]], k)
                self.assertTrue(set(v["problems_stored"]) <= set(v["problems_now"]), f"{k}: nothing that was a problem then is none now")
            else:
                self.assertEqual(v["changed"], [], f"{k}: its stored verdict says something the judge does not say now")
            self.assertTrue(set(v["added"]) <= ADDED_SINCE, (k, sorted(set(v["added"]) - ADDED_SINCE)))
            if v["changed"] or v["added"]:
                top = k.split("/")[0]
                older[top] += 1
                self.assertIn(top, OLDER_FORM, f"{k}: its stored verdict is not what the judge writes now")
        self.assertEqual(dict(older), OLDER_FORM)
        self.assertEqual(sum(1 for v in a.values() if v["result"] is not None and not v["changed"] and not v["added"]), 187 - sum(OLDER_FORM.values()))
        self.assertEqual({x for v in a.values() if v["result"] is not None for x in v["added"]}, ADDED_SINCE, "each of the additions listed is one that is met")

    def test_a_change_is_not_taken_for_an_addition(self) -> None:
        """Review of 7d7b11f: the audit let any difference in a verdict's `params` pass as "said later". The reviewer's
        case — a field an old stored verdict has, altered — and its kin, on a copy of such a verdict."""
        d = EVIDENCE / "dx_17A6_2026-11-15" / "dxw0_run03"
        stored = json.loads((d / "verdict.json").read_text())
        now = json.loads(json.dumps(stored)); now["params"]["polling_loop"] = "as before"      # what the judge writes now: one field more
        self.assertEqual(difference(now, stored), ([], ["params.polling_loop"]))
        edited = json.loads(json.dumps(stored)); edited["params"]["far_lo"] = "0xdeadbeef"
        self.assertEqual(difference(now, edited), (["params.far_lo"], ["params.polling_loop"]))
        edited = json.loads(json.dumps(stored)); edited["records"][3]["far"] = "0x00000000"; edited["records"][5]["frame_sha256"] = ["0" * 64]
        self.assertEqual(sorted(set(difference(now, edited)[0])), ["records[].far", "records[].frame_sha256"])
        edited = json.loads(json.dumps(stored)); edited["params"]["an_answer"] = 5              # something the judge never wrote
        self.assertEqual(difference(now, edited)[0], ["params.an_answer (not written now)"])
        edited = json.loads(json.dumps(stored)); del edited["records"][-1]                      # a record taken away
        self.assertEqual(difference(now, edited)[0], ["records"])
        edited = json.loads(json.dumps(stored)); edited["verdict"] = "FAIL"
        self.assertEqual(difference(now, edited)[0], ["verdict"])
        more = json.loads(json.dumps(now)); more["records"][0]["anything"] = 1                  # an addition that is not on the list
        self.assertFalse(set(difference(more, stored)[1]) <= ADDED_SINCE)

if __name__ == "__main__":
    unittest.main()

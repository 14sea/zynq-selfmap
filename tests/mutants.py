#!/usr/bin/env python3
"""Mutants: deliberate defects, one at a time, each of which the test suite must fail.

    python3 tests/mutants.py            run all of them; exit 1 if any survives
    python3 tests/mutants.py guard      run only those whose name contains "guard"

Works on a scratch copy of the tree, so the working tree is never dirtied. A mutant counts as killed
only if the suite ran (Ran N > 0) and reported FAILED. Mutants are written so that they still compile:
a build error is not a test.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE, JUDGE, RUN, JUDGE2 = "prober/sm_core.c", "host/s1a_judge.py", "host/s1a_run.py", "host/s1b0_judge.py"

MUTANTS = [
    # ---- the prober: generator and guard
    (CORE, "the generator sends WCFG", "    out[i++] = CMD_RCFG;", "    out[i++] = 0x00000001u;"),
    (CORE, "the guard accepts any CMD value", "            else if (v != CMD_DESYNC)\n                return REFUSE(i + 1u, 5u);", "            "),
    (CORE, "the guard ignores the envelope", "            if (v < far_lo || v > far_hi)\n                return REFUSE(i + 1u, 7u);", "            if (v < far_lo && v > far_hi)\n                return REFUSE(i + 1u, 7u);"),
    (CORE, "the guard allows any read length", "v == 0u || v > max_read ||", "v == 0u || (v > max_read && v == 0u) ||"),
    # ---- the prober: one DMA command
    (CORE, "no clear before a command", "    hal_wr(DEVCFG_INT_STS, STS_CLEAR_MASK);\n    s = hal_rd(DEVCFG_INT_STS);", "    s = hal_rd(DEVCFG_INT_STS) & ~STS_CLEAR_MASK;"),
    (CORE, "the clear is not verified", "    if (s & STS_CLEAR_MASK)\n        return C_STALE;", ""),
    (CORE, "the clear also clears PCFG_DONE", "    hal_wr(DEVCFG_INT_STS, STS_CLEAR_MASK);", "    hal_wr(DEVCFG_INT_STS, STS_CLEAR_MASK | 4u);"),
    (CORE, "PCFG_DONE not checked before queuing", "    if (!(s & STS_PCFG_DONE))\n        return C_DONE_DROPPED;\n    hal_wr(DEVCFG_DMA_SRC, src);", "    hal_wr(DEVCFG_DMA_SRC, src);"),
    (CORE, "PCFG_DONE not checked while polling", "        if (!(s & STS_PCFG_DONE))\n            return C_DONE_DROPPED;\n        if (s & STS_D_P_DONE)", "        if (s & STS_D_P_DONE)"),
    (CORE, "SRC and DST written in the wrong order", "    hal_wr(DEVCFG_DMA_SRC, src);\n    hal_wr(DEVCFG_DMA_DST, dst);", "    hal_wr(DEVCFG_DMA_DST, dst);\n    hal_wr(DEVCFG_DMA_SRC, src);"),
    (CORE, "the wait is on DMA_DONE, not D_P_DONE", "        if (s & STS_D_P_DONE)\n            return C_OK;", "        if (s & 0x00002000u)\n            return C_OK;"),
    (CORE, "error bits are not checked", "        if (s & STS_ERR_MASK)\n            return C_DEVERR;", ""),
    (CORE, "the poll limit is ignored below 5000", "        if (n >= poll_limit)", "        if (n >= poll_limit && n >= 5000u)"),
    # ---- the prober: gates and the S1a loop
    (CORE, "no data-cache gate", "    if (hal_cpu(CPU_SCTLR) & 0x4u)", "    if (0)", 1),
    (CORE, "stage 2: no data-cache gate", "    if (hal_cpu(CPU_SCTLR) & 0x4u)", "    if (0)", 0),
    (CORE, "no loopback gate", "    if (v & MCTRL_PCAP_LPBK)", "    if (0)", 1),
    (CORE, "stage 2: no loopback gate", "    if (v & MCTRL_PCAP_LPBK)", "    if (0)", 0),
    (CORE, "stage 2: no PCFG_DONE gate", "    if (!(v & STS_PCFG_DONE))\n        return finish2(S_GATE_NOT_DONE", "    if (0)\n        return finish2(S_GATE_NOT_DONE"),
    (CORE, "no PCFG_DONE gate", "    if (!(v & STS_PCFG_DONE))\n        return finish(S_GATE_NOT_DONE", "    if (0)\n        return finish(S_GATE_NOT_DONE"),
    (CORE, "no CTRL gate", "    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)", "    if (0)", 1),
    (CORE, "stage 2: no CTRL gate", "    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)", "    if (0)", 0),
    (CORE, "no sentinel prefill", "        hal_mem_wr(DST_BUF + 4u * i, SENTINEL);", "        (void)0;", 0),
    (CORE, "stage 2: no sentinel prefill of the data", "        hal_mem_wr(DST_BUF + 4u * i, SENTINEL);", "        (void)0;", 1),
    (CORE, "stage 2: no sentinel before the FAR read", "        hal_mem_wr(DST_BUF, SENTINEL);", "        (void)0;"),
    (CORE, "the health check always passes", "            v = (code == C_OK && same_frame(0u, rec)) ? 1u : 0u;\n            res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);\n            rec++;\n            if (!v)\n                return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);\n            if (anomalies > budget)", "            v = 1u;\n            res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);\n            rec++;\n            if (!v)\n                return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);\n            if (anomalies > budget)"),
    (CORE, "no anomaly budget", "            if (anomalies > budget)", "            if (0)", 1),
    (CORE, "stage 2: no anomaly budget", "            if (anomalies > budget)", "            if (0)", 0),
    (CORE, "a repeat that differs is not noticed", "                if (first != 0xFFFFFFFFu && !same_frame(first, rec)) {", "                if (first != 0xFFFFFFFFu && !same_frame(first, rec) && far == 0xFFFFFFFFu) {"),
    (CORE, "the pad is not checked", "                code = C_PAD_NONZERO;", "                code = C_OK;", 0),
    (CORE, "a frame outside the envelope is accepted in the parameters", "        if (v < far_lo || v > far_hi)\n            return finish(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);", ""),
    (CORE, "a PL read is added", "    put(\"SM1 start\\r\\n\");", "    put(\"SM1 start\\r\\n\"); (void)hal_rd(0x43C00000u);"),
    (CORE, "an SLCR write is added", "    put(\"SM1 start\\r\\n\");", "    put(\"SM1 start\\r\\n\"); hal_wr(0xF8000008u, 0xDF0Du);"),
    (CORE, "the cleanup stream is skipped", "        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, CLEANUP_WORDS, 0u, poll_limit, &sts, &polls);", "        code = C_OK;", 0),
    (CORE, "stage 2: the cleanup stream is skipped", "        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, CLEANUP_WORDS, 0u, poll_limit, &sts, &polls);", "        code = C_OK;", 1),
    (CORE, "the final reference read is not compared", "    v = (code == C_OK && same_frame(0u, rec)) ? 1u : 0u;\n    res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);\n    rec++;\n    if (!v)\n        return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);\n    return finish(S_DONE", "    v = 1u;\n    res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);\n    rec++;\n    if (!v)\n        return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);\n    return finish(S_DONE"),
    # ---- the prober: the guard's rules for stage 2
    (CORE, "the guard accepts a read that is not a pad plus whole frames", "            if (v == 0xFFFFFFFFu || v < 2u)", "            if (v < 2u)"),
    (CORE, "the guard lets a read run past the envelope", "            if (v - 2u > far_hi - far_value)", "            if (0)"),
    (CORE, "the guard accepts a one-word read of any register", "        } else if (x == W_RD_FAR_1) {", "        } else if ((x & 0xF8001FFFu) == 0x28000001u) {"),
    (CORE, "the guard allows a second read on an address that has moved on", "            far = 0;                                    /* the register has moved on: another read needs a new, checked address */\n", ""),
    ("host/packets.py", "reader: a second read on an address that has moved on is accepted", "                far = False                              # the register has moved on: another read needs a new, checked address\n", ""),
    (RUN, "run: a result of another stage's layout is not saved whole", "        layouts = {(m[\"judge\"].HDR, m[\"judge\"].REC): name for name, m in STAGES.items()}", "        layouts = {(J.HDR, J.REC): stage}"),
    (RUN, "run: another stage's result is not called a problem", "            if fits != stage:", "            if False:"),
    (RUN, "run: a missing result header is taken at its word for the size", "        if has_header and fits and n <=", "        if fits and n <="),
    (CORE, "the guard's range check adds to the address and can wrap", "            if (v - 2u > far_hi - far_value)", "            if (far_value + (v - 2u) > far_hi)"),
    (CORE, "stage 2: the parameter range check adds to the address and can wrap", " || n - 1u > far_hi - far)", " || far + (n - 1u) > far_hi)"),
    (RUN, "run: the dry run does not list the YMODEM branch", "            if \"card_or_ymodem\" in s:                 # the branch taken when the card has no file of that size", "            if False:"),
    # ---- the prober: stage 2
    (CORE, "stage 2: the FAR register is not read", "        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, FARRD_WORDS, 0u, poll_limit, &sts, &polls);", "        code = C_OK;"),
    (CORE, "stage 2: a repeat's data is not compared", "                    if (!same_data(first, rec, n))", "                    if (0)"),
    (CORE, "stage 2: a repeat's FAR value is not compared", "                    else if (r2_rd(first, REC2_FARBLK + F_VALUE) != r2_rd(rec, REC2_FARBLK + F_VALUE))", "                    else if (0)"),
    (CORE, "stage 2: an unread FAR is not noticed", "    if (code == C_OK && r2_rd(rec, REC2_FARBLK + F_UNREAD))", "    if (0)"),
    (CORE, "stage 2: the reference's FAR value is not part of its health", "    return (code == C_OK && same_data(0u, rec, 1u)\n            && r2_rd(rec, REC2_FARBLK + F_VALUE) == r2_rd(0u, REC2_FARBLK + F_VALUE)) ? 1u : 0u;", "    return (code == C_OK && same_data(0u, rec, 1u)) ? 1u : 0u;"),
    (CORE, "stage 2: an operation running past the envelope is accepted", " || n - 1u > far_hi - far)", ")"),
    (CORE, "stage 2: more frames per read than the buffer holds", "        if (n == 0u || n > MAX_READ_FRAMES || far < far_lo", "        if (n == 0u || n > 15u || far < far_lo"),
    (CORE, "stage 2: only the first frame of a repeat is compared", "    for (i = FRAME_WORDS; i < FRAME_WORDS * (n + 1u); i++)", "    for (i = FRAME_WORDS; i < FRAME_WORDS * 2u && n; i++)"),
    (CORE, "stage 2: the pad is not checked", "            if (r2_rd(rec, REC2_DATA + i) != 0u) {", "            if (0) {"),
    # ---- the judge of stage 2
    (JUDGE2, "judge2: the FAR values need not follow one rule", "    elif deltas:\n        bad(", "    elif False:\n        bad("),
    (JUDGE2, "judge2: only the first frame of a read is compared with the known frames", "        for j, frame in enumerate(rec[\"frames\"]):", "        for j, frame in enumerate(rec[\"frames\"][:1]):"),
    (JUDGE2, "judge2: the echoed parameters are not compared with the planned ones", "    if list(par) != list(planned):", "    if False:"),
    (JUDGE2, "judge2: a repeat's FAR value is not derived", "                elif first_clean[op][\"far_value\"] != fb[4]:", "                elif False:"),
    (JUDGE2, "judge2: a repeat's data is not derived", "                if first_clean[op][\"frames\"] != rec[\"frames\"]:", "                if False:"),
    (JUDGE2, "judge2: the unused tail is not checked", "        if any(tail):", "        if False:"),
    (JUDGE2, "judge2: the FAR read stream is not compared with the pinned one", "(\"FAR read stream\", r[59:63], FARRD)", "(\"FAR read stream\", r[59:63], r[59:63])"),
    (JUDGE2, "judge2: the reference's health ignores the FAR value", " and rec[\"far_value\"] == recs[0][\"far_value\"]", ""),
    (JUDGE2, "judge2: the FAR value and its unread flag are not held together", "        if fb[5] != unread or (not far_read_attempted and fb[4]):", "        if False:"),
    (JUDGE2, "judge2: the order of records is not checked", "        if (rec[\"kind\"], rec[\"far\"], rec[\"n\"], rec[\"repeat\"], rec[\"op\"]) != (kind, far, m, repeat, op):", "        if False:"),
    (JUDGE2, "judge2: the code is not compared with the derivation", "        if code != derived and not (code == 0x23 and derived in (0, 0x10, 0x11, 0x12, 0x13, 0x14)):", "        if False:"),
    (JUDGE2, "judge2: an unread FAR is not derived", "            elif unread:\n                derived = 0x14", "            elif False:\n                derived = 0x14"),
    (RUN, "run: stage 2 is judged by the judge of stage 1", "    J, tag = STAGES[stage][\"judge\"], STAGES[stage][\"tag\"]", "    J, tag = STAGES[\"s1a\"][\"judge\"], STAGES[stage][\"tag\"]"),
    # ---- the judge
    (JUDGE, "judge: a nonzero pad is not derived", "            elif any(rec[\"pad\"]):", "            elif False:"),
    (JUDGE, "judge: sentinel survivors are not derived", "            if survivors:\n                derived = 0x10", "            if False:\n                derived = 0x10"),
    (JUDGE, "judge: a differing repeat is not derived", "            elif rec[\"kind\"] == 0 and far in first_clean and first_clean[far] != rec[\"frame\"]:", "            elif False:"),
    (JUDGE, "judge: the code is not compared with the derivation", "        if code != derived and not (code == 0x23 and derived in (0, 0x10, 0x11, 0x12)):", "        if False:"),
    (JUDGE, "judge: the order of records is not checked", "        if (rec[\"kind\"], rec[\"far\"], rec[\"repeat\"]) != (kind, far, repeat):", "        if False:"),
    (JUDGE, "judge: missing records are not noticed", "        if i >= n:\n            bad(f\"the records end at {n};", "        if i >= n:\n            (lambda *_: None)(f\"the records end at {n};"),
    (JUDGE, "judge: the anomaly count is not cross-checked", "        if anomalies != implied[1]:", "        if False:"),
    (JUDGE, "judge: the status is not cross-checked", "        if status != implied[0]:", "        if False:"),
    (JUDGE, "judge: the stop record is not cross-checked", "        if stop_record != implied[2]:", "        if False:"),
    (JUDGE, "judge: a frame differing from the known one passes", "            if code == 0 and not matches:", "            if False:"),
    # Not listed: "recorded streams are not held to the policy". In the judge that check is redundant by construction
    # — a stream that passes the pinned-words comparison with its frame address inside the envelope always passes the
    # policy — so removing it cannot be observed. It stays as a second, independently written reading; the policy
    # itself is tested in test_prober_packets.py.
    (JUDGE, "judge: recorded streams are not compared with the pinned words", "        if rec[\"stream\"] != pinned_stream(far):", "        if False:"),
    (JUDGE, "judge: the survivor count is not recounted", "        if survivors != rec[\"survivors\"]:", "        if False:"),
    (JUDGE, "judge: trailing words are accepted", "    if len(words) != total:", "    if len(words) < total:"),
    (JUDGE, "judge: an incomplete run can pass", "    if status != 1:\n        bad(f\"the run did not complete: status {status:#x}\")", "    if False:\n        bad(f\"the run did not complete: status {status:#x}\")"),
    (JUDGE, "judge: the echoed parameters are not compared with the planned ones", "    if list(par) != list(planned):", "    if False:"),
    (JUDGE, "judge: gate readings that fail a gate are accepted on a run that went on", "    if failing:\n        bad(f\"the readings in the header fail", "    if False:\n        bad(f\"the readings in the header fail"),
    (JUDGE, "judge: a gate stop is not held to its own readings", "        if failing != status:", "        if False:"),
    (JUDGE, "judge: the final INT_STS is not judged", "    if status == 1 and (not sts1 & PCFG_DONE or sts1 & ERR_MASK):", "    if False:"),
    (JUDGE, "judge: the data-cache reading is not a gate", "else 0x103 if not sts0 & PCFG_DONE else 0x104 if sctlr & SCTLR_C else 0)", "else 0x103 if not sts0 & PCFG_DONE else 0)"),
    (JUDGE, "judge: reserved header words are not checked", "    if any(words[19:32]):", "    if False:"),
    (JUDGE, "judge: reserved record words are not checked", "        if r[14] or r[15]:", "        if False:"),
    (JUDGE, "judge: a file length that is not a multiple of four is rounded down", "    if len(raw) % 4:", "    if False:"),
    # ---- the run script
    (RUN, "run: a card copy of the PL design of the wrong size is used", "                if not m or int(m.group(1)) != s[\"size\"]:            # not on the card (or not this size): send it", "                if not m:"),
    (RUN, "run: the image is not re-checked after the run", "        if not m or m.group(1) != exp[\"image_crc32\"]:", "        if not m:"),
    (RUN, "run: the judge is given the echoed parameters as the plan", "        verdict = J.judge(words, known, [int(w, 16) for w in exp[\"params\"]])", "        verdict = J.judge(words, known, words[32:64])"),
    (RUN, "run: the live status afterwards is only recorded", "        if not live or not live[0] & J.PCFG_DONE or live[0] & J.ERR_MASK:", "        if False:"),
    (RUN, "run: the card copy is not read back", "            if not record[\"card_verified\"]:", "            if False:"),
    (RUN, "run: the card read-back checksum is not compared", "and bool(m2) and m2.group(1) == record[\"board_crc32\"]", "and bool(m2)"),
    (RUN, "run: an unconfirmed card write is ignored", "        if not record[\"card_written\"]:", "        if False:"),
    (RUN, "run: a short card write is accepted", "        record[\"card_written\"] = bool(m) and int(m.group(1)) == nbytes", "        record[\"card_written\"] = bool(m)"),
    (RUN, "run: the pulled copy is not compared with the board", "        if len(words) != total or host_crc != record[\"board_crc32\"]:", "        if False:"),
    (RUN, "run: the return code is not compared with the result", "        if record[\"return_code\"] != verdict.get(\"expected_return_code\"):", "        if False:"),
    (RUN, "run: a wrong crc32 before go is accepted", "                if not m or m.group(1) != s[\"crc\"]:", "                if not m:"),
    (RUN, "run: the PCFG_DONE bit is not checked before go", "                if not w or bool(w[0] >> s[\"bit\"][0] & 1) != s[\"bit\"][1]:", "                if not w:"),
    (RUN, "run: the cache state is not checked before go", "            if \"expect\" in s and not re.search(s[\"expect\"], text):", "            if False:"),
    (RUN, "run: the result size is taken as the clean size", "        n, total = hdr[3], hdr[5]", "        n, total = 11, 64 + 11 * 266"),
    (RUN, "run: PASS without the judge", "    record[\"verdict\"] = \"PASS\" if record.get(\"judge\") == \"PASS\" and not problems else \"FAIL\"", "    record[\"verdict\"] = \"PASS\" if not problems else \"FAIL\""),
]


def suite(tree: Path) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=tree, capture_output=True, text=True)
    out = r.stdout + r.stderr
    ran = re.search(r"^Ran (\d+) tests", out, re.M)
    res = re.findall(r"^(OK|FAILED.*)$", out, re.M)
    failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", out, re.M)))
    n = int(ran.group(1)) if ran else 0
    summary = f"Ran {n} {res[-1] if res else 'no result'}; {len(failed)} test(s): {', '.join(f[5:48] for f in failed[:2])}"
    return n > 0 and bool(res) and res[-1].startswith("FAILED"), summary


def main() -> int:
    tree = Path(tempfile.mkdtemp(prefix="selfmap_mutants_")) / "tree"
    shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__", "prober", "ret2uboot", "board_*", "sdcard"))
    for sub in ("prober", "probes/ret2uboot"):
        shutil.copytree(ROOT / sub, tree / sub, dirs_exist_ok=True)
    killed, summary = suite(tree)
    print(f"unmutated: {summary}")
    if killed:
        print("the unmutated tree fails; nothing below would mean anything"); return 2
    survivors = 0
    only = sys.argv[1] if len(sys.argv) > 1 else ""       # an optional substring: run just the mutants whose name contains it
    for path, name, old, new, *which in MUTANTS:
        if only not in name:
            continue
        f = tree / path; original = f.read_text()
        want = which[0] + 1 if which else 1          # an optional fifth element picks one occurrence of several
        if original.count(old) < want or (not which and original.count(old) != 1):
            print(f"STALE    {name}: its anchor occurs {original.count(old)} times in {path}"); survivors += 1; continue
        at = -1
        for _ in range(want):
            at = original.index(old, at + 1)
        f.write_text(original[:at] + new + original[at + len(old):])
        killed, summary = suite(tree)
        f.write_text(original)
        survivors += not killed
        print(f"{'KILLED  ' if killed else 'SURVIVED'} {name:62s} {summary}")
    killed, summary = suite(tree)
    print(f"restored: {summary}")
    print(f"{sum(1 for m in MUTANTS if only in m[1])} mutants, {survivors} survived")
    shutil.rmtree(tree.parent, ignore_errors=True)
    return 1 if survivors or killed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Mutants: deliberate defects, one at a time, each of which the test suite must fail.

    python3 tests/mutants.py            run all of them; exit 1 if any survives (or does not build: BROKEN)
    python3 tests/mutants.py guard      run only those whose name contains "guard"

Works on scratch copies of the tree (SM_MUTANT_JOBS of them, 8 by default, one mutant at a time in each),
so the working tree is never dirtied. A mutant counts as killed
only if the suite ran (Ran N > 0) and reported FAILED. Mutants are written so that they still compile:
a build error is not a test.
"""
from __future__ import annotations

import concurrent.futures
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE, JUDGE, RUN, JUDGE2 = "prober/sm_core.c", "host/s1a_judge.py", "host/s1a_run.py", "host/s1b0_judge.py"
JUDGE4, GRADE = "host/s1b1_judge.py", "host/grade_s1b1.py"

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
    (CORE, "stage 2: no PCFG_DONE gate", "    if (!(v & STS_PCFG_DONE))\n        return finish2(S_GATE_NOT_DONE", "    if (0)\n        return finish2(S_GATE_NOT_DONE", 0),
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
    (CORE, "the guard accepts a read that is not a pad plus whole frames", "            if (v == 0xFFFFFFFFu)", "            if (0)"),
    (CORE, "the guard lets a read run past the envelope", "            if (v >= 2u && v - 2u > far_hi - far_value)", "            if (v >= 2u && far_value > far_hi)"),      # never true here; "if (0)" would not compile (unused variable) and a build error is not a kill
    (CORE, "the guard accepts a one-word read of any register", "        } else if (x == W_RD_FAR_1) {", "        } else if ((x & 0xF8001FFFu) == 0x28000001u) {"),
    (CORE, "the guard allows a second read on an address that has moved on", "            far = 0;                                    /* the register has moved on: another read needs a new, checked address */\n", ""),
    ("host/packets.py", "reader: a second read on an address that has moved on is accepted", "                far = False                              # the register has moved on: another read needs a new, checked address\n", ""),
    (RUN, "run: a result of another stage's layout is not saved whole", "        having = layouts.get((hdr[7], hdr[6]), [])", "        having = [stage] if (hdr[7], hdr[6]) == (J.HDR, J.REC) else []"),
    (RUN, "run: another stage's result is not called a problem", "            if fits != stage:", "            if False:"),
    (RUN, "run: a missing result header is taken at its word for the size", "        if has_header and fits and n <=", "        if fits and n <="),
    (CORE, "the guard's range check adds to the address and can wrap", "            if (v >= 2u && v - 2u > far_hi - far_value)", "            if (v >= 2u && far_value + (v - 2u) > far_hi)"),
    (CORE, "stage 2: the parameter range check adds to the address and can wrap", " || n - 1u > far_hi - far)", " || far + (n - 1u) > far_hi)"),
    (RUN, "run: the dry run does not list the YMODEM branch", "            if \"card_or_ymodem\" in s:                 # the branch taken when the card has no file of that size", "            if False:"),
    # ---- the prober: stage 2
    (CORE, "stage 2: the FAR register is not read", "        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, FARRD_WORDS, 0u, poll_limit, &sts, &polls);", "        code = C_OK;"),
    (CORE, "stage 2: a repeat's data is not compared", "                    if (!same_data(first, rec, n))", "                    if (0)"),
    (CORE, "stage 2: a repeat's FAR value is not compared", "                    else if (r2_rd(first, REC2_FARBLK + F_VALUE) != r2_rd(rec, REC2_FARBLK + F_VALUE))", "                    else if (0)"),
    (CORE, "stage 2: an unread FAR is not noticed", "    if (code == C_OK && r2_rd(rec, REC2_FARBLK + F_UNREAD))", "    if (0)"),
    (CORE, "stage 2: the reference's FAR value is not part of its health", "    return (code == C_OK && same_data(0u, rec, 1u)\n            && r2_rd(rec, REC2_FARBLK + F_VALUE) == r2_rd(0u, REC2_FARBLK + F_VALUE)) ? 1u : 0u;", "    return (code == C_OK && same_data(0u, rec, 1u)) ? 1u : 0u;"),
    (CORE, "stage 2: an operation running past the envelope is accepted", " || n - 1u > far_hi - far)", ")"),
    (CORE, "stage 2: more frames per read than the buffer holds", "        if (n == 0u || n > MAX_READ_FRAMES || n - 1u", "        if (n == 0u || n > 14u || n - 1u"),
    (CORE, "stage 2: only the first frame of a repeat is compared", "    for (i = FRAME_WORDS; i < FRAME_WORDS * (n + 1u); i++)", "    for (i = FRAME_WORDS; i < FRAME_WORDS * 2u && n; i++)"),
    (CORE, "stage 2: the pad is not checked", "            if (r2_rd(rec, REC2_DATA + i) != 0u) {", "            if (0) {"),
    # ---- the judge of stage 2
    (JUDGE2, "judge2: the FAR values need not follow one rule", "        elif deltas:\n            bad(", "        elif False:\n            bad("),
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
    (RUN, "run: stage 2 is judged by the judge of stage 1", "    J = STAGES[stage][\"judge\"]", "    J = STAGES[\"s1a\"][\"judge\"]"),
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
    (RUN, "run: the return code is not compared with the result", "        if record[\"return_code\"] != verdict.get(\"expected_return_code\"):", "        if False:"),
    (RUN, "run: a wrong crc32 before go is accepted", "                if not m or m.group(1) != s[\"crc\"]:", "                if not m:"),
    (RUN, "run: the PCFG_DONE bit is not checked before go", "                if not w or bool(w[0] >> s[\"bit\"][0] & 1) != s[\"bit\"][1]:", "                if not w:"),
    (RUN, "run: the cache state is not checked before go", "            if \"expect\" in s and not re.search(s[\"expect\"], text):", "            if False:"),
    (RUN, "run: the result size is taken as the clean size", "        n, total = hdr[3], hdr[5]", "        n, total = 11, 64 + 11 * 266"),
    (RUN, "run: PASS without the judge", "    record[\"verdict\"] = \"PASS\" if record.get(\"judge\") == \"PASS\" and not problems else \"FAIL\"", "    record[\"verdict\"] = \"PASS\" if not problems else \"FAIL\""),
    # ---- stage 3 (S1b.0b): the pad alone, and no read at all
    (CORE, "stage 3: asked to read nothing, the generator still reads", "    if (n_frames == N_NONE) {", "    if (0) {"),
    (CORE, "stage 3: an operation that reads nothing still queues a read command", "    if (code == C_OK && words != 0u) {                  /* with nothing", "    if (code == C_OK) {                  /* with nothing"),
    (CORE, "stage 3: the pad of a pad-only read is not checked", "    if (code == C_OK && words != 0u) {\n        for (i = 0; i < FRAME_WORDS; i++)", "    if (code == C_OK && words > FRAME_WORDS) {\n        for (i = 0; i < FRAME_WORDS; i++)"),
    (CORE, "stage 3: stage 2 accepts the new operations too", "        if (stage3 && (n == 0u || n == N_NONE))", "        if ((stage3 || 1) && (n == 0u || n == N_NONE))"),   # keeps the variable used: it has to build
    (CORE, "stage 3: the pad alone or no read may be asked for outside the envelope", "        if (far < far_lo || far > far_hi)\n            return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);\n        if (stage3", "        if (stage3"),
    (CORE, "stage 3: repeats of an operation that reads nothing are compared over words that were never read", "    if (n == N_NONE)\n        return 1; ", "    if (0)\n        return 1; "),
    (JUDGE2, "judge3: a read status in an operation that reads nothing goes unnoticed", "                if sts or polls:\n                    bad(f\"record {i}: a frame read transfer has a status", "                if False:\n                    bad(f\"record {i}: a frame read transfer has a status"),
    (JUDGE2, "judge3: the same read at the same address may leave different values", "            if len(values) != 1:", "            if False:"),
    (JUDGE2, "judge3: the stage is taken from the result instead of from what was run", "    if (par[0], par[1], par[2]) != (0x31504D53, 1, stage)", "    if (par[0], par[1]) != (0x31504D53, 1)"),
    (JUDGE2, "judge3: the length rule is reported as holding whatever was seen", "        if any(s != {w // FRAME} for w, s in steps.items()):", "        if False:"),
    (JUDGE2, "judge3: undetermined is reported as holding", "            out[\"one_step_per_frame_of_words\"] = None if missing else True", "            out[\"one_step_per_frame_of_words\"] = True"),
    (JUDGE2, "judge2/3: FAR values from records with another anomaly are left out of the finding", "        if rec[\"far_measured\"]:", "        if rec[\"far_measured\"] and code == 0:"),
    (JUDGE2, "judge2/3: a FAR value counts although its read failed", "        rec[\"far_measured\"] = far_read_done and not unread", "        rec[\"far_measured\"] = True"),
    (JUDGE2, "judge3: an anomalous record counts as clean evidence for the length rule", "if rec[\"far_measured\"] and rec[\"code\"] == 0}", "if rec[\"far_measured\"]}"),
    (JUDGE2, "judge3: the table does not say which of its records were anomalous", "for k in where if recs[k][\"code\"] != 0}", "for k in where if False}"),
    (RUN, "run: stage 3 is judged by the judge of stage 2", "\"s1b0b\": {\"judge\": s1b0b_judge,", "\"s1b0b\": {\"judge\": s1b0_judge,"),
    (RUN, "run: only the console lines of the stage asked for are kept", "if re.match(r\"SM\\d \", ln.strip())]", "if ln.strip().startswith(\"SM3 \" if stage == \"s1b0b\" else \"SM2 \" if stage == \"s1b0\" else \"SM1 \")]"),
    # ---- stage 4 (S1b.1): the walk
    (CORE, "stage 4: no data-cache gate", "    if (hal_cpu(CPU_SCTLR) & 0x4u)", "    if (0)", 2),
    (CORE, "stage 4: no loopback gate", "    if (v & MCTRL_PCAP_LPBK)", "    if (0)", 2),
    (CORE, "stage 4: no PCFG_DONE gate", "    if (!(v & STS_PCFG_DONE))\n        return finish2(S_GATE_NOT_DONE", "    if (0)\n        return finish2(S_GATE_NOT_DONE", 1),
    (CORE, "stage 4: no CTRL gate", "    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)", "    if (0)", 2),
    (CORE, "stage 4: the walk reads at an address the device named outside the envelope", "            if (next > c.far_hi) {", "            if (0 && next > c.far_hi) {"),
    (CORE, "stage 4: an address below the envelope is not taken as a stop", "            if (next <= cur)   ", "            if (next <= cur && next >= c.far_lo)   "),
    (CORE, "stage 4: the stop record of a walk that does not advance is counted back from the end", "finish2(S_STOP_STUCK, c.rec, c.anomalies, k);", "finish2(S_STOP_STUCK, c.rec, c.anomalies, c.rec - 2u);"),
    (CORE, "stage 4: the walk follows an address that does not advance", "            if (next <= cur)   ", "            if (next < cur && 0)   "),
    (CORE, "stage 4: a step backwards is followed", "            if (next <= cur)   ", "            if (next == cur)   "),
    (CORE, "stage 4: the limit of frames is not applied", "            if (count >= limit) {", "            if (count >= limit && 0) {"),
    (CORE, "stage 4: the next address is computed instead of taken from the device", "            cur = next;", "            cur = cur + 1u;"),
    (CORE, "stage 4: the successor read reads the frame as well", "walk_op(&c, cur, 0u, pass, OP_SUCC, 0u);", "walk_op(&c, cur, 1u, pass, OP_SUCC, 0u);"),
    (CORE, "stage 4: a later pass is not compared with the first", "    if (code == C_OK && op != OP_TRIPLE && pass != 0u) {", "    if (0 && op != OP_TRIPLE && pass != 0u) {"),
    (CORE, "stage 4: a later pass may be told another address", "        if (first == NO_REC || r2_rd(first, REC2_FARBLK + F_VALUE) != r2_rd(me, REC2_FARBLK + F_VALUE))", "        if (first == NO_REC)"),
    (CORE, "stage 4: a later pass may deliver another frame", "        else if (!same_data(first, me, n))", "        else if (0 && !same_data(first, me, n))"),
    (CORE, "stage 4: the three-frame read is not compared with the single reads", "    if (code == C_OK && op == OP_TRIPLE) {", "    if (0 && op == OP_TRIPLE) {"),
    (CORE, "stage 4: only the first of the three frames is compared", "        for (j = 0u; j < n && code == C_OK; j++) {", "        for (j = 0u; j < 1u && code == C_OK; j++) {"),
    (CORE, "stage 4: the walk goes on after an anomaly", "    return S_STOP_WALK | code;", "    return 0u;"),
    (CORE, "stage 4: the reference is not read during the run", "    if (c->since + n > c->every && !health4(c, KIND_HEALTH, pass)) {", "    if (0 && c->since + n > c->every && !health4(c, KIND_HEALTH, pass)) {"),
    (CORE, "stage 4: a changed reference frame during the run is ignored", "    if (c->since + n > c->every && !health4(c, KIND_HEALTH, pass)) {", "    if (c->since + n > c->every && !health4(c, KIND_HEALTH, pass) && 0) {"),
    (CORE, "stage 4: the frames delivered since the reference are not counted", "    c->since += n;", "    c->since += 0u;"),
    (CORE, "stage 4: the count since the reference starts again with each pass", "        cur = start; count = 0u;", "        cur = start; count = 0u; c.since = 0u;"),
    (CORE, "stage 4: the reads of several frames are not counted towards the reference", "        status = due(&c, n, passes);", "        status = due(&c, 0u, passes);"),
    (CORE, "stage 4: a reference read does not start the count again", "    c->since = 0u;\n    return v;", "    return v;"),
    (CORE, "stage 4: one or two frames left over are not read again", "            if (n0 >= 3u)\n                i = n0 - 3u;", "            if (n0 >= 3u)\n                break;"),
    (CORE, "stage 4: a walk of two frames gets no second path", "            else if (n0 == 2u)\n                n = 2u;", "            else if (n0 == 2u)\n                break;"),
    (CORE, "stage 4: a reference interval too short for a read of three frames is taken", "c.every < MAX_READ_FRAMES", "c.every == 0u"),
    (CORE, "stage 4: the final reference read is ignored", "    if (!health4(&c, KIND_FINAL, passes))", "    if (!health4(&c, KIND_FINAL, passes) && 0)"),
    (CORE, "stage 4: more passes than the header has room for", "passes > MAX_PASSES", "passes > 3u"),
    (CORE, "stage 4: a start outside the envelope is taken", "        || par(P_N_FARS) != 1u || start < c.far_lo || start > c.far_hi", "        || par(P_N_FARS) != 1u"),
    (CORE, "stage 4: a limit above what the result area holds", "limit > MAX_WALK", "limit > 200u"),
    (JUDGE4, "judge4: a later pass may name another address", "                    if first is None or first[\"far_value\"] != rec[\"far_value\"]:", "                    if first is None:"),
    (JUDGE4, "judge4: a later pass may deliver another frame", "                    elif first[\"frames\"] != rec[\"frames\"]:", "                    elif False:"),
    (JUDGE4, "judge4: the three-frame read is not compared", "            if derived == 0 and any(rec[\"frames\"][j] != first_pass[at + j][\"content\"][\"frames\"][0] for j in range(m)):", "            if False:"),
    (JUDGE4, "judge4: only two of the three frames are compared", "first_pass[at + j][\"content\"][\"frames\"][0] for j in range(m)):", "first_pass[at + j][\"content\"][\"frames\"][0] for j in range(m - 1)):"),
    (JUDGE4, "judge4: the register after a frame is not checked against the next address named", "                if s[\"content\"][\"far_value\"] != named[s[\"next\"]]:", "                if False:"),
    (JUDGE4, "judge4: the known frames are not compared", "            if far in frames_known and frame != frames_known[far]:", "            if False:"),
    (JUDGE4, "judge4: the reference frame is not held to its known value", "        against_known(rec, [ref])", "        pass"),
    (JUDGE4, "judge4: the baseline is not held to the known value", "        against_known(base, [ref])", "        pass"),
    (JUDGE4, "judge4: the frames of the walk are not held to their known values", "            against_known(pair[1], [cur])", "            pass"),
    (JUDGE4, "judge4: frames delivered in a read of several are not held to their known values", "            against_known(rec, [first_pass[at + j][\"far\"] for j in range(m)])", "            pass"),
    (JUDGE4, "judge4: a record of another shape than the schedule has is followed", "            return None\n        return rec", "            return rec\n        return rec"),
    (JUDGE4, "judge4: the register after a read of several frames is not checked", "                if rec[\"far_value\"] != want:", "                if False:"),
    (JUDGE4, "judge4: an address below the envelope is not taken as a stop", "            if nxt <= cur:  ", "            if nxt <= cur and nxt >= lo:  "),
    (JUDGE4, "judge4: one or two frames left over need not be read again", "                if n0 >= 3:\n                    at = n0 - 3", "                if n0 >= 3:\n                    break"),
    (JUDGE4, "judge4: a reference interval too short for a read of three frames is a valid parameter", "or every < 3 or", "or every == 0 or"),
    (JUDGE4, "judge4: the reference reads count frames per pass, not over the run", "        since[\"frames\"] = 0\n        settle(rec, rec[\"own\"])", "        settle(rec, rec[\"own\"])"),
    (GRADE, "grade: a walk that did not finish is compared as if it were the column", "    if ended != LEFT:", "    if ended == LIMIT:"),
    (GRADE, "grade: a walk at its limit is compared as if it were the column", "    if ended != LEFT:", "    if False:"),
    (GRADE, "grade: the judge's verdict is not carried over", "    if verdict.get(\"verdict\") != \"PASS\":", "    if False:"),
    (JUDGE4, "judge4: leaving the envelope without the known frames is fine", "    if status == 1 and missing and ends and ends[0][1] == 1:", "    if False:"),
    (JUDGE4, "judge4: the header's account of the walk is not checked", "        if got != want:\n            bad(f\"pass {p}:", "        if False:\n            bad(f\"pass {p}:"),
    (JUDGE4, "judge4: the stage is taken from the result", "    if (par[0], par[1], par[2]) != (0x31504D53, 1, STAGE)", "    if (par[0], par[1]) != (0x31504D53, 1)"),
    (JUDGE4, "judge4: a reference flag need not fit the data", "        if rec[\"ref_equal\"] != (1 if healthy(rec) else 0):", "        if False:"),
    (JUDGE4, "judge4: a record's code need not be what its words say", "        if rec[\"code\"] != derived and not (rec[\"code\"] == 0x23 and derived in (0, 0x10, 0x11, 0x12, 0x13, 0x14)):", "        if False:"),
    (JUDGE4, "judge4: an address that does not advance is followed", "            if nxt <= cur:", "            if False:"),
    (JUDGE4, "judge4: the limit is not applied", "            if count >= limit:", "            if False:"),
    (JUDGE4, "judge4: an address outside the envelope is followed", "            if nxt > hi:", "            if False:"),
    (JUDGE4, "judge4: the reference reads during the walk are not expected", "        if since[\"frames\"] + m > every:", "        if False:"),
    (JUDGE4, "judge4: the echoed parameters need not be the planned ones", "    if list(par) != list(planned):", "    if False:"),
    (JUDGE4, "judge4: words after the data are not checked", "        if any(tail):", "        if False:"),
    (JUDGE4, "judge4: the streams are not compared with the pinned ones", "            if got != want:\n                bad(f\"record {i}: the {name} is not the pinned one\")", "            if False:\n                bad(f\"record {i}: the {name} is not the pinned one\")"),
    # no mutant for "a PASS with anomalies" in stage 4: there any anomaly ends the run, so the status check already
    # fails it, and a forged header (done, with anomalies counted) is failed by the count re-derived from the records
    (JUDGE4, "judge4: a PASS for a run that did not complete", "    if status != 1:\n        bad(f\"the run did not complete", "    if False:\n        bad(f\"the run did not complete"),
    (RUN, "run: stage 4 is judged by the judge of stage 3", "\"s1b1\": {\"judge\": s1b1_judge,", "\"s1b1\": {\"judge\": s1b0b_judge,"),
    # ---- 2026-11-14: the pull in pieces, the diagnostics (stage 5, extra stack), the stop status of a reference read
    (RUN, "run: a piece is taken whatever its crc32", "                if len(got) == n_piece and crc == m.group(1):", "                if len(got) == n_piece:"),
    (RUN, "run: a piece is taken whatever its length", "                if len(got) == n_piece and crc == m.group(1):", "                if True:"),
    (RUN, "run: a damaged piece is not pulled again", "            for attempt in range(1, MAX_PIECE_PULLS + 1):", "            for attempt in range(1, 2):"),
    (RUN, "run: a piece is pulled again without end in sight", "MAX_PIECE_PULLS = 5  ", "MAX_PIECE_PULLS = 50  "),
    (RUN, "run: the repeats of a piece are not recorded", "                record[\"pull\"][\"repeated\"].append(", "                [].append("),
    (RUN, "run: pieces that match are enough, the whole is not checked", "        if len(words) != total or host_crc != record[\"board_crc32\"]:        # `total` words", "        if False:        # `total` words"),
    (RUN, "run: the whole is checked for length only", "        if len(words) != total or host_crc != record[\"board_crc32\"]:        # `total` words", "        if len(words) != total:        # `total` words"),
    (RUN, "run: a copy that is not the board's is not kept", "            (out / \"result_unverified.bin\").write_bytes(raw)", "            pass"),
    (RUN, "run: the pieces are not the pieces asked for", "            addr = RES_ADDR + 4 * at", "            addr = RES_ADDR"),
    (CORE, "the console says stage 2 for stage 3", "    hal_putc(par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');", "    hal_putc(par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 4u ? '4' : '2');"),
    (CORE, "the console says stage 2 for stage 4", "    hal_putc(par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');", "    hal_putc(par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 3u ? '3' : '2');"),
    (CORE, "the console says stage 3 for stage 5", "    hal_putc(par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');", "    hal_putc(par(P_STAGE) == 5u ? '3' : par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');"),
    (JUDGE2, "judge3: stage 2 may ask for the new counts as well", "        return 1 <= m <= MAX_READ_FRAMES or (stage in (3, 5) and m in (0, NONE))", "        return 1 <= m <= MAX_READ_FRAMES or m in (0, NONE)"),
    (CORE, "stage 4: no reference read after an anomaly", "    if (!health4(c, KIND_HEALTH, pass)) {\n        c->stop = c->rec - 1u;\n        return health_stop(c->stop);\n    }\n    return S_STOP_WALK | code;", "    return S_STOP_WALK | code;"),
    (JUDGE4, "judge4: unused parameter words may hold anything", "            or any(par[k] for k in (10, 11, 14)) or par[15] > MAX_DIAG_STACK or any(par[17:]):", "            or par[15] > MAX_DIAG_STACK:"),
    (JUDGE4, "judge4: any amount of extra stack is a valid parameter", " or par[15] > MAX_DIAG_STACK or any(par[17:]):", " or any(par[17:]):"),
    (CORE, "a reference read that failed on the interface is reported as a changed reference frame", "    return IS_INTERFACE(code) ? (S_STOP_INTERFACE | code) : S_STOP_HEALTH;", "    return IS_INTERFACE(code) ? S_STOP_HEALTH : S_STOP_HEALTH;"),
    (CORE, "a changed reference frame is reported as an interface failure", "    return IS_INTERFACE(code) ? (S_STOP_INTERFACE | code) : S_STOP_HEALTH;", "    return S_STOP_INTERFACE | code;"),
    (JUDGE2, "judge2/3/5: a reference read that failed on the interface may be called a changed frame", "        return 0x200 | rec[\"code\"] if rec[\"code\"] >= 0x20 else 0x300\n\n    def expect", "        return 0x300\n\n    def expect"),
    (JUDGE4, "judge4: a reference read that failed on the interface may be called a changed frame", "        return 0x200 | rec[\"code\"] if rec[\"code\"] >= 0x20 else 0x300\n\n    def after_anomaly", "        return 0x300\n\n    def after_anomaly"),
    (CORE, "stage 5: the extra stack is not put beneath the target reads", "            code = extra ? read_deep(extra, rec, far, n, KIND_TARGET, r, k, far_lo, far_hi, poll_limit)", "            code = 0 ? read_deep(extra, rec, far, n, KIND_TARGET, r, k, far_lo, far_hi, poll_limit)"),
    (CORE, "stage 4: the extra stack is not put beneath the walk's reads", "    code = c->extra ? read_deep(c->extra, me, far, n, KIND_TARGET, pass, op, c->far_lo, c->far_hi, c->poll_limit)", "    code = 0 ? read_deep(c->extra, me, far, n, KIND_TARGET, pass, op, c->far_lo, c->far_hi, c->poll_limit)"),
    (CORE, "the deeper read reads something else", "    v = read_op(rec, far, n, kind, repeat, op, far_lo, far_hi, poll_limit);\n    pad[extra - 1u] = v;", "    v = read_op(rec, far, n ? 1u : 1u, kind, repeat, op, far_lo, far_hi, poll_limit);\n    pad[extra - 1u] = v;"),
    (CORE, "stage 5: a sequence longer than the result area allows", "seq > MAX_DIAG_SEQ || extra > MAX_DIAG_STACK", "seq > 200u || extra > MAX_DIAG_STACK"),
    (CORE, "stage 5: any amount of extra stack", "seq > MAX_DIAG_SEQ || extra > MAX_DIAG_STACK", "seq > MAX_DIAG_SEQ || extra > 100000u"),
    (CORE, "stage 4: any amount of extra stack", " || c.extra > MAX_DIAG_STACK || ", " || c.extra > 100000u || "),
    # no mutant for "a sequence may run past the envelope": each address of a sequence goes through the same check as an
    # address from the table; a separate check of the sequence's end was dead code and was removed
    (CORE, "stage 5: a sequence may be repeated any number of times", "(seq != 0u && (n_ops != 1u || repeats > 2u))", "(seq != 0u && (n_ops != 1u))"),
    (CORE, "stage 5: the sequence reads the frame twice instead of the pad and the frame", "static uint32_t op_n(uint32_t k, uint32_t seq)   { return seq ? (k & 1u) : op_frames(k); }", "static uint32_t op_n(uint32_t k, uint32_t seq)   { return seq ? 1u : op_frames(k); }"),
    (CORE, "stage 5: the sequence stays at its first address", "static uint32_t op_far(uint32_t k, uint32_t seq) { return seq ? par(P_FARS) + (k >> 1) : par(P_FARS + k); }", "static uint32_t op_far(uint32_t k, uint32_t seq) { return seq ? par(P_FARS) : par(P_FARS + k); }"),
    (CORE, "stages 2 and 3 take the diagnostic options too", "    if (stage5) {\n        seq = par(P_DIAG_SEQ); extra = par(P_DIAG_STACK);", "    if (1) {\n        seq = par(P_DIAG_SEQ); extra = par(P_DIAG_STACK);"),
    (CORE, "stage 5: a sequence may wrap past the top of the address space", "            if (seq - 1u > far_hi - par(P_FARS))", "            if (0)"),
    (CORE, "stage 5: a sequence may run one address past the top", "            if (seq - 1u > far_hi - par(P_FARS))", "            if (seq - 2u > far_hi - par(P_FARS) && seq > 1u)"),
    (CORE, "stage 5: a sequence that ends exactly at the top is refused", "            if (seq - 1u > far_hi - par(P_FARS))", "            if (seq > far_hi - par(P_FARS))"),
    (JUDGE2, "judge5: an operation without a read is counted as a read of the pad alone", "rec[\"n\"] == NONE else \"frame_reads\"", "False else \"frame_reads\""),
    (JUDGE2, "judge5: the pad alone is counted as an operation without a read", "rec[\"n\"] == NONE else \"frame_reads\"", "rec[\"n\"] in (0, NONE) else \"frame_reads\""),
    (CORE, "the address of the polling variable is not recorded", "    r2_wr(rec, REC2_FARBLK + F_POLL_VAR, (uint32_t)(uintptr_t)&sts);", "    r2_wr(rec, REC2_FARBLK + F_POLL_VAR, 0u);"),
    (JUDGE2, "judge5: the stage is taken from the result", "    if (par[0], par[1], par[2]) != (0x31504D53, 1, stage)", "    if (par[0], par[1], 3 if par[2] == 5 else par[2]) != (0x31504D53, 1, 3 if stage == 5 else stage)"),
    (JUDGE2, "judge2/3: the diagnostic words may be set for stages that do not have them", "            or (stage != 5 and (par[14] or par[15])) \\", "            or False \\"),
    (JUDGE2, "judge5: a sequence of any length is a valid parameter", "par[14] > MAX_DIAG_SEQ or par[15] > MAX_DIAG_STACK", "par[15] > MAX_DIAG_STACK"),
    (JUDGE2, "judge5: the reserved word beside the polling variable is not checked", "        if fb[7]:\n            bad(f\"record {i}: reserved words are not zero\")\n        for name, got, want in ((\"frame read stream\", r[16:59], frames_stream(far, m))", "        if False:\n            bad(f\"record {i}: reserved words are not zero\")\n        for name, got, want in ((\"frame read stream\", r[16:59], frames_stream(far, m))"),
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


def scratch() -> Path:
    tree = Path(tempfile.mkdtemp(prefix="selfmap_mutants_")) / "tree"
    shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__", "prober", "ret2uboot", "board_*", "sdcard"))
    for sub in ("prober", "probes/ret2uboot"):
        shutil.copytree(ROOT / sub, tree / sub, dirs_exist_ok=True)
    return tree


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""       # an optional substring: run just the mutants whose name contains it
    chosen = [m for m in MUTANTS if only in m[1]]
    jobs = max(1, min(int(os.environ.get("SM_MUTANT_JOBS", "8")), len(chosen) or 1))
    first = scratch()
    killed, summary = suite(first)
    print(f"unmutated: {summary}")
    if killed:
        print("the unmutated tree fails; nothing below would mean anything"); return 2
    baseline = int(re.search(r"Ran (\d+)", summary).group(1))
    trees: queue.Queue = queue.Queue()                    # one scratch copy per worker; a mutant has a tree to itself while it runs
    all_trees = [first] + [scratch() for _ in range(jobs - 1)]
    for tree in all_trees:
        trees.put(tree)

    def one(mutant) -> tuple[bool, str]:
        path, name, old, new, *which = mutant
        tree = trees.get()
        try:
            f = tree / path; original = f.read_text()
            want = which[0] + 1 if which else 1          # an optional fifth element picks one occurrence of several
            if original.count(old) < want or (not which and original.count(old) != 1):
                return False, f"STALE    {name}: its anchor occurs {original.count(old)} times in {path}"
            at = -1
            for _ in range(want):
                at = original.index(old, at + 1)
            f.write_text(original[:at] + new + original[at + len(old):])
            try:
                killed, summary = suite(tree)
            finally:
                f.write_text(original)
            ran = int(re.search(r"Ran (\d+)", summary).group(1))
            if killed and ran != baseline:                # the mutant did not build or import: no test judged its behaviour
                return False, f"BROKEN   {name:62s} {summary}"
            return killed, f"{'KILLED  ' if killed else 'SURVIVED'} {name:62s} {summary}"
        finally:
            trees.put(tree)

    survivors = 0
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        for ok, line in pool.map(one, chosen):            # in the order of the list, whatever order they finish in
            survivors += not ok
            print(line, flush=True)
        after = list(pool.map(suite, all_trees))          # every scratch copy, restored, passes again
    dirty = [s for k, s in after if k or not s.startswith(f"Ran {baseline} OK")]
    print(f"restored: {after[0][1]}" + (f" ({len(all_trees)} copies)" if not dirty else f" BUT {len(dirty)} cop(ies) differ: {dirty[0]}"))
    print(f"{len(chosen)} mutants, {survivors} survived")
    for tree in all_trees:
        shutil.rmtree(tree.parent, ignore_errors=True)
    return 1 if survivors or dirty else 0


if __name__ == "__main__":
    sys.exit(main())

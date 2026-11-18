# S1b.3, the chain over block type 0 — EBAZ4203 `17A6`, 2026-11-17: HALTED at run 51 (the result could not be read back)

Question (docs/s1b_plan.md, section 38): the frame list of block type 0 — which addresses the
device names from `0x00000000` on, into which rows and columns they fall, and what it names
after the last.

**What there is: 51 accepted runs, 3,214 addresses, `0x00000000..0x00401283`, each named by the
device after the one before. The first row whole — 1,932 frames, 56 columns, as on 2026-11-15
and -16, frame for frame. The second row begun: 1,282 frames, columns 0 to 36 walked whole.
The 52nd run ran on the board and reported done; its result header came back over the console
with characters missing, the run script stopped, and nothing of that run was stored. The chain
halted there by its rules. The envelope was not left; the list is not complete. Nothing was
graded.**

## The runs

Released by the owner on 2026-11-17 after the review of sections 39 and 40. The host side at
commit `3e30a3c`; the image `prober.bin`, 11,970 bytes, sha256 `fdc4f07f…9452` (kept here);
the set `s1b3` (kept here as `expected_s1b3.json`). Nothing else ran on the host while the
chain ran.

- Pre-check 18:44 UTC: U-Boot at its prompt, `carrier.bit` on the card.
- 18:44 UTC: the first run alone (`--max-new 1`, `first_run.out`). Its record says stage
  `s1b3` — the one piece of the driver no test reaches. PASS, 64 frames. Committed (`904f668`).
- 18:50–22:21 UTC: the chain unattended (`chain_to_the_end.out`), about 4 min 10 s a run; a
  U-Boot `reset`, checked, before every run.
- Runs 00 to 50: every result is the board's (the checksum on the board before the save is the
  checksum on the host after the pull; every card copy verified). 71 of 3,519 pieces came back
  short and were pulled a second time, in 33 of the runs, as the run script provides.
- 14,892 records. **No anomaly, no overflow, no interface failure** in any run.
- Committed as it stood when it halted (`0834b50`), then the summary (`e7c43a6`), before this
  was written. Nothing was retried, nothing moved.

## Run 51: the prober finished; the host did not get the header

Started at `0x00401283`, the last frame of run 50. On the console: `SM4 start`, `SM4 end
status=00000001 records=00000124 anomalies=00000000 words=000223c0`, return code 0 — the
prober's own account of a clean run of 292 records. Then the run script asked for the result
header (`md.l 10000000 40`, sixteen lines), and the reply came back with a stretch missing: it
breaks off inside the third line and resumes in the eleventh. The lines before and after are
whole, and U-Boot's prompt follows.

- That is a loss on the console between board and host, of the kind that makes a piece of a
  result come back short (71 times in this chain). **A piece is pulled again when it does not
  have the board's checksum; the header is read once, with no second attempt.** So what costs a
  repeat anywhere else stopped the run here.
- The run script did what it is written to do: with no header it knows no size, saves nothing
  to the card and pulls nothing. The run directory holds the console log and the run record;
  there is no result.
- The chain did what it is written to do: a run directory without a passing run halts it.
- Nothing suggests the device or the prober did anything unusual. Nothing shows that they did
  not, either, beyond the two console lines: the result itself was never seen.

## What the 51 runs found (`rows.json`)

- **3,214 addresses**, rising, each the one named after the one before; nothing unexpected.
- **One standstill**, after `0x00001ba9`, met by one run (run 30); the address named then:
  `0x00400000`. The fields of the address change there and nowhere else.
- **Row 0 — block type 0, top half, row 0: walked whole.** 1,932 frames, 56 columns: 41 of 36
  frames, 9 of 28, 4 of 30, 2 of 42.
- **Row 1 — block type 0, bottom half, row 0: not ended.** 1,282 frames so far; columns 0 to
  36 walked whole (28 of 36 frames, 6 of 28, 2 of 30, one of 42), each with minors 0, 1, 2, …
  and minor 0 of the next column named after it; 4 frames of column 37. Column for column,
  these 37 have the lengths the first 37 columns of row 0 have.
- The three frames with a known answer were walked and are as known; the reference frame was
  as known in every reading.
- **Content**: in row 0, 178 of 1,932 frames are not all zero; in what was walked of row 1, 247
  of 1,282 (columns 18 to 27, 34 and 35). Elsewhere the list rests on the register.

## The first row against the stored one (`top.json`)

`s1b3_top.py` on `rows.json` and `row_closed.json` of 2026-11-16 (S1b.2's chain with the old
image, closed by S1b.2b): **no disagreement.** The same 1,932 addresses in the same order; the
same frame at every one of them, the 178 that are not all zero among them; the same address
named after each; the standstill at `0x1ba9` and `0x00400000` after it; the same 56 column
lengths. The row has now been read on two days by two images.

## What this does and does not say

- It says nothing yet about where the second row ends, whether more rows follow, or what the
  device names after block type 0: the chain stopped 1,282 frames into the second row.
- The halt is a fault of reading back, not a finding about the device.
- The new image has now run 51 walks, 14,892 records, without an anomaly.

For the owner (section 42 of the plan): whether the header read is to get a second attempt
like the pieces have; and whether run 51 is set aside and the chain goes on from `0x00401283`.
Neither has been done.

## 2026-11-18: run 51 set aside; the chain not yet taken up again

The owner's answer: both, the header read first; nothing on the board until the owner says so.

- The run script now asks again for a short read-only reply that is not whole (the header
  among them), at most five times (plan section 43, commit `0bb3404`). The image is unchanged.
- What the halt left was moved, as it was, into `halted_at_run51/`: the directory `run51`
  (console log, the words of the header that did arrive, the run record), the driver's
  `run51.out`, and `chain.json`, `rows.json` and `top.json` as they were made at the halt.
  Where this file says `rows.json`, `top.json` or run 51 above, that is where they are now.
  Nothing in them was altered; a test holds them by their hashes and makes the summary and
  the comparison again from the 51 runs.
- The chain lists that directory as set aside and stands at **51 accepted runs, to go on: its
  52nd run from `0x00401283`**, the last frame of run 50 (`chain.json` here is that state).
- **Nothing has run on the board since run 51.** Nothing was graded.

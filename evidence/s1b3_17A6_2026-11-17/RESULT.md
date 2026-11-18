# S1b.3, the chain over block type 0 — EBAZ4203 `17A6`, 2026-11-17 and -18: COMPLETE (halted once at run 51, taken up again)

Question (docs/s1b_plan.md, section 38): the frame list of block type 0 — which addresses the
device names from `0x00000000` on, into which rows and columns they fall, and what it names
after the last.

**The outcome (2026-11-18; the account is in the last sections): 62 accepted runs, 3,864
addresses, each named by the device after the one before. Block type 0 is two rows — top half
row 0 and bottom half row 0 — of 1,932 frames in 56 columns each, column for column the same
lengths. At the end of each row the register stood still; after the first the device named
`0x00400000`, after the second `0x00800000`, which is outside block type 0 and was not read.
Graded once against prjxray-db: nothing differs.**

What follows down to "2026-11-18" was written on 2026-11-17, when the chain had halted, and
is left as it was.

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

## 2026-11-18: taken up again, complete

Released by the owner after the review of sections 43 and 44 of the plan. The host side at
commit `473b996`; the same image; nothing else ran on the host.

- Pre-check 14:54 UTC: U-Boot at its prompt, `carrier.bit` on the card. The status word read
  `a802000b`, the value of a fresh start and not the one a run leaves: the board had been
  started anew since run 51 (by whom or how was not looked into; what that run left in memory
  was not used in any case).
- 14:54–15:38 UTC: the chain unattended (`chain_from_run51.out`), runs 51 to 61, a `reset`,
  checked, before each. Every one PASS; no anomaly, no overflow, no interface failure. 12 of
  713 pieces were pulled a second time. **No short reply came back not whole: the new second
  attempt was never used.**
- Run 51 again, from `0x00401283`: its first frame is the last frame of run 50, the same
  content, the same address named after it.
- **Run 61**: 21 frames. At `0x00401ba9` the pad alone left the register where it was, and
  after the frame it showed `0x00800000`. That is above the envelope: both passes ended there,
  the address was not read, and the chain is complete — every frame with a known answer was
  walked.
- In all: 62 runs, 17,908 records; 83 of 4,232 pieces pulled a second time, in 39 of the runs.
- Committed as stored (`887b479`) before anything was made of it.

## What the 62 runs found (`rows.json`, sha256 `16c1d239…c823`, commit `9615af8`)

- **3,864 addresses**, rising, each the one named after the one before; nothing unexpected.
- **Two rows, both walked whole**:

  | | first | last | frames | columns | ended by | named after it |
  |---|---|---|---|---|---|---|
  | top half, row 0 | `0x00000000` | `0x00001ba9` | 1,932 | 56 | a standstill | `0x00400000` |
  | bottom half, row 0 | `0x00400000` | `0x00401ba9` | 1,932 | 56 | a standstill | `0x00800000` |

- **The columns of the two rows have the same lengths, one for one**: 41 of 36 frames, 9 of 28,
  4 of 30, 2 of 42 (the first and the last). In every column the minors are 0, 1, 2, …, and
  minor 0 of the next column is named after the last.
- **Two standstills**, each met by one run (run 30, run 61), each at the last frame of a row.
  The second behaves as the first did: the pad alone leaves the register, the frame moves it.
- **`0x00800000`** is the first address the device names outside block type 0. In the fields
  of the address that is block type 1. It was named, not read: nothing is known of it here.
- **Content**: 178 of the 1,932 frames of the top row are not all zero (columns 18 to 27 and
  39), 250 of the bottom row (columns 18 to 27, 34, 35 and 39). Elsewhere the list rests on
  the register.

## The first row against the stored one (`top.json`, sha256 `e71a717e…37ec`, commit `57778ff`)

Made again from the complete chain: no disagreement, as at the halt — 1,932 addresses, the same
frame and the same address named at every one, 56 columns.

## The grader (`grade.json`, sha256 `732c389a…7148`, commit `06fa08e`)

`grade_s1b3.py`, run once, after the three commits above, on `rows.json` against `part.json`
of `xc7z010clg400-1` in the prjxray-db checkout at `0a0adde` (sha256 `1754ec1c…d095`, the file
the earlier grades used). Its first run on real data. No bitstream was parsed.

- **Nothing differs.**
- Both rows: each of the 56 columns has the number of frames the database gives it, and they
  are the database's columns 0 to 55 in order; 1,932 frames a row.
- The rows walked are the database's rows of block type 0 in its order; 3,864 frames in all,
  as the database's columns add up to.
- After the first row the device named `0x00400000`, the first frame of the next row in the
  database's order; after the last frame `0x00800000`, the first frame of block type 1 there.
  The database lists frames; it does not say what a device names — these two are offered as
  such.
- Not compared: that the register stood still at the end of both rows.

## What this does and does not say

- The device's own account of block type 0 — which addresses, in which order, how many — was
  got without a description of the part, and agrees with the one description it was then held
  against.
- It says nothing about what the frames mean, nor about block type 1 or anything after it.
- What happens in the register at the end of a row is described (S1b.2b, and twice here); why
  is not known.
- The second attempt at a short reply is tested on the host and against the stored replies; on
  the board it has not yet been needed.

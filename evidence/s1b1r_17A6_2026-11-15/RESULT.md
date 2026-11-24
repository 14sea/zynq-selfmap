# S1b.1 with the quiet wait — EBAZ4203 `17A6`, 2026-11-15: PASS

Question (docs/s1b_plan.md, section 12): walking from `0xb80` by the addresses the device itself
names, how many frames does the column have, and what does the device name after the last?

**Answer: 36 frames, `0xb80` to `0xba3`, each naming the next number; after `0xba3` the device
named `0xc00`. Both passes of the walk say so, every frame was read by two paths, and the judge
passes the run. The grader, run afterwards, finds the same in prjxray-db.**

## The run

One run of the parameter set `s1b1r` (commit `4ecf751`, reviewed) with the image `prober.bin`,
11,630 bytes, sha256 `2c566b1e…b296`, crc32 `b0d75377`, after a U-Boot `reset` and a fresh load
of the PL design. Console: `SM4 start`, `SM4 end status=00000001 records=000000a4
anomalies=00000000 words=000133c0`; return code 0. The result is the board's: 78,784 words,
crc32 `b666fed2` on the board before the save and on the host after the pull (39 pieces, none
pulled twice); the card copy (`saf979a3.bin`) verified; `result.bin` sha256 `08e7f4eb…3366`.
`INT_STS` afterwards `50033004`.

## What the judge found (`run1/verdict.json`), from the raw words

- **PASS**, no problem listed. Status 1, 164 records, no anomaly: 72 reads of the pad alone, 72
  reads of one frame, 12 reads of several frames, 8 reads of the reference frame.
- **Both passes: 36 frames, ended because the device named an address outside the envelope,
  `0xc00`.** The envelope given was `0xb80..0xbff` and the limit 64 frames a pass; neither was
  what ended the walk.
- At each of `0xb80..0xba2` the device named the next number; at `0xba3` it named `0xc00`. After
  the frame at `0xba3` was read the register held `0xc01`. 81 cross-checks between the two ways
  the register was read, all met.
- The two passes delivered the same 36 frames; every frame was also delivered by a read of
  several frames (none is left without a second path). The 36 frames are all different from one
  another and none is all zero.
- The three frames with a known answer (`0xb98`, `0xb99`, `0xb9a`) are as known, in every read
  of them; the reference frame was the same at each of its 8 reads, never more than 16 frames
  apart.
- The first 26 frames are the same as in every earlier run that read them (the stopped walks of
  2026-11-14 and the nine complete walks of the 26 addresses today: 486 frame comparisons, no
  difference).
- 163 of the reads lay at the stack positions where the original wait had overflowed; with the
  wait that stores nothing, none did.

## The grader, afterwards (`grade.json`)

Run after the result had been saved, judged and committed (`b6cdd14`), against
`prjxray-db/zynq7/xc7z010clg400-1/part.json` in a checkout beside this repository (sha256 `1754ec1c…d095`, the checkout at
`0a0adde`):

- the 36 addresses walked are minors 0..35 of one column — block type 0, top half, row 0,
  column 23;
- frames in the column: the walk found 36, the database says 36;
- the address named after the last frame is `0xc00`; minor 0 of the next column in the database
  is `0xc00`;
- nothing differs, nothing was left uncompared.

## What this does and does not say

- It is one column of one row, found by asking the device, with no frame count and no layout in
  the prober or the judge. The agreement with the database is one more witness, as the plan
  says, not the source of the answer.
- That the address after the column is the next column's first frame is what the device said at
  this one place. What it does at the end of a row, or between block types, has not been asked:
  that is S1b.2 and S1b.3.
- The contents of the 33 frames without a known answer are recorded and repeatable; nothing is
  claimed about what they mean.
- As said in the plan: while writing the grader I had seen the database's number for this
  column. The prober and the judge do not hold it.

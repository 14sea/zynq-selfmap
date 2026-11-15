# S1b.2, the walk of the row — EBAZ4203 `17A6`, 2026-11-15: the chain HALTED at the end of the row

Question (docs/s1b_plan.md, section 25): block type 0, top half, row 0 — which addresses does the
device name along it, into which columns do they fall and how many frames has each, and what does
the device name after the last frame of the row?

**What there is: 30 accepted runs, 1,891 frames from `0x00000000` to `0x00001b80`; columns 0 to
54 walked whole (1,890 frames; 41 columns of 36 frames, 9 of 28, 4 of 30, one of 42), each
ending with the device naming minor 0 of the column numbered one higher. The 31st run walked 42
frames of column 55 and was then stopped by the prober: asked what follows `0x00001ba9`, the
device named `0x00001ba9` again. The chain halted there by its own rule. The row was not left;
the chain is not complete. The grader has not been run.**

## The runs

Released by the owner after the review of sections 26 and 27. The chain driver at commit
`1af872d`; the image `prober.bin`, 11,630 bytes, sha256 `2c566b1e…b296`, crc32 `b0d75377`; the
parameter set `s1b2` (kept here as `expected_s1b2.json`). Before every run a U-Boot `reset`
(checked) and a fresh load of the PL design.

- 17:41 UTC: the first run alone (`--max-new 1`). Accepted; looked at; then
- 17:47–19:46 UTC: the chain to its end (`chain_to_the_end.out`), about 4 min 20 s a run.
- Every result is the board's: the checksum on the board before the save is the checksum on the
  host after the pull, and every card copy verified. 28 of the 2,091 pieces came back short and
  were pulled a second time, as the run script provides. `INT_STS` after every run `50033004`.
- 8,847 records in all: 4,965 reads that delivered frames, 3,882 reads of the pad alone. No
  anomaly, **no overflow, no interface failure** in any run.
- Nothing was retried, nothing set aside.

## Runs 00 to 29: accepted

Each passed the judge, both of its passes ended at the limit after the same 64 frames and were
told the same address, and each of the 29 seams matched (the same address, the same frame, the
same address named after it, in two runs). From `row.json`:

- **1,891 addresses, each named by the device after the one before**, rising, nothing listed as
  unexpected.
- **Columns 0 to 54 walked whole.** In every one the minors are 0, 1, 2, … and after the last
  frame the device named minor 0 of the column numbered one higher.

  | frames | columns |
  |---|---|
  | 42 | 0 |
  | 30 | 1, 34, 39, 54 |
  | 28 | 6, 9, 14, 17, 22, 25, 42, 46, 49 |
  | 36 | the other 41 of 2..53 |

- **Column 23 is the column S1b.1 walked**: the same 36 addresses, the same 36 frames, the same
  addresses named. The three known frames were walked and are as known; the reference frame was
  as known in every run.
- 4,452 cross-checks between the two ways the address register was read, all met — but for the
  last run, below.

**What the content checks are worth here.** 1,713 of the 1,891 frames are all zero; frames that
are not lie in columns 18 to 27 and 39 only. "The same frame by two paths and in two passes" and
"the same frame at the seam" say little where every frame is the same: 26 of the 29 seams lie on
an all-zero frame. What discriminates there is the address register (every step of it was
recorded and checked) and the reference frame, read every 16 frames and as known throughout.

## Run 30: stopped by the prober

Started at `0x00001b80`, the last frame of run 29, as the chain plans. Status `0x800` ("the
device named an address that is not above the one it was asked about"), 87 records, no anomaly.
The judge fails it, as it fails every run that does not complete; the chain does not count it.
Its records, as stored:

- First pass: 42 frames, `0x00001b80` to `0x00001ba9`, all zero; at each of `0x1b80..0x1ba8` the
  device named the next number. One pass only, and no read of several frames: these 42 frames
  have **not** been read twice or by a second path.
- The last six records:

  | asked | read | register afterwards |
  |---|---|---|
  | `0x1ba7` | the pad alone | `0x1ba8` |
  | `0x1ba7` | the pad and one frame | `0x1ba9` |
  | `0x1ba8` | the pad alone | `0x1ba9` |
  | `0x1ba8` | the pad and one frame | **`0x1ba9`** |
  | `0x1ba9` | the pad alone | **`0x1ba9`** |
  | `0x1ba9` | the pad and one frame | **`0x00400000`** |

  Everywhere else in the row the register after "the pad and one frame" is two steps on. At
  `0x1ba8` it is one step on, and at `0x1ba9` the read of the pad alone does not move it at all;
  the next step from there gives `0x00400000` — by the layout of the address word: block type 0,
  **bottom** half, row 0, column 0, minor 0.

What this says and does not say:

- It says that `0x1ba9` is the last address of this row that the device names in the way it
  named all the others, and that column 55 has 42 frames by one pass (minors 0..41).
- It says that between `0x1ba9` and `0x00400000` there is at least one step at which the
  register still reads `0x1ba9`. How many such steps there are, and what a read delivers there,
  the records do not say: the prober stopped, as it is built to.
- (My reading, not an observation: this looks like frames beyond the last of the row that have
  no address of their own. It is general knowledge of the family that a row is followed by
  padding; nothing here was built on it, and the walk's rule — follow the address the device
  names after the pad alone — does not carry across such a place.)
- `0x00400000` was not read. It lies outside the envelope.

## Not done

- **The grader was not run and the database was not looked at.** The chain did not complete; by
  what was agreed, a halt is saved, committed and reported, and the rest is the owner's.
  (`grade_s1b2.py` can grade a halted chain — the columns walked whole only — if the owner wants
  that.)
- Nothing was changed to get past the end of the row.

## Files

`run00` … `run30` (each: `result.bin`, `header.bin`, `run.json`, `verdict.json`, `console.log`),
`runNN.out`, `chain.json`, `row.json` (sha256 `60074f0c…85bd`), `expected_s1b2.json`,
`resets_console.log`, `chain_to_the_end.out`. Committed as they were in `7b782ad`, before this
file was written.

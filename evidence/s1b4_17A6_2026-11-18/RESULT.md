# S1b.4, the chain over block type 1 — EBAZ4203 `17A6`, 2026-11-18: complete

Question (docs/s1b_plan.md, section 49): which frame addresses does the device name from
`0x00800000` on, as far as the envelope `0x0..0x00ffffff` goes?

**1,280 addresses, in two rows of 640: the top half and the bottom half, row 0 each, five
columns of 128 frames each. The register behaves as in block type 0 throughout, with a
standstill at the end of each row. After the last frame the device names `0x01000000`, which
is above the envelope: it was named, not read, and the chain is complete. 21 runs, every one
PASS; no anomaly, no overflow, no interface failure; the reference frame in block type 0 as
known at all 285 of its readings.**

**Two things were not expected, and neither is explained here (below, "Seen and not
explained"): the frames of columns 2, 3 and 4 are not all zero — all 768 of them hold one and
the same content — and from the first read of such a frame on, the status register shows a
bit that no earlier run of this project had shown.**

## The runs

Released by the owner on 2026-11-18 after the review of sections 50 and 51. The host side at
commit `c96c794`; the image 11,970 bytes, sha256 `fdc4f07f…9452`, the one of S1b.3a, S1b.3
and S1b.4a; the set `s1b4`: S1b.4a's set with the start given by the chain. `prober.bin` and
`expected_s1b4.json` are kept here; they were copied in after the chain had ended, from the
build directory, and are the files every run was checked against (the image by its checksum
on the board before and after, the parameters word for word by the judge). Nothing else ran
on the host while the board was in use.

- Pre-check 20:52 UTC (`precheck_console.log`): U-Boot at its prompt, `carrier.bit` on the
  card (2,083,863 bytes), the status word `50033004` as S1b.4a had left it. A `reset`; the
  usual fresh prompt, status `a802000a`.
- 20:52–20:56 UTC: the first run alone (`first_run.out`). PASS; 64 frames from `0x00800000`.
  Looked at and committed (`34a4874`) before the chain went on.
- 20:59–22:20 UTC: the chain unattended (`chain_to_the_end.out`), runs 1 to 20, a `reset`,
  checked, before each (`resets_console.log`). Every one PASS.
- In all: 21 runs, 5,932 records — 2,600 reads of the pad alone, 2,600 of the pad and a frame,
  447 reads of three frames, 285 of the reference frame. 23 of 1,402 pieces were pulled a
  second time, in 11 of the runs. No short reply came back not whole.
- Committed as stored (`245b25b`) before anything was made of it.

## What the 21 runs found (`rows.json`, sha256 `d02a372b…222f`, commit `25ef37f`)

- **1,280 addresses**, rising, each the one named after the one before; nothing unexpected.
- **Two rows, both walked whole**:

  | | first | last | frames | columns | ended by | named after it |
  |---|---|---|---|---|---|---|
  | top half, row 0 | `0x00800000` | `0x0080027f` | 640 | 5 | a standstill | `0x00c00000` |
  | bottom half, row 0 | `0x00c00000` | `0x00c0027f` | 640 | 5 | a standstill | `0x01000000` |

- **Every column has 128 frames**, minors 0 to 127, and minor 0 of the next column is named
  after the last. The column of S1b.4a's run is the first of them.
- **Two standstills**, each met by one run (run 10, run 20), each at the last frame of a row,
  and as in block type 0: the pad alone leaves the register where it was, the frame moves it.
- **`0x01000000`** is the first address the device names above block type 1. In the fields of
  the address that is block type 2, top half, row 0, column 0, minor 0. Named, not read:
  nothing is known of it here.
- The three frames with a known answer lie below the set's first address and were not asked
  of this chain (plan section 50); the reference frame is one of them and was read as such.

## The first run against S1b.4a's (`first_run_against_s1b4a.json`, commit `7491ad5`)

The stored run of S1b.4a held against the chain's list: no disagreement. Its 64 addresses are
all in the chain, with the same frame and the same address named after each. All 64 frames
are all zero, so that agreement says nothing about content.

## Seen and not explained

Both were found by looking at the stored runs after the chain had ended and before the grader
was run. Nothing was read again on the board for either.

**1. The frames of columns 2, 3 and 4 hold one content, and it is not zero.**

- The 512 frames of columns 0 and 1 (both rows) are all zero.
- The 768 frames of columns 2, 3 and 4 (both rows) are all the same frame: 91 words of zero
  and ten words of `0x00020000`, at words 4, 14, 24, 34, 44, 55, 65, 75, 85 and 95 of the
  101, counted from 0 in the order delivered. Every tenth word, with the middle word passed
  over.
- Each of those frames was delivered the same way every time it was read: in both passes,
  in the reads of three, and by both runs at a seam. No address has two contents.
- What this is, is not known. It is the same in 768 frames, so it is not something the
  walk can tell one frame from another by: for the list of addresses these columns rest on
  the register and on the reference frame, as the all-zero ones do. Whether what is
  delivered here is what is stored, a fixed pattern of the device or of the readback, or
  something of the design, this run cannot say.
- (Corrected 2026-11-18, after the grade: this item first said "UG470 says block-RAM content
  is skipped in readback". That sentence of UG470 is about the background readback check
  only. Of a readback asked for, as these are, UG470 says it reads "all configuration memory
  cells, including the current values on all user memory elements (LUT RAM, SRL, and block
  RAM)". Plan section 46 has both statements in their place.)

**2. The status register after a run reads `50033024` in 14 of the 21 runs, `50033004` in
the other 7.**

- The difference is bit 5. No stored run of this project had shown it before: 159 runs with
  a run record — 138 ending in `50033004`, 16 ending with an error bit set, 5 with no status
  read — all of block type 0 and S1b.4a's run among them.
- Where it appears, in the status words kept with every record: **in each of the 14 runs, at
  the first read of a frame in columns 2 to 4**, and it stays set to the end of the run. In
  run 4 that is the read of the pad and the frame at `0x00800100`, the first frame of column
  2; the read of the pad alone at that address, just before, still shows `50033004`. In run
  14 it is the read at `0x00c00100`. In runs 5 to 10 and 15 to 20, which begin inside those
  columns, it is the first read of a frame.
- The 7 runs without it are runs 0 to 3 and 11 to 13: the ones whose frames are all in
  columns 0 and 1. Every run begins after a `reset` with the bit clear.
- So it comes with the frames of finding 1, at the first of them a run reads. Whether every
  such read raises it cannot be seen: the prober does not clear this bit between reads.
- UG585's register reference names bit 5 of `devcfg.INT_STS` `PCFG_SEU_ERR` and says it
  "triggers when PL detects POST_CRC or ECC error". (Another table of the copy at hand
  describes the bit differently; the reference is what is quoted.) Why reading these frames
  raises it is not known.
- What it did not do: it is not one of the bits the prober and the judges treat as an error,
  so no run stopped and every run passed; `PCFG_DONE` stayed set; the reference frame read
  as known after it in every run; `devcfg.CTRL` in every header is `4e00e07f`, in which bit
  8 (`SEU_EN`, by the same reference: lock the PS down when the PL reports an upset) is
  clear. A `reset` and a new load of the design precede every run.
- Not looked into: whether the design in the PL still works as it should after such a read.
  S1b uses nothing of the design, and nothing here tests it.

## The grader (`grade.json`, sha256 `3e70bb86…9892`, commit `d29fcf9`)

Everything above this heading was written and committed (`9e12785`; one count corrected in
`25637da`) before the grader was run. Then `grade_s1b3.py`, once, on `rows.json` against
`part.json` of `xc7z010clg400-1` in the prjxray-db checkout at `0a0adde` (sha256
`1754ec1c…d095`, the file the earlier grades used). No bitstream was parsed.

- **Nothing differs.**
- Both rows: each of the 5 columns has the number of frames the database gives it, 128, and
  they are the database's columns 0 to 4 in order; 640 frames a row.
- The rows walked are the database's rows of block type 1 in its order; 1,280 frames in all,
  as the database's columns add up to.
- After the first row the device named `0x00c00000`, the first frame of the next row in the
  database's order.
- Not compared, the database having nothing to hold them against: the two standstills, and
  `0x01000000` — the database lists no block type after this one.

With block type 0 (3,864, `evidence/s1b3_17A6_2026-11-17`) that is 5,144 frame addresses named
by the device and found in the database, and none in the one that is not in the other.

The two things under "Seen and not explained" are not something the frame list of the
database speaks to; they were not graded and stand as written.

A test (`tests/test_board_evidence.py`) judges the 21 runs again from their raw words, makes
the summary and the comparison again, and holds the files here by their hashes; it also holds
the two unexplained findings as they are in the stored records.

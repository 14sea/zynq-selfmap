# The grading of S2 (2026-11-26): nothing differs

Called by the owner on 2026-11-26. What is compared and how was written and committed
beforehand (`docs/s2_plan.md`, section 57, commit `7af55bf`), before the database's files
for slices were opened and before the grader was written. This is not a run of the board.

| | |
|---|---|
| the grader | `host/grade_s2.py` |
| its output, as it came | `grade.json` (sha256 `2d6ed3f9…126bc`) |
| the database | prjxray-db, commit `0a0addedd73e7e4139d52a6d8db4258763e0f1f3` (2021-12-14), directory `zynq7` |
| files of it that were read | `xc7z010/tilegrid.json`, `segbits_clblm_l.db`, `segbits_clblm_r.db` (their sha256 are in `grade.json`) |
| graded | `evidence/s2_3_17A6_2026-11-23/ram_map.json`, `evidence/s2_4b_17A6_2026-11-23/srl_map.json`, `evidence/s2_5b_17A6/ram_map.json` and `rule.json` — as stored; none is changed |
| agrees | 16 statements |
| differs | **none** |

The database is one more witness, not the answer: what follows says that two descriptions
made in different ways say the same, and where only one of them says anything.

## The comparisons of section 57

### 1. The cells of LUT RAM at 110 sites (S2.5)

**28,160 of 28,160 entries lie where the database puts that bit of that LUT's content.**
All 440 memories agree at every one of their 64 places; none is "the same places in
another order", none lies in another LUT of its site. The database has all 110 sites, and
a line for every cell.

The database's numbers were read as section 57 said: the tile's first frame address plus
the frame of the line; the line's bit counted from the tile's first word, 32 to a word,
bit 0 the least significant. Under the three other readings the grader also counts (the
bits of a word from the other end, the words of a frame from the other end, both) **no
entry would agree** — 0 of 28,160 each. So the agreement is of the reading named and of no
other.

The comparison takes RAM address a to be bit a of a LUT's content, and the LUT of a memory
from the build's record (memories 0 to 3 are D, A, B, C). With both, every entry agrees;
had either been otherwise, 28,160 entries would not have fallen on their lines. That is
an argument and not a measurement: S2 itself still shows neither (section 10 of the plan).

### 2. The cells of LUT RAM at one site (S2.3)

**256 of 256**, at `SLICE_X16Y30`; the four memories agree at every place.

### 3. The shift registers (S2.4)

**256 of 256 places are content bits of the LUT the build names for their register**, at
`SLICE_X34Y70`. Every one of the 4 × 64 content bits of those LUTs is the place of some
output; none is left over.

As expected, the database has no line that says which bit of content is which stage of a
shift register. Beside the content it has, for such a LUT, the lines `RAM`, `SRL`, `SMALL`
and those of `DI1MUX` — what the LUT is used as and where its data input comes from.
So this is **listed, not graded** (`grade.json`, `s2_4.listed_not_graded`), and it is the
same in all four registers:

| bit of the LUT's content | follows |
|---|---|
| 2 a + 1, for a from 0 to 31 | output a, as it is |
| 2 a + 2, for a from 0 to 30 | output a, inverted |
| 0 | output 0, inverted |

This is the table of `evidence/s2_4b_17A6_2026-11-23/RESULT.md`, there in RAM addresses of
S2.3 and here in the database's numbers of content bits: the two numberings are the same
(comparison 2).

### 4. The rule, part by part (S2.5)

The database has 1,500 sites of this kind (`SLICEM`), the same 1,500 as the list the
designs were made from (`pl/s2a/slicem_sites.txt`), in two types of tile: `CLBLM_L` (600
sites) and `CLBLM_R` (900). 110 were measured.

| part | measured at | held against | agrees |
|---|---|---|---|
| the six moves | 440 memories | the 256 lines of content of each type of tile | 256 of 256, in both types |
| the position | 110 sites | the same lines | 4 of 4 LUTs, in both types |
| the half | 110 sites | the first frame address of each tile | 1,500 of 1,500 sites |
| the word | all 50 rows of a half | the words of each tile | 1,500 of 1,500 sites |
| which four frames of a column (the 32nd to the 35th of 36, counted from 0) | 110 sites — from the entries of the map; `rule.json` does not say it | the frames of each tile's lines | 1,500 of 1,500 sites |
| the column, as measured | 11 columns of sites | the column of frames of each tile | 1,100 of 1,100 sites in those columns |

The lines of content are the same in both types of tile, and no line of content carries
the database's mark of inversion (`!`); the maps of S2.3 and S2.5 call no place inverted.
The two are not the same statement — one is of the bitstream, the other of readback — and
are set side by side, not counted.

**The column.** `rule.json` says the columns measured "do not lie on one line", and gives
eleven measured columns. All eleven are the database's. Section 53 added a reckoning, in
its own words "an extrapolation and no finding": counted among the columns of 36 frames of
a half, the (13 + X/2)-th up to X12 and the (19 + X/2)-th from X16. It fits the database
at every column of sites of this kind, measured or not:

| X | measured | column of frames (the census's number) | which among the columns of 36 frames | section 53 |
|---|---|---|---|---|
| 0 | no | 19 | 13 | 13 |
| 4 | no | 21 | 15 | 15 |
| 6 | no | 23 | 16 | 16 |
| 8 | no | 24 | 17 | 17 |
| 10 | yes | 26 | 18 | 18 |
| 12 | yes | 27 | 19 | 19 |
| 16 | yes | 36 | 27 | 27 |
| 20 | yes | 38 | 29 | 29 |
| 24 | yes | 41 | 31 | 31 |
| 28 | yes | 44 | 33 | 33 |
| 30 | yes | 45 | 34 | 34 |
| 32 | yes | 47 | 35 | 35 |
| 34 | yes | 48 | 36 | 36 |
| 38 | yes | 51 | 38 | 38 |
| 42 | yes | 53 | 40 | 40 |

### 5. Every site of this kind that was not measured — 1,390

- **990 sites in the eleven measured columns of sites** (the rows of a column that were not
  probed): the rule gives a place for every cell, and **253,440 of 253,440 cells lie where
  the database puts them**; every cell agrees at all 990 sites.
- **400 sites in the four columns not measured** (X0, X4, X6, X8): the rule names no column
  of frames for them. The parts that do not need it — the six moves, the position, the
  half, the word, the four frames — each hold at 400 of 400. With section 53's reckoning
  for the column (above), the place of every cell at these sites would be the database's
  too; the rule file does not carry that reckoning, so it is not counted as the rule's.

## What turned out otherwise than section 57 expected

- Section 57 spoke of "the eleven columns of sites not measured". **There are four.** Sites
  of this kind are in fifteen columns of sites — X 0, 4, 6, 8, 10, 12, 16, 20, 24, 28, 30,
  32, 34, 38, 42 — and eleven were measured. X2, X14, X18, X22, X26, X36 and X40 hold no
  site of this kind, in the database and in the list the designs were made from alike. I
  had the list and had not counted its columns; section 53's "22 columns" counts pairs of
  X up to X43, sites of any kind.
- So section 53's sentence "No site of X14 was probed, so where the six lie between the
  two is open" asked for something that cannot be probed in this way: X14 has no site that
  holds LUT RAM.
- Nothing else. The database's files hold what section 57 expected, and its numbers read as
  it said.

## What was not compared

As section 57 listed, and as `grade.json` repeats (`not_compared`): whether a place reads
inverted; which content bit is which stage of a shift register (listed above); control
register 0, the mask of LUT RAM in readback, that reading does not disturb the RAM, bit 5
of the status, the path from PS to PL; and that RAM address a is content bit a.

Not asked, and open to ask now: what the database puts in the columns of 36 frames that
hold no site of this kind. Section 53 left it unsaid, and the grading did not ask it.

## What this does and does not say

- Every place S2 found for a LUT RAM cell is the place a database made in another way —
  from bitstreams, by other people — gives that bit. A systematic error of S2's method
  that this could have shown (section 12, point 8) is not there.
- The rule's four parts that held at the sites measured hold at every site of this kind of
  the part, and the measured columns are right. The one part that did not hold as a rule,
  the column, is right as far as it was measured, and section 53's reckoning fits where
  nothing was measured.
- It does not say that a write to these bits changes a LUT: nothing has been written to
  configuration memory. That is S4.
- It is one database against one board. Where both could be wrong alike it shows nothing.
- With it the closed-book part of S2 ends for its author (section 57, last part): I have
  now seen the database's lines for these tiles.

## The grader

`host/grade_s2.py` reads the stored descriptions, the census, the build's records and the
three files of the database; it writes nothing and parses no bitstream. Its tests
(`tests/test_grade_s2.py`) make up a device and a database and hold that each kind of
difference is counted and said — a cell elsewhere, cells in another order, another LUT,
bits counted from the other end, each part of the rule, a column, the reckoning — and that
the stored `grade.json` is what the grader says of the stored descriptions (where the
database lies beside the repository). Sixteen mutants of it are in `tests/mutants.py`.

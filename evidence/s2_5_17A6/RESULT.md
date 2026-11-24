# S2.5, part 1: where the memories of 110 sites are — EBAZ4203 `17A6`, 2026-11-24: complete

Question (docs/s2_plan.md, section 45, part 1): the design `s2b` has LUT RAM at 110 sites,
four memories of 64 bits at each, every memory loaded with a word of its own. Where in
block type 0 is each of the 440 memories, and is it laid out as the one site of S2.3 was?

**28,160 bits follow a write to every site — as many as the design has cells — all of them
as they are, none inverted, none irregular; every other bit of block type 0, 12,460,288,
read the same in all three states. Each of the 440 loaded words was found exactly once,
whole, under the six moves of S2.3, and the 64 places of each are candidates: no memory
not found, none found twice, no candidate that is no memory's. All 3,864 addresses were
read as loaded, all one, all zero, in eight runs; every run passed. All 110 sites read
back through the design as held, before the frames of every state and after them. CTL0 was
`0x00000501` in every run, as in S2.2's.**

**The prediction made before the board was asked is a miss in one of its three rules, at
two sites: 432 of the 440 memories are where it said, under the form it named first; 8 are
not.** The four memories of `SLICE_X10Y7` and the four of `SLICE_X12Y44` lie six columns of
frames lower than said, in the word and the half that were said. This is outcome 2 of the
six section 45 named for part 1: all found, and some not where part 0 said.

Nothing was graded. Which place is which cell of its memory is known from this only as far
as the six moves say; part 2 asks the device.

## The runs

On the owner's word of 2026-11-24, after the design was on the card (section 51). The host
side at commit `7d42c26`; the image the one of section 32 (19,244 bytes, sha256
`8bf3799c…2a8b`), unchanged since S2.3; the set `s2_5f` (`expected_s2_5f.json`, copied in
before the first run); the design `s2b.bit` from the card (2,083,859 bytes, crc32
`15045cfc`). By section 35 the complete set of mutants was not run. Nothing else ran on the
host while the board was in use; the suite ran between the first run and the others, and
after the chain, with `SELFMAP_NO_BOARD` set.

- Pre-check 19:35 UTC (`precheck_console.log`): the prompt, status `a802000b`, `s2b.bit`
  on the card with its size; a `reset`: `Model: Ebang EBAZ4203`, `a802000a`.
- 19:35:25–19:42:53 UTC: the run of share 0 alone (`first_run.out`). PASS. Committed as it
  stood (`019184e`); the chain starts no second run before that.
- 19:51:47–20:41:00 UTC: the other seven (`chain_to_the_end.out`), a `reset` before each.
  Complete; `candidates.json` written. Committed as it stood (`8a7e92f`).

| run | share | reads a state | frames a state | first | last | records | words pulled | pieces pulled again | bits that follow | memories found |
|---|---|---|---|---|---|---|---|---|---|---|
| run00 | 0 | 174 | 516 | `0x00000000` | `0x0000071b` | 526 | 254,638 | 0 | 0 | 0 |
| run01 | 1 | 174 | 516 | `0x00000780` | `0x00000ea3` | 526 | 254,638 | 0 | 0 | 0 |
| run02 | 2 | 174 | 520 | `0x00000f00` | `0x00001623` | 526 | 254,638 | 2 | 13,312 | 208 |
| run03 | 3 | 176 | 524 | `0x00001680` | `0x004001a3` | 532 | 257,518 | 0 | 512 | 8 |
| run04 | 4 | 172 | 508 | `0x00400200` | `0x00400923` | 520 | 251,758 | 1 | 0 | 0 |
| run05 | 5 | 176 | 524 | `0x00400980` | `0x004010a3` | 532 | 257,518 | 0 | 512 | 8 |
| run06 | 6 | 172 | 512 | `0x00401100` | `0x00401823` | 520 | 251,758 | 0 | 13,312 | 208 |
| run07 | 7 | 82 | 244 | `0x00401880` | `0x00401ba9` | 250 | 122,158 | 1 | 512 | 8 |

In all 1,904,624 words pulled, each run's result with the board's checksum of it and the
card copy read back the same; three pieces of results were pulled again (one of them
twice) and then had their checksum. No reply of a short read was not whole. Every run:
`anomalies=00000000`, return `0x0`, every record's code 0, status afterwards `50033004`. In
every run 128 writes, which the design counted as 128 — 64 addresses for all one and 64
for all zero, each to every site at once — and no access to one site alone. Nothing halted
and nothing was set aside. These are the first runs of the design `s2b` on a board.

## What was found

**The candidates.** 28,160 places in 48 frames, twelve groups of four frames next to each
other:

| frames | sites | column of sites | rows | candidates |
|---|---|---|---|---|
| `0x00001220`–`0x00001223` | 50 | X16 | 50 to 99 | 12,800 |
| `0x00001320`–`0x00001323` | 1 | X20 | 81 | 256 |
| `0x00001620`–`0x00001623` | 1 | X28 | 55 | 256 |
| `0x000016a0`–`0x000016a3` | 1 | X30 | 92 | 256 |
| `0x00001820`–`0x00001823` | 1 | X34 | 66 | 256 |
| `0x00400d20`–`0x00400d23` | 1 | X10 | 7 | 256 |
| `0x00400da0`–`0x00400da3` | 1 | X12 | 44 | 256 |
| `0x00401220`–`0x00401223` | 50 | X16 | 0 to 49 | 12,800 |
| `0x004014a0`–`0x004014a3` | 1 | X24 | 18 | 256 |
| `0x004017a0`–`0x004017a3` | 1 | X32 | 29 | 256 |
| `0x004019a0`–`0x004019a3` | 1 | X38 | 3 | 256 |
| `0x00401aa0`–`0x00401aa3` | 1 | X42 | 40 | 256 |

The sites and rows are the design's and the build's names for what was found there; the
device showed places and words.

**Whose a place is.** In the state as loaded, every group of four frames next to each
other in the census, every word and both halves were read by the six moves of S2.3 as a
memory of 64 bits, and each of the 440 loaded words looked for among them: 712,656 places
looked at. The words are at least 14 bits apart from one another and 15 from one another's
complements; a hit by chance is to be expected 3.4 × 10⁻¹¹ times over the whole search.
440 found, once each, none inverted. The search does not read the prediction.

**The prediction.** `evidence/s2_5_prediction_2026-11-23/prediction.json`, committed
(`f692832`) before the design was on the card, in a repository that was public before the
first run. It carried ten forms of the word rule — the one word more after row 20, 21, …
29 — and named 24 first.

| form: the one word more after row | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 |
|---|---|---|---|---|---|---|---|---|---|---|
| memories where it said, of 440 | 400 | 408 | 416 | 424 | **432** | 424 | 416 | 408 | 400 | 388 |

Rule by rule, under the form 24:

| rule of the prediction | read from | came |
|---|---|---|
| the six moves; the LUT positions A, B, C, D as lower word lower half, lower word upper half, upper word lower half, upper word upper half | S2.3 and S2.4, one site each | so, at all 110 sites |
| rows 0 to 49 in the half the RAM of S2.3 was found in, rows 50 to 99 in the other | two sites | so, at all 110 |
| two words a row, 2 r and 2 r + 1, and one word more somewhere between rows 20 and 30 | two sites | so, at all 110, and the one word more lies after row 24 — the form named first, and no other form fits the rows 21 to 29 |
| site column X in the (19 + X/2)-th column of 36 frames of its half | two sites, X16 and X34 | so for X16, X20, X24, X28, X30, X32, X34, X38, X42; **not for X10 and X12**, found in the (13 + X/2)-th |

| site | memory | said | found |
|---|---|---|---|
| `SLICE_X10Y7` | all four | `0x00401020`–`0x00401023`, words 14 and 15 | `0x00400d20`–`0x00400d23`, words 14 and 15 |
| `SLICE_X12Y44` | all four | `0x004010a0`–`0x004010a3`, words 89 and 90 | `0x00400da0`–`0x00400da3`, words 89 and 90 |

So the line through two columns does not hold to the left of them: between the columns of
frames of X12 and X16 lie six columns of 36 frames more than a step of one column for two
numbers gives. Both measured columns the rule was read from are at X16 or above, and so
is every column it got right. What lies in the six, and where between X12 and X16 they
are, is not shown by this: no site of X14 was probed.

**Room for part 2.** The closing says it (section 48): 48 frames with candidates, 24 reads
a state, the code run's result 222,566 words and a run of sixteen singles 219,110 of
262,144 — both can be planned.

**Bit 5 of the status.** It showed after 24 records and no other (`status_seen.json`):
the two reads that deliver each of the twelve groups of four frames above, in the state
as loaded.

| what every site held | bit 5 after the two reads of a group |
|---|---|
| what the memories are loaded with (state 0) | yes, at all twelve groups |
| all one | no |
| all zero | no |

It showed in runs 02, 03, 05, 06 and 07 — the five that read such frames — and in no
record of runs 00, 01 and 04. Cleared each time; it did not come back by itself. This is
what S2.4 showed in the frames of the shift registers: with the loaded content, and not
with a uniform one.

## What this does and does not say

- It says where each of the 440 memories is, from the word it was loaded with, and that
  each is laid out by the six moves in the state as loaded; that those places follow a
  write; and that nothing else in block type 0 does.
- It does not show that the design's number for a site is the site the build's record
  names (section 47): the names in the tables above are the build's.
- It does not say that the places are a LUT's truth table, or what a write there would
  do: nothing was written to configuration memory, and `SEU_EN` was not set.
- Nothing was compared with any database. Grading is once, at the end of S2.

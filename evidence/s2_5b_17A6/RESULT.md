# S2.5, part 2: which place is which cell, at 110 sites — EBAZ4203 `17A6`, 2026-11-24: complete

Question (docs/s2_plan.md, section 45, part 2): of the 28,160 places part 1 found, which
follows which cell of its memory — at every one of the 110 sites, and is it the cell the
six moves of S2.3 say?

**Every one of the 28,160 places follows exactly one cell, as it is, and it is the cell
its place in the loaded word says: a table for each of the 110 sites, and the 110 are one
table moved. Every cell is confirmed at every site by a run of its own: with cell n alone
set at all sites, exactly the 110 places the tables have for it — one a site — read
otherwise than with all zero, and no other bit of the 72 frames read. 256 cells, 28,160
places confirmed, no contradiction. These are outcomes 7 and 9 of section 45. CTL0 was
`0x00000501` in all seventeen runs, as in part 1's. All 110 sites read back through the
design as held, before the frames of every state and after them.**

**Read as a rule, four of its five parts hold at every site measured and one does not.**
The six moves, the LUT position, the half of the device and the word of a row are one
rule for all 110 sites. The column is not: the nine columns of sites from X16 to X42 lie
on one line among the columns of 36 frames, and X10 and X12 lie six such columns lower
than that line (`rule.json`: `one_rule` is false, and says which part).

Nothing was graded.

## The runs

On the owner's word of 2026-11-24, after part 1 was complete and stored. The host side at
commit `8a7e92f` for the code run and `554d91a` (the code run and its tables stored) for
the singles; the image the one of section 32 (19,244 bytes, sha256 `8bf3799c…2a8b`); the
sets `s2_5c` and `s2_5s` (copied in before the first run); the design `s2b.bit` from the
card. What part 1 found was taken again from its stored runs before every run (section
48), not from its two files. By section 35 the complete set of mutants was not run.
Nothing else ran on the host while the board was in use; the suite ran between the code
run and the singles, and after the chain, with `SELFMAP_NO_BOARD` set.

- Pre-check 20:58 UTC (`precheck_console.log`): the prompt, status `50033004` as part 1's
  last run had left it, `s2b.bit` on the card; a `reset`: `Model: Ebang EBAZ4203`,
  `a802000a`.
- 20:59:06–21:06:04 UTC: the code run alone (`first_run.out`). PASS; closed into the tables
  (`table/table.json`). Committed as it stood (`554d91a`); the chain starts no single
  before that.
- 21:14:55–23:03:09 UTC: the sixteen runs of the singles (`chain_to_the_end.out`), a
  `reset` before each. Complete; `ram_map.json` and `rule.json` written. Committed as it
  stood (`4db4e98`).

| run | kind | states | reads a state | writes | records | words pulled | pieces | pieces pulled again | records after which bit 5 showed |
|---|---|---|---|---|---|---|---|---|---|
| run00 | code | 18 | 24 | 960 | 436 | 222,566 | 109 | 1 | 0 |
| run01 to run16 | singles 0 to 15 (run k: cells 16 k − 16 to 16 k − 1) | 18 | 24 | 96 | 436 | 219,110 | 107 | 1 in run03, else 0 | 192 in each |

In all 3,728,326 words pulled. Every run: `anomalies=00000000`, return `0x0`, every
record's code 0, status afterwards `50033004`; the result with the board's checksum of it
and the card copy read back the same; no reply that was not whole. The design counted
every write the log has; every write went to every site at once, and no access was to one
site alone. Nothing halted and nothing was set aside.

A state reads the 24 reads that deliver the 48 frames with candidates: for each of the
twelve groups of four frames, a read of three frames that ends with the group's lowest and
a read of the other three — 72 frames a state.

## What was found

**The code run.** Eighteen states: all zero, the eight code states each followed by its
complement, all zero. 28,160 bits follow a cell as they are — exactly the candidates of
part 1, none at a place part 1 did not have, none of part 1's left over — none inverted,
none irregular; 204,544 bits still. Each place spells one cell's number, and at every site
it is the number the place has in the loaded word by which part 1 gave it its site: the
cell from the code and the site from the word, each found without the other, agree at all
28,160.

**The singles.** 256 states with one cell one at every site and every other cell zero. In
each, the bits that read otherwise than with all zero are exactly the 110 places the
tables have for that cell. 256 cells confirmed at every site; no contradiction.

**The site of S2.3 again.** `SLICE_X16Y30` is one of the 110. Its 256 entries are, place
for place and cell for cell, the 256 of `evidence/s2_3_17A6_2026-11-23/ram_map.json` —
another design, another day, the same answer.

**The tables, read as a rule** (`rule.json`; a test holds the 28,160 entries of
`ram_map.json` to this and nothing else):

- *The six moves — one rule.* A memory is one half of one word in each of four frames next
  to each other. Address 0 lies in the third of the four at bit 15 of the half word; bit 0
  of the address moves the place one frame up, bit 3 two frames down; bits 1, 2, 4 and 5
  move it 1, 2, 4 and 8 bits down. As S2.3 found at one site.
- *The position — one rule.* A site's four memories lie in two words next to each other.
  By the build's names: A the lower word, bits 15 to 0; B the lower word, bits 31 to 16; C
  the upper word, bits 15 to 0; D the upper word, bits 31 to 16. The design's memories 0,
  1, 2, 3 are on D, A, B, C at every site.
- *The half — one rule.* Rows 0 to 49 lie in the half the census's addresses have as
  `0x0040…`, rows 50 to 99 in the half `0x0000…`.
- *The word — one rule.* Row r of its half (the site's row, less 50 in the upper half) has
  the words 2 r and 2 r + 1 up to row 24, and 2 r + 1 and 2 r + 2 above it: word 50 of
  the frame is no row's. All 50 rows of a half were measured, in both halves, and the
  same row has the same words in every column measured.
- *The column — not one rule.* The four frames are the 32nd to the 35th (counted from 0)
  of a column of 36 frames, at every site. Counted among the columns of 36 frames of its
  half alone, from 0:

  | column of sites X | 10 | 12 | 16 | 20 | 24 | 28 | 30 | 32 | 34 | 38 | 42 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | the census's number of its column of frames | 26 | 27 | 36 | 38 | 41 | 44 | 45 | 47 | 48 | 51 | 53 |
  | which of the columns of 36 frames that is | 18 | 19 | 27 | 29 | 31 | 33 | 34 | 35 | 36 | 38 | 40 |
  | less X/2 | 13 | 13 | 19 | 19 | 19 | 19 | 19 | 19 | 19 | 19 | 19 |

  From X16 to X42, nine columns, a step of one column of 36 frames for two numbers of X
  holds. X10 and X12 keep that step between themselves and lie six columns lower. The
  census has eight columns of 36 frames next to each other there, its columns 26 to 33;
  X10 and X12 are the first two of them. So between X12 and X16 six columns of 36 frames
  hold no site that the numbers of X count on this line. Whether they lie before X14 or
  after it, and what they hold, is not shown: no site of X14 was probed, and only columns
  with even numbers were.

**What is measured and what is the rule's word.** 110 sites of 1,500 of their kind: one
whole column of sites, X16, in all 100 rows, and one site in each of ten other columns.
The word rule and the half rest on the 100 rows of X16 and are met by the ten sites
elsewhere; the column rests on eleven columns, of which two do not fit. For the 1,390
sites not measured the files say what the rule says and that nothing has shown it — and
for a column of sites below X16 the rule now says nothing that can be relied on.

**Bit 5 of the status.** It showed after 3,072 records, all in the singles, and it follows
one rule there without exception (`status_seen.json`; a test holds it): in a state with
one cell set, after the one read of each of the twelve groups that delivers the frame the
cell lies in — and after no other read.

| what every site held | bit 5 |
|---|---|
| all zero (first and last state of all seventeen runs) | no |
| a code state or its complement (16 states) | no |
| one cell one and every other zero (256 states) | after the read that delivers that cell's frame: 12 of the 24 reads; after the other 12, no |

For the 64 cells in the lowest frame of the four it is the first read of a group, for the
192 others the second. At the group of X16 that frame then has 50 bits set, one a site;
at the ten others one. Cleared each time; it did not come back by itself. With part 1 —
yes with the loaded words, no with all one and all zero — this is what S2.3 and S2.4
showed, now at twelve groups of frames and read by read: the bit answers to the content of
the frames a read delivers. I still have no rule for which contents, and give none; the
guess in the note of S2.4 stands as a guess, for no program and no judge.

## What this does and does not say

- It answers the RAM half of question 7 of section 1 at 110 sites: every cell has one
  bit, shown as it is, and where it lies follows from the site by the rule above — for
  the columns measured.
- The site of an entry rests on part 1 alone (the loaded word); a single confirms the cell
  of a place, not its site, because every write goes to every site. That the design's
  number for a site is the site the build's record names is not shown (section 47).
- It does not say that the places are a LUT's truth table, or what a write there would
  do: nothing was written to configuration memory, and `SEU_EN` was not set.
- Nothing was compared with any database. Grading is once, at the end of S2.

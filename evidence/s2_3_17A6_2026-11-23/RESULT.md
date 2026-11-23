# S2.3, which bit is which cell of the design's RAM — EBAZ4203 `17A6`, 2026-11-23: complete

Question (docs/s2_plan.md, section 29): of the 256 places S2.2 found, which is which cell of
the probe design's LUT RAM?

**Every cell has exactly one bit, the 256 bits are the 256 places S2.2 found, none is
inverted, and each is confirmed by a run of its own. This is outcome 1 of the code run and,
with the singles, outcome 9: "the table of the code run, and every cell confirmed by its
single". The code run set the RAM to eighteen states and decoded the table from them; four
runs then set each of the 256 cells alone, and in each of those 256 states exactly the place
the table has for the cell read otherwise than in the base state, and no other bit of the
six frames read. CTL0 was `0x00000501` in every run, as in the runs of S2.2. The RAM read
back through the design's own registers as written, before and after every pass. Nothing
was shifted.**

Nothing was graded. Which LUT of the slice a memory is, and which pin of it carries which
address bit, is not shown by this.

## The runs

On the owner's word of 2026-11-23: first for the precheck and the code run alone, then "go
on run after run, and call when something is wrong or it is done". The host side at commit
`c433f81` for the code run and `528f339` (the code run stored) for the singles; the image
19,244 bytes, sha256 `8bf3799c…2a8b`, crc32 `261627c7`, the image of section 32, on a board
here for the first time (`prober.bin`, kept by the driver); the sets `s2_3c` and `s2_3s`
(`expected_s2_3c.json`, `expected_s2_3s.json`, copied in from the build directory before the
first run); the design `s2a.bit` from the card. By the owner's rule of the same day
(section 35) the complete set of mutants was not run for this image: the tool had run the
324 mutants of S2.3 (none surviving), the ten of section 34 had had a first look. Nothing
else ran on the host while the board was in use; the tests ran between the code run and the
singles, and after the chain, with `SELFMAP_NO_BOARD` set.

- Pre-check 14:06 UTC (`precheck_console.log`): U-Boot at its prompt, `s2a.bit` on the card
  (`filesize=1fcc13`), status `a802000b`; a `reset`: `Model: Ebang EBAZ4203`, the usual fresh
  prompt, `a802000a`. Word for word as before S2.2.
- 14:07:10–14:11:13 UTC: the code run alone (`--max-new 1`; `first_run.out`). PASS; closed
  into the table (`table/table.json`). Committed as it stood (`528f339`) before anything
  else was started: the chain starts no single before that.
- 14:17:16–14:32:57 UTC: the four runs of the singles (`chain_to_the_end.out`), a `reset`
  before each (`resets_console.log`). Complete; `ram_map.json` written. Committed as it
  stood (`ace68a0`).

| run | kind | states | reads a state | accesses to the design | records | words pulled | pieces | records after which bit 5 showed |
|---|---|---|---|---|---|---|---|---|
| run00 | code | 18 | 12 | 7,799 | 220 | 121,278 | 60 | 0 |
| run01 | singles 0 (cells 0–63) | 66 | 2 | 21,767 | 136 | 108,894 | 54 | 64 |
| run02 | singles 1 (cells 64–127) | 66 | 2 | 21,767 | 136 | 108,894 | 54 | 64 |
| run03 | singles 2 (cells 128–191) | 66 | 2 | 21,767 | 136 | 108,894 | 54 | 64 |
| run04 | singles 3 (cells 192–255) | 66 | 2 | 21,767 | 136 | 108,894 | 54 | 64 |

Every run: `SM9 end status=00000001 … anomalies=00000000`, return `0x0`, every record's
code 0, status afterwards `50033004`; the result with the board's checksum of it and the
card copy read back the same; no piece pulled again, no reply that was not whole. Nothing
halted and nothing was set aside.

## What was found

**The code run.** The column of the four frames, twelve reads of three frames, in each of
eighteen states. 256 bits follow a cell — each the same as exactly one cell in every state,
and no two the same cell; 116,096 bits read the same in all eighteen states; none follows a
cell inverted, none changes without following one. The 256 are the places of
`candidates.json`, none more, none missing, none the other way up.

**The singles.** The two reads that deliver the four frames (`0x0040121e` and
`0x00401221`, three frames each), in the base state, then with each cell alone set, then
the base state again. In each run 64 bits follow a cell and 19,328 are still; for each of
the 256 cells the one bit that reads otherwise than in the base state is the place the
table has for it. 256 confirmed, no contradiction.

**The table, read as a rule.** The table is `ram_map.json` (and `table/table.json`, written
when the code run was closed and not touched since). It can be said in a few lines, and a
test holds the 256 entries to this and nothing else:

| memory (bit of the data register) | word of the frame | bits of the word | address 0 at |
|---|---|---|---|
| 0 | 62 | 31 down to 16 | `0x00401222`, bit 31 |
| 1 | 61 | 15 down to 0 | `0x00401222`, bit 15 |
| 2 | 61 | 31 down to 16 | `0x00401222`, bit 31 |
| 3 | 62 | 15 down to 0 | `0x00401222`, bit 15 |

and for every memory alike, a set bit of the RAM's address moves the place so:

| address bit | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| frames | +1 | | | −2 | | |
| bits of the word | | −1 | −2 | | −4 | −8 |

So two bits of the address choose one of the four frames and the other four choose one of
sixteen bits of a half word; a memory is a half word in each of four frames. "Address" is
what the design's address register held; which pin of a LUT that is, the device did not
show. The build's own record (`pl/s2a/build.json`, in `ram_map.json` under
`as_the_build_placed_them`) says memory 0 is the D LUT of `SLICE_X16Y30`, 1 the A, 2 the B,
3 the C — what was placed, not something read from the device.

**Bit 5 of the status.** Not asked for, and seen plainly (`status_seen.json`; a test holds
it):

- In the singles, **with one cell set, bit 5 showed after the read that delivers the frame
  in which that cell's bit lies, and not after the other read** — in all 256 states, 512
  reads, without exception. It was cleared each time (`50033024`, then `50033004`) and did
  not come back by itself.
- In the base states (no cell set; four reads a run) it did not show.
- In the code run it did not show at all: there a frame has none, 32 or 64 of its cells set
  in every state. Nor did it show at these frames in S2.2 (none or 64 set).
- What S2.2 saw — bit 5 after two reads elsewhere in block type 0, alike in all three
  states (section 28) — is another thing and is not explained by this.

That is what was seen. A guess, from general knowledge of the device family and so for no
program and no judge: UG585 names the bit `PCFG_SEU_ERR`; a check of each frame read back
against check bits made when the design was built would notice one changed bit, and could
miss 32 or 64 changed bits laid out as regularly as these. If that is what it is, the bit is
a second witness, independent of the comparison of frames, that a frame is one bit away
from what was loaded. Nothing rests on it here.

## What this does and does not say

- It answers the LUT RAM half of question 7 of section 1, for this design at this one
  site. The shift registers are S2.4; other sites are S2.5.
- It does not say that the places are LUT contents in general, or that a write there would
  do what the read suggests: nothing was written to configuration memory, and S4 is where
  that is asked.
- Nothing was compared with any database. Grading is once, at the end of S2.

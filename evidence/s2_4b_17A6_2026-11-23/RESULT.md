# S2.4, part 2: which place is which output of the shift registers — EBAZ4203 `17A6`, 2026-11-23: complete

Question (docs/s2_plan.md, section 37, part 2): of the 256 places part 1 found, which
follows which output of the design's four shift registers, and which way?

**Every one of the 256 places follows exactly one output, as it is or inverted, and every
output is confirmed by a run of its own in all of its places. This is outcome 10 of the
code run and, with the singles, outcome 12. The code run gave the registers seventeen
contents and decoded the table from them; two runs then turned each of the 128 outputs
alone, and in each of those 128 states exactly the places the table has for that output —
all of them, each the way the table says — read otherwise than with the loaded content,
and no other bit of the six frames read. CTL0 was `0x00000501` in every run, as in part
1's. The registers read back through the design as shifted before and after every pass;
the RAM, never written, read zero.**

**The table is what section 42 said beforehand it would be**, in all three parts, the
guess among them.

Nothing was graded. Which stage of a primitive an output is, and which LUT of the slice a
register is, is not shown by this.

## The runs

On the owner's word of 2026-11-23, after the review of section 43. The host side at commit
`4dd950e` for the code run and `689cf8a` (the code run and its table stored) for the rest;
the image the one of section 32 (19,244 bytes, sha256 `8bf3799c…2a8b`); the sets `s2_4c`,
`s2_4s`, `s2_4p` (copied in before the first run); the design `s2a.bit` from the card. By
section 35 the complete set of mutants was not run. Nothing else ran on the host while the
board was in use; the suite ran between the code run and the others, and after the chain,
with `SELFMAP_NO_BOARD` set.

- Pre-check 20:16 UTC (`precheck_console.log`): the prompt, status `50033004`, `s2a.bit` on
  the card; a `reset`: `Model: Ebang EBAZ4203`, `a802000a`.
- 20:16:57–20:20:32 UTC: the code run alone (`first_run.out`). PASS; closed into the table
  (`table/table.json`). Committed as it stood (`689cf8a`); the chain starts no single before
  that.
- 20:25:25–20:32:51 UTC: the two runs of the singles and the pairs
  (`chain_to_the_end.out`), a `reset` before each. Complete; `srl_map.json` written.
  Committed as it stood (`2aee241`).

| run | kind | states | reads a state | shifts | records | words pulled | pieces | records after which bit 5 showed |
|---|---|---|---|---|---|---|---|---|
| run00 | code | 17 | 12 | 512 | 208 | 105,912 | 52 | 4 |
| run01 | singles 0 (cells 0–63) | 66 | 2 | 2,112 | 136 | 87,390 | 43 | 132 |
| run02 | singles 1 (cells 64–127) | 66 | 2 | 2,112 | 136 | 87,390 | 43 | 132 |
| run03 | pairs | 6 | 2 | 192 | 16 | 10,230 | 5 | 12 |

Every run: `SM9 end status=00000001 … anomalies=00000000`, return `0x0`, every record's
code 0, status afterwards `50033004`; the result with the board's checksum of it and the
card copy read back the same; no piece pulled again, no reply that was not whole. The
design counted every shift the log has. Nothing halted and nothing was set aside.

## What was found

**The code run.** The column of the four frames, twelve reads of three frames, in
seventeen states. 128 bits follow a cell as they are and 128 inverted — every one of the
256 the way it followed the uniform states in part 1, none at a place part 1 did not have,
none of part 1's left over; 116,096 bits still; none irregular.

**The singles.** With each of the 128 cells alone the other way than loaded, the bits
that read otherwise than with the loaded content are exactly the places the table has for
that cell: two for 120 cells, one for four, three for four. 128 confirmed, no
contradiction.

**The table, read as a rule.** It is `srl_map.json` (256 entries, an entry a place; and
`table/table.json`, written when the code run was closed). Read by the rule S2.3 found for
a memory of the RAM, and a test holds the 256 entries to this and nothing else: register k
is a half word in each of the four frames `0x00001820`–`0x00001823` — 0: word 40, bits 15
to 0; 1: word 40, bits 31 to 16; 2: word 41, bits 15 to 0; 3: word 41, bits 31 to 16 —
and of its 64 places

| the place of address | follows | which way |
|---|---|---|
| 2 a + 1, for a from 0 to 31 | output a | as it is |
| 2 a + 2, for a from 0 to 30 | output a | inverted |
| 0 | output 0 | inverted — once anything has been shifted in |

So an output has a place as it is and, the next address up, a place inverted; output 31
has no inverted place, and output 0 has two. "Output a" is what the design's address
register chooses — the bit shifted in a + 1 shifts ago.

**Before any shift.** In the code run's first state — the registers as loaded, nothing
shifted yet — two places read otherwise than their output's loaded content gives:
`0x00001822/40/15` and `0x00001822/41/15`, the places of address 0 of registers 0 and 2.
Both read one; their outputs 0 are loaded with one, and inverted that would be zero. The
same places of registers 1 and 3, whose outputs 0 are loaded with zero, read one and fit.
So before anything is shifted in, the place of address 0 reads one whatever the register
was loaded with; afterwards it reads the opposite of what was last shifted in. The table
and the description say so of the two places; an entry's evidence is of the shifted
states.

**What was said beforehand, and what came.** Section 42 named four things: output a at
address 2 a + 1 (part 0's prediction); address 2 j following output j − 1 inverted (the
note of section 38); hence 120 cells with one place each way and the four outputs 31 with
one; and, as a guess, address 0 following output 0 inverted after shifts and reading one
before, with exactly those two places reading otherwise before any shift. All four are as
the board showed.

**The pairs.** Cells 0 and 1 turned: three bits of `0x00001822` and two of `0x00001823`
change. Cells 0 and 4: one bit in each of `0x00001820`, `0x00001821`, `0x00001823`, two in
`0x00001822`. Cells 0, 1, 2: four and three. Cells 0, 1, 2, 3: one, four and four. No bit
followed no cell.

**Bit 5 of the status.** It showed after the two reads that deliver the four frames
(`0x0000181e`, `0x00001821`) — always after both or after neither — and after no other
record (`status_seen.json`; a test holds it):

| what the registers held | bit 5 after those two reads |
|---|---|
| what they are loaded with, nothing shifted (code run, first state) | yes |
| the same, shifted in (code run, last state; singles and pairs, first and last) | yes |
| that with one cell turned (128 states of the singles) | yes |
| that with two, three or four cells turned (the pairs) | yes |
| all zero (code run; part 1) | no |
| all one (part 1) | no |
| a code state or its complement (14 states) | no |

Cleared each time, and it did not come back by itself. So in these frames it does not
answer to whether anything was ever shifted, nor to a difference of one bit from what was
loaded: it shows with the loaded content and near it, and not with the regular contents.
With S2.3's finding in the RAM's frames — there with one cell set and not with none, 32 or
64 — I have no rule that covers both, and give none. A guess, from general knowledge of
the device family and so for no program and no judge: a check of each frame read back
against check bits, which comes out even for contents as regular as the uniform and the
code states and not otherwise. Nothing rests on it.

## What this does and does not say

- It answers the shift-register half of question 7 of section 1, for this design at this
  one site: all 32 outputs of each register are seen, each at one place as it is, and all
  but the last at a second place inverted.
- It does not say that the places are a LUT's truth table, or what a write there would do:
  nothing was written to configuration memory.
- Nothing was compared with any database. Grading is once, at the end of S2.

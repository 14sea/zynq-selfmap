# S2.4, part 1: where the shift registers' bits are — EBAZ4203 `17A6`, 2026-11-23: complete

Question (docs/s2_plan.md, section 37, part 1): which bits of configuration memory follow
the design's four shift registers, and does reading leave the registers as they were?

**256 bits follow them, all in four frames next to each other, `0x00001820` to
`0x00001823`, in words 40 and 41: 128 as they are and 128 inverted. Every other bit of
block type 0 — 12,488,192 — read the same in all three states. This is outcome 2 of the
five section 37 named for part 1. All 3,864 addresses were read with the registers all
zero, all one, all zero, in eight runs; every run passed. The registers read back through
the design as shifted, at all 32 outputs, before the frames of every state and after them;
the RAM, never written, read zero. CTL0 was `0x00000501` in every run, as in S2.2's.**

**The prediction made before the board was asked is a hit: each of the 128 places it named
is a candidate that follows as it is.** No frame, in the first all-zero state, reads
otherwise than S2.2 stored it two days before, outside the 256.

Nothing was graded. Which output of which register a place is, is not known from this;
that is part 2.

## The runs

On the owner's word of 2026-11-23, after the review of section 40. The host side at commit
`97fbaf9`; the image the one of section 32 (19,244 bytes, sha256 `8bf3799c…2a8b`), on a
board for the second step — S2.4 has no image of its own; the set `s2_4f`
(`expected_s2_4f.json`, copied in before the first run); the design `s2a.bit` from the
card. By section 35 the complete set of mutants was not run. Nothing else ran on the host
while the board was in use; the suite ran between the first run and the others, and after
the chain, with `SELFMAP_NO_BOARD` set.

- Pre-check 16:22 UTC (`precheck_console.log`): the prompt, status `50033004` as S2.3's
  last run had left it, `s2a.bit` on the card; a `reset`: `Model: Ebang EBAZ4203`,
  `a802000a`.
- 16:23:00–16:30:31 UTC: the run of share 0 alone (`first_run.out`). PASS. Committed as it
  stood (`a189c0b`); the chain starts no second run before that.
- 16:34:40–17:24:00 UTC: the other seven (`chain_to_the_end.out`), a `reset` before each.
  Complete; `candidates.json` written. Committed as it stood (`5e1699d`).

| run | share | reads a state | frames a state | first | last | records | words pulled | pieces pulled again | bits that follow |
|---|---|---|---|---|---|---|---|---|---|
| run00 | 0 | 174 | 516 | `0x00000000` | `0x0000071b` | 526 | 254,052 | 0 | 0 |
| run01 | 1 | 174 | 516 | `0x00000780` | `0x00000ea3` | 526 | 254,052 | 3 | 0 |
| run02 | 2 | 174 | 520 | `0x00000f00` | `0x00001623` | 526 | 254,052 | 2 | 0 |
| run03 | 3 | 176 | 524 | `0x00001680` | `0x004001a3` | 532 | 256,932 | 0 | 256 |
| run04 | 4 | 172 | 508 | `0x00400200` | `0x00400923` | 520 | 251,172 | 1 | 0 |
| run05 | 5 | 176 | 524 | `0x00400980` | `0x004010a3` | 532 | 256,932 | 0 | 0 |
| run06 | 6 | 172 | 512 | `0x00401100` | `0x00401823` | 520 | 251,172 | 0 | 0 |
| run07 | 7 | 82 | 244 | `0x00401880` | `0x00401ba9` | 250 | 121,572 | 0 | 0 |

In all 1,899,936 words pulled, each run's result with the board's checksum of it and the
card copy read back the same; six pieces of results were pulled a second time and then had
their checksum. No reply of a short read was not whole. Every run: `SM9 end
status=00000001 … anomalies=00000000`, return `0x0`, every record's code 0, status
afterwards `50033004`. In every run 96 shifts, which the design counted as 96, and no
write to the RAM. Nothing halted and nothing was set aside. These are the first runs in
which the prober shifted the design's shift registers on a board.

## What was found

**The candidates.** 256 places, all read by the run of share 3, 64 in each of the four
frames. Read by the rule S2.3 found for a memory of the RAM (a test holds the 256 to this
and nothing else): register k is a half word in each of the four frames — 0: word 40, bits
15 to 0; 1: word 40, bits 31 to 16; 2: word 41, bits 15 to 0; 3: word 41, bits 31 to 16 —
64 places, and **all 64 follow**: the 32 at the odd addresses as they are, the 32 at the
even addresses inverted. None is one of the RAM's 256 places.

**The prediction (part 0).** It named the 32 places at the odd addresses of each register,
128 in all, as the places of the outputs. All 128 are candidates and all follow as they
are. Whether output a is at address 2 a + 1, as it also said, the uniform states cannot
show; part 2 asks that.

**What the note beside the prediction added.** It said the even addresses hold the
opposite of the word moved up by one and predicted that after shifts even address 2 j
(j ≥ 1) reads the opposite of odd address 2 j − 1; of even address 0 it predicted nothing.
What part 1 shows: all 32 even addresses of every register follow inverted, address 0 among
them. That fits the note and does not test it — with every output holding the same, an
even address cannot be told to follow one output rather than another. Part 2 can tell.

**Across two days.** In the first all-zero state every frame of block type 0 reads as S2.2
stored it on 2026-11-22, outside the 256 places: not one bit otherwise in 3,864 frames.

**Bit 5 of the status did not show — after no record of any run.** Not after the two reads
that deliver these four frames either (`0x0000181e` and `0x00001821`, records 46, 47, 222,
223, 398 and 399 of the run of share 3) — the very reads after which S2.2 saw it in all
three of its states. Then the registers held what they were loaded with and had never been
shifted; here they held all zero or all one. So the bit does not answer to these frames as
such, and not simply to their differing from what was loaded: here they differ from it in
many bits. I do not explain it. Part 2 reads these frames with the registers as loaded
again, shifted in again, and one bit away from that; it will say more.

## What this does and does not say

- It answers "where" for the shift registers at this one site, and "does reading disturb
  them": no.
- It does not say which place is which output, nor which of the two kinds of place — as it
  is, inverted — an output has; that is part 2, and the table's form is point 6 as the
  owner changed it.
- Nothing was written to configuration memory. Nothing was compared with any database.

# S2.4, part 0: a prediction, made before the board was asked — 2026-11-23

`prediction.json` is what `host/s2_4_predict.py` printed, on the host alone, from stored
results (docs/s2_plan.md, section 37, part 0; section 38). No serial port was opened and
nothing was graded.

## What it says

**Found: each of the four loaded words once, all in one group of four frames and in one
arrangement.**

| shift register | loaded word | frames | word | bits | arrangement |
|---|---|---|---|---|---|
| 0 | `0xA5C30F69` | `0x00001820`–`0x00001823` | 40 | 15 down to 0 | the odd addresses, in order, as it is |
| 1 | `0x0F1E2D3C` | the same | 40 | 31 down to 16 | the same |
| 2 | `0x13579BDF` | the same | 41 | 15 down to 0 | the same |
| 3 | `0xFEDCBA98` | the same | 41 | 31 down to 16 | the same |

712,656 places were looked at (3,864 frames as loaded; every four next to each other, every
word, both halves), in the 24 arrangements section 37 fixed beforehand. By chance 0.016 hits
were to be expected in all; there are four, and no fifth.

So the prediction for part 1 is: **the shift registers' bits are in words 40 and 41 of the
frames `0x00001820` to `0x00001823`; register k is a half word there as a memory of the RAM
is in its frames; and output a of a register — the bit shifted in a + 1 shifts ago — is at
the place the rule of S2.3 gives address 2 a + 1.**

It decides nothing. Part 1 reads all of block type 0 whatever this says, and a test will
hold this file against what the board shows: a hit or a miss.

## Seen afterwards, and so not part of the prediction as it was fixed

Two things I saw when I looked at the four places after the search. Neither was asked of
the search beforehand; I set them down before the board is asked so that they cannot be
bent to fit it.

1. **The even addresses are not empty.** At each of the four places the 32 even addresses
   hold the opposite of the loaded word moved up by one: even address 2 j holds the
   opposite of bit j − 1 of the word, for j from 1 to 31, and even address 0 holds a one
   (`0xB479E12D`, `0xE1C3A587`, `0xD950C841`, `0x02468ACF`). A second prediction, then, and
   this one is about what moves: **after shifts, even address 2 j (j ≥ 1) reads the opposite
   of odd address 2 j − 1** — two bits for each of the outputs 0 to 30, one of them
   inverted, and one for output 31. What even address 0 follows I do not predict.
2. **These are the frames after which S2.2 saw bit 5.** Bit 5 of the status showed in S2.2
   after two reads only, `0x0000181e` and `0x00001821`, three frames each, in all three
   states (section 28): the two reads that deliver exactly these four frames. It was not
   explained then. It is a second pointer to the same place, from another side.

Every other word of these four frames reads zero as loaded.

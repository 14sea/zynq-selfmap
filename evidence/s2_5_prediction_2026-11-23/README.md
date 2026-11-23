# S2.5, part 0: a prediction, made before the board was asked — 2026-11-23

`prediction.json` is what `host/s2_5_predict.py` printed, on the host alone, from stored
results and records (docs/s2_plan.md, sections 45 and 46). No serial port was opened and
nothing was graded. The design it speaks of, `s2b`, has not been on a board.

## What it says

For each of the 440 memories of `s2b` — four at each of 110 sites — the four frames it
would lie in, its word and its half of the word; and with the six moves of S2.3 the place
of each of its 64 cells: 28,160 places.

It rests on three rules read from the two sites measured so far (the RAM of `s2a` at
`SLICE_X16Y30`, its shift registers at `SLICE_X34Y70`), each held against both before it
is used:

| rule | what it says | how much of it two sites can carry |
|---|---|---|
| the column | site column X lies in the (19 + X/2)-th column of 36 frames of its half, counted from 0; a memory is in that column's last four frames | two points fix the line; that it is a line is the guess |
| the half and the word | rows 0–49 are one half, rows 50–99 the other; a row has two words; one word more than twice the rows lies between rows 20 and 30 | where the one word lies is open: ten forms are carried, the middle one (after row 24) named first |
| the position | A: the row's lower word, lower half; B: its upper half; C: the upper word, lower half; D: its upper half | both sites agree, eight memories of eight |

Under it the eleven columns of sites lie at these columns of frames (first frame of the
four, lower half / upper half):

| site column | 10 | 12 | 16 | 20 | 24 | 28 | 30 | 32 | 34 | 38 | 42 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lower half `0x0040…` | `1020` | `10a0` | `1220` | `1320` | `14a0` | `1620` | `16a0` | `17a0` | `1820` | `19a0` | `1aa0` |
| upper half `0x0000…` | the same low sixteen bits |

For the one site that is already known, `SLICE_X16Y30`, it gives exactly the 256 places
S2.3 found. That is no test of it — it was read from them — and is said so that nobody
takes it for one.

## What it leaves open, on purpose

Nineteen sites lie in rows 21 to 29 of their half — eighteen of the column, and
`SLICE_X32Y29`. For those the word depends on where the one word more lies, and the file
gives the word under the form named first and under the others. Whatever the board shows
there chooses among ten forms, or none.

## It decides nothing

Part 1 reads all of block type 0 and looks for every memory's loaded word in every group
of four frames, every word, both halves — without this file. Then this file is held
against what was found: memory by memory, a hit or a miss.

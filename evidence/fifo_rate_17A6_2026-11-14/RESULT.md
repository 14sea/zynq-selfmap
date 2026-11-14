# Counting frame reads until the receive FIFO overflows — EBAZ4203 `17A6`, 2026-11-14

Question (docs/s1b_plan.md, section 15, point 1; the owner: "first 1 and 4"): the walk of
S1b.1 was stopped twice by an overflow of the PCAP receive FIFO. How often does that happen, and
on what does it depend?

**Answer so far: it depends on the walk. Through the walk's code (stage 4 of the prober) 5 runs
out of 5 overflowed, after 8 to 28 frame reads — 5 overflows against 84 clean frame reads.
Through the code of stages 2 and 3, 16 runs made 624 frame reads with no overflow at all,
including the same pairs of reads, at the same addresses, read for the first time after a load.
The image is the same in all of them, and the routine that makes a read is one and the same
machine code for every stage. Why the walk overflows is not known.**

## What was run

One image throughout: `prober.bin`, 10,510 bytes, sha256 `e26e6535…` (the reviewed image of
S1b.1, commit `19518ab`). A U-Boot `reset` and a fresh load of the PL design before every run.
Every result below is from a copy with the board's crc32 (pulled over the console, or fetched
read-only from the card file when the pulls came back damaged); `summary.json` has one line per
run. The parameter sets other than the walk were added to the run script the same evening
(commits `1bdae54`, `c300b3c`, `f3f275b`, and the one after); they are parameters for the
prober's stages 2 and 3, not new prober code.

| set | what it does | path | runs | clean frame reads | overflows |
|---|---|---|---|---|---|
| `rate1` | 128 reads of one frame, over `0xb98..0xb9a` in turn | stage 2 | 1 | 130 | 0 |
| `rate3` | 128 reads of three frames from `0xb98` | stage 2 | 1 | 130 | 0 |
| `ratep` | 64 times: the pad alone, then the frame, at one address (`0xb98..0xb9a`) | stage 3 | 2 | 132 | 0 |
| `ratew` | the same pairs at `0xb80..0xb87`, eight times round | stage 3 | 2 | 132 | 0 |
| `ratef` | the same pairs at `0xb80..0xb87`, once: each frame read for the first time after the load | stage 3 | 10 | 100 | 0 |
| the walk, as in S1b.1 | from `0xb80`: the pad alone, then the frame, at each address the device names | stage 4 | 5 (two of them the runs of S1b.1) | 84 | 5 |

The five overflows, all in a read of 202 words (a pad and one frame), `INT_STS` `50070004`
each time:

| run | stopped at | frame reads before it | words short |
|---|---|---|---|
| S1b.1 run 1 | the frame at `0xb9a` | 28 | 10 |
| S1b.1 run 2 | the frame at `0xb87` | 8 | 10 |
| walk run 3 | the reference frame `0xb99`, read again after 16 frames | 17 | 2 |
| walk run 4 | the frame at `0xb8a` | 11 | 10 |
| walk run 5 | the frame at `0xb92` | 20 | 2 |

In each failing read the words that did arrive are the right ones with one or two words missing
at one or more places in the middle (the rest follows shifted), not a read cut off at its end:
the DMA was, for a moment, slower than the PL was sending.

## What this rules out

- *The number of reads.* 130 in a row went by clean, twice.
- *The length of a read.* Three frames in one read (404 words): 130 clean.
- *The pair the walk makes* — the pad alone, then the frame, at one address: 264 pairs clean.
- *The addresses.* The same pairs at `0xb80..0xb87`, where the walk overflowed: clean.
- *Reading a frame for the first time after a load*: 100 such reads clean.
- *A slower poll.* The number of polls until a clean transfer completes has the same distribution
  in the walk as in the other sets (202 words: 5 or 6; 101 words: 3 or 4).
- *Another copy of the code.* The image has one `read_op` and one `dma`; the compiler made no
  separate copy for the walk.

What is left is something the walk's path does around a read that the other stages do not — and
it is not visible in the records. The records do not say what.

## What the walks did read, between them

26 addresses, `0xb80..0xb99`, at least once each (`0xb80..0xb86` in all five runs): at every one
the device named the next number, and wherever two runs read the same frame they read the same
content. None reached the end of the column.

## On the host side

- The run script's pull of a result over the console came back damaged in 11 of 28 attempts this
  evening (the two runs of S1b.1 included). The new retry (at most three pulls, each recorded)
  got the board's copy in every run of this series but two: in one all three attempts were
  damaged, in the other two were and the adapter then dropped off the host. Those two results
  were fetched from the card file in pieces, each piece checked against the board's crc32
  (`recover.py`).
- The serial adapter dropped off this host three times in the evening. The second and third time
  the host was under heavy load from a mutant run started alongside the board work — the kernel
  log shows soft lockups — which was a mistake of scheduling and is not repeated: nothing heavy
  runs on the host while the board is being talked to.
- The judge fails `ratew` and `ratef` for one reason only, as intended: their frames have no
  known answer.
- In walk run 3 the overflow fell on a read of the reference frame, and the prober reported
  status `0x300`, "the reference frame changed", where the record says an interface failure
  (`0x21`). The stop is right; the label is misleading. Not changed here.

Files: `series.py` (how the runs were driven), `recover.py`, `summary.json`; one directory per
run with `console.log`, `header.bin`, `run.json`, and `result.bin` and `verdict.json` either
there or in `<run>_recovered/`; `resets_console.log`.

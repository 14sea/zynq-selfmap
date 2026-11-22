# S2.2, block type 0 in three states of the design's RAM — EBAZ4203 `17A6`, 2026-11-22: complete

Question (docs/s2_plan.md, section 19): is the RAM of the probe design seen in readback, at
which addresses, and does reading disturb it?

**It is seen, and reading does not disturb it. This is outcome 1 of the ten section 19 named
beforehand, and with it outcome 9. All 3,864 addresses of block type 0 the census has were
read in the states all zero, all one, all zero, three frames a read, in eight runs; every run
PASS. 256 bits followed the state — as many as the design's RAM has cells — none inverted,
none restless; the other 12,488,192 bits read the same in all three states. The 256 lie in
four frames next to each other, `0x00401220` to `0x00401223`, 64 in each: every bit of words
61 and 62. The RAM read back through the design's own registers as written, before and after
every pass. CTL0 was `0x00000501` at the start and the end of every run. Bit 5 of the status
showed after two reads in one run — not the reads of those four frames — and was cleared
each time.**

Nothing was graded. Which cell of the RAM a place is, is not known from this; that is S2.3.

## The runs

On the owner's word of 2026-11-22 for the chain (section 20, point 7). The host side at
commit `b9c0398`; the image 16,680 bytes, sha256 `94ad860c…6f50`, crc32 `ed47e7ab`, the
image of section 25, on a board here for the first time (`prober.bin`, kept by the driver);
the set `s2_2` (`expected_s2_2.json`, copied in from the build directory after the chain
closed; each run's record has the parameter words and the list as sent); the design
`s2a.bit` from the card, crc32 in RAM `6a1efe06` at every load. The complete set of mutants
had run on this image (section 27). Nothing else ran on the host while the board was in
use; the tests ran between runs, when nothing was being sent.

- Pre-check 15:25 UTC (`precheck_console.log`): U-Boot at its prompt, `s2a.bit` on the card
  (`filesize=1fcc13`); the status was `a802000b` — the board had been switched off since
  S2.1. A `reset`: the usual fresh prompt, `a802000a`.
- 15:25:43–15:33:14 UTC: the first run alone (`--max-new 1`; `first_run.out`). PASS, no
  candidate. Committed as it stood (`335e62d`) before anything else was started.
- 15:36:07–15:36:52 UTC: the chain started for the rest (`chain_to_the_end.out`) and
  **halted at its second run** — see below. Committed as it stood (`6b53e1d`). Nothing was
  sent to the board after the halt.
- The owner, asked: the run set aside, the chain taken up again; nothing taken from the
  board's memory by hand, the run script as it is. `halted_at_run01/` (`6541ce5`).
- Pre-check 16:12 UTC (`precheck_taken_up_console.log`): the prompt, status `50033004` as the
  stopped run had left it; a `reset`; `a802000a`.
- 16:12:23–17:01:07 UTC: the chain from share 1 to the end (`chain_taken_up.out`), seven
  runs, a `reset` before each. Complete. Committed as it stood (`94cd660`).

| run | share | reads | frames | first | last | records | candidates | pieces pulled again |
|---|---|---|---|---|---|---|---|---|
| run00 | 0 | 174 | 516 | `0x00000000` | `0x0000071b` | 526 | 0 | 2 |
| run01 | 1 | 174 | 516 | | | 526 | 0 | 0 |
| run02 | 2 | 174 | 520 | | | 526 | 0 | 0 |
| run03 | 3 | 176 | 524 | `0x00001680` | `0x004001a3` | 532 | 0 | 2 (one piece, twice) |
| run04 | 4 | 172 | 508 | | | 520 | 0 | 3 |
| run05 | 5 | 176 | 524 | | | 532 | 0 | 0 |
| run06 | 6 | 172 | 512 | `0x00401100` | `0x00401823` | 520 | 256 | 3 |
| run07 | 7 | 82 | 244 | | | 250 | 0 | 0 |

(The first and last address of every share are in each run's record; the table has those
used below.) In all: 1,300 reads a state, 3,864 frames a state, 3,932 records, 1,911,040
words pulled, each run's result with the board's checksum of it and the card copy read back
the same. No reply of a short read was not whole. Every run: `SM8 end status=00000001 …
anomalies=00000000`, return `0x0`, status afterwards `50033004`.

## What the runs say

- **The candidates** (`candidates.json`, written by the driver when the chain closed): 256,
  all in run06, all "as written" (0 in the first state, 1 in the second, 0 in the third):

  | address | word | bits |
  |---|---|---|
  | `0x00401220` | 61, 62 | all 32 of each |
  | `0x00401221` | 61, 62 | all 32 of each |
  | `0x00401222` | 61, 62 | all 32 of each |
  | `0x00401223` | 61, 62 | all 32 of each |

  The design has four memories of 64 bits; here are four frames with 64 bits each. That one
  frame is one memory is not shown by this step: all cells were written alike.
- **Every other bit still**: 12,488,192 of the 12,488,448 bits of block type 0 read the same
  in all three states. No bit differed between the two all-zero states.
- **Reading does not disturb the RAM**: after each of the 24 passes (three a run) the design
  read its RAM back, all 64 addresses of all four memories, as written. The design's counter
  ran; the shift registers held the four words they are loaded with and were not shifted;
  the design counted 192 writes to the RAM a run and no shift. 11,344 accesses to the design
  in all, none wrong.
- **CTL0** `0x00000501` at all 16 readings (bit 8 set: by the register's word, not masked).
- **The reference frame** `0xb99`: the same at the start and at the end of every run (it is
  an all-zero frame under this design, as section 19 said).
- 405 of the 3,864 frames are not all zero under this design.

## Bit 5 of the status (outcome 9)

`status_seen.json`: 19,676 status words in the eight verdicts; one bit outside the error mask
and the usual word, bit 5 (`PCFG_SEU_ERR` in UG585's table), in one run.

- run03, the reads of the list at **`0x0000181e`** (frames `0x181e`–`0x1820`) and
  **`0x00001821`** (frames `0x1821`–`0x1823`), in each of the three states: the status was
  `50033004` at the start of the read, `50033024` from the next reading on and after the
  read; the prober cleared bit 5 and read `50033004`. Six times in all; never still set
  after clearing; after none of the other 3,894 reads.
- The reads before and after them in the list (`0x0000181b`, `0x00001880`) delivered frames
  that are all zero and raised nothing. Of the six frames of the two reads, five are not all
  zero (`0x181f` is). Many other reads delivered frames that are not all zero and raised
  nothing.
- **It did not come with the frames that hold the RAM.** The reads of `0x0040121e` and
  `0x00401221` in run06, which deliver the four frames with the candidates, raised nothing
  in any state — also not in the second, when the RAM held what it was not loaded with.
- The two reads that raised it deliver the last six frames of the column at `0x1800`; the
  candidates lie in the last four frames of the column at `0x401200`. Both columns have 36
  frames. That is an observation of numbers; nothing more is known here.
- Under the carrier design these addresses were read many times in S1b with no such bit.
  Until now the bit had been seen only with frames of block type 1 (S1b.4).

What raises it is not known. It is not an error bit of the interface, the prober does not
stop on it, and `SEU_EN` was clear throughout.

## The run that stopped (`halted_at_run01/`)

The first try of share 1, 15:36 UTC. The prober ran and reported on the console as every
other run did (`SM8 end status=00000001 records=0000020e anomalies=00000000`, return `0x0`).
The dump of the result header, `md.l 10000000 40`, came back with stretches of characters
missing, and of the prompt after it only the first letter arrived. The run script stops when
no prompt comes — it does not ask again, because the state of the console is not known
(docs/s1b_plan.md, section 43) — so nothing was saved to the card and nothing pulled; the
chain halted. The result of that run was left in the board's memory and is gone with the next
`reset`. The share was run again as run01 of the chain and passed.

This is a loss on the console between the board and this host, as in run 51 of S1b.3; there
the prompt had arrived. It is the first time in the 196 stored runs that a prompt was lost.

## What is stored here

`run00` … `run07`: each as the run script left it (`console.log`, `header.bin`, `list.bin`,
`result.bin`, `run.json`, `verdict.json`), with the driver's `runNN.out`. `chain.json`,
`candidates.json`: the driver's, at the close. `prober.bin`, `expected_s2_2.json`: what the
runs were made with. `precheck_console.log`, `precheck_taken_up_console.log`,
`resets_console.log`: everything sent to the board outside the runs. `first_run.*`,
`chain_to_the_end.*`, `chain_taken_up.*`: the three starts of the driver, their output and
times. `halted_at_run01/`: the stopped run, moved and not altered. `status_seen.json`: the
listing of status bits. One test assesses the chain again from the raw words
(`tests/test_board_evidence.py`).

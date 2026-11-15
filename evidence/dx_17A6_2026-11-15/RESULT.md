# What in the walk overflows the receive FIFO — EBAZ4203 `17A6`, 2026-11-15

Question (docs/s1b_plan.md, section 17): the walk of S1b.1 overflowed the PCAP receive FIFO in
five runs of five; the same reads made through stages 2 and 3 did not in 624. Is it where the
read lies on the stack, or how many different frames are read?

**Answer: it is where the read lies on the stack; it is not the number of different frames.
The stage-3 loop read all 26 frames of the walk's first pass three times over without an
overflow, and overflowed in five runs of six once nothing but its stack depth was changed. The
walk ran to its end, PASS, three times of three with 24 more bytes of stack beneath its reads.
Over the 18 runs, every one of the 9 overflows fell in a read whose polling variable lay at an
address that is 24 modulo 32 (728 such reads, at three different addresses); none fell in the
504 reads where it lay at 0 modulo 32 (two different addresses). Only those two residues were
tried. Why the position matters is not known.**

## What was run

One image throughout: `prober.bin`, 11,262 bytes, sha256 `17ad8b14…5682`, crc32 `f0912724`
(commit `ce02bd9`, reviewed). Three rounds of the six sets in the order of the table, a U-Boot
`reset` and a fresh load of the PL design before every run (`series.py`). No run was stopped by
the run script; every result is the board's (pulled in pieces, each piece with the board's
crc32 — 4 pieces of 299 had to be pulled a second time — the whole against the crc32 taken
before the save, and the card copy verified). `summary.json` is made from the stored results by
`summarize.py`, which judges each again.

The address in the third column is the one the records carry: where the status word of the
polling loop lay during the target reads.

| set | what it does | polling variable at | run 1 | run 2 | run 3 |
|---|---|---|---|---|---|
| `dxw0` | the walk over `0xb80..0xb99`, as in S1b.1 | `0x1eaca9d8` | overflow, record 36 | overflow, record 114 | **complete, PASS** |
| `dxs0` | stage 5: the 26 addresses, the pad alone and then the frame | `0x1eacaa20` | complete | complete | complete |
| `dxs18` | the same, 18 words more stack | `0x1eaca9d8` | overflow, record 36 | overflow, record 13 | complete |
| `dxs10` | the same, 10 words more stack | `0x1eaca9f8` | overflow, record 8 | overflow, record 8 | overflow, record 12 |
| `dxw6` | the walk, 6 words more stack | `0x1eaca9c0` | complete, PASS | complete, PASS | complete, PASS |
| `dxw8` | the walk, 8 words more stack | `0x1eaca9b8` | complete, PASS | overflow, record 88 | overflow, record 110 |

A complete stage-5 run is judged FAIL by design (24 of its 26 frames have no known answer); the
judge has no other objection to any of the 18 results. Every overflow is the same event as on
2026-11-14: code `0x21`, `INT_STS` `50070004` in the read's second transfer. Two of the nine
fell in a read of the pad alone (101 words), five in a read of 202 words, two in a group read of
404 words.

## By where the polling variable lay

| address | modulo 32 | reads (pad alone + with frames) | overflows |
|---|---|---|---|
| `0x1eaca9b8` | 24 | 306 | 2 |
| `0x1eaca9c0` | 0 | 339 | 0 |
| `0x1eaca9d8` | 24 | 359 | 4 |
| `0x1eaca9f8` | 24 | 63 | 3 |
| `0x1eacaa20` | 0 | 165 | 0 |

`0x1eaca9f8` is also where the walk's reference reads lie: 35 of the 63, none of which overflowed
here (the overflow of walk run 3 on 2026-11-14 did fall on one);
`0x1eacaa20` is where stages 2, 3 and 5 read without extra stack, and where every run's first
reference read lies.

## What this does and does not say

- **Not the sequence.** `dxs0` made the walk's first-pass reads — 26 different frames, 52 reads
  — three times with no overflow. The runs of 2026-11-14 had never gone past 9 different frames
  by this path; that gap is closed.
- **The stack position.** `dxs18` and `dxs10` differ from `dxs0` in one parameter word, which
  moves the stack beneath the target reads and changes nothing else that the prober does; five
  of those six runs overflowed. `dxw6` differs from `dxw0` in the same word only, and completed
  three times of three.
- **A rate, not a certainty.** At the positions that overflow, a run can still complete
  (`dxw0` run 3, `dxs18` run 3, `dxw8` run 1): 9 overflows in 728 reads. If reads at 0 modulo 32
  overflowed at that rate, 504 clean ones in a row would have a chance of about 1 in 500.
- **Consistent with 2026-11-14.** That image entered with the same stack pointer (`1eacab18`
  in every header, then and now) and had the same frames, so its walk read at `0x1eaca9d8` and
  `0x1eaca9f8` and its stages 2 and 3 at `0x1eacaa20` — inferred: that image did not record the
  address. Five overflows there, none in 624 frame reads here.
- **Not established:** that "24 modulo 32" is the rule. Two residues were tried, five addresses
  in all; 8 and 16 were not, and the extra stack moves the whole frame of the reading routine,
  not the polling variable alone — the address recorded stands for the position of that frame.
  **Not known:** the mechanism.
- `dxw6` is the first time the walk has run to its end on the board: both passes ended where
  the device named `0xb9a`, above the envelope given to it, 26 frames each, every check of the
  judge met. It is a walk of the 26 addresses already read, not of the column: the column's end
  has still not been looked for, and `host/grade_s1b1.py` has not been run.

The board was left at the U-Boot prompt after `dxw8` run 3, the PL configured and the error bits
of that overflow latched (`INT_STS` `50870004`); a `reset` clears them.

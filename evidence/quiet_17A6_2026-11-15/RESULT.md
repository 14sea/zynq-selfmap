# The three waits on the board — EBAZ4203 `17A6`, 2026-11-15

Question (docs/s1b_plan.md, section 20): the overflow of the PCAP receive FIFO follows where the
reading routine's frame lies on the stack, and while a transfer runs the only thing the prober
does there is the loop that waits for it — two stores and one load on every poll. Is it that?

**Answer: yes, and it is the stores. At the two stack positions where the reads had overflowed,
the original loop overflowed again in four runs of six. With the loop that stores nothing until
the transfer is over — whether or not it still loads the limit from the stack — twelve runs of
twelve ran to their end: 1,020 reads at those positions without an overflow, against 4 in 297
with the original loop in the same image, the same day, in alternation. Why two stores to DDR
at those addresses during a transfer make the FIFO overflow is not known.**

## What was run

One image throughout: `prober.bin`, 11,630 bytes, sha256 `2c566b1e…b296`, crc32 `b0d75377`
(commits `40f9437` and `699792d`, reviewed). Three rounds of the six sets in the order of the
table, a U-Boot `reset` and a fresh load of the PL design before every run (`series.py`). No run
was stopped by the run script; every result is the board's (320 pieces pulled, 8 of them a
second time; each whole result against the crc32 taken before the save; every card copy
verified). `summary.json` is made from the stored results by `summarize.py`, which judges each
again. Within a triple the parameter blocks differ in one bit field of one word.

| set | what | wait | run 1 | run 2 | run 3 |
|---|---|---|---|---|---|
| `dxs10` | stage 5, reads at `0x1eaca9f8` | as before | overflow, record 10 | complete | complete |
| `dxs10n` | the same | no stores | complete | complete | complete |
| `dxs10r` | the same | no stack | complete | complete | complete |
| `dxw0` | the walk as it was, reads at `0x1eaca9d8` | as before | overflow, record 84 | overflow, record 56 | overflow, record 43 |
| `dxw0n` | the same | no stores | complete, PASS | complete, PASS | complete, PASS |
| `dxw0r` | the same | no stack | complete, PASS | complete, PASS | complete, PASS |

A complete stage-5 run is judged FAIL by design (24 of its 26 frames have no known answer); the
judge has no other objection to any of the 18 results. The four overflows are the event seen
before: code `0x21`, `INT_STS` `50070004` in the read's second transfer; one of them in a read
of the pad alone.

## By the wait, at the positions that had overflowed (polling variable at 24 modulo 32)

| wait | on every poll, on the stack | reads | overflows |
|---|---|---|---|
| as before | two stores, one load | 297 | 4 |
| no stores | one load | 510 | 0 |
| no stack | nothing | 510 | 0 |

(Target reads of stage 5 and every read of the walk; the address is recorded in the same way
whichever wait is used — it is where the original loop would store.)

## What this does and does not say

- **The controls overflow in this image**, at about the rate seen before (4 in 297 here; 9 in
  728 in the series of the morning, another image). So the image did not move the thing by
  accident, and the rest can be read.
- **The stores are what matters.** Taking the stores away and keeping the load (`n`) is enough:
  510 reads, none overflowed. At the rate of the original loop (13 in 1,025 over both series)
  that many clean reads in a row would have a chance of about 1 in 700; the 1,020 of both quiet
  waits together, about 1 in 500,000.
- **The load alone was not seen to matter**: `n` and `r` do not differ in outcome. That is not
  proof that it cannot contribute; with the stores gone there is nothing left for it to add to.
- `dxs10` overflowed in one run of three here and in three of three in the morning. The two are
  compatible with one rate (4 overflows in 181 reads at that address over both series); the
  morning's three early stops were not a property of that depth.
- **Not known: the mechanism.** A read is polled two to six times, so the original loop makes a
  handful of single-word stores to DDR while the transfer writes its 101 to 404 words there, and
  only where those stores fall at offsets 24 and 28 of a 32-byte block (the other position
  tried, offsets 0 and 4, never overflowed) does the FIFO overflow, about once in eighty reads.
  Nothing here explains that; it is recorded as observed.
- Six complete walks of the 26 addresses, all PASS, all naming `0xb9a` as the address after
  `0xb99`. As before, that is not a walk of the column: its end has not been looked for, and
  `host/grade_s1b1.py` has not been run.

The board was left at the U-Boot prompt after `dxw0r` run 3, the PL configured, no error bit
latched (`INT_STS` `50033004`).

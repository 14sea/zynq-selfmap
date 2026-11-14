# S1b.1 on EBAZ4203 `17A6` — 2026-11-14, run 1: STOPPED, twice over; not judged

This is an interim record, written the moment the run stopped. Nothing was sent to the board after
the stop. No verdict exists yet, and the comparison with an outside description was not run.

Two separate things stopped, in this order:

1. **On the board, the prober stopped the walk itself** at the 27th frame of the first pass, on an
   interface failure: status `0x221` (an error bit in `INT_STS` during a command), return code
   `0x221`, 56 records, 1 anomaly.
2. **On the host, the pull of the result over the console lost one line** (4 of 26,944 words), so the
   pulled copy does not have the board's crc32 and, as the run script's rule says, was kept as
   `run1/result_unverified.bin` and the run stopped there — before the judge, before the status
   afterwards.

The result itself is complete on the card: `saf8b892.bin`, 107,776 bytes, written and read back
with the board's crc32 `3d96d807`. It is also still in the board's RAM as long as the board is
not reset.

## What was run

- Board: EBAZ4203 said by the operator to be `17A6` (banner `Ebang EBAZ4203`, 512 MiB, seen at
  the reset below). The project's own card.
- Before the run the console's USB adapter was found detached from this host (the kernel log
  shows the USB/IP link reset earlier); it was attached again. The board had not lost power: it
  was still in the session of S1b.0b, PL configured. It was restarted with U-Boot's `reset`, as
  before S1b.0b. All of that is in `precheck_console.log`.
- PL design from the card, crc32 `72887bf4`, `fpga loadb`; `INT_STS` `a802000a` → `50021004`.
- Prober: `prober.bin`, 10,510 bytes, sha256 `e26e653514d27bf9c7784caec64f395f705eba4a1450e061a2fa94c86a3bb959`,
  crc32 `1eb080e9` (commit `19518ab`), checked in RAM before `go`. Not checked again after: the
  run stopped before that step.
- Parameters: stage 4, envelope `0x00000b80..0x00000bff`, reference `0x00000b99`, start
  `0x00000b80`, two passes, limit 64, reference interval 16; block crc32 as planned.

## What the board reported (console and header; these two were read without loss)

| | |
|---|---|
| console | `SM4 start` / `SM4 end status=00000221 records=00000038 anomalies=00000001 words=00006940` |
| return code | `0x221` |
| header | status `0x221`, 56 records, 1 anomaly, stop record 55; pass 0: 26 frames walked, not ended, last address named `0x00000b9a`; pass 1 not begun |
| `INT_STS` | `50021004` at the start; `50870004` at the end, as the prober read it |

## What the records say — from the UNVERIFIED pulled copy

The line lost in the pull is at `0x10006a30`: words 12..15 of record 14's header. Everything
below is from other records and reads consistently, but the copy as a whole is not the board's
and none of this is a verdict.

- Records 1..54: for each of the 27 addresses `0xb80..0xb9a` the successor read, and for
  `0xb80..0xb99` the content read; every code 0. **At every one of them the device named the next
  number**: `0xb80` → `0xb81` … `0xb9a` → `0xb9b`. The register after each content read was two
  further, as in S1b.0. 24 of these 26 frames have no known answer; the two that have one,
  `0xb98` and `0xb99`, hash to their known values (`09e6542e…`, `9029c9d0…`), and so does the
  reference frame in the baseline and in the reference read at the seventeenth frame.
- Record 55, the content read at `0x00000b9a`: the command transfer completed normally
  (`50033004`, 6 polls); the 202-word read ended on its 4th poll with `INT_STS` `50070004` —
  **bit 18, the receive-FIFO overflow**, with bits 17 and 16 — and 10 of the 202 words were not
  delivered (sentinel survivors). The prober recorded code `0x21`, queued nothing more (no
  register read, no cleanup), and stopped: `STATUS` afterwards `00000f30`.
- The final `INT_STS` in the header, `50870004`, has bit 23 as well (per UG585 an AXI write
  time-out of the DMA); it was not set in the reading inside record 55.

## Not known

- Why the receive FIFO overflowed on this read. `0x00000b9a` itself was read cleanly in S1a (three
  times), in S1b.0 (as the third frame of three) and addressed in S1b.0b; this was the 28th
  202-word read of the run and about the 270th command. Whether it would happen again, and where,
  is not known from one occurrence.
- The state the configuration interface is in now: the prober stopped inside a session, without
  the cleanup (as designed for an interface failure), and the error bits are latched.
- Why the console lost a line. The same USB adapter had dropped off this host earlier the same
  evening.

## What this is not

Not a PASS, not a FAIL by the judge, and not a count of the frames in the column: the walk was
stopped at 26 frames by an interface failure and says nothing about where the column ends.

Files: `precheck_console.log`; `run1/console.log` (every byte both ways, including the damaged
pull), `run1/header.bin`, `run1/result_unverified.bin` (26,940 words), `run1/run.json`;
`expected_s1b1.json` and `prober.bin` as they were for this run. There is no `result.bin` and no
`verdict.json`.

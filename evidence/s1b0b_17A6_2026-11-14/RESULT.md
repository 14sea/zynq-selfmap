# S1b.0b on EBAZ4203 `17A6` — 2026-11-14, run 1

Question (docs/s1b_plan.md, section 9), asked on the three known frames: what does the frame
address register hold after a read of the pad alone, after no read at all, and after two frames?

**Answer: after the pad alone at F the register held F + 1, at all three addresses. With no read
it held F. Every value fits one step per 101 words delivered. Verdict PASS, first run, no anomaly.**

## What was run

- Board: EBAZ4203 said by the operator to be `17A6` (banner `Ebang EBAZ4203`, 512 MiB, seen at
  the reset below). Console on the CH340; JTAG not used. The project's own card (`SK64G`).
- Before the run the board was still in the power-on session of S1b.0, the PL configured. It was
  restarted with U-Boot's `reset` so that the run began as the earlier ones did (PL not
  configured, data cache on); the read-only look before and after that reset is in
  `precheck_console.log`.
- PL design: the same carrier bitstream (sha256 `8c3369e8…`, 2,083,863 bytes) from the card,
  crc32 `72887bf4` checked in RAM, `fpga loadb`; `INT_STS` went `a802000a` → `50021004`.
- Prober: `prober.bin`, 7886 bytes, sha256 `daa32b08711493745c1ac88cde497de575ca8e483c83c29500cd5694e202f99e`,
  crc32 `26e4b875` — the image fixed in `expected_s1b0b.json` by the test suite (commits
  `d799d0a`, `94f8e80`); its crc32 was checked in RAM before `go` and again after.
- Parameters: stage 3, envelope `0x00000b98..0x00000b9a`, reference `0x00000b99`, the eight
  operations of the plan, three repeats, anomaly budget 24, poll limit 0x200000. The block the
  prober echoed equals the planned one word for word.
- The run script's 44 steps as printed by `--dry-run --stage s1b0b`; the PL design was on the
  card, so the YMODEM branch was not taken. 39 seconds (17:50:03–17:50:42 UTC).

## Result

| read | words | at `0xb98` | at `0xb99` | at `0xb9a` | step |
|---|---|---|---|---|---|
| none (address written, `RCFG` given, nothing read) | 0 | `0xb98` | `0xb99` | — | 0 |
| the pad alone | 101 | `0xb99` | `0xb9a` | `0xb9b` | 1 |
| the pad and one frame | 202 | `0xb9a` | `0xb9b` (the reference read) | — | 2 |
| the pad and two frames | 303 | `0xb9b` | — | — | 3 |

Each cell is the register value read back, the same in every repeat (three per operation; six
for the pad alone at `0xb98`, which was made at two places in the sequence — after a frame read
and after an operation that read nothing — with the same value).

| | |
|---|---|
| console | `SM3 start` / `SM3 end status=00000001 records=0000001a anomalies=00000000 words=00003100` |
| return code | `0x0`; U-Boot answered normally afterwards |
| records | 26: the baseline, 8 operations × 3 repeats, the final reference read; every code 0 |
| frames delivered | all equal to the known frames (`09e6542e…`, `9029c9d0…`); the 101 words of every pad, also of the pad-only reads, all zero |
| result | 12,544 words; crc32 `720f48b9` on the board, in the file read back from the card, and in the copy pulled over the console |
| card file | `saf89f4b.bin`, 50,176 bytes written and read back |
| judge | PASS; the length rule: holds, with a clean value for every planned read |
| live `INT_STS` afterwards | `50033004`: `PCFG_DONE` set, no bit of the error mask |

The values, the pads and the frame hashes were also re-computed from `result.bin` by a few lines
of Python that do not use the judge; they agree.

## Observed, beyond the verdict

- The one-frame read at `0xb98` left `0xb9a`, as in S1b.0: the earlier value repeats, after a
  reset and a fresh load.
- With no read the register gave back the address written: a value read back is where the
  device stands, and neither `RCFG` nor the register read moves it.
- A session that gives `RCFG`, writes the address and reads no frame data ends cleanly: the
  reads after it were normal.
- Polls of `INT_STS` until done: 4 for a 101-word read, 5–6 for 202, 8 for 303; 2 for the
  one-word register read; 2–3 for the cleanup.
- `INT_STS` before the PL load read `a802000a` — after a U-Boot `reset`, as before S1a (also
  after a reset). Before S1b.0, after a power-on, it had read `a802000b`. Two against one; bit 0
  may tell a power-on from a reset. Not tested as such.
- `INT_STS` bit 16 again became set during the first readback and stayed.

## What this does and does not establish

- On these three frames a read of the pad alone makes the device name the address after F
  without delivering F, and the name does not depend on what the session before it did.
- `0xb9b` is a value the register held (after the pad alone at `0xb9a`, and after longer reads).
  Nothing was read there; this run does not say that it is a frame.
- All three addresses are in the middle of one column. What the register does at the end of a
  column, a row or a block type — whether it names the first frame of the next column, an
  address that does not exist, or something else — has not been seen. That is the first thing
  the next step would meet.
- "One step per 101 words" fits the four lengths tried (0, 101, 202, 303; 404 in S1b.0). Lengths
  that are not a whole number of frames were not tried and are refused by the guard.
- One design, one board, two power-on sessions (S1b.0 and this one).

Files: `precheck_console.log`; `run1/console.log` (every byte both ways), `run1/result.bin`,
`run1/header.bin`, `run1/run.json`, `run1/verdict.json`; `expected_s1b0b.json` and `prober.bin`
as they were for this run.

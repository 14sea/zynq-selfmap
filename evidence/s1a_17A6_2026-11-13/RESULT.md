# S1a on EBAZ4203 `17A6` — 2026-11-13, run 1

Question (docs/s1a_plan.md): does a program on the PS, by itself, read three configuration
frames through PCAP and reproduce what zynq-psmap read from this die with the same PL design
loaded?

**Answer: yes. Verdict PASS, first run, nothing unusual.**

## What was run

- Board: EBAZ4203 said by the operator to be `17A6` (banner `Ebang EBAZ4203`, 512 MiB, seen at the
  reset earlier the same day). Console on the CH340; JTAG not used. The project's own card.
- PL design: the carrier bitstream zynq-psmap had loaded (sha256 `8c3369e8…`, 2,083,863 bytes),
  sent by YMODEM, crc32 checked in RAM, `fpga loadb`; `INT_STS` went `a802000a` → `50021004`.
- Prober: `prober.bin`, 4023 bytes, sha256 `94762235…`, crc32 `bfad1be8` — the image fixed in
  `expected.json` by the test suite; its crc32 was checked in RAM before `go` and again after.
- Parameters: envelope `0x00000b98..0x00000b9a`, reference `0x00000b99`, the three frames, three
  repeats, anomaly budget 4, poll limit 0x200000. The block the prober echoed equals the planned
  one word for word.
- The run script's 38 steps, as printed by `--dry-run`, with no deviation. About four minutes,
  nearly all of it the YMODEM transfer of the PL design.

## Result

| | |
|---|---|
| console | `SM1 start` / `SM1 end status=00000001 records=0000000b anomalies=00000000 words=00000bae` |
| return code | `0x0`; U-Boot answered normally afterwards |
| records | 11: the baseline, 3 frames × 3 repeats, the final reference read |
| every record | code 0; no sentinel survivors; the pad half all zero; the frame equal to the known frame |
| frames (sha256, big-endian words) | `0xb98` `09e6542e…`, `0xb99` `9029c9d0…`, `0xb9a` `80f782b9…` — zynq-psmap's values |
| result | 2990 words; crc32 `4d489d2a` on the board, in the file read back from the card, and in the copy pulled over the console |
| card file | `saf77233.bin`, 11,960 bytes written and read back |
| judge | PASS: every code, the order of the records, the status, the anomaly count and the stop record re-derived from the raw words and equal to what the prober reported; every recorded stream equal to the pinned words |
| live `INT_STS` afterwards | `50033004`: `PCFG_DONE` set, no bit of the error mask |

## Observed, beyond the verdict

- **`go` and the return work with the data cache off.** `SCTLR` read `08c51878`: data cache and MMU
  off, instruction cache on.
- **Polling at CPU speed:** the command and read transfers completed on the 5th or 6th read of
  `INT_STS`, the 5-word cleanup on the 2nd. zynq-psmap could only say "within one UART round
  trip"; the poll limit of 0x200000 was never approached.
- **Eleven reads back to back** — 33 DMA commands with nothing but the prober between them —
  with no error bit at any point.
- `INT_STS` after the very first command transfer read `50023004`; after every later transfer
  `50033004`. Bit 16 becomes set during the first readback and stays. It is in neither the error
  mask nor the clear mask; zynq-psmap's records show the same final value. Recorded, not explained.
- `STATUS` read `40000f30` before and `50000f30` after.

## What this does and does not establish

- The method works on a known range: the prober issues the pinned sequence itself, and what
  comes back is bit for bit what was read before from this die with this design.
- Three frames in one column, one design, one board, one power-on. Nothing here says anything
  about other block types, addresses that do not exist, or reading with the caches on.
- Whether the readback disturbed the running design was not observed.
- The card file was verified by reading it back in U-Boot; it has not been read on the host.

Files: `run1/console.log` (every byte both ways), `run1/result.bin`, `run1/header.bin`,
`run1/run.json`, `run1/verdict.json`; `expected.json` and `prober.bin` as they were for this run.

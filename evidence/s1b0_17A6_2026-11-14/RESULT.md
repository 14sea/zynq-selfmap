# S1b.0 on EBAZ4203 `17A6` — 2026-11-14, run 1

Questions (docs/s1b_plan.md, section 2), asked on the three frames already known from S1a:

1. Can the frame address register be read back through PCAP, and what does it hold after a read?
2. Does one read of several frames return those frames, in order?

**Answers: yes to both. Verdict PASS, first run. The register follows the rule the judge calls
"next but one": after a read of n frames starting at F it holds F + n + 1.**

## What was run

- Board: EBAZ4203 said by the operator to be `17A6` (512 MiB, U-Boot 2026.04-rc5; the label was
  not read by this host). Console on the CH340; JTAG not used. The project's own card (`SK64G`).
  A read-only look at the board before the run is in `precheck_console.log`.
- PL design: the same carrier bitstream as S1a (sha256 `8c3369e8…`, 2,083,863 bytes), this time
  loaded from the card (`fatload`, 398 ms), crc32 `72887bf4` checked in RAM, `fpga loadb`;
  `INT_STS` went `a802000b` → `50021004`.
- Prober: `prober.bin`, 7703 bytes, sha256 `3e3ab201761ab6e6af3036b3f8206273dd78cc4deb430bc3a0569900d7ccee07`,
  crc32 `53130c7c` — the image fixed in `expected_s1b0.json` by the test suite at commit
  `5e03e6e`; its crc32 was checked in RAM before `go` and again after.
- Parameters: stage 2, envelope `0x00000b98..0x00000b9a`, reference `0x00000b99`, three
  operations (one frame at `0xb98`, one frame at `0xb99`, three frames from `0xb98`), three
  repeats, anomaly budget 4, poll limit 0x200000. The block the prober echoed equals the
  planned one word for word.
- The run script's 39 steps as printed by `--dry-run --stage s1b0`; the PL design was on the
  card, so the YMODEM branch (7a) was not taken. 27 seconds in all (15:37:53–15:38:20 UTC).

## Result

| | |
|---|---|
| console | `SM2 start` / `SM2 end status=00000001 records=0000000b anomalies=00000000 words=000014e0` |
| return code | `0x0`; U-Boot answered normally afterwards |
| records | 11: the baseline, 3 operations × 3 repeats, the final reference read |
| every record | code 0; no sentinel survivors; the pad frame all zero; every frame equal to the known frame |
| one-frame reads | `0xb98` `09e6542e…`, `0xb99` `9029c9d0…` — as in S1a and in zynq-psmap |
| three-frame reads from `0xb98` | `09e6542e…`, `9029c9d0…`, `80f782b9…` in that order, in all three repeats |
| address register read back | after one frame at `0xb98`: `0x00000b9a`; after one frame at `0xb99`: `0x00000b9b`; after three frames from `0xb98`: `0x00000b9c` — the same in every repeat (11 of 11 records: start + frames + 1) |
| result | 5344 words; crc32 `6e995596` on the board, in the file read back from the card, and in the copy pulled over the console |
| card file | `saf88051.bin`, 21,376 bytes written and read back |
| judge | PASS: codes, order, status, anomaly count and stop record re-derived from the raw words; every recorded stream equal to the pinned words; one address rule over the whole run |
| live `INT_STS` afterwards | `50033004`: `PCFG_DONE` set, no bit of the error mask |

The frame hashes and the pad were also re-computed from `result.bin` by a few lines of Python
that do not use the judge; they agree.

## Observed, beyond the verdict

- **A one-word register read through PCAP works** as sent (`NOOP`, `28002001`, `NOOP`, `NOOP`,
  then a one-word read): each of its two transfers completed on the 2nd read of `INT_STS`.
- **A 404-word read** completed on the 10th read of `INT_STS`; a 202-word read on the 5th or 6th,
  as in S1a.
- **Five commands per session, eleven sessions back to back** (55 DMA commands), no error bit.
- The address read back counts the pad frame: the register is ahead of the last frame
  delivered by two, not one. One reading — not tested here — is that it advances once per
  101 words delivered (202 words: two steps; 404 words: four).
- `0xb9b` and `0xb9c` are values the register held. Nothing was read at those addresses, and
  this run does not say whether they are frames.
- `INT_STS` bit 16 again became set during the first readback and stayed (`50023004` after the
  first command transfer, `50033004` after every later one). Still not explained.
- `INT_STS` before the PL load read `a802000b`; before S1a it had read `a802000a`. Bit 0 is in
  neither the error mask nor the clear mask. Recorded, not explained.
- `STATUS` read `40000f30` before and `50000f30` after, as in S1a.

## What this does and does not establish

- On these three frames the register can be read, its value is repeatable, and it moves with
  the amount read. A read of several frames returns them in address order.
- It does **not** establish how to walk. Under this rule the register never shows the address
  of the frame after the last one delivered; it shows the one after that. Getting the former by
  subtracting one is arithmetic on an address, which the walk was meant to avoid; what the
  register does at the end of a column, a row or a block type has not been seen at all. Both
  are open items for the planning of S1b.1 (docs/s1b_plan.md, section 5).
- Three frames in one column, one design, one board, one power-on.
- Whether the readback disturbed the running design was not observed.

Files: `precheck_console.log`; `run1/console.log` (every byte both ways), `run1/result.bin`,
`run1/header.bin`, `run1/run.json`, `run1/verdict.json`; `expected_s1b0.json` and `prober.bin`
as they were for this run.

# S1b.1 on EBAZ4203 `17A6` — 2026-11-14: two runs, both stopped by the prober on a receive-FIFO overflow

Question (docs/s1b_plan.md, sections 12 to 14): walk the column of the known frames from
`0x00000b80` by the addresses the device names; how many frames, by the device's own account?

**No answer yet. Both runs were stopped by the prober itself, as designed, on an interface
failure — the receive FIFO of the PCAP overflowed during the read of a frame — after 26 frames
the first time and 7 the second. Judge's verdict on each: FAIL (the run did not complete; one
anomalous read; nothing else). The walk never reached the end of the column, and the comparison
with an outside description was not run.**

What the two runs did establish is at the end.

## What was run

- Board: EBAZ4203 said by the operator to be `17A6` (banner `Ebang EBAZ4203`, 512 MiB). The
  project's own card. Console on the CH340; JTAG not used.
- Prober: `prober.bin`, 10,510 bytes, sha256 `e26e653514d27bf9c7784caec64f395f705eba4a1450e061a2fa94c86a3bb959`,
  crc32 `1eb080e9` (commit `19518ab`), checked in RAM before each `go`.
- Parameters: stage 4, envelope `0x00000b80..0x00000bff`, reference `0x00000b99`, start
  `0x00000b80`, two passes, limit 64, reference interval 16.
- Run 1 (19:37 UTC): released by the owner after the review. Before it, the console's USB adapter
  was found detached from this host and attached again; the board, still in the session of
  S1b.0b, was restarted with U-Boot's `reset` (`precheck_console.log`).
- Run 2 (19:46 UTC): on the owner's word ("first (a), then (b)"), the same again after another
  `reset`, to see whether the stop repeats and where (`precheck_run2_console.log`). The `reset`
  cleared the latched error bits (`INT_STS` `50870004` → `a802000a`); no power cycle was needed.

## The two stops

| | run 1 | run 2 |
|---|---|---|
| console | `SM4 end status=00000221 records=00000038 anomalies=00000001 words=00006940` | `SM4 end status=00000221 records=00000011 anomalies=00000001 words=00002020` |
| return code | `0x221` | `0x221` |
| frames walked in pass 0 | 26 (`0xb80..0xb99`) | 7 (`0xb80..0xb86`) |
| the failing record | 55: the content read at `0x00000b9a` | 16: the content read at `0x00000b87` |
| its command transfer | normal (`50033004`, 6 polls) | normal (`50033004`, 6 polls) |
| its 202-word read | `INT_STS` `50070004` on the 4th poll | `INT_STS` `50070004` on the 2nd poll |
| words not delivered | 10 of 202 | 10 of 202 |
| 202-word reads before it in the run | 28, all clean | 8, all clean |
| `INT_STS` at the end (header, and live afterwards) | `50870004` | `50870004` |
| `STATUS` afterwards | `00000f30` | `00000f30` |
| result | 26,944 words, crc32 `3d96d807` | 8,224 words, crc32 `bc488533` |
| card file (written, read back with that crc32) | `saf8b892.bin` | `saf8ba7b.bin` |
| judge, on the verified copy | FAIL: "the run did not complete: status 0x221", "1 anomalous read(s)" — nothing else | the same two, nothing else |

`50070004` has bit 18, `RX_FIFO_OV`; the final `50870004` has bit 23 as well (per UG585 an AXI
write time-out of the DMA). In both runs the prober recorded code `0x21`, queued nothing further
— no register read, no cleanup — and stopped. The judge re-derived the same status, counts, stop
record, console line and return code from the raw words.

The failure is not tied to an address: it fell on `0xb9a` once and on `0xb87` once, and `0xb87`
had been read cleanly in run 1, `0xb9a` in S1a and S1b.0. It is not tied to a place in the run
either (the 29th and the 9th 202-word read). The same 10 words were short both times.

UG585 says of this case that there is no flow control on the PL side of the PCAP, that an
overflow of the receive FIFO loses data, and that the DMA "may enter an unrecoverable state"
(imported/psmap/s0_ug585_discharge.md, C2 and N6); the FIFO holds 31 words. zynq-psmap carried
it as a stop condition and never met it. Counting every read of 202 words or more made on this
board by this project: 30 before today's walk, none failed; 38 in these two runs, 2 failed.

## The host side: the pull over the console lost data three times out of five

Separately from the above, and after it: in both runs the pull of the result over the console
(`md.l`) came back short (run 1: 4 words missing; run 2: 31), so by the run script's rule the
copy was kept as `result_unverified.bin` and the script stopped before the judge. The result
itself was never at risk: in both runs the card copy had been written and read back with the
board's crc32 before the pull.

On the owner's word (step (a)) the verified copies were then fetched read-only: crc32 of the
result still in RAM, `fatload` of the card file to a scratch address and its crc32 — all three
equal — then `md.l` of the scratch copy until the host's crc32 matched (run 1: the first pull
lost 555 words, the second was whole; run 2: the first was whole). `run1_recovered/` and
`run2_recovered/` hold the console log of that, `recover.json`, `result.bin` and `verdict.json`.
The same USB adapter had dropped off this host earlier in the evening.

## What the two runs did establish

From verified copies, and within what a stopped run can say:

- **At each of the 26 addresses `0xb80..0xb99` the device named the next number** after a read of
  the pad alone (`0xb80` → `0xb81` … `0xb99` → `0xb9a`), and after the read of each frame the
  register was the address named after the next frame (25 such checks in run 1, none failing).
  24 of these 26 addresses have no known answer and had never been read by this project.
- The 7 frames walked in both runs (`0xb80..0xb86`) have the same content in both, and the same
  next address.
- `0xb98` and `0xb99`, and the reference frame in every reading, equal their known values.
- U-Boot's `reset` brings the interface back after such a stop: the error bits were gone, the PL
  design loaded again, and the next run read 16 records cleanly before its own overflow.

## What they did not establish

- Where the column ends. Neither run got past `0xb9a`.
- Path independence: no read of several frames was reached; `frames_without_a_second_path` lists
  every frame walked.
- Why the FIFO overflows, how often, and whether a session can be recovered without a reset.
  Two occurrences say it happens at a rate that a walk of this length will meet; they do not
  give the rate.

Files: `precheck_console.log`, `precheck_run2_console.log`; `run1/`, `run2/` (as the run script
left them: `console.log`, `header.bin`, `result_unverified.bin`, `run.json`; no verdict);
`run1_recovered/`, `run2_recovered/` (`console.log`, `recover.json`, `result.bin`,
`verdict.json`); `expected_s1b1.json` and `prober.bin` as they were for both runs.

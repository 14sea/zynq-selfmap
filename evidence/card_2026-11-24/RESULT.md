# The probe design `s2b` saved to the project's card — 2026-11-24

Section 46 of docs/s2_plan.md, point 8: storing `s2b.bit` on the card is a write to the card
and needs the owner's word once. Given on 2026-11-24 ("check that the device is there; when
that is checked it can go on the board"). Done before any run of S2.5. Nothing was loaded
into the PL, and the board was not reset.

## The check before (`check.py`, `console_check.log`)

Read-only, shortly before the saving; its last reply came at 19:22 UTC. U-Boot `2026.04-rc5-dirty (Aug 01 2026 - 15:00:50 +0100)`; status
`a802000b`; the card holds `carrier.bit` (`filesize=1fcc17`) and `s2a.bit`
(`filesize=1fcc13`), which only the project's card does.

The script was run twice, and both sessions are in the log. The first stopped at its third
command: it asked that `printenv cardid` answer `cardid=zynq-selfmap-64g`, and the answer is
`## Error: "cardid" not defined` — as it was in the checks before the chains of S2.3 and
S2.4 (`precheck_console.log` there), which ask the same and go on. The expectation was
wrong, not the board; it was taken out and the same read-only commands sent again. Nothing
else was sent in between.

## The saving (`save_s2b.py`, `console_savepl.log`)

One session at the prompt, 19:22:43–19:26:05 UTC.

- The file: `build/pl/s2b.bit`, 2,083,859 bytes (`0x1fcc13`), sha256 `7f0e1af8…7a12`, crc32
  `15045cfc` — the bitstream of `pl/s2b/build.json`, the copy in
  `evidence/s2_5_build_2026-11-23/`.
- Before: status `a802000b`. The card had no `s2b.bit` (`Failed to load 's2b.bit'`).
- Sent by YMODEM to `0x04000000` (U-Boot: `Total Size = 0x001fcc13 = 2083859 Bytes`); crc32
  in RAM `15045cfc`.
- `fatwrite mmc 0:1 04000000 s2b.bit 1fcc13`: "2083859 bytes written". After `mmc rescan`,
  read back with `fatload` to `0x11000000`: 2,083,859 bytes, crc32 `15045cfc`.
- The two designs that were on the card are what they were: `s2a.bit` read back, 2,083,859
  bytes, crc32 `6a1efe06`; `carrier.bit` read back, 2,083,863 bytes, crc32 `72887bf4`.
- Status afterwards `a802000b`. No reply showed an exception or a restart; nothing was sent
  twice.

`s2a.bit` and `s2b.bit` have the same size. The run script tells them apart by the checksum
of the design in RAM and by the design's identification word.

If the design is built again the card's copy is the old one: the run script then stops at
its checksum of the design in RAM, and the file has to be saved again.

# The probe design `s2a` saved to the project's card — 2026-11-20

Section 5 of docs/s2_plan.md: the design gets to the board as the carrier did on 2026-11-13.
Done after S2.0 and before S2.1, on the owner's word ("as you recommend; it is what the plan
fixed"). One session at the prompt, 20:31–20:35 UTC; nothing was loaded into the PL.

- The file: `build/pl/s2a.bit`, 2,083,859 bytes (`0x1fcc13`), sha256 `09782815…df64`, crc32
  `6a1efe06` — the bitstream of `pl/s2a/build.json`.
- Before: the board as S2.0 left it, status `50033004`. The card had no `s2a.bit`
  (`fatload` of it: `Failed to load 's2a.bit'` — the first time this U-Boot's answer for a
  file that is not there is on record).
- Sent by YMODEM to `0x04000000` (U-Boot: `Total Size = 0x001fcc13 = 2083859 Bytes`); crc32
  in RAM `6a1efe06`.
- `fatwrite mmc 0:1 04000000 s2a.bit 1fcc13`: "2083859 bytes written". After `mmc rescan`,
  read back with `fatload` to `0x11000000`: 2,083,859 bytes, crc32 `6a1efe06`.
- The other design on the card is what it was: `carrier.bit` read back, 2,083,863 bytes,
  crc32 `72887bf4`.
- Status afterwards `50033004`: the PL still holds the carrier. No reply showed an exception
  or a restart; nothing was sent twice.

What was sent is `save_s2a.py` (run from the repository's root; it stops at the first reply
that is not the one wanted). Raw console traffic: `console_savepl.log` (the YMODEM blocks
themselves go past the log, as in every run).

If the design is built again the card's copy is the old one, of the same size: the run
script then stops at its checksum of the design in RAM, and the file has to be saved again.

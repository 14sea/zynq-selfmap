# The PL design saved to the project's card — 2026-11-13

After the S1a run, at the owner's request, so that later runs load the design from the card
instead of spending about four minutes on YMODEM.

- The copy left in RAM by the S1a run could not be used: after `fpga loadb` the buffer at
  `0x04000000` no longer had the file's crc32 (`df7aea69`, not `72887bf4`). U-Boot's loader
  aligns and byte-swaps the bitstream in place (`zynq_align_dma_buffer: Align buffer … (swap 1)`).
- So the file was sent again by YMODEM (2,083,863 bytes; crc32 in RAM `72887bf4`), written with
  `fatwrite mmc 0:1 04000000 carrier.bit 1fcc17` ("2083863 bytes written"), and after
  `mmc rescan` read back with `fatload` to `0x11000000`: crc32 `72887bf4`.
- The PL was not reloaded; `INT_STS` before and after `50033004`.

The card now holds: `BOOT.BIN`, `u-boot.img`, `uEnv.txt`, `uboot-redund.env`, `smr0.bin`
(ret2uboot), `saf77233.bin` (the S1a result), `carrier.bit`.

`host/s1a_run.py` now loads the design from the card and falls back to YMODEM if the file is
absent or not of the expected size; either way the crc32 in RAM is checked before `fpga loadb`.
Raw console traffic: `console_savepl.log`.

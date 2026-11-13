# ret2uboot on EBAZ4203 `17A6` — 2026-11-13

Question (proposal section 11, question 8): does a bare-metal function started by U-Boot's `go`
return to U-Boot cleanly?

**Answer: yes, on this board, three times in one power-on.**

## What was run

- Board: EBAZ4203, said by the operator to be `17A6` (the label was not read by this host; the
  512 MiB of DRAM rules out the EBAZ4205). Console on the CH340. JTAG not used.
- Card: a new 64 GB card prepared for this project (`BOOT.BIN` `264f8478…`, `u-boot.img`
  `16a21245…`, `uEnv.txt` `49d74e35…`, each re-read from the card after a remount). The only
  thing saved to it from U-Boot is the environment with `bootdelay=-1` (after `env default -a`).
- Image: `ret2uboot.bin`, 380 bytes, sha256 `ab3a95c8…`, the image `tests/test_ret2uboot.py`
  checked immediately before the run. Loaded with `loady 0x02000000` (YMODEM), not from the card.
- The PL was not configured at any point (INT_STS bit 2 clear); the program does not touch it.

## Observed, against the values fixed before the run (`expected.json`)

| check | expected | observed |
|---|---|---|
| size reported by `loady` | 380 bytes | `0x0000017c = 380 Bytes` |
| `crc32 02000000 17c` | `0226ee98` | `0226ee98` |
| console | `SMR0 enter` / `SMR0 exit rc=0` | both lines, in order |
| U-Boot after the call | `## Application terminated, rc = 0x0` and a prompt | so, on all three runs |
| `crc32 10001000 f000` | `4caaaa26` | `4caaaa26` on all three runs |
| U-Boot afterwards | `version`, `printenv`, `mmc rescan`, `fatls` work | all answered normally |

## The state U-Boot hands over (read-only snapshot taken by the program)

| register | value | reading |
|---|---|---|
| SLCR_LOCKSTA `F800000C` | `00000001` | the SLCR is **locked**: any SLCR write by the prober needs the unlock first |
| ARM / DDR / IO PLL_CTRL | `00028008` / `00020008` / `00030008` | feedback dividers 40 / 32 / 48: 1333 / 1067 / 1600 MHz from 33.33 MHz |
| PLL_STATUS `F800010C` | `0000003f` | all three PLLs locked and stable |
| FPGA0_CLK_CTRL `F8000170` | `00400800` | IO PLL / 8 / 4 = **50 MHz** |
| FPGA_RST_CTRL `F8000240` | `00000000` | FPGA resets released |
| LVL_SHFTR_EN `F8000900` | `0000000f` | level shifters enabled |
| DEVCFG CTRL / LOCK | `4e00e07f` / `0000001a` | — |
| DEVCFG INT_STS `F800700C` | `a802000b` | bit 2 (PCFG_DONE) clear: the PL is not configured |
| DEVCFG INT_MASK / STATUS / MCTRL | `ffffffff` / `40000a30` / `30800100` | — |
| SCTLR | `08c5187d` | MMU on, data cache on, instruction cache on |
| CPSR | `600001d3` | SVC mode, ARM state, IRQ and FIQ masked |
| SP / r9 | `1eacabb0` / `1ead0ec0` | U-Boot's stack and its `gd`; identical on all three runs |

## Saving the buffer to the card from U-Boot (same day, same power-on, then across a reset)

After a fourth run of the program (buffers cleared first):

| step | observed |
|---|---|
| `crc32 10000000 10000` (the whole 64 KiB buffer) | `3f2e0e62` |
| `fatwrite mmc 0:1 10000000 smr0.bin 10000` | `65536 bytes written in 24 ms` |
| `fatls mmc 0:1` | `smr0.bin`, 65536 bytes, beside the three boot files and the environment |
| `mmc rescan`, `fatload mmc 0:1 11000000 smr0.bin`, `crc32 11000000 10000` | `3f2e0e62` |
| `cmp.b 10000000 11000000 10000` | `Total of 65536 byte(s) were the same` |
| `reset`; the board returns to the prompt with no key pressed (`bootdelay=-1` from the card) | banner: `Model: Ebang EBAZ4203`, `DRAM: ECC disabled 512 MiB` |
| after the reset: read-back area cleared, `fatload` again, `crc32 11000000 10000` | `3f2e0e62`; pattern part `4caaaa26` |

So a result buffer left in DDR by a returning program can be written to the card by U-Boot
and read back identical after a reset. Only the FAT partition was tried; the ext4 partition
was not. The file has not yet been read on the host.

One thing seen at the reset: `Loading Environment from FAT... *** Warning - some problems
detected reading environment; recovered successfully`. The environment was saved once, so
only one of the two redundant copies exists (`uboot-redund.env`); the value read back is the
saved one (`bootdelay=-1`). Not changed.

Raw console traffic for this part: `console_fatwrite.log`.

## What this does and does not establish

- A function that keeps to U-Boot's context (its stack, r9 untouched, no VFP, no mode change)
  can be entered with `go`, write to the console UART and to DDR, and return; U-Boot keeps
  working and the function can be run again.
- The data cache is on. A prober that uses DMA through PCAP must flush and invalidate its
  buffers itself; nothing here tested that.
- Nothing here touched the PL or PCAP, and the program itself never touches the card; the card
  is written by U-Boot after the program has returned.
- One board, one power-on (plus one soft reset), four runs.

Raw console traffic, including every byte sent: `console.log`.

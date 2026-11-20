# S2.1, the path to user logic and the design from its own side — EBAZ4203 `17A6`, 2026-11-20: PASS

Question (docs/s2_plan.md, section 7): can a program on the PS reach our own design in the
PL and return, and is that design, seen through its own registers, the RAM and the shift
registers it was built to be?

**Yes to both. This is outcome 1 of the eight section 7 named beforehand. The first access to
user logic — `md.l 40000000 1` at the U-Boot prompt — came back with the design's
identification, `53324131`. The prober then made its 1,164 accesses and returned: the
counter ran, the RAM read back each of its four states at all 64 addresses, the shift
registers read the words the design loads them with, twice alike, and were never shifted.
IDCODE, CTL0 and STAT read as under the carrier; the reference frame was the same at the end
as at the start; no error bit, no status bit that is not usual. Nothing was written to
configuration memory or to any configuration register.**

Nothing was graded: no frame was read that was not read before, and nothing here says where
the RAM lies in configuration memory.

## The run

On the owner's word of 2026-11-20 ("as you recommend; it is what the plan fixed": the design
to the card first, then S2.1). The host side at commit `411da7e`; the image `prober.bin`,
13,964 bytes, sha256 `480bbdd4…aa46` (kept here), the image of S2.0; the set `s2_1` (kept
here as `expected_s2_1.json`); the design `s2a.bit`, 2,083,859 bytes, sha256
`09782815…df64` (kept here, as section 5 has it: beside the first run that loads it). No
mutants ran on the host.

- The design had been saved to the card at 20:31–20:35 UTC (`evidence/card_2026-11-20/`).
- Pre-check 20:38 UTC (`precheck_console.log`): U-Boot at its prompt, status `50033004` as
  S2.0 and the card session had left it, `s2a.bit` on the card (`filesize=1fcc13`).
- A `reset`; the usual fresh prompt, status `a802000a`.
- 20:38:23–20:38:59 UTC: the one run (`run/`, `run.out`), 36 seconds. The design loaded from
  the card (crc32 in RAM `6a1efe06`); `fpga loadb` named it `s2a_top`; status after the load
  `50021004`.
- At the prompt, before anything was started: `LVL_SHFTR_EN` `0000000f`, `FPGA_RST_CTRL`
  `00000000`, `FPGA0_CLK_CTRL` `00400800`, `PLL_STATUS` `0000003f` — the words wanted, as
  recorded on this board — and then **`md.l 40000000 1`: `53324131`**, with a prompt after it.
- The prober: `SM7 start`, `SM7 end status=00000001 records=0000000b anomalies=00000000
  words=00001ef0`; it returned `0x0` to U-Boot.
- The result is the board's: the checksum on the board before the save is the checksum on
  the host after the pull (`d1486e6e`); the card copy (`sb00afbf.bin`, 31,680 bytes)
  verified; none of the 4 pieces pulled a second time; no reply not whole; no reply showed an
  exception or a restart.
- Status afterwards `50033004`: the PL configured, no error bit, no bit 5. The image in RAM
  after the run is the image (`cf189e46`).
- Committed as stored (`8dbe27d`) before this note and the listing of status bits were made.
- After the run nothing was sent to the board: no second run, no `reset`. It stands at the
  U-Boot prompt with `s2a` loaded.

## What it found (`run/verdict.json`, `status_seen.json`)

**The PL gates, read by the prober itself before it touched the PL:** the four SLCR words as
at the prompt, each the word wanted.

**The design, through its registers** (1,164 accesses, the envelope
`0x40000000..0x4000001f`; the prober's code for user logic `0x0`, "nothing wrong"):

| what | read |
|---|---|
| identification | `0x53324131` |
| counter, read twice | `0x33211fb2`, then `0x3321200b`: it runs |
| RAM: four states written to all 64 addresses, each read back | all four as written |
| writes the design counted | 256 to the RAM (4 x 64), 0 shifts |
| shift registers, read twice | `0xa5c30f69`, `0x0f1e2d3c`, `0x13579bdf`, `0xfedcba98` — the words the design loads them with (`pl/s2a/design.json`), both times |

The last line is a known answer from our own design, and it was met: the shift registers
hold after configuration what the build put into them, and reading them does not shift
them.

**The configuration registers, now with our own design loaded:**

| read | all three times | under the carrier (S2.0) |
|---|---|---|
| IDCODE | `0x13722093` | the same |
| CTL0 | `0x00000501` (bits 10, 8, 0) | the same |
| STAT | `0x46107ffc` | the same |

Outcome 7 — CTL0 differing between the two designs — did not come about. **Bit 8 is set
under `s2a` as well:** by the register's word, readback of this design's LUT RAM and shift
registers is not masked.

**The reference frame `0xb99`** read the same first and last (sha256 `0441772f…8de9`), the
address register `0xb9b` after each. It is not the carrier's frame (`9029c9d0…`): another
design, another content at that address, as section 7 expected. (Seen afterwards: the
hash is that of the all-zero frame in the census. Under `s2a` this address holds nothing,
which makes it a weak witness; docs/s2_plan.md, section 19, point 6.) The writes to the RAM in
between did not change it.

**Status words:** in the records 46 taken at a transfer — 45 of them `50033004`, and the
first of the first record `50023004` — and 9 slots zero, the frame reads not made.
`status_seen.py`, over the 57 words of the records and the header: no bit that is neither
an error nor usual.

## What this does not show

- Where the RAM or the shift registers lie in configuration memory, or what a read of their
  frames delivers. No such frame was read. That is S2.2, and with the mask off (bit 8) it is
  expected to deliver content — which is the thing to be shown.
- That the design answers under another clock or after another boot loader: the gates held
  the four SLCR words to this board's, and the run is of this board.
- Anything about a write to the RAM through configuration memory.

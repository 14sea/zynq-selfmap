# S2.0, the configuration registers through PCAP — EBAZ4203 `17A6`, 2026-11-20: PASS

Question (docs/s2_plan.md, section 6): does a read of another register than the address
register work through PCAP, and what does control register 0 hold?

**It works, and control register 0 holds `0x00000501`: bit 8 is set. By the register's own
word (UG470's table), the design as loaded reads back LUT RAM and shift registers unmasked.
This is outcome 1 of the seven section 6 named beforehand. IDCODE read `0x13722093` all
three times — its low 28 bits are the known ones — so a register read in this form delivers
what UG470 says. The address register obeyed the known rule after every frame read, the
reference frame was the known frame all five times, no error bit, no status bit that is not
usual, the PL configured afterwards. Nothing was written to any configuration register or
to configuration memory.**

Whether the frames of a LUT RAM bear the bit out is not shown by this: that is S2.2.

Nothing was graded: there is nothing here to grade.

## The run

Released by the owner on 2026-11-20 ("the device is on line; it may go on the board"), which
I took as the word for S2.0 and not for S2.1. The host side at commit `7b562dc`; the image
`prober.bin`, 13,964 bytes, sha256 `480bbdd4…aa46` (kept here) — its first time on a board;
the set `s2_0` (kept here as `expected_s2_0.json`). The complete set of mutants had been
run on this image's tree before (docs/s2_plan.md, section 16). No mutants ran on the host
during the run.

- Pre-check 20:14 UTC (`precheck_console.log`): U-Boot at its prompt, status `a802000b` (the
  PL not configured: the board had been without power since the last run), `carrier.bit` on
  the card (2,083,863 bytes).
- A `reset`; the usual fresh prompt, `Model: Ebang EBAZ4203`, status `a802000a`.
- 20:14:52–20:15:24 UTC: the one run (`run/`, `run.out`), 32 seconds. The carrier loaded from
  the card; status after the load `50021004`.
- The prober: `SM6 start`, `SM6 end status=00000001 records=0000000e anomalies=00000000
  words=00001a80`; it returned `0x0` to U-Boot.
- The result is the board's: the checksum on the board before the save is the checksum on
  the host after the pull (`23ef910b`); the card copy (`sb00aa3c.bin`, 27,136 bytes)
  verified; none of the 4 pieces pulled a second time; no reply not whole; no reply showed an
  exception or a restart.
- Status afterwards `50033004`: the PL still configured, no error bit, no bit 5. The image in
  RAM after the run is the image (`cf189e46`).
- Committed as stored (`4e73959`) before this note and the listing of status bits were made.
- After the run nothing was sent to the board: no second run, no `reset`.

That the board is `17A6` is the owner's word and the card's (`carrier.bit` on it); nothing
the host reads over the console tells one EBAZ4203 from another.

## What it read (`run/verdict.json`, `status_seen.json`)

14 records: the reference frame `0xb99` first and last, and between them three times over
the four reads of the set.

| read | header | all three times | held against |
|---|---|---|---|
| the address register, after a read of the reference frame | `28002001` | `0x00000b9b` (and after the first and the last reference read: five times in all) | the rule of S1b.0: as known |
| IDCODE | `28018001` | `0x13722093` | the low 28 bits `3722093`: as known |
| CTL0 | `2800a001` | `0x00000501` | nothing: the finding |
| STAT | `2800e001` | `0x46107ffc` | nothing: recorded |

- **The reference frame** has the known content in all five reads (sha256 `9029c9d0…6b1f`,
  the value of every run since S1a), the pad before it all zero.
- **Every read delivered**: no sentinel survived, every code `0x0`. A register read with no
  frame read made no frame-read transfer (status and polls of that slot zero, as the judge
  requires); its register command was done after 2 or 3 polls, its register read after 2.
- **Status words**: in the records 61 taken at a transfer — 60 of them `50033004`, and the
  first of the first record `50023004`, as at the start of the earlier runs — and 9 slots
  zero, the frame reads not made. `status_seen.py`, over the 72 words of the records and the
  header: no bit that is neither an error nor usual.

### CTL0 `0x00000501`, by UG470's table (the judge's names)

| bit | name | value |
|---|---|---|
| 10 | ConfigFallback | 1 |
| 8 | GLUTMASK_B | **1 — readback of LUT RAM and shift registers is not masked** |
| 0 | GTS_USR_B | 1 |

No other bit is set, and none that the table does not name. By section 6 nothing is
concluded from a single bit other than bit 8 without the owner.

The plan had expected to meet the table's default here (bit 8 clear: outcome 2) and held a
write of MASK and CTL0 in reserve as a proposal of its own (section 12, point 3). **With bit
8 set that write is not needed for the question as it stands**, and nothing of it is
designed.

### STAT `0x46107ffc`, by UG470's table 5-29 (recorded; the judge names no bit of it)

Read off the table after the run, for the record only; no program holds any of it.

| bits | name | value |
|---|---|---|
| 26:25 | BUS_WIDTH | `11` (x32) |
| 20:18 | STARTUP_STATE | `100` (phase 7) |
| 17, 16, 15 | XADC_OVER_TEMP, DEC_ERROR, ID_ERROR | 0, 0, 0 |
| 14, 13 | DONE, RELEASE_DONE | 1, 1 |
| 12, 11 | INIT_B, INIT_COMPLETE | 1, 1 |
| 10:8 | MODE | `111` |
| 7, 6, 5, 4 | GHIGH_B, GWE, GTS_CFG_B, EOS | 1, 1, 1, 1 |
| 3, 2 | DCI_MATCH, MMCM_LOCK | 1, 1 |
| 1, 0 | PART_SECURED, CRC_ERROR | 0, 0 |
| 30 | not in the table | 1 |

The device's own status says what the PS side's has said in every run: configured, started,
no error. Bit 30 is set and the table does not name it; nothing is made of that.

## What this does not show

- Whether a read of a LUT RAM frame delivers the RAM's content. The register says the mask
  is off; no frame of a LUT RAM whose content is known has been read. S2.2.
- Anything about a design other than the carrier. CTL0 is a register the bitstream writes;
  what another design's bitstream leaves in it is read in S2.1 (its outcome 7: a difference
  there is a finding, not a failure).
- Anything about the path to user logic or the design `s2a`: S2.1, which has not been run
  and waits for the owner's word of its own.

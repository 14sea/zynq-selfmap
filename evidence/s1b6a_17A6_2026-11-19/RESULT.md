# S1b.6a, one run at `0x01800000` — EBAZ4203 `17A6`, 2026-11-19: stopped by the walk (`0x900`), FAIL

Question (docs/s1b_plan.md, section 65): after the last frame of block type 2 the device
names `0x01800000`. Can a frame be read there, and does the register go on?

**A frame can be read there, and the register goes on — further than one pass of the walk is
allowed to follow. From `0x01800000` the register behaves as elsewhere and steps through
columns of one frame: five in the top half, `0x01800000..0x01800200`; a standstill; five in
the bottom half, `0x01c00000..0x01c00200`; a second standstill, and after the frame read
there the register holds `0x02000000`. The set allows one standstill in a pass, so the
prober stopped at the second, as it is made to: status `0x900`, 21 records, the first pass
not finished, no second pass. The judge fails the run for that and for nothing else. Every
frame delivered is all zero; no anomaly, no error bit, no status bit that is not usual; the
PL configured afterwards.**

**This ending is none of the six section 65 named beforehand.** It is the one section 62
named for the chain (its ending 3): rows shorter than a pass, two row ends in one pass, a
stop of the walk's making and not of the device's. I did not carry it over to this run's
list, and should have: block type 2 had just shown rows shorter than a pass.

Nothing was graded: there is nothing to grade against.

## The run

Released by the owner on 2026-11-19 after the review of section 66. The host side at commit
`9acff24`; the image `prober.bin`, 11,970 bytes, sha256 `fdc4f07f…9452` (kept here); the set
`s1b6a` (kept here as `expected_s1b6a.json`): the set `s1b5a` with the start at `0x01800000`
and the envelope's upper end at `0x01ffffff`. Nothing else ran on the host.

- Pre-check 18:52 UTC (`precheck_console.log`): U-Boot at its prompt, `carrier.bit` on the
  card (2,083,863 bytes), status `50033004` as the last run had left it.
- A `reset`; the usual fresh prompt, status `a802000a`.
- 18:52–18:53 UTC: the one run (`run/`, `run.out`), 36 seconds. The design loaded from the
  card.
- The prober: `SM4 end status=00000900 records=00000015 anomalies=00000000`; it returned
  `0x900` to U-Boot. The run script did not stop: the result was saved, pulled and checked
  as after any run.
- The result is the board's: the checksum on the board before the save is the checksum on
  the host after the pull (`ed65874b`); the card copy verified; none of the 5 pieces pulled
  a second time; no short reply not whole.
- Status afterwards `50033004`: the PL still configured, no error bit, no bit 5.
- Committed as stored (`914413a`) before the listing of status bits and the layout were made.
- After the run nothing was sent to the board: no second run, no `reset`.

## What it found (`run/verdict.json`, `layout.json`, `status_seen.json`)

- **21 records**: the reference frame once, then for each of 10 addresses the pad alone and
  the pad with a frame. All of pass 0. No read of three frames, no second pass, no reference
  read after the first.
- **The register, read after every read**:

  | address | after the pad alone | after the pad and the frame |
  |---|---|---|
  | `0x01800000` | `0x01800080` | `0x01800100` |
  | `0x01800080` | `0x01800100` | `0x01800180` |
  | `0x01800100` | `0x01800180` | `0x01800200` |
  | `0x01800180` | `0x01800200` | `0x01800200` |
  | `0x01800200` | `0x01800200` (stood still) | `0x01c00000` |
  | `0x01c00000` | `0x01c00080` | `0x01c00100` |
  | `0x01c00080` | `0x01c00100` | `0x01c00180` |
  | `0x01c00100` | `0x01c00180` | `0x01c00200` |
  | `0x01c00180` | `0x01c00200` | `0x01c00200` |
  | `0x01c00200` | `0x01c00200` (stood still) | `0x02000000` |

  The same pattern as at the row ends of block types 0, 1 and 2: one step for every 101
  words, the step after a row's last frame taken up by a place where the register still
  shows that frame's address, and then the first address of what follows.
- **By the fields**: block type 3; the top half, row 0, columns 0 to 4, minor 0 each; then
  the bottom half, row 0, columns 0 to 4, minor 0 each. Ten addresses, one frame a column.
  The layout program lists the top row as walked whole and the bottom row as not ended,
  because the walk did not take the step after its second standstill.
- **After the frame at `0x01c00200` the register held `0x02000000`** — by its fields block
  type 4, top half, row 0, column 0, minor 0. The prober read that value and stopped; the
  address was never written to the register and nothing was read there.
- **Content: all 10 frames are all zero.**
- **The status register**: 107 status words, none with a bit outside the error mask and the
  usual ones. The pad was all zero at every read; no transfer failed.

## What this does and does not say

- **The address register does not end at block type 2.** There are addresses whose block
  type field is 3 at which a read completes without an error and after which the register
  steps on as it does everywhere else. UG470 says a normal bitstream does not include this
  block type; it does not say the register has no such addresses, and it has.
- **It is weaker evidence than any list so far.** Each of the ten addresses was read once
  with a frame, in one pass that was not finished: no second pass, no read of three, no
  second run. The run is a failed run by its judge, and the layout says of itself that it is
  not a finding. What stands is what the records show: twenty reads, each with the register
  read after it.
- **It does not show block type 0 readable afterwards** (section 60): a run stopped with
  `0x900` has no reference read after its last read. What there is: the prober returned, the
  status afterwards has `PCFG_DONE` and no error bit, and U-Boot answered. The next run of
  anything begins with a new load of the design.
- **It is not a list of block type 3.** Two rows of five were seen, and the register then
  pointed at block type 4. Whether a frame can be read at `0x02000000`, and how far the
  register goes on, is not known. The block type field has three bits.
- **The content says nothing**, as in block type 2: all zero.
- Five is the number of columns in a row of block type 1, as 56 — the columns of one frame
  in a row of block type 2 — is the number of columns in a row of block type 0. That block
  type 3 holds one frame for each column of block type 1 is a guess from the counts, like
  the other. Not shown.
- What block type 3 is, is not learnt; UG470 and UG585 only, as agreed, and they do not say.

## What follows

Nothing, until the owner says. The walk as it is cannot cross this block type in one pass:
its two rows together are shorter than a pass and each ends with a standstill. Going on
needs a set that allows two standstills in a pass (the prober and the judge take up to
four; no program would change) and a decision about `0x02000000`. Neither is proposed here.

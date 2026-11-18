# S1b.4a, one run into block type 1 — EBAZ4203 `17A6`, 2026-11-18: PASS

Question (docs/s1b_plan.md, section 46): does the walk, as it is, work at the address the
device named after the last frame of block type 0?

**It does, over the 64 frames of this run. From `0x00800000` the device behaved as it does in
block type 0: after the pad alone the register names the next number, a frame can be read
there, a read of three frames goes on by itself, and two passes agree. 64 addresses,
`0x00800000..0x0080003f`, all with the fields of block type 1, top half, row 0, column 0,
minors 0 to 63; after the last the device names `0x00800040`. Every frame delivered is all
zero. No anomaly, no overflow, no interface failure; the reference frame in block type 0 was
as known at every one of its 14 readings in between.**

## The run

Released by the owner on 2026-11-18 after the review of section 47. The host side at commit
`6163031`; the image `prober.bin`, 11,970 bytes, sha256 `fdc4f07f…9452` (kept here, the one
of S1b.3a and S1b.3); the set `s1b4a` (kept here as `expected_s1b4a.json`): the set of the
chain over block type 0 with the start fixed at `0x00800000` and the envelope's upper end at
`0x00ffffff`. Nothing else ran on the host.

- Pre-check 16:48 UTC: U-Boot at its prompt, `carrier.bit` on the card (2,083,863 bytes).
  The status word still read `50033004`, as the last run of the chain had left it.
- A `reset`; the usual fresh prompt, status `a802000a`.
- 16:48–16:52 UTC: the one run (`run/`, `run.out`). The design loaded from the card.
- The prober: `SM4 end status=00000001 records=00000124 anomalies=00000000`, return code 0.
- The result is the board's: the checksum on the board before the save is the checksum on the
  host after the pull; the card copy verified. 2 of 69 pieces were pulled a second time. No
  short reply came back not whole.
- Status afterwards `50033004`: the PL still configured, no error bit.
- Committed as stored (`ed538c8`) before the layout was made.

## What it found (`run/verdict.json`, `layout.json`)

- **292 records**: 128 reads of the pad alone, 128 of the pad and a frame (64 addresses, two
  passes), 22 reads of three frames, 14 of the reference frame. The judge passes the run and
  lists nothing.
- **The register**: at every one of the 64 addresses the pad alone leaves it at the next
  number, and that address is the one read next. No standstill. Both passes ended at the
  limit of 64 frames, both told `0x00800040`.
- **The fields** of all 64 addresses: block type 1, top half, row 0, column 0; minors 0, 1,
  …, 63. The column was not left: it has at least 64 frames, and minor 64 is named. No column
  of block type 0 is longer than 42.
- **Going to and fro** between the reference frame in block type 0 and block type 1 needed
  nothing: 14 reference reads, each as known.
- **Content: every one of the 64 frames is all zero**, in both passes and in the reads of
  three.

## What this does and does not say

- The walk's rules, made on block type 0, held for these 64 frames of block type 1. That is
  what the step was for.
- It is not a list of anything: one column begun, not ended.
- **The content says nothing here.** With every frame all zero, "the same twice, and the same
  in a read of three" cannot tell one frame from another; the 64 addresses rest on the
  register alone, read after every read. The same was true of most of block type 0.
- **Nothing is learnt about the carrier and block RAM.** All zero is what block RAM that is
  not there, or not used, or used and holding zeros would each give; and one column of one
  row is not the device.
- Nothing was seen to go wrong with the interface or with the PL's configuration (status
  afterwards as after every run). Whether reading these frames disturbs a design that uses
  block RAM is not something this run could see: nothing here uses the carrier.
- Nothing was graded.

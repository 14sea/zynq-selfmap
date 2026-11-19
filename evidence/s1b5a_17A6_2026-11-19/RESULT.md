# S1b.5a, one run into block type 2 — EBAZ4203 `17A6`, 2026-11-19: PASS

Question (docs/s1b_plan.md, section 58): after the last frame of block type 1 the device
names `0x01000000`. Can a frame be read there, and does the walk, as it is, work there?

**It does, over the 64 addresses of this run — outcome 1 of the four said beforehand. From
`0x01000000` the register behaves as it does in block types 0 and 1, and it steps through a
structure of its own: columns of one frame. The top half has one row of 56 such columns,
`0x01000000..0x01001b80`; after the last the register stands still for one step and then
names `0x01400000`, the bottom half, where 8 more columns of one frame were walked before
the limit of 64. Every frame delivered is all zero. No anomaly, no overflow, no interface
failure, no status bit that is not usual — bit 5 did not show. The reference frame in block
type 0 was as known at each of its 14 readings, the last of them after the last read in
block type 2.**

Nothing was graded: there is nothing to grade against (section 58). This is the first result
here that stands on the device alone.

## The run

Released by the owner on 2026-11-19 after the review of section 60. The host side at commit
`d5684de`; the image `prober.bin`, 11,970 bytes, sha256 `fdc4f07f…9452` (kept here, the one
that has been on the board since S1b.3a); the set `s1b5a` (kept here as
`expected_s1b5a.json`): the set `s1b4a` with the start at `0x01000000` and the envelope's
upper end at `0x017fffff`. Nothing else ran on the host.

- Pre-check 15:58 UTC (`precheck_console.log`): U-Boot at its prompt, `carrier.bit` on the
  card (2,083,863 bytes), status `a802000b`.
- A `reset`; the usual fresh prompt, status `a802000a`.
- 15:58–16:02 UTC: the one run (`run/`, `run.out`). The design loaded from the card.
- The prober: `SM4 end status=00000001 records=00000124 anomalies=00000000`, return code 0.
- The result is the board's: the checksum on the board before the save is the checksum on the
  host after the pull (`473a51c4`); the card copy verified. 2 of 69 pieces were pulled a
  second time. No short reply came back not whole.
- Status afterwards `50033004`: the PL still configured, no error bit, no bit 5.
- Committed as stored (`4858ffc`) before the listing of status bits and the layout were made.
- After the run nothing was sent to the board: no second run, no `reset`. It was left as the
  run left it.

## What it found (`run/verdict.json`, `layout.json`, `status_seen.json`)

- **292 records**: 128 reads of the pad alone, 128 of the pad and a frame (64 addresses, two
  passes), 22 reads of three frames, 14 of the reference frame. The judge passes the run and
  lists nothing.
- **The register.** After the pad alone at `0x01000000` it names `0x01000080`; a frame can be
  read at `0x01000000`, and after the pad and the frame the register holds `0x01000100`: one
  step for every 101 words, as everywhere before. The address named is always the next *column* at minor 0: by the fields, each column of
  block type 2 has one frame. Both passes took the same 64 addresses and both were told
  `0x01400400` at the limit.
- **The top half**: row 0, columns 0 to 55, one frame each — 56 addresses,
  `0x01000000..0x01001b80`, walked whole.
- **The end of that row**: at `0x01001b80` the pad alone leaves the register where it is; the
  frame read there leaves it at `0x01400000`. One standstill, the one a pass is allowed; the
  same behaviour as at the row ends of block types 0 and 1. A read of three frames from
  `0x01001a80` runs to the row's last frame and leaves the register at `0x01400000` too.
- **The bottom half**: row 0, columns 0 to 7, one frame each, `0x01400000..0x01400380`; then
  the limit. The row was not ended: column 8 (`0x01400400`) is named and was not read.
- **Content: every frame delivered is all zero** — 64 addresses in two passes and the reads
  of three, 194 frames in all.
- **The status register**: 1,462 status words in the run, none with a bit outside the error
  mask and the usual ones. Reading these frames does not raise bit 5, which reading columns
  2 to 4 of block type 1 does.
- **Going to and fro** between the reference frame in block type 0 and block type 2 needed
  nothing: 14 reference reads, each as known, at most 16 frames between two of them. The
  run was walked to its end, so the last record is a reference read after the last read in
  block type 2 (section 60's table, first line): block type 0 was readable afterwards.

## What this does and does not say

- The address register knows block type 2. It does not pass through it in one step or leave
  it at once: it steps through rows and columns there, by the same rules as elsewhere, and
  PCAP delivers a frame of 101 words at each address without an error.
- 56 is also the number of columns in a row of block type 0. Both numbers are the device's;
  that the one-frame columns of block type 2 stand one for one beside the columns of block
  type 0 is a guess the count suggests, not something this run shows.
- **It is not a list.** The bottom row was begun, not ended; what the device names after it
  is not known, nor whether there is more than these two rows. If the bottom row is like the
  top one, block type 2 has 112 addresses — a guess.
- **The content says nothing.** All zero is what frames that hold zeros, frames that hold
  something the readback does not deliver, and addresses with nothing behind them would each
  give. The walk has only ever read addresses the device named, so there is no reading of an
  address that does not exist to hold this against. The 64 addresses rest on the register
  alone, read after every read.
- What block type 2 *is* is not learnt. UG470 names it (`CFG_CLB`, table 5-24) and, as far as
  I have found, says nothing more; nothing else was consulted, as agreed.
- The 5,144 addresses of block types 0 and 1 stand as they were. These addresses are beyond
  that count, and the grader's database has no block type after 1: nothing here was graded
  and nothing here can be, as things are.
- Whether reading these frames disturbs the loaded design is not something this run could
  see beyond the reference frame and the status: nothing here uses the carrier.

## What follows

Nothing, until the owner says. By section 58 a chain over block type 2 would be the next
proposal after outcome 1; it has not been written.

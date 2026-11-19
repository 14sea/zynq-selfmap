# S1b.5, the chain over block type 2 — EBAZ4203 `17A6`, 2026-11-19: complete

Question (docs/s1b_plan.md, section 62): which frame addresses does the device name from
`0x01000000` on, as far as the envelope `0x0..0x017fffff` goes?

**112 addresses, in two rows of 56: the top half and the bottom half, row 0 each, 56 columns
of one frame each. The register behaves as in block types 0 and 1 throughout, with a
standstill at the end of each row. After the last frame the device names `0x01800000`, which
is above the envelope: it was named, not read, and the chain is complete — ending 1 of the
five said beforehand. Two runs, both PASS; no anomaly, no overflow, no interface failure; no
status bit that is not usual; the reference frame in block type 0 as known at all 25 of its
readings, the last of them after the last read in block type 2. Every frame delivered is all
zero.**

Nothing was graded: there is nothing to grade against (section 58). This list stands on the
device alone.

## The runs

Released by the owner on 2026-11-19 after the review of section 63. The host side at commit
`e700289`; the image 11,970 bytes, sha256 `fdc4f07f…9452`, the one that has been on the board
since S1b.3a; the set `s1b5`: S1b.5a's set with the start given by the chain. `prober.bin`
and `expected_s1b5.json` are kept here; they were copied in from the build directory before
the first run and are the files both runs were checked against. Nothing else ran on the host
while the board was in use.

- Pre-check 17:34 UTC (`precheck_console.log`): U-Boot at its prompt, `carrier.bit` on the
  card (2,083,863 bytes), the status word `50033004` as S1b.5a had left it. A `reset`; the
  usual fresh prompt, status `a802000a`.
- 17:34–17:39 UTC: the first run alone (`first_run.out`). PASS; 64 frames from `0x01000000`.
  Looked at — it is the stored run of S1b.5a over again, record for record, but for how many
  times a transfer was polled — and committed (`a7d6d90`) before the chain went on.
- 17:40–17:44 UTC: the chain unattended (`chain_to_the_end.out`): run 1, after a `reset`,
  checked (`resets_console.log`). PASS; 49 frames from `0x01400380`, and both passes ended
  because the device named an address outside the envelope.
- In all: 2 runs, 516 records — 226 reads of the pad alone, 226 of the pad and a frame, 39
  reads of three frames, 25 of the reference frame. 2 of 122 pieces were pulled a second
  time, one in each run. No short reply came back not whole. Status after each run
  `50033004`.
- Committed as stored (`e723687`) before anything was made of it. After the chain nothing
  was sent to the board.

## What the two runs found (`rows.json`, sha256 `4d1f2fbe…816d`, commit `d999cec`)

- **112 addresses**, rising, each the one named after the one before; nothing unexpected.
- **Two rows, both walked whole**:

  | | first | last | frames | columns | ended by | named after it |
  |---|---|---|---|---|---|---|
  | top half, row 0 | `0x01000000` | `0x01001b80` | 56 | 56 of one frame | the register stood still | `0x01400000` |
  | bottom half, row 0 | `0x01400000` | `0x01401b80` | 56 | 56 of one frame | the register stood still | `0x01800000` |

- **Every column has one frame**, minor 0, and after it the device names minor 0 of the
  column numbered one higher.
- **The end**: at `0x01401b80` the pad alone leaves the register where it is; the frame read
  there leaves it at `0x01800000` — by its fields block type 3, top half, row 0, column 0,
  minor 0. Both passes of run 1 ended there, and a read of three frames from `0x01401a80`
  leaves the register at the same address. That address was never written to the register.
- **The seam**: run 1 began at `0x01400380`, the last frame run 0 walked: the same frame,
  the same address named after it, no standstill in either.
- **Content: all 112 frames are all zero** — in both passes, in the reads of three, and in
  both runs where an address was read by both (343 frames delivered in all).
- **The status register** (`status_seen.json`, commit `9c32dc3`): 2,584 status words in the
  two runs, none with a bit outside the error mask and the usual ones. Bit 5 did not show.
- **The reference frame**: 25 readings, each as known, at most 16 frames between two of
  them. Both runs were walked to their end, so each ends with a reference read after its
  last read in block type 2: block type 0 was readable afterwards.

## The first run against the stored run of S1b.5a (`first_run_against_s1b5a.json`, commit `91598d3`)

All 64 addresses of the stored run are in the chain's list, in the same order, none more and
none fewer between the first and the last of them; the same frame at each; the same address
named after each; the standstill at `0x01001b80` in both. No disagreement. The program adds
what has to be added: every frame the two share is the same content, so that they agree on
it says nothing about which frame either read.

## What this does and does not say

- **Block type 2, as the address register has it, is these 112 addresses**: one frame for
  each of 56 columns, in each half. That rests on the register read after every read, on two
  passes and the reads of three in each run, on the seam, and on 64 of the addresses having
  been read on two occasions. It rests on nothing else: there is no second witness.
- **The content says nothing.** All zero is what frames that hold zeros, frames holding
  something the readback does not deliver, and addresses with nothing behind them would each
  give; the walk has only ever read addresses the device named, so there is no reading of an
  address that does not exist to hold this against. Learning what these frames are needs a
  write, which is not S1b's.
- 56 is the number of columns in a row of block type 0, and block type 2 has one row in each
  half as block type 0 has. That each of its frames belongs to the column of block type 0
  with the same number is a guess the counts suggest, not something shown.
- What block type 2 *is* is not learnt. UG470 names it `CFG_CLB` (table 5-24) and, as far as
  I have found, says no more; nothing else was consulted, as agreed.
- **`0x01800000` was named, not read.** UG470 says of its block type: "A normal bitstream
  does not include type 011." Whether a frame can be read there, and whether the register
  goes on from there, is not known and was not tried.
- The device's own count now stands at 5,256 addresses: 3,864 of block type 0, 1,280 of
  block type 1 — the 5,144 that were graded, with no difference — and these 112, which the
  grader's database does not carry.
- Whether reading these frames disturbs the loaded design is not something these runs could
  see beyond the reference frame and the status register.

## A slip of mine in the order of things

Section 63 says the summary, the comparison and the listing of status bits are each committed
before the next is made. The summary was; the comparison and the listing were made one after
the other and then committed, each in its own commit. Both are what unchanged programs give
over runs already committed, and a test now holds each file to what the program gives; nothing
was altered between. It is said here because the order was not the one written down.

## What follows

Nothing, until the owner says. Open, and not proposed: whether to read at `0x01800000`.

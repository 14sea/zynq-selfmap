# S1b — plan for the first widening (2026-11-13; the walk and step S1b.0 agreed by the owner the same day)

S1a showed the method on three known frames. S1b widens the range step by step until the device
has listed its own frames. Each step gets its plan reviewed, its host side built and tested, and
the owner's go-ahead before it touches the board. This document proposes how to walk, and
details the first step only.

## Where S1b stands (an index, kept up to date; last changed 2026-11-19, after S1b.5a)

The sections below are in the order in which things were proposed, built, reviewed and run,
and none is rewritten afterwards. This table says where each step is to be found and what it
gave. Evidence is under `evidence/`; every directory with a board run has a `RESULT.md`.

| step | the question | sections | evidence | what came of it |
|---|---|---|---|---|
| S1b.0 | does the device name its next address? | 2, 5–8 | `s1b0_17A6_2026-11-14` | PASS. The address register can be read back; after n frames read from F it holds F + n + 1 |
| S1b.0b | where does the register stand after the pad alone? | 9–11 | `s1b0b_17A6_2026-11-14` | PASS. On F + 1: one step for every 101 words, the pad included. This is how the walk asks for the next frame without reading it |
| S1b.1 | the walk of one column | 12–14, 23, 24 | `s1b1r_17A6_2026-11-15` | PASS with the quiet wait. 36 frames, `0xb80..0xba3`, then `0xc00`. Graded: no difference |
| — the receive-FIFO overflow | why the walk stopped at first | 15–22 | `s1b1_17A6_2026-11-14`, `fifo_rate_17A6_2026-11-14`, `dx_17A6_2026-11-15`, `quiet_17A6_2026-11-15` | The polling loop stored to the stack while a transfer ran. A wait that stores nothing does not overflow. The mechanism in the hardware is not known |
| S1b.2 | the row: its columns and their frames | 25–28 | `s1b2_17A6_2026-11-15` | 30 runs, columns 0 to 54 walked whole; the chain halted, by its rule, at the end of the row |
| S1b.2b | what the end of a row is | 29–31 | `s1b2b_17A6_2026-11-16` | After the last frame the register stands still for one step, then names `0x00400000`. The row: 56 columns, 1,932 frames |
| — the row graded | | 32–34 | `s1b2b_17A6_2026-11-16` (`row_closed.json`, `grade.json`) | No difference from prjxray-db |
| S1b.3a | a walk that crosses the end of a row | 35–37 | `s1b3a_17A6_2026-11-17` | PASS. One standstill allowed in a pass; beyond it the register behaves as before |
| S1b.3 | all of block type 0 | 38–45 | `s1b3_17A6_2026-11-17` | Complete in 62 runs. 3,864 addresses: the top half and the bottom half, one row each, 1,932 frames and 56 columns each, the columns of equal length one for one. After the second row the device names `0x00800000`. Graded: nothing differs |
| — a halt of the host's making | run 51 of that chain | 42–44 | `s1b3_17A6_2026-11-17/halted_at_run51` | The console lost characters while the result header was read. The run script now asks again for a short read-only reply that is not whole; the run was set aside and the chain taken up again |
| S1b.4a | does the walk work in block type 1? | 46–48 | `s1b4a_17A6_2026-11-18` | PASS. `0x00800000..0x0080003f`, the register as in block type 0, every frame all zero |
| S1b.4 | all of block type 1 | 49–52 | `s1b4_17A6_2026-11-18` | Complete in 21 runs. 1,280 addresses: the top half and the bottom half, one row each, 5 columns of 128 frames. After the second row the device names `0x01000000`. Graded: nothing differs. Two things seen and not explained (section 52) |
| — small checks after S1b.4 | the PS registers; does bit 5 clear? | 53–57 | `pslook_17A6_2026-11-19`, `sbit_17A6_2026-11-19` | The level-2 cache is off, the DDR ports have equal priority. Bit 5 clears with one write and stays away |
| S1b.5a | can block type 2 be read, and does the walk work there? | 58–61 | `s1b5a_17A6_2026-11-19` | PASS. Columns of one frame: 56 in the top half (`0x01000000..0x01001b80`), a standstill, then `0x01400000` and 8 more before the limit. Every frame all zero; bit 5 did not show. Not graded: nothing to grade against |

Section 3 is the outline as it was first drawn, section 4 the owner's first decisions,
section 41 how the mutants are run. Section 53 is the account of what is not understood so
far; sections 54 and 55 are the small checks proposed and built after it, sections 56 and
57 what they gave on the board. Sections 58 to 61 are the one run into block type 2;
section 62 proposes the chain over it.

**What the device has said so far.** Block type 0 has 3,864 frame addresses in two rows. Each
row has 56 columns: 41 of 36 frames, 9 of 28, 4 of 30 and 2 of 42. With the carrier design
loaded, 428 of those frames are not all zero (178 in the top row, 250 in the bottom row).
Block type 1 has 1,280 frame addresses in two rows of 5 columns of 128 frames; the frames of
columns 0 and 1 are all zero, those of columns 2 to 4 all hold one and the same content that
is not zero. After block type 1 the device names `0x01000000`. In all 5,144 addresses, the
number the proposal gave as the database's; graded, none differs. At `0x01000000` block
type 2 begins, and it can be read: 56 columns of one frame in the top half, then the bottom
half, of which 8 columns of one frame have been walked and no end seen; every frame all
zero. These are beyond the 5,144 and have no second witness.

**What S1b can and cannot stand behind** is said in section 3 and has not changed: which
addresses the device names, and that reading them is repeatable and does not depend on the
path. Not the content. Where frames are all alike — all zero in most of block type 0, all
zero or all one pattern in block type 1 — the list rests on the address register and on the
reference frame alone. UG470 lists block-RAM content among what a readback reads (it is the
background readback check that skips it; section 46), but nothing in S1b tests whether what
is delivered in block type 1 is what is stored there.

**Still open in S1b.**

- Block type 2: one run has been made into it (section 61). The bottom half is not walked
  to its end, and what the device names after it is not known. A chain over it is proposed
  in section 62; not decided.
- What the frames of columns 2 to 4 of block type 1 hold, and which reads of them raise the
  status bit (sections 52, 53, 57). The bit itself clears and stays away (section 57).
- The frame census as one document beside the schema (proposal, section 4): which addresses
  exist, their block type, whether readback is stable. So far each step has its own summary
  (`rows.json`, `top.json`, `layout.json`); the one document has not been written.
- Not explained: why the stores to the stack overflowed the FIFO; what the places at the end
  of a row are.

## 1. How to find the next frame: ask the device

The open question since the proposal is what happens when a frame address that does not exist is
addressed. The plan here is to never have to find out:

- UG470 says the frame address register increments by itself as frames are read.
- So after reading a frame, read the FAR register back. Whatever it says is the next frame
  the device itself names. The prober addresses only what was given to it as a start (one address
  already known to exist) and what the device has named since.
- The walk stops when the address the device names leaves the envelope the host gave.

The alternative — stepping through addresses arithmetically and seeing what comes back — would
send addresses nobody has seen exist. It is not proposed.

Two things in this are new and unverified on our board, which is why the first step tests them
on the known frames before anything is walked:

1. reading a configuration register (FAR) through PCAP — a one-word read; zynq-psmap's sequence
   only ever read FDRO;
2. what the FAR reads after an FDRO read that includes the pad frame (the next frame, or the one
   after).

## 2. Step S1b.0 — does the device name its next address? (on the three known frames)

Nothing outside `0x00000b98..0x00000b9a` is addressed. Nothing is written to configuration
memory.

| # | what the prober does | known answer |
|---|---|---|
| a | reads FAR `b98` as in S1a, then reads the FAR register | the frame: yes. The FAR value: predicted `b99` or `b9a`; which one is the finding |
| b | the same from `b99` | as above, one higher |
| c | one FDRO read of three frames starting at `b98` (404 words: the pad and three frames) | the three known frames, in order |
| d | after (c), reads the FAR register | predicted three or four above `b98` |
| e | repeats (a) to (d) twice more | identical every time |

Pass: every frame equals the known frame; the FAR values are the same on every repeat and are
consistent with one rule (either "next" or "next but one") across (a), (b) and (d). Anything else
is recorded and the walk of S1b.1 is not attempted.

What has to change in the prober, all still read-only:

- the generator gains two streams: "read the FAR register" and "read N frames from an address";
- the guard additionally accepts the one-word FAR read header and a longer Type-2 read, up to
  the length the stage allows;
- the destination buffer grows to 404 words (1616 bytes, still inside one 4 KiB page);
- a new stage number in the parameter block, and a record layout that carries the FAR read back.

The twin's model of the configuration engine gets a FAR register that increments; which of the
two rules it follows is a switch, and the tests run both, because the board has not said yet.

The judge and the run script are generalised from S1a's, with the same principles: save first,
judge afterwards; re-derive everything from the raw words; the echoed parameters must be the
planned ones.

## 3. The steps after it (outline; each gets its own plan)

| step | envelope | start | what it yields |
|---|---|---|---|
| S1b.1 | the column of the known frames (`0x00000b80..0x00000bff`) | minor 0 of that column — it exists because minor 0x18 does | how many frames this column has; every frame of it read twice |
| S1b.2 | the row of that column, block type 0, top half | where S1b.1 began | the columns of the row and their frame counts; what the address does at the end of a row |
| S1b.3 | all of block type 0, both halves | — | the frame list of block type 0 |
| later, a separate decision | block type 1 (block-RAM content) and block type 2 | — | UG470 warns that reading block-RAM content interferes with user functions; the carrier design must be checked for block RAM first |

From S1b.1 on most frames have no known answer, and none is manufactured: **no bitstream is
parsed on the host, not even for grading** (owner, 2026-11-13 — the method has to carry over to
devices where that is not practical). What S1b claims is therefore limited to what it can stand
behind:

- *which frames exist*, as named by the device — graded afterwards against prjxray-db's frame
  list for this part, where such a database exists;
- *that reading them is repeatable and independent of the path*: every frame is read twice, and
  once more as part of one long read that relies on the address incrementing by itself; all
  must be identical. An address that silently returned another frame's content would have to
  do so identically on both paths;
- the three known frames still equal to their known values; the reference frame unchanged.

It does not claim that the content read from the other frames is what the PL holds. That is
established later and differently: from S2 on the prober writes known patterns through user
logic and finds them in the readback, which checks content without any external description.

## 4. Decisions (owner, 2026-11-13)

1. The walk follows the address the device names; addresses are not stepped through.
2. Reading the FAR register is accepted as the first new kind of packet, tried on the known
   frames first. Its words are UG470 table 6-1 with the FAR address in the header: `NOOP`,
   `28002001`, `NOOP`, `NOOP`, then one word read. It is sent in the same session as the frame
   read, before the cleanup stream, so that it shows the address as that read left it.
3. No bitstream parsing on the host, for grading or otherwise. The grader is prjxray-db's
   existing content (the frame list now; bit roles in later stages). Vivado is used to build the
   PL design and for nothing else.

## 5. S1b.0 as built (host side; written before the board run — the result is in section 8)

**What there is to review:** this plan; stage 2 in `prober/sm_core.c` (`read_op`, `run_s2`, and the
three additions to the guard); `host/s1b0_judge.py`; the plan printed by
`host/s1a_run.py --stage s1b0 --dry-run`; the image and parameters fixed in
`build/prober/expected_s1b0.json`.

- **One image for both stages.** The prober picks the stage from the parameter block. Stage 1 runs
  as before (its tests are unchanged), but the image is a new build and has a new hash.
- **Parameters of the run:** envelope `0x00000b98..0x00000b9a`, reference `0x00000b99`; three
  operations — one frame at `b98`, one frame at `b99`, three frames from `b98` — each three
  times; anomaly budget 4; poll limit 0x200000.
- **Each operation, in one session:** the frame read (the pinned stream with the length of
  n + 1 frames), the FAR register read (`NOOP`, `28002001`, `NOOP`, `NOOP`, then one word), the
  cleanup. Five DMA commands, each cleared, verified, ordered and waited for as in S1a, each
  with `PCFG_DONE` checked before and during.
- **Record:** 480 words — the three streams as sent, the status and poll count of all five
  commands, the FAR value read back, up to 404 raw data words.
- **Anomalies:** as in S1a, plus two of the data class: the FAR value differs from the first run
  of the same operation; the FAR read delivered nothing. The reference read is healthy only if
  both its frame and its FAR value equal the baseline's.
- **What the board is expected to answer and what would count as which outcome:**

| outcome | meaning | consequence |
|---|---|---|
| PASS, rule "next" | after reading n frames from F the register holds F + n | inside a column the value can be used as the next address; how it behaves at the end of a column is not shown by S1b.0 and is the first thing S1b.1 has to observe, on an address the device has named |
| PASS, rule "next but one" | it holds F + n + 1 (the pad frame counted) | **open — to be settled before S1b.1 is planned.** Subtracting one is arithmetic on an address, which the walk is meant never to do: inside one column it may give the frame in between, at a column boundary it need not give a valid address at all. S1b.0 only sees three consecutive frames and cannot tell |
| FAIL: values consistent but fitting neither rule | the register does something else | recorded; S1b.1 is redesigned before it is planned |
| FAIL: the FAR read never completes, or delivers nothing | a one-word register read does not work through PCAP as sent | recorded; an interface stop may need a power cycle; the walk needs another way |
| FAIL: the three-frame read does not return the three known frames | reading across frames in one read does not behave as UG470 says here | recorded; long reads are not used |

- **The twin does not know the answer.** Its FAR register follows either rule by a switch, and
  the tests run both; a board result is not predicted by it.
- **Tests and mutants:** 121 tests; `tests/mutants.py` carries 102 deliberate defects across the
  prober (both stages), both judges and the run script, all failed by the suite
  (`evidence/host_checks/mutants_2026-11-13.txt`). The first run of the enlarged set had one
  survivor — a repeat of a three-frame read compared on its first frame only — which showed a
  gap in the twin's faults (none could touch a later frame); a fault and a test were added.

New compared with S1a, and so what could go wrong on the board: a one-word read through PCAP;
a 404-word read; five commands per session instead of three. None writes configuration memory.

## 6. Changes after the first review of S1b.0 (2026-11-13)

Two gaps were found by the reviewer and reproduced before they were fixed.

| finding | fix | held by |
|---|---|---|
| The guard (and the independent reader) accepted a second FDRO read in one stream while still judging the range by the first frame address — but after a read the device's address has moved on, so the second read would start past what was checked | a read uses up the frame address: another read needs a new address, which is checked like the first | `test_one_fdro_read_per_frame_address` |
| With stage S1b.0 selected, a valid result of stage S1a (or the reverse) was not saved: only its header was kept, because the size was checked against the selected stage — and an earlier test had asserted exactly that | how much is saved no longer depends on the stage asked for: a result consistent with any known layout is saved whole, to the card and to the host, and then judged; a header that fits no layout, or no header at all, gets everything a result could occupy saved | `test_a_valid_result_of_the_other_stage_is_saved_whole_and_fails`, `test_a_header_that_fits_no_layout…`, `test_sizes_are_believed_only_under_a_valid_magic`, `test_with_no_result_header…` |

The generator never produces a second read, so no board run was affected; the guard exists for
the day the generator is wrong. The board image changed with the guard and its hash is fixed
again in `build/prober/expected_s1b0.json`.

## 7. Changes after the second review of S1b.0 (2026-11-14)

No new defect in the normal flow. Three points, all accepted:

| finding | change |
|---|---|
| A PASS with the rule "next but one" was said to let the walk use the value minus one. S1b.0 cannot support that: it sees three consecutive frames only, and subtracting is the address arithmetic the walk was meant to avoid | the table in section 5 no longer derives a walk from either outcome beyond what the run shows; what to do under "next but one", and what happens at a column end under either rule, are open items for the planning of S1b.1 |
| The guard compared `address + frames` with the upper bound; at the top of the address space the sum wraps and passes (reproduced: envelope `fffffffe..ffffffff`, three frames from `ffffffff`; the Python reader refused it) | the guard and the parameter check compare a difference instead, which cannot wrap (`test_the_range_check_cannot_be_wrapped`) |
| The dry run did not list the `loady 04000000` that is sent when the card has no PL file of the right size | the dry run prints that branch as its own line and lists the three branches after `go` |

Images of this stage, in order: `35ae0fd2…` (7727 bytes, first submitted); `9d047501…` (7731 bytes,
after the first review); `3e3ab201761ab6e6af3036b3f8206273dd78cc4deb430bc3a0569900d7ccee07`
(7703 bytes, crc32 `53130c7c`, after this review — the one in `build/prober/expected_s1b0.json`).

Host checks after this review: 122 tests; 105 deliberate defects, all failed by the suite
(`evidence/host_checks/mutants_2026-11-14.txt`; the counts in section 5 are those of the first
submission). The first run after the range check was rewritten had one survivor: with the
difference form, a read that is not a pad plus whole frames was also refused by the range check
in every envelope the tests used, so removing the whole-frames check went unnoticed. A case with
the widest envelope (`0..ffffffff`), where the range check cannot refuse anything, now holds it
(`test_a_read_that_is_not_a_pad_plus_whole_frames…`). `tests/mutants.py` takes an optional
substring to run a subset.

Reading that record line by line showed one more weakness, in the mutant set itself: the defect
"the guard lets a read run past the envelope" had been written as `if (0)`, which leaves a
variable unused and does not build under `-Werror` — it was counted as failed by the suite
though no test had judged it (94 tests ran, not 122). It is now a defect that builds, and two
tests fail on it; the runner reports a mutant that changes the number of tests run as BROKEN
and counts it as not failed. The record above is from the run after this change: 105 of 105
failed with all 122 tests run.

## 8. S1b.0 on the board (2026-11-14): PASS, rule "next but one"

Released by the owner after the second review. One run on `17A6`, first attempt, no deviation
from the dry run; record in `evidence/s1b0_17A6_2026-11-14/RESULT.md`.

- The frame address register can be read through PCAP (one-word read, as sent).
- After a read of n frames starting at F it held **F + n + 1** in all 11 records: `0xb9a` after
  one frame at `0xb98`, `0xb9b` after one frame at `0xb99`, `0xb9c` after three frames from
  `0xb98`. The pad frame is counted.
- A three-frame read returned the three known frames in order, three times out of three.
- No error bit, no anomaly; the result on the board, on the card and on the host have one crc32.

This is the row of the table in section 5 that was left open. What S1b.1 needs settled before it
is planned — nothing below is decided:

1. **What the walk does with a value that is one further than the frame it wants.** Choices seen
   so far: (a) read from F with a count that covers the rest of the envelope in one long read,
   never computing an address, and use the register only at the end, as a report of how far the
   device says it went; (b) read frame by frame and take the next address as the value minus
   one — arithmetic on an address, valid inside a column only if minor addresses are dense, and
   unknown at a column end; (c) find a read that leaves the register on the next frame (for
   instance a read with no pad frame, or of the pad alone) — a new sequence, to be tried on the
   three known frames first, like this step.
2. **What the register does at the end of a column**, under either choice: it has not been seen.
   The three known frames sit at minors 0x18..0x1a of one column; S1b.1's envelope
   (`0x00000b80..0x00000bff`) contains the column end, wherever that is.
3. **Whether the count of one step per 101 words holds** for other lengths (it fits the two
   lengths tried: 202 and 404 words).

## 9. Step S1b.0b — where does the register stand after the pad alone? (plan and host side, 2026-11-14)

The owner chose the third of the three ways in section 8: before the walk is planned, look for a
read that leaves the register on the next frame — on the three known frames, like S1b.0.

**Why the pad alone.** S1b.0 saw start + frames + 1. One reading of that is that the register
moves once for every 101 words delivered, the pad included. If that is what happens, no read of
a pad plus frames can leave the register on the first frame not yet delivered: it is always one
further. But a read of the pad alone at F would deliver no frame and leave the register on
whatever the device takes to be the frame after F. That is the question the walk has to ask —
"what comes after F?" — answered by the device, with no arithmetic on the host or the prober.
Whether the device does this is not known; this step asks.

**What is run.** The same image as the other stages, stage 3 in the parameter block; envelope
`0x00000b98..0x00000b9a`, reference `0x00000b99`, three repeats of these eight operations, each
followed in the same session by the read of the address register:

| # | operation | words read | what it is for |
|---|---|---|---|
| 0 | one frame at `0xb98` | 202 | the read S1b.0 made: the register should say `0xb9a` again |
| 1 | the pad alone at `0xb98` | 101 | the question |
| 2 | no read at `0xb98` (the address is written, `RCFG` is given, nothing is read) | 0 | does the register give back what was written when nothing moved it |
| 3 | the pad alone at `0xb99` | 101 | the question at a second address |
| 4 | two frames from `0xb98` | 303 | a third length of read; the two frames are known |
| 5 | the pad alone at `0xb9a` | 101 | the question at the last frame of the envelope |
| 6 | no read at `0xb99` | 0 | as 2, at a second address |
| 7 | the pad alone at `0xb98` | 101 | as 1, but following an operation that read nothing instead of one that read a frame: does the value depend on what came before |

26 records (baseline, 24, final reference), 12,544 words. Every frame delivered is compared with
its known frame; the reference frame is read first and last, and after any anomaly.

**What is required for PASS, and what is only reported.** Required: the run completes with no
anomaly; every frame equals its known frame; and the same read at the same address leaves the
same value every time — across repeats (checked by the prober) and across the two places in the
sequence where the same read is made (checked by the judge). *Not* required: any particular
value. The judge reports a table — address, kind of read, value read back — and whether the
values fit "one step per 101 words": yes, no, or undetermined (section 10). The twin's register
follows any of three rules and the tests run all three; a PASS says the measurement is sound,
not that the answer is convenient.

| the register after the pad alone at F | what it would mean | what follows |
|---|---|---|
| F + 1 at all three addresses (`0xb99`, `0xb9a`, `0xb9b`) | on these frames the device names the frame after F without delivering F | S1b.1 can be planned around it: per frame, one read for the content and one for the successor. What the device names at the end of a column is then the first thing S1b.1 would see, inside its envelope, and is still unknown |
| F | the pad alone does not move the register; the two steps of a one-frame read both come with the frame | no successor read of this kind; the walk falls back to one long read over the envelope, the register read once at the end |
| anything else, or not the same at operations 1 and 7 | the register depends on more than the address and the length | recorded; the walk does not use the register until that is understood |

Other things the run can show, none required: operation 0 not saying `0xb9a` (yesterday's value
does not repeat: stop and look before anything else); operations 2 and 6 not saying the address
written (then a read-back value is not simply "where the device stands", and every reading above
needs rethinking); the 101 words of a pad-only read not being all zero (each such read is then an
anomaly; the budget is 24, one per target read, so the run still makes every measurement and
re-reads the reference after each).

**New compared with S1b.0, and so what could go wrong on the board:** a 101-word read; a 303-word
read; a session that gives `RCFG` and writes the address but reads no frame data before the
register read. None writes configuration memory. The stop rules are unchanged: an interface
failure stops the run at that command; a changed reference frame stops it; everything is saved
before it is judged.

**What changed in the code.**

- `prober/sm_core.c`: stage 3 is stage 2 with two more operations — a frame count of 0 (the pad
  alone) and `N_NONE` (no read: the two words of the read are NOOPs, no read command is queued,
  no pad is checked). Stage 2 still refuses both. The console tag follows the stage (`SM3`).
- The guard, and the independent reader in `host/packets.py`, now accept an FDRO read of exactly
  one frame of words. It delivers no frame, so only the address has to be inside the envelope.
  A count that is not a whole number of frames is still refused, and so is a second read without
  a new address.
- `host/s1b0_judge.py` takes the stage; `host/s1b0b_judge.py` is its stage-3 entry. A result of
  the other stage is INVALID to each, also when relabelled.
- `host/s1a_run.py --stage s1b0b`. Stages 2 and 3 share a record layout, so the run script no
  longer infers the stage from the sizes; the console lines kept are those of whichever stage
  really ran.
- `prober/twin_hal.c`: a third rule for the register (`SM_FAR_RULE=skipdata`: the pad counts only
  when a frame follows it).

**Host checks** (as first submitted; the counts after the review are in section 10). 154 tests;
119 deliberate defects, all failed by the suite with all 154 tests run. The first run of the enlarged set had
one survivor and one defect that did not build. The survivor: the stage-2 judge accepting the new
counts — no test offered it a stage-3 result relabelled as stage 2, which it would have passed;
that test now exists. The other was rewritten so that it builds.

**The image** changed with stage 3: 7886 bytes, sha256
`daa32b08711493745c1ac88cde497de575ca8e483c83c29500cd5694e202f99e`, crc32 `26e4b875`
(`build/prober/expected_s1b0b.json`). Stages 1 and 2 run from the same image and their twin
tests are unchanged and pass; the images that ran on the board for S1a and S1b.0 are kept with
their evidence.

**Before the board:** the owner's review of this section and of the code; then
`host/s1a_run.py --stage s1b0b --dry-run` and, on the owner's word only, `--go`.

## 10. Changes after the first review of S1b.0b (2026-11-14)

One finding, of medium weight, reproduced before it was fixed; the three changes the review was
asked to look at (the guard's pad-only read, stage 2 still refusing the new operations, the
stage no longer inferred from sizes) passed.

| finding | fix | held by |
|---|---|---|
| The judge put a FAR value into its table only from records whose code was 0. With every pad-only read anomalous for another reason (a pad that is not zero) under the rule where the pad does not move the register, all twelve FAR reads had succeeded and none had moved — yet the table had no 101-word row and the length rule was reported as holding. The verdict was FAIL and the raw records complete; the conclusion field was wrong | a FAR value is a measurement whenever the FAR read itself succeeded, whatever else is wrong with the record; the table names the records that had another anomaly, with their codes. The length rule has three answers: *no* as soon as one value does not fit; *yes* only if every value fits and every read the plan asked for has a value from a record with nothing else wrong; otherwise *undetermined*, with the reads that lack such a value listed | `test_a_far_value_is_a_measurement_even_in_a_record_that_is_anomalous_for_another_reason`, `test_the_length_rule_has_three_answers`, `test_a_far_value_that_differs_in_an_anomalous_record_is_in_the_table`, `test_a_far_read_that_failed_measures_nothing` |

The same selection was in the stage-2 judge (the rule of S1b.0 was drawn from clean records
only) and is changed with it: `test_the_rule_is_drawn_from_every_far_value_that_was_read…`.
The S1b.0 board run had no anomalous record, so its verdict and its rule are unaffected; the
stored result still passes the judge as it is now (`tests/test_board_evidence.py`).

Only the judge changed. The board image is the one of section 9 (`daa32b08…`, 7886 bytes).

Host checks after this review: 159 tests; 124 deliberate defects, all failed by the suite with
all 159 tests run (`evidence/host_checks/mutants_2026-11-14_s1b0b.txt`).

## 11. S1b.0b on the board (2026-11-14): PASS — the pad alone leaves the register on F + 1

Released by the owner after the review of section 10. One run on `17A6`, first attempt, no
deviation from the dry run; record in `evidence/s1b0b_17A6_2026-11-14/RESULT.md`. The board was
restarted with U-Boot's `reset` first, so that the run began as the earlier ones had.

| read | words | register afterwards |
|---|---|---|
| none | 0 | F (at `0xb98`, `0xb99`) |
| the pad alone | 101 | F + 1 (at `0xb98`, `0xb99`, `0xb9a`; at `0xb98` the same after a frame read and after an operation that read nothing) |
| the pad and one frame | 202 | F + 2 (as in S1b.0) |
| the pad and two frames | 303 | F + 3 |

26 records, no anomaly, every frame equal to its known frame, every pad all zero; one crc32 on
the board, on the card and on the host. This is the first row of the outcome table in section 9:
on these frames the device names the address after F without delivering F.

What it does not show is unchanged from section 8, item 2: all three addresses are in the middle
of one column, and what the register does at the end of a column has not been seen. `0xb9b` is a
value the register held, not a frame that was read.

S1b.1 can now be planned around the successor read. Its plan is the next document, for the
owner's review before anything is built.

## 12. S1b.1 — proposal for the walk of one column (2026-11-14; accepted by the owner the same day, all four points as proposed — built in section 13)

For the owner to accept, change or reject before any code is written. Envelope and aim are those
of section 3: the column of the known frames, `0x00000b80..0x00000bff`, starting at minor 0;
how many frames the column has, by the device's own account; every frame read more than once.

**The walk (a new stage of the same prober).** From `cur = 0x00000b80`:

1. *successor read:* the pad alone at `cur`, then the register → `next`;
2. *content read:* the pad and one frame at `cur` → the frame; then the register → kept as a
   cross-check (it should equal the successor of `next`, once that is known);
3. `cur = next`, and again.

The prober never computes an address: every address it reads at, after the first, is one the
device named. It ends the walk, and says which, when: `next` lies outside the envelope (the
expected end — the device has named something beyond the column; nothing is read there);
`next` is not above `cur` (the register is not advancing: stop); or a limit of 64 frames is
reached (the result area holds no more with the present records; a second run would continue
from the last address).

**Read more than once, by different paths.** The whole walk is made twice; the two must name the
same addresses and deliver the same frames. Then, along the list of addresses the walk found,
three frames are read in one read from every third address — the existing three-frame read, so
no larger buffer or record — and each must equal what the single reads delivered. The three
known frames must equal their known values; the reference frame is read first, last, after any
anomaly and every 16 operations.

**What is new, and so what could go wrong on the board.** Reads at addresses with no known
answer (minors 0..0x17 and from 0x1b on); the successor read and the content read at the last
frame of the column; and whatever the device names there. If the device names an address inside
the envelope that is not a frame, the walk will read at it: what a read at such an address
returns is not known. All of it is read-only, and the stop rules are those of the earlier
stages.

**What is claimed, and how it is graded.** As in section 3: which addresses the device named and
that reading them is repeatable and path-independent — not that the content of frames without
a known answer is right. After the result is saved and judged, and only then, a separate script
compares the list of addresses with prjxray-db's frame list for this part (the count for this
column, and whether the address named at the end is the next column's first). The prober and the
judge never see that database.

**Open points for the owner.**

1. The starting address `0x00000b80` is not named by the device: it is "minor 0 of the column
   of `0xb98`", taken from the layout of the address word in UG470. Accept that one computed
   address, or start at `0xb98` and learn only the upper part of the column?
2. The limit of 64 frames per run, and the envelope `0xb80..0xbff`.
3. Three-frame reads along the walked list as the path-independence check, instead of one long
   read of the whole column (which would need a new record layout and a larger buffer).
4. Grading against prjxray-db by a separate script after the fact.

## 13. S1b.1 as built (host side; nothing on a board yet — as first submitted; section 14 changes six things in it)

The owner accepted section 12 as proposed: the computed starting address `0x00000b80`, the limit
of 64 frames, three-frame reads as the second path, grading afterwards by a separate program.

**What there is to review:** this section; stage 4 in `prober/sm_core.c` (`run_s4`, `walk_op`,
`first_of`, `nth_content`, `health4`); `host/s1b1_judge.py`; `host/s1a_run.py --stage s1b1`;
`host/grade_s1b1.py`; the tests `tests/test_prober_s1b1.py`, `tests/test_s1b1_host.py`,
`tests/test_grade_s1b1.py`; the mutants marked stage 4 and judge4 in `tests/mutants.py`.

**The run.** Stage 4 in the parameter block: envelope `0x00000b80..0x00000bff`, reference
`0x00000b99`, start `0x00000b80`, two passes, at most 64 frames a pass, the reference frame
re-read after every 16 frames. Records have the layout of stages 2 and 3.

1. the baseline: the reference frame;
2. pass 0 and pass 1, each from the start: at `cur`, the pad alone and the register (the device
   names `next`), then the pad and the frame at `cur` and the register; then `cur = next`;
3. along the addresses of pass 0, three frames in one read from every third address;
4. the reference frame once more.

How many records that makes is what the run is to find out, so — unlike the earlier stages — no
record count, result size or console line is fixed beforehand; the judge derives all three from
the result itself.

**How a pass ends.** The device names an address outside the envelope: the pass ends, the address
is recorded and not read. The limit of frames is reached: the pass ends, a later run would go on
from the last address named. The device names an address that is not above the one it was asked
about: the whole run stops (status `0x800`) — following it could not end.

**Anomalies.** In the earlier stages a data anomaly was recorded and the run went on to the next
operation. A walk has no next operation that does not depend on this one, so here any anomaly —
a pad that is not zero, a short read, a register read that delivers nothing, a later pass that is
told another address or delivers another frame, a three-frame read that differs from the single
reads — is followed by one read of the reference frame and ends the run (status `0x700` + the
record's code; `0x300` if the reference frame has changed as well). An interface failure stops at
that command, as before.

**What the prober compares on its own, and what the judge re-derives.** The prober compares each
record of pass 1 with pass 0 at the same address (address named, and frame), and each frame of a
three-frame read with the single read of that frame. The judge takes none of that on trust: it
re-derives every record's code from its raw words, then follows the records the way the prober
must have — the next address being the one in the record before — and requires the header's
account of each pass (frames, how it ended, the last address named) to be what the records show.
On top of that, required for PASS: the passes name the same addresses and end alike; the
register after the read of a frame is the address the device names after the next frame, wherever
both were measured (70 such checks on a column of 36); the known frames equal their known values,
and a walk that leaves the envelope has passed them.

**What a PASS claims.** Which addresses the device named from `0x00000b80` on, how the walk
ended, and that reading those frames is repeatable and independent of the path. Not that the
content of a frame without a known answer is right — 33 of 36 would have none, on a column of
that length. A walk that stops at the limit is a sound measurement too and is reported as such.

**The twin does not know the answer.** The model is told by each test which address follows
which; the prober is not. The tests run columns of 1, 2, 3, 4, 17, 36 and 48 frames, a column
that does not end inside the limit, an end that names an address further on inside the envelope
(which is then followed, and read), an address that names itself, a step backwards, and the two
register rules under which the pad alone does not move the register (the walk stops at its first
frame). The judge has no frame count of its own: the same tests hold it to whatever the model did.

**Grading afterwards.** `host/grade_s1b1.py <verdict.json>` compares the addresses in a verdict
with prjxray-db's `part.json`: that they are minors 0.. of one column, the frame count of that
column, and whether the address named at the end is minor 0 of the next column. It is the only
file under `host/` or `prober/` that names the database (a test holds that), it reads nothing of
the judge's but the verdict file, and it is run only after a result is saved and judged. A
disagreement is a finding to look into, not a failed walk.

One thing to say plainly: the program was written before the board run, and writing it meant
looking at how the database is laid out — its author has therefore seen the number the database
gives for this column. Neither the prober nor the judge takes any number from it, the twin's
tests run seven column lengths, and the comparison is mechanical. The closed-book rule binds the
instrument, which it does here; it cannot make the author forget.

**New compared with S1b.0b, and so what could go wrong on the board.** Reads at addresses with no
known answer; the successor read and the content read at the last frame of the column, and
whatever the device names there; if that is an address inside the envelope that is not a frame,
a read at it; many more commands in one run than the 124 of S1b.0b, and a larger result (on a
column of 36 frames: about 800 commands and 78,000 words, some two minutes to pull over the
console; at the limit of 64 frames, 1,425 and 137,000). None writes configuration memory.

**The image** changed with stage 4: 10,186 bytes, sha256
`be437ea4e0fd838921f9e56475ffec8426fa2dee74577401993f1524bda83480`, crc32 `00404121`
(`build/prober/expected_s1b1.json`). Stages 1 to 3 run from the same image; their twin tests are
unchanged and pass, and the three stored board results still pass their judges.

**Host checks.** 201 tests. 169 deliberate defects (45 of them new, for stage 4, its judge and the
run script), all failed by the suite with all 201 tests run
(`evidence/host_checks/mutants_2026-11-14_s1b1.txt`). The first run of the new ones had one
survivor, "a PASS with anomalies" in the stage-4 judge: there the check cannot be reached on its
own — any anomaly ends the run, so the status check fails first, and a forged header is failed by
the count re-derived from the records. It was dropped, with a note in `tests/mutants.py`; the
check stays. The runner now works on eight scratch copies in parallel.

**Before the board:** the owner's review; then `host/s1a_run.py --stage s1b1 --dry-run` and, on
the owner's word only, `--go`; and only after the result is saved and judged,
`host/grade_s1b1.py`.

## 14. Changes after the first review of S1b.1 (2026-11-14)

Six findings, each reproduced on the submitted code before it was changed. The first would have
let a wrong reference frame pass.

| # | finding | fix | held by |
|---|---|---|---|
| 1 | The judge compared only the frames of the walk with the known frames. The reference frame — baseline, every reading during the run, the final one — was compared only with itself: the same wrong bit in all of them passed, on the prober and on the host | every frame a clean record delivered is compared with the known frame at its address, where there is one: in the walk, in a read of several frames, and in every reading of the reference frame | `test_the_reference_frame_is_held_to_its_known_value_in_every_reading`, `test_a_known_frame_delivered_in_a_read_of_several_is_compared_too` |
| 2 | "The reference every 16 frames" was counted from the start of each pass and not at all among the reads of several frames: on a walk of 64 frames, 79 frames were delivered between two readings of the reference | one count over the whole run: before any read that delivers n frames, the reference is read first if with these more than the interval would have been delivered since its last reading. The interval must be at least 3 (one read of three frames). The judge follows the same rule and reports the longest stretch | `test_never_more_frames_than_asked_between_two_readings_of_the_reference`, `test_the_reference_interval_is_followed_and_reported` |
| 3 | Only whole groups of three were read a second way: a walk of 35 frames left its last two, and a walk stopped at 64 its last, with a single path — and passed | where one or two frames are left over, the last three are read again (overlapping the group before); a walk of two frames gets one read of both. A walk of one frame has no second path: the judge lists such frames (`frames_without_a_second_path`), also for a run that stopped early | `SecondPath` (four tests), `test_frames_without_a_second_path_are_listed` |
| 4 | "Outside the envelope" was looked at before "not above the address asked about": a device naming `0x0` after the last frame ended both passes as if it had named the next column, and passed | not-above is looked at first, in the prober and in the judge: any address not above the one asked about stops the run (`0x800`), wherever it lies. Only an address above the envelope ends a pass | `test_an_address_below_the_envelope_is_not_a_normal_end`, and two shapes in the judge's fault table |
| 5 | A content record relabelled as reading no frame was followed by the judge, whose comparison with the frame it did not have raised an exception instead of giving a verdict | a record that is not the one the schedule has at that place ends the following of the schedule there (reported; nothing is compared with it). 800 randomly damaged buffers and 8 truncated ones must all get a verdict | `test_no_record_however_malformed_makes_the_judge_fall_over` |
| 6 | The grading program took a walk stopped after six frames for the column ("6 frames, the database says 36") and held the address it had last been told against the start of the next column | only a pass the device itself ended is compared for length and for what follows; a walk at its limit or stopped is compared as a beginning of the column (its addresses; not more frames than the database has), and the output carries the judge's verdict | `test_a_walk_that_did_not_finish_is_not_taken_for_the_column` |

Found while fixing, by the judge's own tests: with a reference read now possible between the two
records of a frame, the prober reported the stop record of a walk that does not advance by
counting back from the end, and so could name the reference read instead of the record in which
the device named the address. It now keeps that record's number.

Added with finding 1 in mind: the register after a read of several frames is now held to the
address the device names after the frame that follows them (81 register checks on a column of 36,
instead of 70).

A clean walk of a 36-frame column is now 164 records (it was 162): the reference readings fall at
other places. The claim of a PASS in section 13 is narrowed accordingly: path independence is
claimed for the frames that are in a read of several frames — all of them, unless the walk found
one frame only.

**The image** changed again: 10,510 bytes, sha256
`e26e653514d27bf9c7784caec64f395f705eba4a1450e061a2fa94c86a3bb959`, crc32 `1eb080e9`
(`build/prober/expected_s1b1.json`).

**Host checks after this review:** 212 tests; 191 deliberate defects, all failed by the suite with
all 212 tests run (`evidence/host_checks/mutants_2026-11-14_s1b1.txt`, a complete run).

## 15. S1b.1 on the board (2026-11-14): stopped twice by a receive-FIFO overflow — no answer yet

Released by the owner after the review of section 14. Two runs on `17A6`; record in
`evidence/s1b1_17A6_2026-11-14/RESULT.md`.

- Run 1 stopped at the 27th frame of the first pass, run 2 (the same again after a `reset`, on
  the owner's word) at the 8th: each time the prober's own stop on an interface failure, status
  `0x221`, in the 202-word read of a frame — `INT_STS` `50070004` (`RX_FIFO_OV`), 10 of the 202
  words not delivered. Different addresses, different places in the run, the same signature.
- The judge's verdict on each verified result: FAIL, for "did not complete" and "1 anomalous
  read" and nothing else.
- What was read before the stops is sound as far as it goes: at each of `0xb80..0xb99` the
  device named the next number; the frames common to both runs are identical; the known frames
  and the reference frame equal their known values.
- A `reset` from U-Boot brings the interface back.
- Separately, the pull of the result over the console lost data in three of five attempts that
  evening; the card copy, verified against the board's crc32 before any pull, was fetched
  read-only instead.

UG585 describes exactly this hazard (no flow control on the PL side of the PCAP; a 31-word
FIFO; an overflow loses data and may leave the DMA unrecoverable); zynq-psmap carried it as a
stop condition and never met it. Of the reads of 202 words or more this project has made on
this board, 30 before this walk were clean and 2 of the 38 in these two runs overflowed. A walk
of one column needs about a hundred such reads, so as designed — an interface failure ends the
run — it will not get through.

**Open, for the owner — nothing below is decided or built:**

1. *How often, and on what does it depend.* The existing image can measure this on the known
   frames with no new code: stage 2 with many operations and repeats makes up to 128 frame
   reads in a run and stops at the first overflow; a handful of runs (a `reset` between them)
   gives a rate, and the same with three-frame reads says whether the hazard grows with the
   length of a read.
2. *Whether a session can be recovered without a reset.* After an overflow: clear the status,
   send the cleanup, read the reference frame; if it equals the baseline, read the failed frame
   again, a bounded number of times, every attempt recorded. UG585 warns that the DMA may not
   recover; only the board can say. This is new prober code and a new stage of its own, to be
   tried on the known frames before any walk relies on it.
3. *Whether it can be avoided.* Candidates, none tested: fewer accesses to DDR by the processor
   while a read is in flight (the data cache is off, so every stack access of the polling loop
   goes to DDR alongside the DMA's writes); a different placement of the destination buffer.
4. *The host's pull.* A bounded number of retries of the `md.l`, each recorded, the board's
   crc32 deciding — or the card file as the primary copy. A change to the run script.

## 16. Counting the overflows (2026-11-14): it is the walk, not the reads

On the owner's word, points 1 and 4 of section 15. Record:
`evidence/fifo_rate_17A6_2026-11-14/RESULT.md`.

- Point 4, the host's pull: the run script now pulls the result at most three times, records
  every attempt, keeps every damaged copy, and judges only a copy with the board's crc32
  (commit `1bdae54`; 196 mutants killed with the 215 tests of that commit). In use the same
  evening it was needed in 5 runs and was not enough in 2, whose results were fetched from the
  card in pieces. A pull in pieces, each checked against the board's crc32 of that piece, is the
  better design and is not yet in the run script.
- Point 1, the count: through stages 2 and 3, 16 runs and 624 frame reads on the same image with
  no overflow — reads of one frame, of three, the walk's own pair of reads, at the known frames
  and at the walk's first eight addresses, repeated and for the first time after a load. Through
  stage 4, the walk, 5 runs of 5 overflowed, after 8 to 28 frame reads.

So the hazard is not a rate per read that a longer run simply meets more often, as section 15
supposed. It belongs to something the walk's path does around a read, and nothing in the records
shows what: the routine that makes a read is the same machine code for every stage, the polls
have the same distribution, the addresses and the pairs of reads were reproduced without it.

**Open, for the owner — nothing below is decided or built:**

1. *Find what in the walk's path does it*, by changing one thing at a time in a diagnostic image
   and counting again: the walk's schedule driven from the stage-3 loop; the walk with the
   stage-3 loop's work between reads added; the reads made at another stack depth. Each is a new
   image, to be reviewed, and reads only addresses already read.
2. *Or go round it*: let the prober recover from an overflow and read the frame again (section
   15, point 2) — which leaves the cause unknown and the hazard in every later stage.
3. *The pull in pieces* in the run script, and the status of a reference read that fails on the
   interface (`0x300` today, where the record says `0x21`).

## 17. Finding what in the walk overflows: the diagnostic image and the pull in pieces (2026-11-14; host side, nothing on a board yet)

The owner chose points 1 and 3 of section 16. For review before any board run.

### What is known, and the two readings of it

The routine that makes a read (`read_op`, with `dma` beneath it) is one piece of machine code
for every stage. Through stages 2 and 3 it made 624 frame reads without an overflow; through
the walk it overflowed in 5 runs of 5, at the 9th to the 29th frame read. Two differences
between those sets of runs survive everything section 16 ruled out:

- **Where the read is made from.** The walk calls it one function deeper (`walk_op`, 72 bytes of
  stack; its reference reads come through `health4`, 40 bytes), stages 2 and 3 straight from the
  stage loop. Nothing else differs while a transfer is in flight: the polling loop is the same
  instructions, and on every poll it stores two words — the status it read and the count — into
  two neighbouring words of `read_op`'s frame. With the data cache off those stores go to DDR,
  where the DMA is writing the frame. In the walk they go to an address 72 (or 40) bytes lower.
  Why that should matter is not known; that it is the only thing that differs during a transfer
  is read off the disassembly.
- **What is read.** Every clean run revisited at most nine addresses; no run of stages 2 and 3
  ever read more than nine *different* frames after a load. The walks had read 8, 11, 17, 19 and
  27 different frames when they overflowed. `ratef`'s ten clean runs stop exactly where the
  earliest walk failed, so they do not separate "the walk's path" from "many different frames".

The first reading says the cause is in the prober's use of memory; the second, in the device or
in the sequence. They call for different remedies, so they are told apart first.

### The diagnostic image

One image, the earlier stages unchanged in behaviour; what is new is selected by parameters:

- **Stage 5** is stage 3 with a generated sequence: at each of N addresses from a first one, the
  pad alone and then the frame — the reads of the walk's first pass, made by the stage-3 loop.
  (The addresses are computed, which the walk never does; this is a diagnostic on addresses the
  walk has already read, `0xb80..0xb99`, not a walk.)
- **Extra stack**, in stages 4 and 5: a number of words (at most 64) placed beneath each target
  read and beneath nothing else. In the built image this is `sub sp` by the words rounded up to
  8 bytes, and then the same `read_op`.
- **Every record now carries the address of the polling loop's status word** (the first of the
  two words stored on every poll; one word of the FAR block that was reserved). It is reported
  by the judges and judged by none: it is what the series is about.

### The series (each set: a `reset`, a fresh load, one run; several runs of each)

| set | what | the read lies | asks |
|---|---|---|---|
| `dxw0` | the walk, envelope `0xb80..0xb99` (26 frames, twice, and the reads of several frames) | 72 bytes down, as in S1b.1 | the control: does the new image still overflow in the walk |
| `dxs0` | stage 5, the 26 addresses once | at stage 3's depth | **many different frames, by the path that never overflowed: if this overflows, it is the sequence, not the path** |
| `dxs18` | the same, 18 words beneath | 72 bytes down | the path's depth without the path: if `dxs0` is clean and this overflows, it is the depth |
| `dxs10` | the same, 10 words | 40 bytes down | the depth of the walk's reference reads |
| `dxw6` | the walk, 6 words | 96 bytes down | the walk moved off its depth: if this is clean where `dxw0` is not, the depth again, from the other side |
| `dxw8` | the walk, 8 words | 104 bytes down | another depth, to see whether it is one depth or many |

The actual addresses are read from the records, not taken from this table. What each outcome
would mean is as the last column says; if neither depth nor sequence separates the runs, the
records will at least show at which addresses reads failed and at which they did not, and the
next image is designed from that.

The judge will fail `dxs*` for one reason — frames `0xb80..0xb97` have no known answer — as it
did `ratew`; `dxw*` it can pass (the walk's second pass and its reads of several frames check
each frame against itself, and `0xb98`, `0xb99` against their known values). Either way what is
counted is how far the prober got.

### Also changed, from point 3

- **The pull is made in pieces.** For each 2048 words the board is asked for its own crc32 of
  that piece, and the piece is pulled until the host's copy has it, at most five times, every
  repeat recorded. The whole must then have the crc32 the board gave for the result before the
  card write; pieces that each match do not make the whole the board's (a test holds that with a
  result that changes in between). This replaces the three whole-result attempts of `1bdae54`.
- **A reference read that fails on the interface stops the run with the interface's status**
  (`0x200` + the record's code), in stages 2 to 5 and in their judges; only a reference frame
  that reads cleanly and differs is `0x300`. One stored result, the third walk of the counting
  series, carries the old `0x300`; the judge now says so of it ("the header's status is 0x300;
  the records imply 0x221").

### State

- Image: 11,234 bytes, sha256 `d5154bb80f244eb224f42cae6c0fd6cde3c93a9b7d2e64880b51965e94371877`,
  crc32 `94bd3065`. The stack frames of `read_op`, `walk_op`, `health4` and the stage loop are
  the sizes they were in the image that overflowed (240+32, 40+32, 28+12, 120+32 bytes), so the
  depths above are the old ones; `dxw0` is there to confirm it on the board.
- Host checks: 232 tests. 220 deliberate defects; a complete run failed 219 of them with all 232
  tests run, and its one survivor (the stage-5 judge accepting a sequence longer than the prober
  takes — the test had offered one only in an envelope too small to hold it) is failed by the
  test as corrected; that single re-run is appended to the record
  (`evidence/host_checks/mutants_2026-11-14_diag.txt`). Earlier in the same work the set showed
  three more gaps, each closed by a test (a stage-4 result with more extra stack than the prober
  takes; stage-3 and stage-5 results taken for each other; the same for the sequence length), two
  defects that did not build and were rewritten, and one check in the prober that no test could
  reach because the check after it covers the same case — removed.
- Nothing here recovers from an overflow, and nothing reads an address the walk has not read.

**Before the board:** the owner's review. Then, with nothing else running on the host, the
series above; stop and report after it. *(The image named here is not the one to load: the
review changed it — section 18.)*

## 18. Changes after the review of the diagnostics (2026-11-15; host side, nothing on a board yet)

The review of `e1391ec` found two things. Both were reproduced on the twin as reported, both are
changed. Neither is reached by the six parameter sets of section 17.

1. **A generated sequence could wrap past the top of the address space** (prober). Stage 5
   formed the j-th address as a 32-bit sum and checked each one against the envelope. With the
   envelope open to `0xffffffff`, three addresses from `0xfffffffe` came out as `0xfffffffe`,
   `0xffffffff`, `0x0` — each inside — and the run completed; the judge, which counts in whole
   numbers, called the same parameters invalid. The prober now settles the end of the sequence
   by subtraction (`seq - 1 > hi - first` is refused) before anything is read or written; a first
   address above the top, for which that difference means nothing, is refused by the check that
   was already there. A sequence ending exactly at `0xffffffff` is accepted. The judge needed no
   change.
2. **An operation without a read was counted as a read of the pad alone** (stage 2/3/5 judge,
   the summary by polling variable only — no verdict depended on it). The summary sorted by
   whether a frame had been delivered; "no read" (count 15) delivers none and fell in with the
   pad alone (count 0). It is now sorted by the count the record carries, into a third number,
   `operations_without_a_read`. The walk's judge has the same summary and is left as it is: the
   walk has no such operation, and a record that claims one is already a problem there.

### The image changed, and what was checked about that

The first change is in the prober, so there is a new image: **11,262 bytes, sha256
`17ad8b14b4229f4fd57fa1b94fdd6dd99c851311ebc10fe7605e9f0f3eed5682`, crc32 `f0912724`** — 28 bytes
(seven instructions) more than `d5154bb8…`. Because the series of section 17 rests on where the
reads lie on the stack, the two images were compared (the reviewed one rebuilt from `e1391ec`
in a scratch copy, hash as recorded):

- every function starts at the address it had — the new instructions are in the stage loop,
  the last function of the image, before any register is touched;
- every `push` and every adjustment of the stack pointer, in every function, is the same (34
  lines of the disassembly, compared as text): `read_op`, `walk_op`, `health4` and the stage
  loop have the frames listed in section 17;
- the rest of the difference is that code after the new instructions, and the strings after
  the code, lie 28 bytes further on.

So the depths in section 17's table still hold; the records' own polling-variable word remains
what is read, and `dxw0` remains the control.

### State

- Image: as above. The six parameter sets are unchanged.
- Host checks: 233 tests (one added: the sequence at the top of the address space, refused when
  it would pass the top, accepted when it ends there; the summary's third number is added to
  the existing test of the summary). 225 deliberate defects, five of them new (the new check
  removed; off by one address in either direction; "no read" counted with the pad alone; the
  pad alone counted with "no read"). A complete run after the change
  failed all 225, each with all 233 tests run and none failing to build
  (`evidence/host_checks/mutants_2026-11-15_review.txt`).
- Nothing here recovers from an overflow, and nothing reads an address the walk has not read.

**Before the board:** the owner's review of this section. Then, with nothing else running on the
host, the series of section 17 with the image of this section; stop and report after it.

## 19. The diagnostic series on the board (2026-11-15): it is the stack position, not the sequence

Released by the owner after the review of section 18. Image `17ad8b14…`, three rounds of the six
sets, a `reset` before every run, nothing else running on the host. 18 runs, none stopped by the
run script, every result the board's. The full account is
`evidence/dx_17A6_2026-11-15/RESULT.md`; `summary.json` there is made from the stored results,
and `tests/test_board_evidence.py` makes it again.

| set | polling variable at | run 1 | run 2 | run 3 |
|---|---|---|---|---|
| `dxw0` (walk, as it was) | `0x1eaca9d8` | overflow | overflow | complete, PASS |
| `dxs0` (stage 5) | `0x1eacaa20` | complete | complete | complete |
| `dxs18` | `0x1eaca9d8` | overflow | overflow | complete |
| `dxs10` | `0x1eaca9f8` | overflow | overflow | overflow |
| `dxw6` (walk, 24 bytes lower) | `0x1eaca9c0` | complete, PASS | complete, PASS | complete, PASS |
| `dxw8` (walk, 32 bytes lower) | `0x1eaca9b8` | complete, PASS | overflow | overflow |

Read against the table of section 17:

- `dxs0` clean three times: **not the sequence** — 26 different frames by the path that never
  overflowed still do not overflow.
- `dxs18` and `dxs10` overflow (five runs of six) with nothing changed but the depth: **the
  stack position**.
- `dxw6` clean and `dxw8` not: it is not one bad depth with clean ones on both sides. All 9
  overflows lie at addresses that are 24 modulo 32 (three addresses, 728 reads); the two
  addresses at 0 modulo 32 had none in 504 reads. Only these two residues were tried, and the
  mechanism is not known — the result note says what is and is not established.
- The addresses are the ones section 17 worked out from the frames (72 and 40 bytes below
  stage 3's), now read from the records.

The pull in pieces did its work: 4 pieces of 299 came back damaged and were pulled again; no run
was lost to the console.

**Stopped here, as agreed.** Open, for the owner: whether to understand the position first (the
other residues; the polling loop without its two stores) or to go on with the walk at a position
that did not overflow, which needs a parameter and no new image — in either case an overflow
stops a run and is seen by the judge; it has not produced a wrong frame. The column's end has
not been looked for; `host/grade_s1b1.py` has not been run.

## 20. A wait that stores nothing while a transfer runs (2026-11-15; host side, nothing on a board yet)

The owner's choice after section 19: build the image whose polling loop does not write the stack.

### What the prober does on the stack while a transfer runs

Only the loop that waits for it. Read from the machine code of the image that overflowed, per
poll: one store of the status and one of the count, through pointers into the frame of the
reading routine (`sp+24`, `sp+28` there — the address the records carry, and its neighbour), and
one load of the poll limit from the same frame (`sp+0`: the first argument passed on the stack).
Nothing else: the register read is a leaf call with no frame; the address of the status register
is loaded from the code. The data cache is off, so each of these is an access to DDR, where the
transfer is writing at the same time. A read is polled only two to six times, so these are few
accesses — and still the overflows follow where that frame lies (section 19).

### The image: three waits, chosen by a parameter

Parameter word 15 now holds two things: its low byte is the extra stack of section 17, its bits
8 and up choose the wait, in stages 4 and 5 only (every other stage waits as it always did):

| value | name | on every poll, on the stack |
|---|---|---|
| 0 | as before | two stores, one load |
| 1 | no stores | one load (the limit, from the same slot) |
| 2 | no stack | nothing |

Values 1 and 2 are one routine, `queue_and_wait_quiet`: it writes the register that queues the
command itself, after it has saved its own registers, then polls with the status and the count
in registers, and stores the count once on the way out; the status is stored by its caller
after that. With value 1 it is handed the address of the stack slot the original loop loads the
limit from and reads it there on every poll; with value 2 it is handed none. The four ways out
(an error bit, PCFG_DONE gone, D_P_DONE, the limit) and the checks before the command are the
same as before, and so is every register access, in order. A value above 2 is refused as a bad
parameter block before anything is touched.

Value 0 runs the original loop, in the original function. Its machine code was read again in
this image: per poll the same two stores through registers and the same one load from the
caller's first stack argument. What differs around it: the function now reads the choice (two
words of the parameter block) before it sends anything, and saves two more registers on entry.

Unchanged against `17ad8b14…`, compared in the disassembly: the frames of `read_op` (240 bytes,
status at `sp+24`, count at `sp+28`), `walk_op`, `health4` and the stage loop. So the reads lie
where they lay, and the sets of section 17 keep their depths. The functions do start at other
addresses than before (three small ones were added in front of them); the controls below are
run in this image for that reason.

No result can tell the waits apart — that is the point of them. So they are held two other ways:

- **On the twin**, which is shown where the prober keeps its count of polls
  (`hal_watch`, a do-nothing on the board) and looks at it each time a queued transfer is
  polled: as before, it finds 0, 1, 2, … ; with the quiet waits, 0 throughout, and the count
  only once the wait is over. And for ten injected faults in both stages the three waits bring
  back the same result word for word and make the same register accesses in the same order.
- **In the machine code** (`tests/test_prober_image.py`): between the write that queues the
  command and the way out of the quiet loop there is no store and nothing addressed through the
  stack pointer; its one load through a register is conditional on a place having been passed;
  the caller passes the slot its own loop reads, and only for value 1.

### The series proposed (each set: a `reset`, a fresh load, one run; three rounds)

Two of section 19's sets, each with the three waits; within a triple one parameter word differs,
in one bit field.

| set | what | wait | section 19, same position |
|---|---|---|---|
| `dxs10` | stage 5, reads at `0x1eaca9f8` | as before — control | overflow 3 of 3, within 13 records |
| `dxs10n` | the same | no stores | |
| `dxs10r` | the same | no stack | |
| `dxw0` | the walk as it was, reads at `0x1eaca9d8` | as before — control | overflow 2 of 3 |
| `dxw0n` | the same | no stores | |
| `dxw0r` | the same | no stack | |

| outcome | reading |
|---|---|
| controls overflow, `n` and `r` do not | the stores are what matters; the quiet wait is the remedy |
| controls and `n` overflow, `r` does not | the load matters as well (or instead): any access to that frame during a transfer |
| all three overflow | not the loop's use of the stack; something else that moves with the frame — a new question |
| the controls do not overflow | this image moved something else; nothing can be read from the rest until that is understood |

How much three rounds can show: `dxs10` overflowed after 8 to 12 reads each time, so three
complete runs of 52 reads at that position would be strong; the walk overflows at about one
read in a hundred, so three complete walks (339 reads) would be suggestive only — more rounds of
the walk sets if it comes to that.

### State

- Image: 11,630 bytes, sha256 `2c566b1ed6b65555cfdddcdcb513ca2578360d0c4b6827ae676b9e857153b296`,
  crc32 `b0d75377`.
- Host checks: 241 tests. 252 deliberate defects, 27 of them new (in the quiet wait: each way
  out, each check before the command, the order of the register writes, a store put back into
  the loop, the limit handed to the wrong variant; the choice taken by the wrong stages, mixed
  up with the extra stack, or not refused when it names no wait; the same in both judges). A
  complete run failed all 252, each with all 241 tests run
  (`evidence/host_checks/mutants_2026-11-15_quiet_wait.txt`). A first complete run had failed
  240 of 249 and could not apply the other nine: the change had altered or duplicated the lines
  they are anchored to. Their anchors were corrected (the quiet wait's checks before the command
  use another variable name so that each line of the two can be named), and three defects were
  added for the quiet side.
- Found while doing it: the tests of the run script's parameter sets read a set before anything
  had written it and passed only because another test ran first; they now have the sets written
  themselves.
- Nothing here recovers from an overflow, and nothing reads an address the walk has not read.

**Before the board:** the owner's review. Then, with nothing else running on the host, the
series above; stop and report after it. *(Section 21 changes the twin and the tests after that
review; the image is the one named here.)*

## 21. Changes after the review of the quiet wait (2026-11-15; the twin and the tests only — the image is unchanged)

The review of `40f9437` found one thing, in the host model, and it was reproduced as reported.

**The twin looked at the prober's count of polls after the variable was gone.** The count is a
local variable of the routine that makes a read; the twin was told where it is and looked at it
on every status read while a transfer was being waited for, until a status read showed the
transfer done. A wait that gives up at the limit never shows that: the routine returned, and the
next status read — made at the end of the run — still looked. Built with the address sanitizer,
the twin stopped there with a stack-use-after-return, in both stages and with all three waits.
And the test of section 20 had relied on that last look to see the final count.

Changed, in `prober/twin_hal.c`: a wait begins with the write that queues a command and consists
of status reads and nothing else, so the first call through any other door ends it, whichever
way it went. That call is the reading routine's own — it records the status and the count as
soon as the transfer function returns — so the variable is still there: the twin looks one last
time (reported on a line of its own, `WATCHED`) and then leaves it alone until the next command
is queued.

Tests: the count once each wait is over is now taken from that line — it is the number of polls
made, the same for the three waits — and after the wait that gave up there is no further look.
A new test builds the twin with the address and undefined-behaviour sanitizers (`make
twin_asan`) and runs it through ten faults, three waits and both stages, 60 runs, requiring a
clean exit and the same result as the ordinary twin; run against the twin as it was, it fails
in the twelve runs with a wait that gives up.

The board is not concerned: `hal_watch` does nothing there, and neither `sm_core.c` nor
`sm_board.c` was touched. **The image is the one of section 20**: 11,630 bytes, sha256
`2c566b1e…b296`, crc32 `b0d75377`, rebuilt and compared.

Host checks: 242 tests. The 28 deliberate defects that concern the wait and the watch were run
again and all failed (`evidence/host_checks/mutants_2026-11-15_quiet_wait_review.txt`); the
complete set of 252 was not run again, the prober being unchanged.

**Before the board:** the owner's review of this section. Then the series of section 20.

## 22. The three waits on the board (2026-11-15): it is the stores

Released by the owner after the review of section 21 (three rounds). Image `2c566b1e…`, a
`reset` before every run, nothing else running on the host. 18 runs, none stopped by the run
script, every result the board's. The full account is
`evidence/quiet_17A6_2026-11-15/RESULT.md`; `summary.json` there is made from the stored
results, and `tests/test_board_evidence.py` makes it again.

| set | wait | run 1 | run 2 | run 3 |
|---|---|---|---|---|
| `dxs10` | as before | overflow | complete | complete |
| `dxs10n` | no stores | complete | complete | complete |
| `dxs10r` | no stack | complete | complete | complete |
| `dxw0` | as before | overflow | overflow | overflow |
| `dxw0n` | no stores | complete, PASS | complete, PASS | complete, PASS |
| `dxw0r` | no stack | complete, PASS | complete, PASS | complete, PASS |

At the positions that had overflowed: the original wait, 4 overflows in 297 reads; no stores, 0
in 510; no stack, 0 in 510. Read against the table of section 20, it is the first row: **the
controls overflow, `n` and `r` do not — the stores are what matters, and the quiet wait is the
remedy.** The load alone was not seen to matter. Why two single-word stores to DDR at those
addresses during a transfer make the receive FIFO overflow is not known, and nothing here needs
it: it is recorded as observed.

What this changes for the walk: with the quiet wait the walk of the 26 addresses ran to its end
six times of six, PASS. The walk of the column itself (S1b.1, section 12) has still not been
run to its end, and `host/grade_s1b1.py` has not been run. The image already holds what that
walk needs — its parameter block with the wait chosen in word 15 — so no new image is required
for it; a parameter set for it does not exist yet.

**Stopped here, as agreed.** Open, for the owner: S1b.1 with the quiet wait (a parameter set in
the run script, for review, then the board); whether the original wait is to be kept in the
image at all once that has run.

## 23. S1b.1 with the quiet wait: the parameter set, and what is proposed for the board (2026-11-15; host side, nothing on a board yet)

The owner's choice after section 22: a parameter set for S1b.1 with the quiet wait, for review,
then the board.

### What was added — host side only

- **A parameter set, `s1b1r`**: the parameter block of `s1b1` (section 13: from `0xb80`, envelope
  `0xb80..0xbff`, two passes, at most 64 frames a pass, the reference frame every 16) with one
  word changed — word 15 = `0x200`, the wait that touches no memory while a transfer runs
  (`POLL_NO_STACK`, the `r` of section 22). It is written where the other sets are
  (`tests/test_prober_image.py`), entered in the run script, judged by the walk's judge. The set
  `s1b1` is left as it was: it is what overflowed on 2026-11-14.
- **Nothing in the prober, the judges or the grader.** The image is the one of sections 20 to
  22: 11,630 bytes, sha256 `2c566b1e…b296`, crc32 `b0d75377`, rebuilt and compared. The judge
  already takes the choice of the wait (section 20) and reports it in its verdict.
- Tests (245 in all, two new): the two blocks differ in word 15 and nowhere else; the plan the
  run script types differs from the walk's in one line, the write of that word; through the run
  script the twin walks the same column to the same end with the same frames, PASS, and sees
  nothing stored while a transfer is waited for (with `s1b1` it sees the count stored on every
  poll); stops are saved whole and fail as they do for `s1b1`; a board that was given the old
  block instead is not the run that was planned. For that the pretended board keeps what the
  twin printed. Two deliberate defects (the set judged by another judge; the set given the old
  block), both failed; the complete set was not run again — nothing it is aimed at changed.

### Proposed for the board

One run of `s1b1r` after a `reset` and a fresh load, as S1b.1 was designed (section 12): the
walk reads every frame by two paths and twice over, in the one run. Then:

1. The result is saved (card and host), judged, and **committed, whatever it says**.
2. Only if the run completed and the judge says PASS: `host/grade_s1b1.py` is run on that
   verdict against prjxray-db's `part.json` — after the commit, so that what the device said is
   fixed before the database is looked at. Its output is recorded beside the result. A
   difference is a finding to report, not something to repair.
3. If the run stops — an overflow, an anomaly, the register not advancing, a pulled copy that
   cannot be verified — it is saved, judged and committed as it is, the grader is not run, and
   the series ends there.
4. In every case: stop and report.

What a complete run can and cannot say is as in section 12. Two things from since then bear on
it: the wait is the one that did not overflow in 1,020 reads at the positions that had
(section 22), on 26 of this column's addresses — beyond `0xb99` nothing has been read; and one
pass can hold 64 frames, so a column longer than that ends a pass at the limit, which the judge
reports as such and the grader does not take for the column's end.

(Said before, and still so: while writing the grader I saw the database's number of frames for
this column. Neither the prober nor the judge holds it, and a test holds that they do not name
the database.)

**Before the board:** the owner's review. Then the run above.

## 24. S1b.1 on the board with the quiet wait (2026-11-15): PASS — 36 frames, then `0xc00`

Released by the owner after the review of section 23, and run in the order written there: one
run of `s1b1r` after a `reset`; the result saved, judged and committed (`b6cdd14`); then the
grader. The full account is `evidence/s1b1r_17A6_2026-11-15/RESULT.md`.

- The walk ran to its end: status 1, 164 records, no anomaly; the judge passes it.
- **Both passes: 36 frames, `0xb80..0xba3`, each naming the next number; after `0xba3` the
  device named `0xc00`**, which lies outside the envelope and ended the pass. Neither the
  envelope's top nor the limit of 64 frames was what ended it.
- Every frame was read by two paths and twice over, the same each time; the three known frames
  are as known; the first 26 frames are those of every earlier run.
- The grader, afterwards: the 36 addresses are minors 0..35 of one column (block type 0, top
  half, row 0, column 23); the database says 36 frames for it, and `0xc00` is minor 0 of the next
  column. Nothing differs.

S1b.1 is answered. The table of section 4 has S1b.2 next (the row of that column: the columns of
the row and their frame counts, and what the address does at the end of a row); it has not been
proposed in detail and nothing of it is built.

**Stopped here, as agreed.**

## 25. S1b.2 — proposal for the walk of the row (2026-11-15; a proposal, nothing built, nothing on a board)

The owner asked for a detailed proposal before anything is written. This is it.

### The question

Section 3: the row of the column S1b.1 walked — block type 0, top half, row 0. Which addresses
does the device name along it; into which columns do they fall and how many frames has each;
and what does the device name after the last frame of the row?

### The idea: the walk as it is, in a chain of runs

Nothing new in the prober. Stage 4 already walks from a given address by the addresses the
device names, reads every frame by two paths and twice over, and stops at 64 frames a pass
(`END_LIMIT`), recording the address named after the last one. A row is walked by running it
again and again, each run beginning where the one before ended.

- **The image is the one that passed S1b.1**: 11,630 bytes, sha256 `2c566b1e…b296`. No new
  image, no change to the judge of a run.
- **One parameter block, in which one word varies.** Envelope `0x00000000..0x0001ffff` — every
  address whose block type, half and row fields are zero, by the layout of the address word in
  UG470; reference frame `0xb99`; two passes; at most 64 frames a pass; the reference frame
  every 16; the wait that touches no memory (word 15 = `0x200`). Only the starting address
  (word 16) differs from run to run.
- **Why chunks of 64 frames and not one column a run**, as I had first sketched it to the owner:
  the prober requires the reference frame to lie inside the envelope, and the only frames with a
  known answer are `0xb98..0xb9a`. An envelope of one column would have no known frame in it
  anywhere but in column 23. With the row as the envelope the reference stays `0xb99` throughout,
  and a run ends at the limit rather than at a column's edge. The columns are then read off the
  list of addresses afterwards, on the host.
- **The envelope still fences every read.** The guard refuses any command that would read
  outside it, so no run of the chain can read the bottom half, another row, or block types 1 and
  2 — in particular no block-RAM content (section 3's last line stands).

### The chain

Run 0 starts at the first address of the row. Each later run starts **at the last frame the run
before walked** — one frame of overlap at every seam, so that each seam is checked across two
runs (a different load of the design, a different run of the prober): the frame must be the same
and the device must name the same address after it. A run thus adds 63 new frames.

Before every run a U-Boot `reset` and a fresh load of the PL design, as in every run so far.
After every run the result is pulled in checked pieces, verified against the card copy, and
judged by the walk's judge as it stands.

The chain goes on to the next run only if all of these hold:

1. the run script reports no stop, and the result is the board's;
2. the judge says PASS;
3. both passes ended at the limit and named the same address after the same last frame;
4. for every run but the first: its first frame is the last frame of the run before, with the
   same content, and the address named after it is the one named there.

The chain is **complete** when a run passes and both of its passes ended because the device
named an address outside the envelope: the row has been left, and that address is the answer to
the third question. It is not read.

The chain **halts** — the run saved and judged as it is, nothing retried, report — on anything
else: an anomaly; a stop of the prober (including "the address named is not above the current
one", status `0x800`); the two passes disagreeing; a seam that does not match; a result that
cannot be verified; and when a bound of 48 runs is reached (about 3,000 frames, about three and
a half hours of board time at the four minutes or so that a full run should take). The bound is
a limit on unattended board time, not a statement about the row; going past it is the owner's
decision.

A chain that was interrupted is taken up from its last complete run: the state is the stored
runs themselves, each judged again from its raw words before it is relied on.

### What the host derives afterwards, from the stored runs alone

A new program (the "row summary"; it knows the layout of the address word and nothing about the
part) judges every stored run again and puts the walked addresses in order:

- the list of addresses of the row as the device named them, with the hash of every frame;
- the seams, checked again;
- the addresses grouped by their column field: for each column, how many frames, whether their
  minors are 0, 1, 2, … without a gap, and whether the address named after its last frame is
  minor 0 of the column numbered one higher. Whatever does not have that shape is **listed as
  found**, not treated as an error: the prober follows what the device names, and the summary
  describes it;
- column 23 again: the same 36 addresses and the same 36 frames as in S1b.1;
- the three known frames, as known;
- what was named after the last frame of the row.

### Grading, afterwards

As for S1b.1 and in the same order: every run saved and judged, the row summary made, **all of it
committed**; only then a separate script compares the summary with prjxray-db's `part.json` —
the columns of this row and their frame counts, and what the database has after the row's last
frame. It is the only new file allowed to name the database (the test that holds this for
`grade_s1b1.py` is extended to it). A difference is a finding to report. If the chain halted
before the row was left, the grader compares only the columns that were walked whole and says
that the rest was not.

### What is new, and so what could go wrong on the board

- **Addresses never read before**, about sixty-three at a time, including the first address of
  the row, which no run has touched. If the device names an address inside the envelope that is
  not a frame, the walk reads at it; what such a read returns is not known. It is read-only, and
  the stop rules are the ones that have been used throughout.
- **Frames whose content is not constant.** Every frame is read four times in a run and again at
  each seam, and the same content is required each time. A frame that holds running state of the
  carrier design would differ between reads; that is an anomaly, the run stops, the chain halts.
  It would also be the first sight of such a frame — to be reported as that, not worked around
  here. Whether reading a frame disturbs the carrier's own state is not observed (it was not in
  S1a either); the prober does not depend on the carrier, and each run begins with a fresh load.
- **Reads of several frames across a column's edge.** In S1b.1 the three-frame reads stayed
  inside one column. Here they will cross from one column into the next. The judge requires the
  frames so delivered to be the ones the walk read one by one, in the walk's order; if the device
  delivers something else across an edge, the run fails there and the chain halts with a finding.
- **The end of the row.** What the device names there is the question; the three outcomes are
  all provided for: an address outside the envelope (complete), an address not above the current
  one (the prober stops; halt), an address inside the envelope (the walk follows it, and the
  summary shows it).
- **The wait.** The quiet wait did not overflow in 1,020 reads at the positions that had, and in
  S1b.1's 163. If an overflow appears anyway, the run stops, and the chain halts.
- **Board time and the console.** Tens of runs. Each is independent; a console that drops ends
  one run, not the chain's record.

### What would be built (after the owner's word; host side only)

1. The run script: the parameter set `s1b2` and a starting address given at run time, checked to
   lie in the envelope; the run record says where the address came from.
2. The chain driver: the rules above and nothing else.
3. The row summary.
4. `host/grade_s1b2.py`.
5. Tests on the twin for each — chains of several runs over model rows with columns of
   different lengths, rows that end in each of the three ways, a seam that does not match, a run
   that stops, a chain taken up again — and deliberate defects for each rule.

Then the owner's review, and only then the board.

### Open points for the owner

1. **Where to begin.** Section 3 said "where S1b.1 began" (`0xb80`). That leaves the part of the
   row below `0xb80` unwalked. Proposed instead: begin at `0x00000000`, the address with every
   field zero, and walk through to the end — column 23 is then walked again on the way, as a
   check against S1b.1. Like `0xb80` in S1b.1, `0x0` is a computed address, not one the device
   has named; that it is a frame is an expectation from the layout of the address word, to be
   confirmed in UG470 before anything is built, and in the end by the read itself. The
   alternative: begin at `0xb80` or `0xc00`, learn the upper part only, and decide about the lower
   part afterwards.
2. **The envelope of the whole row**, instead of the one-column envelope of S1b.1.
3. **One frame of overlap at each seam**; the bound of 48 runs.
4. **The shape of a column is described, not required**: the chain does not stop because a
   column's minors or the step to the next column look unexpected.
5. **The same order of grading**: commit first, then the database.
6. As before, and to be said each time: I have general knowledge of how rows of this family are
   laid out, and I saw one number of the database while writing the first grader. None of it
   goes into the prober, the judge, the chain's rules or the row summary; the tests that hold
   that are extended to the new files.

## 26. S1b.2 as built (2026-11-15; host side, nothing on a board yet)

The owner accepted section 25 with all six points as proposed. This is what was built. The
prober is untouched; the image is the one of S1b.1: 11,630 bytes, sha256 `2c566b1e…b296`,
crc32 `b0d75377`, rebuilt and compared.

### The first address

Point 1 said `0x0` would be confirmed in UG470 before anything was built. UG470 v1.17, "Frame
Address Register": *"The typical bitstream starts at address 0 and auto-increments to the final
count"*; and its readback command sequence sets the address to `00000000`. Address 0 is the
first frame by the document's account; the read itself is still what will show it.

### What there is

| file | what it does |
|---|---|
| `tests/test_prober_image.py` | writes the parameter set `s1b2`: `s1b1r`'s block with the envelope `0x00000000..0x0001ffff` and the start `0x0` |
| `host/s1a_run.py` | the set `s1b2`; `--start` (hex) replaces the one word of its block that may be given at run time, refused for any other set and for an address outside the set's envelope; `--start-from` is recorded with the run and sent nowhere |
| `host/s1b2_judge.py` | the judge of one run of the chain: the walk's judge with one rule changed (below) |
| `host/s1b2_chain.py` | the chain: `--dir DIR` says where the chain stored there stands (reads only); `--go` goes on with it on the board |
| `host/s1b2_row.py` | the row summary, made from the stored runs |
| `host/grade_s1b2.py` | the grader, for afterwards |
| `tests/test_s1b2.py` | 26 tests on the twin behind the pretended board |

### One thing section 25 did not foresee: the judge of a run

Section 25 said the judge of a run would be the walk's judge unchanged. It cannot be, in one
point. S1b.1's judge fails a walk that leaves the envelope without having passed the known
frames in it — and by that rule fails a walk that begins above them. The last run of a chain
begins above them and leaves the row: the first model chain halted on exactly that.

`s1b1_judge.judge` now takes an argument that is off unless asked for; with it on, only the
known frames **at or above the run's start** count for that rule. A walk only goes upward, so a
run that begins beyond a known frame cannot pass it; the run of the chain that began below it
must, and is failed if it does not. `s1b2_judge` is the walk's judge with the argument on, and
the run script uses it for `s1b2` only. For every other set the judge is what it was: the test
that S1b.1 fails a walk begun above the known frames still stands, and the stored S1b.1 results
judge as before. The reference frame is held against its known answer in every run, as before,
so a run that passes no known frame is still checked against one throughout.

### The chain, as built

The rules are those of section 25, in `s1b2_chain.assess`:

- The state of a chain is its stored runs, `DIR/run00`, `run01`, …, and nothing else. Each is
  read from its files and judged again from its raw words, against the block **the chain plans
  for it** — the set's block with the start the chain's own rule gives — before the next is
  looked at. A run that was started elsewhere is not that run.
- A run is accepted if the run script recorded a started, unstopped, passing run with a verified
  card copy; the stored result has the checksum the board gave; the judge passes it; both passes
  ended alike, after as many frames as the walk lists. Every run but the first must begin at the
  last frame of the one before, with the same content and the same address named after it.
- Accepted and ended at the limit: go on, the next run starting at this run's last frame.
  Accepted and both passes ended outside the envelope: complete. Anything else: halted. Halted
  too: run directories with a gap, run directories after the row was left, a run of one frame at
  the limit, and 48 runs without the row being left.
- **Nothing is retried.** A run directory that does not hold an accepted run stays, and the chain
  stands there. Taking a chain up after such a run is a person's act: the directory is renamed
  (anything not named `runNN` is listed as set aside and not looked at), and the chain then
  stands at the run before it.
- On the board (`--go`): a U-Boot `reset` checked as before every run so far, then the run
  script; after every run the whole chain is assessed again and `chain.json` written. A reset
  that does not give the fresh prompt ends the session with nothing run and nothing stored.
  `--max-new N` stops after N runs where the chain stands.

The chain knows no layout: not of the address word, not of a row. It follows the judge's account
of what the device named.

### The row summary and the grader

`s1b2_row.py` knows the fields of the address word and nothing about any part. From the accepted
runs it lists every address with the address named after it, the hash of its frame and the run
that first walked it; groups them into columns as they come, with the number of frames of each
and whether its shape is the plain one (minors 0, 1, 2, …; then minor 0 of the column numbered
one higher); lists whatever is not of that shape under "unexpected", and addresses out of order
or not chained, if there were any; says whether the row was left and what was named then; holds
the column of S1b.1 against a stored verdict of S1b.1 (the same addresses, frames and addresses
named, and no frame more or fewer); and lists which known frames were walked. A chain that
halted is summarized as far as its accepted runs went, with its last column marked as not walked
whole.

`grade_s1b2.py` compares that summary with the database: the frame count of every column walked
whole; the list of columns; the total; and the address named after the row against the first
frame of the row next in the database's order — which is offered as what it is, since the
database lists frames and does not say what a device names. For a chain that halted it compares
the columns walked whole and says the rest was not compared. A test holds that only the two
graders name the database, that the grader imports nothing of the chain's, and that the chain
and the summary contain no number that could be a count of columns or frames.

### Tests

275 tests in all: 26 new ones for the chain, 3 for the tests' own files (below). The model rows
are made up — 26 columns of 2 to 28 frames, 128 frames, column 23 placed so that it holds the
known frames — so that nothing passes because a number was known. On the twin behind the
pretended board:

- a row walked from its first address to the address named after its last, in three runs of 64,
  64 and 2 frames; every frame once in order; each seam frame read by two runs; the board given
  the planned block and no other;
- a chain taken up after one run, and after two, is the same chain; looking at it runs nothing;
- halts: an overflow, a frame that differs between two reads, a run that left nothing behind, a
  card copy that is not the result, a failing first run — and a board that would now pass is not
  tried again; a seam whose content differs, a seam after which another address is named (each
  run passing by itself); a stored result with one word changed, with and without its record
  made to agree; a record edited six ways; a gap; a run moved aside; a run after the end;
- the bound; and nine decisions the twin cannot be made to produce, on runs written out as the
  judge would describe them (passes that disagree in each way, a walk shorter than its passes
  say, a run that did not end, one frame at the limit);
- the ends of a row: an address outside the envelope; an address not above the last frame, and
  the same address again (the prober's own stop, status `0x800`); a row that ends exactly where
  a run reaches its limit; a row shorter than one run; an address inside the envelope of an
  unexpected shape, followed and listed;
- the row summary and the grader on those chains, and on a database that says the same, one
  frame more in a column, a column more, a column fewer, no further row, another row;
- the one rule of the judge of a run, against S1b.1's judge on the same results.

Mutants: 315 in all, 61 of them new (the chain's rules, the row summary, the grader, the run
script's starting address, the one rule of the judge of a run). The record of the complete run
is `evidence/host_checks/mutants_2026-11-15_s1b2.txt`: 315 killed, none survived, none BROKEN or
STALE; the eight scratch copies pass again once restored. It took three goes, and each of the
first two showed something that was mine to mend:

- The first run of the 61 new ones alone killed 56. Three survived — the address named after a
  column was accepted for a column of any number; the last column's minors were not looked at;
  the grader took a column of another row — and each got a test. Two were BROKEN: one was a kill
  that happened in `setUpClass`, the other a mutant aimed at a clause that turned out to be
  redundant, which was removed from `s1b2_row.py`.
- The first complete run (kept as `mutants_2026-11-15_s1b2_run1.txt`) left 29 of the 315 not
  counted as killed, none of them a survivor. 28 were BROKEN: the new tests prepared their
  chains and read the parameter set in `setUpClass`, so with a broken prober whole classes were
  not run and the number of tests did not match. What several tests share is now made in the
  first test that asks for it, so that each of them fails by itself. One was STALE: its anchor
  was the line of S1b.1's judge that this step changed.

### The tests' own files

The complete run after that mending was cut short: the disk was full, and the machine had to be
started again. The cause was in the tests, and older than this step. Every twin run, pretended
board and chain left its files in a directory made with `tempfile.mkdtemp`, and nothing removed
them: about 160 MB for one run of the suite (115 MB before this step), and a complete run of the
mutants is some 330 runs of the suite — about 50 GB, several times that day.

- `tests/scratch_dirs.py`: the tests make their directories under one root per process, removed
  when the process ends, whether it ends well or not. Three tests: that it is so, and that no
  test file makes directories any other way.
- `tests/mutants.py` gives every run of the suite a directory of its own and removes it after
  the run, also if the run was cut short; and it does not start with less than 8 GB free.

Measured afterwards: a run of the suite leaves nothing behind, and during the complete run of
the mutants the temporary directory stayed near 1 GB (the eight copies of the tree).

### What the tests cannot show

That the device behaves at a column's edge, at the first address and at the end of the row as
the twin does: the twin's rows are what I wrote. That is what the board run is for, and why
every way the chain can end short of the row's end is a halt with a report.

### Proposed for the board

`s1b2_chain.py --dir evidence/s1b2_17A6_<date> --go`, with nothing else running on the host.

1. **The first run alone** (`--max-new 1`): it reads the first 64 addresses of the row, none of
   which has been read before. I look at it before going on; if it is not an accepted run, the
   chain stands halted and I report.
2. **Then the chain to its end** — complete, or halted by its own rules. About four minutes a
   run; the bound is 48 runs.
3. The runs, `chain.json` and the row summary are **committed, whatever they say**. A full run
   stores about 3 MB (result, record, verdict, console transcript), so the row may add some
   tens of megabytes to the repository; nothing is left out.
4. **Then the grader**, on the committed summary; its output is recorded and committed.
5. Stop and report.

**Before the board:** the owner's review.

## 27. Review of `7f63553` (2026-11-15): one finding, accepted — known frames passed over across runs

**Finding (P2).** A chain could report "complete" with none of the known frames walked. The
judge asked for the known frames only of a pass that left the envelope. A run that was led past
them and ended at its limit of 64 frames passed; the next run began above them and — by the
rule of section 26 — was not asked for them; and the chain's completion looked at the last run
only. The reviewer's case on the twin: the model row with six columns of 20 frames added, and
the device naming column 24 after column 22. Four runs, all PASS, the chain complete, and
`known_frames_walked` empty.

Reproduced as described, and accepted. Section 26 argued that "the run of the chain that began
below a known frame must pass it, and is failed if it does not"; that was true only of a run
that left the envelope. The row summary did list the three frames as not walked and the step
from column 22 as unexpected — but the chain's word was "complete" and every judge's was PASS,
and those are what the next step would have relied on.

**Mended in two places**, each sufficient for this case:

- **The judge of a run** (`s1b1_judge.judge`, with or without the chain's argument): however a
  pass ended, a known frame whose address lies between the first and the last address the walk
  read, and which the walk did not read, fails the run — "the walk went past the known frame(s)
  … without reading them". The rule for a pass that left the envelope is as it was. The run that
  went past the frames is thus the one that fails, and the chain halts there. For the stored
  results of S1b.1 and of the series before it nothing changes (the tests that judge them again
  pass).
- **The chain** (`s1b2_chain.assess`): when a run leaves the envelope, the chain itself counts —
  from the walks of all its runs, whatever their judges said — whether every known frame inside
  the envelope was walked. If not: halted, "… left the envelope, but no run of the chain walked
  the known frame(s) …". A consequence, and the same as S1b.1's rule for one walk: a chain begun
  above the known frames cannot be complete. The set in use begins at `0x0`.

**Tests** (277; two new, two extended):

- the reviewer's case: the chain halts at the second run, the one that went past the frames;
  that run's stored result is failed by both judges with that one problem; and — to show the
  second mending by itself — the rest of that row, run from where that run ended, passes run by
  run and is halted by the chain's own count when it leaves the envelope;
- a chain begun above the known frames: its one run passes, the chain is halted, nothing more is
  run;
- on written-out runs: none of the known frames walked, one of three not walked, a frame just
  above the last one walked — halted; a known frame outside the envelope — not asked; a row not
  yet left — nothing asked yet;
- the judge alone, by both judges: led past all three and ended by the limit — failed; one of
  the three skipped — failed, naming that one; ended by the limit below them, on the first of
  them, or begun above them — passed.

Six mutants for the two rules, all killed. A seventh (the address named after the row counted
as walked) could not change anything — that address is outside the envelope and is not asked
for — and was removed.

The complete run afterwards (`evidence/host_checks/mutants_2026-11-15_s1b2_review.txt`): 321
mutants, 320 killed, none survived, none BROKEN; one STALE — "runs after the row was left are
overlooked", whose anchor was two lines of the chain that this mending rearranged. Its anchor
was put right and that mutant run alone: killed (`mutants_2026-11-15_s1b2_review_stale.txt`).
Nothing but the list of mutants changed between the two records, so the other 320 were not run
again. During the run the temporary directory stayed near 1.2 GB.

The prober and the image are unchanged. Nothing was run on a board.

## 28. S1b.2 on the board (2026-11-15): 55 columns walked whole; the chain halted at the end of the row

Released by the owner after the review of sections 26 and 27, and run as section 26 says: the
first run alone, looked at, then the chain to its end. The full account is
`evidence/s1b2_17A6_2026-11-15/RESULT.md`. The runs, `chain.json` and the row summary were
committed as they were (`7b782ad`) before anything else was written.

- **Runs 00 to 29 are accepted**: 1,891 frames, `0x00000000` to `0x00001b80`, every one named
  by the device after the one before; 29 seams, all matching. No overflow, no interface failure,
  no anomaly in 8,847 records.
- **Columns 0 to 54 walked whole**, 1,890 frames: 41 columns of 36 frames, 9 of 28 (6, 9, 14,
  17, 22, 25, 42, 46, 49), 4 of 30 (1, 34, 39, 54), one of 42 (column 0). In each the minors are
  0, 1, 2, … and the device then named minor 0 of the column numbered one higher. Nothing is
  listed as unexpected. Column 23 is S1b.1's column again, frame for frame.
- **Run 30 was stopped by the prober** (status `0x800`), and the chain halted, as section 25
  provided for "an address not above the current one". It had walked 42 frames of column 55,
  `0x1b80..0x1ba9`, in one pass. Asked what follows `0x1ba9` (a read of the pad alone), the
  device named `0x1ba9` again; after the frame at `0x1ba9` was read, the register held
  `0x00400000`. One step earlier the register was already one step short: after the frame at
  `0x1ba8`, `0x1ba9` and not what follows it.
- **The third question is therefore answered in part.** The last address of the row that the
  device names like the others is `0x1ba9`; beyond it there is at least one step at which the
  register still reads `0x1ba9`, and then `0x00400000`. The walk's rule — the address named
  after a read of the pad alone — does not carry across that place. How many such steps there
  are, and what a read delivers there, is not known.
- **What the content checks were worth**: 1,713 of the 1,891 frames are all zero (everything
  outside columns 18 to 27 and 39). Where every frame is the same, "the same frame twice, by two
  paths, and at the seam" says little; the address register, recorded at every step, and the
  reference frame are what discriminate there.
- The first address: `0x00000000` was read and is a frame like the others, as UG470 says.

The grader was not run and the database was not looked at: the chain did not complete, and a
halt is saved, committed and reported. One test judges the stored chain again (278 tests).

**Stopped here.** For the owner: whether the halted chain is to be graded as it is (the grader
compares the columns walked whole and says what it did not compare); and what, if anything, is
to be done about the end of the row — column 55 has been read once only, and the step from
`0x1ba9` to `0x00400000` is not understood. Nothing of that has been built or tried.

## 29. S1b.2b — proposal for the end of the row (2026-11-15; a proposal, nothing built, nothing on a board)

The owner agreed to the order: the end of the row first, the grading of the row afterwards, once.
This is the proposal for the first; nothing of it is built.

### The question

Section 28 left two things open. What does the address register do between `0x00001ba9` and
`0x00400000` — how many steps does it stand still, and what does a read deliver there? And are
the 42 frames of column 55, read once by one path, the same when read again by another?

### The idea: the reads of S1b.0 at the last addresses of the row

No new image. The table-driven stage reads, at an address given in the table, the pad and 0, 1,
2 or 3 frames in one read, and records the address register afterwards and every word delivered.
S1b.0 and S1b.0b used it at `0xb98..0xb9a` and found: after the pad and n frames the register is
n + 1 steps on. Here the same reads are made where that stops being true, and the register is
written down at every step.

- **The image is the one in use**: 11,630 bytes, sha256 `2c566b1e…b296`.
- **Stage 5 in its table form, with the wait that touches no memory** (word 15 = `0x200`), no
  extra stack. Stage 5 is stage 3's loop with the choice of the wait. On the board stage 5 has
  run in its sequence form only, and the table form as stages 2 and 3 (with the old wait, at a
  depth where it never overflowed). The table form of stage 5 with the quiet wait is new on the
  board in that combination. The alternative is stage 3 as it ran in S1b.0b; I propose stage 5
  because the cause of the overflows is known to be the stores of the old wait.
- The envelope is the row's, `0x00000000..0x0001ffff`; the reference frame `0xb99`, read before,
  after, and after any anomaly, as in every run.

### Two parameter sets, one run each

**`s1b2e` — the end.** Sixteen reads, each made three times (the prober compares every repeat
with the first: the same words, the same register):

| at | frames after the pad | steps the register is moved |
|---|---|---|
| `0x1ba6` | 0, 1, 2, 3 | 1, 2, 3, 4 |
| `0x1ba7` | 0, 1, 2, 3 | 1, 2, 3, 4 |
| `0x1ba8` | 0, 1, 2, 3 | 1, 2, 3, 4 |
| `0x1ba9` | 0, 1, 2, 3 | 1, 2, 3, 4 |

Every position from `0x1ba7` to four steps beyond `0x1ba9` is thus reached from more than one
starting address (the position two beyond `0x1ba9`, for one, from `0x1ba8` with three frames and
from `0x1ba9` with one), and the register read there must agree. Six of the sixteen repeat what
run 30 already recorded. `0x1ba6` is there as the control: all four of its reads lie where the
rule of S1b.0 held in run 30, bar the last.

**`s1b2c` — column 55 again.** Fourteen reads of three frames, at `0x1b80`, `0x1b83`, …,
`0x1ba7`, each made twice: the 42 frames by a second path and a second time. The frames are
held against those run 30 delivered one by one (the stored result of run 30; no board involved
in the comparison).

A run of either is a few seconds; 49 and 29 records.

### What this reads that has not been read, and the one thing to decide

A read of n frames from F delivers the frames at F and the n − 1 positions after it. From
`0x1ba9` with three frames that is the frame at `0x1ba9` **and whatever lies at the two
positions after it**. Nothing has been delivered from there yet.

- If the register stands still there because the device has positions without an address of
  their own, those two reads deliver what such positions hold — the answer to "what does a read
  deliver there".
- If there is only one such position, the second is the frame the register calls `0x00400000`:
  block type 0, **bottom half**, row 0, column 0, minor 0. That is outside the row.

**The guard does not prevent this, and I want that said rather than found.** It holds a read
inside the envelope by arithmetic: the address written and the count of frames. `0x1ba9 + 2` is
far below `0x0001ffff`. At the end of a row the device leaves the row while the arithmetic stays
inside. So this step, unlike every one before it, may deliver up to **two frames from beyond
the row** — read-only, block type 0 (configuration of logic and I/O; no block-RAM content,
which is block type 1), and no address is written that the device did not itself name.

The bound is in the table: no read starts above `0x1ba9`, and none asks for more than three
frames; so at most two positions beyond `0x1ba9` are delivered, and the register is seen at most
four steps beyond. A parameter set cannot be changed at run time (only `s1b2` takes a start).

If the owner would rather not have anything delivered from beyond the row yet: the table of
`s1b2e` without its last two reads (`0x1ba9` with 2 and 3 frames) and without `0x1ba8` with 3 —
then only the register is seen beyond, up to three steps, and no word from there.

### What would count as what

The run is judged by the judge of the table-driven stage as it stands: the records are the ones
planned, every repeat is the first again, the reference frame is as known, nothing overflowed.
(When building I will check whether that judge requires anything of the register that cannot
hold here; if it does, that is a change to a judge and will be reported as one.)

On top of it a small program, new, lays the result out and knows no layout but the address
word's:

- the register at each position, from each starting address that reaches it, and whether they
  agree;
- for each position beyond `0x1ba9` that was delivered: whether its words are all zero, and its
  hash;
- column 55: the 42 frames of `s1b2c` against run 30's, one by one.

There is no expected answer for the register beyond `0x1ba9`, and none is written into the
program. What is required is only what has been required of every read so far: that the same
read gives the same thing each time, and that two ways to the same position agree. A
disagreement is an anomaly: the run is saved as it is and reported.

Stop rules as in every run: an interface failure or an unhealthy reference ends the run; the
budget of anomalies is 0 beyond what the prober needs to record one.

### What would be built (after the owner's word; host side only)

1. The two parameter sets, written by the image's tests like the others.
2. The run script: the two sets (fixed tables; no address at run time).
3. The layout program above.
4. Tests on the twin, whose model of the end of a row has to be extended: positions after the
   last frame at which the register stands still, in one and in two steps, so that the layout
   program is shown to tell them apart — and deliberate defects for each rule.

The twin will be made to do whatever I write. What the device does there is what the run is for.

### After it

In this order, each needing its own word: the two runs, saved, judged, committed; then
`grade_s1b2.py` on the halted chain of section 28 — and what the end of the row was found to be
held against the database by hand or by a small addition to the grader, to be proposed then.
Whether the walk should learn to cross the end of a row is a question for the step after (it
needs a new image) and is not part of this.

### Open points for the owner

1. **Up to two frames delivered from beyond the row**, as described — or the smaller table that
   delivers none.
2. **Stage 5 with the quiet wait** in its table form, rather than stage 3 as it ran before.
3. **Both sets**, or the end alone: `s1b2c` only repeats column 55 by another path; it reads
   nothing new.
4. As before: I know in general terms how rows of this family are said to end, and that
   knowledge is why I expect the register to stand still for a step or two. Nothing is built on
   it: the program holds no expected value there, and the tests that keep the database out of
   everything but the graders are extended to the new files.

## 30. S1b.2b as built (2026-11-15; host side, nothing on a board yet)

The owner accepted section 29 with all four points as proposed: up to two frames may be
delivered from beyond the row; stage 5 in its table form with the quiet wait; both sets; and
nothing of what I know of the family goes into a program. This is what was built. The prober is
untouched and the image is the one in use: 11,630 bytes, sha256 `2c566b1e…b296`, crc32
`b0d75377`, rebuilt and compared.

### What there is

| file | what it does |
|---|---|
| `tests/test_prober_image.py` | writes the two parameter sets, `s1b2e` and `s1b2c` |
| `host/s1a_run.py` | the two sets; fixed tables, no address at run time (`--start` is refused for them) |
| `host/s1b0_judge.py` | one option, off unless asked for (below) |
| `host/s1b2e_judge.py` | the judge of these two runs: the judge of the table-driven stage, stage 5, with that option on |
| `host/s1b2_end.py` | the layout of the two runs; reads verdict files and nothing else |
| `prober/twin_hal.c` | the twin can be given places at which the register shows another number than the place's own |
| `tests/test_s1b2_end.py` | 17 tests on the twin behind the pretended board |

**The two sets**, as proposed — one correction to section 29: a run has 50 and 30 records, not
49 and 29 (the reference read before and the one after).

- `s1b2e`: stage 5, envelope `0x00000000..0x0001ffff`, reference `0xb99`, sixteen reads — at each
  of `0x1ba6`, `0x1ba7`, `0x1ba8`, `0x1ba9` the pad alone and the pad with one, two, three
  frames — three times over; no anomaly budgeted for; word 15 = `0x200`.
- `s1b2c`: the same but fourteen reads of three frames at `0x1b80`, `0x1b83`, …, `0x1ba7`, twice.

A test holds the bound that was agreed: no address above `0x1ba9` in either table, no read of
more than three frames, at most two places beyond `0x1ba9` delivered by `s1b2e` and none by
`s1b2c`; and, from the twin's own log of a run, that the prober wrote no other address to the
register than those and the reference, and asked for no more than 404 words in a read.

### One change to a judge, as section 29 said might be needed

The judge of the table-driven stage holds every frame that has no known answer against the run
("no known answer for FAR …"). That is right for S1b.0, where every read was of a known frame;
the diagnostic series lived with it (its runs were about how far the prober got). These two runs
read nothing but frames without a known answer, and their verdict has to mean something.

`s1b0_judge.judge` takes an option, off unless asked for: with it on, such a frame is counted
(`frames_delivered_without_a_known_answer`) instead of held against the run. A frame at an
address that has a known answer is compared as ever — the reference frame in particular, before,
after and after any anomaly. `s1b2e_judge` is that judge for stage 5 with the option on, and the
run script uses it for the two new sets only. A test judges the same result both ways: the old
judge fails it with 72 problems, all of them "no known answer"; the new one passes it; and
everything else in the two verdicts is the same, word for word.

What that judge requires of the address register is unchanged, and is what is wanted here: the
same read leaves the same value every time. How the value depends on the length read it reports
and does not require.

### The layout (`s1b2_end.py`)

From the verdict of `s1b2e`:

- whether the starting addresses are one step apart **by the device's own word** (after the pad
  alone at one, the register holds the next). Only then are positions derived: start i is
  position i, and a read from it that clocks out k frames of words ends at position i + k;
- the register at each position, from every read that ends there, and whether they agree —
  positions 4 to 7 lie beyond the last address written;
- what was delivered at each position (a read of n frames from position i delivers positions i
  to i + n − 1), from every read that delivered it, whether they agree, whether it is all zero;
- beyond the last address written: the register step by step, at which steps it did not change,
  and the frames delivered from there.

From `s1b2c` and the stored verdict of run 30: each of the 42 frames against the one the walk
delivered at that address. Which address a frame of a read of three belongs to is taken from the
walk's own account of what follows what, not from arithmetic; the register after each read is
held against the walk's successors as far as they reach (the last read ends beyond them and is
listed without a judgment); and the one read both table runs make must have left the same in both.

**It holds no expected value** — a test holds that the file contains no address and no count —
and requires only that two ways to the same position agree. A disagreement is listed and the
exit code is 1; so it is for a run the judge did not pass, which is laid out all the same and
marked as not a finding.

**It says when content says nothing.** On the board the frames of column 55 are all zero. Where
every frame delivered is the same, agreement about content cannot tell one position from
another; the layout then says exactly that, in both parts. The register is what will tell.

### The twin's ends of a row

`SM_SHOWS` gives the twin places at which the register reads another number than the place's
own; with `SM_SUCC` that models places the device passes through that have no address. The tests
run both sets on four ends: one such place; two, the register standing still at the first; two,
standing still at both; none. Two of the four reproduce the last six records of run 30 as they
are stored from the board (a test compares them), and the layout tells all four apart by the
register alone. Which of them the device is — or whether it is none of them — the twin cannot
say: it does what I wrote.

### Tests and mutants

295 tests, 17 of them new: the tables and their bound; the judge both ways, a reference frame
that differs, an overflow, a register and a frame that differ between repeats (each stops the
run, as no anomaly is budgeted for); the layout on the four ends, on frames that are all zero, on
a place beyond the row that is not zero, on starting addresses that are not one step apart, on
verdicts changed so that two ways disagree in each manner; the column against the walk, with a
frame, a register and a repeat that differ, a walk that is shorter and one that is longer.

Thirty-three mutants for this step (the twin's row end is not among them: it is the model, and
the tests of the four ends hold it). While they were being written, run by themselves, 32 were
killed and one was BROKEN: it removed an `if` and left a `for` with no body, which is not a
program, so the suite did not load and it said nothing about the tests. It was rewritten to make
the condition false instead.

The complete run afterwards (`evidence/host_checks/mutants_2026-11-15_s1b2b.txt`): 354 mutants,
354 killed, none survived, none BROKEN, none STALE; the unmutated tree before and the restored
tree after both run 295 tests, OK. The rewritten mutant ("s1b2 end: a repeat that differs is not
noticed") is killed by the test of two ways to a place that do not agree. The temporary
directory was empty afterwards.

### What the tests cannot show

What the device does beyond `0x1ba9`. And one thing the run itself may not be able to show: if
the places beyond the row deliver all-zero frames, as the whole of column 55 does, then "what a
read delivers there" has the answer "zeros" and nothing distinguishes a place beyond the row
from a frame of it but the register.

### Proposed for the board

With nothing else running on the host; before each run a U-Boot `reset` and a fresh load, as
always.

1. `s1a_run.py --stage s1b2e --go` — one run. Saved, judged, **committed whatever it says**.
2. `s1a_run.py --stage s1b2c --go` — one run. The same.
3. `s1b2_end.py` on the two verdicts and the stored verdict of run 30; its output is recorded
   beside them and committed.
4. If a run stops or does not pass: it is saved and committed as it is, nothing further is run,
   and the layout is made of what there is and recorded as that.
5. Stop and report. The grader is not run in this step.

**Before the board:** the owner's review.

## 31. S1b.2b on the board (2026-11-16): the register stands still twice at the end of the row

Released by the owner after the review of section 30, and run as section 30 proposes: `s1b2e`,
then `s1b2c`, each after a U-Boot `reset`, each committed as saved (`30badca`, `c5191ab`); then
the layout, committed as it came out (`8496bec`). The image is unchanged (`2c566b1e…b296`). The
full account is `evidence/s1b2b_17A6_2026-11-16/RESULT.md`.

- **Both runs pass**: 50 and 30 records, status 1, no anomaly, no overflow, no interface
  failure; every repeat left what the first did; the reference frame as known. The layout has no
  disagreement (exit 0).
- **The register beyond `0x1ba9`, by frames of words clocked**: `0x1ba9` (one step), `0x00400000`
  (two), `0x00400000` (three), `0x00400001` (four). Each of these is what every read that ends
  there left — 4, 3, 2 and 1 reads from different starting addresses, three times each. The
  register does not change at the first step beyond the last address of the row, and not at the
  third.
- **Two frames were delivered from beyond `0x1ba9`**, the most the owner allowed and the most
  the table can deliver. Both are all zero, as is every one of the 72 frames of that run. Their
  content does not say what they are.
- **Column 55 by the second path**: 42 frames compared with the walk of run 30, 42 the same; the
  register after 13 of the 14 reads is what the walk's successors say, and the 14th ends beyond
  the walk at `0x00400000`, as the same read does in `s1b2e`. All 42 are all zero: the agreement
  that carries weight is the register's.
- **For the row of S1b.2** the device has now named, one after another, `0x00000000` to
  `0x00001ba9`: columns 0 to 55, 1,932 frames (column 55 has 42, like column 0), and after
  them, past one step at which the register stands still, `0x00400000` — outside the envelope.
  The stored chain of S1b.2 is not altered by this: it halted, and stays recorded as halted.

Not shown: what the two positions beyond `0x1ba9` are; what a read started at `0x00400000`
does (no address above `0x1ba9` was written); whether other rows end this way; the mechanism.

One test judges the two stored runs again from their raw words, holds each against its stored
verdict and its hash, makes the layout again and holds it against the stored one (296 tests).
It adds no program, so no mutant was added; the programs it uses are held by the 354 of
section 30.

The grader was not run and the database was not looked at.

**Stopped here.** For the owner, separately: (1) grading — the columns of the row against
prjxray-db, now that what the device says about the end of the row is saved and committed
first; `grade_s1b2.py` was written for a chain that completed, and what it is to do with a
halted chain plus this step needs a word before it is run; (2) whether the walk is to learn to
cross a row end (a change to the prober, a new image, its own proposal and review). Nothing of
either has been built or tried.

## 32. Grading the row — proposal (2026-11-16; a proposal, nothing built, the database not looked at)

The owner's order (section 28): the end of the row first, then the row graded once. The end is
recorded (section 31). This is how I propose to grade; nothing of it is built or run.

### The difficulty

`grade_s1b2.py` grades a row summary (`row.json`), and the stored summary is that of a halted
chain: columns 0 to 54 whole, column 55 with **one** frame (`0x1b80`, the last frame of the last
accepted run), the row not left. Run as it is, the grader would compare 55 columns, say of
column 55 "the chain stopped in it after 1 frame; the database gives it N", and compare neither
the length of the row nor what follows it. What the device said about column 55 and the end is
in three other stored results: the walk of run 30 (stopped by the prober, so not accepted by the
chain), `s1b2c` and `s1b2e`.

Two ways:

- **A. Grade the stored summary as it is** and compare column 55 and the end by hand in the
  record. No program; and the two comparisons that are new would be made by me, reading a
  number off the database's output and a number off `end.json`.
- **B. First write down, by a program and from the stored results alone, what the device says
  the whole row is — and commit that — then give it to the grader unchanged.** Proposed.

### B: the row as closed by S1b.2b

A program `host/s1b2_closed.py` takes the stored `row.json`, the stored verdict of run 30, and
the two verdicts of S1b.2b, and writes `row_closed.json` in the form of `row.json`. It holds no
number of frames or columns and reads no database. Its rules, fixed here before any database is
opened:

1. **The frames of the last column.** The walk of the run the chain did not accept contributes
   its addresses only if (a) its only fault is the stop at an address that names itself (status
   `0x800`), (b) it began at the last frame of the last accepted run, with the same frame there,
   and (c) `s1b2c` read **every** one of its addresses again by the other path with the same
   frame, and the register after each of those reads was what the walk's successors say
   wherever they reach. Then the column is the walk's addresses, in the walk's order.
2. **The last address of the row** is the address A at which the pad alone leaves the register
   at A — in the walk and in `s1b2e`, every repeat.
3. **The address named after the row** is the first value other than A that the register shows
   as further frames of words are clocked from A, agreed by every read that reaches that
   position; the number of steps the register stood still before it is recorded beside it.
4. Columns 0 to 54 are taken from `row.json` unchanged. The chain's state stays `halted`, and
   the summary says of itself that it was closed by a second step and from which results.
5. If any of this is not so — a run that did not pass, a disagreement in the layout, an address
   of the walk not read again, a frame or a register that differs — **no closed summary is
   written**; the program says which rule failed, and the grading is then way A's first half
   only (the 55 columns), reported as that.

On the stored results these rules give (by section 31; the program has to arrive at it itself):
column 55 with 42 frames `0x1b80..0x1ba9`, the row 56 columns and 1,932 frames, the address
named after it `0x00400000` after one step standing still.

### The grader

Unchanged in what it compares: the number of frames of each column walked whole, the columns
being the database's columns of that row in order, the frames of the row in all, and the address
named after the row against the first frame of the row next in the database's order. One
addition: where the summary records steps at which the register stood still, the grader lists
them under `not_compared` — the database lists frames and has nothing to hold them against.
The two positions beyond `0x1ba9` and the frames delivered there are likewise not graded.

It reads `part.json` of prjxray-db as it is on this machine, as in S1b.1, and prints only what
concerns this row and the address after it. No bitstream is parsed; Vivado is not involved.

### Order

1. Build `s1b2_closed.py`, the grader's one addition, tests on the twin (the four row ends; each
   rule of 1 to 5 broken in turn refuses), mutants. The owner's review.
2. After it: `row_closed.json` made from the stored results and **committed**.
3. Then the grader, once, on `row_closed.json`; `grade.json` stored beside it and committed
   whatever it says. A difference is a finding about the database or the device, not a failure,
   and nothing is changed to make it go away.
4. Stop and report.

No board is involved in any of it.

### For the owner

- A or B.
- Rule 1: whether a walk the chain did not accept may count once a second path has confirmed
  every frame of it. The alternative is to say column 55 was "read, 42 frames, not accepted by
  the chain" and leave it out of the grading.
- Whether steps 1 to 3 may run together after the review of step 1, or the grader waits for a
  word of its own after `row_closed.json` is committed.

## 33. Grading the row, as built (2026-11-16; host side — no database read, nothing graded)

The owner agreed to section 32 on all three points: way B; a walk the chain did not accept
counts once the second path has confirmed every frame of it; steps 2 and 3 may follow one
another after the review of this.

### What was built

- **`host/s1b2_closed.py`** — `close(row, walk, again, at_the_end)` and a command line of the
  four files. It applies the rules of section 32 in order and returns either the row in the
  form of `row.json`, or `{"refused": [...], "rules": {...}}` with exit code 1 and nothing a
  grader could take for a row. It imports `s1b2_end` (the layout: the same program that made
  `end.json`) and `s1b2_row` (the summary: the same program that made `row.json`), and nothing
  else of the project; no database, no number of frames, columns or steps.
  - Rule 1a is held as: status `0x800`, no anomaly, the last address of the walk names itself,
    the walk is a chain of names (each address the one named after the one before), and every
    problem the judge lists is one of the two it lists for such a stop — the run not completing
    with that status, and the cross-check at the last address against the address that names
    itself. Anything else among the problems refuses.
  - Rule 2 also requires that the starting addresses of `s1b2e` follow one another as the walk
    says they do: two runs on two days naming the same successors.
  - Rule 3 takes "outside the row" from the address word: block type, half or row differs from
    the last frame's.
  - Rule 4 is not an assumption but a check: the longer list is given to `s1b2_row.summarize`,
    and the columns before the one cut short have to come out exactly as the chain's summary
    has them, and the one cut short has to be the same column beginning at the same address.
  - What it adds to the summary: the frames of the walk after the seam, marked as coming from
    "the run the chain stopped on"; under `end`, the address named, the steps the register
    stood still, the register step by step, and the frames delivered from beyond (how many, and
    whether all zero); under `closed`, that it was closed, by what, the rules, and the counts.
    **`chain` is copied unchanged: `halted`, with its reasons.**
- **`host/grade_s1b2.py`**, two additions and nothing else: a summary that carries `closed` is
  said to be one in the grade (`summary_closed_by`); and where the summary records steps at
  which the register stood still, and frames delivered from beyond the row, each is listed
  under `not_compared`. What it compares, and how, is as it was.

### On the stored results (no database involved)

A test runs the program on the stored `row.json`, the stored verdict of run 30 and the two
stored verdicts of S1b.2b. All six rules hold. It gives what section 31 said by hand: 56
columns, 1,932 frames; columns 0 to 54 and the first 1,891 addresses exactly as the chain's
summary has them; column 55 `0x1b80..0x1ba9`, 42 frames, minors 0 to 41; nothing unexpected;
after the row `0x00400000`, the register having stood still one step before it (steps 1 and 3
beyond the last frame); two frames from beyond, both all zero. Given the two runs of S1b.2b in
each other's place, it refuses. `row_closed.json` itself is **not yet written to the evidence**:
that is step 2, after the review. (The test holds the stored file against the program once it
exists.)

### Tests and mutants

14 new tests (310 in all). On the twin: the three ends of a row at which a walk is stopped
(one place, two places with the register still at the first, two with it still at both) are
closed, with 1, 1 and 2 steps standing still; every rule broken in turn refuses, and the test
says which rule; a summary with nothing to close refuses; an address after the standstill that
lies in the same row refuses, one in another row, half or block type does not; the command
line; the program holds no answer. The grader on a closed row: agrees and differs where a
made-up database does, says the summary was closed, lists the two things not compared; the
chain's own summary is graded as before; a refusal given to the grader is "no column".

One thing the tests showed about the rules, not about the program: the two runs of S1b.2b
share one read (`0x1ba7`, four steps). If only one of them is changed to name another address
after the row, rule 1c refuses — the layout holds the shared read of the two runs against each
other. A test now says so.

37 mutants were written (34 for `s1b2_closed.py`, 3 for the grader's additions). Run by
themselves, 33 were killed and 4 survived:

- two were gaps in the tests, now closed: no case had a walk whose last address names
  *another* address with everything else in order, and none had a failed cross-check at the
  last address that is not the stop's;
- one was equivalent and was removed: "the run at the end may have written another last
  address". That condition is implied by two others (the starting addresses are one step
  apart; the pad alone at the walk's last address leaves it standing) — if the walk's last
  address were not the last one written, the pad alone there would name the next. The
  condition stays in the program because rule 3 reads the register "beyond the last address
  written" and should not depend on an implication made elsewhere;
- one was a mutant that changed nothing (the first of two refusal points bypassed; the second
  still refused) and was replaced by one that does: a row whose rule 4 failed written all the
  same. Killed.

The complete run afterwards (`evidence/host_checks/mutants_2026-11-16_s1b2_closed.txt`): 390
mutants (the 354 of section 30 and these 36), 390 killed, none survived, none BROKEN, none
STALE; the unmutated tree before and the restored tree after both run 310 tests, OK. The
temporary directory was empty afterwards.

### What the tests cannot show

That the rules are the right ones: they were fixed in section 32 and agreed to by the owner
before the database was opened, and the program holds them; whether a walk the chain did not
accept should count is a decision, not a finding. And that the database says anything about the
end of a row: the grader will list what it could not compare.

### Proposed, after the review (no board)

1. `s1b2_closed.py` on the stored `row.json`, the stored verdict of run 30 and the two stored
   verdicts of S1b.2b; its output written to
   `evidence/s1b2b_17A6_2026-11-16/row_closed.json` and **committed**, with its hash held by
   the test.
2. Then `grade_s1b2.py` once on that file, against prjxray-db's `part.json` as it is on this
   machine; `grade.json` stored beside it and committed whatever it says.
3. If step 1 refuses (it does not on the stored results today): the refusal is stored and
   committed, the grader is run on the chain's own `row.json` instead, and that is reported as
   what it is.
4. The record, and stop. A difference is a finding and nothing is changed to make it go away.

**Before any of it:** the owner's review.

## 34. The row graded (2026-11-16): no difference from prjxray-db

Released by the owner after the review of section 33; no board involved. In the order laid
down: `row_closed.json` written and committed (`6c06397`), then the grader once, its output
committed as it came (`fffe4cc`). The account is at the end of
`evidence/s1b2b_17A6_2026-11-16/RESULT.md`.

- **The closing**: all six rules hold on the stored results. 56 columns, 1,932 frames; the
  chain's 55 columns and 1,891 addresses unchanged; the chain still recorded as halted.
- **The grade**: each of the 56 columns has the number of frames the database gives it; they
  are the database's columns 0..55 of row 0 of the top half, in order, and it has no more;
  1,932 frames on both sides; the address the device named after the row, `0x00400000`, is the
  first frame of the row next in the database's order — row 0 of the bottom half, the top half
  having one row in the database. **Nothing differs.**
- **Not compared**: the two steps at which the register stood still, and the two frames
  delivered from beyond the row. The database has nothing on either.

So S1b.2's three questions are answered for this row: which addresses the device names along
it, into which columns they fall and how many frames each has, and what it names after the
last — the last with a standstill the walk's rule did not foresee.

A test holds the stored `row_closed.json` and `grade.json` by their hashes and against the
programs (310 tests; the stored grade is read, the database is not). A slip is recorded in the
result note: the grade was committed before the suite was run, and an assertion that had
become untrue ("no grade in this directory") failed until the next commit replaced it.

**Stopped here.** Next, for the owner — nothing of it proposed in detail or built: S1b.3 (all
of block type 0, both halves) needs a walk that can cross a row end; what the register does
there is now known for one row end (it stands still, then names the next row), and the change
to the prober, a new image, and how its guard is to bound a walk that leaves a row each need a
proposal and a review of their own.

## 35. S1b.3a — proposal: a walk that crosses the end of a row (2026-11-16; a proposal, nothing built, nothing on a board)

S1b.3 is "all of block type 0, both halves". The walk as it is stops at the end of a row
(status `0x800`). Before any chain over more than one row: the walk has to cross a row end, and
that has to be seen once, alone, on the one row end that is known. This proposes that first
step only. The chain over block type 0, its summary over several rows and its grading are a
later proposal, written when this one's result is in.

### What is known, and what the walk already reads there

At the last address A of the row (section 31; one row end, one day):

| read at A | register afterwards |
|---|---|
| the pad alone | A — it stands still |
| the pad and the frame at A | N, an address outside the row (`0x00400000`) |

The walk makes exactly these two reads at every address: the pad alone ("what follows?") and
the pad with the frame (its content). **So at a row end it already has N in hand, in the record
of the content read. No new read is needed to cross; only what the prober does with what it
has read changes.**

### The rule proposed

At an address `cur`, after the two reads as now:

- the pad alone left the register **above** `cur`: as now, that is the next address;
- the pad alone left it **at** `cur` (a standstill), and the read of the frame at `cur` left it
  at some `N` **above** `cur`: `N` is the next address, and the step is marked as a standstill
  in the walk. If `N` is beyond the envelope the pass ends as "left", as now; otherwise the walk
  goes on at `N` — an address the device named, written to the register like any other;
- anything else stops the run with `0x800` as now: the register below `cur` after the pad
  alone; or at `cur` after the pad alone and not above `cur` after the frame (a place where it
  stands still for longer than was seen — the twin has such an end, and it must halt there).

A parameter gives **how many standstills a pass may cross; 0 in every existing parameter set**,
where the prober then behaves exactly as now (stop at the first). One more than allowed stops
the run with a status of its own. For this step: **1**.

### The reads of three frames must not span a standstill

After its passes the walk reads the frames again three in one read, from every third address of
the list. A read of three starting two frames before a row end would deliver the last two
frames of the row **and whatever lies at the place where the register stands still** — and the
prober would hold that against the first frame of the next row.

So the list is cut at every standstill, and the reads of three are laid within each piece by
the rule that now applies to the whole list (three from every third address; one or two left
over: the last three of the piece again; a piece of two: both; a piece of one: no second path,
and the judge lists it). **With that, no read of this walk delivers anything from a place the
device has not named**: the pad alone delivers nothing, a content read delivers the frame at the
address written, and a read of three delivers three addresses that follow one another by the
device's own word with no standstill between them.

One limit of that, said plainly: the prober takes "no standstill between them" as "nothing lies
between them". If a device had a place between two named addresses at which the register does
*not* stand still, a read of three across it would deliver one frame from there before the
check that catches it (the register after the read is one step short) stops the run. That has
been so since S1b.1 and has not happened across 55 column ends.

### The guard

Unchanged. It still holds every address written inside the envelope and every read to at most
three frames, by arithmetic. It does not know where a row ends, and is not asked to: the
envelope keeps the walk inside what the owner released; that reads do not run across a row end
is the walk's rule above, re-derived by the judge from the records.

### The judge

`s1b1_judge` re-derives the same rule from the raw words: a standstill is accepted only as
above, counted against the allowance in the parameter block, and — with the allowance 0 — is the
stop it is now, so every stored run is judged as before. For a standstill step the cross-check
of the register changes its form: "after any read whose last frame delivered is X, the register
is what it was after the single read of X" (elsewhere this is the check there is now, in other
words). Every read of three is checked to lie within one piece. The second pass must stand
still where the first did.

### The image

A new image: `sm_core.c` changes in the walk stage only (the rule, the allowance, the pieces).
The other stages' source is untouched, but the binary moves. The wait that touches no memory is
used, as in every run since section 22; the address of the polling variable is recorded in
every result as before; no anomaly is budgeted for, so an overflow would stop the run and be
seen. The twin gets no new model: its four row ends (section 30) are what the walk is tested
on — it must cross two of them, halt at the one where the register stands still for longer,
and walk straight on at the one with no standstill.

### The run proposed for the board: one, across the known row end

- The walk's parameter set with three differences: **the envelope is block type 0 whole,
  `0x00000000..0x007fffff`**; the allowance is 1; the start is `0x00001b80`, the last frame of
  the chain's last accepted run (the seam). Two passes, at most 64 frames a pass, the reference
  frame `0xb99` every 16 frames, the quiet wait, no extra stack.
- What it would read, if the device does again what it did: the 42 frames of column 55 (read
  twice already, by two paths), the standstill at `0x1ba9`, and then **22 frames from
  `0x00400000` on — the bottom half, where nothing has been read or written to the register
  yet**. Block type 0 only (configuration of logic, I/O and clocking; block-RAM content is block
  type 1, outside the envelope and never written to the register). Read-only, as everything so
  far.
- What it answers that is open: what a read started at `0x00400000` does (the pad alone there:
  does the register go on, or stand still again?), and whether the walk carries on beyond a row
  end as it does along a row.

### What would count as what

- **PASS** (the judge): the run completes; both passes the same list and the same standstill;
  every cross-check of the register holds; every read of three within one piece and equal to
  the single reads; the reference frame as known throughout; no anomaly.
- Afterwards, on the host and from stored results only: the seam with run 29 at `0x1b80`, the
  42 frames against run 30's and `s1b2c`'s, the registers at the row end against `s1b2e`'s. A
  difference is reported; it does not alter the run.
- **A second standstill within the pass** (for one, at `0x00400000` itself): the run stops with
  the status for "more than allowed". That is a finding about the device, saved and reported;
  the walk is not made to go on.
- Anything else that stops the run: saved, committed, reported; nothing retried.
- The grader is not run in this step. (What the database says of the top half's rows was seen
  in section 34's grade; nothing of the bottom half has been looked at.)

### For the owner

1. **Only this step now** (one run across the known row end), and the chain over block type 0
   as a proposal of its own afterwards — or both at once.
2. **The rule**: one more step and no more — the register after the frame's own read. A row
   end at which that is not enough halts. (The alternative, clocking further frames until the
   register moves, delivers from places without a name; I do not propose it.)
3. **The allowance: 1** (a second standstill in the pass halts and is reported) — or 2, which
   would let the walk go on if `0x00400000` itself turns out to be an address at which the
   register stands still.
4. **The envelope `0x0..0x007fffff`**: this run enters the bottom half, up to 22 frames. A
   smaller bite is possible (a limit of 48 frames a pass: 6 frames beyond the row end — enough
   for the pad alone at `0x00400000` and two reads of three there).
5. **A new image**, with the walk's behaviour unchanged wherever the allowance is 0.

## 36. S1b.3a as built (2026-11-16; host side, nothing on a board yet)

The owner agreed to section 35 on all five points: this step alone; the rule of one more step
and no more; an allowance of 1; the envelope `0x0..0x007fffff` with a pass of 64 frames; a new
image whose walk is unchanged wherever the allowance is 0.

### What was built

- **The prober, `sm_core.c`, in the walk stage only** (and three definitions in `sm.h`).
  - Parameter word 10 is the allowance: how many standstills a pass may cross. The
    table-driven stages use that word for frames per read; the walk has no table and its
    judge required the word to be 0 until now. More than 4 is refused as a bad parameter block.
  - At an address `cur`, after the two reads the walk always makes: if the pad alone left the
    register at `cur`, the allowance is not 0, and the read of the frame left the register
    above `cur`, that value becomes the next address; the header's "last address named" is
    set to it. With the allowance used up the run stops with a new status, `0x900`. In every
    other case nothing differs: below `cur`, or at `cur` and not above after the frame, is
    `0x800` as before; with the allowance 0 the new branch is never entered.
  - The list of pass 0 is cut after each frame at which the register stood still; the reads of
    three are laid within each piece by the rule that applied to the whole list.
  - No new read, no new record field, no change to the guard, to the streams, or to any other
    stage's source.
- **The image**: 11,970 bytes, sha256 `fdc4f07f…9452` (340 bytes more than `2c566b1e…`). The
  checks the image test makes of the disassembly hold as before, the one on the wait that
  touches no memory among them.
- **The judge, `s1b1_judge.py`** re-derives the same from the two records at each address and
  from the parameter block: the standstill, the allowance, the status `0x900`, the pieces and
  the reads of three within them (a read laid otherwise is "not the record the schedule has
  here").
  - The cross-check of the register: "names" now means what the pad alone left — which is what
    it always was except at a standstill. The step of a standstill has no cross-check of the
    old kind and is not counted. A read of three that ends with the frame of a standstill is
    held against the single read of that frame: both end at the same place.
  - **A run without the allowance is reported exactly as before**: the new keys (`standstills`,
    `pieces`, `standstills_a_pass_may_cross`, `stood_still` on a step) appear only where the
    allowance is set or a step stood still. Every stored result is judged again to the stored
    verdict, word for word, by the tests that already held them.
- **The set `s1b3a`** and its entry in the run script: `s1b2`'s set with the envelope's upper
  end `0x007fffff`, word 10 = 1, the start `0x00001b80`; judged as a run of a chain (it begins
  beyond the known frames). Its start is fixed: `--start` is refused.
- **`host/s1b3a_seam.py`** — for after the run, from stored results only: the run's verdict
  held against `row_closed.json`. Every address the two share: the same frame, the same
  address named; at the last frame of the stored row the run must have stood still and gone on
  to the address the row has named after it; the two registers of the standstill against the
  stored step-by-step values. Addresses the stored row does not have are counted, and have to
  follow the row's last frame. No expected value; exit 1 on a disagreement or a run that did
  not pass.

### On the twin

The four row ends of section 30, through the run script on the pretended board:

- **two places, the register still at the first** (the one whose registers are the board's)
  and **one place**: crossed. 64 frames a pass: the 42 of the column, then 22 by the names the
  device gave; one standstill, at `0x1ba9`; pieces of 42 and 22; 22 reads of several frames,
  none across the standstill; **nothing delivered from either place without an address, and
  no address written that the device did not name**.
- **two places, the register still at both**: stops with `0x800` after 42 frames, as before —
  the register is not above after the frame. No standstill is accepted.
- **no such place**: walked straight on, 64 frames, one piece.
- With the allowance 0 at the board's end: the stop of S1b.2's run 30 — the last six records
  and the judge's two problems as stored from the board.
- Three row ends close together (pieces of 4, 1, 2, 9): with the allowance 3 crossed, and the
  reads of several frames are (3 and the last 3 again), (none), (both), (three threes); the
  piece of one frame is listed as having no second path. With the allowance 1 or 2: `0x900`
  at the standstill that is one too many, nothing written above it.
- A standstill whose next address is beyond the envelope ends the pass as "left" (the row as
  the envelope: this is the end S1b.2's chain did not reach); one at the limit ends it at the
  limit.

**One thing the tests showed about the run proposed, not about the program.** From `0x1b80` the
column has 42 frames, and 42 is fourteen threes: an uncut list would place its reads of three
exactly where the cut list does. So on the board this run cannot show the difference between
cutting and not cutting; the twin's rows with pieces of 4, 1 and 2 are what holds that rule.
It will matter in a chain, where a run may meet a row end at any place in its list.

### Tests and mutants

24 new tests (334 in all); one older test adjusted (it asserted that word 10 of a walk's block
must be 0; it now asserts that 5 there, and anything in words 11 and 14, is invalid).

43 mutants written: 11 in the prober, 18 in the judge, 1 in the run script, 13 in the seam
program. Four older mutants had anchors on lines this step rewrote (the leftover rule in the
prober and the judge, the unused parameter words) and were re-anchored. Run by themselves: 41
of the 43 killed; one BROKEN (it left a variable set and unused, which the build refuses) and
rewritten; one survived — "too many standstills imply the old stop" in the judge — because the
test filtered the judge's problems by a text that the mismatch also contains. The test now
holds the exact list of problems. Both killed afterwards, and the four re-anchored ones.

The complete run afterwards (`evidence/host_checks/mutants_2026-11-16_s1b3a.txt`): 433
mutants (the 390 of section 33 and these 43), 433 killed, none survived, none BROKEN, none
STALE; the unmutated tree before and the restored tree after both run 334 tests, OK. The
temporary directory was empty afterwards.

### What the tests cannot show

- What the device does at `0x00400000`: whether the pad alone there names `0x00400001` or
  leaves the register standing. The twin has both kinds of end; the walk crosses the one and
  stops with `0x900` at the other.
- That the new image runs on the board as the old one did. The source of the other stages and
  of the wait is unchanged, but the binary moved; the run itself is the check, with no anomaly
  budgeted for and the address of the polling variable recorded in every record.
- Whether a row end elsewhere is like this one.

### Proposed for the board

With nothing else running on the host; a U-Boot `reset` and a fresh load before the run.

1. `s1a_run.py --stage s1b3a --go` — **one run**, with the new image (`fdc4f07f…9452`). Saved,
   judged, **committed whatever it says**.
2. `s1b3a_seam.py` on its verdict and the stored `row_closed.json`; the output recorded beside
   the run and committed.
3. If the run stops or does not pass: saved and committed as it is, nothing retried, the seam
   program run on what there is and its output recorded as that.
4. Stop and report. The grader is not run; the database is not looked at for anything beyond
   the row already graded.

**Before the board:** the owner's review.

## 37. S1b.3a on the board (2026-11-17): PASS — the walk crossed the end of the row

Released by the owner after the review of section 36, and run as section 36 proposes: one run
of `s1b3a` with the new image (`fdc4f07f…9452`) after a U-Boot `reset`, committed as saved
(`f46bea7`); then `s1b3a_seam.py` against the stored row, committed as it came out (`9a2328a`).
The full account is `evidence/s1b3a_17A6_2026-11-17/RESULT.md`.

- **PASS**: 292 records, status 1, no anomaly, no overflow, no interface failure. Both passes
  the same 64 addresses and ended at the limit.
- **The standstill at `0x1ba9` was crossed**: the pad alone left `0x1ba9`, the read of the
  frame `0x00400000` — the values of sections 28 and 31, a third time.
- **At `0x00400000` the register goes on**: the pad alone there names `0x00400001`. The open
  question of section 31 ("what a read started at `0x00400000` does") is answered for this
  row end: nothing unusual; the address behaves like any other. So, by the register, the end
  of this row is two steps at which it does not advance as along a row, and then the next row.
- **22 frames of the bottom half**, `0x00400000..0x00400015`, each named after the one before,
  read in both passes and in reads of three. No read lay across the standstill; nothing was
  delivered from the two places without an address.
- **Against the stored row**: no disagreement — the 42 shared addresses, the standstill, its two
  registers.
- **All 64 frames are all zero.** The content checks are empty here; the register and the
  reference frame carry the result.
- The new image: one clean run. The polling variable of the walk's reads lay 32 bytes lower
  than with the old image, in the same residue (24 mod 32).

One test judges the stored run again from its raw words and holds verdict, comparison and
image by their hashes (335 tests). The grader was not run.

**Stopped here.** For the owner: S1b.3 proper — a chain of runs over block type 0 with the
allowance set, where it stops (the device naming an address beyond `0x007fffff`, or anything
unforeseen), a summary over more than one row, and its grading — needs its proposal. Among
the things it has to settle: whether the chain starts again at `0x00000000` with the new image
or takes up from the stored row; and that from here on most of what is read may again be all
zero, so that the register is what the result rests on.

## 38. S1b.3 — proposal: the chain over block type 0 (2026-11-17; a proposal, nothing built, nothing on a board)

S1b.3 is "all of block type 0, both halves: the frame list of block type 0" (section 3). The
walk can now cross a row end (section 37). This proposes the chain that uses it, what is made
of its runs, and how that is graded. Nothing of it is built.

### What is known and what is not

Known, from the device: the top half begins with a row of 56 columns and 1,932 frames,
`0x00000000..0x00001ba9`; after it the device names `0x00400000`, the bottom half, where 22
frames have been walked. Not known: how long that row is, whether more rows follow in either
half, what the device does at their ends, and what it names after the last frame of block
type 0. No number of rows or frames is assumed below; the chain goes where the device names
and stops where it leaves the envelope or does something not provided for.

### The chain

The chain driver of S1b.2, with a parameter set of its own and nothing else changed in its
rules (section 25): each run starts at the last frame of the run before; a run is relied on
only if the run script, the judge, the two passes and the seam all agree; nothing is retried.

- **The set `s1b3`**: the walk with the envelope `0x00000000..0x007fffff` (block type 0 whole
  and nothing above it), one standstill a pass allowed, two passes, at most 64 frames a pass,
  the reference frame `0xb99` at most 16 frames apart, the wait that touches no memory. The
  start is the one word given at run time, by the chain. The image is the one of section 37
  (`fdc4f07f…9452`), unchanged.
- **It goes on** after a run that ended at the limit, as now.
- **It is complete** when a run's passes both end because the device named an address beyond
  the envelope — after a standstill or without one — and every frame with a known answer was
  walked by some run. No address at or above `0x00800000` is ever written to the register:
  block type 1 (block-RAM content) is outside the envelope, and a read of one frame at the last
  address named delivers that frame and nothing after it.
- **It halts** on anything else, as now. In particular: a second standstill within one pass
  (status `0x900` — a row shorter than a pass, which would be news); a standstill that one more
  step does not resolve, or an address named that is not above (`0x800`) — which is what the
  end of block type 0 may turn out to be, since nothing is known of it; any anomaly; any seam
  that does not match. A halt is saved, committed and reported, and what the chain has by then
  is summarised as that.

### Where it starts: at `0x00000000`, again

Two ways. **A: from `0x00000000`**, walking the top row a second time (31 runs, about 2 h 15
min) and going on from there. **B: taking up at `0x00400015`**, the last frame of section
37's run, and putting the list together from four stored sources made with two images.

I propose **A**:

- the frame list of block type 0 is then one chain's, with one image and one envelope;
- the top row is read on another day by another image — 1,932 addresses against the stored
  ones, among them the 178 frames that are not all zero and the three with a known answer.
  That is a repetition worth having: the new image has so far delivered nothing but zeros;
- the chain's completion rule ("every known frame was walked by some run of the chain") holds
  as it is. A chain that begins beyond the known frames can never be complete by that rule
  (section 27), and B would need the rule changed.

The cost is the board time. The runs are unattended.

### How long, and the bound

A run is about 4 min 20 s. The top row is 31 runs. How many the rest takes is not known. The
driver has a bound on the number of runs, "a bound on unattended board time, not a statement
about the row": 48 for S1b.2. Proposed here: **96 runs** (about 7 hours) for the chain as a
whole, in this order, as in S1b.2:

1. the first run alone (`--max-new 1`), looked at;
2. then the chain until it is complete, halts, or reaches the bound.

At the bound the chain stops and says where it stands; going on needs a word from the owner
and a new bound. Each run is about 3 MB of evidence, mostly its console log; the repository's
history compresses that well (it is 21 MB now with 34 such runs in it).

### What is made of the runs

Three programs, all working from stored results, none reading a database but the grader:

- **The summary over rows** (`s1b3_rows.py`). The chain's list of addresses, cut into rows
  where the register stood still — the device's own mark — and each row described by the
  program that described the row of S1b.2 (columns by the column field, frames in each, minors
  0, 1, 2, …, the next column's minor 0 named after each). For every row: its block type, half
  and row fields; that all of its addresses share them; that the fields change exactly where
  the register stood still and nowhere else. Anything that is not so is listed as unexpected,
  as found. It holds no number of rows, columns or frames.
- **The top row against the stored one**: every address of the chain's first row against
  `row_closed.json` — the same addresses in the same order, the same frames, the same address
  named after each, the standstill and its registers. A difference is listed; it alters
  neither.
- **The grader** (`grade_s1b3.py`), for afterwards: each row by the grader of the row as it
  is; the rows being the database's rows in the database's own order; the frames of block type
  0 in all; and the address named after the last frame against the first frame of the next
  block type in the database — offered as such, since the database lists frames and not what a
  device names. The standstills are listed as not compared.

The order is the one kept so far: **the chain's runs and its summary are saved, judged and
committed first; the grader is run once afterwards**, on a complete chain, and its output
committed whatever it says. If the chain halts, nothing is graded without a word from the
owner about what is to be graded.

### What this step cannot show, said beforehand

- **Most frames may again be all zero.** The carrier design occupies little: in the top row,
  1,754 of 1,932 frames are all zero. Wherever frames are all zero, "the same frame in two
  passes, in a read of three and at the seam" says nothing; the list rests on the register,
  read after every read, and on the reference frame. That is a real limit of a read-only
  census with this design, and S2 (patterns written through user logic) is where content
  begins to discriminate.
- What the places at a row end are. The chain delivers nothing from them.
- Block types 1 and 2: outside the envelope; a separate decision (section 3).

### For the owner

1. **A or B** for the start (A proposed: from `0x00000000` again).
2. **The envelope `0x0..0x007fffff`, one standstill a pass, and the rule that everything not
   provided for halts** — a second standstill in a pass among them.
3. **The bound: 96 runs**, the first run alone and looked at, then unattended to the end, a
   halt or the bound.
4. **The three programs**, and the order: summary and comparison first and committed; the
   grader once, afterwards, on a complete chain only.
5. Whether the summary, the comparison and the grading may follow one another after the chain
   completes (as in section 33), or each waits for a word.

## 39. S1b.3 as built (2026-11-17; host side, nothing on a board yet, no database read)

The owner agreed to section 38 as proposed: the chain starts at `0x00000000` again; the
envelope `0x0..0x007fffff` with one standstill a pass, everything not provided for halting;
a bound of 96 runs with the first run alone; the three programs, the summary and the
comparison committed before the grader is run once on a complete chain. Point 5 had no
proposal of mine beside it; I take the precedent of section 33 — after the chain completes the
summary, the comparison and the grading follow one another, each committed before the next —
and say so here so that it can be overruled before the board.

### What was built

- **The image is unchanged**: `fdc4f07f…9452`, the one of section 37.
- **The set `s1b3`**: `s1b3a`'s set with its starting address given at run time — the one word
  that differs, checked by a test. The run script takes `--start` for it as for `s1b2`, and
  refuses an address outside the envelope (`0x00800000` among them).
- **The chain driver, `s1b2_chain.py`**: the set it drives is now a parameter (`--stage s1b2`
  or `s1b3`; the default is the row's, so the stored chain of S1b.2 is assessed as before, and
  the test that holds it still passes). The bound is the set's: 48 and 96. A step at which the
  register stood still carries that into the chain's list. **No rule of the chain changed.**
- **`host/s1b3_rows.py`** — the summary over rows: the list cut after every frame at which the
  register stood still; each piece described by `s1b2_row.summarize` (the program that described
  the row of S1b.2); for each row its block type, half and row, whether it was walked whole and
  how it ended, the address named after it. Listed as unexpected: columns of a row that do not
  share its fields (`s1b2_row` says so), a standstill after which the address named is in the
  same row, a row whose fields are those of an earlier one, a list that is not a chain of names
  or does not rise.
- **`host/s1b3_top.py`** — the chain's first row against `row_closed.json`: the same addresses
  in the same order, the same frame at each, the same address named after each, the standstill
  at the end and the address gone on to, the same numbers of frames in the columns; and how
  many of the frames compared are not all zero.
- **`host/grade_s1b3.py`** — for afterwards: each row through `grade_s1b2.grade` unchanged; the
  rows against the database's rows of the block type in its order (the top half's by number,
  then the bottom half's); if the chain left the envelope, the frames in all and the address
  named after the last frame against the first frame of the next block type in the database.
  The standstills are listed as not compared. It is the only new file that names the database;
  the two tests that guard that were given its name.
- **The twin** has room for a model of several rows (400 frames, 96 successors, 32 shown
  values). It is test equipment; the image does not contain it.

### On the twin

A made-up device of three rows — 128, 70 and 66 frames, in the top half and in rows 0 and 1 of
the bottom half, each ending as the board's row ended — through the chain on the pretended
board:

- **Complete in five runs**: every address the device names, in order, once; the three
  standstills each met by one run; the device naming `0x00800000` after the last, which is
  never written. No address was written that the device did not name, and nothing was
  delivered from the six places without an address.
- The summary: three rows with their fields, lengths and columns, nothing unexpected.
- A chain taken up again after two runs is the chain run through. A seam that falls on the
  last frame of a row (the next run begins with the standstill) is walked the same.
- **The end of the block type**: without a standstill — complete; with the register standing
  still for longer — the chain halts (`0x800`), and the summary has the last row as not ended.
- **A row of ten frames**: the chain halts with `0x900`, as section 38 said a row shorter than
  a pass would.
- A fault in a run halts the chain, and driving it again leaves it where it halted.
- A row that ends without a standstill is not cut, and the summary lists the change of fields
  inside the piece as unexpected — the chain itself follows what the device names.
- The grader on a made-up database: agrees, and says where a count, a row more, a row fewer
  or the address after the block type differs; a halted chain is graded as far as it went.

### What is not tested

The function that makes a run on the board (`board_runner`) now passes the set's name to the
run script. No test drives a board; a wrong name there would show at the first run — the
chain checks each run's record for the stage — which is why the first run is made alone and
looked at.

### Tests and mutants

23 new tests (358 in all). Four older tests were adjusted to the driver's parameter and the
new set (the list of sets that take a start; the bound 96 among the driver's numbers; a
stand-in for `read_run`; "every other set asks for no standstill"), and two guard tests were
given the new grader's name. A slip, recorded: the checkpoint `33e8f37` was committed by a
command that did not wait for the suite, and those two guard tests were failing in it; the
next commit (`62d0f6a`) put that right. Nothing but the two lists changed.

45 mutants written: 5 in the chain driver, 2 in the run script, 16 in the summary, 11 in the
comparison, 11 in the grader; one older mutant re-anchored (the stage of a run record).
An attempt to run the 45 by themselves first was cut off by a time limit of mine after 32
(all killed) and left its eight scratch copies in the temporary directory; they were removed
by hand. The complete run then served for all of them.

The complete run (`evidence/host_checks/mutants_2026-11-17_s1b3.txt`): 478 mutants (the 433 of
section 36 and these 45), 478 killed, none survived, none BROKEN, none STALE; the unmutated
tree before and the restored tree after both run 358 tests, OK. The temporary directory was
empty afterwards.

### What the tests cannot show

- How long the bottom half is, how many rows it has, and what the device does at the end of
  block type 0. The twin has an end with a standstill, one without, and one where the register
  stands still for longer; the chain completes at the first two and halts at the third.
- That the new image, which has run one walk of 292 records on the board, runs some thousands
  more as cleanly. Each run stops at the first anomaly, and the chain at the first run that
  did not pass.
- Whether most of what is read will again be all zero. `s1b3_top.py` counts the frames that
  are not.

### Proposed for the board

With nothing else running on the host. The chain's directory is
`evidence/s1b3_17A6_<date>/`, with the set kept beside the runs as `expected_s1b3.json`.

1. `s1b2_chain.py --stage s1b3 --dir … --go --max-new 1` — **the first run alone**, from
   `0x00000000`. Looked at: the run record's stage, the judge's verdict, 64 frames, the seam
   address the chain plans next. Committed.
2. `s1b2_chain.py --stage s1b3 --dir … --go` — the chain, unattended, until it is complete,
   halts, or has 96 runs. A U-Boot `reset` (checked) before every run, as always. Its output
   kept; everything committed as it is when it stops, whatever the state.
3. If it is **complete**: `s1b3_rows.py` → `rows.json`, committed; `s1b3_top.py` against
   `row_closed.json` → `top.json`, committed; then `grade_s1b3.py` once → `grade.json`,
   committed whatever it says. The whole suite is run before each commit of a new evidence
   file.
4. If it **halts**, or stops at the bound: the summary is made of what there is and committed
   as that; the comparison of the first row is made if that row was walked whole; **nothing is
   graded**, and nothing is retried or moved aside, without a word from the owner.
5. The record, and stop.

**Before the board:** the owner's review.

## 40. Review of `1140ce6` (2026-11-17): one finding, accepted — the seam did not compare the standstill

**Finding (P2).** The seam between two runs — one frame read by both — was held on three
things: the address, the frame, the address named after it. Since section 36 a step also says
whether the register stood still there, and the seam did not compare that. Two runs can agree
on all three and differ in it: in one the pad alone leaves the register standing and the next
address shows only after the frame is read, in the other the pad alone names it at once. Each
run passes its judge; the chain went on and could report "complete"; and the summary over
rows, which lists a seam frame once — as the earlier run had it — showed nothing unexpected.
The reviewer reproduced it on the twin. Checked against the code, and so it is.

That is the chain failing by its own rule: the seam exists so that two runs have to agree on
one frame, and what the register does there is, at the end of a row, the observation that
matters most.

**Changed.** `s1b2_chain.py`, rule 4: the register stood still at the seam frame in both runs
or in neither; otherwise the run is not accepted and the chain halts, saying which run saw
what. For the stored chain of S1b.2 nothing changes (no step of it stood still; the test that
holds it passes). The summary's taking the seam frame from the earlier run is left as it is:
with this rule the two records of a seam frame agree on everything the summary uses.

Looked at for the same gap and found without it: the judge compares the second pass with the
first record by record, register included; `s1b3a_seam.py` and `s1b3_top.py` both compare the
standstill itself.

**Tests.** One new test (359 in all), both directions, on the twin: a row whose last frame is
a seam, with the device one thing for the run that ends there and another for the run that
begins there — the mark disappears; the mark appears. In each the two runs pass by themselves
and agree on the frame and on the address named; the chain halts at the seam with the reason;
driving it again leaves it halted. Where both runs stood still there, or neither, it completes.

**Mutants.** Three: the comparison removed (which is the code as reviewed) — the new test then
fails in both directions, confirming the reproduction — and the comparison made one-sided
either way. All killed, by that test.

The complete run after the change (`evidence/host_checks/mutants_2026-11-17_s1b3_review.txt`):
481 mutants (the 478 of section 39 and these three), 481 killed, none survived, none BROKEN,
none STALE; the unmutated tree before and the restored tree after both run 359 tests, OK. The
temporary directory was empty afterwards.

## 41. How the mutants are run from here on (owner, 2026-11-17)

Until now the complete set was run after every step and after every change made on review:
some 480 runs of the whole suite, about an hour, during which nothing may run on the board.
The owner asked whether that is necessary. What the mutants are for stands — they show whether
a test fails when the program is wrong, which reading the program cannot show — and so do
their limits: they try only checks that exist. The gap of section 40 was a check that had
never been written; every mutant was killed while it was there, and a review found it.

What was out of proportion was running all of them every time. Agreed:

1. **After a change, the mutants of the files that were changed**, by themselves — minutes —
   together with the check that every mutant's anchor still occurs exactly once in its file.
   The result is waited for before the change is committed.
2. **The complete set at key points only**: a change of substance to the prober (the guard,
   the walk) or to a judge or the chain's rules of acceptance; and before a new image is run
   on the board for the first time.
3. **Programs that only run on the host over stored results** — summaries, comparisons,
   graders: their own mutants once, when they are written. A fault in one of them costs no
   board time and spoils no evidence; it can be run again on what is stored.

A record of a step says which mutants were run and that the complete set was not.

On the time: it is not the compiling. A clean build of the image and the twin takes under
three seconds and happens only where a mutant changes C source (141 of the 481); the hour is
the whole suite, about a minute, once for every mutant whatever file it is in.

## 42. S1b.3 on the board (2026-11-17): halted at run 51 — the result header was not read back

Released by the owner after sections 39 to 41, and run as section 39 proposes: the first run
alone, looked at and committed (`904f668`); then the chain unattended. It halted at its 52nd
run. Everything was committed as it stood (`0834b50`), then the summary of what there is
(`e7c43a6`) and the comparison of the first row. The full account is
`evidence/s1b3_17A6_2026-11-17/RESULT.md`.

- **51 runs accepted**, 14,892 records, no anomaly, no overflow, no interface failure. 3,214
  addresses, `0x00000000..0x00401283`.
- **The first row whole**, 1,932 frames in 56 columns, and **no disagreement with the stored
  row** in any of its addresses, frames (178 of them not all zero), names or column lengths:
  the row read on a second day by the second image.
- **The standstill at `0x1ba9` was crossed in the chain** (run 30), and the walk went on in the
  bottom half: 1,282 frames so far, columns 0 to 36 whole, with the lengths of the first 37
  columns of the first row.
- **Run 51**: the prober reported a clean run on the console; the sixteen-line dump of the
  result header came back with a stretch of characters missing; the run script stopped and
  stored no result; the chain halted. Console losses of this kind happened 71 times in this
  chain while pieces of results were pulled, and each cost one repeat — a piece is checked
  against the board's checksum and pulled again. **The header read has no second attempt.**
- Nothing was graded, nothing retried, nothing moved.

One test assesses the stored chain again from the raw words of its 51 results and holds the
summary and the comparison by their hashes (360 tests).

**Stopped here.** For the owner, two things, neither done:

1. **The header read.** I propose that the run script read the header again when the dump is
   not sixteen whole lines — the same command, at most a few times, every attempt recorded, the
   run stopping as now if none is whole — and likewise for the other short read-only replies it
   depends on (a status word, a checksum). Never for a command that does anything: `go`, a
   write, a save. That is a change to the run script: its tests, the related mutants, a review.
   Without it the remaining runs each carry the chance that stopped this one (once in 52 runs
   here).
2. **Going on.** With the owner's word: the directory of run 51 is renamed, kept and committed
   as what it is (the driver lists such directories as set aside), and the chain makes its
   52nd run again from `0x00401283`, the last frame of run 50, and goes on to the end, a halt
   or the bound of 96 runs. The result of the run that was not read is probably still in the
   board's memory; taking it out by hand would put into the chain a result that did not come
   through the run script, and I do not propose it — the run takes four minutes.

## 43. The run script asks again for a short reply that is not whole (2026-11-18)

The owner's answer to section 42: both points as proposed, the first before the second, and
nothing on the board until the owner says so. This section is the first point. Host only: the
prober, its image (`fdc4f07f…9452`), the judges and the chain are as they were.

**What a whole reply is** (`whole()` in `host/s1a_run.py`). For `md.l A N`: every line of that
dump is there, each at its address, each with its four words (the last with what is left), and
there is no other line of a dump. For `crc32 A B`: U-Boot's line for exactly that range, with
its eight digits. A reply that lost a stretch of characters lacks a line, or a line lacks a
word, or the next line is not at the next address. Any other command is an error in that
function: there is no way to pass one in and have it asked twice.

**What is asked again** (`read()` in `execute()`): the same command, at most five times in all
(`MAX_READS`), when the reply is not whole. Every attempt is among the recorded steps with its
reply as it came; every reply that was not whole is listed in the run record
(`replies_not_whole`). If none of the five is whole the run does what it did before when it
could not read that reply. The places:

| | reply | if never whole |
|---|---|---|
| before `go` | the status word after the clear, and after the PL load | stop; `go` is not sent |
| before `go` | the checksums of the PL design, the parameter block, the prober image | stop; `go` is not sent |
| after `go` | the result header (sixteen lines) | stop; nothing saved (as on 2026-11-17) |
| after `go` | the checksum of the result | stop; nothing saved |
| after `go` | the checksum of the card copy read back | the card copy is not verified: the run fails, the result is still pulled |
| after `go` | the checksum of each piece | stop |
| after `go` | the status word afterwards; the checksum of the image afterwards | a problem: the run fails |

**What is never asked again.**

- A whole reply, whatever it says. A checksum that is not the expected one, a status word with
  the wrong bit: these are findings and stop or fail the run on the first reply, as before.
- Any command that does something: `go`, `mw.l`, `fpga loadb`, `fatload`, `fatwrite`, `loady`,
  `dcache off`. Each is sent once whatever comes back. (`fatload` only reads the card, but it
  writes memory; it stays with the others.)
- The status word read before the PL load, which is recorded and not checked.
- A command after which no prompt came. That is not a reply with a stretch missing; the state
  of the console is not known, and the run stops there as before.

**Two things that are stricter than before.**

- A checksum is taken only from the line for the range asked about. Until now any `==>` and
  eight digits would do.
- The header is accepted by its form when it is read, and is now also **held to the pulled
  result**: the first words of the copy that has the board's checksum must be the header as it
  was read; if not, the run fails with that as its problem. A loss of characters can only make
  a reply shorter, and the rule for a whole dump leaves almost nothing for it to do unseen (a
  word's last digits and the two blanks after it lost, and the characters printed beside the
  words happening to be digits and a blank); this check closes that by content.

`header.bin` is written only from a whole header (before: from whatever words the one reply
had). The stop reads `the result header could not be read whole in 5 attempts`.

**Held against what the board has said so far** (a test, from the run records in `evidence/`):
7,227 checksum replies and 726 dumps of a few words, every one whole by this rule and saying
what the run took from it — and one that is not whole: the header dump of run 51.

**What this does not cover**, and I leave as it is:

- The replies of commands that do something. A loss in the line `… bytes read` of the card
  read-back, in `… bytes written`, or in the prober's own two console lines fails that run —
  after its result was saved, pulled and judged — and a chain halts on it. Short lines; none
  was lost in the 52 runs.
- The chain driver's own check after its `reset` before every run (one status word). If that
  reply is damaged the driver stops before anything is run and leaves no run directory.
- The pull of the pieces is as it was (the board's checksum of the piece decides).

Tests: 373 (twelve new for the run script, one for the stored replies). Mutants: fourteen new
for this change and six older ones moved to the lines as they now read (495 in all, none
stale). Run as section 41 says — the 58 of the run script, all killed
(`evidence/host_checks/mutants_2026-11-18_run_script.txt`); the others were not run.

## 44. Run 51 set aside (2026-11-18); the chain ready to be taken up again, not started

The second point of section 42, as far as it goes without the board.

- `evidence/s1b3_17A6_2026-11-17/halted_at_run51/` now holds what the halt left, moved and not
  altered: the directory `run51`, the driver's `run51.out`, and `chain.json`, `rows.json`,
  `top.json` as made at the halt — the files that going on would have written over. The chain
  lists the directory as set aside.
- The chain as stored: 51 runs, each accepted, **to go on with run 51 from `0x00401283`**
  (the last frame of run 50; the device named `0x00401284` after it).
- The test of the stored chain was split in two: one holds the halt as it was (the state then,
  the 51 runs as they are judged now, the summary and the comparison made again and equal to
  the stored ones, by hash); one holds the chain as it stands, and is the one to change when
  the chain has gone on. 374 tests. No program was changed in this step, so no mutant was run.

**On the board, when the owner says so, and not before:**

1. The devices checked; nothing else running on the host.
2. `s1b2_chain.py --stage s1b3 --dir evidence/s1b3_17A6_2026-11-17 --go`, unattended: a
   `reset`, checked, before every run; run after run to complete, a halt, or the bound of 96
   runs (45 more at most, about four minutes each).
3. Whatever it ends in: committed as it stands first. Then the summary over rows; then the
   first row against the stored one; and only if the chain is complete, the grader once —
   each committed before the next, as section 39 has it.
4. A halt is reported and nothing is retried or moved without the owner.

## 45. S1b.3 on the board (2026-11-18): the chain complete; block type 0 graded — nothing differs

Released by the owner after sections 43 and 44. The full account is the last sections of
`evidence/s1b3_17A6_2026-11-17/RESULT.md`.

- **The chain**: taken up from `0x00401283`, eleven more runs (51 to 61), all accepted; 62 in
  all, 17,908 records, no anomaly, no overflow, no interface failure. No short reply came back
  not whole, so the second attempt of section 43 was never used on the board. Committed as
  stored (`887b479`).
- **The end**: at `0x00401ba9` the register stood still after the pad alone and showed
  `0x00800000` after the frame — outside the envelope; not read. Complete.
- **The list** (`rows.json`, `9615af8`): 3,864 addresses; two rows, top half row 0 and bottom
  half row 0, 1,932 frames and 56 columns each, the columns of the same lengths one for one;
  a standstill at the end of each row; nothing unexpected.
- **The first row against the stored one** (`top.json`, `57778ff`): no disagreement.
- **The grader** (`grade.json`, `06fa08e`), once, after those commits: nothing differs from
  prjxray-db — the columns and their frames in both rows, the rows of block type 0 and their
  order, 3,864 frames, and the two addresses named after the rows (`0x00400000`,
  `0x00800000`) against the first frames of the next row and of block type 1. Not compared:
  the standstills.

374 tests. No program was changed on this day after section 43; no mutant was run.

**S1b.3 is done. Stopped here.** What comes next is the owner's: block type 1 from
`0x00800000` (not read so far; the walk's rules were made on block type 0 and nothing says
they hold there), or something else. I have not started on either.

## 46. S1b.4a — proposal: one run into block type 1 (2026-11-18; a proposal, nothing built, nothing on a board)

The owner asked for a proposal for block type 1. This proposes one run, not a chain: the
walk as it is, started once at the address the device named after block type 0. Nothing of it
is built. Section 3 made this "a separate decision" with one condition — "the carrier design
must be checked for block RAM first" — and that check is the first part below.

### What is known and what is not

Known, from the device: after the last frame of block type 0 it names `0x00800000`. By
UG470's layout of the address (table 5-24) that is block type 1, "block RAM content", top
half, row 0, column 0, minor 0. Nothing has been read there by this project.

Not known, and none of it assumed below:

- whether a read there behaves as in block type 0 at all: a pad of one frame, the register
  after the pad alone, the address going on by itself through a read of three frames;
- whether what is read is the same twice;
- how long a column is, where a row ends and what the register does there, how many rows
  there are, what the device names after the last frame;
- whether going to and fro between the reference frame (`0x0b99`, block type 0) and block
  type 1 needs anything the walk does not do.

What the official documents say (the only outside source allowed): UG470 lists block-RAM
content among what a readback reads; and of its background readback check it says "Block RAM
content is skipped during readback to avoid interfering with user functions". It does not say
what the interference is. The project's proposal (section 10) has the same warning and one
report of block-RAM readback failing in a finished system.

### The carrier design and block RAM

What I may use is the source of our own design. The design loaded in every run is
`carrier.bit` (sha256 `8c3369e8…0b8a`), built in zynq-fabricmap; its build record
(`gate_runs/claimb_round1_carrier_2026_08_13_erratum006/carrier_build.json`) names that hash,
the source commit `e4ffb009` and the hash of every source file, and the six Verilog files in
that checkout have those hashes. In them:

- **No block-RAM primitive is instantiated**, and no FIFO primitive.
- Five memories are declared. Two carry `ram_style = "distributed"` (101×32 and 15×32 bits).
  **Three carry no attribute**: two small read-only tables (64×6 and 6×64 bits) and one array
  of 5×32 bits. They are tiny, and synthesis ordinarily builds such arrays from LUTs; but
  **the source does not settle where they were put.**

What would settle it is the build's own utilisation or cell list. That is a Vivado report,
and the project's rule excludes those ("no Vivado report file is used, not even for
grading"). I have not opened one. So the honest state is: *no block RAM by intent; not
proven absent.*

I propose to go on without settling it, because the step does not depend on the answer:

- **Who could be interfered with.** Only the carrier's own logic. Nothing uses the carrier
  during a run: the prober reads no PL register (a test holds that), the host does not touch
  it, and every run begins with a fresh load of the design. If reading these frames disturbs a
  block RAM of the carrier, nothing here relies on what it held.
- **What could reach us instead** is one of two things, and both are provided for: content
  that is not the same twice (an anomaly: the run stops and is stored), or the configuration
  interface doing something not seen before (an error bit, a transfer that does not finish,
  the PL no longer configured: the run stops and is stored; the next run loads the design
  again; if U-Boot itself does not answer, the board is switched off and on — proposal section
  10 counts none of that as damage).

The alternative is for the owner to allow one look at that build's utilisation, for this
question only. I do not think it is needed, and it would be the first time a Vivado report
is read in this project.

### The run

One parameter set, `s1b4a`: the set `s1b3` with two words changed.

| | `s1b3` | `s1b4a` |
|---|---|---|
| start | given by the chain | `0x00800000`, fixed |
| envelope | `0x00000000..0x007fffff` | `0x00000000..0x00ffffff` |
| everything else | | the same: two passes, at most 64 frames a pass, one standstill a pass, the reference frame `0x0b99` at most 16 frames apart, the wait that touches no memory |

- **The image is unchanged** (`fdc4f07f…9452`). The prober is not built again.
- **Why the envelope begins at 0.** The prober refuses a parameter block whose reference frame
  is outside the envelope, and the only frames with a known answer are in block type 0. The
  walk cannot use the lower part: it goes only to addresses the device names, and stops if one
  is not above the one before. Its upper end is the end of block type 1 by the address layout:
  an address at or above `0x01000000` is never written to the register.
- **Judged** by the judge of a run of a chain, as it is (a run that begins above the known
  frames is not failed for not passing them). No rule is changed for this run.
- **One run**, after a `reset`, checked, as before every run. About four and a half minutes.

Could the first look be smaller — eight frames instead of 64? It could; one word. I propose
64: what is exposed to an unknown is the first read, not the sixty-fourth, the walk stops at
the first thing it does not expect, and 64 is the run every test and every board run so far
was made with.

### What may come out, said beforehand

1. **It passes**: 64 frames from `0x00800000`, both passes alike, ended at the limit — or
   fewer, ended by leaving the envelope or by whatever a column or row end does there, if
   that is something the walk provides for. Then the walk works in block type 1, and the next
   proposal is the chain over it (below).
2. **It stops before the first read there** (a gate, the first reference read): nothing about
   block type 1; reported as that.
3. **It stops at an anomaly in block type 1**: a pad that is not zero, a register that does
   not move as the walk expects, a frame that differs between two reads or between a single
   read and a read of three, a reference frame no longer as known. That is a finding about
   block type 1. It is stored, committed and reported; the walk is not adjusted to it in the
   same step. What is to be looked at then would be proposed separately, as the end of the
   row was (section 29).
4. **The interface fails** (an error bit, a transfer that does not complete, the PL no longer
   configured). Stored, committed, reported, and nothing more is run until the owner says so.

In no case is anything retried, and nothing is graded in this step: one run of 64 frames is
not a list. The run's addresses are laid out by the summary of a row as far as they go.

### What this step cannot show

- **Content.** If the carrier holds no block RAM with content, every frame will again be all
  zero, and "the same twice" says nothing; the list rests on the register. If frames are not
  all zero, that is the first thing the device says about the question above — and still no
  proof either way.
- Where block type 1 ends, or what follows it. UG470 names a block type 2; nothing is read
  there, and nothing at or above `0x01000000` in any case.
- That reading these frames is harmless to a design that uses block RAM. Nothing here uses
  the carrier, so nothing here can see that.

### What would follow, not proposed yet

If the run passes: the chain over block type 1, with the set's start given at run time. One
rule of the chain has to change for it, and that is why it is not folded into this step: a
chain is complete only if every frame with a known answer in the envelope was walked by one
of its runs (section 27), and a chain that begins at `0x00800000` never walks `0x0b98`–
`0x0b9a`. That is a change to the chain's acceptance rules — a proposal, a review and the
complete set of mutants (section 41).

Also worth saying: S2 (finding LUT RAM through patterns written by user logic) does not need
block type 1. The census of S1b does: block type 0 is 3,864 of its frames, not all.

### What has to be built for this step

Host only. The parameter set (generated and pinned by the test that pins the others), its
entry in the run script, tests against the twin with a pretended stretch of frames at
`0x00800000`, the mutants of those lines. No image, no judge, no chain rule: by section 41,
the mutants of the changed files and the check of the anchors.

### For the owner

1. **The carrier and block RAM**: go on as proposed (none instantiated; three tiny memories
   not settled by the source; the step does not depend on it) — or allow one look at the
   build's utilisation first.
2. **The set `s1b4a`**: `s1b3` with the start `0x00800000` and the envelope
   `0x00000000..0x00ffffff`; the image unchanged; one standstill a pass allowed as in `s1b3`.
3. **64 frames** for the first run, or fewer.
4. **One run; whatever it ends in is stored, committed and reported; nothing retried, nothing
   graded**; the chain over block type 1 is a later proposal.

## 47. S1b.4a as built (2026-11-18; host side, nothing on a board yet)

The owner's answers to section 46: all four as proposed — go on without settling whether the
carrier holds a block RAM; the set as proposed; 64 frames; one run, stored, committed and
reported whatever it ends in, nothing retried, nothing graded.

### What was built

- **The parameter set `s1b4a`** (`build/prober/expected_s1b4a.json`, written by the test that
  writes the others): the set `s1b3` with word 4 = `0x00ffffff` (the envelope's upper end) and
  word 16 = `0x00800000` (the start). The 30 other words are the same. The image it names is
  `fdc4f07f…9452`: **the prober was not built again.**
- **Its entry in the run script**: judged by the judge of a run of a chain; the start is fixed
  (`--start` is refused for it).
- **`host/s1b4a_layout.py`**: lays one run out with the program that lays out a chain's rows —
  the addresses cut where the register stood still, block type, half and row of each piece,
  its columns and their frames — as far as the run went. It calls an end reached only if the
  judge passed the run and both passes left the envelope. It counts the frames that are not
  all zero and the different contents, and says so when every frame is alike. A run that did
  not pass is laid out too, with a note that this is not a finding. It holds no number of any
  part and reads no database.

No change to the prober, to a judge, to the chain or to the rules of the run script.

### What the twin was made to do

Nothing is known of block type 1 on the device, so the shapes are invented (columns of ten
and of five frames, a row ending after fifteen) and none of them is a prediction:

| pretended | the run |
|---|---|
| a stretch of frames with no end in reach | PASS, 64 frames, both passes at the limit |
| every frame all zero | PASS; the layout says the content tells nothing |
| three columns | PASS, the names followed across both changes of column |
| a row that ends as the rows of block type 0 did | PASS, the standstill crossed, the list in two pieces |
| the device names `0x01000000` — after a standstill, and without one | PASS, both passes "left the envelope"; that address is never written |
| the device names an address in block type 0 | stopped (`0x800`): a name that is not above is not followed, although the envelope begins at 0 |
| an address that names itself for good | stopped (`0x800`) |
| a pad not zero, a short read, a frame that differs, an error bit, no end of transfer, PL lost, a register off by a bit | stopped at that read; the result stored whole and judged FAIL |

In every one of them the only addresses written to the register are the reference frame and
addresses the device had named, all inside block type 1.

### Tests and mutants

395 tests (21 new). Ten new mutants: two for the run script's entry, eight for the layout
program; 505 in all, none stale. Run as section 41 says — those of the changed files: the 60
of the run script and the 8 of the layout program, all killed
(`evidence/host_checks/mutants_2026-11-18_s1b4a.txt`); the others were not run. One assertion
was added to a test after that run (the addresses written in the runs with a fault): it can
only make the suite stricter.

### On the board, when the owner says so, and not before

1. The devices checked; nothing else running on the host.
2. A `reset`, checked for the usual fresh prompt.
3. One run: `s1a_run.py --stage s1b4a --go --out evidence/s1b4a_17A6_<date>/run`. About four
   and a half minutes.
4. Whatever it ends in: the directory committed as it stands, with the set and the image
   beside it. Then the layout (`layout.json`), a record, and the report.
5. **If it does not pass** — a stop, an anomaly, an interface failure, a board that does not
   answer: that is what is reported. Nothing is run a second time, and nothing further is run
   at all until the owner says so.

## 48. S1b.4a on the board (2026-11-18): PASS — the walk works at `0x00800000`

Released by the owner after section 47. One run, 16:48–16:52 UTC, after a pre-check and a
`reset`; stored and committed as it came (`ed538c8`) before anything was made of it. The full
account is `evidence/s1b4a_17A6_2026-11-18/RESULT.md`.

- **PASS.** 292 records, no anomaly, no overflow, no interface failure; the result is the
  board's, the card copy verified; the PL configured and no error bit afterwards.
- **64 addresses, `0x00800000..0x0080003f`**, each the one the device named after the one
  before: block type 1, top half, row 0, column 0, minors 0 to 63. Both passes ended at the
  limit, told `0x00800040`. The column has at least 64 frames; none of block type 0 has more
  than 42.
- **The register behaves there as in block type 0**: the pad alone names the next number, a
  read of three goes on by itself, no standstill in these 64.
- **The reference frame** in block type 0 was as known at each of its 14 readings in between.
- **Every frame is all zero.** The content tells nothing; the addresses rest on the register.
  Nothing is learnt about whether the carrier holds a block RAM.
- Of the four outcomes section 46 set out beforehand this is the first.

396 tests (one new: the stored run judged again from its raw words, the layout made again).
No program was changed after section 47; no mutant was run.

**Stopped here.** Nothing was graded and nothing further was run. What section 46 named as
the next proposal, if this passed, is the chain over block type 1 — with one rule of the
chain to change (a chain is complete only if every frame with a known answer in its envelope
was walked, and one that begins at `0x00800000` never walks them), which makes it a change to
the chain's acceptance rules: a proposal, a review, the complete set of mutants. I have not
started on it.

## 49. S1b.4 — proposal: the chain over block type 1 (2026-11-18; a proposal, nothing built, nothing on a board)

The walk works at `0x00800000` (section 48). This proposes the chain that goes on from there
to the end of block type 1, the one rule of the chain that has to change for it, what is made
of the runs, and how that is graded. Nothing of it is built.

### What is known and what is not

Known, from the device: 64 addresses from `0x00800000`, one column begun and not ended, the
register behaving as in block type 0, every frame all zero. Not known: how long that column
is, how many columns a row has, where a row ends and what the register does there, how many
rows there are, and what the device names after the last frame — or whether it names
anything above. No number of any of these is assumed below.

### The rule that has to change

When a run leaves the envelope, the chain counts for itself whether every frame with a known
answer **inside the envelope** was walked by one of its runs; if not, it halts instead of
being complete (section 27). That rule was made deliberately, and section 27 says of it: "a
chain begun above the known frames cannot be complete".

The chain over block type 1 is such a chain. Its envelope begins at 0 — the prober wants the
reference frame inside it, and the only frames with a known answer are `0x0b98`–`0x0b9a` — and
it begins at `0x00800000`. As the rule stands it would walk block type 1 to its end and then
halt for three frames it was never meant to walk.

**Proposed: the chain asks for the known frames from its own first address on** — every frame
with a known answer whose address is at or above the starting address of the chain's set, and
inside the envelope. Nothing else in the chain's rules changes.

- For the two chains there are (`s1b2`, `s1b3`) the first address is 0, the bottom of their
  envelope: the rule asks of them exactly what it asked. The stored chains are assessed again
  by the tests and must come out as they did.
- It is the rule the judge of a run already has ("only for a known frame at or above its own
  start"), now for the chain as a whole.
- What section 27 guarded against stays guarded: a run that goes past a known frame without
  reading it is failed by its judge, and a chain that leaves the envelope without one of the
  known frames at or above its first address is halted by its own count.
- What is given up, said plainly: "begun above the known frames" no longer keeps a chain from
  being complete. What a set's first address is, is fixed by the test that writes the set;
  for `s1b4` it is the address the device named after block type 0, and a test holds it to the
  stored result.
- **For this chain the rule then asks for nothing**: there is no frame with a known answer in
  block type 1. Its "complete" rests on what every run's judge holds — the register after
  every read, two passes alike, every frame once more in a read of three, the reference frame
  as known at most 16 frames apart — on the seams, and on both passes of the last run leaving
  the envelope. Not on content, if the frames go on being all zero.

This is a change to the chain's acceptance rules: by section 41, the complete set of mutants
before anything runs on the board.

**The other way, without a rule change (B):** one chain from `0x00000000` again, with the
envelope `0x00000000..0x00ffffff`, through block type 0 and on into block type 1. The known
frames are walked, the rule holds as it is, and the list of both block types is one chain's.
It costs the 62 runs of block type 0 a third time — about four and a half hours of board time
that say nothing new about block type 1 — and a bound well above 96. It would also cross from
block type 0 into block type 1 within one pass, which no run has done. What it would add
about block type 0 is a second walk of its bottom row (walked once so far; the top row twice,
by two images) of a list that was graded with no difference. I propose the rule change (A).
B remains possible later, as a census in one piece, if that is wanted.

### The chain

The chain driver as it is, with a parameter set of its own.

- **The set `s1b4`**: the parameter block of `s1b4a`, word for word — envelope
  `0x00000000..0x00ffffff`, two passes, 64 frames a pass, one standstill a pass, the reference
  frame `0x0b99` — with the start given at run time by the chain. The image unchanged.
- **It starts at `0x00800000` again.** The first run walks the 64 addresses of section 48 a
  second time (four minutes), and they are held against that stored run.
- **It goes on** after a run that ended at the limit; **it is complete** when both passes of a
  run end because the device named an address above the envelope — after a standstill or
  without one. No address at or above `0x01000000` is ever written to the register.
- **It halts** on anything else, as now: a second standstill within a pass; a standstill one
  more step does not resolve; an address named that is not above the one before — which is
  what the end of block type 1 may turn out to be, since block type 0 ended by naming the
  first address of the next block type and nothing says the last one does the like; any
  anomaly; a seam that does not match. A halt is stored, committed and reported, and what
  there is by then is summarised as that.
- **The bound: 48 runs** (about three and a half hours), as for S1b.2: a bound on unattended
  board time, not a statement about the part. At the bound the chain stops and says where it
  stands; going on needs the owner's word.
- **The order on the board**, as for S1b.3: the first run alone and looked at; then
  unattended to the end, a halt or the bound.

### What is made of the runs

- **The summary over rows**: the program of S1b.3 (`s1b3_rows.py`) as it is, told which set's
  chain it reads. It holds no number of rows, columns or frames.
- **The first run against the stored run of S1b.4a**: every address that run walked — the same
  address in the chain's list, the same frame, the same address named after it. A difference
  is listed and alters neither.
- **The grader**: `grade_s1b3.py` as it is. It was written for "the block type of the rows it
  is given" and takes block type 1 without change: each row's columns and their frames, the
  rows in the database's order, the frames of the block type in all, and the address named
  after the last frame against the first frame of the next block type — if the database lists
  one; if not, that is listed as not compared. Tests with a made-up database of block type 1
  are added; the real one is not opened.

The order kept so far: the runs and the summary are stored, judged and committed first; the
grader is run once afterwards, on a complete chain, and its output committed whatever it
says. If the chain halts, nothing is graded without a word from the owner.

### What this step cannot show, said beforehand

- **Content, most likely.** If every frame is again all zero, the whole list of block type 1
  rests on the register and on the reference frame. That is a limit of a read-only census
  with this design, and the record will say it of every row.
- What a row end of block type 1 is, beyond what the walk's one rule for a standstill takes
  in. If it is something else the chain halts there, and that is looked at separately.
- What follows block type 1. Whatever is named above the envelope is named, not read.
- Whether the carrier holds a block RAM, and whether reading these frames disturbs one.

### What has to be built

Host only; the image is not built again.

- the chain's rule, with tests: the stored chains unchanged; a chain begun above the known
  frames complete where nothing known lies at or above its start, and halted where something
  does and was not walked;
- the set `s1b4` and its bound; the summary told which set; the comparison with the stored
  run; tests of the grader on block type 1;
- **the complete set of mutants**, before the board.

### For the owner

1. **A or B**: the rule change and a chain from `0x00800000` (A, proposed) — or no rule
   change and one chain from `0x00000000` through both block types (B, four and a half hours
   more).
2. **The rule as worded**: the chain asks for the frames with a known answer at or above its
   set's starting address, inside the envelope.
3. **The set `s1b4`, the bound of 48 runs**, the first run alone and looked at, then
   unattended.
4. **The summary, the comparison with S1b.4a's run, the grader as it is**; summary and
   comparison first and committed, the grader once on a complete chain — and whether these may
   follow one another when the chain completes, as in S1b.3, or each waits for a word.

## 50. S1b.4 as built (2026-11-18; host side, nothing on a board yet, no database read)

The owner's answers to section 49: all four as proposed — the rule change and a chain from
`0x00800000` (A); the rule as worded; the set `s1b4`, a bound of 48 runs, the first run alone
and looked at; the summary, the comparison with S1b.4a's run and the grader as it is, in that
order, following one another when the chain completes as in S1b.3.

### The rule

`s1b2_chain.assess`, one line: when a run leaves the envelope, the frames with a known answer
the chain asks for are those whose address is **at or above the starting address of the
chain's set** and not above the envelope's upper end. Before, it was "not below the
envelope's lower end". Nothing else in the chain changed.

- The sets of the two chains there are begin where their envelopes do (a test holds that), so
  the rule asks of them what it asked; and the two stored chains, assessed again from their
  raw words, come out as they are stored: S1b.2's halted at its 31st run, S1b.3's complete
  with 62.
- On written-out runs: a chain beginning at an address is asked for a known frame at that
  address and for every one above it in the envelope — walked, complete; one not walked,
  halted, also when it lies below the start of the chain's last run — and not for one below
  its first address or above the envelope.

**Two older tests say something else now**, and that is the change itself:

- "a chain begun above the known frames cannot be complete" is now "a chain is asked for the
  known frames from its first address on": the same made-up chain, begun in the column after
  the known frames, is complete. Beside it: one begun at the last known frame is asked for
  that frame and walks it.
- In the test of the case found in the review of section 27, the last part — the rest of the
  row, run as a chain of its own from above the known frames — used to be halted by the
  chain's count and is now complete. The first part is as it was: the run that goes past the
  known frames is failed by its judge and the chain halts there. So of the two things mended
  in section 27, the judge's still catches that case on the twin; the chain's own count is now
  shown only on written-out runs, where judges are not asked.

### The rest

- **The set `s1b4`**: the parameter block of `s1b4a` word for word (a test compares them); the
  run script takes its start at run time; `--stage s1b4` in the chain driver, bound 48. The
  image is `fdc4f07f…9452`, unchanged.
- **`s1b3_rows.py <chain directory> [<set>]`**: told which set's chain it reads (`s1b3` if
  none is named). The summary itself is as it was. For this chain it lists the three known
  frames as not walked, which is so.
- **`host/s1b4_first.py`** (new): a stored run held against the chain's list — every address
  of that run in the list, the same frame, the same address named, a standstill in both or in
  neither; and between the first and the last of them the list is that run's, none more, none
  fewer, in order. How many of those frames are not all zero. It holds no number and reads no
  database.
- **The grader** is untouched. Given block type 1 with a made-up database it compares the
  columns and their frames, the rows in the database's order and the frames in all, and lists
  the address named after the last frame as not compared when the database has no block type
  after this one.

### What the twin was made to do

A made-up block type 1 of three rows (two of the top half, one of the bottom; 100, 66 and 90
frames in columns of lengths no part has), each row ending as the rows of block type 0 did on
the board, and `0x01000000` named after the last:

- the chain walks all 256 addresses in five runs and is complete; no address is written to
  the register but the reference frame and addresses of block type 1;
- the summary gives the three rows, their columns, three standstills, and the end;
- an end where the register stands still for good halts the chain, and the summary of what
  there is says so; the bound stops it where it stands;
- the chain's first 64 addresses against a run of the set `s1b4a` on the same device: no
  disagreement; and each way the two can differ is listed when it is made to happen.

### Tests and mutants

419 tests (23 new in `tests/test_s1b4.py`; five older ones changed — the two above, and three
that list the sets with a start given at run time, the bounds, and the sets with a standstill
allowed). 18 new mutants and two older ones moved to the lines as they now read: 523 in all,
none stale. **The complete set was run**, as section 41 asks for a change to the chain's
acceptance rules: 523 of 523 killed, none survived, none broken, the suite whole again
afterwards (`evidence/host_checks/mutants_2026-11-18_s1b4.txt`).

### On the board, when the owner says so, and not before

1. The devices checked; nothing else running on the host.
2. The first run alone: `s1b2_chain.py --stage s1b4 --dir evidence/s1b4_17A6_<date> --go
   --max-new 1`. Looked at, committed.
3. Then the same without `--max-new`, unattended: a `reset`, checked, before every run; to
   complete, a halt, or the bound of 48 runs.
4. Whatever it ends in: committed as it stands first. Then `rows.json`; then the first run
   against S1b.4a's stored run; and only if the chain is complete, the grader once — each
   committed before the next.
5. A halt is reported; nothing is retried or moved, and nothing graded, without the owner.

## 51. Review of `b97dad9` (2026-11-18): one finding, accepted — a word taken for a set

**Finding (P3).** `s1b3_rows.py` checked its arguments in one expression: the last word had
to be either the directory or one of the sets a chain is driven with. That was meant to cover
the call with no set named; it also let any third word through that was spelled like the
directory. `s1b3_rows.py s1b4a s1b4a` then ended in a `KeyError` and exit 1 instead of the
usage text and exit 2. Reproduced here, and so it is. The commands of section 50 are not
touched by it: there the directory and the set are not the same word.

The test of that command line had tried a word that is not a set only with a directory of
another name, which is why it did not show.

**Changed.** A third word, when there is one, is looked up among the sets by itself. The test
now also calls the program with the same word twice — one that is another stage's set, one
that is nothing — from inside the directory, and asks for exit 2 and nothing on stderr; on
the program as it was, it fails.

**Not changed:** the rule of section 50, the set, the image, the other programs. The reviewer
confirmed the rest: the rule takes the set's own first address, the stored chains stand as
before, `s1b4` is `s1b4a` word for word, the image is the one stored with the runs.

419 tests (none new; one made stricter). One new mutant — the check put back as it was — and
one moved to the line as it now reads: 524 in all, none stale. Run as section 41 says: the 19
of the summary program, all killed (`evidence/host_checks/mutants_2026-11-18_s1b4_review.txt`);
the others were not run, the complete set having been run on `b97dad9`, which this does not
touch beyond that one line. Nothing was run on the board.

## 52. S1b.4 on the board (2026-11-18): the chain complete; block type 1 graded — nothing differs; two things not explained

Released by the owner after the review of sections 50 and 51. The record is
`evidence/s1b4_17A6_2026-11-18/RESULT.md`; this section is its short form and what is left
open by it.

**What was done, in the order of section 50.** The devices checked; the first run alone,
looked at, committed (`34a4874`); the chain unattended, 20 more runs, a `reset` before each;
its result committed as it stood (`245b25b`); the summary over rows (`25ef37f`); the stored
run of S1b.4a against it (`7491ad5`); the record, written before the grader was run
(`9e12785`, a count corrected in `25637da`); the grader once (`d29fcf9`). Nothing was halted,
retried or moved. The new second attempt at a short reply was never used.

**What the device said.**

- Block type 1: 1,280 addresses, `0x00800000..0x0080027f` and `0x00c00000..0x00c0027f` — the
  top half and the bottom half, row 0 each, five columns of 128 frames each, minors 0 to 127.
- The register as in block type 0, with a standstill at the end of each row; the walk and the
  chain needed nothing new.
- After the last frame the device names `0x01000000`: by the fields of the address, block
  type 2. Above the envelope; named, not read.
- Graded against prjxray-db: nothing differs. With block type 0 that is 5,144 addresses.

**Seen and not explained** (in full in the record; found before the grader was run):

1. The 512 frames of columns 0 and 1 are all zero. The 768 frames of columns 2, 3 and 4 all
   hold the same content: ten words of `0x00020000`, every tenth word from word 4, the middle
   word passed over. The same at every reading.
2. In every run, from the first read of a frame in columns 2 to 4 on, `devcfg.INT_STS` shows
   bit 5 (`50033024` instead of `50033004`), which UG585's register reference names
   `PCFG_SEU_ERR`: "triggers when PL detects POST_CRC or ECC error". The read of the pad
   alone at the same address does not show it; the runs that stay in columns 0 and 1 never
   show it; no run of this project had shown it before. It is not among the bits the prober
   and the judges treat as errors, so nothing stopped; `SEU_EN` is clear, so the PS does
   nothing about it; the reference frame read as known afterwards in every run. The prober
   does not clear the bit, so whether every such read raises it cannot be seen.

Neither changes the list of addresses. Both bear on what comes later: S2 reads LUT RAM back
while a design runs, and the block-RAM columns were always to be approached last (proposal,
section 10).

**What the tests hold.** One new test in `tests/test_board_evidence.py` (420 in all): the 21
runs judged again from their raw words against the set kept with them, the summary and the
comparison made again, the stored files by their hashes, and both findings above as the
stored records have them — the content by column, and the bit from exactly the first read of
a frame in columns 2 to 4 in each run. No program was changed, so no mutants were run.

**Open, for the owner — nothing of it has been begun.**

- Block type 2: whether to read into it, and how. The walk's rules were found in block type 0
  and held in block type 1; nothing says they hold there. A first step would be one run, as
  S1b.4a was.
- The status bit: whether to look into it now (which read raises it, whether it can be
  cleared, whether the design is disturbed) or to leave it recorded until S2 needs the
  answer. The judges do not report it at present; they could, without treating it as an error.
- The frame census as one document beside the schema (proposal, section 4). With block types
  0 and 1 walked and graded there is now something to put in it.

## 53. What is not understood so far (2026-11-18): an account, with what is known and what is guessed kept apart

Written at the owner's request after S1b.4. Three things are taken one by one — the two
findings of section 52 and the overflow of sections 15 to 22 — and then everything else that
is not clear is listed. For each: what was observed; what the official documents say; a
guess, marked as one. **The guesses rest in part on general knowledge of this device family.
They may stand in this document. They go into no program and no judge, and nothing is
concluded from them.**

### A correction first

On 2026-11-18 two short texts (the index at the head of this plan and the record of S1b.4)
said "UG470 says block-RAM content is skipped in readback". That sentence of UG470 stands in
its chapter on the background readback check and is about that check. Of a readback that is
asked for, UG470 says that it reads "all configuration memory cells, including the current
values on all user memory elements (LUT RAM, SRL, and block RAM)". Section 46 had both in
their place. Both texts were corrected (`af96955`).

### 1. Columns 2 to 4 of block type 1: 768 frames with one content

*Observed.* Ten words of `0x00020000` in each frame, at words 4, 14, 24, 34, 44, 55, 65, 75,
85, 95 of 101; the same in all 768 frames and at every reading. The 512 frames of columns 0
and 1 are all zero.

*Guess.* A frame is 50 words, one word, 50 words. The ten bits are then one in every unit of
ten words, ten units to a column and row; three columns, two rows: 60 units. If the part has
60 block RAMs — a number I believe to be the datasheet's and have not checked in a document
here — this is one bit for each block-RAM site, repeated in each of the 128 frames, and
columns 0 and 1 are addresses with no RAM behind them. It does not look like stored content:
the carrier's source instantiates no block RAM, and content would not be the same at one
place in 128 frames.

*What would test it without a database.* What S2 does for LUT RAM, done for block RAM: user
logic writes a known pattern, readback finds it. The proposal puts block RAM last. Not now.

### 2. `PCFG_SEU_ERR` from the first read of such a frame

*Observed* (section 52): only a read that delivers a frame of columns 2 to 4 shows it; the
pad alone does not; block type 0 never did, its 428 frames that are not zero included.

*The documents.* UG585, register reference: bit 5 of `devcfg.INT_STS`, write one to clear,
"triggers when PL detects POST_CRC or ECC error". UG470, chapter 8, of the background check:
"after a frame with erroneous bits is read, ECCERROR is asserted".

*Guess.* The frame ECC logic looks at every frame that is read back, whoever asked for it.
The frames of block type 0 carry check bits the tools computed, and pass. A frame of zeros
passes by itself. The 768 frames have ten bits set and a middle word of zero: no check can
come out right, and the error is flagged. That one guess accounts for all four observations.
If it is right, the flag is not an upset; it is what reading a frame does whose check bits do
not cover its content.

*What follows from it, if it is right.* S2 reads LUT RAM frames after user logic has changed
them, and S4 writes frames back changed: in both the check bits no longer fit, and the bit
would then show as a matter of course. That is a test S2 makes without being asked to. Until
then: the bit must stay out of the error mask but must be seen; and `SEU_EN` in
`devcfg.CTRL` must never be set, since with it this bit locks the PS down.

### 3. The receive-FIFO overflow (sections 15 to 22)

*Observed.* With the data cache off, a polling loop that stores two words to the stack while
a transfer runs overflows the FIFO in about one read in a hundred — when those words lie at
offsets 24 and 28 of a 32-byte block, and in no read when they lie at 0 and 4. Only those two
places were tried. With a wait that stores nothing: 119 runs, 33,515 records, no overflow.

*The documents.* UG585: the PCAP side has no flow control; when the FIFO overflows "incoming
read data from PCAP will be dropped and the DEVCI DMA may enter an unrecoverable state".
After an overflow the status also showed the AXI write time-out bit.

*What can be said.* An overflow means the DMA's writes to memory were held up for a moment,
and the one thing that differed was the processor writing to memory at the same time.

*Not known.* Why the end of a 32-byte block, and why one read in a hundred. Directions, none
with evidence: how the DDR controller arbitrates between its ports; whether the level-2
cache is in fact on (only SCTLR was ever recorded); the alignment of the DDR's bursts.

*How much it matters.* The rule "nothing is stored while a transfer runs" is held by a test
of the machine code, and the count above is large. Low priority.

### 4. Everything else that is not clear

- **The end of a row.** The step at which the register stands still, and the two frames of
  zeros a longer read delivers there (section 31). A guess: filler between rows. Not tested.
- **Whether readback disturbs the running design** (proposal, question 5). Known only: the
  reference frame and the status did not change. What the design does was never checked.
- **Whether what is read is what the PL holds.** S1b never claimed it (section 3). S2.
- **Addresses the device does not name.** The walk goes only where it is pointed. Nothing
  outside that was read; nor block type 2 or above.
- **The carrier's three small memories** without an attribute (section 46): the source does
  not say whether they became block RAM. It bears on item 1.
- **`a802000a` after a `reset`, `a802000b` after power-on.** Bit 0, which UG585 calls
  `PCFG_INIT_NE_INT`. Presumably an edge only power-on produces. Not tested.
- **The console loses characters** — 23 of 1,402 pieces had to be pulled again in S1b.4.
  The cause (adapter, USB forwarding, host) is not known; it is worked around.
- **Not begun:** the AXI path from the returning program to user logic (question 9), the
  readback mask, GCAPTURE, the bit order of shift registers (questions 4 to 7).

*One thing can be closed.* Earlier records call bit 16 of the status "set by the first
readback, not explained". UG585's register reference: bit 16 is "Rx FIFO level >= threshold",
bit 17 the same for the transmit FIFO, bit 13 "DMA command is done", bit 12 both DMA and
PCAP done. They are states, not errors, and are what `50033004` consists of beside
`PCFG_DONE` and two bits above them.

## 54. Small checks before S2 — proposal (2026-11-18; the owner: do what can be done now, leave the rest to S2)

Three things, of which two are host only and one is a short session at the U-Boot prompt. No
new image, no run of the prober, nothing addressed in the PL.

**(a) A listing of status bits that are neither an error nor usual** — host only. The judges
hold every status word against the error mask and ask for `PCFG_DONE`; bit 5 passed them
unseen and was found by chance. A program reads the verdicts the judges wrote, stored or
new, and lists for every run each bit outside the error mask and outside `50033004`, where
it first showed and whether it stayed. It is a listing: it fails nothing.

- *Why not a field in the judges' verdicts:* stored verdicts are held equal, in tests, to what
  the judges give now. A new field would make every stored verdict differ, or have them
  rewritten. A program beside the judges changes neither.
- From here on it is run over every board result before the record is written.

**(b) A look at registers, from U-Boot** — on the board, read only. One `md.l` each:

| registers | why |
|---|---|
| `devcfg` CTRL, LOCK, CFG, INT_STS, INT_MASK, STATUS; MCTRL | the state the checks are made in; CFG holds the FIFO thresholds |
| `slcr` ARM, DDR and IO PLL control; ARM and DDR clock control; PCAP clock control | how fast the PCAP side delivers and the memory side takes (item 3) |
| `l2cpl310` reg1_control, reg1_aux_control | whether the level-2 cache is on (item 3) |
| `ddrc` axi_priority_wr_port0–3, axi_priority_rd_port0–3 | how the DDR controller ranks its ports (item 3) |

They are recorded. Nothing is concluded from them in a program; the record says what UG585
says of the values.

**(c) Can bit 5 be cleared, and does it stay away?** — on the board, one write to a PS
register. The board stands as run 20 of S1b.4 left it: PL configured, status `50033024`.

1. `md.l f800700c 1`. If it does not show `PCFG_DONE` and bit 5, nothing is written and the
   check is not made (the record says so).
2. `mw.l f800700c 00000020`, once. The register is write-one-to-clear; the prober writes its
   own clear mask to it before every read. This writes the one bit that mask leaves out.
3. `md.l f800700c 1` three times, a second before each.

What each outcome would say:

| after the write | reading |
|---|---|
| the bit is gone and stays gone | a latched event: something that happened at a read, not a state the PL holds |
| the bit is still there, or is back within seconds | the PL holds its error signal up while nothing is being read |

Either is recorded as it comes. Neither proves the guess of section 53, item 2; the first
fits it and the second would count against it.

**Not in this step, left to S2 or to a later decision:** single reads at `0x008000ff` and
`0x00800100` with the present image; a prober that clears bit 5 before every read (a new
image, the full review); the stack offsets 8 and 16; block type 2; the census document.

**On the board, when the owner says so, and not before.** The devices checked; `ps_look.py
--dry-run` shown; no `reset` beforehand — the check needs the state the last run left. Then
`ps_look.py --go --out evidence/pslook_17A6_<date>`, once. Its output committed as it stands;
then the record. If the status is not as expected, or a reply cannot be read whole, the
program stops by itself and that is what is reported.

## 55. The small checks as built (2026-11-18; host side, nothing on a board yet)

**`host/status_seen.py`** — (a). `status_seen.py <verdict.json | directory> ...`; a directory
stands for its own verdict or for those of its `runNN` directories. For each run: the bits
outside `ERR_MASK | 0x50033004` in the header's two readings and in the status words of every
record, each with the first place it showed, how many words have it, whether it stayed once
it showed and whether it is there at the end. One name is carried, bit 5's, from UG585.

Over what is stored: of 179 verdicts, the 158 from before S1b.4 have no such bit; in S1b.4,
bit 5 in the 14 runs of section 52, first at `0x00800100` and `0x00c00100` in runs 4 and 14.

**`host/ps_look.py`** — (b) and (c). Its commands are written out in it and it has no other
way to send one: seven dumps, the status, the write, the status three times. `--dry-run`
prints them; `--go --out DIR` sends them and leaves `console.log` and `look.json`.

- A dump whose reply is not whole is asked for again, at most five times, by the rule of
  section 43 (`s1a_run.whole`); if it cannot be read, the look stops there.
- The write is sent only if the status read just before has `PCFG_DONE` and bit 5; it is sent
  once, its reply is not examined, and it is never repeated. No prompt after it: stop.
- `--out` must not exist yet, so that a second call cannot write over a first.

**Tests.** 441 in all, 21 new: `tests/test_status_seen.py` (10: made-up verdicts; every
stored verdict; the command line) and `tests/test_ps_look.py` (11: against a pretended
console that clears the bit as the register does — the commands sent are held to a list
written in the test; the cases in which the write must not go out; replies that are not
whole; the dry run). The stored evidence is not touched.

**Mutants.** 26 new (9 and 17), 550 in all, none stale. Run as section 41 says for programs
of the host: their own, once — 26 of 26 killed
(`evidence/host_checks/mutants_2026-11-18_small_checks.txt`). No prober, judge or rule of the chain was
changed, so the complete set was not run.

## 56. The look at PS registers on the board (2026-11-19): the registers read; the bit not cleared, the board having been restarted

Released by the owner, who said that the board had been restarted. The record is
`evidence/pslook_17A6_2026-11-19/RESULT.md`.

- `ps_look.py`, once (`c000712`, as it came). Eight commands, all dumps, each whole at the
  first attempt. **Nothing was written to the board.**
- **(c) was not made.** The status read `a802000b`: no `PCFG_DONE`, no bit 5. The program
  stopped there by its own rule. Whether bit 5 can be cleared and stays away is still open.
- **(b), by UG585's register reference:**
  - the level-2 cache is off (`reg1_control` 0). One of the three directions of section 53,
    item 3, is gone;
  - the DDR controller's four write ports, and its four read ports, have the same setting:
    the lowest starting priority, aging on, page match on. Nothing puts the DMA's writes
    ahead of the processor's;
  - the PCAP clock is the IO PLL divided by 8 (200 MHz with this board's reference); the
    PLL and clock settings are in the record.
- This fits the plain account of the overflow — a store by the processor can hold up a write
  of the DMA — and does not explain the two things that are odd about it: the place within a
  32-byte block, and one read in a hundred. The mechanism is still not known.

One test added (`tests/test_board_evidence.py`, 442 in all): what was sent, that nothing was
written, and the values the record speaks of. No program was changed.

**To make (c)** the state has to be there again: the PL configured and bit 5 set, which only
a run of the prober over a frame of columns 2 to 4 of block type 1 produces. Proposed, and
not released: one run with the set `s1b4` started where run 5 of the stored chain started
(`s1a_run.py --stage s1b4 --start 0080013b`), which can be held against that stored run
record for record; `status_seen.py` over it; then `ps_look.py` straight after, with no
`reset` between. About five minutes on the board, the image and every program as they are.

## 57. Bit 5 cleared after a run (2026-11-19): it can be cleared and stays away

Released by the owner: the three steps of section 56. The record is
`evidence/sbit_17A6_2026-11-19/RESULT.md`.

- After a `reset`, one run of the set `s1b4` from `0x0080013b`: PASS, and run 5 of the stored
  chain over again — every record the same but for the number of polls (`feb4f39`).
- `status_seen.py`: bit 5 from record 2, the first read of a frame, to the end.
- `ps_look.py` straight after, no `reset` between (`6e3cf5f`): status `50033024`; the one
  write; `50033004` three times, a second apart.

**So the bit is a recorded event, not a signal the PL keeps raised**: it clears as UG585 says
and does not return while the design sits loaded and nothing is read. That is the outcome
that fits the guess of section 53, item 2; it is not proof of it. Whether every read of such
a frame raises it is still not known, and is left to a prober that clears the bit between
reads, if one is wanted, or to what S2 shows.

The second look also showed the registers of section 56 unchanged with the PL configured
and after a run: the level-2 cache off, the DDR ports ranked alike, the same clocks.

Two tests changed or added (`tests/test_board_evidence.py`: the run judged again and held
against run 5, the listing, the look; `tests/test_status_seen.py`: see below). 443 in all. No
program was changed, so no mutants were run.

**A slip in the order of things, recorded in the result file as well.** The two commits
above were made while one test was failing: `test_status_seen` counted every stored verdict
outside S1b.4's directory, and the new run made one more. The suite had been run, but its
result was passed through `tail` before the commit and did not stop it. The commits hold
only what the board gave and were left as they are; the test now names the directories whose
runs read frames of columns 2 to 4. From here on the suite's exit code is what a commit
waits for, not a line of its output.

**What is left of the small checks:** nothing. What remains open is listed in section 53 and
goes to S2 or to a later decision: block type 2; which reads raise the bit; the stack offsets
8 and 16; the census document.

## 58. S1b.5a — proposal: one run into block type 2 (2026-11-19; a proposal, nothing built, nothing on a board)

After the last frame of block type 1 the device named `0x01000000` (section 52). By the
fields of the address that is block type 2, top half, row 0, column 0, minor 0. The proposal
asked what is there and whether PCAP can read it (section 11, question 3). This is the
smallest step that can answer: one run, as S1b.4a was for block type 1.

### What is known and what is not

- UG470, table 5-24, of the block type field: "Valid block types are CLB, I/O, CLK (000),
  block RAM content (001), and CFG_CLB (010). A normal bitstream does not include type 011."
  It says nothing more about type 010 that I have found. It also says every frame of a
  7-series device has the same length, 101 words.
- The device itself: its address register went to `0x01000000` after block type 1, in the
  same way it went to `0x00800000` after block type 0 — after a standstill, by itself.
- Not known: whether a frame can be read there; how the register behaves there; how many
  addresses there are; what the device names after them (`0x01800000` would be type 011);
  what reading there does to the status register. Reading block type 1 raised a bit nobody
  had expected (sections 52 and 57); this may raise something too.
- The walk's rules were found in block type 0 and held in block type 1. Nothing says they
  hold in block type 2.
- **There is nothing to grade against.** The grader's database has no block type after 1
  (it said so in section 52). Whatever this finds stands on the device alone: the first
  result of this project without a second witness.

### The run

The image as it is (`fdc4f07f…9452`). A new set, `s1b5a`: the set `s1b4a` with two words
changed —

| word | `s1b4a` | `s1b5a` | |
|---|---|---|---|
| 4 | `0x00ffffff` | `0x017fffff` | the envelope's upper end: the last address of block type 2 |
| 16 | `0x00800000` | `0x01000000` | the start: the address the device named |

Everything else as it was: the envelope's lower end 0, because the reference frame `0xb99`
is in block type 0; the quiet wait; two passes of at most 64 frames; one standstill allowed
in a pass; the reference frame at least every 16 frames. Neither the prober nor any host
program limits addresses by block type — the envelope is a range of numbers — so nothing
has to change for an address above `0x00ffffff` to be allowed. The guard still lets nothing
out but read commands.

On the board: the devices checked; a `reset`; the one run (`s1a_run.py --stage s1b5a`), about
four minutes; its result committed as stored; `status_seen.py` over it; the layout by
`s1b4a_layout.py`; the record. Then stop. No second run, whatever the first gave.

### What may come out, said beforehand

1. **It passes**: up to 64 frames from `0x01000000`, both passes alike. Then block type 2
   can be walked like the others, and a chain over it is the next proposal.
2. **It passes with few frames**: the device soon names an address above the envelope
   (`0x01800000` or beyond) or stands still. That is an answer too — block type 2 is small, or
   is only a place the register passes through — and the record says which address.
3. **It stops at the first address**: the pad alone does not move the register, or moves it
   to an address not above the one read (`0x800`), or the pad is not zero, or two readings
   of a frame differ. The walk does not work there as it is. Everything read is in the result;
   what to make of it is a later question.
4. **The interface fails** (an error bit, a transfer that does not complete, `PCFG_DONE`
   gone): the prober stops at once, at that read, as it is made to — with no further read,
   the reference frame included. A `reset` — at worst switching the board off and on — and
   the next run of block type 0 or 1 shows whether anything stayed. The proposal counts that
   as no damage (section 10); nothing is written to configuration memory at any point.
5. **A status bit outside the usual shows**, as bit 5 did. The prober does not stop for it;
   `status_seen.py` lists it; it goes into the record and, like everything here, to the owner
   before anything further is run.

Whether the run itself shows that block type 0 could still be read after the reads in
block type 2 depends on how it ends. A run walked to its end (1, 2) reads the reference frame
last and holds it against its known content. A run the walk stops for something that is not
a failure of the interface — a pad that is not zero, two readings that differ — reads the
reference frame once more and then stops. A run stopped because the register does not go on
(`0x800`, `0x900`), or by a failure of the interface (4), ends on the read in block type 2: its
result shows nothing about block type 0 afterwards, and the record has to say so.

*(Corrected 2026-11-19 after review, section 60. This paragraph first said the reference
frame is read again "in every case", and item 4 said the prober stops "with one reference
read". Neither is what the prober does.)*

### What this step cannot show

- What block type 2 is. It lists addresses and delivers whatever comes back.
- Whether what comes back is what the device holds. If all frames are alike, as in most of
  what has been read, the list rests on the register alone.
- Anything about the rest of block type 2 beyond the first 64 addresses, or about type 011.

### What has to be built

The set's entry in the run script and its expected values (`tests/test_prober_image.py`);
tests on the twin with made-up layouts above `0x01000000` — one that goes on, one that ends
after a few frames, one whose register does not move, one that names `0x01800000` at once;
the mutants of what is touched. No new image, no change to the prober, a judge or the chain,
so the complete set of mutants is not due (section 41).

### What would follow, not proposed here

If it passes: a chain over block type 2 (`s1b5`, the set with the start given at run time;
the completion rule of section 50 already fits; the summary over rows is general). If it
does not: a look at what the result holds, and a decision whether block type 2 is left as
"named, not readable by this walk".

### For the owner

1. **Go into block type 2 now**, with nothing to grade it against — or leave it named and
   not read, and turn to S2. I propose the one run: the device points there, question 3 of
   the proposal asks, and it costs four minutes and no new image.
2. **The set `s1b5a`** as above: the start `0x01000000`, the envelope up to `0x017fffff`, 64
   frames a pass (or fewer for the first run).
3. **One run, then stop**: stored, committed, listed for status bits, laid out, reported;
   nothing retried, no chain without a further proposal.
4. **What I may read about block type 2.** So far only UG470 and UG585. Since no grading is
   possible here, the closed-book rule has no "afterwards" for this block type. I propose to
   keep to the two documents before and after the run, and to look nowhere else for what
   type 010 is unless the owner says so.

## 59. S1b.5a as built (2026-11-19; host side, nothing on a board yet)

The owner accepted all four points of section 58 as proposed: the one run into block type 2
now; the set as described; one run and then stop; and for what block type 2 is, UG470 and
UG585 only, before the run and after it.

**The set `s1b5a`.** `s1b4a` with two words changed, as proposed: word 4, the envelope's
upper end, `0x017fffff`; word 16, the start, `0x01000000`. The run script has the entry
(`host/s1a_run.py`, judged by the judge of a run of a chain, as `s1b4a` is); the expected
values are written with the others (`tests/test_prober_image.py`,
`build/prober/expected_s1b5a.json`). The start is fixed: `--start` is refused for it. The dry
run differs from that of `s1b4a` in exactly the two words written for those parameters.

**Nothing else was changed.** The image is the one that has been on the board
(`fdc4f07f…9452`). No line of the prober, of a judge, of the chain, of `s1b4a_layout.py` or
of `status_seen.py` was touched: the two programs that are run over the result take a walk
in block type 2 as they are, and a test says so.

**Tests** (`tests/test_s1b5a.py`, 17; 460 in all). The twin is given made-up layouts above
`0x01000000`, one for each outcome section 58 names beforehand:

- frames that go on: 64 walked, both passes at the limit;
- three frames and then an address above the envelope, with and without a standstill: a
  pass with three frames, the address named and not read;
- the first address names the one above the envelope: a pass with one frame;
- the register does not move at the first address: stopped there (`0x800`), one frame, the
  result stored whole;
- an address of block type 1, or address 0, is named: not followed, stopped (`0x800`) — the
  envelope begins at 0 for the reference frame's sake, and the walk is given nothing below
  its start all the same;
- the faults of the twin (a pad that is not zero, a short read, a frame that changes, an
  error bit, a transfer that does not end, `PCFG_DONE` gone, a register that jumps): each
  stops the run where it should, and the result is stored;
- in every one of them no address is written but the reference frame and what the device
  named, and nothing above `0x017fffff`.

Also: the set word for word against `s1b4a`'s; its start against the address the stored
chain over block type 1 ended with; that the result is not accepted as one of `s1b4a`; the
layout of such runs (block type 2 in its fields, an end that names block type 3, a run that
stopped called that); the listing of status bits over such a run, and over the same run with
a bit put in from the first read of a frame on.

One older test was changed: the list of sets that allow a standstill has one more name.

**Mutants.** Three new, of the set's entry (judged by the other judge; allowed a start;
given `s1b4a`'s values); 553 in all, none stale. Run as section 41 says: the 64 of the run
script, the one file of a program that was changed, and one of another program that the
same filter takes along — 65 of 65 killed (`evidence/host_checks/mutants_2026-11-19_s1b5a.txt`). No prober, judge or
rule of the chain was changed, and the image is not new, so the complete set is not due.

### On the board, when the owner says so, and not before

1. The devices checked; nothing else running on the host.
2. A `reset`, checked for the fresh prompt.
3. The one run: `s1a_run.py --stage s1b5a --go --out evidence/s1b5a_17A6_<date>/run`. About
   four minutes if it goes on; shorter if it ends or stops early.
4. Whatever it ends in — pass, fail or a stop of the run script: committed as stored.
5. `status_seen.py` over it; `s1b4a_layout.py` over its verdict; each kept beside the run.
6. The record. Then stop: no second run, no `reset`, nothing sent to the board after the run
   but what the run script itself sends. The owner decides what follows.

## 60. Review of `0605838` (2026-11-19): one finding, accepted — not every ending has a reference read after it

**Finding (P2).** Section 58 said that in every case the reference frame of block type 0 is
read again after the reads in block type 2, and that on a failure of the interface the
prober stops "with one reference read". The reviewer ran the twin: a run stopped at the first
address with `0x800`, and one stopped by an interface error with `0x221`, hold the first
reference read and none after it. Checked against the source, and so it is
(`prober/sm_core.c`, `walk_op` and `run_s4`):

| the run ends | reference frame after the last read in block type 2 |
|---|---|
| walked to its end, both passes and the reads of three | yes — the last record |
| stopped by the walk for something that is not a failure of the interface (`0x7..`) | yes — one read, then the stop |
| stopped because the address named is not above the one read (`0x800`), or at a standstill more than a pass may cross (`0x900`) | no |
| stopped by a failure of the interface (`0x2..`) | no — nothing is read after it at all |

That is the prober as it was reviewed and as it has run since S1b.1; stopping at once on an
interface failure is the rule of the proposal ("data taken after a failed health check would
not be trustworthy"). **Nothing in the prober is wrong and nothing was changed in it.** What
was wrong is my account of it in the proposal, and the consequence I drew: a result that
ends early does not by itself show that block type 0 was still readable.

**Changed.** The two passages of section 58, in place and marked as corrected. One test added
(`tests/test_s1b5a.py`, 18 there, 461 in all) that states the table above on the twin — for
the endings section 58 names and for the twin's faults — so that the sentence is held by
something.

**What it means for the run on the board.** Section 59's steps stand. Added to step 6: if
the run ends early with `0x800` or with an interface failure, the record says in so many
words that the run does not show block type 0 readable afterwards. Showing it then needs
another run; the run script begins every run by loading the design again, so even that run
would show the state after a new load, not the state the reads in block type 2 left. That
limit is stated, not worked around, and what to do in that case is the owner's decision.

No program of the host was changed either (a test only), so no mutants were run: 553, none
stale.

## 61. S1b.5a on the board (2026-11-19): PASS — block type 2 can be read, and has columns of one frame

Released by the owner after the review of section 60. The steps of section 59, in their
order: the devices checked and the host idle; a `reset` and the fresh prompt (status
`a802000a`); the one run, 15:58–16:02 UTC; its result committed as stored (`4858ffc`);
`status_seen.py` and `s1b4a_layout.py` over it; the record
(`evidence/s1b5a_17A6_2026-11-19/RESULT.md`). After the run nothing was sent to the board.

**Outcome 1 of section 58: it passes, 64 frames, both passes alike.** 292 records, no
anomaly; the checksum on the board is the checksum on the host; 2 of 69 pieces pulled a
second time; no short reply not whole; status afterwards `50033004`.

- The register behaves at `0x01000000` as everywhere before: the pad alone leaves it on the
  next address, and that address can be read.
- The next address is always the next column at minor 0. **Each column of block type 2 has
  one frame.**
- **The top half is one row of 56 such columns**, `0x01000000..0x01001b80`. At its last
  frame the register stands still for one step and then names `0x01400000` — the row end as
  in block types 0 and 1, and the one standstill a pass may cross.
- **The bottom half** was walked for 8 columns, `0x01400000..0x01400380`, to the limit of 64
  frames; `0x01400400` is named. That row was not ended.
- **Every frame delivered is all zero** (194 in all).
- **No status bit that is neither an error nor usual** in 1,462 status words: reading these
  frames does not raise bit 5.
- **The reference frame** as known at all 14 readings. The run was walked to its end, so the
  last of them is after the last read in block type 2: the case of section 60's first line.
  The case section 60 was written for — an early end without that reading — did not arise.

**What it does not say.** It is not a list: one row whole, one begun. All zero cannot tell
frames that hold zeros from addresses with nothing behind them, and the walk has never read
an address the device did not name, so there is nothing to hold this against. What block
type 2 is, is not learnt: UG470 gives the name `CFG_CLB` and no more that I have found, and
nothing else was consulted. That the 56 one-frame columns stand beside the 56 columns of a
row of block type 0 is a guess from the count. Nothing was graded, and nothing can be: the
grader's database has no block type after 1.

**Tests.** One added (`tests/test_board_evidence.py`, 462 in all): the stored result by its
hash, judged again from its raw words, with the addresses, the standstill, the records, the
layout and the listing of status bits as said above. No program was changed, so no mutants
were run: 553, none stale.

**Next.** Nothing until the owner says. By section 58 the next proposal after this outcome
would be a chain over block type 2 — it would be short: the rest of the bottom row and
whatever is named after it. It has not been written.

## 62. S1b.5 — proposal: the chain over block type 2 (2026-11-19; a proposal, nothing built, nothing on a board)

The walk works at `0x01000000` (section 61). This proposes the chain that goes on from there
until the device names an address above block type 2, what is made of its runs, and what is
said beforehand about how it may end. Nothing of it is built.

### What is known and what is not

Known, from the device: 64 addresses from `0x01000000` — a row of 56 columns of one frame in
the top half, a standstill, and 8 columns of one frame in the bottom half; the register
behaving as elsewhere; every frame all zero; no status bit raised. Not known: how long the
bottom row is; whether there are rows after it; what the register does at its end; what the
device names after the last frame of block type 2, or whether it names anything above. No
number of any of these is assumed below. In particular the chain is not told that the bottom
row has 56 columns: if it has, the chain is two runs long; it goes on for as long as the
device names addresses inside the envelope.

### The chain

The chain driver as it is (`host/s1b2_chain.py`), with a parameter set of its own. **No rule
of the chain, of a judge or of the prober changes.**

- **The set `s1b5`**: the parameter block of `s1b5a`, word for word — envelope
  `0x00000000..0x017fffff`, two passes, 64 frames a pass, one standstill a pass, the reference
  frame `0x0b99`, the quiet wait — with the start given at run time by the chain, its first
  address `0x01000000`. The image unchanged (`fdc4f07f…9452`).
- **It starts at `0x01000000` again.** The stored run of S1b.5a is of another set and cannot
  be a run of the chain. So the first run walks the 64 addresses of section 61 a second time
  (four minutes), and they are held against that stored run. Every later run starts at the
  last frame the run before walked, as in every chain so far.
- **The known frames**: the chain asks for those at or above its first address (section 49).
  There is none in block type 2, so the rule asks for nothing here, as in block type 1.
  "Complete" rests on what every run's judge holds — the register after every read, two
  passes alike, every frame once more in a read of three, the reference frame as known at
  most 16 frames apart — on the seams, and on both passes of the last run leaving the
  envelope.
- **It goes on** after a run that ended at the limit; **it is complete** when both passes of
  a run end because the device named an address above `0x017fffff`. That address is recorded
  and never written to the register.
- **It halts** on anything else, as now. A halt is stored, committed and reported, and what
  there is by then is summarised as that.
- **The bound: 12 runs** (about 50 minutes): a bound on unattended board time, not a
  statement about the part. At the bound the chain stops and says where it stands.
- **The order on the board**, as for S1b.4: the first run alone and looked at; then
  unattended to the end, a halt or the bound. A `reset`, checked, before every run.

### How it may end, said beforehand

1. **Complete**: after the last frame the device names an address above the envelope —
   `0x01800000`, by its fields the first address of block type 3, or another. The run that
   leaves the envelope is walked to its end, so its last record is a reference read
   (section 60, first line).
2. **Halted because the address named is not above the one read** (`0x800`): the register
   stands still for good, or goes back to a lower address, at the end of the bottom row or
   of a later one. Block types 0 and 1 each ended by naming the first address of the next
   block type; nothing says the last block type the register knows does the like. This is
   the ending I think as likely as the first. By section 60 such a run has no reference read
   after its last read in block type 2, and the record will say so; the next run of anything
   begins with a new load of the design.
3. **Halted at a second standstill in a pass** (`0x900`). The set allows one. A row here is
   shorter than a pass — 56 frames against 64 — which was never so before: if block type 2
   has rows after the bottom one, a pass can come to hold two row ends, and the chain would
   halt for a reason of the walk's making, not of the device's. With the two rows seen so
   far it cannot happen (the first run crosses one end, the second would meet one). The
   prober and the judge take up to 4 for that word; I propose to leave it at 1, as in every
   chain so far, and to treat such a halt as a halt: reported, and a set with 2 proposed
   then, if the owner wants it.
4. **Halted on an anomaly or a failure of the interface**: stored as it is; nothing retried.
5. **The bound**: more than about 750 addresses in block type 2. Reported; going on needs
   the owner's word.

### What is made of the runs

- **The summary over rows**: `s1b3_rows.py` as it is, told the set (`s1b5`). It holds no
  number of rows, columns or frames.
- **The first run against the stored run of S1b.5a**: `s1b4_first.py` as it is — every
  address that run walked in the chain's list, with the same frame, the same address named
  after it, a standstill in both or in neither. A difference is listed and alters neither.
- **The status bits**: `status_seen.py` over every run.
- **No grader.** The database has no block type after 1 (section 52). The list of block type
  2 will stand on the device alone, and the record will say so. What it has instead of a
  second witness is only its own repetition: two passes, the reads of three, the seams, and
  64 of its addresses read on two days.

The order kept so far: the runs are stored and committed as the chain stands first; then the
summary; then the comparison and the listing of status bits; each committed before the next.

### What this step cannot show, said beforehand

- **Content.** If every frame is again all zero, the list rests on the register and on the
  reference frame alone, and nothing is learnt of what these frames hold or whether anything
  is stored behind them. That needs a write (S2 and later), not another read.
- **What block type 2 is.** UG470 names it and no more; nothing else is consulted, as agreed
  for section 58, unless the owner says otherwise.
- **What follows block type 2.** An address named above the envelope is named, not read. If
  it is `0x01800000`: UG470 says a normal bitstream does not include type 011. Whether to
  read there is not proposed here and would be a proposal of its own.
- Whether reading these frames disturbs the loaded design, beyond the reference frame and
  the status register.

### What has to be built

Host only; the image is not built again.

- the set `s1b5` (the run script takes its start at run time; the expected values written
  with the others; a test that it is `s1b5a`'s block word for word) and its bound in the
  chain driver;
- tests on the twin with a made-up block type 2 of rows of one-frame columns, of lengths the
  part does not have: a chain that is complete, with the summary and the comparison over it;
  each of the endings 2 and 3 above, halted and summarised as that; the bound; and that no
  address is written but the reference frame and addresses the device named inside the
  envelope;
- mutants as section 41 asks: no prober, no judge and no rule of the chain is changed and
  the image is not new, so the complete set is not due — the mutants of the two files that
  change (the run script, 64; the chain driver, 40) and whatever new ones the set gets, with
  the anchor check over all 553.

### For the owner

1. **The chain as proposed**: the set `s1b5`, from `0x01000000` again, the first run alone
   and looked at, then unattended; the bound of 12 runs.
2. **One standstill a pass, as it is** — a second one in a pass is a halt and is reported
   (ending 3) — or the set with 2 from the start.
3. **What is made of the runs**: the summary, the comparison with S1b.5a's run, the listing
   of status bits, in that order, following one another when the chain is complete or
   halted; no grading.
4. **The address named after block type 2 is recorded and not read**; reading there, if it
   comes to that, is a separate proposal.

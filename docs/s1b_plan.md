# S1b — plan for the first widening (2026-11-13; the walk and step S1b.0 agreed by the owner the same day)

S1a showed the method on three known frames. S1b widens the range step by step until the device
has listed its own frames. Each step gets its plan reviewed, its host side built and tested, and
the owner's go-ahead before it touches the board. This document proposes how to walk, and
details the first step only.

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


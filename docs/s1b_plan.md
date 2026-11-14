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

## 5. S1b.0 as built (host side; nothing on a board yet)

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

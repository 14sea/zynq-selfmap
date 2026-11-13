# S1b — plan for the first widening (draft for the owner's review, 2026-11-13)

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

From S1b.1 on most frames have no known answer. During the walk the only criteria are internal:
every frame read twice and identical, the three known frames still equal to their known values,
the reference frame unchanged. Afterwards, as grading and not as input, the frames are compared
with the loaded bitstream and the frame list with prjxray's.

## 4. Questions for the owner

1. Is "follow the address the device names" the walk you want, rather than stepping through
   addresses?
2. S1b.0 adds one kind of packet the verified sequence never used: a read of the FAR register.
   It is a read, of a register UG470 documents as readable. Agreed as the first new thing to try?
3. For S1b.1 and later: the frames without a known answer are graded afterwards against the
   loaded bitstream. That needs a frame parser on the host — as a grader only. Acceptable?

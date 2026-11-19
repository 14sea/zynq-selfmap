# The frame census — EBAZ4203 `17A6`, as of 2026-11-19

`frame_census_17A6.json` is the census the proposal asks of S1 (section 4): which frame
addresses the device names, the fields of each, and whether its frame reads back the same.
It follows `schemas/frame_census_v1.schema.json`, a document modelled on the structure
description (`schemas/self_map_v2.schema.json`), which has no place for it and is not
changed. Label: **closed-book** — it rests on observations made on the device only.

It is written by a program and not by hand:

    python3 -B host/s1_census.py \
      --chain s1b3=evidence/s1b3_17A6_2026-11-17 --chain s1b4=evidence/s1b4_17A6_2026-11-18 \
      --chain s1b5=evidence/s1b5_17A6_2026-11-19 \
      --seen s1b6a=evidence/s1b6a_17A6_2026-11-19 \
      --also s1b1r=evidence/s1b1r_17A6_2026-11-15 --also dx=evidence/dx_17A6_2026-11-15 \
      --also quiet=evidence/quiet_17A6_2026-11-15 --also s1b2=evidence/s1b2_17A6_2026-11-15 \
      --also s1b3a=evidence/s1b3a_17A6_2026-11-17 --also s1b4a=evidence/s1b4a_17A6_2026-11-18 \
      --also sbit=evidence/sbit_17A6_2026-11-19 --also s1b5a=evidence/s1b5a_17A6_2026-11-19 \
      > census/frame_census_17A6.json

A test (`tests/test_board_evidence.py`, `test_the_frame_census`) makes it again from the raw
words of the stored runs and holds the stored file to the result, and every number below to
the document.

## What it holds

**5,256 entries**, one for each address the three complete chains walked, in rising order.
They are **one stretch**: from `0x00000000` to `0x01401b80` every entry is the address the
device named after the one before, and after the last it named `0x01800000`. The document
says this itself (`stretches`); had a chain been left out, it would list two stretches and
claim nothing across the gap.

| block type | addresses | rows | columns a row | frames a column |
|---|---|---|---|---|
| 0 | 3,864 | top half and bottom half, row 0 each, 1,932 frames | 56 | 41 of 36, 9 of 28, 4 of 30, 2 of 42 |
| 1 | 1,280 | top half and bottom half, row 0 each, 640 frames | 5 | 128 |
| 2 | 112 | top half and bottom half, row 0 each, 56 frames | 56 | 1 |

An entry has the address, its fields (UG470's layout of the address word), the address the
device named after it, whether the register stood still there (the six last frames of rows),
how many times its frame was read and in which records of which runs, how many different
contents those readings had, and the sha256 of the content.

- **16,181 readings; every address at least 3** — both passes and a read of several frames —
  167 of them 4, and the 82 frames at which one run of a chain took over from the one
  before, 6.
- **Not one address was read two ways**: `not_stable` is 0.
- **Other occasions.** Every other stored run with a passing walk — eight groups, 46 runs,
  from 2026-11-15 to 2026-11-19, each after a load of its own — was held against the
  entries: 2,146 of the addresses were walked on more than one occasion, 2,498 readings in
  all, and none differs.
- 4,060 entries are all zero. 1,196 are not: 428 in block type 0, with 424 different
  contents among them, and 768 in block type 1, all one content.

Beside the entries:

- **Seen, not walked**: the ten addresses of block type 3 that the one run at `0x01800000`
  read, once each, in a pass the walk stopped (`0x900`). They are not entries. Only reads
  that succeeded are taken from such a run — no code, no short read, the pad all zero; here
  all 20 were, and none is listed as not used (`seen_runs`).
- **Named, not read**: `0x02000000`, which the address register held when that run stopped.
- **A status bit**: bit 5 of `devcfg.INT_STS` in 14 of the 21 runs over block type 1, with
  the record at which it first showed in each. Seen, not judged.

## What it is bound to

- **The prober image**: sha256 `fdc4f07f…9452`. The file kept beside each chain's runs is
  held against what the chain's set declares (hash, size, checksum); and in every one of
  the 85 run records the checksum U-Boot gave of the image in RAM — in the step just before
  the prober was started, and again after it returned — against that file.
- **The design** (`carrier.bit`, an opaque file here): 2,083,863 bytes, sha256
  `8c3369e8…0b8a` as the sets declare it. U-Boot's checksum of the design in RAM, in the
  step just before it was loaded into the PL, is the same in all 85 run records (`72887bf4`),
  and it is the checksum of the file with that sha256 —
  checked where the file is at hand, as it was when the document was made
  (`pl_design_sha256_held_against_the_file`).

A chain whose own files do not bear out what its set declares is refused.

## What it stands behind, and what it does not

- That the device named these addresses, in this order, and that a frame read at each came
  back the same every time it was read — within a run, across the runs of a chain, and, for
  two in five of them, across loads and days.
- **Not what a frame holds.** The content is the content with the carrier design loaded
  (`carrier.bit`, sha256 `8c3369e8…0b8a`, an opaque file here). Three in four frames are all
  zero; where frames are alike, readings that agree cannot tell one frame from another, and
  the entry rests on the address register, read after every read.
- Not that these are all the addresses there are. The walk reads only where the device
  points; it pointed on, to block type 3 and then to `0x02000000`, and was not followed
  further (docs/s1b_plan.md, section 67).
- Not what a read at an address the device does not name would give.
- **Nothing in it is graded.** The comparison of block types 0 and 1 with prjxray-db is kept
  apart, in `grade.json` beside each chain's runs: nothing differs. Block types 2 and 3 have
  nothing to be compared with.

# S1b.2b, the end of the row — EBAZ4203 `17A6`, 2026-11-16: both runs PASS

Questions (docs/s1b_plan.md, section 29): what does the address register do between `0x00001ba9`
and `0x00400000`, and what does a read deliver there? And are the 42 frames of column 55, read
once by one path in run 30 of S1b.2, the same when read again by another?

**What there is: beyond `0x00001ba9`, the last address of the row, the register stands still
twice — one step at `0x00001ba9`, then it reads `0x00400000`, one more step at `0x00400000`, and
then `0x00400001`. Two frames were delivered from beyond `0x1ba9`, both all zero. The 42 frames
of column 55 are the same by the second path, and every one of them is all zero — so the content
says nothing about position here; the register does. No overflow, no anomaly. The grader has not
been run and the database has not been looked at.**

## The runs

Released by the owner on 2026-11-16 after the review of section 30. The host side at commit
`cc61231`; the image `prober.bin`, 11,630 bytes, sha256 `2c566b1e…b296`, crc32 `b0d75377` — the
image of S1b.1 and S1b.2, unchanged. Nothing else ran on the host.

- Pre-check (`precheck_console.log`): U-Boot 2026.04-rc5 at its prompt, `INT_STS a802000b` (the
  board had been powered off since S1b.2), `carrier.bit` on the card, 98 files.
- Before each run a U-Boot `reset`, checked for the usual fresh prompt (`resets_console.log`),
  and a fresh load of the PL design from the card.
- 18:40 UTC `s1b2e`: 50 records, status 1, no anomaly; console `SM5 end status=00000001
  records=00000032 anomalies=00000000 words=00005e00`. `result.bin` sha256 `f76eda60…8658`; card
  copy `safb4e0e.bin`, verified; the board's crc32 of the result `581caa69` is the host's. One of
  the 12 pieces came back short and was pulled a second time, as the run script provides.
- 18:41 UTC `s1b2c`: 30 records, status 1, no anomaly; console `… records=0000001e … words=00003880`.
  `result.bin` sha256 `8de52d70…3f82`; card copy `safb4e5d.bin`, verified; crc32 `bc7ef00f` on
  both sides; no piece repeated.
- `INT_STS` after each run `50033004`. The wait that touches no memory; the polling variable at
  `0x1eacaa20` (≡ 0 mod 32); no interface failure in either.
- Each run was committed as saved before the next thing was done (`30badca`, `c5191ab`), and the
  layout as it came out (`8496bec`) before anything was written about it. Nothing was retried,
  nothing set aside.

Both runs pass the judge: the records are the ones planned, every repeat left what the first
did (register and words), the reference frame `0xb99` was as known before and after. The frames
delivered have no known answer and are counted, not graded: 72 and 84.

## The end (`s1b2e`): the register, step by step

A read writes an address to the register and clocks out the pad and 0 to 3 frames; "steps" is
the number of frames of words clocked, the pad included. Each read was made three times and left
the same every time.

| read at | 1 step | 2 steps | 3 steps | 4 steps |
|---|---|---|---|---|
| `0x1ba6` | `0x1ba7` | `0x1ba8` | `0x1ba9` | **`0x1ba9`** |
| `0x1ba7` | `0x1ba8` | `0x1ba9` | **`0x1ba9`** | `0x00400000` |
| `0x1ba8` | `0x1ba9` | **`0x1ba9`** | `0x00400000` | **`0x00400000`** |
| `0x1ba9` | **`0x1ba9`** | `0x00400000` | **`0x00400000`** | `0x00400001` |

The four starting addresses are one step apart by the device's own word (first column), so a
read from the i-th of them that clocks k steps ends at position i + k of one line. Every
diagonal of the table is one position, and **every diagonal agrees**:

| steps beyond `0x1ba9` | register | reached by |
|---|---|---|
| 0 | `0x00001ba9` | 3 reads |
| 1 | `0x00001ba9` | 4 reads |
| 2 | `0x00400000` | 3 reads |
| 3 | `0x00400000` | 2 reads |
| 4 | `0x00400001` | 1 read |

So the register does not change at the first step beyond `0x1ba9` and not at the third. What
run 30 saw (after the pad alone at `0x1ba9`: `0x1ba9`; after the pad and one frame:
`0x00400000`) is the first two rows of this, the same on another day after another reset.

The same read was made in both runs (`0x1ba7`, 4 steps): `0x00400000` in both, the same words.

## What was delivered

A read of n frames from position i delivers positions i to i + n − 1. Six positions were
delivered: the four addresses written (by 3, 5, 6 and 6 reads) and the two beyond `0x1ba9` (by
3 reads and by 1). **Every frame delivered is all zero**, 72 of 72. All ways to a position agree
— and that says nothing about which position any of them read, as `end.json` notes itself.

- **Two frames came from beyond the last address of the row**, as the owner allowed
  ("at most two"), and no more: the table has no read that could deliver a third.
- What those two are is not settled by their content. By the register, the first was clocked
  while it read `0x1ba9` a second time, and the second while it had come to read `0x00400000`.
  The position at which the register still reads `0x00400000` (three steps beyond) and the one
  at `0x00400001` were not delivered by any read.

## The column again (`s1b2c`)

14 reads of three frames from `0x1b80`, `0x1b83`, …, `0x1ba7`, twice.

- **42 frames compared with the 42 of run 30's walk, 42 the same**; no address of the walk left
  unread; the address of each frame of a read taken from the walk's own successors.
- **The register after each read is what the walk's successors say** for the 13 reads that stay
  within the walk (`0x1b84`, `0x1b87`, …, `0x1ba8`). The 14th (`0x1ba7`, 4 steps) ends beyond
  where the walk's successors reach: `0x00400000`.
- Every frame of the column is all zero, in both runs and in the walk: one content. That the two
  paths agree on content is weak; that the register went the same way by both is not.

Column 55 therefore has the 42 addresses `0x1b80..0x1ba9`, named one after another by the
device, read by two paths on two days; like column 0, it has 42 frames.

## What this does not show

- Whether the two positions beyond `0x1ba9` hold frames of their own or are something else
  (the register has no address of its own for the first of them). Their content, all zero, is
  the content of every frame near them.
- What a read started **at** `0x00400000` does: no address above `0x1ba9` was written. That
  `0x00400000` is an address like the others is the register's word only.
- Whether other rows end the same way. This is one row end, of one row.
- The mechanism. The table above is what the register read; nothing in the programs expects it.

## What follows from it for the walk (not built, not decided)

The walk's rule is "the address after F is what the register reads after the pad alone at F",
and it stops when that is not above F. At `0x1ba9` the pad alone leaves `0x1ba9`; one more frame
of words leaves `0x00400000`. A walk that is to cross a row end has to be told what to do when
the register stands still — a change to the prober, and a new image. `0x00400000` is outside the
envelope of S1b.2 (`0x0..0x1ffff`), so for the row of S1b.2 the count is: columns 0 to 55,
1,932 frames (`0x00000000..0x00001ba9`: the 1,890 of columns 0 to 54 and the 42 of column 55).
The stored chain of S1b.2 remains what it was: halted.

For the owner: grading (the row against prjxray-db, with the end of the row now recorded
first), and whether the walk is to learn to cross a row end, are separate decisions; neither has
been started.

## Afterwards: the row closed, and the grader (2026-11-16, later the same day)

Everything above was written before this, and stands as written. Then, as sections 32 and 33 of
the plan lay down and the owner released after review:

1. **`row_closed.json`** (sha256 `d8457ed8…de59`), written by `s1b2_closed.py` from the stored
   `row.json` of the chain, the stored verdict of run 30 and the two verdicts above, and
   committed (`6c06397`) before the grader was run. All six rules hold. It is the chain's
   summary — still `halted`, its 55 columns and 1,891 addresses unchanged — with the 41 further
   frames of run 30's walk added, each read again by `s1b2c`: 56 columns, 1,932 frames, column
   55 `0x1b80..0x1ba9`; after the row `0x00400000`, the register having stood still one step
   before it.
2. **`grade.json`** (sha256 `6ecfc55f…9887`), `grade_s1b2.py` run once on that file against
   `/home/test/prjxray-db/zynq7/xc7z010clg400-1/part.json` (sha256 `1754ec1c…d095`, the
   checkout at `0a0adde` — the file S1b.1 was graded against), committed as it came out
   (`fffe4cc`):
   - each of the 56 columns has the number of frames the database gives it (41 of 36, 9 of 28,
     4 of 30, 2 of 42);
   - the columns walked are the database's columns 0..55 of this row, in order — the database
     has no further column in it;
   - frames in the row: 1,932 found, 1,932 in the database;
   - the address named after the row, `0x00400000`, is the first frame of the row next in the
     database's order: row 0 of the bottom half; the database has no second row in the top half;
   - **nothing differs.**
   - Not compared, and listed as such: the steps at which the register stood still (1 and 3
     beyond the last frame) — the database lists frames and has nothing to hold that against;
     and the two frames delivered from beyond the row.

What the agreement is worth: the frame counts and the order of the columns were found by asking
the device what follows what; no count and no layout is in the prober, the judges, the chain or
the program that closed the row. The database is a second witness to them, and agrees. It is
not a witness to the two places where the register stands still, nor to what a read delivers
there: on those the device's word stands alone, from one row end.

One slip in the order of work, recorded: `grade.json` was committed (`fffe4cc`) without the
suite having been run first, and one test then failed — it asserted that no `grade.json` lay
in this directory, which was true of the board step and no longer was. The assertion was
replaced by one that holds the stored grade (its hash, and that it is the grade of
`row_closed.json`) in the next commit. Neither file was touched.

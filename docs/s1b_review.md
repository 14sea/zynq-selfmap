# S1b — review of the whole (2026-11-19)

The proposal has S1 to S3 finished and reviewed before S4 is decided (section 7). This is the
review of S1b, prepared for the owner. It is not written from memory: every statement below
was checked against the source, the tests, the stored evidence or the history of the
repository on 2026-11-19, at commit `6653730`, and where a check was a program run, the
numbers are its output. Nothing was changed for it but this file and a pointer in the plan.

It ends with findings and what I recommend for each. None of them is acted on here.

## 1. What S1b was to deliver, and what there is

The proposal, section 7: "Read-only census, widened in steps: walk the FAR space; record
which addresses exist and how many frames each block type has", its output "the frame list,
compared afterwards with prjxray's 5144". Section 4 adds the form: a census document beside
the structure description — which addresses exist, their block type, whether readback is
stable.

| asked | there is | where |
|---|---|---|
| the frame list | 5,256 addresses the device named, in one line from `0x00000000` to `0x01401b80`: 3,864 of block type 0, 1,280 of block type 1, 112 of block type 2 | `census/frame_census_17A6.json` |
| how many frames each block type has | the same, by rows and columns | the census's `rows`; `census/README.md` |
| compared afterwards with prjxray's 5144 | block types 0 and 1: 5,144, graded row by row and column by column, nothing differs. Block type 2 is not in the database | `grade.json` beside the runs of S1b.1, S1b.2b, S1b.3, S1b.4 |
| whether readback is stable | 16,181 readings, at least 3 of every address, no address read two ways; 2,146 addresses walked again on other occasions, 2,498 readings, none differing | the census's entries and `other_occasions` |
| the census as one document | written, with a schema of its own; the copied schema untouched | `schemas/frame_census_v1.schema.json`, plan sections 68 and 69 |

Beyond what was asked: the address register goes on above block type 2. Ten addresses of
block type 3 were read once each in a run the walk stopped, and the register then stood at
`0x02000000`. By the owner's decision this was not followed further (plan, sections 67, 68).

**S1b never wrote configuration memory.** Every packet the prober sent in every stored run is
in that run's result, and every judge replays them through the packet parser against the
read-only policy (section 3 below).

## 2. What the result rests on, said once

- **On the address register.** After every read the prober reads the register back, and the
  judges hold each value to the walk's rule. Three in four frames are all zero and cannot be
  told apart by content; for them the register is all there is.
- **On repetition.** Every address: two passes and a read of several frames in one run. The
  82 frames at which one run of a chain took over from another: two runs. Two in five of the
  addresses: other runs on other days, each after a new load of the design.
- **On a second witness, for block types 0 and 1 only.** The grader compares the structure
  — rows, columns, frames a column — with prjxray-db. It compares no content.
- **On one board and one design.** EBAZ4203 `17A6`; `carrier.bit` (`8c3369e8…0b8a`). The
  prober image is `fdc4f07f…9452` for everything from S1b.3a on — all three chains of the
  census. Six earlier images came before it, one for each step up to the quiet wait; the
  top row of block type 0 was walked by two images, S1b.2's and this one, and read alike.

## 3. The four fixed points of the proposal's discipline

**1. The program is checked for safety before it runs, by rule.**

| the proposal says | what there is | held by |
|---|---|---|
| every device access through a few helpers; the host build logs each; a test holds the log to an allow-list written in the test | `hal_rd`/`hal_wr`; the twin logs every access; the registers written and read are listed in the test, for every stage of the prober, the walk among them | `test_the_only_registers_touched` in four test files |
| one generator of command packets; a real parser shows a read-only stage can only produce reads | `host/packets.py`, structural; held against the C guard on mutated streams | `tests/test_prober_packets.py` |
| an address envelope and budgets (frames, time, anomalies) | the envelope, and a limit of frames a pass. **Time**: a poll limit on each transfer, no budget for a run. **Anomalies**: see section 4, D1 | the parameter checks in `run_s4`; the guard |
| the same rules enforced inside the prober at run time; the host replays the logged packets afterwards | the guard refuses before anything is sent; every stream sent is in the record, and each judge replays it through the parser | the judges; every stored result judged again in the suite |
| the image inspected (the reserved register, privileged instructions, sections); its sha256 in the run record; an image whose hash was not checked is not run | so; the run script refuses an image that is not the expected one, and checks its checksum in RAM before the start and after the return | `tests/test_prober_image.py`; `s1a_run.py` |

**2. The closed-book rule**, "including a check that the prober's build inputs contain none
of the forbidden sources". Held for the sources: a test goes through every file of `host/`
and `prober/` for the database's name, a frame count, a grader's import — the graders
excepted — and the programs that make the lists each have a test that they hold no number of any
part. *Not checked by a test*: the Makefile and the linker script; I read them for this
review, and they name nothing but the prober's sources and the toolchain. For block types 2 and 3 a narrower rule was agreed and kept: UG470 and UG585
only.

**3. All raw readback archived, unmodified, with digests, before interpretation.** Held. The
result is saved whole to the card, pulled, and the pulled copy accepted only if its checksum
is the one the board gave; the judge reads that file. 185 run records are stored; five have
no result, each with the stop that says why (section 5).

**4. Grading afterwards, kept apart.** Held, and checked in the history: for each graded
step the summary was committed before the grade — S1b.1 by 1.5 minutes, S1b.2b by 8
seconds, S1b.3 by 3 minutes, S1b.4 by 6 minutes — and no summary was changed after its
grade. The census carries no grading. No bitstream was parsed and no Vivado report used.

## 4. Where S1b differs from what the proposal says

- **D1. Anomalies.** The proposal: record and skip while the interface is healthy; stop when
  a health check fails or the budget is used up. The first stages do that. **The walk does
  not**: it refuses a set with an anomaly budget and stops at the first anomaly, after one
  read of the reference frame (plan, sections 29 and 39). That is narrower than the
  proposal, by decisions made in the plan; the proposal's text was not brought up to it.
- **D2. Not every ending reads the reference frame again** (plan, section 60): a run stopped
  because the register does not go on, or by a failure of the interface, ends on its last
  read. Only S1b.6a ended so on the board.
- **D3. Digests.** The proposal has the UART carry "a digest of every saved block". The
  digests are U-Boot's checksums, asked for by the host after the prober has returned; the
  prober itself prints a start and an end line.
- **D4. Labels.** "Every result is labelled closed-book or half-open." The census is. The
  summaries of the single steps (`rows.json` and the like) carry no label; all of S1b is
  closed-book, and nothing in it uses what our own design put where.
- **D5. More than the database knows.** Block type 2 is valid by UG470 and not in the
  database; block type 3 is, by UG470, in no normal bitstream. They are in the census — the
  one as entries, the other listed apart — because the device named them, and they are the
  part of it with no second witness.

## 5. An audit of the stored evidence

For this review every stored run was taken again: 185 run records under `evidence/`; where a
result is stored, the judge of the run's set, as it is now, judged it from its raw words, and
the outcome was held against the verdict stored beside it. (A script of a few lines, run
once; it is not in the repository — finding F1.)

| | runs |
|---|---|
| the stored verdict is exactly what the judge writes now | 143 |
| the same verdict, the stored file an older form of it | 41 |
| no result at all; the record says why | 1 |

*(Corrected 2026-11-19, when the audit was made a test — section 11. The script had passed
over the first run of all, whose record does not name its set, and over the four results
recovered from the card, which lie in directories of their own; it gave 142, 37, 1 and 5.
The test takes them all: 184 results judged, 140 PASS and 44 FAIL.)*

- **In no run does PASS or FAIL differ from what was stored.**
- The 41 are runs of 2026-11-14 and the diagnostic series of 2026-11-15. The judges were
  given fields later (where the polling variable lay, the wait in use); the stored verdicts
  are the judges' words of that day and were left as they were. In one of them — the run in
  which the overflow was first met — the judge of today lists one problem more than was
  stored (the header's status against what the records imply). It was a failed run then and
  is one now.
- Five runs have no result of their own: three pulls of 2026-11-14 that did not give the
  board's checksum, one where the serial adapter dropped off the host, and run 51 of the
  chain over block type 0, set aside when the console lost characters. For the first four
  the result was taken from the card afterwards and is kept in a directory beside the run,
  with the board's checksum (I first wrote "two": it is four). Run 51 has none. All five
  are in their `RESULT.md`.
- Every directory with a board run has a `RESULT.md`.

**What no test holds** (finding F1): the 19 result files of `fifo_rate_17A6_2026-11-14` —
17 runs that counted reads before the overflow, and the two recovered copies. No test names that directory; their verdicts
are read by one test that looks for status bits, their raw results by none. They could be
altered without the suite noticing. Nothing in the census or in any list rests on them.

## 6. What is weak, and what is not known

Carried from the plan (section 53) and the records; nothing here is new, it is in one place.

**About the result itself**

1. Content is not stood behind. 4,060 of 5,256 frames are all zero.
2. Block type 2 (112 addresses) has no second witness; block type 3 (10) was read once each
   in a failed run; `0x02000000` was not read. Where the register's address space ends is
   not known.
3. 3,110 of the addresses were walked on one occasion only.
4. No address the device does not name was ever read. What such a read gives is not known.
5. One board. Nothing says another die of the same part answers the same.

**Seen and not explained**

6. Block type 1, columns 2 to 4: 768 frames, all one content that is not zero.
7. Reading those frames sets bit 5 of the status register (`PCFG_SEU_ERR`). It clears and
   stays away. Whether every such read sets it is not known. Reading block types 2 and 3
   does not.
8. The receive-FIFO overflow: not met once since the polling loop stores nothing while a
   transfer runs; the mechanism in the hardware is not known.
9. The two places after the last frame of a row, at which the register shows no address of
   their own.
10. `a802000a` after a reset against `a802000b` after power-on; and the console losing
    characters now and then, which the run script now meets by asking again.

**Not looked at, because S1b could not**

11. Whether readback disturbs a running design: nothing here uses the carrier.
12. The proposal's questions 4 to 7 (the mask on LUT RAM, stopping the design, GCAPTURE, the
    layout within a LUT) and the AXI path of question 9. They are S2's and S3's.

## 7. The reviews so far, and my own slips

The plan has eleven sections that record a review and what was changed after it (6, 7, 10,
14, 18, 21, 27, 40, 51, 60, 69). Every finding in them was accepted after being reproduced;
none was argued away.

My slips, as recorded where they happened:

- **On three occasions a commit was made before the suite's result was in, with tests
  failing in it**: 2026-11-16 (plan, section 34), 2026-11-17 (section 39), and twice on
  2026-11-19 (section 57), the last because a command joined the test to the commit and hid
  the test's exit code. Each was put right in the next commit and none touched a result;
  but it is one slip made three times. Since the third: the suite's output to a file, its
  exit code looked at, the commit a command of its own — kept in every commit since.
- A sentence of UG470 quoted without its context, and a count given wrong (251 for 159);
  both corrected in commits of their own.
- An account of the prober's behaviour written from memory and wrong (section 60). Since
  then such accounts are checked against the source first.
- Outputs made in another order than the plan had them (section 64).
- An ending not said beforehand, though the step before had shown what leads to it
  (section 67).
- The census program: three places where it took what it was given, and a fourth made in
  mending the third (section 69).

One pattern in the last three: I test what I thought of. What came back from the board and
from review each time was something I had the means to think of and did not list.

## 8. Tests and mutants as S1b closes

- 527 tests; the suite passes (about 105 seconds).
- 598 mutants, none stale. The complete set was last run on 2026-11-18, before S1b.4 went
  on the board: 523 of 523 killed. Since then no line of the prober, of a judge or of the
  chain's rules has changed (the chain driver gained an entry in its table of bounds), and
  the image is the same; what was added — two sets, the census program — had its own
  mutants run, all killed. By section 41 the complete set is not due.
- The prober image has not changed since S1b.3a.

## 9. Findings, and what I recommend

| | finding | I recommend |
|---|---|---|
| F1 | 19 stored result files (`fifo_rate`) are held by no test; and the audit of section 5 was a script run once | make the audit a test: every stored result judged again, its PASS or FAIL the stored one, and from the first run with today's form of verdict on, the whole verdict. Host only, small. **Now, before S1b is closed** |
| F2 | the proposal's text on anomalies (section 6) says what the walk does not do (D1) | a dated note in the proposal, as the other sections have them. **Now** |
| F3 | the Makefile and linker script are outside the closed-book test | add the build inputs to that test. **Now**, with F1 |
| F4 | the proposal's stage table still calls S1b "in progress" | change it when the owner accepts this review, not before |
| F5 | block type 3 is listed as seen from a failed run, `0x02000000` as named | leave, as decided (section 68). If it is ever wanted: one run with a set that allows two standstills a pass; no program changes |
| F6 | the complete set of mutants has not been run since 2026-11-18 | leave: not due, and S2 brings a new image, before whose first run the complete set is due anyway |
| F7 | the single steps' summaries carry no closed-book label (D4) | leave: the census does, and it is what S2 will read |
| F8 | items 6 to 10 of section 6 are not explained | carry to S2 as they are. Item 7 will come up by itself: S2 reads LUT RAM frames and must know whether reading them sets the bit |

## 10. What S2 inherits

- A prober that reads any frame the device names, returns to U-Boot, and a run script,
  judges and a twin that have met the board 185 times.
- The census: for any address S2 wants to read, whether the device names it, its fields,
  and what it read as with the carrier loaded.
- The rule that the walk reads only where the device points, and the quiet wait.
- Open: the AXI path from this program to user logic (not used yet); a probe design of our
  own (the carrier is not it); a new image, and with it the complete set of mutants.
- The unexplained things of section 6.

**For the owner.** Whether S1b is accepted as finished with F1 to F3 done; or what else is
wanted before it is.

## 11. After the owner's word: F1 to F3 done (2026-11-19)

The owner: as recommended — F1 to F3 now.

- **F1. The audit is a test** (`tests/test_evidence_audit.py`, 5 tests). Every run record
  under `evidence/` — 185 — with its result judged again from its raw words by the judge of
  its set: the result is the one whose checksum the board gave; PASS or FAIL is what was
  stored (140 and 44); the stored verdict is word for word what the judge writes now (143),
  or an older form of it in fields the judges were given later (41, in five directories,
  each counted); the one run in which today's judge lists a problem more is named, with the
  problem; and no result or verdict lies under `evidence/` that the audit does not reach.
  Tried on a copy of the directory no test had held: one bit of a result changed, and a
  stored FAIL edited to PASS — each shows.
- **F2. The proposal says what the walk does** about anomalies: a dated note in its
  section 6.
- **F3. The build inputs are under the closed-book test** (`tests/test_s1b2.py`): the
  directory of the prober holds six files and no other; the Makefile's rules name no source
  but those, include nothing and fetch nothing; the linker script pulls in no file; the
  sources include no file of the project's but `sm.h`; and none of the six names the
  database. Tried: a seventh file in the directory fails it.

532 tests. No program of the host or the prober was changed — these are tests and a note —
so no mutants were run: 598, none stale.

Left as recommended: F4 waits for the owner's word that S1b is closed; F5 to F8 stand.

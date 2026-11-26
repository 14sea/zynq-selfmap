# S2 — review of the whole (2026-11-26)

The proposal has S1 to S3 finished and reviewed before S4 is decided (section 7). This is the
review of S2, prepared for the owner, as `docs/s1b_review.md` was for S1b. It is not written
from memory: every statement below was checked against the source, the tests, the stored
evidence or the history of the repository on 2026-11-26, at commit `8555e22`, and where a
check was a program run, the numbers are its output. Nothing was changed for it but this file
and a pointer at the head of the plan.

It ends with findings and what I recommend for each. None of them is acted on here.

## 1. What S2 was to deliver, and what there is

The proposal, section 7: "LUT RAM location: the probe circuit writes known patterns into LUT
RAM through user logic; read back; find where the patterns land. Also settles the readback
mask (GLUTMASK) and the bit order of shift registers." Its output: a "bit table for SLICEM
LUTs (closed-book)".

| asked | there is | where |
|---|---|---|
| where the patterns land | S2.2: 256 bits of block type 0 follow the 256 cells of one slice of LUT RAM, in words 61 and 62 of the frames `0x00401220`–`0x00401223`; the other 12,488,192 bits still. S2.3: each cell has one bit, each confirmed by a run of its own. S2.5: 28,160 cells at 110 sites, each confirmed at every site | `evidence/s2_2_17A6_2026-11-22/`, `evidence/s2_3_17A6_2026-11-23/ram_map.json`, `evidence/s2_5b_17A6/ram_map.json` |
| settles the readback mask | control register 0 reads `0x00000501` (bit 8, `GLUTMASK_B`, set) under the carrier (S2.0), under `s2a` (S2.1 to S2.4) and under `s2b` (S2.5), in every run; and the content is seen. Nothing was written to MASK or CTL0 | S2.0, S2.1, S2.2 |
| the bit order of shift registers | at one site: output a is at the place of RAM address 2 a + 1 as it is, and at 2 a + 2 inverted (a up to 30); the place of address 0 follows output 0 inverted once anything has been shifted in. Every output confirmed | `evidence/s2_4b_17A6_2026-11-23/srl_map.json` |
| a bit table for SLICEM LUTs | three descriptions in this project's own form (`ram_map_v1`, `ram_map_v2`, `srl_map_v1`; the copied schema is not used, by the owner's decision of 2026-11-22), and a rule with five parts, four of which hold at every site measured | the three files above; `evidence/s2_5b_17A6/rule.json` |
| labelled closed-book | every description says `closed-book`. Whether that is the proposal's word for all of them is finding F1 | section 4, D2 |

Beyond what was asked:

- **Question 5 of the proposal** (must the design be stopped for readback?): for LUT RAM that
  is not being written while it is read, no. In S2.2 every address of block type 0 was read in
  three states with the design's clock running; after each of the 24 passes the RAM read back
  through the design as written, and the counter had gone on. The same held in every later
  chain.
- **Question 9** (the PS-to-PL path from a returning program): it works. S2.1 made the first
  access at the U-Boot prompt and 1,164 from the prober; every later run made more.
- **Two predictions made and committed before the board was asked**: S2.4's (`e5bf98e`, 15:11
  UTC on 2026-11-23; the first run of the step `a189c0b`, 16:34) — 128 places of 128; and
  S2.5's (`f692832`, 2026-11-23 21:29; the first run `019184e`, 2026-11-24 19:51) — 432 of 440
  memories, the 8 others at the two sites to the left of every site the rule was read from.
- **The grading** (sections 57 and 58 of the plan): nothing differs. All 28,160 cells of S2.5
  and the 256 of S2.3 lie where prjxray-db puts them; the 256 places of the shift registers
  are content bits of their LUTs; the four parts of the rule hold at all 1,500 sites of this
  kind; by the rule, 253,440 cells at 990 sites not measured lie where the database puts them.

**S2 never wrote configuration memory, and `SEU_EN` was never set.** At PCAP the prober sent
nothing that writes but `CMD` (RCFG, DESYNC) and `FAR`, as in S1b. Beyond the DEVCFG
registers of its transfers it wrote bit 5 of `INT_STS` alone (`0x20`), only after a status
word with that bit had been recorded, and the design's registers by a list the host gave.
Every packet sent and every PL access made is in its run's result, and the judges replay them
(section 3).

## 2. What the result rests on, said once

- **On user logic, read from both sides.** A state is set through the design and read back
  through the design before and after every pass of frames, so what the RAM held is known
  from the design's side and not assumed.
- **On searching the whole of block type 0** whenever something new is looked for: S2.2,
  S2.4 part 1, S2.5 part 1 — all 3,864 addresses in three states each, every other bit still.
  Nothing was looked for only where I expected it.
- **On a run of its own for every cell**: the singles — 256 at one site (S2.3), 128 outputs
  (S2.4), 256 cells at 110 sites at once (S2.5) — each changing its places and no other bit
  read.
- **On the builds' records for names.** Which site a memory is at and which LUT of the site it
  is come from the builds' own records of where Vivado placed them (`pl/*/build.json`). The
  memories of LUT RAM are constrained to a site only; which LUT each went on is what the build
  records.
  In S2.5 which site a place belongs to rests in addition on the word each memory was loaded
  with: the singles write every site at once (the owner accepted this, plan section 50), and
  the description says so in its own text.
- **On one board and three images.** EBAZ4203 `17A6`. Images: `480bbdd4…aa46` (S2.0, S2.1),
  `94ad860c…6f50` (S2.2), `8bf3799c…2a8b` (S2.3 to S2.5; 19,244 bytes, unchanged since plan
  section 32). Designs: the carrier (S2.0), `s2a` (S2.1 to S2.4), `s2b` (S2.5).
- **On a second witness, once.** prjxray-db at commit `0a0added`, three of its files
  (section 3, point 4).

## 3. The four fixed points of the proposal's discipline

**1. The program is checked for safety before it runs, by rule.**

| the proposal says | what there is in S2 | held by |
|---|---|---|
| every device access through a few helpers; the twin logs each; a test holds the log to an allow-list written in the test | as in S1b, the lists extended: four SLCR words read as gates before any PL access (never written); `INT_STS` written with `0x20` alone; the design's registers through two helpers that refuse any address not on the host's list | `test_the_only_registers_touched` (`tests/test_prober_s2.py` among five); `test_nothing_is_written_but_the_transfers_own_words_the_list_and_bit_5` |
| one generator of command packets; a real parser shows a read-only stage produces only reads | three register reads added (IDCODE, CTL0, STAT); nothing else | `host/packets.py`; `tests/test_prober_packets.py` |
| an address envelope and budgets | the frame envelope as before, and a second one: the PL addresses the prober may touch, given by the host and enforced in the prober | `test_an_address_outside_the_envelope_is_not_touched`, `test_an_envelope_that_is_not_inside_the_design_is_refused` |
| the same rules inside the prober; the host replays the logged packets | so; and the judges hold that bit 5 is written only after a status word showed it | `test_bit_5_is_never_written_unless_a_status_word_showed_it`; `test_seu_en_set_stops_the_run_before_anything_is_sent` |
| the image inspected; its hash in the record; an unchecked image is not run | so, for all three images | `tests/test_prober_image.py`; the run script |

**2. The closed-book rule.** Held, with one gap. A test goes through every file of `host/`
and `prober/` for the database's name and for the graders' names, the graders excepted
(`tests/test_s1b2.py`, `test_nothing_but_the_graders_names_the_database`); another holds the
programs of S2, the run script and the prober to name no file of the database
(`tests/test_grade_s2.py`, `ClosedBook`); the two designs are held to name neither the
database nor a frame address (`tests/test_pl_s2a.py`, `tests/test_pl_s2b.py`). The build
script asks Vivado for the names of SLICEM sites and nothing else (plan, section 12,
point 5), and the sites of both designs are in columns of sites numbered 10 or higher, away
from those an earlier project tied to frame addresses. *The gap* (finding F3): section 9 of
the plan says that the test of the sources "for numbers of the part stays and is extended to
the new programs". The name test was extended; the numbers test was not. The prediction and
the rule of S2.5 hold numbers of the part — 36 frames to a column, 50 rows to a half, the
forms 20 to 29 and the one named first, 24 (`host/s2_5_predict.py`, `host/s2_5_rule.py`) —
each said in the program's own text to come from the census or the sites' names, and no test
holds that.

**3. All raw readback archived, unmodified, with digests, before interpretation.** Held. S2
added 53 run records (238 now, 185 at the close of S1b): 52 with a result of their own,
every one PASS, and one with none — the first try of share 1 in S2.2, which lost its prompt
and was set aside (`halted_at_run01/`, plan section 28). The first run of every chain was
committed alone, as it stood, before the chain would start a second; every chain's rest was
committed as it stood before it was read.

**4. Grading afterwards, kept apart.** Held, and checked in the history. Graded once, at the
end of S2, on the owner's word (plan, section 12, point 8). What would be compared, and how,
was committed first (`7af55bf`, 07:38 UTC on 2026-11-26) before the database's files for
slices were opened; the grader and its output came after (`f39a50c`). The four descriptions
graded were last changed on 2026-11-23 and 2026-11-24 (`ace68a0`, `2aee241`, `4db4e98`) and
not since; since `7af55bf` nothing under `evidence/` has changed but the grade's own directory
and the record of its mutants. The grade is in a directory of its own, and the grader is the
only program that names the database. No bitstream was parsed and no Vivado report used.
*One thing to say:* the stored `grade.json` is not the grader's first output. After its
first run the grader was changed in what it reports — the other readings counted whether or
not anything differs, three statements added — and in nothing it compares; the first output
was not kept (plan, section 58, and finding F4).

## 4. Where S2 differs from what the proposal says

- **D1. The form of the description.** The proposal (section 4) has zynq-fabricmap's schema
  "used as it is". S2 writes its own (`ram_map`, `srl_map`), because the copied schema's one
  relation says that the address user logic gives is the index of a truth table, which S2
  does not show. The owner decided this on 2026-11-22; the proposal has it, dated.
- **D2. The label.** The proposal (section 3) labels a result *half-open* when it "also uses
  'what value our own design put there'". Every description of S2 says `closed-book`. For
  S2.3 the content came from user logic, and the label fits. Two things lean on the values
  the designs were loaded with: **which site a place of S2.5 belongs to** — part 1 found each
  memory by its own loaded word, and part 2 wrote every site at once (section 2) — and the
  two predictions, which were read from frames as loaded. The cells within a site, and S2.4's
  table, rest on what user logic did. `ram_map.json` of S2.5 says in its own text how a site
  was found; the label does not. The plan never discusses the label (the word "half-open"
  does not occur in it). Finding F1.
- **D3. Small first.** The proposal (section 6) has every stage start on a small range where
  the answer is known from earlier board work. S2 began with the whole of block type 0 and
  kept its sites away from the columns that earlier work knew — so that nothing I knew could
  meet what the device showed (plan, sections 9 and 12). On purpose, and agreed.
- **D4. Grading before S6.** The proposal has the grading as S6. S2 was graded at its own end,
  as S1b was between its steps, by the owner's decision (plan, section 12, point 8).
- **D5. The complete set of mutants before a new image goes on the board.** S1b had this as a
  rule (`docs/s1b_plan.md`, section 41), and the images of S2.0 and S2.2 met it (plan,
  sections 16 and 27). The owner changed it on 2026-11-23 (plan, section 35) and again on
  2026-11-25 (section 55): the image of section 32 went on the board after the mutants of
  what changed, and S2 was graded after the mutants the tool had never judged. The rest are
  due before S4.
- **D6. Anomalies.** As in S1b (its review, D1): the chains stop at the first anomaly and run
  nothing again. One chain halted once (S2.2, the lost prompt); it was taken up again on the
  owner's word.
- **D7. The proposal's text is behind** (finding F2): question 7 of section 11 still ends
  with "*2026-11-22:* still open", although S2.3, S2.4 and S2.5 answer it; the row of S2 in
  the stage table, after "graded 2026-11-26, nothing differs", still ends "Nothing of S2 is
  graded: once, at its end"; the paragraph at the head is dated 2026-11-24 and speaks of
  2026-11-26; the note on bit 5 among the risks stops at 2026-11-22.

## 5. An audit of the stored evidence

The audit S1b's review made into a test (`tests/test_evidence_audit.py`) judges every stored
run again from its raw words in every run of the suite. In the run of the suite made for this
review (section 8) it holds:

| | runs |
|---|---|
| run records under `evidence/` | 238 |
| with a result of their own | 232; and 4 recovered from the card in S1b, so 236 judged |
| PASS, FAIL | 192, 44 — every one of S2's 52 a PASS, the 44 all of S1 |
| stored verdict word for word what the judge writes now | 236 less the 41 of an older form, all of 2026-11-14 and 2026-11-15, as at the close of S1b |

- **In no run does PASS or FAIL differ from what was stored.**
- Every directory of S2 with a board run has a `RESULT.md` (eight); the two of the card have
  one; the two predictions and the build of `s2b` have a `README.md`.
- Each stored chain of S2 is assessed again from its raw words by a test of its own
  (`tests/test_board_evidence.py`): the candidates, the tables, the descriptions by the rule,
  the predictions scored, bit 5 read by read. Which runs show a status bit outside the usual
  word is pinned by `tests/test_status_seen.py`.
- The test that holds the stored grade to the grader runs only where the database lies
  beside the repository; in a clone it is skipped, and says so.
- Two pieces of results pulled again in S2.5 part 2 and three in part 1, each accepted only
  with the board's checksum; the record of the run says so.

I found nothing under `evidence/` of S2 that no test reaches.

## 6. What is weak, and what is not known

Carried from the plan and the results; nothing here is new, it is in one place.

**About the result itself**

1. That RAM address a is bit a of a LUT's content is not shown by S2 (plan, section 10). The
   grading assumed it, and 28,160 entries agreeing is an argument for it, not a measurement.
2. Which LUT of a slice a memory or a register is, is the build's word, not the device's.
   Which pin carries which address bit is not shown at all.
3. In S2.5 the site of a place rests on the loaded words and the build's record (section 2,
   and D2). The grading holds the build's names against the database and found every entry
   agreeing, so a wrong attribution would have shown; but S2 alone does not exclude one.
4. The shift registers were measured at one site. Four of their cells have three places and
   four one; two places read otherwise before any shift.
5. Not looked at: LUT RAM written while it is read; LUT RAM in any form but `RAM64X1S`; block
   RAM; flip-flops; a LUT used as logic (plan, section 10).
6. What a design reads back as whose bitstream leaves `GLUTMASK_B` clear: not known. Every
   design here set it.
7. One board, one die, one database. Where the board and the database could be wrong alike,
   the grade shows nothing.
8. In the census's numbers each half has 41 columns of 36 frames. By section 53's reckoning
   (two numbers of X to a column) 22 of them hold sites, 15 of those sites of this kind; the
   grading checked the reckoning at those 15 only. What the 19 that hold no site this count
   reaches are, and what the 7 that hold other sites are, was not asked. Since the grading
   neither is a closed-book question for its author.

**Seen and not explained**

9. **Bit 5 of `INT_STS`** (`PCFG_SEU_ERR`). It clears and stays away. In S2 it shows after the
   read that delivers a frame whose content is as loaded (the shift registers' frames as
   loaded or reloaded; the twelve groups of S2.5 as loaded), or one to a few cells away from
   that (S2.3 and S2.5 singles: one cell; S2.4: one to four); not with all zero, all one or a
   code state. Read by read, without exception, over 3,072 records of S2.5's singles. No rule
   is given and nothing rests on it. With S1b's block type 1, columns 2 to 4, it is the one
   thing in this project seen often and understood not at all.
10. The receive-FIFO overflow of S1b: not met in S2 (the wait stores nothing); the mechanism
    is not known.
11. The console losing characters: one run of S2.2 stopped on it; in S2.5 five pieces of
    results were pulled again. The rules for it (ask again for a short read-only reply, never
    resend an act, stop on a lost prompt) were enough.

**Not looked at, because S2 could not**

12. GCAPTURE through PCAP and whether it disturbs a design (the proposal's question 6): S3.
13. Whether writing a located bit changes the LUT: S4.

## 7. The reviews so far, and my own slips

The plan has twelve sections that record a review and what was changed after it (14, 15, 22,
23, 25, 26, 32, 33, 40, 43, 48, 49): 35 findings. Every one was reproduced on the twin or in a
scratch copy, or shown from the code as it was, before it was accepted; none was argued
away. One was the owner's to decide
(section 23, the sixth: a clean copy of the repository runs every test; section 24). Four of
the reviews found something in the prober and made a new image (sections 22, 23, 25 and
32). Of those images, section 25's (`94ad860c…6f50`, S2.2) and section 32's (`8bf3799c…2a8b`,
S2.3 to S2.5) went on the board; those of sections 22 and 23 never did. The tool's own unmutated copy found two faults more (section 54).

My slips, as recorded where they happened:

- **A test that passes in my tree and not in a fresh one, four times**: the first run of the
  mutants did nothing because two test modules read a built image (section 13); a clean copy
  could not run the tests (section 23, the sixth finding); a test that needed a built tree
  (section 32, finding 2); and two tests that passed only where `build/` and the compiler
  already were — pushed so in `d1bbd89`, in the public repository, and found by the tool's
  unmutated copy (section 54). Since section 54: a test that needs a build makes it, and after
  a change to the tool or to such a test the suite is run in a copy made as the tool makes
  its own.
- **A word read and not judged** (section 22): the status after a read of the list was judged
  for bit 5 alone. A rule since S1b, not carried to the new word.
- **A check a review asked of one tool not carried to the next of its kind** (section 23): the
  chain's driver was written from S1b's and not from the census, where a review had asked for
  the check on images two days before.
- **A gap between a check and the act it guards** (section 23, finding 1; my part in it in
  section 25): a register read and then cleared, with nothing asked about what may happen
  between.
- **A loop that ends only because an earlier check holds** (section 31): a mutant of mine let
  a list through, the prober walked past it, and the twin printed without end until the host
  stopped the job. Both are bounded now.
- **Counts and times given wrong**: 452 accesses for 451 and 79 mutants for 77 (section 21);
  a rate of mutants (section 27); mutants called "none stale" without counting again after a
  change (section 16); a mutant prefix reused that made 55 old mutants stale before any run
  (section 39); "eleven columns of sites not measured" where there are four — the list was in
  the repository and I had not counted its columns (section 58).
- **Exit codes**: a line that wraps a run took the code of `date` (section 27), and a
  background command the code of `grep` (section 28).
- **The audit and the status test did not know a new kind of run** until one was stored
  (sections 18 and 36). A run of the twin stored under `evidence/` in a scratch copy, before
  the board, shows it; that has been done before every board step since S2.4.
- **The suite run in a shell that still had the twin's variables set** (section 31): 955
  errors that were none. The older tests do not clear those variables; noted then, not
  changed (finding F5).
- Two of three ways the first access could fail were built and tested, the third not,
  although it was written down (section 14).

The pattern of S1b holds — I test what I thought of — and S2 adds one: what passes where I
work is not yet what passes in a clone, and the place that shows it is the tool's unmutated
copy or a reviewer's fresh checkout, not my tree.

## 8. Tests and mutants as S2 closes

- **1,244 tests** (541 at the close of S1b). The whole suite was run for this review: see the
  last lines of this section.
- **1,697 mutants, none stale** — held for this review against the tree by the tool's own
  rule, without running the tool. Every one has had a verdict from the tool at least once
  (every name of the list held against every record in `evidence/host_checks/`: none
  without one).
- **On the tree as it is now**: 371 — the 355 that had never been judged (section 56) and the
  16 of the grader (section 58), all killed. **The other 1,326** were last judged on
  2026-11-22 (986) and 2026-11-23 (340), all killed then, before the two tests of section 54
  were mended. By section 55 they are run before S4. At the rate section 56 measured, about
  22 an hour at eight at a time, that is about 60 hours.
- The prober image has not changed since section 32.

*The suite, for this review:* in this tree at `8555e22`, with `SELFMAP_NO_BOARD=1` and its output to a
file: `Ran 1244 tests in 638.792s`, `OK (skipped=2)`, exit code 0. Run again on the tree as
committed with this file: the same count, OK.

## 9. Findings, and what I recommend

| | finding | I recommend |
|---|---|---|
| F1 | the descriptions are all labelled closed-book, while S2.5's site of a place and the two predictions rest on what the designs were loaded with, which the proposal calls half-open (D2) | the owner decides what the label means for these. My recommendation: leave the stored descriptions as they are, and say it in a dated note in the proposal's section 3 and in the README's results of S2 — the cells within a site and S2.3's and S2.4's tables closed-book; which site a place of S2.5 belongs to, and the predictions, half-open by section 3's words. Documents only. **Now** |
| F2 | the proposal's text is behind (D7) | dated notes: question 7 answered (S2.3, S2.4, S2.5), the last sentence of the stage table's row of S2, the date at the head, bit 5 among the risks. **Now**; the row's "done" when the owner closes S2, as with S1b |
| F3 | the numbers of the part in the programs of S2 are held by no test, though section 9 of the plan said that test would be extended | a test that holds each such constant of `s2_5_predict.py` and `s2_5_rule.py` to where it is said to come from — 36 to the census's columns, 50 to the rows in the list of sites — and a numbers test over the other programs of S2 as S1b's programs have. Tests only. **Now**, before S3 adds programs of its own |
| F4 | the stored grade is not the grader's first output (section 3, point 4) | leave for S2: section 58 says what changed and that no comparison did. For the next grading (S6): commit the grader's first output as it comes, before any change to what it reports |
| F5 | the older tests do not clear the twin's variables before they start it (section 31) | a setup that clears every `SM_*` variable for the whole suite. Tests only, small. **Now**, with F3 |
| F6 | 1,326 mutants not run on the tree as it is | leave until S4, as section 55 has it. Before the run: say its cost (about 60 hours), and the owner turns off the machine's automatic sleep |
| F7 | bit 5 has no rule (section 6, item 9) | carry to S3 as it is. S3's reads will meet it; the read stage records it already. A step of its own only if the owner wants it understood |
| F8 | the columns of sites below X16 (section 53's open point) | close it: X14 has no site of this kind, and X0 to X8 are answered by the database. A measurement of them now would not be closed-book for its author; I do not propose one |

## 10. What S3 inherits

- A prober that reads any frame the device names and three configuration registers, reaches
  the PL through the gates and by a list, sets states as lists of accesses from the host,
  records bit 5 after every read and clears it alone — image `8bf3799c…2a8b` — and a run
  script, judges, chains and a twin that have met the board 238 times.
- Two probe designs, a build that refuses any design but the one it names, benches, and
  bitstreams on the card.
- Where every LUT RAM bit of a SLICEM site lies: measured at 110 sites, and by a rule the
  database agrees with at all 1,500.
- **GCAPTURE is not in what the prober may send.** The guard accepts `CMD` with RCFG and
  DESYNC only. Adding it is the first point S3's proposal has to put to the owner.
- **Closed-book after the grading, as a fact** (plan, section 58): in the grading the
  database's lines for the flip-flops and multiplexers of these sites were shown as well as
  the LUT lines; the files named `mask_…` and those for routing were not opened. S3 does not
  rest on that: it searches where the device points, says beforehand what it expects, and
  confirms each finding by a run of its own, as S2 did.
- The open things of section 6.

**For the owner.** Whether S2 is accepted as finished with F1 to F3 and F5 done; or what else
is wanted before it is.

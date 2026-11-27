# S3 — flip-flop state: plan (2026-11-26; agreed by the owner the same day, all ten points as recommended — section 12)

S2 found where the content of LUT RAM and of shift registers lies in configuration memory. S3
asks the same of flip-flops: user logic sets a flip-flop to a known value, the state is
captured into configuration memory, the configuration is read back through PCAP, and the
places where the values land are the answer. The proposal (section 7) calls S3 optional and
read-only; one of the first things this document has to say is that capture, by UG470's own
words, is a write by the device into configuration memory cells (section 2), and so the
owner has to decide what kind of step it is.

This document proposes how S3 is cut into steps, the probe design it needs, and details the
first steps. The later steps are outlined; each gets a proposal of its own when the step
before it has answered. The points for the owner are in section 11. **No board run happens
without the owner's word for that step.**

Every statement below about a document was checked against its text on 2026-11-26 (UG470
v1.17, UG585 v1.15), every statement about the prober and the designs against the source at
commit `d30f1d3` and after; the simulation models are those Vivado 2025.2 ships
(`data/verilog/src/unisims/`). Where something rests on general knowledge of the device
family it is marked as that; such things may stand in this document and go into no program
and no judge.

## 1. What S3 is to deliver

The proposal, section 7: "Flip-flop state through GCAPTURE", optional, no write of
configuration memory, its output a "flip-flop bit table (closed-book)". Section 4 says that
flip-flop state has no place in the copied schema and is recorded beside it, in a document
modelled on it. Of the open questions of the proposal's section 11, S3 is where this one is
answered:

| question | in S3 |
|---|---|
| 6. Does GCAPTURE work through PCAP, and does it disturb the design? | S3.1 (does a capture happen at all, and is the design undisturbed), S3.2 (is anything seen) |

And one thing S2 left (`docs/s2_review.md`, section 6, item 9): bit 5 of `devcfg.INT_STS`
shows after reads of frames whose content is one cell away from what was loaded. A capture
changes cells that were loaded; S3 will meet it as a matter of course.

## 2. What is known going in, and what is not

| fact | source |
|---|---|
| "Readback Capture is a superset of Readback Verify—in addition to reading all configuration memory cells, the current state of all internal CLB and IOB registers is read" | UG470, chapter 6 |
| "Users can sample block RAM outputs, and CLB and IOB registers by instantiating the CAPTUREE2 primitive in their design and asserting the CAP input on that primitive while the design is operating. On the next rising clock edge on the CAPTUREE2 CLK input, the internal GRDBK signal is asserted, storing all CLB and IOB register values into configuration memory cells." | UG470, Readback Capture |
| "Register values are stored in the same memory cell that programs the register's initial state configuration, thus sending the GRESTORE command ... after the Capture sequence can cause registers to return to an unintended state." | the same |
| "Alternatively, the GRDBK signal can be asserted by writing the GCAPTURE command to the CMD register. This command asserts the GRDBK signal for two CCLK or TCK cycles, depending on the start-up clock setting." GCAPTURE is CMD code `01100`; RCAP (`00110`) "Resets the CAPTURE signal after performing readback-capture in single-shot mode" | the same; table 5-25 |
| COR0 (register `01001`, read/write), bit 23 `SINGLE`: "0: Readback is not single-shot. New captured values are loaded on each successive CAP assertion on the CAPTUREE2 primitive. Capture can also be performed with the GCAPTURE instruction in the CMD register. 1: Readback is single-shot. The RCAP instruction must be loaded into the CMD register between successive readbacks." Bits 16:15 `SSCLKSRC`, the start-up clock: CCLK, UserClk, JTAGClk | UG470, tables 5-23, 5-30, 5-31 |
| UG470's sample bitstream, for another part, writes COR0 `02003FE5` (bit 23 clear) | UG470, table 5-19 |
| `CAPTUREE2` has the ports `CAP` and `CLK` and one attribute, `ONESHOT`, `"TRUE"` by default | the simulation model Vivado ships |
| The prober reads IDCODE, CTL0 and STAT through PCAP as one word each; it sends nothing that writes but `CMD` (RCFG, DESYNC) and `FAR`, and has never sent GRESTORE | S2.0; `host/packets.py`; `docs/s2_review.md`, section 1 |
| The prober reaches the probe design on `M_AXI_GP0` and makes the accesses a list from the host names, writes only at offsets its image allows (four registers, and the shift registers' data where a set allows it) | S2.1 to S2.5; `docs/s2_plan.md`, section 30, point 5 |
| zynq-xpart established that GRESTORE disturbs a running design | the proposal, question 6 |

Not known:

- **Whether a capture through either way happens at all under this setup**: the PL configured
  by `fpga loadb` through PCAP, the prober in U-Boot's context. What "CCLK" is for a Zynq
  whose PL is configured from the PS, UG470 does not say and I did not find in UG585; for
  GCAPTURE that is what the length of the pulse depends on. `CAPTUREE2` names its own clock.
- **What COR0 holds** on our board, under our designs: so whether captures repeat or each
  needs RCAP. That `ONESHOT` is what sets `SINGLE` is my reading of the two names (general
  knowledge, not from a document read here).
- **Where any flip-flop's cell is.** S2 found LUT content only. Nothing in this project ties a
  flip-flop to a frame address.
- **What the cell of a flip-flop reads back before any capture**: by UG470's sentence, the
  initial state the bitstream gave it; this is not shown yet.
- **Whether a capture disturbs the running design**, or anything else in configuration memory
  (LUT RAM, shift registers). UG470 says nothing of it that I found; the warning it gives is
  about GRESTORE afterwards.
- **What it means for the cells afterwards.** By UG470's sentence a capture overwrites the
  cells that program the flip-flops' initial states. Our runs reload the design before every
  run (`fpga loadb` after a reset), so nothing would carry from one run to the next; within a
  run, nothing the prober does uses those cells but reading them.

## 3. Capture writes configuration memory cells — what kind of step S3 is

The proposal has S1 to S3 as stages that do not write configuration memory, and S3 as
capture. UG470's sentence above says that a capture stores the registers' values into the
cells that program their initial state: the device writes configuration memory, at our
request, at cells we do not choose and the frames of which we do not send. Nothing of a
frame is sent by us, no FDRI, no WCFG, no MASK or CTL0.

That is neither S2's kind of step (only user logic writes) nor S4's (we write frames). I put
it to the owner (point 2) with a recommendation: treat S3 as its own class — allowed under S3,
on the owner's word for each step as always, never with GRESTORE, and with the design
reloaded before every run, which every run does already. The proposal gets a dated note in
its sections 6 and 7 that says what a capture writes. The mutant rule of `docs/s2_plan.md`
section 35, which counts S3 among the stages that only read, is kept for S3 if the owner
agrees with this; the complete set before S4 stays as it is.

## 4. The method, in outline

The mirror of S2, with one step more: after user logic sets a state, the state is captured,
then frames are read.

1. **States.** The probe design holds a few flip-flops that the prober can set and read
   through registers. A *state* is a content of them. The prober sets a state through user
   logic, reads it back through user logic, *captures*, reads it back through user logic again
   (did the capture disturb it?), and then reads frames.
2. **Before any capture.** One pass of frames with no capture at all, so that what the cells
   hold as loaded is on record, and a capture's change can be told from it.
3. **Is anything seen, and where** (S3.2). States all zero, all one, all zero, each
   captured. A bit is a *candidate* if it follows them (or follows them inverted); every other
   bit must read the same in all three, but for the *restless* ones (point 5). The number of
   probe flip-flops is known; the count of candidates must be that.
4. **Which bit is which** (S3.3): code states and their complements, then singles, as in
   S2.3.
5. **Restless bits.** A capture takes every flip-flop of the design, not only the probes: the
   AXI front, the register file, the counter. Whatever of them differs from one capture to the
   next would show as a bit that follows something. Two things stand against it. The design is
   made so that the accesses before every capture end alike (a fixed write, a fixed read, then
   the capture) and the counter can be stopped by a register; and each state is captured
   twice, so that a bit that differs between two captures of one state is restless, listed,
   and kept out of the candidates. A restless bit inside the probes' candidates is a stop.

What the prober does on the board is set states, capture by a write to the design, and read;
the comparing is the host's, from the raw words, after they are saved.

## 5. The steps

| step | the question | PL design | new in it | writes |
|---|---|---|---|---|
| S3.0 | what does COR0 hold, under the carrier and under `s2a`? | the carrier, `s2a` | one more register read header; a new image | nothing |
| S3.1 | does a capture happen, from the design's side, and is the design undisturbed by it? | `s3a` (section 6) | our third design; the first capture; COR0 under it | user logic; the capture (section 3) |
| S3.2 | is flip-flop state seen in readback, where, and does a capture disturb anything? | `s3a` | reading block type 0 in captured states, and once before any capture | the same |
| S3.3 | which configuration bit is which flip-flop, in one slice | `s3a` | code states and singles; the description | the same |
| S3.4 | wider: more sites, other kinds of flip-flop | a second design | how far is decided when S3.3 is in | the same |

One new thing a step, as in S1 and S2: S3.0 has a new packet on known designs; S3.1 a new
design and the first capture, and reads only the reference frame; S3.2 is the first step that
looks for content.

**S3.0** is S2.0 once more, with COR0 (`28012001`, UG470's form of a one-word read of register
`01001`): the carrier, then `s2a`, three readings each, the reference frame first and last.
Its answer decides whether RCAP has to be proposed (point 5). It can be left out (point 4):
S3.2's three states show a single-shot capture by themselves — the second and third would
capture nothing — but only after a chain has been run for nothing.

**S3.1** sets the probes in four states and after each captures once, reading the probes
through the design before and after the capture, the counter before and after, and COR0,
CTL0 and STAT under `s3a`. Its outcomes, said beforehand, include: the capture write does not
return (the board is switched off and on, as for any PL access that hangs); the probes read
otherwise after a capture (a capture disturbs the design: a finding, and the stop of S3 as
planned); COR0 has bit 23 set under `s3a` though the design asks for repeated captures.

**S3.2** has the shape of S2.2: all 3,864 addresses of block type 0, since nothing says where
the cells are; in eight shares, several runs, of the order of an hour of board time, an
estimate from S2.2's. Whether block types 1 and 2 are read too is a point of its own proposal.

**S3.3** and **S3.4** are outlined only. S3.3 reads where S3.2 found candidates and the rest
of their columns. S3.4's breadth — more sites, a column, the other flip-flop primitives — is
decided after S3.3, as S2.5's was after S2.3.

## 6. The probe design `s3a`

Our own, in `pl/s3a/`, built as `s2a` and `s2b` were (Vivado 2025.2; the build's record; the
bitstream an opaque file known by its hash).

- **Eight flip-flops in one slice**, `FDRE`, placed by the constraints on the slice's eight
  flip-flop positions (that a slice has eight is general knowledge; the build shows it: Vivado
  refuses a placement that cannot be). Their initial values fixed in the source by a rule, not
  all alike, so that S3.2's pass before any capture can show where the initial values lie, if
  it does (a half-open finding: it uses what our design put there). A register write loads all
  eight from the data; a register read gives them.
- **The site** by the rule S2 used: a column of sites numbered 10 or above, a row fixed by a
  rule and not by where I expect anything. Whether it should be a SLICEM site S2 measured, a
  SLICEM site it did not, or a SLICEL site, is point 7.
- **`CAPTUREE2`**, its clock FCLK0, `ONESHOT` `"FALSE"`, its `CAP` a pulse of one clock made by
  a register write. No other way to capture is in the design.
- **The counter stops** while a register bit says so, so that a capture finds it still.
- **The same eight register offsets as `s2a`**, the probes, the capture and the stop put on
  offsets the image already allows to be written, so that the image of S3.0 runs this design
  as the image of S2.3 ran `s2b`. The identification word is another.
- **Nothing else that is a changeable memory cell** but the flip-flops a register file needs:
  no LUT RAM, no shift register, no block RAM, no I/O pin. The build script fails unless the
  eight probes are on their positions, exactly one `CAPTUREE2` exists, and no RAM or
  shift-register primitive does; it writes the bitstream and a record of hashes, and no logic
  location file, no mask file, no report that anyone opens.
- **A bench** under iverilog, with a model of the AXI3 master as before. The capture itself
  is not simulated (the model of `CAPTUREE2` does nothing but check its timing); the bench
  shows that one register write makes one pulse on `CAP`.

## 7. The discipline in S3: what stays and what changes

**Stays.** The four fixed points of the proposal's section 6. Save first, judge afterwards;
the judge re-derives everything from the raw words; a stop is a stop. The prober sends nothing
to PCAP that writes configuration memory or any register but `CMD` (RCFG, DESYNC) and `FAR`;
**never GRESTORE**; `SEU_EN` never set. No board run without the owner's word for that step.
The host runs no mutants while the board is in use.

**Changes, each for the owner to accept:**

- *Capture* (section 3). With `CAPTUREE2`, it is a write to the design, at an offset the list
  allows; the prober's packets do not change. With GCAPTURE it is a new kind of packet, a
  `CMD` write the guard and the parser would have to accept (point 3).
- *One more register read* (COR0) and so a new image, if S3.0 is done.
- *Restless bits* in the judge (section 4, point 5): a bit that differs between two captures
  of the same state is not a candidate; it is listed, and the count of them is part of the
  result.
- *Closed-book, as a fact* (`docs/s2_plan.md`, section 58): in the grading of S2 the
  database's lines for the flip-flops of the sites of this kind were shown along with the LUT
  lines; the numbers in them were not written down and are not looked at again. Section 57
  said then that anything measured afterwards is no longer closed-book for its author and
  would have to say so: the descriptions of S3 will. What keeps S3 honest is what kept S2: the
  search over the whole of block type 0, what is said and committed beforehand, a run of its
  own for every finding, and the tests that keep the database's name and the part's numbers
  out of the programs (`tests/test_s2_numbers.py` is extended to the programs of S3).
- *Grading* once, at the end of S3, on the owner's word, as S2 (point 9).

## 8. What S3 will not show

- IOB flip-flops, block RAM outputs (UG470 names both as captured), latches, the flip-flops of
  other kinds of tile.
- Which flip-flop of a slice a probe is, beyond the build's record of where it was placed; the
  clock enable, set and reset of a flip-flop and where their configuration lies.
- That writing a located cell sets a flip-flop's initial state: that would be a write, S4's
  kind.
- Another die. One board, as in S1 and S2.

## 9. What it costs

- **Host:** the prober's COR0 read (if S3.0) with its twin, judge, set and tests; the design
  `s3a`, its bench and build; the twin's model of capture (a switch for each outcome of
  S3.1 the prober can meet); the judges and chains of S3.1 and S3.2, the restless bits among
  them; tests and mutants; a review before each board step.
- **Board:** S3.0 two short runs; S3.1 one; S3.2 of the order of an hour; S3.3 less than an
  hour, as S2.3. Then S3.4.
- **Mutants:** by `docs/s2_plan.md` sections 35 and 55: the mutants of what changed after each
  change; the never-judged before S3 is graded; the complete set before S4.

## 10. What is carried in from S2

- The prober, the run script, the chains, the twin, the census; the image `8bf3799c…2a8b`, to
  be replaced if S3.0 is done.
- Where every LUT RAM bit of a SLICEM site lies. S3 does not use it to choose where it
  reads; it may use it afterwards to say whether a candidate of S3.2 falls on a LUT RAM bit
  (it must not: the design has none).
- Bit 5, recorded after every read and cleared alone. S3 reads frames whose cells a capture
  changed; where bit 5 shows is recorded as before and nothing rests on it.

## 11. For the owner

1. **The cut into steps** (section 5): S3.0 the COR0 read, S3.1 the design and the first
   capture, S3.2 the search, S3.3 the table, S3.4 wider — each of the last three with a
   proposal of its own.
2. **What kind of step a capture is** (section 3). I recommend: its own class — allowed
   under S3 on the owner's word for each step, never with GRESTORE, the design reloaded before
   every run (as now); a dated note in the proposal's sections 6 and 7; S3 kept among the
   stages that only read for the mutant rule. The other way is to treat it as S4's class and
   hold S3 until the go-ahead the proposal reserves for the first write.
3. **How a capture is made.** I recommend `CAPTUREE2` in the design, triggered by a register
   write: the prober's packets stay as they are (`CMD` with RCFG and DESYNC only), the clock of
   the capture is the design's own, and the capture is an access on the list like any other.
   The other way is GCAPTURE through PCAP, as the proposal's table names it: a new kind of
   `CMD` write for the guard and the parser, with a pulse whose length depends on a start-up
   clock not known here. The proposal's row of S3 gets a dated note either way.
4. **S3.0, the COR0 read** — a new image for one word. I recommend doing it: it says
   beforehand whether captures repeat, and the cost is a step of the size of S2.0. Without it,
   S3.2 would find out after a chain.
5. **RCAP.** Not proposed. If COR0 has `SINGLE` set under `s3a`, RCAP becomes a proposal of
   its own (a `CMD` write that, by UG470, resets the capture signal and writes no cell).
6. **The design `s3a`** as in section 6: eight `FDRE` in one slice, initial values by a rule,
   `CAPTUREE2` with `ONESHOT` `"FALSE"`, a counter that can be stopped, the offsets of `s2a`.
7. **Where the slice is.** I recommend a SLICEM site in a column S2 measured, at a row S2 did
   not probe, chosen by a rule: the flip-flops of the same kind of site as S2's LUTs, and
   nothing of S2's result used to choose it. Other ways: a SLICEL site (a site S2 says nothing
   of), or both at once.
8. **Restless bits** as in section 4, point 5: two captures of every state; a bit that differs
   between them listed and kept out; a restless bit among the probes' candidates a stop.
9. **Grading once, at the end of S3**, on the owner's word, as S2 — and only after its
   results are stored and committed.
10. **Documents**: UG470 and UG585 as before, and the simulation models Vivado ships for
    `CAPTUREE2` and `FDRE`. No other document.

If this is agreed, the next thing built is the host side of S3.0 (if point 4 is agreed):
the COR0 read in the generator, the guard, the parser, the twin, a judge and a set; then its
"as built" section here and the owner's review, and only then, on the owner's word, the board.

## 12. Decisions (owner, 2026-11-26)

The owner: all ten points of section 11 as recommended, and begin.

1. **The steps** as in section 5: S3.0, S3.1, S3.2, S3.3, S3.4; the last three each with a
   proposal of its own.
2. **A capture is a class of its own**: allowed under S3, on the owner's word for each step,
   never with GRESTORE, the design reloaded before every run. The proposal says so in a dated
   note (sections 6 and 7). For the mutant rule S3 stays among the stages that only read
   (`docs/s2_plan.md`, section 35, point 2); the complete set before S4 stands.
3. **Capture by `CAPTUREE2` in the design**, triggered by a register write. GCAPTURE is not
   added to what the prober may send; its packets stay `CMD` with RCFG and DESYNC, and `FAR`.
4. **S3.0, the COR0 read, is done**: a new image.
5. **RCAP is not proposed**; it becomes a proposal of its own only if COR0 has `SINGLE` set
   under `s3a`.
6. **The design `s3a`** as in section 6.
7. **Its slice**: a SLICEM site in a column S2 measured, at a row S2 did not probe, chosen by
   a rule.
8. **Restless bits** as in section 4, point 5.
9. **Grading once, at the end of S3**, on the owner's word.
10. **Documents**: UG470, UG585, and Vivado's simulation models of `CAPTUREE2` and `FDRE`.

The host side of S3.0 is built next. Its account follows here as a section "as built" before
anything is put to the owner for review.

## 13. S3.0 as built (2026-11-26; host side, nothing on a board yet)

What section 5 and point 4 of section 12 asked for: one word of COR0 read through PCAP, beside IDCODE, CTL0 and
STAT, under the carrier and under `s2a`. Nothing else in the prober changed.

### What was built

- **The prober** (`prober/sm.h`, `prober/sm_core.c`): the read header `W_RD_COR0_1` = `28012001` (UG470 table 6-1
  with COR0's address `01001` of table 5-23, one word); `REG_COR0` as the fifth choice an operation may make, so that
  `N_REGS` is 5; the generator sends that header for it; the guard accepts that header as the fifth of its list of
  one-word register reads and nothing more. It still sends nothing that writes but `CMD` (RCFG, DESYNC) and `FAR`.
- **A new image**: 19,260 bytes, sha256 `18cd254d4915518a369bccf4ed80cecb677b4c67bfc02abff2a224c8eccf5557`, crc32
  `ec805203` (section 32's of S2 was 19,244 bytes, `8bf3799c…2a8b`). One literal more in it, the header; the test of
  the image's literals accounts for it (`CONSTANTS_S3_0`).
- **The reader** (`host/packets.py`): COR0 is the fifth register a read-only stage may read one word of. MASK and
  COR1 stay among those that are not.
- **The twin** (`prober/twin_hal.c`): answers a one-word read of COR0; what it holds is `SM_CREG=…,cor0:V`. Its default
  is made up — the word UG470's sample bitstream writes for another part, `02003FE5`.
- **The judge** (`host/s2_judge.py`, the judge of stages 6 and 7): COR0 is a register of its table, its read held to
  the pinned stream with its header; like CTL0 and STAT it has no known answer and must read the same every time. Its
  value is reported with every field of UG470's table 5-31 by name, the bits no field names, SINGLE (bit 23) said in
  words, and the start-up clock (`SSCLKSRC`, bits 16:15) by its name.
- **Two sets** (`host/s1a_run.py`; written with the others by `tests/test_prober_image.py`): `s3_0` is the set of S2.0
  with a fifth operation, COR0 — the carrier loaded, five operations three times, 17 records; `s3_0b` the set of
  S2.1 with a fourth — `s2a` loaded, the gates and the design's sequence of S2.1, four operations three times, 14
  records. Their judges are S2.0's and S2.1's. Nothing else in either set differs from the set it is made from
  (the tests say which words).

### What the first run of the whole suite showed, and what was changed for it

The suite with the new image failed six tests, all for one reason, and ran 30 minutes instead of about 11. S2.5's
part 2 takes the stored runs of part 1 again before it builds on them (`s2_5_chain.taken_again`, sections 48 and 49
of `docs/s2_plan.md`), and held them to the set as the build writes it now — which since this image names another
image than the one kept with part 1's runs. So the stored part 1 "did not stand": the stored chain of part 2 could
not be assessed again (`tests/test_board_evidence.py`), nor the stored runs of part 2 audited
(`tests/test_evidence_audit.py`, five tests sharing one preparation).

That is the check doing what it was made for, in a case it was not made for: a stage closed on one image, read again
under another. **Changed** (`host/s2_5_chain.py`): part 1's runs are held to the set kept with them — copied beside
the runs before the first run, as every chain's procedure has it — and that copy must be the build's set in every
word but the three that say which image it is (`IMAGE_WORDS`); where no set is kept, the build's is taken, as
before. A kept set that cannot be read, or that differs in anything else, is a reason part 1 does not stand. Two
tests (`tests/test_s2_5_part2.py`): with the build's own set kept, part 1 stands; with a kept set that names another
image, the kept image is held to it and fails; with a kept set differing in a parameter, in the design or in a word
added, or not readable, part 1 does not stand and says why; and the part 1 the board made stands under the image of
S3.0.

Why the failing suite took 30 minutes: not the image, and not the long comparison I first took it for (a run with
unittest's comparison output cut short took as long). Two training jobs of another project had been running on this
machine since about 12:35 UTC, about sixteen of its twenty processors between them; the two slowest test modules,
run on a copy of the tree as it was before S3.0 (`9c0255a`), took as long as on this one (457 and 533 seconds). They
were not stopped: they are not this project's.

### Tests

1,264 (13 new: 11 in `tests/test_prober_s3_0.py`, 2 in `tests/test_s2_5_part2.py`). The whole suite, with
`SELFMAP_NO_BOARD=1`: in this tree, 1,264 OK (2 skipped); in a copy made as the mutants tool makes its own (no
`build/`, `XGCC` named, a `TMPDIR` of its own), 1,264 OK (4 skipped) — each in about 38 minutes, for the reason above.

### Other tests changed by the new register

- Three tests used register 4 as "a register that is not on the list" (`tests/test_prober_s2.py`,
  `tests/test_s2_host.py`, `tests/test_prober_packets.py`); since COR0 is 4 they use 5.
- `tests/test_prober_packets.py`: the list of registers both the guard and the reader take is five; a write to COR0
  is among the writes both refuse.
- `tests/test_s2_host.py`: the judge's case of "a header that reads another register" uses COR1, and a COR0 header in
  CTL0's place is now on the list but still not the stream the plan has.
- `tests/test_s2_4_host.py`, `tests/test_s2_5_host.py`: they held the build's image to be section 32's ("no new
  one"). S2.4 and S2.5 ran on that image, and the stored runs say so (`tests/test_board_evidence.py` holds it); the
  build's image is S3.0's.
- New: `tests/test_prober_s3_0.py`, 11 tests — the stream, the guard and the reader, a register beyond COR0 refused
  as a parameter, the judge's report of COR0 (a word made up with SINGLE clear and the start-up clock CCLK; one with
  SINGLE set, another clock and a bit no field names), a COR0 that reads otherwise once, both sets word by word
  against the sets they are made from, and a twin run of each set's own parameter words judged PASS. The image is
  pinned there.

### Mutants

1,720 in the list, none stale by the tool's own rule. **23 are new** — 19 of S3.0 (the header, the generator, the
guard, the list of registers, the reader, the judge's report, the two sets) and 4 of the change to `taken_again` —
and the anchors of six older ones were on lines that changed: their anchors follow the lines, and two of them, which
asked whether COR0 is refused, now ask it of COR1 under new names. **The tool has run none of them**: the owner
(2026-11-26) — not now. By section 55 of `docs/s2_plan.md` every mutant the tool has never judged is run before the
stage is graded; these are among them.

### For the board, when the owner says

The card holds `carrier.bit` and `s2a.bit` already; the image goes by YMODEM, as it does in every run. A precheck as
before every step. Then one run of `s3_0` (the carrier), its result stored and committed as it stands and reported;
then, on the owner's word of its own as in S2.0 and S2.1, one run of `s3_0b` (`s2a`). What is said beforehand is
section 6 of `docs/s2_plan.md` for S2.0 and section 7 for S2.1, with one thing more for each: COR0 reads the same
three times, and what its bit 23 says is the finding — section 5 above says what follows from either answer.

## 14. The external review of S3.0, and what was changed for it (2026-11-27; host side, nothing on a board yet)

The owner brought an external review of `73089a0`. It names nothing that stands in the way of a board run — the header,
the guard as compiled, the fields of table 5-31, the two sets and the dry runs are as section 13 says — and five things
wanting (F1 to F5 below). Each was reproduced against the source before it was taken; all five stand, two of them with
a correction of degree. A sixth (F6) was found while the others were mended. What the review says it verified was
not verified a second time here.

### F1 — a kept set that is no record, or that the system will not give, was an exception of the program

`s2_5_chain.taken_again` (section 13) caught `ValueError` alone when it read the set kept with part 1's runs, and then
asked what it had read for its words. Reproduced: with `expected_s2_5f.json` holding `[]`, `null` or `123` it raised
`AttributeError`; with a file the system refuses to give, `PermissionError`. Neither let anything through — the run
script stops on either — but a reason was owed, as the same file gives one a few lines above and below
(`(OSError, ValueError)`, then "is not a record"). **Changed**: `OSError` is caught with `ValueError` ("is not a file
that can be read"), and what was read must be a record ("is not a set"). One test
(`tests/test_s2_5_part2.py`): the four that are no record, through `taken_again` and through the run script's
`known_for`; and a kept set that reads until the system refuses it.

### F2 — the run script's entry for `s3_0b` was held by no test

The test of the twin run named its own judge and its own file, and only `s3_0`'s entry was held to S2.0's judge.
Reproduced: with `"s3_0b": {"judge": s2_0_judge, …` the whole suite passed — 1,264 OK (4 skipped) in a scratch copy,
a look of mine and not the tool's verdict. Of degree: on the board that entry would not have passed unseen — a run of
`s3_0b`'s set given to S2.0's judge is INVALID ("sizes do not add up for a stage-6 result"). **Changed**
(`tests/test_prober_s3_0.py`): `s3_0b`'s judge is held to S2.1's; the twin run of each set is judged by the judge and
read from the file the run script's entry names, and its record count is held (17, 14); and a new test runs the dry run
of each stage and holds what it would send — the image of S3.0, the one design of the stage (`carrier.bit`,
`s2a.bit`), the stage's number, the number of operations, three passes, the prober's size, the layout's header (64,
2640), and that the design's identification register is read at the prompt for `s2a` alone.

### F3 — fields of COR0 no test had set

No word of the tests had PWRDWN_STAT, DRIVE_DONE, OSCFSEL or bit 26 set, nor SSCLKSRC `11`; SINGLE was held as a word
said of it and not as the field. Reproduced, as a look of mine: PWRDWN_STAT read from bit 26, DRIVE_DONE from bit 26,
OSCFSEL five bits wide, and SSCLKSRC `11` called CCLK each passed `tests/test_prober_s3_0.py`. The fields are a report
and decide nothing; they are stored with the result, and a field read and not held is not checked. **Changed**: a
word with every one of them set (`0DD5D58B`: bits 27, 26, 24, 23; OSCFSEL `101010`; SSCLKSRC `11`; the cycles 5, 2,
6, 1, 3) is held field by field, with all ones and all zeroes; SINGLE is held as the field too. And one thing the
reproduction showed besides: the bits the table names are added up, which is their union only while no two fields
share a bit (a mutant that set two fields on one bit carried into a third). The table is right; a test now holds
that its fields lie apart and leave exactly 26 and 28 to 31 unnamed, as UG470's table 5-31 has them reserved.

### F4 — the mutants of S3.0, and the rehearsal

The review is right that the rule asks for them before the board: point 1 of section 35 of `docs/s2_plan.md` is "after
every change the mutants of what changed", and point 2 lets an image on the board with that. Section 13 named only
section 55 (before grading). Of degree: they are not quick — the tool runs the whole suite for each, about 25 an hour
at eight at a time. **The owner (2026-11-27): the increment only.** That is the 23 of section 13, the 6 older ones
whose anchors moved with S3.0, and the 15 of this section — 44; their run and its record follow this section's commit
and are reported under "Mutants" below. The 1,326 the tool has killed before stay where section 55 puts them: before
S4.

The rehearsal (`docs/s2_review.md`, section 7: a twin run stored under `evidence/` in a scratch copy and the whole
suite run there, before every board step since S2.4) was not named in section 13. It belongs to the board step and is
done when the owner has given the word for it, before the precheck; a run stored is one more in the count
`tests/test_evidence_audit.py` holds (238 now), in the commit that stores it.

### F5 — what is said beforehand, two documents behind, and the old chains' own commands

**What is said beforehand of the two runs.** Section 13 pointed to sections 6 and 7 of `docs/s2_plan.md` and added one
line. Said in full, before either run:

- *Both runs.* The outcomes of section 6 (for `s3_0`) and of section 7 (for `s3_0b`) of `docs/s2_plan.md` hold as
  written. IDCODE, CTL0 and STAT are expected as S2.0 and S2.1 read them on 2026-11-20 — `13722093`, `00000501`,
  `46107ffc`, the same under both designs. The judge holds IDCODE to the known word; a CTL0 or a STAT that reads
  otherwise than then, the same three times, is a finding and not a failure, and nothing is concluded from it without
  the owner.
- *COR0 reads the same three times.* If not, the run fails (the judge: it does not read the same every time), and
  what it read each time is in the result.
- *COR0 has bits set that table 5-31 does not name* (26, 28 to 31), or a field holds something the table has no word
  for: recorded as read, as outcome 7 of S2.0 was for CTL0; nothing is concluded from it.
- *Bit 23 (SINGLE).* Either value is the finding. Clear: captures repeat, as the design `s3a` will ask. Set: RCAP
  may become a proposal of its own — decided by what COR0 reads under `s3a` in S3.1 (section 5), not here.
- *COR0 under `s2a` is not what it was under the carrier* — in bit 23 or anywhere else. A finding, not a failure, as
  outcome 7 of S2.1 was for CTL0: COR0 is a register the bitstream writes (UG470's sample bitstream does, table
  5-19), the carrier was built in another project and `s2a` here. It would say that S3.0 cannot answer for `s3a`,
  which S3.1 reads for itself in any case.

**Two documents were behind.** `README.md` said S3 was not started and counted 1,244 tests; `proposal.md` said S3 to
S6 had not been begun. Both now say what is so: S3 planned and agreed, S3.0 built and reviewed on the host and not
on a board.

**The old chains' own commands.** `host/s2_5_chain.py --dir evidence/s2_5_17A6` without `--go` — a look at a stored
chain, which sends nothing — says "halted" and "it does not stand" since the image changed: it holds the stored runs
to the set of the build. Reproduced; `host/s2_4_chain.py` on its stored chain says the same, and so will every chain
that is given the build's set. **Not changed**: these are the commands that made the chains, the stages are closed, and
nothing reads what they print; what takes a stored chain again for use is `taken_again` and the tests of the stored
evidence, which hold the runs to the set kept with them. Whoever looks at a closed chain with its own command under a
later image is told here what the answer means.

### F6 — the tests of the sets were made ready once for their class (found here, not by the review)

`TheSetsAndTheImage` in `tests/test_prober_s3_0.py` made the image and the sets ready in `setUpClass`, by
`test_s1b2.the_set()`, which runs the image's own tests. Where one of those fails — as it does for a mutant of the
prober — the class's tests did not run at all, the suite counted fewer tests, and the mutant tool calls that a mutant
that did not build. It is the fault of section 25 of `docs/s2_plan.md`, which a test holds every test file to; that
test looked for the image's tests by name and did not see them called through `the_set()`. Reproduced on `73089a0`
in a scratch copy: with `W_RD_COR0_1` naming COR1 the file ran 7 tests of 11. **Changed**: the class makes ready
before every test (`setUp`; the work is done once, `the_set()` keeps what it made or its error), and stages the
designs there too, for a tree that has none staged; the rule's test (`tests/test_stage_designs.py`) now refuses
`the_set(` in a class's or a module's preparation as well. No other class had it.

### Tests

1,268 (4 new: three in `tests/test_prober_s3_0.py` — every field from its own bits, the fields apart, the dry run of each
stage — and one in `tests/test_s2_5_part2.py`). The whole suite, with `SELFMAP_NO_BOARD=1`, in this tree: 1,268 OK (2
skipped), in about 13.5 minutes. In a copy made as the mutants tool makes its own it is the tool's first step, with
the run below.

### Mutants

1,735 in the list, none stale by the tool's own rule. **15 are new**: three of F1 (the system's refusal not caught;
a kept set that is no record asked for its words; such a set taken for the build's), three of F2 (`s3_0b` judged as
stage 6; either stage running the set it is made from) and nine of F3 (PWRDWN_STAT, DRIVE_DONE and DONE_PIPE read
from bit 26; OSCFSEL narrower, and a bit higher; SSCLKSRC one bit wide, `11` called CCLK, `10` called UserClk;
GWE_CYCLE two bits wide).

**The tool's run of the 44 of the increment** (added 2026-11-27, after this section's commit `2068eb6`, on which it
ran): the unmutated tree in the tool's own copy 1,268 OK (4 skipped); **44 judged, 44 killed, none survived**, every
one with all 1,268 tests run — among them the mutants of the prober that F6 would have left with fewer; the eight
copies restored and passing. `evidence/host_checks/mutants_2026-11-27_s3_0_increment.txt`. The tool takes one
substring of a name, and no substring gives these 44: the tool was loaded, its `taken` replaced by one that gives the
44 by name, and its `main` run — everything else the tool's own; the record's first line names them. It took 4 hours
39 minutes, not the two I had said: three jobs of another project ran on this machine for about three hours of it.
Before the run, as a look of mine and not the tool's verdict, each of the 44 had failed the test files of its own
part in a scratch copy.

**Not run**: the other 1,691 of the list. The tool has judged every one of them before, as they stand, on an earlier
tree (the records in `evidence/host_checks/`); of what they mutate, this section changed `host/s2_5_chain.py` and
`host/s2_judge.py` by a few lines each. They are run with the complete set before S4 (point 4 of section 35 of
`docs/s2_plan.md`).

### For the board, when the owner says

As section 13 has it, with what is said beforehand above and the rehearsal named under F4. Nothing in this section
changed the prober: the image is section 13's, 19,260 bytes, sha256 `18cd254d…5557`, crc32 `ec805203`.

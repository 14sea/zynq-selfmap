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

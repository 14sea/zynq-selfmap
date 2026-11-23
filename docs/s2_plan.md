# S2 — LUT RAM location: plan (2026-11-20; agreed by the owner the same day, all ten points as recommended — section 12)

S1b said which frame addresses the device has. It stood behind no content: three frames in four
are all zero, and nothing in S1 tells one bit of a frame from another. S2 is the first stage in
which the device is asked what a bit is. User logic writes known patterns into LUT RAM, the
configuration is read back through PCAP, and the places where the patterns land are the answer.

This document proposes how S2 is cut into steps, describes the probe design it needs, and
details the first two steps. The later steps are outlined; each gets a proposal of its own
when the step before it has answered. The points for the owner are in section 11 and what
the owner decided in section 12. **No board run happens without the owner's word for that
step.**

**Where S2 stands (2026-11-23).** The host side of S2.0 and S2.1 is built (section 13). A
review of it found one fault in the run script, and a review of the mending two more; all
three are mended (sections 14 and 15). The complete set of mutants has been run, and the
mutants of the run script on the script as it is now (section 16). **S2.0 has been on the
board: PASS, and control register 0 has bit 8 set — LUT RAM is not masked in readback, by the
register's word (section 17).** **S2.1 has been on the
board: PASS — the first access to our own design returned, and the design is a RAM from its
own side (section 18).** **S2.2 is proposed in full in section 19 and agreed, all eight
points as recommended (section 20); its host side is built and waits for the owner's review
(section 21) — its mutants have not all been run. A first review found one fault, mended
(section 22): the status read after a read of the list was judged for bit 5 alone. A second
found six; five are mended (section 23), and the sixth on the owner's decision (section 24):
a clean copy of the repository now runs every test. A third found four, all mended
(section 25): stage 8 no longer clears an error bit at any time. A fourth found three in the
chain's driver, mended without a new image (section 26). The complete set of mutants has
been run on that image — 1,015, all killed in the end, after one survivor in the chain that
now has its test (section 27).** **S2.2 has been on the board: the chain of eight runs is
complete — 256 bits of block type 0 follow the RAM, as many as it has cells, in four frames
next to each other; every other bit is still; reading does not disturb the RAM; bit 5 of the
status showed after two reads that are not of those frames (section 28).** **S2.3 is
proposed in full in section 29 and agreed, all eight points as recommended (section 30).
Its host side is built and waits for the owner's review (section 31): a new stage of the
prober and so a new image, the judge, the table, the chain. A review of it found five
things, all reproduced and mended (section 32) — one of them in the prober, so the image
is new again. A review of that found three small things more, mended without a new
image, and I found one of my own while preparing the mutants: a mutant could lead a test
to the board's console (section 33). The tool has run the 324 mutants of S2.3 and none survives (section 33,
at its end). The owner then decided that the code run is held to the CTL0 S2.2's runs
read, and a run under another halts the chain there (section 34; host side only, the
image is the same). The complete set has not been run for the new image, and by the
owner's rule of 2026-11-23 it is not due before the board: once before S2 is graded, and
before the first write (section 35). **S2.3 has been on the board (2026-11-23) and is
complete: every cell of the RAM has one bit, the 256 are the places S2.2 found, and each
is confirmed by a run of its own (section 36).** S2.4 and S2.5 are not proposed in full yet.

Every statement below about a document was checked against its text on 2026-11-20 (UG470
v1.17, UG585 v1.15, UG908 v2026.1), every statement about the prober against its source at
commit `a6dac1d`. Where something rests on general knowledge of the device family it is marked
as that; such things may stand in this document and go into no program and no judge.

## 1. What S2 is to deliver

The proposal, section 7: "LUT RAM location: the probe circuit writes known patterns into LUT
RAM through user logic; read back; find where the patterns land. Also settles the readback
mask (GLUTMASK) and the bit order of shift registers." Its output: a "bit table for SLICEM
LUTs (closed-book)". It does not write configuration memory: only user logic writes.

Of the open questions of the proposal's section 11, S2 is where these are answered or met:

| question | in S2 |
|---|---|
| 4. Is LUT RAM masked in PCAP readback? | S2.0 reads the register that says so; S2.2 tests it on LUT RAM itself |
| 5. Must the design be stopped for readback? | S2.2: does a read of the frames change what user logic then reads from its RAM, and does the design go on running |
| 7. How are shift-register and LUT-RAM bits laid out within the 64 bits? | S2.3 (LUT RAM), S2.4 (shift register) |
| 9. The PS-to-PL path under a returning program | S2.1 |

And one thing S1b left: whether reading a frame sets bit 5 of `devcfg.INT_STS` when its
content is no longer what was loaded (`docs/s1b_plan.md`, section 53, item 2). S2 reads such
frames as a matter of course.

## 2. What is known going in, and what is not

| fact | source |
|---|---|
| The device names 5,256 frame addresses; block type 0 has 3,864 in two rows of 56 columns. Reading them is repeatable | `census/frame_census_17A6.json` |
| The prober reads any frame the device names, reads the address register, returns to U-Boot; the run script saves first and judges afterwards | S1, 185 stored runs |
| Bit 8 of control register 0, `GLUTMASK_B`: "Global LUT mask signal. Masks any changeable memory cell readback value. 1: Does not mask changeable memory cell readback values. 0: Masks changeable memory cell readback value, such as distributed RAM or SRL (default)." | UG470, table 5-27 |
| "Writes to the CTL0 and CTL1 registers are bit-masked by the MASK register." | UG470, the MASK register |
| The sample bitstream printed there, for another part (XC7K325T), writes MASK `00000401` then CTL0 `00000501`, and near its end MASK `00000501` then CTL0 `00000501` — the second pair covers bit 8 and sets it | UG470, table 5-19 |
| CTL0 (address `00101`) and IDCODE (`01100`) are read/write registers, STAT (`00111`) is read-only. "To read registers other than STAT, the address specified in the Type 1 packet header in step 2 of Table 6-1 should be modified" | UG470, table 5-23 and the text after table 6-1 |
| A readback that is asked for reads "all configuration memory cells, including the current values on all user memory elements (LUT RAM, SRL, and block RAM)"; and of verifying: "Certain bits within the readback data stream must not be compared, because these can correspond to user memory, such as block or distributed RAM, SRLs" | UG470, chapter 6 |
| `M_AXI_GP0` is the address range `4000_0000` to `7FFF_FFFF`; "The PL level shifters must be enabled via LVL_SHFTR_EN before PL logic communication can occur" | UG585 |
| `SEU_EN` is bit 8 of `devcfg.CTRL`: "enables an automatic lockdown of the PS when a PL SEU is detected" | UG585, register reference |
| As U-Boot leaves `17A6`: `FPGA0_CLK_CTRL` `00400800` (50 MHz), `PLL_STATUS` `0000003f`, `FPGA_RST_CTRL` `00000000`, `LVL_SHFTR_EN` `0000000f`, the SLCR locked, the MMU and both caches on | `evidence/ret2uboot_17A6_2026-11-13/RESULT.md` |
| `M_AXI_GP0` is an AXI3 master. A slave that does not drive `RLAST` leaves the master's first read unfinished and the processor stalled until the board is switched off and on | zynq-fabricmap, erratum 002 (its carrier's source says so at the PS7 instance) |
| The JTAG identification of these boards is `0x13722093` | the boards' acceptance records (outside this repository) |

Not known:

- **What control register 0 holds on our board.** The table gives bit 8 a default of 0, which
  masks. UG470's own sample bitstream sets it. What a bitstream of Vivado 2025.2 for this part
  writes is not known to me: no bitstream is parsed here, and UG908 names no setting for it (I
  searched its text for the register bit's name and found nothing). The device can be asked:
  the register is readable.
- **Whether a frame that holds LUT RAM reads back its current content, its loaded content, or
  something else,** with the mask on and with it off. The documents say what the bit is for
  and not what a masked cell reads as.
- **Where any LUT is.** Nothing in this project so far connects a site of the PL with a frame
  address. zynq-fabricmap's addresses came from the database and may not be used.
- **Whether a read of such frames disturbs the RAM or the running design.** UG470 warns of
  that for block RAM. I found no such sentence about LUT RAM in it; that is not the same as it
  being safe.
- **The path from this program to user logic.** Never used (proposal, question 9).
- **Whether reading register values through PCAP works for any register but the address
  register.** The prober has only ever read that one.

## 3. The method, in outline

The mirror image of zynq-fabricmap's B1, as the proposal says (section 4): there
configuration bits were set and function observed; here user logic sets the content and the
configuration readback is observed.

1. **States.** The probe design holds a small LUT RAM that the prober can write and read
   through registers. A *state* is a content of the whole RAM. The prober sets a state through
   user logic, reads it back through user logic — so that what the RAM holds is known from the
   design's side and not assumed — and then reads frames through PCAP.
2. **Is anything seen, and where** (S2.2). Three states: all zero, all one, all zero again.
   Frames are read over the whole of block type 0 in each. A bit of configuration memory is a
   *candidate* if it follows the states (0, 1, 0), or follows them inverted. Every other bit
   must read the same in all three. The number of candidates is known beforehand: the number
   of RAM bits in the design. This step uses no knowledge of where a site lies; that is why it
   has to be wide.
3. **Which bit is which** (S2.3). Each RAM bit has a number. In state k the bit holds bit k
   of its number, and in a second state its complement. A candidate's readings over these
   states spell a number; every candidate must spell a valid one, every number must be spelt
   by exactly one candidate, and the complement states must agree. These are the code probes:
   confidence 1 in the structure description.
4. **Single confirmations.** One RAM bit set and all others clear: exactly the one candidate
   decoded for it differs from the all-zero state. Confidence 2.
5. **Wider** — more sites, the shift register — once one slice is understood.

What the prober does on the board is set states and read; the comparing is the host's, from
the raw words, after they are saved. Every result of S2 is labelled closed-book: it rests on
what user logic wrote and what the device read back. The *name* of a site is what our own
constraints gave it (proposal, section 3: "what we placed, and on which site").

## 4. The steps

| step | the question | PL design | new in it | writes |
|---|---|---|---|---|
| S2.0 | does a read of another register through PCAP work, and what does control register 0 hold? | the carrier, as in every run so far | three read headers; a new image | nothing |
| S2.1 | does this program reach user logic, and does the probe design work as a RAM from the design's side? | `s2a` (section 5) | the first PL access; our own design; its build | user logic only |
| S2.2 | is LUT RAM content seen in readback, where, and does reading disturb it? | `s2a` | reading frames in three states over block type 0 | user logic only |
| S2.3 | which configuration bit is which RAM bit, in one slice | `s2a` | code probes and single confirmations; the first entries of the structure description | user logic only |
| S2.4 | the shift register: where its bits are and in which order | `s2a` | shifting instead of addressed writes | user logic only |
| S2.5 | more sites: how regular is the table from site to site | a second design | how far is decided when S2.3 is in (section 11, point 9) | user logic only |

S2.0 and S2.1 are detailed in sections 6 and 7 and could be built once this is agreed. S2.2
to S2.5 are outlined in section 8; what S2.0 says about the mask decides the form of S2.2.

One new thing a step, as in S1: S2.0 has new packets on the known design; S2.1 has a new
design and the new path, and reads no frame it has not read before; S2.2 is the first step
that looks for content.

## 5. The probe design `s2a`

Our own, in this repository (`pl/s2a/`: the Verilog, the constraints, the build script), built
by Vivado 2025.2 and loaded as an opaque file whose hash is recorded. The carrier is not used
for it: it is another project's design, it holds an ICAP and memories of its own whose
placement nobody here knows, and S2.2's count of candidates must be the count of bits we put
there.

**What is in it.**

- The PS7 instance with `M_AXI_GP0`, clocked by FCLK0, and a slave on it: an AXI3 front
  (section 11, point 4: copied from zynq-fabricmap, where it met this board, or written new)
  and a small register file.
- **One slice of LUT RAM**: four `RAM64X1S`, 256 bits, constrained to one named SLICEM site
  and to its four LUT positions. They share clock, write enable and address; each has its own
  data bit. A register write gives an address and four data bits and makes one write; a
  register read gives the four outputs at an address. (That four such memories fit one slice
  when they share their write address is general knowledge of the family, not from a document
  read here. The build shows it: Vivado refuses a placement that cannot be.)
- **One slice of shift registers** at a second named site: four `SRLC32E`. A register write
  shifts one bit into each; a read gives the outputs at an address. They are not shifted in
  any step before S2.4, so they hold what the design loaded.
- An identification register with a fixed word, a scratch register, and a counter that counts
  FCLK0 and can be read: the first two say that reads and writes arrive, the third that the
  clock runs and went on running.
- **Nothing else that is a changeable memory cell.** No array in the source, no inferred RAM,
  shift-register extraction switched off. The build script fails unless the built design holds
  exactly the eight memory primitives named above (point 5).
- No block RAM, no ICAP, no I/O pin.

**What the build script may ask Vivado, and what it may not** (for the owner, point 5). It
names the SLICEM sites — there is no other source for the name of a site than Vivado's model
of the part. It fails by itself, and says why, unless: the eight cells are on the sites and
positions the constraints name; no other RAM or shift-register primitive exists in the
design; timing is met. It writes the bitstream and a record of hashes (sources, script,
bitstream, tool version). It writes no logic location file, no mask file, no readback file,
and no report that anyone opens; `write_bitstream` is given none of those options.

**Clock.** FCLK0 as U-Boot leaves it, 50 MHz on this board. The design is constrained to
twice that, so that the margin does not depend on the measured value being exact.

**Simulation before the board.** The slave and the register file under iverilog, with a
model of an AXI3 master that behaves as GP0 does (single beats, and it waits for `RLAST`).
The benches are in the repository and are run by the test suite.

**Getting it to the board.** As the carrier got there: by YMODEM into RAM, the checksum
compared, `fatwrite` to the project's card, the file read back and compared (the copy in RAM
after `fpga loadb` is not the file: the load swaps it in place). The bitstream file is kept
beside the evidence of the first run that loads it.

## 6. Step S2.0 — what does control register 0 hold? (the carrier loaded; nothing written)

**The run.** The carrier design, the card and the procedure of every run so far. The
reference frame `0xb99` is read first and last and held to its known content. Between them,
three times over:

| read | the header | known answer |
|---|---|---|
| the address register, after a read of the reference frame | `28002001`, as now | `0xb9b`: the rule of S1b.0, a control that nothing has changed |
| IDCODE | `28018001` | the low 28 bits `3722093`, as the JTAG scans of these boards gave them |
| CTL0 | `2800a001` | **none: this is the finding** |
| STAT | `2800e001` | none; recorded |

Each header is UG470's read of one word of a register (type 1, read, the register's address
from table 5-23, one word). Each is sent in the session form the address-register read
already has: after synchronisation, followed by one word read, the session closed by the
cleanup stream.

**Pass:** every read delivers one word; IDCODE is the known one all three times; the address
register obeys the known rule; CTL0 and STAT read the same all three times; the reference
frame is unchanged at the end; no error bit. Then CTL0's value is taken as the device's, and
its bit 8 is the answer to the first half of question 4.

**What may come out, said beforehand.**

1. **Pass, bit 8 set.** The design as loaded reads back LUT RAM unmasked, by the register's
   own word. S2.2 will show whether the frames bear it out.
2. **Pass, bit 8 clear.** The mask is on, as the table's default has it. S2.2 is still run:
   it then shows what a masked cell reads as, which no document says. Seeing content would
   need bit 8 set, and the only documented way is a write of MASK and CTL0 through PCAP — a
   write to a configuration *register*. That is not proposed here; it would be a proposal of
   its own, and it is the owner's to decide whether it falls under "writes configuration
   memory" (point 3).
3. **IDCODE is not the known word**, or differs between repeats. Then a register read in
   this form does not deliver what UG470 says, and the CTL0 value is worth nothing. The run
   fails; everything read is in the result.
4. **A read delivers nothing** (the sentinel survives), or the interface fails: the prober
   stops at that read, as it does now.
5. **The address register or the reference frame is not as before** after these reads. Then
   reading a register disturbs something; the run fails and the record says what differed.
6. **A status bit outside the usual shows.** Not a stop; `status_seen.py` lists it.
7. **CTL0 reads as something that fits no description** (bits set that the table calls
   reserved, for one). Recorded as read; nothing is concluded from single bits beyond bit 8
   without the owner.

**What has to be built.** In the prober: three more read headers in the generator, each a
named constant; the guard accepts exactly those four register reads and still nothing that
writes anything but `CMD` (RCFG, DESYNC) and `FAR`; a stage that makes the reads above; the
`SEU_EN` gate (point 7). In the host: the same in the packet parser and its policy; the
twin's configuration engine gets the three registers, with switches for each outcome above;
a judge; the set; tests and mutants. **A new image** — the first since S1b.3a — and with it
the complete set of mutants before the board (`docs/s1b_plan.md`, section 41).

**What S2.0 cannot show.** Whether the register's bit governs what a read of a LUT RAM frame
delivers. That takes LUT RAM whose content is known: S2.2.

## 7. Step S2.1 — the path to user logic, and the design from its own side

The same image as S2.0, built once with both stages, so that the complete set of mutants is
run once.

**Before the prober touches the PL**, each read live and a failure a stop with nothing
accessed: the gates the prober has now; `LVL_SHFTR_EN`, `FPGA_RST_CTRL`, `FPGA0_CLK_CTRL` and
`PLL_STATUS` equal to the words recorded on this board (section 2). These four reads of the
SLCR are new: the S1a plan allowed such reads "for the record", but the prober as built reads
four DEVCFG registers and nothing else (`test_the_only_registers_touched`). It still never
writes the SLCR.

**The first access is made by hand, so to speak:** before `go`, the run script reads the
identification register from the U-Boot prompt (`md.l 40000000 1`). The prober runs in
U-Boot's context and mapping, so this is the same access, made where a failure costs least.

**Then the prober**, through two helpers that refuse any address not on the design's list:

1. reads the identification register: the fixed word;
2. writes and reads the scratch register with a few patterns;
3. reads the counter twice: the two differ;
4. writes the RAM, all 64 addresses, in four states — all zero, all one, the address's own low
   bits, their complement — and after each reads all 64 addresses back: what was written;
5. reads the shift registers' outputs at all 32 addresses, twice: alike (they are not shifted);
6. reads IDCODE, CTL0 and STAT as in S2.0 — now with our own design loaded — and the reference
   frame first and last.

**What is different from every run so far.** The design is not the carrier, so the known
content of the three known frames no longer applies: the reference frame is held to its own
first reading in the run and to nothing else. What does carry over is everything the device
says about addresses, which does not depend on the design.

**What may come out, said beforehand.**

1. **Pass.** The path works from a returning program; the design is a RAM from its own side.
2. **The access at the U-Boot prompt does not return.** The slave does not answer, or the
   clock does not reach it. The board has to be switched off and on by the owner — the JTAG
   pod of this board is another project's and is not used. Nothing is damaged; the design is
   wrong and goes back to simulation.
3. **The access raises an abort in U-Boot** (the range not mapped, or the slave answers with
   an error). U-Boot prints it and resets; it is in the console log. The prober is not
   started.
4. **A PL gate fails.** Nothing in the PL is accessed. The record shows the word that
   differed from 2026-11-13.
5. **The identification or the scratch register reads wrong**, or the counter stands still:
   the prober stops there, having written nothing but the scratch register.
6. **The RAM does not read back what was written.** A fault of the design or of its
   placement; a new build.
7. **CTL0 differs from what S2.0 read with the carrier.** A finding, not a failure: two
   designs built at different times by the same tool leave the register differently.
8. **The reference frame differs between the start and the end**, or an error bit shows:
   the run fails as a health stop.

**What has to be built.** The design, its benches, its build script and its record; in the
prober the PL gates, the two helpers with their list, the stage; in the twin a model of the
register file, the RAM and the shift registers, with a switch for each outcome above that the
prober can meet (5, 6, 8; a slave that never answers cannot be met by a twin and is what the
bench is for); the judge, the set, the run script's step at the prompt; tests and mutants.

**What S2.1 cannot show.** Anything about where the RAM lies in configuration memory, or
whether readback sees it. No frame is read here that was not read before.

## 8. Steps S2.2 to S2.5 — outline only

Each is proposed in full when the step before it is in. What is said here is the shape and
the size, so that the whole can be judged.

**S2.2 — is the RAM seen.** States all zero, all one, all zero. In each, the frames of block
type 0 are read — all 3,864, since nothing says where the site is — and after each pass the
RAM is read through user logic again and must hold the state, and the counter must have
gone on. Whether block types 1 and 2 are read as well is a point of that step's proposal:
block type 1 raises bit 5 by itself, and the search is cleaner if it comes last or apart.
Size: three states of block type 0 are about 4.7 MB of frames. The result area of the prober
holds 1 MiB, and a run of S1b.5 with a result of 561 KB took about four minutes from its
start to its last file; so this is several runs, each making all three states for its share
of the addresses, and of the order of an hour of board time in all (an estimate from that
one rate, not a measurement). It needs a read stage that takes a list of states —
a second new image.

Its outcomes include the one that changes the stage: **nothing follows the states.** With
S2.0's bit 8 clear that is the mask doing what the table says; with bit 8 set it is a
contradiction to be understood before anything else is done.

It is also where bit 5 is met: a frame whose LUT RAM content was changed by user logic is
read for the first time. I propose that the read stage records the status after every read,
and, where bit 5 is set, clears that one bit and records that it did (point 7) — so that
each read says for itself whether it raised it.

**S2.3 — one slice decoded.** Code probes and single confirmations as in section 3, reading
only the frames in which S2.2 found candidates and the rest of their column. 256 bits: eight
code states and their complements, then singles. Output: the first structure description of
this project (`schemas/self_map_v2.schema.json`, as it is): 256 entries, each with its
address, the RAM position it answers to, its confidence and the records it rests on. Where
the schema has no place for something, it goes into a document beside it, as the proposal's
section 4 has it.

**S2.4 — the shift register.** The same slice positions used as `SRLC32E`. Found by shifting
known sequences in; the question is which configuration bit holds the bit that was shifted
in j steps ago, and whether all 32 are visible (the proposal's question 7).

**S2.5 — wider.** A second design with LUT RAM on more sites. How far — a column, a row,
every SLICEM the part has — is decided when S2.3 has shown how much one slice costs (point
9). What "the bit table for SLICEM LUTs" can honestly mean depends on that: measured for the
sites probed, and for the others at most a rule that the probed ones obey.

## 9. The discipline in S2: what stays and what changes

**Stays.** The four fixed points of the proposal's section 6. Save first, judge afterwards;
the judge re-derives everything from the raw words; the echoed parameters must be the planned
ones; a stop is a stop. The prober sends nothing to PCAP that writes configuration memory or
any register but `CMD` (RCFG, DESYNC) and `FAR`; `SEU_EN` is never set. No board run without
the owner's word for that step. The host does not run mutants while the board is in use.

**Changes, each for the owner to accept:**

- *The prober's list of what it may do* grows by: reads of three more configuration
  registers (S2.0); reads and writes of the probe design's registers, by a list (S2.1); reads
  of four SLCR words as gates (new: today it reads four DEVCFG registers and writes five,
  and beyond those touches only the console UART and its own areas of DDR); later, clearing
  bit 5 of `INT_STS`. The twin logs every access
  as before, and the tests hold the log to lists written in the tests.
- *A second envelope.* Beside the range of frame addresses, the list of PL addresses the
  prober may touch. Both are given by the host and enforced in the prober.
- *Vivado* builds a design of our own for the first time in this project. What it may be
  asked is in section 5.
- *Closed-book, for the author.* I know things about where LUT bits lie in a 7-series frame
  from earlier projects that used the database. None of it may steer a step: the search of
  S2.2 is over all of block type 0 for that reason, and S2.3 reads where S2.2 found
  candidates, not where I would expect them. The test of the sources for the database's name
  and for numbers of the part stays and is extended to the new programs.
- *Grading* (point 8): once, at the end of S2, by a program that prints counts and
  differences, after the last result is committed. Not between steps, as S1b did — there the
  walk went only where the device pointed and a grade could steer nothing; here each step
  chooses what the next one reads, and a grader for LUT bits has to be written against the
  database's files, which shows its author where every column lies.

## 10. What S2 will not show

- The content bits of ordinary LUTs (SLICEL), or of a SLICEM LUT used as logic. A LUT RAM's
  cells are presumably the cells that hold a LUT's truth table, but nothing in S2 writes
  them from the configuration side; S4 and S5 do.
- That the RAM address user logic gives is the index of the truth table as a LUT has it, or
  which physical pin carries which address bit. The table of S2 is in the RAM's addresses.
- Other ways of using the same cells (two outputs of 32 bits, dual-port memories), unless a
  later step places them.
- Flip-flop state (S3), block RAM, routing, anything in block types 1 and 2.
- Another die. One board, as in S1.

## 11. For the owner

1. **The cut into steps** (section 4): S2.0 the register read, S2.1 the path and the design,
   then S2.2 to S2.5, each of the later ones with a proposal of its own. Or another order —
   S2.1 before S2.0, say, or both in one session.
2. **Three new kinds of packet in S2.0**: reads of IDCODE, CTL0 and STAT. Nothing is written
   by them. STAT is there because it is the one UG470's table shows; it can be left out.
3. **If the mask is on.** Then S2 cannot locate anything without bit 8 of CTL0 being set,
   and the documented way is a write of MASK and CTL0 through PCAP. I do not propose it now.
   I ask how the owner wants it treated if it comes to that: as a further kind of packet to
   be proposed and agreed like the others, or as a write that needs the go-ahead the
   proposal reserves for S4. (I would treat it as the second in caution, though it writes no
   configuration memory: CTL0 also holds the security bits, and the write must be shown to
   touch bit 8 alone.)
4. **The AXI front of the design**: copy `carrier_axi3_lite.v` from zynq-fabricmap, with its
   bench and an import record — it has met this board, and the fault it was written against
   (erratum 002) is the one that would cost a power cycle here. The proposal's section 13
   names zynq-psmap and zynq-xpart as sources that may be copied and calls zynq-fabricmap's
   schema "a reference only"; so this needs the owner's word. The other way is to write it
   new. I recommend the copy.
5. **What the build script may ask Vivado** (section 5): the names of SLICEM sites; three
   conditions it fails on; no report that is opened. In particular, whether naming the SLICEM
   sites from Vivado's model is acceptable — I see no way to place a RAM without it.
6. **Documents.** So far UG470 and UG585. For this stage I ask for two more, both official
   and neither with any position in configuration memory: the libraries guide (UG953), for
   what the ports of `RAM64X1S` and `SRLC32E` do, and the CLB guide (UG474). Neither is on
   this host; if agreed they have to be fetched. Without them the design is written from what
   Vivado accepts and what simulation shows, which is possible.
7. **Bit 5 and `SEU_EN`.** A gate now: the prober refuses to start if `SEU_EN` is set (so far
   it was only seen to be 0). From S2.2's read stage on: record the status after every read
   and clear bit 5 alone when it is set — the first time the prober would clear a bit that is
   not one of the transfer's own.
8. **Grading once, at the end of S2**, not after each step (section 9).
9. **How far S2 goes** — one slice, a column, every SLICEM site — is left open until S2.3 is
   in. If the owner already knows the answer, the second design can be planned for it.
10. **One image for S2.0 and S2.1**, the complete set of mutants run once before S2.0; a
    second image for the read stage of S2.2.

If this is agreed, the next thing built is the host side of S2.0 and S2.1 together — the
design and its benches, the prober's two stages, the twin, the judges, the sets — followed by
its "as built" section here and the owner's review, and only then, on the owner's word for
each, the two board runs.

## 12. Decisions (owner, 2026-11-20)

Asked what I recommend on each of the ten points, I answered; the owner: all ten as
recommended, and begin. Where the recommendation differs from section 11 as first written,
this section is what holds.

1. **The steps** as in section 4, S2.0 before S2.1. Both may be on the board on one day, but
   the result of S2.0 is committed and reported, and S2.1 has the owner's word of its own.
2. **The three reads** of IDCODE, CTL0 and STAT; no further register for now.
3. **A write of MASK and CTL0, should the mask be on, needs the owner's go-ahead once, as S4
   does.** Only the class is decided now. Nothing of it is designed until S2.0 has read bit
   8 as clear; then it is a proposal of its own.
4. **The AXI3 front is copied** from zynq-fabricmap: `carrier_axi3_lite.v` and its bench,
   unchanged, with the source commit and hashes in an import record. Nothing else is copied;
   the top level and the register file are written here. (The file was read before this was
   recommended: it names no site and no frame address.)
5. **What the build script may ask Vivado** as in section 5, **and one thing more: the two
   sites are not in a column of sites that earlier projects tied to frame addresses.**
   zynq-fabricmap's carrier constrained or measured the site columns `SLICE_X0` to
   `SLICE_X9`, and I know addresses of some of them from there. The sites of `s2a` are
   taken from columns of a higher number, so that nothing I already know can meet what S2.2
   finds.
6. **No further document for now** — this replaces point 6 of section 11. What the ports of
   `RAM64X1S`, `SRLC32E` and `PS7` are is taken from the simulation models Vivado ships
   (`data/verilog/src/unisims/`), which the benches need in any case; they describe behaviour
   and hold no position in configuration memory. The libraries guide is not needed. The CLB
   guide is asked for again if S2.4 turns out to need it.
7. **The `SEU_EN` gate now; from the read stage of S2.2 on, the status recorded after every
   read and bit 5 cleared alone** when it is set — the write always `0x20`, and the judge
   holds that it happens only after a status word with bit 5 was recorded.
8. **Grading once, at the end of S2.** The owner was told the cost: a systematic error of
   the method is found late. What stands against it are S2.3's own conditions — every
   candidate spells a valid number, every number has exactly one candidate, the singles
   agree.
9. **How far S2 goes is decided after S2.3.** My leaning, said so that it can be disagreed
   with: one whole column of sites, and one site in each other column of SLICEM sites.
10. **One image for S2.0 and S2.1**, the complete set of mutants once before S2.0; a second
    image for the read stage of S2.2, whose content waits for S2.0's answer.

The host side of S2.0 and S2.1 is built next. Its account follows here as a section "as
built" before anything is put to the owner for review.

## 13. S2.0 and S2.1 as built (2026-11-20; host side, nothing on a board yet)

For the owner's review. Sections 6 and 7 say what the two steps are; this says what was built
for them, where it differs from those sections, and what it cannot show. Every statement
about the prober here was checked against the source as committed with this section.

### The prober: one new image, two new stages

The image is new, the first since S1b.3a: 13,964 bytes, sha256 `480bbdd4…aa46`, crc32
`cf189e46` (it was 11,970 bytes, `fdc4f07f…9452`). It still has no data section, reads r9
once and writes it never, and makes the one coprocessor read it always made; the two
functions that wait for a transfer are instruction for instruction what the tests of the
machine code held before.

- **The generator** has `sm_reg_read_stream(reg, …)`: the address-register read with the
  header of one of four registers — FAR `28002001`, IDCODE `28018001`, CTL0 `2800a001`, STAT
  `2800e001`. An unknown choice gives the FAR read.
- **The guard** accepts those four headers and no other read of a register. This holds in
  every stage: the guard is one function and says what a read-only stage may send. Which
  register a stage does read is decided where the stream is made, and each judge still holds
  every recorded stream to the one pinned for its stage. Nothing that writes is accepted but
  `CMD` (RCFG, DESYNC) and `FAR`, as before. The host's packet reader has the same list.
- **Stage 6 (S2.0)** is the table-driven stage with one word more in its parameters: word 12,
  four bits an operation, names the register read after it. At most eight operations. Every
  word of the block the stage has no use for must be zero, or the block is refused before any
  register is read.
- **Stage 7 (S2.1)** is stage 6 with user logic in it: after the gates the four SLCR words
  are read, recorded and held to the four words the host gave; the reference frame is read;
  then the sequence of section 7 is made through `pl_rd` and `pl_wr`; then the register
  operations; then the reference frame again.
- **The two helpers** are the only code that forms an address in the PL (one instruction in
  the image, and a test of the machine code holds that it is in the function both go through).
  They refuse an address that is not one of the design's eight registers, one outside the
  envelope the host gave, and a write to any register but four: the scratch register, the two
  address registers, the RAM's data register. The shift registers' data register is not
  among them — a write there shifts. After the first refusal or the first answer that is not
  right, nothing more is accessed.
- **The PL block** of a stage-7 result lies between the header and the records and is counted
  with the header: the four SLCR words as read, and every access made, in order — the address
  (bit 0 set for a write) and the value. 1,164 accesses in a clean run.
- **New ways to stop**: `0x105`, `SEU_EN` is set; `0x110` to `0x113`, one of the four SLCR
  words is not the host's; `0xa00` with a code, user logic did not answer as the design must
  (the identification word, the scratch register, the counter, the RAM, the shift registers,
  the design's count of writes — or the prober's own helper refused an address).

### The two sets

| | `s2_0` | `s2_1` |
|---|---|---|
| stage | 6 | 7 |
| design loaded | the carrier | `s2a`, sha256 `09782815…df64`, 2,083,859 bytes |
| envelope | `0xb98..0xb9a`, reference `0xb99` | the same |
| operations, each three times | the reference frame and FAR; then, with no frame read, IDCODE, CTL0, STAT | with no frame read: IDCODE, CTL0, STAT |
| the wait | the one that touches no memory | the same |
| anomalies budgeted | none | none |
| PL envelope | — | `0x40000000..0x4000001f` |
| SLCR words wanted | — | `0000000f`, `00000000`, `00400800`, `0000003f` |
| records, result | 14 records, 6,784 words | 11 records, 7,920 words |

The three registers are read in the session form S1b.0b used on the board for an operation
that reads no frame: synchronisation, RCFG, the frame address written, no read, then the
register's header and one word, then the cleanup.

### The probe design `s2a`

`pl/s2a/`: the top level and the register file (written here), the constraints, the build
script, a bench, the description (`design.json`), the list of SLICEM sites and the record of
the build. The AXI3 front and its bench are in `imported/fabricmap/`, unchanged, with an
import record.

- Eight registers at `0x40000000`: the identification word `0x53324131`, a scratch register,
  a counter of FCLK0, the RAM's address and data, the shift registers' address and data, and
  — more than section 5 listed — the design's own count of RAM writes and of shifts since it
  was loaded. The last lets the design say for itself that nothing shifted it.
- The LUT RAM is four `RAM64X1S` on `SLICE_X16Y30`; the shift registers are four `SRLC32E`
  on `SLICE_X34Y70`, loaded with four different words. Both sites are in columns of sites
  numbered above 9 (section 12, point 5); which of those, and which row, was picked by hand
  and means nothing.
- The slave answers every transfer. An address that is no register reads zero.
- Built by Vivado 2025.2: setup slack 3.115 ns against the 10 ns the design is held to, hold
  slack 0.175 ns. The bitstream is `build/pl/s2a.bit`; its hash is in `pl/s2a/build.json` and
  from there in the set.

### Where what was built differs from sections 5 to 7

1. **The `SEU_EN` gate is in stages 6 and 7 only.** Section 11, point 7, says "the prober
   refuses to start if `SEU_EN` is set". The older stages were left exactly as they ran on
   the board, and their judges with them: a gate there would be a change to five stages and
   four judges whose 185 stored runs are judged again by the suite. S2 uses only the new
   stages. If the owner wants the gate in every stage, it is a small change with a large
   re-check.
2. **The four memories of the LUT RAM are not constrained to LUT positions.** Section 5 says
   "constrained to one named SLICEM site and to its four LUT positions". Vivado keeps its own
   order for them: given positions A, B, C, D for memories 0 to 3, it placed them D, A, B, C —
   with the position before the site and after it, on the cell and on its leaf. The build's
   own check is what showed it. The site is constrained; the build requires four different
   positions and writes down which memory is on which (`build.json`: memory 0 on D, 1 on A,
   2 on B, 3 on C). The shift registers do keep the positions given (0 to 3 on A to D).
3. **The shift registers' last-stage outputs are not connected**, and a read of their data
   register gives four bits, not eight. Connected, Vivado allowed such a cell on position A
   only. The last stage is read like any other, at address 31.
4. **The host reads the four SLCR words at the prompt before it reads the design**, and
   stops if one is not the set's. Section 7 has the prober do this; the host now does it
   first as well, so that the first access to the PL is not made with the PS side unchecked.
5. **The judge of S2.1 holds the shift registers to what the design's source loads into
   them**, not only to reading alike twice. A known answer from our own design; it rests on
   the simulation model's statement that address a reads bit a of the loaded word.
6. **Nothing puts `s2a.bit` on the card.** The run script takes the design from the card if
   it is there and sends it by YMODEM if not, as it always did. Section 5's "written to the
   card and read back" is a session at the prompt, as on 2026-11-13, and is to be part of
   what is proposed for the board; without it each run sends 2 MB over the console.

### Three builds that failed, and what each showed

The build script stops unless its conditions hold, and three times it or Vivado did:
a cell given its site before its position takes the site's first free position, and the next
cell is refused; a shift register whose last-stage output is used can sit on one position
only (3 above); and the four memories were not where the constraints put them (2 above).
To find these I read Vivado's console output of the failed builds — its messages, no
report. No logic location file, mask file, readback file, checkpoint or report was written.

### Tests that changed their statement

- `test_prober_packets`: "only the FAR register and only one word of it" held that a read of
  STAT or of IDCODE is refused by the guard and by the reader. It now holds the list of four,
  every other register of UG470's table 5-23 refused, every other count refused, and a write
  to any of the three new ones refused.
- Five tests held the image of the sets `s1b4a` to `s1b6a` to the hash that had been on the
  board. The sets are made from the image as it is built, which is now another. What they
  hold instead is what ran: the image kept beside each step's run has that hash and is the
  one kept with the chain before it.
- Tests that made up chains and runs with the current image had its checksum and size
  written out as numbers; they take them from the image now.
- `test_prober_image`: the image now holds four addresses of the SLCR and reaches into the
  PL. The test that said it holds neither was replaced by one that says where: one literal,
  in the function that makes the four gate reads, and one instruction, in the function every
  PL access goes through.

No stored result or verdict was changed, and every stored run is judged as before.

### What holds it

- `tests/test_prober_s2.py` (37 tests): the two stages on the twin — what is sent, what is
  touched and in which order, every gate, every form of parameter block that must be
  refused, and each way the device or the design may fail to answer, with where the prober
  stops and that it touches nothing afterwards.
- `tests/test_s2_host.py` (44): the judge on clean results, on runs that went badly (it must
  come to the prober's account from the raw words alone), and on results tampered with; the
  run script with both sets against a pretend U-Boot, a design that answers with another
  word and one that does not answer among them.
- `tests/test_pl_s2a.py` (17): the bench of the design behind the front, and the front's own
  bench; three broken register files that the bench must fail without standing still; the
  description, the source, the constraints, the build script, the prober's header and the
  twin saying the same; the record of the build being the record of these sources and of the
  staged bitstream; and that the scripts ask Vivado for nothing the rule excludes.

641 tests (541 before).

### Mutants

711 mutants, none stale (609 before: 102 new, and seven older ones whose place in the source
had moved were set right). By section 41 of `docs/s1b_plan.md` the ones of the new code were
run now, and **the complete set is due before this image first goes on a board; it has not
been run.** (It has since: section 16.)

The 98 of the new code (`s2`), first run: 93 killed, 3 survived, 2 did not build. The three
that survived were in the judge, and each was a check with no test of its own:

- a result whose sizes do not add up — the check was covered only by cases that a later check
  also refuses. With it gone, a result one word longer than its header and records, with a
  header saying so, was judged as if the word were not there;
- an echoed parameter block that no prober runs with, under a status that says done, when
  the plan given to the judge is that same block;
- a PL block that shows an access to the design in a run whose first reading of the
  reference frame failed. The test there was had only the gate stops, which have a message
  of their own.

Three tests were added. The two that did not build left a variable unused, which the
prober's build refuses; they were rewritten to make the same change and build. All five were
then run again and are killed, and the five of the packet reader with them. The record is
`evidence/host_checks/mutants_2026-11-20_s2.txt`.

### My slips

- The first run of the mutants did nothing: the tool's own check of the unmutated tree
  failed. Two test modules read the built image when they are imported, and a fresh copy of
  the tree has no build. I had run the suite only in a tree that had one. Both modules build
  the image first now, and the suite was run on a fresh copy.
- While writing the record of the mutants I started the tool with no argument, which is the
  complete set, with its output thrown away. I stopped it after two minutes and removed its
  scratch copies. Nothing came of it and nothing is recorded from it; the complete set is
  still to be run, whole and into a file.
- A draft of this proposal said the prober already reads the SLCR words for the record. It
  does not, as its own test says; the text was corrected before the proposal was committed.

### What none of this can show

- What the three registers hold on the board. The twin's values are made up.
- Whether U-Boot's mapping reaches `0x40000000`, and whether the design answers there. The
  bench drives the register file with a model of an AXI3 master; the PS7 itself is not
  simulated.
- Whether the SLCR words are still the ones recorded on 2026-11-13. If not, the run stops at
  the prompt with the word it read.
- Whether a read of the reference frame is disturbed by anything here; the run says.
- Whether a second build of the same sources gives the same bitstream. It was not tried; the
  set names one file by its hash.

## 14. Review of `363ad58` (2026-11-20): one finding, accepted and mended

**The finding (P2).** Section 7 says of the first access to user logic: if it raises an
abort, U-Boot prints it and resets, and the prober is not started. The run script did not
hold to that. A reply with an abort in it has no line of a dump, so `read()` took it for a
reply that had lost characters and asked again (the rule of `docs/s1b_plan.md`, section 43).

**Reproduced** as the reviewer described it: the pretend board answers `md.l 40000000 1`
with an abort and the text of a restart, then a prompt; asked again, it answers with the
word that is wanted. The script sent `go 02000000`, and the run was judged PASS.

**It can happen on this board.** After a reset this board comes to a prompt by itself, without
a countdown (its console of 2026-11-19, the resets between the runs of a chain). So an abort is followed by a prompt, as a reply is.

**It is wider than the finding.** Every reply that may be asked for again had the same hole —
the status word, the checksums, the result header, the SLCR words — and `host/ps_look.py`
has the same loop.

**What is changed** (`restart_seen()` in `host/s1a_run.py`, used by `do()` there and by
`ps_look.py`). The reply to any command is looked at before it is taken for anything: if a
line of it says that U-Boot took an exception or that the board started again, the run stops
there. The reply is in the record, the record is written, nothing more is sent, and the
command is not sent again. The lines:

- the name of an exception (`data abort`, `prefetch abort`, `undefined instruction`,
  `software interrupt`) or `Resetting CPU`, anywhere in a line;
- at a line's beginning: `resetting ...`, the loader's line (`U-Boot SPL `), the line of a
  countdown, and U-Boot's own first line — this last one not in the reply to `version`,
  where it is the answer.

The exception lines are U-Boot's as they are generally known. **None has been seen on this
board**; whether the board prints them so is not established. The lines of a restart are
this board's own. (As first mended, the reply to a file transfer did not pass through this
check, and the names of the exceptions were looked for in the text column of a dump too:
section 15.)

**The rule holds for the reply to `go` as well.** Until now, a prober that did not come back
in the ordinary way but left a prompt had its result read from memory, saved and judged,
whatever the console showed. Now a restart in the reply to `go` stops the run with nothing
pulled: after a restart the loader has run again, and what stands at the result's address is
no longer known to be the prober's. This changes what every stage would do in a case that
none of the 185 stored runs met.

**Decided by the owner (2026-11-20): stop, pull nothing, record; whether the run is made
again is decided after the record has been looked at.** So nothing here makes a run again:
the run script ends with FAIL, and a chain halts at a run that stopped, as it does at any
run with a problem. For the looking, the run record names the restart (`restart`: the step,
the command, the line) and keeps that reply whole, where any other long reply is cut to its
two ends; the console log beside it has every byte as always.

**Tests** (648; 641 before).

- The reviewer's case, and the same at two of the SLCR words: asked once, nothing sent
  after, `go` not sent.
- A restart at one place of every kind of command the script sends, and at every place of
  the two kinds that are asked again: the commands sent are those of a clean run up to that
  place and no more.
- Each line alone is enough, also when the word that was asked for follows it whole.
- A restart in a long reply to `go`: the reply is in the record whole, the record names it,
  and the run's directory holds the record and nothing else.
- What is not such a line: U-Boot's line in the reply to `version`, a dump, the load of a
  design, the prober's own lines.
- **The rule over everything this board has said.** None of the 24,799 replies kept with
  the 185 runs has such a line. Of the 25,940 exchanges in the console logs, the ones that
  have are the 186 replies to `reset` — sent between the runs of a chain, never by the run
  script — every one of them, and no other.
- `ps_look.py`: at a dump, at the status before the write (no write follows), at the write
  (nothing is read after it), at a reading after the write.

**Mutants.** 19 new (730, none stale): the check taken out of the run script and out of each
of the two places in `ps_look.py`, each line dropped from the list, the three ways of looking
for a line changed, and three on what is recorded. The first 16 were run and are killed
(`evidence/host_checks/mutants_2026-11-20_restart.txt`) — on the script as it was before the
owner's decision put the restart into the record. **The three on the record have not been
run, and the 16 not on the script as it is now**: the complete set is running, and two runs
of the mutants beside each other take several times as long. All 19 are due, with every
other mutant of the run script and of `ps_look.py`, when it has ended. (Run since: section 16.)

**The rest of the review** found nothing to change: the six differences of section 13 were
compared with the source; the image rebuilt from source is the image; the hashes of the
design's sources, of the imported files and of the bitstream agree.

**My slip.** Section 7 names three ways the first access can go wrong at the prompt. I built
and tested two — another word, and no prompt — and not the third, although it is written
there. And the rule of section 43 asked again for whatever was not whole without asking what
else a reply that is not whole might be.

**Not changed.** The prober, its image (`480bbdd4…aa46`), the judges, the sets, the design.

## 15. Review of `7830797` (2026-11-20): two findings, both accepted and mended

**1. The reply to a file transfer went round the check (P2).** I had left it out and said so
in section 14: a transfer that does not report its size stops the run anyway. The reviewer's
case is the other one — the size is reported, and after it the board starts again.
Reproduced: the script went on to `go`, and the run was judged PASS. The reason I gave was
no reason; the rule is that no reply is taken for anything before it has been looked at, and
a transfer's reply is a reply.

Mended: both transfers (the prober, and the PL design when the card does not have it) go
through one function, and every reply — a command's or a transfer's — goes into the record
in one place, where it is looked at first. A transfer's reply that shows a restart is kept
whole, as a command's is (otherwise its last 400 characters are kept, as before).

**2. A whole line of a dump was taken for an exception when its bytes spelled one (P2).** The
names of the exceptions are looked for anywhere in a line, and a line of `md.l` ends with
its bytes as text. I had seen this and set it aside: a result is binary. But a result holds
frames, and a frame holds whatever the device holds. Reproduced with a reference frame whose
bytes read `data abort`: the judge passes the result, and the run stopped while pulling it.
From S2.2 on the frames hold patterns that user logic wrote, so this is not far-fetched.

Mended (`dump_line()`): in the reply to `md.l`, a line that is a whole line of a dump to the
character is data and is not looked at. The form: the address and a colon, one to four
words, blanks up to the column where the text begins, and one character of text for each
byte — 47 characters and four more for each word. A line that began as a dump and ends
otherwise is looked at whole as before, so an exception raised after a line had begun is
still seen; so is every line after the dump.

The form is U-Boot's as it is generally known, and it is held to this board: of the lines in
the console logs that begin as a dump, more than 4.8 million have exactly this form, and
fewer than 300 have not — the ones the console damaged (a line cut short, two run together).
A damaged line is looked at whole; it would stop a run only if its own text spelled an
exception, and then the record shows the line.

**Tests** (652; 648 before).

- A transfer whose reply has the right size and then a restart, for both transfers and three
  forms of the text: nothing sent after it, `go` not sent, the reply in the record whole.
- A dump's whole lines of one to four words whose text spells an exception are not seen;
  twelve lines that begin as a dump and are not one are; the same line in the reply to
  another command is; a line after the dump is.
- The reviewer's case through the run script: S2.1 with a reference frame that spells
  `data abort` at every alignment is pulled whole and passes.
- The pretend U-Boot of the tests printed its dumps with a made-up text column. It prints
  them in U-Boot's form now, with the bytes as text — otherwise no test could have met this.
- The form of a dump's line over the console logs (above).
- In the run script's source: one place puts a reply into the record, and looks first.

**Mutants.** Six new (736, none stale). **None of the mutants of the run script has been run
on the script as it is now** — neither these six nor the 19 of section 14: the complete set
is still running (on `363ad58`; it is far slower than I said — most of a day, not hours), and a
second run beside it makes both several times slower. All mutants of the run script and of
`ps_look.py` are due when it has ended, and nothing of S2 goes on a board before. (Run since:
section 16 — where two of the 736 turned out to be stale.)

**My slips.** Both findings are things I had looked at and decided wrongly. The first I wrote
down as a limit instead of closing it. The second I judged by what results have held so far,
in the very stage that changes what they hold. And the pretend board's text column was a
constant, so my own tests could not have shown it.

**Not changed.** The prober, its image (`480bbdd4…aa46`), the judges, the sets, the design.

## 16. The mutants, run (2026-11-20)

**The complete set**, on the tree of `363ad58` (the tree the image was built from; the three
commits of sections 14 and 15 change the run script, `ps_look.py` and tests, and nothing the
image is made of): 711 mutants, **711 killed**, none survived, none failed to build, none
stale; each run of the suite ran 641 tests. 08:56 to 15:50 GMT, eight copies. The record is
`evidence/host_checks/mutants_2026-11-20_complete.txt`.

**The run script and `ps_look.py` as they are now** (`98709d7`, 652 tests): every mutant of
the two files, in five runs one after another — 133 mutants, **131 killed, 2 stale**, none
survived:

| run | mutants | killed |
|---|---|---|
| `run: ` | 80 | 78 (2 stale) |
| `run s2: ` | 9 | 9 |
| `look: ` | 19 | 19 |
| `restart:` | 20 | 20 |
| `dump:` | 5 | 5 |

These are all 132 of the two files and one of a judge whose name has `run: ` in it. The 19 of
section 14 and the six of section 15 are among them, so each has now been run on the script
it is about.

**The two that were stale** were the two older mutants that let a transfer go round `link()`,
one for the image and one for the design. `98709d7` put both transfers into `transfer()`, and
the two lines they named were gone. They are one mutant now, on the one line there is; it
was run by itself and is killed (three tests fail, among them the one of every way the line
can fail and the one that counts the uses of the line). **735 mutants.** The record of the five runs and of this
one is `evidence/host_checks/mutants_2026-11-20_run_script.txt`.

**My slip.** Sections 14 and 15 say "none stale". For `98709d7` that was not so: I counted
the anchors before the change that moved the transfers and did not count again after it, and
my own count was a script of mine, not the tool's rule. This time every one of the 735 was
held against the tree with the rule `tests/mutants.py` itself uses (the anchor occurs once,
or as often as the occurrence asked for): none is stale. A test of this in the suite would
be worth nothing — under a mutant it would fail for that mutant's own anchor and kill every
mutant there is — so it stays a thing the tool says when it is run.

**What this does and does not show.** Every check the mutants take out is held by a test:
that is a statement about the tests, on a pretend board and a twin. It says nothing about
the board. By section 41 of `docs/s1b_plan.md` the condition "the complete set before a new
image first goes on a board" is met for this image (`480bbdd4…aa46`); the other conditions
of section 13 — the owner's word for each step, `s2a.bit` on the card — are as they were.

## 17. S2.0 on the board (2026-11-20): PASS; control register 0 is `0x00000501`

The owner released it after section 16. One run of the set `s2_0` on `17A6`, the carrier
loaded, the new image's first time on a board; the account is
`evidence/s2_0_17A6_2026-11-20/RESULT.md`. The result was committed as stored (`4e73959`)
before it was read.

- **A register read through PCAP works in the form section 6 gave.** IDCODE `0x13722093`
  three times (the low 28 bits as known); the address register `0xb9b` after every read of
  the reference frame; the reference frame the known frame all five times; no error bit, no
  status bit that is not usual.
- **CTL0 is `0x00000501`**: bits 10 (ConfigFallback), 8 (GLUTMASK_B) and 0 (GTS_USR_B), the
  same three times. **Bit 8 set: outcome 1 of section 6.** By the register's word the carrier
  as loaded reads back LUT RAM and shift registers unmasked. The first half of question 4 is
  answered so; the second half — do the frames bear it out — is S2.2's.
- **STAT is `0x46107ffc`**, the same three times; read off UG470's table in the result note,
  held by no program.
- **The write of MASK and CTL0** that point 3 of section 12 kept in reserve is not needed for
  the question as it stands, and nothing of it is designed.

**What it changes for the steps to come.** S2.1 is as built; its outcome 7 now has a value to
compare with (`0x00000501` under the carrier). S2.2's read stage — the second image of
point 10 — can be proposed for the case "the mask is off": what is read is expected to be
the content, and the step has to show that it is.

**One thing the run met that the tests had not.** The audit of the stored runs
(`tests/test_evidence_audit.py`) has the number of runs written into it; a new run makes it
fail until the numbers are raised. They were raised in the commit that stored the run (186
runs, 141 PASS; the audit re-judged the new run and agreed with its stored verdict). Every
board run from here on does the same, and the raw result's commit is where it belongs.

## 18. The design on the card, and S2.1 on the board (2026-11-20): PASS

Asked what was left to check before S2.1 and what speaks against the card, I answered (the
top level compared port by port with zynq-fabricmap's carrier, read and not copied: the same
hookup, and a BUFG written out; the constraint 10 ns against the board's 20; the YMODEM
branch for a PL design has never run on this board, 184 runs took theirs from the card). The
owner: as recommended, it is what the plan fixed, no need to ask.

**The card** (`evidence/card_2026-11-20/`, `411da7e`): `s2a.bit` by YMODEM into RAM, crc32
`6a1efe06`, `fatwrite`, read back the same; `carrier.bit` read back as it was; nothing loaded.
This U-Boot's word for a file that is not on the card is now on record (`Failed to load`
and the name); the run script's rule, that the size wanted was not reported as read, covers
it.

**S2.1** (`evidence/s2_1_17A6_2026-11-20/RESULT.md`; stored as it came in `8dbe27d`): outcome 1
of section 7.

- **The first access to user logic returned**: `md.l 40000000 1` at the prompt read
  `53324131`. The four SLCR words were the ones wanted, at the prompt and again from the
  prober.
- **The design from its own side**: 1,164 accesses, nothing wrong; the counter runs; the RAM
  read back each of its four states at all 64 addresses (256 writes counted by the design);
  the shift registers read the four words they are loaded with, twice, and were not shifted.
- **The configuration registers under our own design** are what they were under the carrier:
  IDCODE `0x13722093`, **CTL0 `0x00000501`**, STAT `0x46107ffc`. Outcome 7 did not come about;
  bit 8 is set for this design too.
- **The reference frame** the same first and last, and not the carrier's frame — as expected
  of another design.

**A fault this run showed, in a test and not in the run.** The audit of the stored runs
handed every judge the carrier's known frames. The judge of `s2_1` is handed the design's
facts by the run script (`known_for`), and with the carrier's frames it says of this result
that the shift registers' words were not given, and fails it. The run script's verdict was
right; the audit asked the wrong question. It now takes what the run script takes, and its
re-judging of this run is the stored verdict word for word. **My slip:** `363ad58` gave the
set facts of its own and did not carry that to the audit; no test could show it while no run
of the set was stored.

**Where S2 stands after this.** Answered so far: a register read through PCAP works (S2.0);
CTL0 says the mask is off, for both designs; the PS reaches our design, and the design holds
content we chose and content we write. Not yet asked of the device: where that content lies
in configuration memory and whether a read of those frames shows it. That is S2.2, whose
read stage is the second image of point 10 and is to be proposed next, for the case that the
mask is off. One thing that proposal has to deal with — from general knowledge of the
family, to be checked against UG470's text before anything rests on it: the mask exists
because reading back a LUT RAM or a shift register that is in use can disturb it. `s2a` is
idle unless the PS accesses it, and the proposal has to say what idle must mean during a
read.

## 19. S2.2 — is the RAM seen in readback, where, and does reading disturb it? (proposal, 2026-11-20)

For the owner. Section 8 outlined this step and left its form to S2.0's answer; the answer is
in (bit 8 of CTL0 is set under both designs), and S2.1 has shown the design working. This
section is the step in full. The points to decide are at its end. Nothing of it is built.

### What is known now that section 8 did not have

| fact | source |
|---|---|
| CTL0 is `0x00000501` with `s2a` loaded: by the register's word, LUT RAM and shift registers are not masked in readback | S2.1, section 18 |
| The design answers; its RAM holds what is written through its registers, at all 64 addresses and in four states; the shift registers hold the four loaded words | S2.1 |
| Block type 0 is 3,864 addresses in 112 columns of 28, 30, 36 or 42 frames (18, 8, 82 and 4 of them) | `census/frame_census_17A6.json` |
| A read of up to three frames in one transfer delivers what single reads deliver, and the address register after it is known: every address of the census was read once in such a read besides its single reads, and each frame agreed | S1b (the walk's second path, `docs/s1b_plan.md`; the census's readings) |
| A run whose result is 561 KB takes 255 s from its start to its verdict — 2.2 KB of result a second, nearly all of it the pull over the console | 118 stored runs |
| A plain readback reads "the current values on all user memory elements (LUT RAM, SRL, and block RAM)"; the state of registers is read only after a capture (the `CAPTUREE2` primitive or the `GCAPTURE` command) | UG470, chapter 6 |
| With `s2a` loaded the frame `0xb99` is all zero: its hash in S2.1 is the hash of the all-zero frame | S2.1's verdict; the census |

And what is still not known: UG470 has no sentence that reading back a LUT RAM in use
disturbs it (section 2). I believe from documents of older families that it can, and that
this is why the mask exists; that belief is in no program. The step measures it.

### The run

One run does this, for a *share* of the addresses of block type 0:

1. the gates of S2.1 (`SEU_EN` clear; the four SLCR words; the design's identification);
2. CTL0 read once (the packet of S2.0): the run's own record of the mask while it reads;
3. the reference frame, as in every run;
4. **for each of three states — all zero, all one, all zero:**
   - the RAM is written to the state through the design's registers, all 64 addresses, and
     read back through them: it must hold the state;
   - the counter is read;
   - **every address of the share is read through PCAP**, the device's status recorded
     after every read; where bit 5 of `INT_STS` shows, that bit alone is cleared and the
     clearing recorded (section 12, point 7);
   - the RAM is read through the design's registers again, all 64 addresses: **it must still
     hold the state** — this is question 5, asked of the device;
   - the counter is read again and must have gone on; the shift registers' outputs are read
     and must be the loaded words; the design's count of writes must be the writes made and
     its count of shifts zero;
5. CTL0 and the reference frame again.

Nothing is written to configuration memory or to a configuration register. The prober
writes what it wrote in S2.1 — the design's RAM, through the design — and one thing more:
`0x20` to `INT_STS`, and only after a status word with bit 5 has been recorded.

**How the frames are read.** In reads of three frames, the form S1b used in every chain;
a column's last read is of what is left (one frame, in the columns of 28). 1,300 reads cover
block type 0 once. Nothing about reading is new in this step; what is new is that content
is looked for.

**Where the addresses come from.** From the census: the host writes the list of reads of
the share — an address and a number of frames each — into memory before the prober is
started, as it writes the parameters. The prober does no arithmetic on addresses; it
refuses a list with an address outside the envelope or a count above three, and echoes the
list in its result. The judge holds the echoed list to the planned one, and the planned one
to the census: every address in it is one the device named, and every read lies in one
column.

**The shares.** A read with its record is 480 words; three states of a share of 179 reads
fill the result area (1 MiB, as it is). So block type 0 is **eight runs**, each of whole
columns, each making all three states for its own columns, a `reset` and a fresh load of
the design between them — a chain, driven as S1b's chains were, that halts at the first run
that is not PASS. About 7.5 MB in all: **about an hour of board time**, by the rate above.

### What the host does with it

Per run, from the raw words and after they are saved: everything S2.1's judge holds, the
list, the address register after every read (as the census has it), the status words, the
three RAM read-backs. Then, for every bit of every frame read, its three readings:

| readings in the states 0, 1, 0 | the bit is |
|---|---|
| alike | *still* |
| 0, 1, 0 | a *candidate*: it follows the RAM |
| 1, 0, 1 | a candidate, inverted |
| anything else | *restless*: it changed between two readings of the same state |

A run passes if it has no restless bit and nothing else is wrong; its candidates are
listed, each as an address, a word and a bit. A program over the eight verdicts (as
`s1b2_closed.py` was for the chains) closes the step: **the candidates of all runs together
are the answer, and their number is known beforehand — 256, the bits of RAM in the design.**

### What may come out, said beforehand

1. **256 candidates, all other bits still, the RAM undisturbed.** The RAM is seen, the mask
   bit means what the table says, reading does not disturb a RAM that is not being written.
   The addresses in which the candidates lie are what S2.3 reads.
2. **No candidate.** With bit 8 set that contradicts the register's own word. Nothing is
   concluded and no write of MASK or CTL0 is designed; the next proposal is block types 1
   and 2 under the same three states, since nothing here says the RAM must lie in block
   type 0.
3. **Fewer than 256, not none.** Some of the RAM is seen and some is not, or is elsewhere.
   The candidates are reported as they are; block types 1 and 2 as in 2.
4. **More than 256.** Something besides the 256 cells follows the state — the same cell
   seen at two places, or logic of the design. Reported; S2.3's code probes say which
   candidates are cells of the RAM, because only those spell a number.
5. **Candidates, some as written and some inverted.** Recorded as found; not a failure.
6. **Restless bits.** A bit that reads differently in the two all-zero states. The run
   fails and names them. (By UG470 the registers of the design — the counter among them —
   are not read without a capture, and the prober sends none; if they show nonetheless,
   this is where.)
7. **The RAM does not hold its state after the frames were read.** Reading disturbs it.
   The prober stops there with a code of its own; the result has everything up to that
   point, and the difference. This is an answer to question 5, and S2.3 cannot be done as
   outlined: a proposal of its own follows.
8. **The counter stands, the shift registers read otherwise, or the counts of writes are
   off.** The design did not go on as it was. A stop, as in S2.1.
9. **Bit 5 shows.** Not a failure: which read raised it is recorded, it is cleared, and
   the question S1b left (section 1) has its first answer — whether it comes with frames
   whose RAM content is no longer what was loaded.
10. **The interface fails, a read is short, the address register is not what the census
    has.** A stop, as always.

### What has to be built

- **The prober: a new stage, and so a new image** — the second of point 10. The list of
  reads and its checks; the three states; the RAM, counter, shift-register and count checks
  around each pass; the status after every read and the clearing of bit 5; a stop code for
  a disturbed RAM. The log of accesses to the design as in S2.1, larger. The guard and its
  list of what may be sent to PCAP are not changed: every packet of this stage exists.
- **The twin**: configuration memory in which bits chosen by the test follow the RAM of
  the design's model, with a switch for each outcome above that a prober can meet (2 to 9).
- **The host**: the judge; the program that makes the shares from the census; the closing
  program; the chain's driver for this set; the run script's step that writes the list.
- Tests and mutants; and, by the owner's rule for a new image, **the complete set of
  mutants before it first goes on a board** — about seven hours, as measured today.

### What S2.2 cannot show

- Which candidate is which bit of the RAM. All 256 change together here. S2.3.
- Anything about the shift registers' bits: they are never shifted, so they are still. S2.4.
- Why a bit follows, or what the still bits are.
- That reading does not disturb a RAM that is being written at that moment: the prober is
  the only writer and does not write while it reads.

### For the owner

1. **The breadth:** all of block type 0, three states, and nothing of block types 1 and 2
   unless fewer than 256 candidates are found — then as a proposal of its own. *(Recommended.
   Block type 1 raises bit 5 by itself and would blur outcome 9.)*
2. **The read form:** three frames a read, as proven — eight runs, about an hour. The other
   way is one read for a whole column: five runs, about 35 minutes, but a read of up to 42
   frames has never been made here and would first have to be shown to deliver what single
   reads do. *(Recommended: three frames. One new thing a step.)*
3. **The list of reads comes from the census and is written by the host;** the prober does
   no arithmetic on addresses and echoes the list. *(Recommended.)*
4. **A RAM that does not hold its state after a pass stops the run** (outcome 7), instead
   of being recorded while the run goes on. *(Recommended: what follows such a pass is not
   what this plan assumes.)*
5. **CTL0 is read at the start and the end of every run.** One packet more, already
   allowed. *(Recommended.)*
6. **The reference frame stays `0xb99`,** although it is all zero under `s2a` and so a weak
   witness. What stands in for it here: every frame of the share is read three times, and
   every bit that is not a candidate must read alike. *(Recommended; choosing another
   frame would need a reason to prefer one, and there is none yet that the device gave.)*
7. **One word for the whole chain of eight runs,** after the owner's review of the "as
   built" section. The chain halts by itself at the first run that is not PASS, at a
   restart, and at anything the judge does not know; it runs nothing again. The first run's
   result is committed before the second starts, as in S1b. *(Recommended. The other way
   is the first run alone, a report, and a second word for the rest.)*
8. **The complete set of mutants** for the new image before the board, as the rule has it:
   about seven hours on this host, during which nothing else heavy runs and the board is
   not used. *(No choice proposed; said so that the time is known.)*

## 20. Decisions on S2.2 (owner, 2026-11-20)

The owner: all eight points of section 19 as recommended.

1. All of block type 0 in three states; block types 1 and 2 only if fewer than 256
   candidates are found, and then as a proposal of its own.
2. Three frames a read.
3. The list of reads is made by the host from the census; the prober does no arithmetic on
   addresses and echoes the list.
4. A RAM that does not hold its state after a pass stops the run.
5. CTL0 is read at the start and at the end of every run.
6. The reference frame stays `0xb99`.
7. One word for the whole chain of eight runs, after the review of the "as built" section;
   the chain halts by itself and runs nothing again.
8. The complete set of mutants for the new image before the board.

The host side is built next; its account follows as a section "as built".

## 21. S2.2 as built (2026-11-21; host side, nothing on a board yet)

For the owner's review. Section 19 says what the step is and section 20 what was decided;
this says what was built, where it differs from them, and what is and is not tested.
**Nothing of it has been on a board.**

### What there is

| part | where |
|---|---|
| the prober's stage 8 | `prober/sm_core.c` (`run_s8`), `prober/sm.h` |
| the twin: cells of the RAM shown in configuration memory, the list, the faults | `prober/twin_hal.c` |
| the shares and the rule for the address register | `host/s2_2_shares.py` |
| the judge | `host/s2_2_judge.py` |
| the chain's driver, which also closes the step | `host/s2_2_chain.py` |
| the run script: a set run a share at a time | `host/s1a_run.py` (`--share`, `with_share`, `planned_words`) |
| the set | `build/prober/expected_s2_2.json`, written by `tests/test_prober_image.py` |
| tests | `tests/test_prober_s2_2.py` (38), `tests/test_s2_2_host.py` (74) |

**A new image** — the second of point 10: `prober.bin`, 16,360 bytes, sha256
`73d7bbf8…a01f`, crc32 `57c6ef68` (replaced by the review of section 22, before any board).
Every set is written for it. The image of S2.0 and S2.1
(`480bbdd4…aa46`) stays beside their evidence.

### The stage

Parameters (words of the block; every other word must be zero, and the prober refuses the
block before it looks at the device if one is not):

| word | holds |
|---|---|
| 3, 4, 5 | the envelope — block type 0 as the census has it, `0x00000000..0x00401ba9` — and the reference frame `0xb99` |
| 7 | how many states: 3 |
| 9, 15 | the poll limit; the wait that touches no memory |
| 16 | how many reads the list has |
| 17 | the states, four bits each: `0x010` — all zero, all one, all zero. No other state exists in this stage |
| 24 to 26, 28 to 31 | the PL envelope, the design's identification word, the four SLCR words: as in S2.1 |

The list lies at `0x10180000`, one word a read: the address in the low 28 bits, the number
of frames (1 to 3) above. The prober refuses a list with a count of 0 or above 3, an address
outside the envelope, or a read that runs past it; it looks at exactly as many words as word
16 says.

What it does, in order: the gates of S2.1; the reference frame; the design's
identification and one reading of the shift registers' outputs; CTL0; then for each state
the RAM written and read back, the counter, **the reads of the list**, the RAM read again,
the counter, the shift registers, the design's count of writes; CTL0; the reference frame.
1,418 accesses to the design in a run of three states, all in the log.

The result: the header, a PL block of 2,896 words (the log is longer than S2.1's), then
records of the form stages 2 to 7 use — 4 and three times the list. Two words of a record
that were free have a use in a read of the list: **the status (`INT_STS`) after the read**,
and, where bit 5 showed in it, **what the register read after that bit was cleared**
(otherwise `ffffffff`). The clearing writes `0x20` and nothing else, straight after the read
that showed the bit.

New stop: `0xa09`, the RAM did not hold its state after the frames were read. The stops of
S2.1 for the design (`0xa02`, `0xa04` to `0xa07`) and the gate stops are as there.

### The shares

Made from the census by `s2_2_shares.py` and by nothing else: the columns of block type 0 in
the order the device named them, each read in threes from its first address, whole columns
to a run.

| share | reads | frames | addresses |
|---|---|---|---|
| 0 | 174 | 516 | `0x00000000 .. 0x0000071b` |
| 1 | 174 | 516 | `0x00000780 .. 0x00000ea3` |
| 2 | 174 | 520 | `0x00000f00 .. 0x00001623` |
| 3 | 176 | 524 | `0x00001680 .. 0x004001a3` |
| 4 | 172 | 508 | `0x00400200 .. 0x00400923` |
| 5 | 176 | 524 | `0x00400980 .. 0x004010a3` |
| 6 | 172 | 512 | `0x00401100 .. 0x00401823` |
| 7 | 82 | 244 | `0x00401880 .. 0x00401ba9` |

1,300 reads, 3,864 frames: every address of block type 0, each once. A list holds at most
178 reads (section 19 said 179: the longer log took the room of one).

**The rule for the address register**, which the judge holds every read to: the register
passes through the addresses in the census's order, with one place more after the last
frame of a row, where it still shows that frame's address; after a read of n frames it is
n + 1 places on. This is S1b's finding written as one rule. It is held against everything
the board has said: all 25,230 clean records of the stored chains obey it — 1,900 of them
reads of three frames, some ending at a row's last frame — and so do the reads of S2.0 and
S2.1.

### The judge, the chain, the closing

The judge is section 19's: the list read is the list planned, read by read, in every state,
and the list is one made from the census; the address register; the log of accesses walked
against the sequence; the status after every read and the rule for the clearing; CTL0 the
same before and after; then every bit by its three readings. A run passes with any number
of candidates; restless bits fail it.

`s2_2_chain.py` drives the runs (a `reset`, then the run script, as S1b's chains did),
judges every stored run again from its raw words before it relies on it, and holds the
stored verdict to what the judge says now. It halts at a run that is not a passing run of
its share and **runs nothing again**. When every share has its run it closes the step: the
addresses read are counted against block type 0, the candidates of all runs against the
256 cells the design has, and the outcome is said in section 19's numbers — 1 (256), 2
(none), 3 (fewer), 4 (more), with 5 (some inverted) and 9 (bit 5, by run) beside it. The
places are written to `candidates.json`, labelled closed-book.

### Where what was built differs from sections 19 and 20

1. **The list goes to the board as a file, by YMODEM, like the prober** — not word by word
   as the parameters do. 178 words would be 178 exchanges at the prompt in every run. What
   is in memory is held to the list by U-Boot's checksum before `go`, whichever way it came,
   and the file sent is kept beside the run's record (`list.bin`).
2. **There is no separate echo of the list.** Every record says which address and how many
   frames it read; the judge holds the records to the planned list. A run that stops early
   has said nothing of the reads it did not make.
3. **A read that fails ends the run there**, with the stop of the interface or, for a short
   read or a pad that is not zero, `0x400`. Stages 2 to 7 read the reference frame once
   more before such a stop; this stage does not.
4. **All four DEVCFG words are read before the first failing gate ends the run** (S2.1's
   stage returned at the first). The header then has all of them. The SLCR is still read
   only once the gates before it hold, and nothing is written in either case.
5. **The chain's driver and the closing are one program.**
6. **The shift registers** are read once before the first state; every later reading is
   held to that one by the prober, and that one to the design's words by the judge.
7. **`status_seen.py` is not changed.** It lists bits from the transfers' own status words;
   the status after a read is another word, and bit 5 there is reported by the judge
   (`bit_5`) and by the chain's closing.

### What cannot be told, and is said so in the tests

- **A bit that flips once, in the all-one state, reads 0, 1, 0 as a cell does.** Three
  states cannot tell them apart. What stands against it is the count — one more than the RAM
  has cells is outcome 4 — and after that S2.3's code probes.
- Where the cells show in the twin is made up by the tests, differently for every seed.
  That the judge finds them wherever they are put says the judge is right about a device
  that behaves so; whether the board does is the run.
- A reference frame that held cells of the RAM would end a run with a health stop only if
  the last state differed from what was loaded. With the set's states it would not; and on
  the board the frame is all zero under `s2a` before and after the RAM was written (S2.1).

### Tests that changed their statement

- The bound on the image's size: 16 KiB since the first commit, 32 KiB now. Stage 8 came
  within 24 bytes of it, and no part of the memory map sets a bound (the image is at
  `0x02000000`; the next thing above is the PL design at `0x04000000`). It is a guard
  against growth by accident, and says so.
- The list of data constants a literal pool may hold has one more (which words of the
  block stage 8 uses); the one instruction that forms the PL's base is matched with a
  register's other name as well.
- The audit of stored runs takes a run of a share with its list.

### Mutants

949 mutants, none stale by the tool's own rule (735 before). Eleven older ones were anchored
on lines this work changed and were set right. 214 are new: 75 of stage 8, 88 of its judge,
14 of the shares and the rule for the register, 26 of the chain, 11 of the run script.

**They have not all been run.** The first run, of stage 8's, was stopped by the host after
66 mutants: the machine was short of memory, with eight copies of the suite running. I did
not start it again; that is for the owner to say. What the 66 showed
(`evidence/host_checks/mutants_2026-11-21_s2_2_first_part.txt`): 62 killed, 2 survived, 2
that the tool could not judge.

- *Survived: a list one read longer than a list may be.* The test for it passed for the
  wrong reason: the twin refuses a read beyond the list's room and hands the prober a zero,
  and the prober then refuses the list for that word. On a board the word would be read and
  the result area overrun. The test now also asks that the twin saw nothing it refuses;
  tried by hand, the mutant fails it.
- *Survived: a read of no frame taken from the list.* The same line refuses such a read a
  second time, by its last condition (a count of zero, less one, is above every distance).
  The mutant changes nothing that can be seen and was taken out; the plain check stays.
- *Not judged, two:* each put a new constant into the image, which the test of the image's
  literals refuses, and with the image every test that needs it fell — the tool counts that
  as a mutant that did not build. One said nothing the others do not and was taken out; the
  other was written again without a new constant (where bit 5 shows, the transfers' bits
  are cleared instead of it) and, tried by hand, fails two tests.

Not run at all so far: 11 of stage 8's, the two just changed, and every mutant of the judge,
of the shares, of the chain and of the run script, with the eleven that were set right. They
are due before this section can be called reviewed, and the complete set after that. A run
of the suite alone takes about 1 GB at its peak; eight at once fitted this machine on
2026-11-20, and why they did not today I do not know.

### My slips

- I counted the accesses of a state as 452; they are 451. A comment and a test said 452
  until the test ran.
- The made-up device of the first tests had nothing after block type 0, so the last read's
  register had no value to be held to; the real census has. Seen at the first run of the
  tests.
- Eleven older mutants were anchored on lines this work changed. This time they were found
  by the tool's own rule before any run (section 16), not by a run.
- In the check of a list, one condition I wrote is unreachable for any list of consecutive
  addresses the census can have (a read across a column's end is already an address the census does not
  have). I kept it — it guards the one place where an address is added to — and gave it a
  test with a census in which two columns are neighbours by number.

- I wrote that 79 mutants of stage 8 were chosen for the run that was stopped, and that 13
  of them had not run. It was 77 and 11: counted again on 2026-11-21 from the record and the
  list (66 ran; three of those are gone or renamed; 12 of the 75 there are now have no line
  in the record, one of them the one written again). The record's first line said 79 too
  and is set right; nothing the tool printed is changed.

### For the board, when the owner has reviewed this

- **The mutants of this work** that have not been run, and then **the complete set**, as the
  rule has it: 949 now, about nine hours on this host by yesterday's rate.
- Then, on the owner's word, the chain: a pre-check as before every step; `s2a.bit` is on
  the card; eight runs with a `reset` before each, about an hour; the first run's result
  committed before the second starts.
- If the first access to the design at the prompt does not return, the board has to be
  switched off and on, as in S2.1.

## 22. Review of `0417966` (2026-11-21): one finding, accepted and mended

A review of the host side of S2.2 as it stood at `0417966`, by a reviewer outside this work.
It found one fault, to be mended before the board. I reproduced it before changing anything;
it is as the review says, with one point to add. **Nothing has been on a board; the image is
a new one again.**

### The finding

Stage 8 reads the status register (`INT_STS`) when no transfer is running: after every read
of the list, and once more where it has cleared bit 5. Both words went into the record and
were looked at **for bit 5 alone**. An error bit in either, or a lost `PCFG_DONE`, changed
nothing: the run went on, and the judge, which looked at the same two words for the same one
bit, passed it.

### Reproduced, on the prober and the judge as they were

The twin got three faults for it (`prober/twin_hal.c`): `lateerr@D` — command D completes,
and once a status read has shown it done an error bit (`0x00040000`) appears; `latedrop@D` —
`PCFG_DONE` goes one status read after that; `clearerr` — the write that clears bit 5 raises
an error bit. Command 14 is the last of the list's first read.

| case | at `0417966` |
|---|---|
| `lateerr@14` | status after the read `50063004`; the run completes, 64 records; **PASS** |
| `bit5@2,clearerr` | after the clearing `50063004`; the run completes; **PASS** |
| a clean result with `PCFG_DONE` cleared in one record's status after the read | **PASS** |
| the same with an error bit set there | **PASS** |
| `latedrop@14` | the run stops one record later, `0x223`, at the next read's first transfer |

**The point to add.** For `PCFG_DONE` the prober was not blind: the read's own routine looks
at it in a status read just before this one, and every transfer looks at it before it
begins. A loss that lasted ended the run — one record late, and by a word other than the one
that showed it. For error bits there was nothing: every transfer begins by clearing them.
The judge had neither.

### What was changed

- **The prober** (`run_s8`, `s8_sts`): the status after a read of the list is held to what a
  transfer's own status is held to — no error bit, `PCFG_DONE` set — and so is the word read
  after bit 5 was cleared. The first that is not so ends the run at that read: the read's
  record gets the code (`0x21` an error bit, `0x23` `PCFG_DONE` lost), the run the status
  `0x221` or `0x223`, as for a transfer that fails.
- **Bit 5 is cleared only after a read with nothing amiss.** Before, it was cleared wherever
  it showed, also after a read that had failed. After a fault the prober now writes nothing:
  the register is left as it was found, and the header's last status shows it.
- **The judge** derives the read's code from the two words as well and holds the record's
  code to it; a clearing recorded after a read that was not clean is refused. Its rule that
  `PCFG_DONE` be the same before and after the clearing is gone: that case is now a stop the
  prober reports and the judge can follow. A stop of this kind is said as any other stop of
  the interface; nothing in the result is called inconsistent.
- One thing the judge cannot refute stays as it was in every stage: the read's own routine
  looks at `PCFG_DONE` in a status read it does not record, so a code of `0x23` with nothing
  recorded that shows it is taken — but not in a record that also shows bit 5 cleared, since
  the prober clears nothing after such a code.

The same cases now: `lateerr@14` stops with `0x221` at record 2 after 14 commands, nothing
written after it; `latedrop@14` `0x223` at record 2; `bit5@2,clearerr` `0x221`, the word
after the clearing in the record; the two changed results are refused (`record 5: code 0x0,
but its raw words say 0x23`, `… 0x21`).

**The image**: `prober.bin`, 16,472 bytes, sha256 `452b16c5…9098`, crc32 `3f67013b` (replaced
in section 23). The one of section 21 (`73d7bbf8…a01f`) was never on a board.

### Tests

774 (764 before). On the twin, `TheStatusBetweenTransfers` (7): an error bit after the last
transfer, in the first state and in the second; `PCFG_DONE` lost; both after the clearing;
nothing written after a read that was not clean, bit 5 or not; a read that failed by itself
keeps its own code; clean runs have every code zero. For the judge (3): each such run is a
stop it follows and says nothing else about; a clean result with any one bit of the error
mask set, or `PCFG_DONE` cleared, in either word is refused; a stopped run with its code, its
words or a clearing changed is refused.

### Mutants

961, none stale by the tool's own rule (949 before). Nine were anchored on the lines changed
and were set right, one of them taken out with the rule it stood for; 13 are new, six of the
prober and seven of the judge. **None of them has been run by the tool** — the run that was
stopped (section 21) has not been started again, and that is still the owner's to say. The
22 that are new or changed, and the one of section 21 that was written again, were tried by
hand, one at a time, against the two test files of S2.2: all 22 fail them. That is not the
tool's run of the whole suite and does not stand for it.

### Not mended, and the owner's to decide

**An error bit that appears between two transfers of one read is still not seen.** Found
while reproducing: `lateerr@11` (after the frame read, before the register is read) passes,
before this change and after it. Every transfer begins by writing the clear mask and then
checks that the bits are gone; what stood in the register before that write is never read.
This is the sequence of every stage since S1a, taken from zynq-psmap, and all 197 stored
results were made with it. A test pins it as known
(`test_not_seen_an_error_bit_that_appears_between_two_transfers_of_one_read`).

What stands against such an error today is the data: no word of a read may keep the value
put there before it, the pad must be zero, the address register must read what the census
says, and every frame is read in three states.

It could be closed for stage 8 alone: one read of the register before each clear, and a stop
if it shows an error bit. Other stages would make the accesses they always made. The first
transfer of a run would then meet whatever U-Boot left; in all 197 stored results the status
at the gates is `50021004`, no error bit. It costs another image and the tests of stage 8
that count accesses. **I would do it before the board** — after the board it costs the
chain again — but it changes the transfer routine every stage shares, so I have not.

### My slip

Section 12, point 7, has the status recorded after every read and bit 5 cleared alone, and
I built exactly that: the word recorded, and judged for the one bit the point was about. A
word the prober reads and nobody judges is not a check — a rule this project has had since
S1b, and I did not hold the new word to it.

### For the board

As in section 21, with the numbers of today: the mutants of S2.2 that have not been run by
the tool, then the complete set (961), then the owner's word. The decision above first, if
it is to be built.

## 23. Review of `9fa606e` (2026-11-21): six findings; five mended, one for the owner

A second review, of the whole repository as it stood at `9fa606e`. Six findings. Each was
reproduced here before anything was changed; all six are as the review says. **Nothing has
been on a board; the image is a new one again.**

| | finding | here |
|---|---|---|
| 1 | high — an error bit between two transfers of one read is cleared unseen | mended (the owner's word: before the board) |
| 2 | high — a chain that is gone on with does not hold its stored runs to the prober image and the design | mended |
| 3 | medium — the chain's driver runs on without the first run committed | mended |
| 4 | medium — a clean copy of the repository cannot run the tests | reproduced; for the owner — decided and mended, section 24 |
| 5 | low — the dry run states the wrong length of the result | mended |
| 6 | low — a stored record that is not a record ends in an exception; a list of candidates outlives its chain | mended |

### 1. The status register before every clearing

Section 22 left this to the owner, who said: before the board. Every transfer begins by
writing the clear mask; what stood in the register before that write was never read.

**In stage 8 the register is now read first** (`dma()`), and an error bit in it ends the
transfer there — code `0x24`, nothing cleared, nothing queued, the word kept in the record
as that transfer's status with no poll. The run ends at that read: status `0x224`, or
`0x624` at the first reading of the reference frame. The other stages make the accesses
they always made; a test counts the reads of the register between a transfer and the next
clearing for stages 6 and 7 (two, and three where a read ends) and for stage 8 (one more).

On the twin, `lateerr@D` for every transfer of a read but the last now stops the run before
transfer D + 1 begins, in the list (any state), at CTL0 and at the reference frame; after
the last transfer it is the status after the read that shows it, as section 22 has it. The
test that pinned the gap as known is replaced by these.

**What the judge cannot tell.** A transfer that was never queued records one status word.
With an error bit in it, the word does not say whether it was read before the clearing
(`0x24`) or after it (`0x20`, a bit that would not clear): the judge takes either code there
and neither anywhere else. Both are stops.

The first transfer of a run meets what U-Boot left: in all 197 stored results the status at
the gates is `50021004`, no error bit.

A test of the image that named a register of the compiler's choosing (`cmp r4, #1` in
`dma()`) now asks for the comparison in whichever register it is; the routine that waits
without touching memory is unchanged, and its test with it.

### 2. Stored runs held to the image, the design and the list

Reproduced: with the set's two declared hashes changed, stored runs still passed and the
chain went on; a damaged `list.bin` likewise. The census had this check since its own review
(`docs/s1b_plan.md`, section 69); the chain of S2.2 was written without it.

`s2_2_chain.py` now holds the set in force to files — the prober image (the copy kept with
the runs; the build's where none is kept) and the staged design — and every stored run's
record to the set: the image's checksum in the step just before the prober was started and
again after it returned; the design's in the step just before its load; the list's before
the start; and the list kept beside the run must be the list planned for its share. **The
driver keeps the image with the runs** when it makes the first (`prober.bin` beside
`run00`). A chain begun with one image does not go on with another: the kept copy is then
not the image the set declares, or the records do not show the declared one.

### 3. The first run alone

Section 21 has the first run's result committed before the second starts; the driver ran
all runs through. Now **no second run is started until everything in `run00` is in git as
it stands** — tracked, unchanged, nothing untracked or ignored beside it. Until then the
chain is "held", which is not a halt, and `--max-new` does not get past it.

### 4. A clean copy cannot run the tests — for the owner

Reproduced on an archive of `9fa606e`: 774 tests, 12 failures and 450 errors — 408 for
`build/pl/carrier.bit` and 37 for `build/pl/s2a.bit`, neither of which is in git (`build/`
is ignored). With the two files put there, all 774 pass.

`s2a.bit` has a tracked copy (`evidence/s2_1_17A6_2026-11-20/`, the same bytes). The carrier
has none here: it is zynq-fabricmap's (`gate_runs/claimb_round1_carrier_2026_08_13_erratum006/`,
tracked there, sha256 `8c3369e8…0b8a`). To mend it the carrier would have to come into this
repository as an imported file, with a record like the two Verilog files have — and that
record says, by the owner's decision of section 12, point 4, that nothing else of that
project is copied. **So this is the owner's to say.** What I would do: import `carrier.bit`
with its record (2 MB), and have the tests put both designs into `build/pl/` from their
tracked copies, each held to its recorded hash, where they are missing. It does not stand
in the way of the board.

### 5. The dry run's length of the result

It said `64+480*N` words for every stage; for S2.1 and S2.2 the records begin after the PL
block (`2640+480*N`, `2960+480*N`). The run itself always took the length from the result's
header. The dry run now says the header of the stage's own layout.

### 6. Two cases of a stored chain that is not as it should be

A `run.json` that parses but is no record (`[]`) ended in an exception: now a halt that says
so, and the same for steps that are no list. A `candidates.json` written for a complete
chain stayed when a later look found the chain halted: looking (without `--go`) still writes
nothing but says the file is there and does not stand; the driver takes it away.

### The image, the tests, the mutants

`prober.bin`: 16,532 bytes, sha256 `e44c5d7b…bda4`, crc32 `ad72adb3` (replaced in section
25). Neither image before it of this step was on a board.

791 tests (774 before).

990 mutants, none stale by the tool's own rule (961 before): four set right, 29 new — five
of the prober, three of the judge, twenty of the chain, one of the run script. **None has
been run by the tool**; the run stopped on 2026-11-21 (section 21) has not been started
again. All 33 were tried by hand, one at a time, against the test files they concern: 32
failed them at once. **One survived**: "every stage reads the register before it clears it"
— no test of the older stages noticed one read more before each clearing, so what section 22
and this section say of them ("the accesses they always made") was said and not held. The
test that counts those reads was written for it, and the mutant fails it. As in section 22:
this is not the tool's run and does not stand for it.

### My slips

- The chain's driver was written from S1b's and not from the census, where the check on
  images had been asked for by a review two days before. A check a review once asked for in
  one tool belongs in the next tool of its kind.
- I wrote "the other stages make the accesses they always made" before any test said so.

### For the board

The mutants of S2.2 that the tool has not run, then the complete set (990), then the owner's
word; the board's serial adapter has not been attached to this host since 2026-11-20. With
the driver as it is now the first step on the board is one run, a commit of it, and then
the rest.

## 24. The carrier imported; a clean copy runs the tests (owner, 2026-11-21)

Finding 4 of section 23. The owner's decision: import the carrier's bitstream, with a record
of where it is from. This adds to section 12, point 4, which had two files of zynq-fabricmap
copied and nothing else; the import record now says both decisions.

**What was done.**

- `imported/fabricmap/carrier.bit`: 2,083,863 bytes, sha256 `8c3369e8…0b8a`, from
  zynq-fabricmap `gate_runs/claimb_round1_carrier_2026_08_13_erratum006/carrier.bit` at
  commit `90829f8e`, unchanged. It is byte for byte the file every run of S1 and S2.0 was
  made with (`build/pl/carrier.bit` here), and its hash is the one zynq-psmap's record of
  the known frames names (`data/known_frames_17A6.json`). The record is
  `imported/fabricmap/IMPORT.json`.
- `host/stage_designs.py`: puts a design that is missing in `build/pl/` there from its copy
  in git, once the copy has the hash and length its record gives — the carrier from the
  import, held to the import record; `s2a.bit` from `evidence/s2_1_17A6_2026-11-20/`, held
  to `pl/s2a/build.json`. A copy that is not what its record says is refused and nothing is
  written. A design that is already staged is left as it is: the run script and the chain
  hold what is staged to the set before they use it.
- The tests' step that makes `build/` ready (the image built, the sets written:
  `tests/test_prober_image.py`) stages the designs as well; the one test that needs a
  design without going through that step stages it itself.

The files stay opaque: read whole, hashed, written. The test that reads every file of the
design for a word of the database or a frame address passes the bitstream by, and says why.

**Held.** An archive of the tree as committed, with no `build/` and no `.git`: the whole
suite passes — 798 tests, one skipped (it asks git which files are tracked, and there is no
git there). The prober built there from source is the image of section 23 (`e44c5d7b…bda4`).
Before, the same archive gave 12 failures and 450 errors.

798 tests (791 before). 992 mutants, none stale; the two new ones, of the staging program,
were tried by hand and fail its tests. One thing no mutant can show in the working tree:
that the readiness step stages the designs at all — with `build/` in place nothing is
missing. Only a clean copy shows it, and that was run by hand as said above. None of the
mutants of S2.2 has been run by the tool yet (sections 21 to 23).

Not changed: `build/` stays out of git; a design is not built again by any test.

## 25. Review of `334df53` (2026-11-21): four findings, all accepted and mended; and why mutants were "not judged"

A third review. It confirms the six of section 23 as mended and a clean copy as running, and
finds four more. Findings 1 and 2 were reproduced on the twin before anything was changed;
3 and 4 follow from the code as it was, and the premise of 4 is now asserted in a test.
**Nothing has been on a board; the image is a new one again.**

### 1. (high) Between the read of the register and the write that clears it

Section 23 had stage 8 read the status register before each transfer cleared it. An error
bit that appears between that read and the write was still cleared. Reproduced with a new
fault of the twin, `preclear@D` — the bit set just before the write that begins command D:
all 318 commands were made and the judge passed the run.

The review's own proposal is what was built, and it is the better mechanism: **stage 8
clears the two done bits when a transfer begins (`0x00003000`) and never an error bit.** The
read before the write is gone again. The check after the write is the one every stage has
— the register must be clean — and in stage 8 an error bit there stood before the transfer
was to begin, whenever it appeared: code `0x24`, the transfer not queued, the bit left
where it is. A done bit that would not clear is `0x20` as before. So the two codes no longer
overlap, and **the judge holds each exactly**: what section 23 called "what the judge cannot
tell" is no longer so.

The other stages write what they always wrote. Both transfer routines (the wait as it was,
and the one that touches no memory) begin alike, and a test runs each.

The first transfer of a run now also meets, and no longer clears, an error bit U-Boot left;
in all 197 stored results the register at the gates is `50021004`.

### 2. (medium) After the reads that are not of the list

The register was looked at after a read of the list only. Reproduced: an error bit after
CTL0's last transfer (`lateerr@9`) was met by the next transfer — after the RAM had been
written for the first state; after the reference frame's first reading the design had been
read before the stop; after the last transfer of all (`lateerr@318`) the prober said done
and it was the judge that failed the run, from the header's last status.

**The register is now read, recorded and held after every read of the stage** (`s8_read`):
the reference frame, CTL0 and the list alike. The run ends at that read, before the design
is touched again: `0x621` at the first reading of the reference frame, `0x221` elsewhere,
the last record included. Bit 5 is cleared after a read of the list only, as agreed; after
another read it is recorded, reported, and left for the next read of the list to meet.

What is left: the moment between the last look at the register and the next thing done.
After the last record that is the header's own reading of the register, which the judge
holds.

### 3. (medium) The board reset for a run the run script then refuses

The chain held the set to the image kept with the runs; the run script loads the build's.
With the two apart the driver reset the board, the script refused, and a run directory
without a record halted the chain. In section 23 I had this check in mind and left it out
as implied by the others. It was not: the others look at the kept copy.

Now, before anything is sent: the driver holds the build's image to the set and to the kept
copy (`ready`), and the board's runner asks the run script's own dry run of that share
whether it refuses (`refusal`). Either way nothing is sent, no directory is made, and the
chain is held, not halted.

### 4. (low) The commit check asked `git status`

A tracked file that git was told to assume unchanged, or to skip, shows in no status. The
check no longer asks the index anything: **the files under `run00` are hashed and held to
the tree of the last commit**, both ways — every file there in the commit with those bytes,
every file of the commit there. The test sets both flags and asserts that `git status` says
nothing and the check still refuses.

### Why two mutants were "not judged" on 2026-11-21, and it was not the mutants

Section 21 says of two mutants that each put a new constant into the image, that the
image's tests refused it, "and with the image every test that needs it fell — the tool
counts that as a mutant that did not build". I took one out and wrote the other again.

That was the wrong mend. Found while trying this section's mutants by hand: three of them,
two of them as old as the prober, showed fewer tests run. The cause is **a test class of
mine** (`WithAShare`, written with S2.2): it made `build/` ready in `setUpClass`. Every
other test does that before each test. When a test of the image fails, a class that
prepares once runs none of its tests; the suite runs six fewer; and the tool, which counts
tests, says BROKEN. Fourteen of the first 230 mutants of the prober fail a test of the
image — most of them are there to be caught by exactly those tests — and every one would
have been BROKEN in the complete run.

The class now prepares before every test, a test holds every test file to that, and the
mutant taken out in section 21 is back (it fails two tests). The three I had begun to write
again for the same wrong reason are killed in either form.

### The image, the tests, the mutants

`prober.bin`: 16,680 bytes, sha256 `94ad860c…6f50`, crc32 `ed47e7ab`. None of the images of
this step has been on a board.

806 tests (798 before).

1,002 mutants, none stale. This change moved the anchors of 42; all were set right, five of
the withdrawn mechanism were taken out, and those of the new one added. The 52 that are new
or changed were tried by hand against the tests of the prober and of S2.2, one at a time:
all fail them, with the count of tests run unchanged. Two I had written did not build (a
parameter left unused) and were written again before they counted. **None has been run by
the tool**; that is still the owner's to say, and the complete set is still due before the
board.

### My slips

- Section 23, finding 1: I read the register and then cleared it, and did not ask what
  happens between the two. A check and the act it guards have to be one step, or the act
  must not be able to destroy what the check looks for.
- Section 22: "after every read of the list" was the plan's wording for bit 5. I gave the
  new check the same reach without asking where else a read ends.
- Section 23, finding 2: I wrote down that a check was implied and did not build it.
- Section 21: a mutant the tool cannot judge is a question about the tests first. I changed
  the mutants and did not look at why the count of tests fell.

### For the board

As before: the mutants of S2.2 by the tool, then the complete set (1,002), then the owner's
word. On the board the first step is one run; it is committed; then the rest.

## 26. Review of `c1e932b` (2026-11-21): three findings, all in the chain's driver, all mended

A fourth review. It confirms the four of section 25 and finds three more, one medium and two
low, all in `host/s2_2_chain.py`. Findings 1 and 2 were reproduced here before anything was
changed; 3 is plain from the code as it was. **The prober and the judge are not touched:
the image is the one of section 25.**

### 1. (medium) The name of a run taken by something that is not a directory

The chain looked at directories only. With a plain file called `run00` it took `run00` for
the next run; the run script's dry run was not told where the run would write; the board was
reset; and only then did the run script refuse the directory, after which the driver ended
in an exception. Reproduced: the chain said "go on", the runner was called, `FileExistsError`.

- A name of a run that is not a directory — a file, a link, also a link to a run's directory
  — **halts the chain when it is looked at**, before anything is asked or sent.
- The run script's dry run takes `--out` and says of it what the run would say
  (`host/s1a_run.py`: the check stood after the dry run's return); the driver passes the
  directory when it asks.

### 2. (low) Links in the commit check

A link that leads nowhere was passed by (it is no file), and a committed file replaced by a
link to the same bytes passed (the bytes were read through it). Reproduced, both.

`committed` now walks the directory without following links and **refuses anything that is
not a plain file or a directory**, under the run and in the last commit's tree alike (a
link committed as a link is refused too); the run's directory itself may not be a link.

### 3. (low) What the command said and what `chain.json` said

A refusal by the dry run was raised inside the board's runner: the command printed HALT and
ended with a code, while `chain.json` — written before — said "go on" and gave no reason.

The asking is the driver's now (`refuses`), before the runner is called, with the image
check of section 25. Whatever keeps a run from being started — the image, the run script's
refusal, a board that did not come up fresh after its reset — leaves the chain **held, with
the reason, and marked `blocked`**, in `chain.json` as in what the command prints; the
command ends with a code then. A chain held because the first run is not committed yet is
not blocked, and the command ends without a code as before: a run is waited for, none
failed to start.

### Tests, mutants

811 tests (806 before): a name of a run taken by a file, by a link that leads nowhere and by
a link to a run's directory; links under a run, in the commit, and as the run's directory; a
refusal and a runner that could not begin, each in what is returned and in `chain.json`; the
command's code, through the command itself; the dry run with a directory.

1,015 mutants, none stale (1,002 before): three set right, 13 new. All 16 were tried by
hand against the tests of the chain and of the run script, one at a time; all fail them,
with the count of tests run unchanged. None has been run by the tool.

### Whether more is to be mended

Asked by the owner with this review. The four reviews, in order: a status word judged for
one bit only (the prober and the judge); a gap between transfers, and a chain not bound to
its image; the moment between a read and a write, and reads the check did not reach; and
now three ways the chain's driver can be led astray by what lies in its directory. The first
three changed what a run on the board would have said. This one does not: every case of it
ends, on the code as it was, in a run that is not made or a chain that stops — a board reset
for nothing at worst, never a result judged wrongly. It was worth mending because it was
cheap and because the driver is what is trusted to stop.

What I know to be open is said where it belongs: the moment between the last look at the
register and the next act (section 25); a single flip in the all-one state that reads as a
cell (section 21); and that **no mutant has been run by the tool since 2026-11-21's run was
stopped**. That last is the largest: 1,015 mutants, of which every one of S2.2 has only
been tried by hand or not at all. It is due before the board, and it is the next thing.

## 27. The complete set of mutants on the image of S2.2 (2026-11-21 and 22): 1,015, all killed in the end

What section 26 named as the largest thing open. The owner said on 2026-11-21 to run the
set four at a time. It took four starts, and on the way it found one fault in the tool, one
test that could take the machine's memory, two mutants that did not build, one class of
tests that could vanish from the count, and **one survivor: a rule of the chain that no test
held**. Nothing under `prober/` or `host/` was changed by any of it: the image is the one of
section 25 (16,680 bytes, sha256 `94ad860c…6f50`), and the judge and the chain are as
section 26 left them.

### What was run, and on what

| started (GMT) | on | from | at a time | judged | killed | survived | BROKEN | how it ended |
|---|---|---|---|---|---|---|---|---|
| 11-21 16:59 | `c5b1ba1` | 0 | 4 | 1 | — | — | — | stopped by me: the tool took the unmutated tree for one with no result |
| 11-21 17:18 | `8247f74` | 0 | 4 | 818 | 817 | 0 | 1 | stopped by the session, about 11-22 08:50: the machine short of memory |
| 11-22 08:57 | `0c9143e` | 817 | 8 | 3 | 2 | 0 | 1 | stopped by the session, between 09:11 and 09:27: the same |
| 11-22 09:49 | `e70d932` | 818 | 8 | 197 | 195 | 1 | 1 | by itself, 12:52: every scratch copy restored |
| 11-22 13:01 | `76697f4` | two by name | 1 | 2 | 2 | 0 | 0 | by itself: restored |

No mutant was stale in any of them. The records are
`evidence/host_checks/mutants_2026-11-22_set_1_stopped.txt`, `…_set_2_stopped.txt`,
`…_set_3_rest.txt` and `…_set_4_two.txt` (nothing is kept of the first start: one line).

**Every one of the 1,015 has been killed by the tool**: the first 817 of the list in the
second row, the 818th in the third, 195 of the remaining 197 in the fourth, and the last two
in the fifth. One (the 820th) was judged twice and killed twice.

They were not all killed on one commit, and that is to be said plainly. Between the first
verdict and the last, these changed and nothing else: the tool itself (how it reads the
suite's last line; where a run begins; two mutants rewritten so that they build), a helper
of `tests/test_prober_s2_2.py` (below), the setup of one class of `tests/test_s2_2_host.py`
(below), and four tests added. No test was taken away or made to ask less, so a mutant
killed on an earlier commit has, on the last, every test that killed it — with the one
helper as the exception I cannot rule out by argument alone: it now follows at most four
frames of a record where it followed whatever the record said. I know of no mutant whose
killing rested on more than four; I have not run the first 817 again to show it.

### 1. The tool: a suite that passed with a skipped test

The test of section 24 that asks git is skipped where there is no `.git`, and the tool's
scratch copies have none; unittest's last line is then `OK (skipped=1)`, the tool looked for
a line that is `OK` and nothing more, and said "Ran 811 no result" of the unmutated tree.
It went on regardless; I stopped it after one mutant. The tool now reads `OK` with whatever
follows it in brackets, **and refuses to begin on a tree that did not pass** — before, only
a tree that failed was refused (`8247f74`; `tests/test_mutants_tool.py`).

### 2. The memory: a test followed a count of four thousand million

Both stops fell at the same place in the list, and I did not see it at the first: I
reported that stop as the machine's and its cause as unknown, and the owner, who had
started other programs, took it for theirs. At the second it could not be missed. The
mutant "s8: its records begin where stage 7's do" puts stage 8's records over the PL block;
word 14 of a record, the count of frames, then reads as anything; and `Run.rec` in
`tests/test_prober_s2_2.py` built a list with one entry for each. Shown by hand, the one
mutant in place against the two test files of S2.2 with the address space held to 6 GB:
6,028 MB resident, 18 lines of `MemoryError`, 403 seconds. With the helper holding the count
to what a record has room for: 130 MB, 48 seconds, the mutant killed (`e70d932`).

**The judge was looked at for the same thing and does not have it**: it refuses a count of
accesses above the log's room and a count of frames outside 1 to 3 before it follows
either. A result from the board with such a word in it is refused, not followed.

### 3. Two mutants that did not build

"s8: a failure of the interface is taken for a short read" and "s8: the RAM's read-back is
held to all zero whatever the state": each replacement left a parameter unused, which the
build refuses. Both date from section 21 and were among those never run. Rewritten so that
the parameter is still named (`&& 0`, `& 0u`); both killed by the tool since.

### 4. A class of tests that could vanish from the count

"shares: the whole of a row is one column" builds, and the suite under it ran 808 tests of
818: the cutting of the census refused, the class `Shares` did its cutting once for the
class, and its ten tests did not run — which the tool, rightly, does not take for a kill.
The same kind of thing as section 25's, in another class. The cutting is done before every
test now (`76697f4`), and the mutant is killed with the count whole.

### 5. The survivor: what the closing finds did not have to halt the chain

"chain8: the closing's problems do not halt it" — with the line that halts the chain for
what all runs together show (addresses read that are not block type 0's, a place that is a
candidate in two runs, CTL0 not the same in every run) taken out, every test passed. The
three findings were tested on `close` by itself; nothing held `assess` to acting on them.
On the board this would have been a chain of eight runs called complete, with a list of
candidates written, though its runs did not agree.

New test: CTL0 reads as another value all through the second of three runs. Each run passes
its judge (which holds a run's two reads of CTL0 to each other and to nothing else); the
closing does not; the chain is halted, no list of candidates is written, `chain.json` says
halted, and it is halted when looked at again. The mutant is killed by it.

### Tests, mutants

819 tests (811 at section 26): four of the tool, one of the helper, two of where a stopped
run goes on, one of the chain — and `Shares` and its ten as before. 1,015 mutants, none
stale; `SM_MUTANT_FROM=n` passes by the first n of the list, for a run that was stopped.

### My slips

- The first stop's cause. Above, under 2.
- **Times.** I said about 13 hours for four at a time; it was a rate of 0.9 a minute, which
  is 19. At the first look I said the rate "matched" the 13 hours when it already gave 20.
  Eight at a time was 1.1 a minute, not twice four.
- The line "# ended … exit code" that I wrap around a run took the code of the `date` in
  the same line, not the tool's, in the first three starts: it would always have said 0.
  None of those three reached it. From the fourth start on it is the tool's own.

### For the board

The owner's rule — the complete set before a new image first goes on the board — is met for
the image of section 25. Nothing of S2.2 has been on a board. The next step is the first
run alone (section 23), on the owner's word and with the board's serial line attached to
this machine again; it has not been since 2026-11-20 21:46 GMT.

## 28. S2.2 on the board (2026-11-22): complete — 256 candidates in four frames; the RAM undisturbed

On the owner's word for the chain. The full account is
`evidence/s2_2_17A6_2026-11-22/RESULT.md`; this section is what the plan needs of it.

### What came out

**Outcome 1 of section 19, and with it outcome 9.**

- Eight runs, one of each share, every one PASS: 3,864 addresses of block type 0, 1,300
  reads a state, three states. Image `94ad860c…6f50`, on a board for the first time.
- **256 candidates**, none inverted, no restless bit; 12,488,192 other bits the same in all
  three states. All 256 in the run of share 6: **`0x00401220`, `0x00401221`, `0x00401222`,
  `0x00401223`, words 61 and 62 of each, all 32 bits** — 64 a frame.
- **The RAM held its state through every pass** (24 passes), read back through the design's
  registers. The counter ran, the shift registers were as loaded and not shifted.
- **CTL0 `0x00000501`** at all 16 readings. Question 4 of section 1 (is LUT RAM masked in
  PCAP readback?) is answered for this design and this register value: no. Question 5 (must
  the design be stopped?): for a RAM that is not being written, no — it is read, and it is
  not disturbed. Nothing was written to MASK or CTL0, and section 12's point 3 stays as it
  is: not designed.
- **Bit 5** showed after two reads, `0x0000181e` and `0x00001821`, the same two in each of
  the three states, in the run of share 3; cleared each time, never still set. The reads
  that deliver the four frames with the candidates raised nothing in any state.

### What this says to the question S1b left (section 1, and S1b's sections 53 to 57)

Outcome 9 asked whether bit 5 comes with frames whose RAM content is no longer what was
loaded. **Not with these:** the four frames were read while the RAM held all ones, having
been loaded all zero, and the bit did not show. It showed with six frames in another column,
whose content did not change between the states.

A guess, marked as one and not in any program: the design has a second kind of memory, the
shift registers, loaded with words that are not zero and never shifted; the frames that
raise the bit are the last of a column of 36, as the candidates are the last four of
theirs. If those frames hold the shift registers, the bit comes with their content as
loaded, not with a change. S2.4 is the step that finds where the shift registers are, and
will say. Nothing else is done about it now.

### The run that stopped

The first try of share 1 ended with no prompt after the dump of the result header: the
console lost stretches of the reply and all but the first letter of the prompt. The run
script stopped, as section 43 of `docs/s1b_plan.md` has it for a missing prompt; nothing
was saved or pulled; the chain halted and was reported. The owner: set aside, and the chain
taken up again; nothing taken from memory by hand; the run script not changed. It lies in
`halted_at_run01/` and the share passed at the second try. One such loss in 196 stored runs;
the rule stays as it is.

### Differences from what was written beforehand

- Section 21 has the pre-check "as before every step"; there were two, one before each time
  the board was taken in hand.
- The set's file `expected_s2_2.json` was copied to the runs after the chain closed, not
  before the first run as in earlier steps: the driver keeps the image with the runs and
  not the set. Each run's record has the parameter words and its list as they were sent,
  and the test that assesses the stored chain holds the copy to the image kept by the
  driver.
- I wrote the background command for the second start so that it ended with the exit code
  of a `grep`, not the driver's; the driver's code (1, at the halt) was in a line the
  command printed, and that is where I read it. The third start ends with the driver's own.

### Tests

820, then 821. The audit of stored runs counts 196 (nine more: the eight and the one that
stopped). `tests/test_status_seen.py` said no run outside block type 1 had a status bit of
this kind; it now names the one that has, and a test holds what its record says.
`tests/test_board_evidence.py` assesses the stored chain again from the raw words — state,
candidates, the closing, `chain.json` and `candidates.json` as the programs give them now —
and names the header dump of the stopped run as the second stored reply that is not whole.
No program of the host or the prober was changed, so no mutant was run.

### Next

S2.3 is not proposed in full; its outline is section 8. What it now has to start from: four
frames, two words in each. The proposal is the next thing to write, on the owner's word.

## 29. S2.3 — which configuration bit is which bit of the RAM (proposal, 2026-11-22)

For the owner. Section 8 outlined this step; S2.2 is in. This section is the step in full.
The points to decide are at its end. Nothing of it is built.

### What is known now that section 8 did not have

| fact | source |
|---|---|
| 256 bits of block type 0 follow the RAM, and no other: the addresses `0x00401220` to `0x00401223`, words 61 and 62 of each, all 32 bits | S2.2, section 28 |
| These are the last four frames of a column of 36, `0x00401200` to `0x00401223`; the shares read it in twelve reads of three frames, the last two of them `0x0040121e` and `0x00401221` | the census; the list of share 6 |
| Reading those frames does not disturb the RAM, and raises no bit 5, in the states all zero and all one | S2.2 |
| The design's RAM takes a state that differs from address to address and gives it back: the address's low four bits and their complement, at all 64 addresses | S2.1 (stage 7's four states) |
| A state costs 451 accesses to the design (the RAM written and read back, read again after the frames, the counter, the shift registers, the counts), each two words in the log; a read with its record is 480 words; the result area holds 262,144 words | stage 8 as built, section 21 |
| A megabyte of result takes seven and a half minutes to pull | the eight runs of S2.2 |
| The complete set of mutants is 1,015 and ran at 0.9 a minute, four at a time: 19 hours | section 27 |

Not known, and what this step asks: which of the 256 places is which cell. S2.2 wrote all
cells alike. That one frame is one memory, that a word is half of one, that the bits lie in
the order of the addresses — each of these is a thought the numbers invite, and none of
them is in any program or assumed by any check below.

### The numbering

A cell of the RAM is named from the design's side and from nowhere else: **memory k (0 to
3: the bit of the data register it is written by) and address a (0 to 63: what the address
register held)**. Its number is n = 64 k + a, eight bits. The description this step writes
says, for a place in configuration memory, which n it is. It does not say which LUT of the
slice memory k is, nor which pin carries which address bit (section 10); the build's own
record of where it put each memory (`pl/s2a/build.json`) can be copied beside the table as
what the build said, and is marked as that.

### The states

All through the design's registers, as before.

- **Base**: all zero.
- **Code states**, eight and their complements: in code state j every cell holds bit j of
  its number; in the complement, the opposite. For j below 6 that is a pattern over the
  addresses, the same in all four memories; for j = 6 and 7 it is whole memories, zero or
  one.
- **Singles**, 256: cell n holds one, every other cell zero.

### The runs

**The code run — one run.** The gates, CTL0 and the reference frame as in S2.2; then
eighteen states — base, the eight code states each followed by its complement, base again;
in each, the state written and read back through the design, the **twelve reads of the
column**, the RAM read through the design again (it must still hold the state), the
counter, the shift registers, the counts; CTL0 and the reference frame. 216 reads; about
120,000 words, half a megabyte: one run, about five minutes with its pull.

**The singles — four runs of 64 states.** Run r has the singles of the cells 64 r to
64 r + 63, with the base state before the first and after the last. In each state the
**two reads that deliver the four frames** (`0x0040121e` and `0x00401221`: six frames, two
of them not among the four), and everything around them as above. About 120,000 words a
run; about twenty minutes for the four.

In all about half an hour of board time, five runs, a `reset` and a fresh load of the
design before each.

The status is recorded after every read and bit 5 cleared alone where it shows, as stage 8
does. Nothing is written to configuration memory or to a configuration register.

### What the host does with it

Per run, from the raw words and after they are saved: everything S2.2's judge holds (the
list, the address register, the log of accesses walked against the planned sequence, the
status words, CTL0, the RAM as read back before and after every pass). Then:

**The code run.** For every bit of every frame read, its eighteen readings.

- A bit is *still* if all eighteen are alike.
- A bit *spells* n if it reads 0 in both base states, bit j of n in code state j and the
  opposite in its complement, for all eight j. (Or all of that inverted: recorded as
  inverted, as S2.2 would have.)
- Anything else is *irregular*: it changed and spells nothing.

The run passes if nothing else is wrong and there is no irregular bit. The decoding is then
closed by a program over the verdict: **the bits that spell are exactly the 256 places of
S2.2; every n from 0 to 255 is spelt by exactly one.** That is the table at confidence 1,
written out and committed before any single is run.

**The singles.** For state n, the bits that differ from the base reading of the same run:
**exactly one, and it is the place the table has for n.** The base at the end of the run
must read as the base at its start. Each entry that holds is at confidence 2, and has the
record numbers of its eight code states and of its single.

The singles are judged against the committed table and by nothing else; the table is held
by its hash in the chain's record.

### What may come out, said beforehand

The code run:

1. **256 bits spell, each a number of its own, and they are the 256 places of S2.2; every
   other bit of the column is still; the RAM undisturbed.** The table at confidence 1.
2. **Two places spell the same number, or a number is spelt by none.** No table. Reported
   with the readings; the singles are not run.
3. **Irregular bits.** A place that follows the all-one state and not the patterns, or one
   whose complement readings do not agree. The run fails and names them; no singles.
4. **A bit that was still in S2.2 changes.** Something follows a pattern that did not
   follow all ones. It either spells (then there are more than 256, or it is not one of
   S2.2's) or is irregular; in both cases reported, no table, no singles.
5. **Places that spell inverted.** Recorded as found; not a failure.
6. **The RAM does not hold a state after the frames were read.** S2.2 saw the two uniform
   states undisturbed; a pattern is new. The prober stops there, as in S2.2.
7. **Bit 5 shows.** Recorded, cleared, reported: it did not show in this column in S2.2.
8. **The design did not go on, the interface fails, the address register is not what the
   census has.** A stop, as always.

The singles, for each cell:

9. **Exactly the decoded place differs.** Confidence 2.
10. **Another place, more than one, or none.** That entry is a contradiction (confidence 0)
    and the run fails; the chain halts there. What the other singles of that run said is
    stored and reported.

The table itself is looked at only after it is committed: whether a frame is a memory,
what order the addresses have. What is seen is written down as seen. It is the first thing
in this project that S2.5 could find to be different at another site.

### What is written out

`schemas/self_map_v2.schema.json` is the structure description the proposal names, copied
as it is. Three of its required parts have no counterpart here: the `binding` (a token and
a universe of zynq-fabricmap's sessions), the `genome_bit`, and a `relation` whose only
kind is `lut_init` with an `init_index` — which would say that the RAM's address is the
index of a LUT's truth table, the very thing section 10 says S2 does not show.

I propose a document of this project's own, modelled on it as the census's was
(`schemas/ram_map_v1.schema.json`): per entry the place (`address/word/bit`), the cell
(design, memory k, address a), the confidence and state in the copied schema's words, the
transition observed, and the records it rests on — the run, and the record numbers of the
code states and of the single. The copied schema is not edited and nothing is written in
its form until a stage shows what its `relation` claims (S4 or S5). This is point 4.

### What has to be built

- **The prober: a new stage, and so a new image.** Stage 8 knows two states, all zero and
  all one. I propose that the new stage knows none: **the host gives it, beside the list
  of reads, a list of accesses to the design** — for each state, what to write to which
  register, what to read from which and what the reading must be, before the frames and
  after them. The prober makes them in order, logs every one as now, and stops at the first
  reading that is not what the list says. It refuses a list with an address outside the PL
  envelope, with a register it may not write, or longer than its room. It does no
  arithmetic on states, as it does none on addresses. Both lists go to the board as files
  and are held by U-Boot's checksum before `go`, as the list of reads is now.
- **The twin**: configuration memory in which each cell of the design's model shows at a
  place the test chooses — a bijection, and switches for outcomes 2 to 7 and 10.
- **The host**: the program that makes the states and the two lists; the judge of the code
  run and the program that closes it into the table; the judge of the singles; the chain's
  driver (the code run, the commit of it and of the table, then the four); the schema and
  the program that writes the description; the run script's step for the second list.
- Tests and mutants; and the complete set before the image first goes on a board.

### What S2.3 cannot show

- Anything outside the column. A bit elsewhere that follows a pattern and did not follow
  all ones would not be read. S2.2 read everything in two uniform states; this step reads
  one column in sixteen states more and six frames in 256 more.
- Which LUT of the slice a memory is, which pin an address bit is on, whether the same
  cells are a LUT's truth table (section 10).
- That the table holds at another site (S2.5) or on another die.
- That a single cell can be read while its neighbours are being written: the prober is
  still the only writer and does not write while it reads.

### For the owner

1. **The form of the step:** one code run of eighteen states over the whole column, the
   table closed and committed, then 256 singles in four runs. *(Recommended. The other
   order — singles alone, 256 states, no code probes — gives confidence 2 without
   confidence 1 and has no check that every bit of the column was seen under patterns.)*
2. **What the singles read:** the two reads that deliver the four frames — four runs, about
   twenty minutes. The other way is the whole column in every single: eight runs of 32
   states, about an hour. *(Recommended: the two reads. What the rest of the column does
   under patterns is the code run's question, and it reads all of it eighteen times.)*
3. **The states come from the host as a list of accesses; the prober knows no state.**
   The other way is a stage that computes the patterns itself from a code in the parameter
   block, as stage 8 does for its two. *(Recommended: the list. The judge then walks the log
   against a list it made itself, the prober has less in it that can be wrong, and the same
   image can serve where only the states differ.)*
4. **The description is a document of our own** (`ram_map_v1`), and nothing is written in
   the copied schema's form in S2. *(Recommended, for the reason above. The other way is the
   copied schema with `init_index` holding the RAM's address and a note that it means only
   that — I would not: a field that says more than was shown will be read as what it says.)*
5. **Which registers the prober may write is a parameter, bounded in the image.** Today it
   is a constant of the image: the scratch register, the two address registers, the RAM's
   data — not the shift registers' data, whose write is a shift. I propose the image's bound
   be those and the shift registers' data, and the set's parameter say which of them this
   run may write; S2.3's sets do not allow the shift, the prober refuses a list that asks
   for one, and the judge fails a run whose log has one. **Then S2.4 — states that are
   sequences of shifts — would need no new image**, as S2.0 and S2.1 shared one (section
   12, point 10): one complete set of mutants instead of two. Whether S2.4 needs anything
   the list cannot say is known only when it is proposed. *(Recommended. The other way keeps
   the constant as it is; S2.4 then has an image of its own and its own complete set.)*
6. **One word for the code run and the singles together**, after the owner's review of the
   "as built" section: the code run alone and committed; the table closed and committed;
   the singles only if the code run ended in outcome 1 (with or without 5 and 7); the chain
   halts by itself and runs nothing again. *(Recommended. The other way is a report after
   the code run and a second word for the singles — reasonable too: the table is the first
   result of this project that says what a bit is.)*
7. **A lost prompt** stopped one run in 196 (section 28). The rule is left as it is: the
   run stops, the chain halts, the owner decides. *(Recommended. Five runs.)*
8. **The complete set of mutants** for the new image before the board: 1,015 now and more
   with this stage; at the rate measured, **about a day** on this host, during which
   nothing else heavy runs and the board is not used. *(No choice proposed; said so that
   the time is known. Point 5 decides whether it is paid once or twice.)*

Considered and not proposed: the states written at the U-Boot prompt by the run script
(`mw.l` to the design's registers) and the frames read by a stage of the image that is on
the board now. It needs no new image and no day of mutants. It needs a run for every
state — some 270 runs, each with some hundreds of exchanges at the prompt that are never sent
twice — and it moves the setting of the state from the program whose every access is
logged in the result to the console, which is the part of this arrangement that loses
characters. For the eighteen states of the code run alone it would do; for the singles I
do not think so. I have not examined it further than this.

If this is agreed, the next thing built is the host side — the stage, the twin, the lists,
the two judges, the closing, the chain, the schema — followed by its "as built" section
and the owner's review, the mutants, and only then, on the owner's word, the board.

## 30. Decisions on S2.3 (owner, 2026-11-22)

The owner: all eight points of section 29 as recommended.

1. One code run of eighteen states over the whole column; the table closed and committed;
   then the 256 singles in four runs.
2. The singles read the two reads that deliver the four frames.
3. The states come from the host as a list of accesses to the design; the prober knows no
   state.
4. **The description is a document of this project's own (`ram_map_v1`); nothing is written
   in the copied schema's form in S2.** I pointed out that this changes a decision of
   2026-11-13 — "zynq-fabricmap's structure description is used as it is" (the proposal,
   sections 4 and 12). The owner: accepted, knowing that. `proposal.md` has the change with
   its date, in both sections.
5. Which registers the prober may write is a parameter, bounded in the image by the four it
   may write now and the shift registers' data. S2.3's sets do not allow the shift; the
   prober refuses a list that asks for one; the judge fails a run whose log has one.
6. One word for the code run and the singles together, after the review of the "as built"
   section: the code run alone and committed, the table closed and committed, the singles
   only if the code run ended in outcome 1; the chain halts by itself and runs nothing
   again.
7. A lost prompt stops the run and halts the chain, as now.
8. The complete set of mutants for the new image before the board.

`proposal.md` was brought up to date the same day, at the owner's word: where the work
stands, the row of S2 in the stage table, the questions 4, 5, 7 and 9, the note on bit 5
among the risks — each as a dated note, the text of 2026-11-13 left as it was.

The host side is built next; its account follows as a section "as built".

## 31. S2.3 as built (2026-11-22; host side, nothing on a board yet)

For the owner's review. Sections 29 and 30 are the proposal and the decisions; this is what
was built from them, where it differs, and what it cannot show.

### What there is

| part | where |
|---|---|
| the prober's stage 9 | `prober/sm_core.c` (`run_s9`, `pl_addr`, `log9`), `prober/sm.h` |
| the twin: the list of accesses; a stop for a program that floods it | `prober/twin_hal.c` |
| the numbering, the states, the two lists of a run | `host/s2_3_states.py` |
| the judge; its two layouts | `host/s2_3_judge.py`; `host/s2_3c_judge.py`, `host/s2_3s_judge.py` |
| the table, the singles held to it, the description | `host/s2_3_table.py`; `schemas/ram_map_v1.schema.json` |
| the chain's driver | `host/s2_3_chain.py` |
| the run script: the sets `s2_3c` and `s2_3s`, both lists made at run time | `host/s1a_run.py` (`with_plan`, `acc_bytes`, `PLANS_AT_RUN_TIME`) |
| the sets | `build/prober/expected_s2_3c.json`, `expected_s2_3s.json`, written by `tests/test_prober_image.py` |
| tests | `tests/test_prober_s2_3.py` (36), `tests/test_s2_3_host.py` (113) |

**A new image**: `prober.bin`, 19,248 bytes, sha256
`ca2f6b5e3253dbecc70dbd56767b7f0463fb6d80aabca3d1ce39da35338de5e9`, crc32 `0231c989`. Every
set is written for it. The image of S2.2 (`94ad860c…6f50`) stays beside its evidence.

### The stage

Stage 9 is stage 8 with the states taken out. Its gates, its reads, the status after every
read, the clearing of bit 5 and the two reads of CTL0 are stage 8's, by the same functions.
What is new is that it makes **the host's list of accesses**, entry by entry.

Parameters (every other word must be zero; the block is refused before the device is looked
at if one is not):

| word | holds |
|---|---|
| 3, 4, 5 | the envelope and the reference frame, as in S2.2 |
| 7 | how many states (at most 80) |
| 9, 15 | the poll limit; the wait that touches no memory |
| 16 | how many reads the list of reads has (at most 178) |
| 18 | how many entries the list of accesses has, the marks counted (at most 32,768) |
| 19 | which registers of the design this run may write, one bit for each offset |
| 24 to 26, 28 to 31 | the PL envelope, the identification word, the four SLCR words |

**The list of accesses** lies at `0x10190000`, two words an entry. The first word is the
register's offset in the design with the kind of the entry in its two low bits; the second
is a value.

| kind | what the prober does |
|---|---|
| 0 | reads the register; the reading is logged (the value must be zero) |
| 1 | writes the value to the register |
| 2 | reads the register; **it must read the value**, or the run ends there |
| 3 | a mark, no access. Value 0: every read of the list of reads is made now. Value 1: the state is over |

A state is: entries, the first mark, entries, the second mark; the list is exactly as many
states as word 7 says. The prober refuses, before anything is touched, a list that is not of
that form, an offset that is no register of the design or lies outside the PL envelope, a
write to a register word 19 does not name, a word 19 beyond the image's own bound, and a
run whose result would not lie in its area.

What it does, in order: the gates; the reference frame; the design's identification (its
own access, the only one: word 26); CTL0; for each state the entries up to the mark, the
reads, the entries up to the state's end; CTL0; the reference frame.

**The result.** The log of accesses has room for the identification and every entry that is
not a mark, so the PL block — and with it the place where the records begin — is as long as
the list makes it: 64 + 16 + 2 x accesses words. The records are stage 8's.

**New stops**: `0xa0a`, a reading before the frames of a state was not what the list says;
`0xa0b`, one after them — for the readings of the RAM that is the stop of S2.2's "the RAM
did not hold".

### The states and the lists (`host/s2_3_states.py`)

The numbering and the states are section 29's. The list of accesses for a state: the RAM
written; read back at all 64 addresses, each reading held to the state; the counter read;
the mark; the RAM read back again at all 64, held again; the counter; the design's count of
writes, held to the writes made so far in the run; the shift registers' outputs at all 32
addresses, held to the words the design loads. Before the first state the shift registers
are read the same way.

| run | states | entries | accesses | reads a state | result |
|---|---|---|---|---|---|
| the code run | 18 | 7,834 | 7,799 | 12 (`0x00401200` .. `0x00401223`) | 121,278 words |
| singles, each of four | 66 | 21,898 | 21,767 | 2 (`0x0040121e` .. `0x00401223`) | 108,894 words |

Every list writes the two address registers and the RAM's data, and nothing else: word 19
is `0x00111000`.

The reads come from the census and from `evidence/s2_2_17A6_2026-11-22/candidates.json`: the
one column of block type 0 in which S2.2's frames lie, read in threes as S2.2's shares read
it; for the singles those of these reads that deliver a frame with a candidate. Candidates
in two columns, or none, give no plan.

### The judge (`host/s2_3_judge.py`)

Everything about a read is held as S2.2's judge holds it — that part is taken over from it
line for line. What is its own:

- **The log against the list.** Access by access: the same register, the same value
  written, and where the list holds a reading to a value, that reading. The first that is
  not so is where the run must have ended, with the stop that says before or after the
  frames.
- **The states are taken from the log**: what the RAM read back as, at all 64 addresses,
  before the frames of a state and after — both must be there, and alike.
- **The counter must have gone on** between the two readings of a state. The prober knows
  nothing of a counter; this is the judge's.
- **The design's count of writes** is held to the writes the log shows, and no access of the
  log may be a write to the shift registers' data.
- **Which run it is** is read from the states — the code run's, or those of one run of the
  singles — and both lists must then be the lists `s2_3_states.plan` makes for that run from
  the design, the census and S2.2's finding; word 19 must be what those lists write.
- **The finding.** Every cell has a row of values over the states. A bit of a frame whose
  readings are constant is *still*; one whose readings are the row of exactly one cell
  *follows* that cell; the opposite of a cell's row: it follows it inverted; anything else
  that changed is *irregular* and fails the run. Cells the states do not tell apart are
  listed, and no bit is said to follow one of them.

The same judge judges both kinds of run. It passes a run with any number of bits that
follow; whether that is a table is asked next.

### The table, the singles, the description (`host/s2_3_table.py`)

- `close_code`: **every cell has exactly one bit, and the bits are exactly the places S2.2
  found, each shown the way S2.2 saw it.** Then the table; otherwise none, and which of the
  outcomes it is.
- `hold_singles`: for each of a run's 64 cells, the bits that follow it must be exactly one,
  the place the table has, shown the same way. A cell for which that is not so is a
  contradiction.
- `ram_map`: the description, `schemas/ram_map_v1.schema.json` — per cell the place
  (`address/word/bit`), the memory and the RAM's address, whether inverted, the confidence
  and state in the copied schema's words, the transition observed, and the evidence: the
  states of the code run in which the cell was set, the records of the code run that hold
  the frame in those states, and the run, state and record of its single. The build's
  record of where it put each memory is copied beside the entries under a name that says
  what it is.

### The chain (`host/s2_3_chain.py`)

`run00` is the code run; `run01` to `run04` the singles. Each stored run is judged again from
its raw words and held to the image, the design and both lists, as S2.2's chain does (the
checks are that chain's own functions, and one more for the list of accesses).

- The code run is closed into the table, which is written to `DIR/table/table.json` —
  **once**. A table that is there is held to what the code run's verdict gives now and is
  never written over.
- **No single is started before `run00` and `table/` are committed as they stand.** Until
  then the chain is held, which is not a halt.
- No table: the chain halts, says which outcome, and runs no single.
- A contradiction halts the chain at that run; what the run's other singles said is in
  `chain.json`.
- Complete: five runs stored, every cell confirmed once. Then `ram_map.json` is written; it
  is taken away again if the stored runs no longer make a complete chain.

### Where what was built differs from sections 29 and 30

1. **The list has offsets, not addresses.** The image's tests hold that an address of the
   PL is formed by one instruction in one function. That function was `pl_access`; it is
   now `pl_addr`, which gives the address of a register or refuses to, and is asked by
   `pl_access` and by stage 9's check of its list. The test names both callers.
2. **The identification is still the prober's own access**, held to word 26, before the
   list's first entry. Section 29 had the prober know "no state"; it knows this one word of
   the design, as stages 7 and 8 do.
3. **The counter is the judge's.** Stage 8 stops if it stands still; stage 9 logs two
   readings and the judge fails the run.
4. **A single that contradicts the table does not fail its run; it halts the chain.**
   Section 29 said "that entry is a contradiction and the run fails". The judge is a
   function of the result and the plan and of nothing else, so that a stored run judged
   again — by the chain, by the audit — says what it said; the table is not a thing it is
   given. The run passes as a run; the chain holds it to the table and halts.
5. **A later state is written only at the addresses where it differs from the state
   before**, and is read back whole. In a run of the singles that is one or two writes a
   state.
6. **Two sets and two layouts** (`s2_3c`, `s2_3s`): the run script knows a result by the
   length of its header, and the two kinds of run have two.
7. **The image's bound on what a run may write** has the four registers of the stages
   before and the shift registers' data: `0x01111010`. Section 30 said so; the scratch
   register is among the four although no list of S2.3 writes it.
8. **Limits**: 80 states and 32,768 entries a run. The result area decides before either.
9. **The table has its own directory**, so that the question "is it committed" is the one
   already asked of a run's directory.

### What cannot be told, and is said so in the tests

- **Nothing outside the column** (section 29). The singles read six frames; a second place
  of a cell elsewhere in the column would have shown in the code run as a cell with two
  bits, and nowhere else.
- **A bit that is a function of several cells** has no cell's row: it is irregular and
  fails the run. That is a refusal to say, not a finding about it.
- **Where the cells show in the twin is made up by the tests.** That the judge finds them
  wherever they are put says the judge is right about a device that behaves so.
- **The log beyond the last access of a run that stopped** is zero in the twin whether or
  not the prober cleared it; the clearing has no test that could fail.
- **The bound on the prober's walk of the list** (below) cannot be shown to matter on a list
  the check lets through; it is there for the case that the check is wrong.

### Tests that changed their statement

- `tests/test_prober_image.py`: the PL's base is formed in `pl_addr`, asked from two
  places; three new constants are accounted for (the words stage 9 uses, the bound, and the
  bound's complement, which the compiler uses to hold word 19 to it).
- Nothing else: the tests of the stages before pass as they were.

970 tests in all (821 before this step).

### Mutants

**1,304 now, none stale** by the tool's own rule (its condition for an anchor, applied to
every mutant without running any).

- **53 older ones had lost their anchors.** 40 because stage 9 has stage 8's words: each now
  names the first of the two places, and has a twin for stage 9 at the second. 13 stood in
  lines that changed (the choice of the wait, the address of a register, the log's bound,
  the console's digit, the run script's list of stages) and are written again.
- **249 new** for what is S2.3's own: stage 9 (36), the states and lists (29), the judge
  (102, of which 63 are S2.2's judge's own mutants at the lines taken over from it), the
  table (26), the chain (42, 21 of them S2.2's chain's), the run script's sets (14).

**None of them has been run by the tool.** What has been done is a first look: each of the
289 that are new or are stage 9's, alone, in a scratch copy, against the three test files of
this step (`test_prober_image`, `test_prober_s2_3`, `test_s2_3_host`) and not the whole
suite. That is not the tool's verdict — the tool runs everything and holds the number of
tests that ran — and it says nothing of the 13 written again, which older tests must kill.

- First pass: 231 killed, 62 not. Three of the 62 did not build (an unused parameter, an
  unused function, an unbalanced bracket) and are written again. 55 showed tests that were
  missing — most of them for what the judge has from S2.2's, which my first tests had not
  taken over, and for the block's checks stage 9 has from stage 8. About thirty tests were
  added for them.
- **One of the 55 was a fault of the judge**, not of the tests: without the design's words
  for its shift registers the judge did not say so, it raised an exception. Mended.
- **Four are taken out**, because nothing can kill them, and the lines they stood in stay:
  the chain's check that a passing result is of the run planned in its place (the judge
  cannot pass a run against another run's lists); the chain's check that every cell is
  confirmed when five runs are stored (a run with a contradiction has halted it before);
  which of two equal readings of the RAM is called the state; and the line of the run
  script that keeps the list of accesses beside a run, which only a run on the board
  reaches — as the same line for the list of reads has none.
- Second pass: **289 of 289 killed**, none that did not build.

One of the mutants is the one that took the machine's memory (below); it now ends.

### My slips

- **A mutant of mine took the machine's memory.** It let a list through that ends inside a
  state; the prober walked on past the end of the list, the twin printed a violation for
  every word without end, and the test kept all of it. The host stopped the job. Mended at
  both ends, as section 27's was not: the prober's walk of the list is bounded by the
  list's length whatever the check before it said, and the twin ends with a code after a
  thousand accesses nobody may make. A loop that ends only because an earlier check holds
  is the thing to look for when a stage is written.
- **Stage 9 did not at first take stage 8's three branches** — the choice of the wait, the
  clearing of the done bits alone, CTL0 as the register of its one other read. I found it
  by reading for "stage 8" before the first test ran; a result would have shown it at the
  first run, and a mutant now holds each.
- **I ran the suite in a shell that still had the twin's variables set** from a diagnosis
  (`SM_LIST` and the like, pointing at files already removed): 955 errors that were none.
  The older tests do not clear those variables before they start the twin. I have not
  changed that; it is noted here.
- A commit message gave the image's size before its last rebuild; set right in the same
  commit. Several of my own expectations in new tests were wrong and were set right by the
  twin, not the other way round — each is a place where I had the device's behaviour in
  mind and not the prober's.

### For the board, when the owner has reviewed this

- The mutants of this work by the tool, then **the complete set** for the new image, as the
  rule has it: 1,304 now.
- Then, on the owner's word, the chain: a pre-check; `s2a.bit` is on the card; the code run
  alone (`--max-new 1`); its directory and the table committed; the four runs of the
  singles; whatever it ends in committed as it stands before anything is made of it.
- The set's file is copied beside the runs before the first run, not after the last (section
  28).

## 32. Review of `5936a8e` (2026-11-23): five findings, all reproduced, all mended; a new image

The owner passed on a review of the host side of S2.3 as section 31 describes it. It
confirms S2.2's evidence from the raw words and the two builds, and finds five things: one
high, three medium, one low. **Each was reproduced here before anything was changed**, in
scratch directories and on the twin; no board was touched. All five are accepted. Finding 3
is in the prober: **the image of section 31 is superseded** (below).

### 1. (high) A single could be started with no table stored

The chain asks git whether `run00` and `table/` are committed as they stand; it did not ask
whether the table is in `table/`. Reproduced in a scratch repository: the code run made and
closed, `table/table.json` taken away and a placeholder put beside it, both directories
committed — the driver saw a directory by that name (so it wrote no table: written once,
never over), git had nothing against either directory, and `run01` was made. Only then did
the chain halt ("singles are stored and no table is"). On a board that is a run of the
singles made against a table nobody had committed.

- **The chain halts when it is looked at** if something has the name `table` and the table
  is not in it as a plain file: before git is asked and before anything is sent. A
  `table.json` that is a link or a directory is not the table; a link that leads nowhere
  in `table`'s place is something with that name.
- What was already so stays so: a table that is stored is held to what the code run's
  verdict gives now, and git is asked about `table/` as a whole. Together: before a single,
  the table is there, is the one the code run gives, and is committed.

### 2. (medium) A clean copy failed one test, by the order of the tests

`test_the_chain_over_the_three_states_of_the_ram` — mine, of this session — has the chain of
S2.2 assessed, and the chain holds the staged design to the set; in a copy fresh from git
nothing has staged `build/pl/s2a.bit` when that test comes. Reproduced in a fresh clone
(`halted`, 0 runs). The test now stages the designs itself, as the test of the description
beside it already did. This is section 24's rule ("a clean copy runs every test"), broken by
a test I added after it and ran only in a tree that had been built.

### 3. (medium) A refused stage-9 block was answered with words the run did not write

Stage 9's result has a log whose length the parameter block gives. The prober cleared the
header and the fixed part of the PL block, checked the block, and cleared the log only if
the block was taken; a refused block was still answered with a result of the full length.
Reproduced with a twin whose memory is not zero when the prober starts: a block refused for
its version alone gave status `0x500`, no record, and **3,482 words of what had lain there**
— the reviewer's number. On a board that memory holds the log of the run before, which
would read as this run's.

- **The log is cleared with the header, before the block is looked at** (`run_s9`): one
  loop over header, PL block and log. Its length is bounded whatever the block holds
  (`log9` gives nothing for a count it would not take), so the clearing stays in the
  result's area.
- **The twin can start with memory that holds something** (`SM_DIRTY=1`): every word a
  pattern of its own, and a result of which a word still holds it is not written out — the
  twin says STALE and ends with a code. **Every test of stage 9 on the twin now runs so**,
  and results on such memory are held word for word to those on empty memory, for refused
  blocks, a complete run and runs that stop. (One word of a record differs between any two
  processes of the twin, memory or no: where a variable lay on the host's stack. It is
  left out of the comparison and said so.)
- **The other stages were asked the same** and have nothing of the kind: their twin tests
  pass unchanged on such memory, and are now run once more that way in every suite
  (`tests/test_prober_dirty.py`). Stage 9 is the first whose header length depends on the
  block.

### 4. (medium) Runs under different CTL0 values still ended in a description

Each run's judge holds CTL0 to itself, before and after. S2.2's chain held the runs to each
other when it closed; S2.3's listed the values it saw and asked nothing. Reproduced: one
run of the singles with CTL0 reading `0x00000401` on the twin, the others `0x00000501`:
the chain was complete and `ram_map.json` written. That is a table decoded under one
setting of the readback mask and confirmed under another, by the register's word. I dropped
the check when I wrote this chain from S2.2's; it was in the file I started from.

- **A run of the singles in which CTL0 read otherwise than in the code run halts the chain
  at that run**, not at the end: nothing more is run on a board whose register changed.
- Not done, and said: the chain does not hold its CTL0 to the value S2.2's runs read
  (`0x00000501`). `candidates.json` does not carry it. What it would guard is caught another
  way — the table must be exactly S2.2's 256 places — but not by name. *(Done since: section
  34. And "caught another way" was too much said — see there.)*

### 5. (low) A console that fails ended the driver in an exception

When the serial adapter cannot be opened, the board's runner raised pyserial's exception
through the driver; `chain.json`, written before, said "go on" and nothing of why.
Reproduced for both chains with the port replaced (the real one was not opened). It is the
same fault as section 26's third, at the one place that mending did not reach.

- The runner of both chains takes what the line can raise — the run script's own list of
  it (`TRANSPORT`) — while it opens the console, resets and asks for the status; closes
  what it opened; and says "the console failed … the run script was not started". The
  driver holds the chain with that reason in `chain.json`, blocked, as for a board that
  did not come up fresh.

### What changed, in numbers

- **The image**: 19,244 bytes, sha256 `8bf3799cd5a29b92d9196dfd432e8e4db13e977000bc67503c69cba819e62a8b`,
  crc32 `261627c7`. Section 31's (`ca2f6b5e…`, 19,248 bytes) was never on a board and is
  not to be.
- **Tests**: 980, all passing in a clean environment; ten more than before (four of the chain of S2.3, one
  of S2.2's, two of stage 9 on memory that holds something, three in the new file).
- **Mutants**: 1,313, none stale. Three of the chain's were anchored on lines this changed
  and are anchored again; nine are new, one or two for each mending. **A first look, not
  the tool's verdict** (scratch copies, the test files of stages 8 and 9 and of the two
  chains): twelve of twelve killed. A thirteenth I wrote and took out again: "CTL0 is held
  to the run before, not to the code run". No test can tell the two apart — the chain
  halts at the first run that differs, so the run before always read what the code run
  read.

### What the review confirmed, and what is still open

It recomputed S2.2 from the raw words (196 stored runs, 194 with a result, every CRC and
verdict as recorded), rebuilt the prober to the recorded hash and the design to the same
placement, and found every mutant's anchor. I have not repeated that here.

Still open, as before this review: the mutants of this work by the tool, then the complete
set for the image — now this section's image — and then the board, each on the owner's
word.

### My part in these

Three of the five are things I dropped or left behind while building on S2.2's files: the
CTL0 check between runs (4), the test that needs a built tree (2), the console's exception
at the one place I had not mended (5). The first and third are of another kind — a gate
that asked about a directory where it meant a file, and a result's length taken from a
block before the block was taken. A length that comes from the input is the thing to look
for in the next stage that has one.

## 33. Review of `ce77a49` (2026-11-23): three small findings, mended; and a lock between the mutants and the board

The same reviewer looked at section 32's mending: a copy fresh from git, with no `build/`,
passes all 980 tests, and each of the five holds. It found three things more, all low.
**Each was reproduced here first.** All three are accepted. **Nothing under `prober/sm_*`
changed: the image is section 32's** (19,244 bytes, `8bf3799c…2a8b`).

### 1. (low) A complete chain was still complete with `table/` a link

The directory moved away and a link to it put in its place: the table is read through the
link, and git — which refuses such a link — is asked only before a single. Reproduced: the
chain complete, `ram_map.json` written again. Now **what has the name `table` must be a
directory of the chain's own**, asked whenever the chain is looked at; a link (also one to
a directory, also one that leads nowhere) or a file halts it, complete or not.

### 2. (low) The twin called a written word stale when it held what had lain there

Section 32's check told an unwritten word by its content. A frame word that equals the
filling of its own place — reproduced with one — made the twin end with STALE for a run
that was complete. **The twin now keeps which words were written** (by the prober, or by
the engine delivering a transfer) and counts the words of the result that were not; the
filling is only what an unwritten word would show. A fault of the model, not of the
prober: but a check that can be wrong one way is not believed the other way either.

### 3. (low) A close that failed took the place of what had failed before

In the runner of both chains: the read failed, closing the port failed too, the reason
written was the close's, and the log was not closed. The reset before a run is now **one
function for both chains** (`came_up_fresh`, in `host/s2_2_chain.py`): the port and the log
are each closed whatever the other says, and the first thing that failed is the one that
is told. A close that fails alone is told as well, and no run is started.

### 4. (mine) A mutant could lead a test to the board

Found while listing the mutants for this section, not by the review. The chains' tests of
the command (`--go` with an image that is not the set's) are kept from the board's runner
by one check, `ready`. A mutant that takes that check away — there is one in the list
since section 26, "a run is started though the build's image is not the set's" — lets
that test go on to the real runner: it opens the board's console, sends a `reset`, and if
the board answers as usual, starts the run script with `--go` from the scratch copy. With
the adapter attached, **a run of the mutant tool could have made a run on the board that
nobody asked for.** The two mutants I had just written for this section ("the runner
starts a run without the reset") would have done the same by a shorter way.

- **The lock**: where `SELFMAP_NO_BOARD` is set, `host/uboot_console.py` opens no console
  — and every session with the board begins there, which a test now holds. The mutant
  tool sets it for every suite it runs, and what a suite starts inherits it.
- **What I can say of the runs already made.** Section 27's record has that mutant killed
  with the command's test ending in *an error* — an exception, which is what a port that
  is not there gives; a console that answered would have ended in a failed comparison
  instead. Section 24 notes the adapter had not been attached since 2026-11-20, and the
  set was run before the board was attached for S2.2. That is consistent with no board
  having been reached; the record cannot prove it. The first looks of 2026-11-22 and 23
  ran no mutant of that kind (the chain of S2.3 has no copy of it; today's ran with the
  console replaced in the tests concerned).
- The owner's rule stands beside the lock and is not replaced by it: no mutants while the
  board is in use.

### In numbers

- **Tests**: 987, all passing in a clean environment, and with the lock set.
- **Mutants**: 1,326, none stale. Three of section 32's were on lines that are now one
  function; they are written again for it, with thirteen more — the three ways the line
  can fail, what is told, what is closed, the fresh prompt's two signs, the table's
  directory.
- **By the tool, for the record** (the owner, 2026-11-23: after this mending): the mutants
  of S2.3 and those written or written again since the last complete set — 324 of the
  1,326. What it found is below.

### The tool's run on the mutants of S2.3 (2026-11-23)

The 324: the 299 of S2.3 (`s9`, `states9`, `judge9`, `table9`, `chain9`, `run s2.3`), the
13 older ones written again for stage 9, the 12 of `chain8` for the reset before a run.
Eight at a time, with the lock set, 07:02Z to 12:43Z on `d7b62d2`
(`evidence/host_checks/mutants_2026-11-23_s2_3.txt`): **315 killed, none survived, none
stale, 9 BROKEN.** The nine again, 12:48Z to 13:10Z on `6939cad`
(`evidence/host_checks/mutants_2026-11-23_s2_3_again.txt`): **all nine killed**, each
with the baseline's 989 tests run. So of the 324 none survives.

The nine were two faults of mine, neither in the prober nor in a host program:

- **Eight: the tool read the wrong count.** `tests/test_prober_dirty.py` (section 32)
  runs the twin tests of the other stages in a process of their own and, when they fail,
  shows what they printed — a line `Ran 38 tests` among it. The tool took the *first*
  `Ran N` of a suite's output for the suite's count, saw 38 (or 57, or 22) where the
  baseline has 987, and said BROKEN of mutants whose suites had run whole and failed.
  The tool now takes the last such line, which is the suite's own, and the test shows
  what it quotes indented; both are held by tests (`2b34a0b`). The tool's rule was right
  to refuse: a count it cannot trust is no kill.
- **One: a class left the count.** `s9: stage 9 is run as stage 8` — 978 tests, not 987.
  `StageNine` made its run of the twin in `setUpClass`; since section 32 that run is on
  memory that holds something, under this mutant the twin ends with code 4 — the check
  section 32 gave it, a result that holds a word nobody wrote — and the class's nine
  tests were not run at all (reproduced on `d7b62d2`: `setUpClass` raises on the twin's
  exit status 4). So section 32 brought it in; the first looks ran only the test files
  concerned and do not hold the count, and could not see it. Section 27 had already
  recorded the same fault in another class (`WithAShare`). The run is now made inside
  the first test that asks for it (`once()`): if it cannot be made, every test that
  needs it fails and none leaves the count (`6939cad`).

What this run does and does not say:

- The 315 were killed on `d7b62d2` with 987 tests; they were not run again on `6939cad`.
  The two commits between change the tool's reading, the indenting of quoted output, one
  test class's fixture, and add two tests of the tool — no prober source, no host
  program, and no assertion is taken away.
- It is the run for the record of S2.3's own mutants. It is **not** the complete set:
  the other 1,002 mutants have not been run against the image of section 32
  (`8bf3799c…`), and by the owner's rule of 2026-11-17 that set is due before the image
  first goes on a board.
- Other test files still make things in `setUpClass` and are left as they are. No other
  class makes a run of the twin on memory that holds something there: the stage-9 runs
  are made by `Run` of `tests/test_prober_s2_3.py`, used in that file and in
  `tests/test_s2_3_host.py`, neither of which has a `setUpClass` now, and
  `tests/test_prober_dirty.py` makes its runs inside its tests. Whether a class loses
  its tests under some mutant outside these 324 is for the complete set to show, as it
  did on 2026-11-22 (section 27).

Tests now: 989. Mutants: 1,326, none stale. Image unchanged.

## 34. The code run is held to the CTL0 of S2.2's runs (owner, 2026-11-23)

Section 32 left this open and said so; the owner took it up and decided it, before anything
of S2.3 has been on a board — a condition for halting counts only if it is set down before
the run it would halt.

### What was open

S2.3 is built on S2.2's 256 candidates, and those were found with CTL0 reading `0x00000501`
at all 16 readings (section 28). S2.3's chain held each run's two readings to each other
(the judge) and the singles to the code run (section 32). Nothing held the code run to
S2.2. Two cases:

| | as it was | now |
|---|---|---|
| CTL0 is another value and readback of the RAM is not what it was | no table of S2.2's 256 places comes out: the chain halts at the code run, and says "table" | halts at the code run, and says CTL0 |
| CTL0 is another value and the frames read as before | **the chain completes and writes `ram_map.json`** | halts at the code run |

Section 32 said the thing "is caught another way". That is true of the first row only. The
second is a description made of candidates found under one value of the register and a
table decoded under another, with nothing to show it but a field of `chain.json`. I do not
think it likely — the same board, the same card, the same design, whose file is held to its
hash — but on the same board with the same design a CTL0 that reads otherwise says that
something before the prober was not as it was, and that is worth a stop.

### The three points, as decided

1. **The whole word is compared**, not bit 8. No program is told what a bit of CTL0 means:
   the word the device gave on 2026-11-22 against the word it gives now.
2. **The value is read from S2.2's own chain file**
   (`evidence/s2_2_17A6_2026-11-22/chain.json`, its closing's `ctl0`), which lies beside
   `candidates.json` — no constant in a program, and `candidates.json`, the evidence of a
   closed step, is not touched. It is taken only from a complete chain whose closing has
   exactly one value that is a word as the judge writes it (`0x` and eight digits);
   anything else gives none, and then nothing of S2.3 can be planned or run.
3. **Another value halts the chain at the code run.** That run is made (it reads; it writes
   nothing but through the design's registers), its judge has nothing against it, and the
   chain halts on it by the register's name *before the run is closed*: no table is taken
   from it, none is written, no single is started. A halt is the owner's to decide, as
   every halt is. Section 7's "CTL0 differs — a finding, not a failure" was said of another
   case: there the design had been changed and the question was open. Here the design is
   the same and a step rests on the other.

### As built

- `host/s2_3_states.py`: `CHAIN_OF_S2_2` and `ctl0_in_s2_2(chain)`.
- `host/s1a_run.py`: both sets of S2.3 name that file (`chain_before`), and `known_for`
  gives what it says as `known["ctl0_in_s2_2"]` — where it already gives the candidates.
  The run script itself does nothing with it: a run is judged as a run.
- `host/s2_3_chain.py`: in `assess`, for run00, before `close_code`. A chain that is told
  of no value halts there too. The closing of a complete chain says both — what its runs
  read and what S2.2's read.
- What is left for a look by hand at such a halt: the run is stored whole, and
  `host/s2_3_table.py <verdict.json> <candidates.json>` closes it and prints the closing,
  so whether the 256 places would have come out can be seen without the chain going on.

One clause is held by no mutant and I say which: `not known.get("ctl0_in_s2_2") or …`
guards the case that the chain is told of no value *and* a passing run has none either. No
passing run lacks the value, so I can make no test in which the clause alone decides; a
chain told of no value halts by the comparison (tested: no key, and an empty one).

Not done, and said: `ram_map.json` itself does not say under which CTL0 it was found;
`chain.json` beside it does. That would be a change to the description's form, and was
not part of this decision.

### In numbers

- **Tests**: 992, all passing in a clean environment. New: the chain with a board that
  reads `0x00000401` in every run (one run made, a passing run, halted, no table, nothing
  run again); the code run alone is what is held to S2.2; what is taken from S2.2's file
  and what is refused. One part of section 32's test changed with the rule: a code run
  under another value now halts at run00, where it used to halt at run01.
- **Mutants**: 1,336, none stale — ten new (three of the chain, five of the reading of
  S2.2's file, two of the run script's sets). A first look, against the test file of
  S2.3's host side: ten of ten killed. The tool has not run them; the complete set, which
  is next, has them. *(The complete set was begun and stopped: section 35. The ten have
  had the first look only.)*
- **Image**: unchanged (`8bf3799c…`, section 32). Nothing under `prober/` was touched.

## 35. When the complete set of mutants is run (owner, 2026-11-23)

The rule of 2026-11-17 was: after a change the mutants of what changed; the complete set on
a substantive change of the prober or a judge, and before a new image first goes on a
board. The owner asked what a complete run proves, whether it is needed, and how many more
there would be. What I answered, and what was decided.

### What the record says

- A mutant that survives has nearly always been one of **new code, in the first run of the
  new mutants**: three of the 98 of S2.0 (section 13), two of the first part of S2.2
  (section 21), one of the chain of S2.2 (section 27, whose mutants had not all been run
  till then); the same in S1b. Those runs are the short ones.
- **The complete set run again over mutants already killed** has ended "all killed, none
  survived" time after time (315, 320, 354, 390, 433, 478, 481, 523, 711; 1,015 with the
  one just named).
- What a complete run has found besides is faults of the tests' own build — a class that
  leaves the count, a count misread. Today's two (section 33) showed in the run of the
  324 that belong to S2.3.
- Faults of the programs themselves were found, these two days, by review: eight in two
  rounds (sections 32 and 33). No mutant finds a check that was never written.
- The list grows — 609 on 11-19, 1,015 on 11-22, 1,336 now — and a complete run is about a
  day of this machine, during which the board is not used. By the old rule I counted six
  to nine more of them to the end of the project.

### The rule now

1. **After every change**: the whole suite; the mutants of what changed; and review, as
   before. Nothing of this is new.
2. **Stages that only read (S2, S3)**: with point 1 an image may go on the board. No
   complete set for each new image.
3. **Before a stage is graded** (the end of S2; before S6): the complete set once. Grading
   is done once and opens the book: a judge found too loose after it cannot be mended
   closed-book. Before it, it can — the results are stored as the board gave them and a
   mended judge judges them again, mostly without the board. And grading asks only for
   the table: what else S2 says of the device (that readback leaves the RAM as it was,
   what the status bits do) rests on the judges alone.
4. **Before the first write to configuration memory (S4)**: the complete set, or at the
   least every mutant of the prober and of what guards a write. What a wrong write does,
   it does before anything is graded.

The owner's first thought was "on the board when the logic is right, grade at the end of
S2, and come back to the tests if something is wrong". Points 3 and 4 are where I asked
for more than that, and why; the owner took the rule as written here.

### What follows for S2.3

- The complete set begun today at 13:35Z on `e7b21e4` was **stopped at 13:57Z on the
  owner's word**: 16 judged, 16 killed
  (`evidence/host_checks/mutants_2026-11-23_complete_stopped.txt`). It says nothing of
  the set and is kept as what was run.
- For the image of section 32 there is, then: the suite (992 tests); the tool's run on
  the 324 mutants of S2.3, none surviving (section 33); a first look at the ten of
  section 34, all killed; two rounds of review. **Not** run against this image by the
  tool: the other 1,002, and the ten of section 34. They are due with point 3.
- The board is still the owner's word, step by step.

## 36. S2.3 on the board (2026-11-23): complete — which bit is which cell, 256 of 256 confirmed

The account in full, with the runs and their numbers, is
`evidence/s2_3_17A6_2026-11-23/RESULT.md`. Here: what was done, what it says against what
section 29 named beforehand, and what was learnt on the way.

### What was done

On the owner's word, in two steps. The precheck and the code run alone (14:06–14:11 UTC);
the run stored and committed as it stood (`528f339`); then, on the word "run after run, and
call when something is wrong or it is done", the four runs of the singles (14:17–14:33 UTC),
stored and committed as they stood (`ace68a0`). Five runs, five passes, no halt, nothing set
aside, no piece of a result pulled twice. The image of section 32 on a board for the first
time, under the rule of section 35.

### What it says

- **Outcome 1 of the code run**: every cell of the RAM has exactly one bit; the 256 bits are
  the places S2.2 found; none inverted; every other bit of the column — 116,096 — still
  through eighteen states.
- **Outcome 9 with the singles**: each of the 256 cells set alone changes exactly the place
  the table has for it and no other bit read. 256 confirmed, no contradiction.
- **CTL0 `0x00000501`** in all five runs: the value of S2.2's runs, to which section 34 holds
  the code run. That check was passed on its first day.
- The RAM read back through the design as written before and after every pass (18 in the
  code run, 66 in each run of the singles); the shift registers held what was loaded and
  were not shifted.
- **The table as a rule.** A memory is a half word (16 bits) of word 61 or 62 in each of the
  four frames `0x00401220`–`0x00401223`. For every memory alike: address bit 0 moves the
  place one frame up, bit 3 two frames down, bits 1, 2, 4 and 5 move it 1, 2, 4 and 8 bits
  down the word. The 256 entries follow from four first places and these six moves, and a
  test holds them to that. Which pin of a LUT an address bit is, the device did not show.

This answers question 7 of section 1 for the LUT RAM, at one site. The description is
`ram_map.json`, in this project's own form (section 30, point 4), labelled closed-book.

### Not asked for: where bit 5 shows

With one cell set, bit 5 of the status showed after the read that delivers the frame in
which that cell's bit lies and not after the other read: 256 states, 512 reads, no
exception. Not in the base states; not anywhere in the code run, where a frame has none, 32
or 64 cells set. Cleared each time, and it did not come back. A test holds this
(`tests/test_status_seen.py`). The result note has a guess at what it is, marked as general
knowledge and used by no program. What S2.2 saw of bit 5 at two other reads (section 28) is
not explained by it.

It may be worth a proposal of its own before S2.4: if the bit says "this frame is one bit
away from what was loaded", it is a second witness that costs nothing. I have not looked
into it further.

### Learnt on the way: two tests of the stored evidence did not know S2.3

Neither is a fault of the runs; both showed when the runs were stored, and are in the
commits that stored them:

- `tests/test_evidence_audit.py` judges every stored run again. It did not make the plan of
  a run of S2.3 (both lists are made at run time), judged the code run without it and
  called it invalid. It now makes the plan as the run script does; judged again from their
  raw words, the five runs are what their stored verdicts say.
- `tests/test_status_seen.py` pins which stored runs show a status bit outside the usual
  word. The four runs of the singles do; the list has them now, and a test of its own says
  what they show.

The first of these I should have met before the board: a run of the twin stored under
`evidence/` in a scratch copy would have shown it. Noted for S2.4.

### In numbers

- **Tests**: 994, all passing (two new: the stored chain of S2.3 assessed again from its raw
  words, with the table as a rule; where bit 5 showed).
- **Mutants**: 1,336, none stale; none new. Nothing under `prober/` or `host/` was changed.
- **Stored runs**: 201, of which 195 have a result of their own; 155 pass.

### What is next, and whose word it needs

- S2.4 (the shift registers) and S2.5 (other sites) are not proposed in full. By section 30,
  point 5, S2.4 may need no new image.
- Before S2 is graded: the complete set of mutants, once (section 35).
- Nothing was written to configuration memory, and `SEU_EN` was not set.

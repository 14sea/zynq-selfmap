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

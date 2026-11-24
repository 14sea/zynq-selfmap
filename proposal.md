# zynq-selfmap — proposal (draft v0.3, 2026-11-13)

v0.3 folds in the owner's decisions of 2026-11-13 (section 12). The proposal itself has not
changed since; what has been done under it is noted where it belongs — the stage table of
section 7, the open questions of section 11 — and those notes are dated.

**Where the work stands (2026-11-24).** S0, S1a and S1b are done: the owner closed S1b on
2026-11-20, after its review as a whole (`docs/s1b_review.md`). S1b, the read-only census, has
block types 0 and 1 complete and graded: 3,864 and 1,280 frame addresses, 5,144 in all,
nothing differs from prjxray-db. Block type 2 is complete too: 112 frame addresses, two rows of 56 columns of one frame, every
frame all zero; not graded, there being nothing to grade against. After it the device names
`0x01800000` (block type 3): one unfinished pass there read ten addresses, all zero, and left the
register at `0x02000000`, which was not read. **All six steps of S2 are done on the
board, and S2 is not graded yet** — control register 0 read (bit 8 set: LUT RAM is not masked in
readback); the path from the prober to a design of our own; the search of block type 0
for the design's LUT RAM (256 bits follow the RAM, as many as it has cells, in four frames
next to each other, and reading does not disturb it); which bit is which cell (every cell
has one bit, each confirmed by a run of its own); and the shift registers at another site
(256 bits follow their 128 outputs, each output shown once as it is and once inverted, in
the frames and words a prediction had named beforehand, every output confirmed); and
**the sixth, S2.5 (2026-11-24) — LUT RAM at 110 sites: each of the 440 memories found
once, every one of the 28,160 cells with one bit and confirmed, and 432 of the 440 where
a prediction had said. The two sites it missed lie six columns of frames lower: of the
five parts of the rule by which a memory's place depends on its site, four hold at every
site measured and the column does not.** Nothing
of S2 is graded: that is done once, at its end, after the complete set of mutants has
been run once; neither is begun. S3 to S6 have not been begun, and nothing
has written configuration memory. The frame census is written as one document (`census/`). What S1b leaves open and what it leaves unexplained is listed in its review (sections 6 and 10). The steps of S1b, with their evidence, are listed at the head of `docs/s1b_plan.md`.
The plan for S2 is `docs/s2_plan.md`, agreed by the owner on 2026-11-20 (its section 12);
where it stands is said at its head.

## 1. In one sentence

Let a Zynq-7010 find out, **without consulting any bit database**, which bits of its own PL
configuration memory are what, write the result down as a structure description that carries
its evidence, and only afterwards grade that description against existing data.

The prober is a program running on the PS. It reads the PL configuration through PCAP and
drives a small probe circuit in the PL.

## 2. Scope

In scope:

- A census of the configuration frames that actually exist on the device (the device is the
  authority, not any list).
- Locating the memory-like bits: LUT RAM, shift registers, flip-flop state. Block RAM last.
- Locating the content bits of ordinary LUTs, then LUT-level read-modify-write with
  read-after-write verification.
- Connectivity as seen through LUT pins (which LUT output reaches which pin of which LUT).

Out of scope:

- The meaning of routing switches, I/O, clocking and configuration-centre bits. They can only
  be found by writing unknown bits blind, which risks multiple drivers, and an arbitrary wire
  cannot be observed from inside the device.
- Interpreting bitstream files. The initial design is built by Vivado and loaded; after that
  it is opaque.
- Any other device. This project is limited to the XC7Z010. A no-PS device such as the
  XC7K70T would be a separate project with its own access path; nothing here is designed
  for it.
- Any claim of being first (section 9).

## 3. The closed-book rule

During probing the prober and its author **may use**:

- Official documents: UG470 (frame format, FAR, commands, readback), UG585 (PCAP).
- The source and constraints of our own probe design (what we placed, and on which site).

During probing they **may not use**:

- prjxray-db or any third-party bit database.
- Vivado's logic location file (`.ll`), essential-bits files, mask files.
- Differencing of bitstream files.

Used **afterwards, for grading only**: what prjxray-db (zynq7) already contains. Grading results
are recorded separately and never edited back into the probed description. No bitstream is
parsed on the host and no Vivado report file is used, not even for grading (owner, 2026-11-13):
the method is meant to carry over to parts where neither is practical, so nothing may lean on
them. Where no open database exists, a result stands on the device's own evidence alone.

Every result is labelled as one of:

- closed-book: rests on observations made on the device only;
- half-open: also uses "what value our own design put there".

## 4. The structure description

zynq-fabricmap's structure description is used as it is. `schemas/self_map_v2.schema.json` is
a byte-for-byte copy (provenance in `schemas/IMPORT.json`); it is not edited here.

- Coordinates: `FAR/word/bit`.
- Per entry: the address, its relation (which LUT, which INIT position), a confidence
  (0 contradiction, 1 decoded from the code probes only, 2 confirmed by a single probe), a
  state (unknown / decoded / confirmed / no effect / contradiction), the transition actually
  observed, and the record numbers it rests on.
- Interaction edges between entries, and the binding of a map to the run that produced it.

That schema describes LUT content, which is what S2, S4 and S5 produce. The mirror image of
fabricmap's B1 applies: B1 set configuration bits and observed function; here user logic sets
the content and configuration readback is observed, with the same code probes followed by
single confirmations.

Two things it has no place for are recorded beside it, in documents modelled on it and added
only when their stage is reached: the frame census of S1 (which addresses exist, block type,
whether readback is stable) and flip-flop state (S3). The copied schema is never extended in
place.

*2026-11-19:* the frame census is written: `census/frame_census_17A6.json`, following
`schemas/frame_census_v1.schema.json`, made by `host/s1_census.py` from the stored runs
(`census/README.md`; `docs/s1b_plan.md`, section 68).

*2026-11-22:* the owner changed the first sentence of this section for S2. What S2 finds is
written in a document of this project's own, modelled on the copied schema as the census's
was (`schemas/ram_map_v1.schema.json`, to be written in S2.3), and **nothing is written in
the copied schema's form in S2**. The reason (`docs/s2_plan.md`, sections 29 and 30): the
only relation the copied schema has is `lut_init` with an `init_index`, which would say that
the address user logic gives a LUT RAM is the index of a LUT's truth table — and S2 does not
show that; its `binding` and `genome_bit` have no counterpart here either. A field that says
more than was shown would be read as what it says. The copied schema stays as it is, for the
stage that shows what its relation claims (S4 or S5).

## 5. The prober

- **Where it runs.** A bare-metal program on the PS of an EBAZ4203. The board boots from a TF
  card into the U-Boot already used on these boards; U-Boot loads the probe bitstream
  (`fpga loadb`) and the prober from the card and starts it.
- **What it starts from.** The PCAP readback sequence that zynq-psmap derived from UG585 and
  verified on this die (two unidirectional DMA commands), moved from "the host issues it
  word by word through U-Boot" to "the PS program issues it".
- **Who decides.** The prober chooses what to read and in which order. The host prepares the
  card, starts the run and collects the results.
- **No bitstream is interpreted or generated.** The one bitstream involved is the probe design,
  built by Vivado and loaded as an opaque file; its hash is recorded only to say which design
  was loaded. What the prober sends to PCAP are short configuration command packets it builds
  itself from UG470 (synchronisation, a frame address, a read command), and from S4 on frames
  it has just read from the device and changed.
- **Where results go.** Raw readback is kept in DDR and saved whole to the card; the UART
  carries progress and a digest of every saved block. Nothing is summarised before it is
  saved.
- **Separation.** The probing logic does not call PCAP directly; frame access sits behind a
  small interface so that the same logic runs on the host against recorded or simulated
  frames. This is for testing, not a commitment to other devices.

## 6. Discipline

Lighter than zynq-fabricmap's ruling-per-session regime. Four fixed points:

1. **The program is checked for safety before it runs — by rule, not by enumeration.** A
   census of unknown frames cannot be dry-run as a fixed list: where the prober goes next
   depends on what the device answers. So the check is on the *form* of what the prober can
   send and on an *envelope* it must stay inside:
   - every device access goes through a few helpers; the same source compiled for the host
     logs each access, and a test holds the log to an allow-list written in the test, not
     derived from the source;
   - configuration command packets are produced by one generator whose only free parameters
     are the frame address and the length; a real packet parser (not a word-by-word pattern
     match) checks that for any parameter value a read-only stage can only produce
     read commands — no WCFG, no FDRI, no GRESTORE, no IPROG, no register outside the list;
   - the host gives each run an address envelope and budgets (frames, time, anomalies); the
     prober chooses freely inside it and refuses to step outside. The envelope is a safety
     limit and may be drawn with any knowledge; it restricts where the prober may go, not
     what it may conclude, so it does not break the closed-book rule;
   - the same rules are enforced again inside the prober at run time, and after the run the
     host replays the logged packets through the parser;
   - the board image is inspected for what a host run cannot show (the register U-Boot
     reserves, privileged instructions, sections that would need startup code), and its
     sha256 goes into the run record. An image whose hash was not checked is not run.
2. **The closed-book rule** of section 3, including a check that the prober's build inputs
   contain none of the forbidden sources.
3. **All raw readback is archived**, unmodified, with digests, before any interpretation.
4. **Grading happens afterwards** and is kept apart from the probed description.

A stage that writes configuration memory (S4 onwards) additionally needs the owner's go-ahead
once, when that stage is first reached.

**Small first, then wider.** Every stage starts on a small range where the answer is already
known from our own earlier board work (the frames zynq-psmap read on this die), to confirm the
method. The envelope is then widened in steps — one column, one row, one block type, the
device — and each step is reviewed before the next.

**Anomalies (proposed; the owner raised both halves).** An anomaly is recorded with everything
needed to analyse it (the packet sent, the raw reply, the status registers) and then one of
two things happens:

- *record and skip* when the configuration interface is still healthy — checked by re-reading
  a fixed reference frame and comparing it with its first reading, and by the status
  registers. The run continues and the host analyses all recorded anomalies at the end;
- *stop and report* when that health check fails, when a transfer does not complete, when
  PCFG_DONE drops, or when the anomaly budget of the run is used up. Data taken after a failed
  health check would not be trustworthy, and continuing could hide the cause.

*2026-11-19 (review of S1b):* this is what the first stages do (S1a, S1b.0, S1b.0b): an
anomaly is recorded and the run goes on, within a budget. **The walk, from S1b.1 on, is
narrower**: it takes no anomaly budget and stops at the first anomaly — after one read of the
reference frame if the interface has not failed, at once if it has; and a run stopped because
the address register does not go on ends on its last read (`docs/s1b_plan.md`, sections 29,
39 and 60). Nothing was skipped in any run of a chain; a chain's run either passed whole or
the chain halted there.

## 7. Stages

| stage | content | writes configuration memory? | output |
|---|---|---|---|
| S0 | Host only: the frame-access interface, the schema, the safety checker, tests; the PCAP readback sequence copied from zynq-psmap | no | a testable skeleton |
| S1a | Read-only, small: the prober reads the few frames zynq-psmap already verified on this die and must reproduce them | no | the method confirmed on a known range — **done 2026-11-13, PASS** (`evidence/s1a_17A6_2026-11-13/`) |
| S1b | Read-only census, widened in steps: walk the FAR space; record which addresses exist and how many frames each block type has | no | the frame list, compared afterwards with prjxray's 5144 — **done (closed by the owner 2026-11-20, after the review in `docs/s1b_review.md`)**: block type 0 done and graded, 3,864 addresses in two rows of 1,932 frames and 56 columns; block type 1 done and graded, 1,280 addresses in two rows of 640 frames and 5 columns; 5,144 in all and nothing differs. After block type 1 the device names `0x01000000`, block type 2: done (2026-11-19), 112 addresses in two rows of 56 columns of one frame, all zero, not graded (the database has none); after it the device names `0x01800000`, where one unfinished pass (2026-11-19) read ten addresses of block type 3, all zero, and left the register at `0x02000000`, not read. Reading the frames of three of the five columns of block type 1 raises a status bit that is not explained. Step by step in `docs/s1b_plan.md`, which begins with an index |
| S2 | LUT RAM location: the probe circuit writes known patterns into LUT RAM through user logic; read back; find where the patterns land. Also settles the readback mask (GLUTMASK) and the bit order of shift registers | no (only user logic writes) | bit table for SLICEM LUTs (closed-book) — **all six steps done on the board, not graded** (`docs/s2_plan.md`, which says at its head where it stands). Done on the board: S2.0 (2026-11-20; control register 0 is `0x00000501`, bit 8 set), S2.1 (2026-11-20; the prober reaches our own design `s2a` and returns), S2.2 (2026-11-22; 256 bits of block type 0 follow the design's 256 cells of LUT RAM, in the frames `0x00401220` to `0x00401223`; every other bit is still; reading does not disturb the RAM). S2.3 (2026-11-23; every one of the 256 cells has one bit, in words 61 and 62 of those frames, each confirmed by a run of its own), S2.4 (2026-11-23; the shift registers of a second site: 256 bits follow their 128 outputs in the frames `0x00001820` to `0x00001823`, words 40 and 41, half as they are and half inverted, where a prediction made beforehand said, and every output is confirmed). S2.5 (2026-11-24; LUT RAM at 110 sites: 28,160 bits follow, each of the 440 memories is found once by the word it was loaded with, every cell has one bit and is confirmed at every site; 432 memories are where a prediction made beforehand said and 8, at two sites, are six columns of frames lower; four of the five parts of the rule the sites obey hold at every site measured, the column does not). The bit tables are closed-book descriptions (`evidence/s2_3_17A6_2026-11-23/ram_map.json`, `evidence/s2_4b_17A6_2026-11-23/`, `evidence/s2_5b_17A6/ram_map.json` with `rule.json`). Nothing of S2 is graded: once, at its end |
| S3 | Flip-flop state through GCAPTURE | no | flip-flop bit table (closed-book); optional |
| S4 | LUT-level read-modify-write with read-after-write, **writing only bits that S2 located** | yes | the first configuration write; confirms the located bits are LUT content |
| S5 | Ordinary LUTs (SLICEL): known INIT values with locked pins in our design, searched for in readback; then pin-connectivity probing | yes | bit table for SLICEL LUTs (half-open); a connectivity graph |
| S6 | Grading against prjxray-db; the report | no | a list of differences |

S1–S3 never write configuration memory. They are finished and reviewed before S4 is decided.

## 8. Equipment

- Board: EBAZ4203 `17A6` (XC7Z010, TF-card boot). The stages above carry no risk of damaging
  the board. A 4203 keeps no state on the board itself; this project uses **its own TF
  card** and leaves the card and saved environment of other projects untouched.
- The EBAZ4205 is not used (it is the reference board).
- Tools: Vivado 2025.2, to build the probe design and for nothing else; an ARM bare-metal
  toolchain for the prober.

## 9. Prior work, and what can be claimed

From the search as of 2026-11 (notes kept outside this repository):

- On-chip readback has precedent: a soft core reading flip-flop state through ICAP
  (Morales-Villanueva and Gordon-Ross, FCCM 2013); a hard core reading LUT RAM through ICAP
  (Jozwik et al., IJRC 2013); a Zynq ARM core reading and writing block-RAM frames through
  PCAP (Hofmann et al., XBERT, FCCM 2021).
- In every paper read, bit positions came from vendor-tool differencing, the vendor's `.ll`
  file, or the authors' offline analysis (Ziener 2006; Ceschia 2003; Bellato 2004; Kalte and
  Porrmann 2005; Choi and Yoo 2020; Attia and Betz 2020; Kashani et al. 2022).
- Not found: a device locating the bits itself, with no `.ll` and no database, by writing
  through user logic and reading back through the configuration port.

So the only statement available is "not found in a search as of 2026-11", and only for that
combination. Two papers on the list were not read and thirteen candidates were not obtained.

Our own related work: zynq-fabricmap B1 had a board rebuild, closed-book, the map of 292 LUT
INIT addresses — but its address whitelist came from prjxray, and it observed function, not
configuration readback.

This project is engineering and measurement. It makes no claim of a new mechanism.

## 10. Risks

- S1–S3 do not write configuration memory; the risk is in readback itself. UG470 says reading
  block-RAM content interferes with user functions, and Jozwik et al. report block-RAM
  readback failing in their final system. Block-RAM frames therefore come last, and the probe
  circuit does not depend on block RAM.
- The effect of reading an unknown block type, or a FAR that does not exist, is untested.
  (2026-11-18: block type 1 and the places at the end of a row have been read; see section
  11, questions 1 to 3. Reading the frames of three of the five columns of block type 1 sets
  `PCFG_SEU_ERR` in `devcfg.INT_STS`; nothing stopped, and what it means for the running
  design has not been looked into — `docs/s1b_plan.md`, section 52.)
  (2026-11-22: the same bit showed in block type 0, under our own design, after the reads
  of six frames of one column, the same in each of three states of the design's RAM; not
  after the reads of the frames that hold that RAM, whatever it held. From S2.2 on the
  prober records it and clears it alone. Still not explained — `docs/s2_plan.md`,
  section 28.)
- From S4 on configuration memory is written, and only at LUT bits that the project located
  itself and that belong to the probe circuit.
- If the PL-side AXI clock is not running, a PS read of the PL never returns and only a power
  cycle recovers. The prober confirms the clock before its first PL access.
- A wedged configuration interface or a hung PS is not damage: power-cycle and continue. Only
  a failed acceptance retest counts as damage.

## 11. Open questions

To be settled from documents or on the board:

1. **Can the whole FAR space be read?** zynq-psmap verified a handful of chosen frames (three
   distinct frames; one FAR read ten times). A full-device read, across block types and row
   boundaries, has not been verified.
   *2026-11-18:* block type 0 has been read whole, across the end of both of its rows, by
   following the addresses the device names (S1b.3), and block type 1 the same way (S1b.4).
   Not read: anything above block type 1.
   *2026-11-19:* block type 2 has been read whole the same way (S1b.5). Not read: `0x01800000`,
   which the device names after it, and anything above.
   *2026-11-19, later:* a read at `0x01800000` completes and the register goes on (S1b.6a): ten
   addresses of block type 3 in one unfinished pass, then the register at `0x02000000`. UG470
   says a normal bitstream does not include that block type. Where the register's address
   space ends is not known.
2. **What happens at a FAR that does not exist?** Zeros, an error, a wrap, or a stuck
   configuration interface.
   *2026-11-18:* answered only for the end of a row. After the last frame of a row the address
   register stands still for one step and then names the first address of the next row or
   block type; a read that runs on past the last frame delivers frames of zeros, with no error
   and the interface healthy afterwards (S1b.2b, S1b.3a). The walk goes only where the device
   points, so no address chosen because it should not exist has been read.
3. **What is in block type 010, and can PCAP read it?** UG470 lists it as valid; prjxray does
   not carry it.
   *2026-11-18:* still open. After the last frame of block type 1 the device names
   `0x01000000`, the first address of that block type; it was recorded, not read.
   *2026-11-19:* PCAP can read it. One run of 64 addresses (S1b.5a): columns of one frame, 56
   in the top half and at least 8 in the bottom half, every frame all zero, no status bit
   raised. What is in it is not answered: all zero says nothing, and the block type is not
   walked to its end.
   *2026-11-19, later:* walked to its end (S1b.5): 112 addresses, two rows of 56 columns of one
   frame, all zero; then the device names `0x01800000`, which was not read.
4. **Is LUT RAM masked in PCAP readback?** UG470 describes a global GLUTMASK for the 7 series;
   on UltraScale, Attia and Betz had to edit the bitstream to clear per-frame mask bits.
   Untested here.
   *2026-11-22:* not masked, on this board and with these two designs. Control register 0
   reads `0x00000501` under the carrier and under our own design (S2.0, S2.1): bit 8,
   `GLUTMASK_B`, is set, which by UG470's table does not mask. And the content is seen: the
   256 cells of the design's LUT RAM read back as user logic wrote them, all zero, all one,
   all zero (S2.2). Nothing was written to MASK or CTL0. What a design reads as whose
   bitstream leaves the bit clear is not known.
5. **Must the design be stopped for readback?** Attia and Betz say UltraScale does not support
   readback with clocks running; zynq-psmap's non-perturbation result covers only its few
   frames.
   *2026-11-22:* for LUT RAM that is not being written at that moment, no. With the design's
   clock running, every address of block type 0 was read in three states of the RAM; after
   each of the 24 passes the RAM read back through the design as written, and the design's
   counter had gone on (S2.2). Not shown: a RAM written while it is read, block RAM,
   flip-flop state.
6. **Does GCAPTURE work through PCAP, and does it disturb the design?** Never used by us;
   zynq-xpart established only that GRESTORE disturbs a running design.
7. **How are shift-register and LUT-RAM bits laid out within the 64 bits?** On UltraScale the
   shift-register state occupies only the odd bits. For the 7 series this is what S2 is for.
   *2026-11-22:* still open. For one slice of LUT RAM the places are known — all 32 bits of
   two words in each of four frames (S2.2) — and not yet which place is which cell (S2.3),
   nor anything of the shift registers (S2.4).
8. **Getting results off the board, and returning to U-Boot.** The earlier PS program on this
   board (zynq-psoracle's, started with `go 0x02000000`) brought its own startup code and
   took the machine over; it never returned. The prober is meant to be a function in U-Boot's
   context that returns, so that U-Boot can save the DDR buffer (this U-Boot has `go`, FAT
   write and ext4 write). `probes/ret2uboot` tests exactly that and nothing else: it prints
   two lines, snapshots PS registers read-only, fills a 64 KiB buffer and returns 0. Its
   pre-run check passes on the host (`tests/test_ret2uboot.py`, 11 tests; five mutants
   killed). **Run on `17A6` on 2026-11-13: it returns cleanly** — three runs in one power-on,
   every value as fixed beforehand, U-Boot intact afterwards
   (`evidence/ret2uboot_17A6_2026-11-13/RESULT.md`). Saving the buffer to the card works too:
   `fatwrite` of the 64 KiB buffer, read back identical after `mmc rescan` and again after a
   reset (FAT partition only; ext4 untried). This question is closed for S1-sized data.
9. **The PS-to-PL path under a bare-metal program.** What is already known, from our own
   earlier work, none of it re-verified for this project:
   - this U-Boot's `fpga loadb` enables the PS-PL level shifters and releases the FPGA resets
     after a load (`zynq_slcr_devcfg_enable()` in its source);
   - on the 4203 the boot loader leaves FCLK0 at 50 MHz (measured on `17A6`); it must still
     be decoded and confirmed, never assumed;
   - zynq-psoracle's PS program read and wrote an AXI-Lite slave at `0x43C00000` on M_AXI_GP0
     from bare metal on this board, and did PCAP readback by DMA;
   - zynq-fabricmap has the eligibility check for the clock path (PLL lock, FCLK0 source and
     divisors) and an AXI-Lite carrier in RTL;
   - the JTAG smoke test of the 4203 names the three registers that let a load "succeed" into
     a dark fabric (PCFG_PROG_B, LVL_SHFTR_EN, FPGA_RST_CTRL).
   `probes/ret2uboot` recorded these registers as U-Boot leaves them on `17A6` (same result
   file): FCLK0 at 50 MHz, all PLLs locked, level shifters on, FPGA resets released, the SLCR
   locked, and the MMU and both caches on. What remains open is whether anything
   differs when the reader is a returning function rather than a stand-alone image (caches
   and DMA buffers in particular).
   *2026-11-18:* for PCAP readback, one thing did differ. With the data cache off, a polling
   loop that stored to the stack while a transfer ran overflowed the receive FIFO about once
   in a hundred reads; a wait that stores nothing has not overflowed since (`docs/s1b_plan.md`,
   sections 15 to 22). The mechanism in the hardware is not known. The AXI path from this
   program to user logic has not been used yet; S2 needs it.
   *2026-11-20:* the path works. With our own design loaded, the first access to user logic
   at the U-Boot prompt returned, and the prober made 1,164 accesses to the design's
   registers on `M_AXI_GP0` and returned to U-Boot (S2.1); in S2.2 it made 11,344 more in
   eight runs, with PCAP reads between them. The gates it holds first: `SEU_EN` clear, the
   level shifters, the FPGA resets, FCLK0's control word and the PLLs as recorded on this
   board, and the design's identification word.

Decided on 2026-11-13: see section 12.

## 12. Decisions (owner, 2026-11-13)

- Name: zynq-selfmap. This document in English.
- The prober follows zynq-psmap's method but runs on the PS; the TF card may be used.
- Discipline: a safety check of the program before it runs; the closed-book rule; all raw
  readback archived; grading afterwards.
- Board: `17A6`, on the grounds that these stages cannot damage it.
- XC7K70T work, if any, is a separate project. This one is limited to the XC7Z010.
- Exploring without prjxray-db is the point; prjxray-db is the grader, not the teacher.
- The two attack papers that could not be analysed are dropped from the survey.
- Later the same day: zynq-fabricmap's structure description is used as it is; a run starts
  on a small known range and is widened once the principle is confirmed; the safety check is
  by rule and envelope because unknown frames cannot be enumerated in advance; the first
  board test is whether a bare-metal function returns to U-Boot cleanly.
- *2026-11-22:* one of these is changed by the owner for S2: zynq-fabricmap's structure
  description is not used for what S2 finds; a document of our own, modelled on it, is
  (section 4, the note of that day).

## 13. Relation to other projects

- A new standalone directory. No existing project is modified; anything needed is copied in
  with its source commit recorded.
- Sources that may be copied (all our own): zynq-psmap `0bd984f` (the PCAP readback
  sequence, the UG585 discharge, frame-address helpers); zynq-xpart `74208fa` (notes on the
  PCAP/ICAP hand-off).
- zynq-fabricmap's schema is a reference only. Its board time on `17A6`, its card and the
  zynq-psoracle checkout it pins are not touched; the two projects share the board by turns.

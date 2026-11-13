# zynq-selfmap — proposal (draft v0.2, 2026-11-13)

Status: proposal only. No code, nothing on a board. v0.2 folds in the owner's decisions of
2026-11-13 (section 12).

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

Used **afterwards, for grading only**: prjxray-db (zynq7) and the `.ll` file. Grading results
are recorded separately and never edited back into the probed description.

Every result is labelled as one of:

- closed-book: rests on observations made on the device only;
- half-open: also uses "what value our own design put there".

## 4. The structure description

The shape follows zynq-fabricmap's self map; no file of that project is referenced (this
project defines its own schema).

- Coordinates: `FAR/word/bit`.
- Per entry: address, role, confidence (unknown / decoded / confirmed / no effect /
  contradiction), and the observation ids it rests on.
- Collateral rules, e.g. the frame ECC field in word 50 when anything else in the frame
  changes.

Three additions:

- Frame-level records: exists or not, block type, whether readback is stable.
- Roles: LUT RAM, shift register, flip-flop state, ordinary LUT content, block RAM content,
  and "read but never written" for bits whose role is unknown.
- How it was observed: readback only / written through user logic then read back / written
  through configuration then observed functionally.

## 5. The prober

- **Where it runs.** A bare-metal program on the PS of an EBAZ4203. The board boots from a TF
  card into the U-Boot already used on these boards; U-Boot loads the probe bitstream
  (`fpga loadb`) and the prober from the card and starts it.
- **What it starts from.** The PCAP readback sequence that zynq-psmap derived from UG585 and
  verified on this die (two unidirectional DMA commands), moved from "the host issues it
  word by word through U-Boot" to "the PS program issues it".
- **Who decides.** The prober chooses what to read and in which order. The host prepares the
  card, starts the run and collects the results.
- **Where results go.** Raw readback is kept in DDR and saved whole to the card; the UART
  carries progress and a digest of every saved block. Nothing is summarised before it is
  saved.
- **Separation.** The probing logic does not call PCAP directly; frame access sits behind a
  small interface so that the same logic runs on the host against recorded or simulated
  frames. This is for testing, not a commitment to other devices.

## 6. Discipline

Lighter than zynq-fabricmap's ruling-per-session regime. Four fixed points:

1. **The program is checked for safety before it runs.** The code that builds configuration
   command sequences is compiled for the host as well. A host dry run produces every sequence
   the planned run can emit and a checker — a real packet parser, not a word-by-word pattern
   match — holds them to the stage's allow-list (read-only stages: no WCFG, no FDRI, no
   GRESTORE, no IPROG, no write to any register outside the listed ones). The same allow-list
   is enforced again inside the prober at run time. The prober's and the bitstream's sha256
   are written into the run record; a binary whose hash was not checked is not run.
2. **The closed-book rule** of section 3, including a check that the prober's build inputs
   contain none of the forbidden sources.
3. **All raw readback is archived**, unmodified, with digests, before any interpretation.
4. **Grading happens afterwards** and is kept apart from the probed description.

A stage that writes configuration memory (S4 onwards) additionally needs the owner's go-ahead
once, when that stage is first reached.

## 7. Stages

| stage | content | writes configuration memory? | output |
|---|---|---|---|
| S0 | Host only: the frame-access interface, the schema, the safety checker, tests; the PCAP readback sequence copied from zynq-psmap | no | a testable skeleton |
| S1 | Read-only census: walk the FAR space; record which addresses exist and how many frames each block type has | no | the frame list, compared afterwards with prjxray's 5144 |
| S2 | LUT RAM location: the probe circuit writes known patterns into LUT RAM through user logic; read back; find where the patterns land. Also settles the readback mask (GLUTMASK) and the bit order of shift registers | no (only user logic writes) | bit table for SLICEM LUTs (closed-book) |
| S3 | Flip-flop state through GCAPTURE | no | flip-flop bit table (closed-book); optional |
| S4 | LUT-level read-modify-write with read-after-write, **writing only bits that S2 located** | yes | the first configuration write; confirms the located bits are LUT content |
| S5 | Ordinary LUTs (SLICEL): known INIT values with locked pins in our design, searched for in readback; then pin-connectivity probing | yes | bit table for SLICEL LUTs (half-open); a connectivity graph |
| S6 | Grading against prjxray-db and `.ll`; the report | no | a list of differences |

S1–S3 never write configuration memory. They are finished and reviewed before S4 is decided.

## 8. Equipment

- Board: EBAZ4203 `17A6` (XC7Z010, TF-card boot). The stages above carry no risk of damaging
  the board. A 4203 keeps no state on the board itself; this project uses **its own TF
  card** and leaves the card and saved environment of other projects untouched.
- The EBAZ4205 is not used (it is the reference board).
- Tools: Vivado 2025.2 (to build the probe design, and at the very end to produce the `.ll`
  file for grading); an ARM bare-metal toolchain for the prober.

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
2. **What happens at a FAR that does not exist?** Zeros, an error, a wrap, or a stuck
   configuration interface.
3. **What is in block type 010, and can PCAP read it?** UG470 lists it as valid; prjxray does
   not carry it.
4. **Is LUT RAM masked in PCAP readback?** UG470 describes a global GLUTMASK for the 7 series;
   on UltraScale, Attia and Betz had to edit the bitstream to clear per-frame mask bits.
   Untested here.
5. **Must the design be stopped for readback?** Attia and Betz say UltraScale does not support
   readback with clocks running; zynq-psmap's non-perturbation result covers only its few
   frames.
6. **Does GCAPTURE work through PCAP, and does it disturb the design?** Never used by us;
   zynq-xpart established only that GRESTORE disturbs a running design.
7. **How are shift-register and LUT-RAM bits laid out within the 64 bits?** On UltraScale the
   shift-register state occupies only the odd bits. For the 7 series this is what S2 is for.
8. **Getting results off the board.** Whether the prober can return to U-Boot so that U-Boot
   writes the DDR buffer to the card, or the prober needs its own card writer, or the bulk
   goes over the UART.
9. **The PS-to-PL path under a bare-metal program.** Which clock and reset state the U-Boot
   hand-off leaves, and what the prober must set up itself before touching the probe circuit.

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

## 13. Relation to other projects

- A new standalone directory. No existing project is modified; anything needed is copied in
  with its source commit recorded.
- Sources that may be copied (all our own): zynq-psmap `0bd984f` (the PCAP readback
  sequence, the UG585 discharge, frame-address helpers); zynq-xpart `74208fa` (notes on the
  PCAP/ICAP hand-off).
- zynq-fabricmap's schema is a reference only. Its board time on `17A6`, its card and the
  zynq-psoracle checkout it pins are not touched; the two projects share the board by turns.

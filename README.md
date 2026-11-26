# zynq-selfmap

A Zynq-7010 finds the structure of its own PL configuration memory.
It does not use a bit database to do this.

## What the project does

1. A program on the PS reads the PL configuration memory through PCAP. This program is the *prober*.
2. A small design in the PL contains data that we know. The prober can change this data.
3. The prober reads the frames before the change and after the change.
4. The host computer compares the frames. The bits that change show where the data is.
5. The project writes the result as a description of the structure. Each entry of the description refers to the runs that show it.
6. At the end of a stage, the project compares the description with the Project X-Ray database (prjxray-db). This comparison is the *grading*.

## The closed-book rule

These rules apply before the grading of a stage:

- No host program reads a bit database.
- No host program reads the contents of a bitstream.
- No host program uses a Vivado report to find the position of a bit.

A document can contain general knowledge of the 7 series. Such text has a label.
No program and no judge uses it.

Where a prediction is possible, the project makes the prediction before the measurement.
The commit of the prediction is earlier than the run on the board.

## Status on 2026-11-26

| Stage | Subject | Status |
|---|---|---|
| S0 | Host programs and tests | Complete |
| S1a | Frames that an earlier project measured | Complete. The prober read the same contents. |
| S1b | Census of the frame addresses | Complete. Grading: no difference. |
| S2 | Position of the bits of LUT RAM and of shift registers | Complete. All six steps, S2.0 to S2.5, are complete on the board. Grading: no difference. The owner closed S2 on 2026-11-26, after the review in `docs/s2_review.md`. |
| S3 | State of flip-flops (not mandatory) | Not started |
| S4 | First write to the configuration memory | Not started |
| S5 | LUTs of SLICEL sites | Not started |
| S6 | Grading and report | Not started |

Until this date, no program of this project wrote to the configuration memory.

### Results of S1b

- Block type 0 has 3,864 frame addresses. Block type 1 has 1,280 frame addresses.
- The 5,144 addresses are the same as in prjxray-db.
- Block type 2 has 112 frame addresses. All their frames contain zero. The database has no data for them.
- The census is in `census/`.

### Results of S2

These results are closed-book, with one exception. In step S2.5, the site of each table comes from the initial words that the design put in the memories, and the predictions of S2.4 and S2.5 use the frames with those words. The proposal (section 3) calls this half-open. The grading came after the results (see "Grading of S2").

- Control register 0 reads `0x00000501`. Bit 8 is set. Thus the readback shows the contents of LUT RAM.
- LUT RAM, one site, four memories of 64 bits:
  - 256 bits of block type 0 follow the 256 cells.
  - The bits are in the frames `0x00401220` to `0x00401223`, in words 61 and 62.
  - Each cell has one bit. A different run for each cell agrees with the table.
- Shift registers, one site, four registers of 32 outputs:
  - 256 bits follow the 128 outputs. Each output has two bits.
  - One bit shows the value of the output. The other bit shows the opposite value.
  - The bits are in the frames `0x00001820` to `0x00001823`, in words 40 and 41.
  - The prediction gave these frames and these words before the run.
- The two tables are `evidence/s2_3_17A6_2026-11-23/ram_map.json` and `evidence/s2_4b_17A6_2026-11-23/srl_map.json`.
- LUT RAM, 110 sites, four memories of 64 bits at each site (step S2.5):
  - The design gives each of the 440 memories a different initial word. The search found each word one time in the frames. Thus each memory has a known position.
  - 28,160 bits of block type 0 follow the 28,160 cells. Each cell has one bit.
  - A different run for each cell agrees with the table at all the sites.
  - The table is `evidence/s2_5b_17A6/ram_map.json`.
- The prediction of step S2.5:
  - Before the run, a prediction gave the position of each of the 440 memories. It is in `evidence/s2_5_prediction_2026-11-23/`.
  - 432 memories are in the predicted position.
  - 8 memories, at two sites, are not. They are in the predicted words, but six columns of frames lower.
- The rule of step S2.5 is `evidence/s2_5b_17A6/rule.json`. It has five parts:
  - Four parts are correct for all the 110 sites: the sequence of the bits in a memory, the word and the half word for each LUT position, the half of the device, and the word for each row.
  - The part for the column is not one rule. It is correct for the site columns X16 to X42. The site columns X10 and X12 are six columns of frames lower.
  - The measurement is for 110 of the 1,500 sites of this type. For the other sites, the rule is not a measurement.

### Grading of S2

The grading was on 2026-11-26. Before the grading, a document gave the comparisons (`docs/s2_plan.md`, section 57). The result is in `evidence/s2_grade_2026-11-26/`.

- There is no difference.
- LUT RAM: the 28,160 bits of step S2.5 and the 256 bits of step S2.3 are in the same positions as in prjxray-db.
- Shift registers: the 256 bits are bits of the contents of the correct LUTs. The database does not give the sequence of the stages. Thus there is no grading for the sequence.
- The rule: the four correct parts are correct for all the 1,500 sites of this type in the database. The 11 measured columns are correct.
- For the 990 sites that are not measured but are in measured columns, the rule gives the same positions as the database: 253,440 bits.
- The sites of this type are in 15 columns. 4 columns (X0, X4, X6, X8) are not measured.
- The grading does not show that a write to these bits changes a LUT. That is the subject of S4.

## Equipment

- An EBAZ4203 board with an XC7Z010 device. In this project, the name of the board is `17A6`.
- A TF card with U-Boot.
- A USB adapter for the serial console.

The runs use only the serial console. JTAG is not necessary.

## Contents of the repository

| Directory | Contents |
|---|---|
| `prober/` | The prober in C: the program for the board, and a twin for the host computer |
| `probes/` | A small program that showed that a program can return to U-Boot |
| `pl/` | The two PL designs, `s2a` and `s2b`, with their test benches and build records |
| `host/` | The host programs: run scripts, judges, chains, tables, census and grading |
| `tests/` | The tests and the list of mutants |
| `evidence/` | The records of each step on the board |
| `census/` | The census of frame addresses |
| `data/` | Frames that an earlier project measured on this board |
| `schemas/` | The JSON schemas of the descriptions |
| `imported/` | Files from other repositories of the author, with a record of their source |
| `docs/` | The plans and the reviews |
| `proposal.md` | The proposal for the full project |

## How to do the tests

The tests do not use a board. This command does all the tests:

    SELFMAP_NO_BOARD=1 python3 -B -m unittest discover -s tests

`SELFMAP_NO_BOARD=1` makes sure that no test opens the serial console.
There are 1,244 tests. They take approximately 10 minutes.

These tools are necessary:

- Python 3.12 with the packages `jsonschema` and `pyserial`
- `make` and a C compiler
- Icarus Verilog 12
- xPack `arm-none-eabi-gcc` 14.2.1-1.1
- `git`

The Makefiles look for the ARM compiler adjacent to this repository.
Set `XGCC` to use a compiler in a different location.
One test compares the image of the prober with a recorded hash. A different version of the compiler can make a different image. Then this test fails.

Vivado 2025.2 is necessary only to build the PL designs again. The bitstreams are in the repository.

## How to read the evidence

Each directory in `evidence/` contains the records of one step.
Most steps are a sequence of runs. Each run has its own directory with these files:

| File | Contents |
|---|---|
| `run.json` | The record of the run script |
| `result.bin` | The words that the prober gave, without change |
| `verdict.json` | The decision of the judge |
| `console.log` | All the text on the serial console |

A test reads each `result.bin` again and gives it to the judge again. The new decision must be the same as `verdict.json`.

## Documents

- `proposal.md` gives the purpose, the closed-book rule and the stages.
- `docs/s1a_plan.md`, `docs/s1b_plan.md` and `docs/s1b_review.md` are the records of S1.
- `docs/s2_plan.md` is the record of S2. The first paragraphs tell you the status. `docs/s2_review.md` is the review of S2 as a whole.
- `census/README.md` describes the census.

The plans are in time sequence. A later section can correct an earlier section.
The plans are not in Simplified Technical English.

## Technical names in this file

| Name | Meaning |
|---|---|
| prober | The program on the PS that reads the configuration memory |
| twin | A copy of the prober that operates on the host computer for the tests |
| run | One start of the prober on the board, with its records |
| chain | A sequence of runs for one step |
| judge | A host program that reads the result of a run and gives a decision |
| closed-book | Made without a bit database |
| grading | The comparison of a description with prjxray-db |
| census | The list of the frame addresses that the device gives |
| mutant | A copy of a program with one fault. A test must find the fault. |

## Related repositories

- [zynq-psmap](https://github.com/14sea/zynq-psmap): the PCAP readback sequence comes from this project.
- [zynq-fabricmap](https://github.com/14sea/zynq-fabricmap): the AXI front of the design `s2a` comes from this project.
- [ebaz4205-bringup](https://github.com/14sea/ebaz4205-bringup): notes on the related EBAZ4205 board.

## Licence

Apache License, Version 2.0. Refer to [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

# S0 + S1a — plan (2026-11-13)

Goal of S1a: a program on the PS reads three configuration frames through PCAP by itself and
reproduces, word for word, what zynq-psmap read from the same die with the same PL design
loaded. Nothing is written to configuration memory. If this holds, the method is confirmed on
a known range and S1b may widen it.

**No board run happens before the owner has reviewed this plan and the built image.**

**Status, 2026-11-13: steps 1 to 5 are done on the host and were revised after a first review
(section 10); step 6, the owner's review, is next.** What there is to review: this plan;
`prober/`; the plan the run script prints with `host/s1a_run.py --dry-run`; the image
`build/prober/prober.bin`, whose size and sha256 are fixed in `build/prober/expected.json` by
the test suite. The suite is 72 tests. `tests/mutants.py` re-runs 50 deliberate defects in the
prober, the judge and the run script on a scratch copy; its last output is
`evidence/host_checks/mutants_2026-11-13.txt` (50 of 50 failed by the suite).

## 1. What is known going in

| fact | source |
|---|---|
| A function started by `go` returns to U-Boot; its result buffer can be saved to the card | this project, `evidence/ret2uboot_17A6_2026-11-13/` |
| The PCAP readback sequence: 43 command words, a 202-word read, a 5-word cleanup; two unidirectional DMA commands; clear-and-verify before every command; completion on `D_P_DONE`; the error mask | zynq-psmap `docs/s0_derived_sequence.md`, copied to `imported/psmap/`; PASS on `17A6` on 2026-08-29 |
| Three frames of this die with the carrier design loaded: FAR `0x00000b98`, `0x00000b99`, `0x00000b9a` | zynq-psmap's recorded readouts, extracted to `data/known_frames_17A6.json` |
| That run had the D-cache off (`dcache off` in U-Boot) | the same record |

What differs from the verified run: the words are issued by a PS program instead of by the
host through U-Boot commands, and polling is at CPU speed instead of across the UART.

## 2. What the prober may do — the whole list

- Read: DEVCFG `CTRL`, `INT_STS`, `STATUS`, `MCTRL`; SLCR and CPU state for the record; the
  console UART status.
- Write: DEVCFG `INT_STS` (write-1-to-clear of the DMA status and error bits only — never
  bit 2, `PCFG_DONE`), `DMA_SRC_ADDR`, `DMA_DEST_ADDR`, `DMA_SRC_LEN`, `DMA_DEST_LEN`; the
  console UART TX FIFO; DDR inside its own four areas.
- Send to PCAP: only the readback stream and the cleanup stream of the imported sequence.
- It never touches the PL address space, never writes the SLCR, never sends WCFG, FDRI,
  GRESTORE, GCAPTURE, START, SHUTDOWN, RCRC or IPROG.

DDR areas (the two DMA buffers are zynq-psmap's):

| area | address | size |
|---|---|---|
| image | `0x0200_0000` | a few KiB |
| result | `0x1000_0000` | up to 1 MiB |
| parameters (written by the host before `go`) | `0x1010_0000` | 32 words |
| command buffer | `0x1020_0000` | 43 words |
| destination buffer | `0x1030_0000` | 202 words |

## 3. Safety, by rule and envelope

1. **One generator.** `sm_readback_stream(far)` and `sm_cleanup_stream()` are the only code
   that produces configuration words. Their only free parameter is the frame address.
2. **A guard in the prober.** Every stream is parsed before it is handed to the DMA, and
   refused unless it is made of exactly: dummy/sync, NOOP, `CMD = RCFG`, `CMD = DESYNC`,
   `FAR = x` with x inside the run's envelope, the zero-count FDRO read header, and a Type-2
   read of at most the allowed length.
3. **An envelope from the host.** The parameter block carries the address range, the list of
   frames, the repeat count, the reference frame, the anomaly budget and the poll limit. For
   S1a the envelope is `0x00000b98 .. 0x00000b9a`.
4. **Gates before any DMA,** each read live and a failure a stop: `CTRL` bits 27 and 26 set;
   `MCTRL` loopback clear; `PCFG_DONE` set; D-cache off.
5. **Checked on the host before the run:**
   - the generator's output for FAR `0x00000b99` equals the imported 43 words, and the cleanup
     stream the imported 5;
   - an independent packet parser in Python (structural: it decodes any header) accepts every
     stream the generator can produce and agrees with the C guard on mutated streams;
   - the twin — the same C compiled for the host against a small model of DEVCFG and the
     configuration engine — logs every device access; the log is held to an allow-list, to the
     required order of the four DMA register writes, and to clear-verify-wait around every
     command;
   - the board image is inspected (r9, privileged instructions, sections) and its sha256 is
     fixed in `expected.json`.
6. **After the run** the host replays every stream recorded in the result through the Python
   parser.

## 4. Anomalies

| what | class | action |
|---|---|---|
| a gate fails | stop | nothing is sent |
| a stale status bit does not clear; a DMA does not complete within the poll limit; any bit of the error mask | interface | stop and report; no further DMA command is queued |
| `PCFG_DONE` is found clear — checked before every DMA command is queued, on every poll while it runs, and after the three commands of a read | interface | stop and report; the command in hand is the last one |
| the very first read (the reference frame's baseline) is not clean, whatever the reason | — | stop: there is nothing to judge health against (status `0x600` + the record's code) |
| the last read of the run (the reference frame again) is not clean or differs from the baseline | — | the run ends as a health stop (`0x300`), not as done |
| sentinel words survive (a short read); the pad half is not zero; a repeat differs from the first read of the same frame | data | record, then re-read the reference frame: identical to its first reading → skip and continue; different → stop |
| more anomalies than the budget | — | stop |

Everything needed to analyse an anomaly is in the record: the stream sent, the raw 202 words,
`INT_STS` after each of the three DMA commands and the poll counts.

## 5. The result

One buffer, saved whole: a header (status, counts, the parameters echoed, the gate readings)
and one fixed-size record per read (frame address, kind, code, the status words, the streams
as sent, the raw 202 words). No summarising on the board.

**The host saves first and judges afterwards.** After `go`, whatever the console and the
return code say, the host reads the header, takes the size from it, checksums the result on
the board, writes it to the card (and requires U-Boot's `N bytes written` for exactly that
size), pulls it over the console and requires the same checksum. A run with anomalies or an
interface stop is archived whole in the same way as a clean one.

**The judge does not take the board's word.** From the raw words alone it re-derives every
record's code (sentinel survivors, the pad, a differing repeat, the outcome of each of the
three DMA commands from its status word and poll count), walks the records against the
prober's schedule so that no read can be missing, repeated or replaced, and from that walk
derives the status, the anomaly count and the stop record the header ought to carry. Any
disagreement is a failure. Only then are the frames compared with
`data/known_frames_17A6.json`, which the board does not carry. The console line and the return
code are compared with what the result implies.

## 6. Steps

| # | step | where | done when |
|---|---|---|---|
| 1 | this plan; the imports; the known frames | host | committed |
| 2 | the generator and the guard in C; the independent parser in Python; their tests | host | tests and mutants pass |
| 3 | the DMA transaction, the gates and the S1a loop in C; the twin with its device model; fault-injection tests | host | tests and mutants pass |
| 4 | the board image and its inspection; `expected.json` | host | built, hash fixed |
| 5 | the run script: what the host types into U-Boot, in order (`host/s1a_run.py`; `--dry-run` prints it), and the judge (`host/s1a_judge.py`) | host | reviewed text, not yet executed |
| 6 | **owner review** of this plan, the image and the run script | — | the owner's go-ahead |
| 7 | the run on `17A6`; results saved to the card and pulled over the UART | board | verdict written |

## 7. The board run, as it will be proposed in step 5

1. Prompt check; `dcache off`; record `dcache`.
2. Load the carrier design exactly as zynq-psmap did: `loady 0x04000000`, check `crc32`,
   `fpga loadb`; `PCFG_DONE` must then read set.
3. Write the parameter block with `mw.l`; clear the result area.
4. `loady 0x02000000` the prober; check `crc32` against `expected.json`; `go 0x02000000`.
5. Read the header; `crc32` the result; `fatwrite` it to the card; dump it over the UART.
6. Compare with the known frames on the host; replay the recorded streams through the parser.

Expected: three frames, each read three times, every read equal to the known frame; the pad
half all zero; no anomaly; the reference frame unchanged at the end.

## 8. What is new in this run compared with what has been verified, and so what could go wrong

- `go` and the return with the data cache off (the return was verified with it on).
- The four DMA register writes and the status polling done by a program at CPU speed.
- The same sequence repeated eleven times in one run (zynq-psmap did thirteen in one session,
  but each from the host with seconds between them).
- A wedged configuration interface or a hung PS would need a power cycle; neither damages the
  board. Nothing in this run writes configuration memory.

## 9. What S1a will not show

- Anything about frames other than these three, other block types, or addresses that do not
  exist. That is S1b.
- Whether the readback disturbs the running design (zynq-psmap's P2 covered only its own
  frames; the carrier's behaviour is not observed here).
- Reading with the caches on.

## 10. Changes after the first review (2026-11-13)

A review of the first version found four defects; each was reproduced before it was fixed.

| finding | fix | held by |
|---|---|---|
| After `PCFG_DONE` dropped during a read, the remaining DMA commands of that read were still queued | `PCFG_DONE` is checked before every command is queued and on every poll | `test_pcfg_done_dropping_stops_the_run_at_that_command`, `…_found_clear_before_a_command…`, `…no_command_follows_the_failing_one` |
| With any anomaly or stop, the host stopped after `go` and saved nothing; the result size was assumed to be the clean one | the run script saves first and judges afterwards, sizing from the header | `tests/test_s1a_run.py` (a pretend U-Boot whose `go` runs the twin) |
| The judge passed a nonzero pad under a clean code, eleven copies of the baseline, and an anomaly count no record showed | the judge re-derives codes, order, status and counts from the raw words | `tests/test_s1a_host.py` |
| A failed card write could still end in PASS | the write must be confirmed for the exact size; otherwise the run fails (the result is still pulled) | `test_an_unconfirmed_card_write_fails_the_run…` |

Also corrected: the parameter block is 32 words, not 64; the handling of a failed baseline and
of the final reference read is now stated in section 4; the mutants are a script in the
repository with its output kept, where before they were only a claim.

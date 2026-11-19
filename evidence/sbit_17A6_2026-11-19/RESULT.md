# Bit 5 of the status register, cleared after a run — EBAZ4203 `17A6`, 2026-11-19

Question (docs/s1b_plan.md, section 54 (c), as proposed again in section 56): after a run that
has read frames of columns 2 to 4 of block type 1, the status register shows bit 5
(`PCFG_SEU_ERR`). Can it be cleared, and does it stay away while nothing is read?

**It can, and it does. Straight after such a run the status read `50033024`; one write of that
bit; then `50033004` at each of three reads a second apart, with the PL configured and
nothing being read. The bit records something that happened at a read; it is not a state the
PL goes on holding up.**

## What was done

Released by the owner on 2026-11-19 ("the three steps"). The host side at commit `79b2e1b`;
the image and every program as they were. Nothing else ran on the host meanwhile.

1. Pre-check 05:37 UTC (`precheck_console.log`): U-Boot at its prompt, `carrier.bit` on the
   card, status `a802000b`. A `reset`, as before every run of the chain; fresh prompt, status
   `a802000a`.
2. 05:37–05:41 UTC: one run of the prober, the set `s1b4` started at `0x0080013b` — where run
   5 of the stored chain over block type 1 began (`run/`, `run.out`). **PASS**, 292 records,
   no anomaly; the checksum on the board is the checksum on the host; 1 of 69 pieces pulled a
   second time; no short reply not whole. Status afterwards `50033024`.
3. `status_seen.py` over it (`status_seen.json`): bit 5, first at record 2 — the read of the
   pad and the frame at `0x0080013b`, the first read of a frame in the run — and in every
   status word after it.
4. 05:41 UTC, with no `reset` between and nothing else sent: `ps_look.py` (`look/`,
   `look.out`). Twelve commands: the seven dumps, the status, the one write
   `mw.l f800700c 00000020`, the status three times with a second before each.

## What it found

- **The run is run 5 of the stored chain over again.** Judged from its raw words: the same
  verdict in every part, and of its 292 records every field the same — the addresses, the
  frames, the register after each read, every status word — but for how many times a
  transfer was polled before it was done.
- **The bit**: as in the stored run, from the first read of a frame on.
- **The look**: `devcfg.INT_STS` `50033024` before the write; `50033004`, `50033004`,
  `50033004` after it. `PCFG_DONE` set throughout.
- Of the 23 registers of the look, two differ from the look made on the unconfigured board
  (`evidence/pslook_17A6_2026-11-19`): `INT_STS` and `devcfg.STATUS` (`50000f30`, was
  `40000a30`). The level-2 cache, the DDR controller's priorities and the clocks are the same
  with the PL configured and after a run.

## What it says, and what it does not

- UG585 gives the bit as write-one-to-clear, and so it is.
- It stays away for the three seconds it was watched, the design loaded and idle. So it is
  an event that was recorded when a frame was read, not a signal the PL keeps raised. That
  fits the guess of plan section 53, item 2 — the frame ECC logic flagging a frame whose
  check bits do not cover its content, at the moment it is read back — and the other outcome
  would have counted against it. It does not prove the guess.
- Not learned here: whether every read of such a frame raises the bit or only the first.
  The prober does not clear it between reads; that needs a changed prober.
- Not watched longer than three seconds. The board was left as it was after the look: the PL
  configured, status `50033004`.

## A slip of mine in the order of things

The run was committed as stored (`feb4f39`) and then the look as it came (`6e3cf5f`) while
one test of the suite was failing: an older test counted "every stored verdict outside the
directory of S1b.4" and found one more. I had put the suite's last line through `tail`
before the commit, which let the commit go ahead whatever the suite said. Nothing in the two
commits is wrong — they hold only what the board gave — and they were not rewritten. The
test now names the directories whose runs read such frames; the commit with this record is
the first after them with the suite whole.

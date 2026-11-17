# S1b.3a, a walk across the end of the row — EBAZ4203 `17A6`, 2026-11-17: PASS

Question (docs/s1b_plan.md, section 35): with one standstill allowed, does the walk cross the
end of the row at `0x00001ba9`, and what does the device do from `0x00400000` on — in
particular, what does a read started at `0x00400000` leave in the register?

**What there is: the walk crossed. At `0x1ba9` the pad alone left the register standing and
the read of the frame left it at `0x00400000`, as on 2026-11-15 and 2026-11-16; the walk went
on there. At `0x00400000` the pad alone names `0x00400001`: the register goes on, it does not
stand still again. 22 frames of the bottom half were walked, `0x00400000..0x00400015`, each
named by the device after the one before, each read in both passes and again in a read of
three. Every frame of the run is all zero. No overflow, no anomaly. The grader has not been
run.**

## The run

Released by the owner on 2026-11-17 after the review of section 36. The host side at commit
`56b3118`. **The image is new**: `prober.bin`, 11,970 bytes, sha256 `fdc4f07f…9452`, crc32
`84f107a1` (kept here); the walk stage changed, nothing else in the source. Nothing else ran
on the host.

- Pre-check (`precheck_console.log`): U-Boot 2026.04-rc5 at its prompt, `INT_STS 50033004`
  (the PL as the last run left it), `carrier.bit` on the card, 100 files.
- A U-Boot `reset`, checked for the usual fresh prompt (`resets_console.log`), and a fresh load
  of the PL design from the card.
- 04:52 UTC, the set `s1b3a` (kept here as `expected_s1b3a.json`): the walk's set with the
  envelope `0x00000000..0x007fffff`, one standstill a pass allowed, the start `0x00001b80`;
  two passes, at most 64 frames a pass, the reference frame `0xb99` at most 16 frames apart,
  the wait that touches no memory.
- 292 records, status 1, no anomaly; console `SM4 end status=00000001 records=00000124
  anomalies=00000000 words=000223c0`. `result.bin` sha256 `e35a57e1…5dda`; card copy
  `safbdda6.bin`, verified; the board's crc32 of the result `88ba8644` is the host's. One of
  the 69 pieces came back short and was pulled a second time, as the run script provides.
  `INT_STS` afterwards `50033004`.
- 128 reads of the pad alone, 128 reads of one frame, 22 reads of three frames, 14 reads of the
  reference frame. **No overflow, no interface failure.** The polling variable lay at
  `0x1eaca9b8` for the walk's reads (≡ 24 mod 32, as in S1b.2 with the old image, 32 bytes
  lower), `0x1eaca9d8` for 13 of the reference reads and `0x1eacaa00` for the first.
- Committed as saved (`f46bea7`) before the comparison below was made, and that as it came out
  (`9a2328a`) before this was written. Nothing was retried, nothing set aside.

## What the walk found

Both passes: the same 64 addresses, the same frames, the same addresses named, ended at the
limit after `0x00400015` with the device naming `0x00400016`.

- **`0x1b80..0x1ba9`, 42 frames** — column 55 again, each address naming the next number.
- **At `0x1ba9`: a standstill, crossed.**

  | read at `0x1ba9` | register afterwards |
  |---|---|
  | the pad alone | `0x00001ba9` |
  | the pad and the frame | `0x00400000` |

  The same two values as in run 30 of S1b.2 and in `s1b2e`, now on a third day with another
  image.
- **`0x00400000..0x00400015`, 22 frames.** At `0x00400000` the pad alone names `0x00400001`,
  and after the frame the register reads `0x00400002`: from here on it behaves as along a row,
  one step for each frame of words. No second standstill.
- **The reads of three**: 14 in the first piece, the last of them the three frames up to
  `0x1ba9`, after which the register read `0x00400000` — what it read after the single read of
  `0x1ba9`. 8 in the second piece, the first of them at `0x00400000`. None lies across the
  standstill. Every frame of the walk is in one of them, and each such read delivered what the
  single reads did. 145 cross-checks of the register, all met.

**What the content checks are worth: nothing, here.** All 64 frames are all zero — the 42 of
column 55 and the 22 beyond. That two passes and a read of three delivered "the same frame"
says nothing about which frame was read. What carries the result is the register, read after
every one of the 278 reads at these addresses, and the reference frame, as known in all 14
readings.

## Against the stored row (`seam.json`)

`s1b3a_seam.py` on this run's verdict and `row_closed.json` of 2026-11-16: no disagreement.

- The run begins at `0x1b80`, which the stored row has; 42 addresses in both, 42 the same
  frames (one content), the same address named after each of the first 41.
- At the last frame of the stored row the run stood still and went on to `0x00400000`, the
  address the stored row has named after it; the register after the pad alone and after the
  frame are the stored values one and two steps beyond.
- 22 addresses the stored row does not have, `0x00400000..0x00400015`, following its last
  frame; no standstill among them.

## What this does and does not say

- A read started at `0x00400000` behaves like a read started at any address along a row. With
  what `s1b2e` showed (from `0x1ba9`: `0x1ba9`, `0x00400000`, `0x00400000`, `0x00400001`), the
  register's account is: after the last frame of the row, two steps at which it does not
  advance as along a row — it reads `0x1ba9` at the first and already `0x00400000` at the
  second — and then `0x00400000` as an address like any other. Of the twin's four ends of a
  row, this is the one with two places, the register still at the first.
- It does not say what those two places are, nor what a read delivers there beyond "all zero"
  (S1b.2b). This run delivered nothing from them, by design.
- It is one row end. The frames beyond it are all zero in this design, so nothing here shows
  that the frame delivered after writing `0x00400000` is the frame that follows the two places
  when clocking on from `0x1ba9`; the register says they are the same place.
- The cutting of the list at a standstill made no difference to this run's reads (42 frames
  before it are fourteen threes), as section 36 said beforehand.
- The new image ran one walk of 292 records clean. That is one run.

For the owner: the chain over block type 0 (S1b.3 proper), its summary over more than one row
and its grading are the next proposal; nothing of it has been built.

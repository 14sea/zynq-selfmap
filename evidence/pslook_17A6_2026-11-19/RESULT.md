# A look at PS registers from U-Boot — EBAZ4203 `17A6`, 2026-11-19

Plan (docs/s1b_plan.md, section 54): (b) read some PS registers that bear on the receive-FIFO
overflow; (c) clear bit 5 of `devcfg.INT_STS` and see whether it stays away.

**(b) was done: 23 registers read, every dump whole at the first attempt. (c) was not made:
the board had been started anew since S1b.4, the status read `a802000b` — no `PCFG_DONE`, no
bit 5 — and the program wrote nothing, as it is made to. Nothing was written to the board at
all.**

## What was done

Released by the owner on 2026-11-19, who said beforehand that the board had been restarted.
The host side at commit `0429752`. `ps_look.py --dry-run` shown, then `ps_look.py --go --out`
once, 05:30 UTC (`look.out`, `look.json`, `console.log`). No `reset`, no load, no run of the
prober. Eight commands were sent, all of them dumps: the seven of the look and the status.
The program stopped with "the status has not both PCFG_DONE and bit 5 set: nothing was
written". Committed as it came (`c000712`).

The state the registers were read in: U-Boot at its prompt after a fresh start, the PL not
configured.

## The registers, and what UG585's register reference says of the values

| register | value | by UG585 |
|---|---|---|
| `l2cpl310.reg1_control` | `00000000` | `l2_enable` = 0: "L2 Cache is disabled" |
| `l2cpl310.reg1_aux_control` | `02060000` | not looked into; the cache is off |
| `ddrc.axi_priority_wr_port0`–`3` | `000803ff`, all four | priority `0x3FF` (the reset value; "lower the value more will be priority"), aging, urgent and page match not disabled |
| `ddrc.axi_priority_rd_port0`–`3` | `000003ff`, all four | the same for the read ports |
| `slcr.PCAP_CLK_CTRL` | `00000801` | `DIVISOR` 8, source the IO PLL, clock active |
| `slcr.IO_PLL_CTRL` | `00030008` | `PLL_FDIV` 48 |
| `slcr.ARM_PLL_CTRL` | `00028008` | `PLL_FDIV` 40 |
| `slcr.DDR_PLL_CTRL` | `00020008` | `PLL_FDIV` 32 |
| `slcr.ARM_CLK_CTRL` | `1f000200` | `DIVISOR` 2, all five clock enables set |
| `slcr.DDR_CLK_CTRL` | `0c200003` | `DDR_2XCLK_DIVISOR` 3, `DDR_3XCLK_DIVISOR` 2, both active |
| `devcfg.CFG` | `00000508` | `RFIFO_TH` 01 "half full for read", `WFIFO_TH` 01; the low byte `08` not looked into |
| `devcfg.CTRL` | `4e00e07f` | the value in the result headers of S1b.4; bit 8 (`SEU_EN`) clear |
| `devcfg.LOCK` | `0000001a` | not looked into |
| `devcfg.INT_STS` | `a802000b` | the value seen before after power-on; no `PCFG_DONE` |
| `devcfg.INT_MASK` | `ffffffff` | every interrupt masked |
| `devcfg.STATUS` | `40000a30` | not looked into |
| `devcfg.MCTRL` | `30800100` | the value in the result headers of S1b.4 |

With the 33.33 MHz reference of this board — known from earlier work on it, not read here —
those are: IO PLL 1,600 MHz and a PCAP clock of 200 MHz; DDR PLL 1,067 MHz, `ddr_3x` 533 MHz,
`ddr_2x` 356 MHz; ARM PLL 1,333 MHz, the fastest processor clock 667 MHz.

## What this says about the overflow (plan section 53, item 3)

- **The level-2 cache is off.** One of the three directions named there is gone: nothing
  between the processor and the memory holds its stores back or gathers them. This was read
  after a fresh start; the prober does not touch that register, so it is the state it runs in.
- **The DDR controller ranks its four ports alike**, at the lowest starting priority, with
  aging. UG585 on the arbitration: "round robin with aging"; port 0 is "used by the CPUs and
  APU"; and, of page match, "a port that has been selected by the arbiter continues to get
  preference (priority 0) as long as there continues to be page hits". So nothing in the
  settings puts the DMA's writes ahead of the processor's. That fits the plain account — a
  store by the processor can hold up a write of the DMA — and says nothing yet about why the
  place within a 32-byte block matters, or why one read in a hundred.
- **The clocks** are recorded for whoever works out the margin between what the PCAP side
  delivers and what the memory side takes. No conclusion is drawn from them here.

The mechanism is still not known. Left as section 54 left it: the stack offsets 8 and 16
with the present image, if it is wanted.

## (c) is still to be made

It needs the state a run of S1b.4 leaves: the PL configured and bit 5 set. That state went
with the restart. To have it again a run of the prober is needed that reads a frame of
columns 2 to 4 — any run of the stored chain from run 4 on would do — and then this program
straight after it, with no `reset` between. That is a run on the board and has not been
released.

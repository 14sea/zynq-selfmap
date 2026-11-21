/* zynq-selfmap prober — shared definitions. See docs/s1a_plan.md. */
#ifndef SM_H
#define SM_H
#include <stdint.h>
#include <stddef.h>

/* ---- DEVCFG (UG585; imported/psmap/s0_derived_sequence.md section 1) ---- */
#define DEVCFG_CTRL        0xF8007000u
#define DEVCFG_INT_STS     0xF800700Cu
#define DEVCFG_STATUS      0xF8007014u
#define DEVCFG_DMA_SRC     0xF8007018u
#define DEVCFG_DMA_DST     0xF800701Cu
#define DEVCFG_DMA_SLEN    0xF8007020u
#define DEVCFG_DMA_DLEN    0xF8007024u
#define DEVCFG_MCTRL       0xF8007080u
#define CTRL_PCAP_MASK     0x0C000000u   /* PCAP_PR | PCAP_MODE, both required set */
#define CTRL_SEU_EN        0x00000100u   /* UG585: "enables an automatic lockdown of the PS when a PL SEU is detected".
                                            Never set by the prober; from stage 6 on a gate: nothing is sent if it is set */
#define MCTRL_PCAP_LPBK    0x00000010u
#define STS_PCFG_DONE      0x00000004u
#define STS_D_P_DONE       0x00001000u
#define STS_ERR_MASK       0x00F4C840u
#define STS_CLEAR_MASK     0x00F4F840u   /* errors + D_P_DONE + DMA_DONE; never PCFG_DONE */
#define STS_SEU_ERR        0x00000020u   /* bit 5, PCFG_SEU_ERR: not a bit of a transfer. Stage 8 clears it, alone, where it shows */
#define PCAP_ENDPOINT      0xFFFFFFFFu
#define DMA_HOLD_TAG       0x1u

/* ---- configuration words (UG470 table 6-2, as imported) ---- */
#define W_DUMMY            0xFFFFFFFFu
#define W_SYNC             0xAA995566u
#define W_NOOP             0x20000000u
#define W_WR_CMD_1         0x30008001u
#define W_WR_FAR_1         0x30002001u
#define W_RD_FDRO_0        0x28006000u
#define W_T2_READ          0x48000000u
#define W_RD_FAR_1         0x28002001u   /* read the FAR register, one word (UG470 table 6-1 with the FAR address) */
/* S2.0 (docs/s2_plan.md, section 6): one word of three more registers, read the same way. The addresses are UG470's
 * table 5-23: IDCODE 01100, CTL0 00101, STAT 00111 (the last is the header table 6-1 itself prints). */
#define W_RD_IDCODE_1      0x28018001u
#define W_RD_CTL0_1        0x2800A001u
#define W_RD_STAT_1        0x2800E001u
enum { REG_FAR, REG_IDCODE, REG_CTL0, REG_STAT, N_REGS };   /* which register an operation reads after its frame read */
#define CMD_RCFG           0x00000004u
#define CMD_DESYNC         0x0000000Du
#define FRAME_WORDS        101u
#define READ_WORDS         202u          /* (frames to read + 1) x 101: the first frame out is a pad */
#define STREAM_WORDS       43u
#define CLEANUP_WORDS      5u
#define FARRD_WORDS        4u            /* NOOP, the read header, NOOP, NOOP */
#define MAX_READ_FRAMES    3u            /* stages 2 and 3: frames per FDRO read */
#define N_NONE             0xFu          /* stage 3 only, as a frame count: no FDRO read at all; a count of 0 is the pad alone */
#define DATA2_WORDS        (FRAME_WORDS * (MAX_READ_FRAMES + 1u))   /* 404 */

/* ---- DDR areas ---- */
#define RESULT_ADDR        0x10000000u
#define RESULT_MAX_WORDS   0x00040000u   /* 1 MiB */
#define PARAM_ADDR         0x10100000u
#define PARAM_WORDS        32u
#define CMD_BUF            0x10200000u
#define DST_BUF            0x10300000u
#define SENTINEL           0xA5A55A5Au

/* ---- parameter block (written by the host) ---- */
#define PARAM_MAGIC        0x31504D53u   /* "SMP1" */
enum { P_MAGIC, P_VERSION, P_STAGE, P_FAR_LO, P_FAR_HI, P_REF_FAR, P_N_FARS, P_REPEATS,
       P_ANOMALY_BUDGET, P_POLL_LIMIT, P_FARS = 16 };
#define P_NFRAMES_LO       10u           /* stages 2 and 3: frames per read, 4 bits per entry, entries 0..7 */
#define P_NFRAMES_HI       11u           /*          entries 8..15 */
#define MAX_FARS           16u
/* stage 4 (the walk): P_FARS[0] is the starting address, P_REPEATS the number of passes */
#define P_WALK_LIMIT       12u           /* frames per pass, at most */
#define P_HEALTH_EVERY     13u           /* never more than this many frames delivered between two reference reads */
#define MAX_WALK           64u
#define MAX_PASSES         2u
/* stage 4, the end of a row (2026-11-16): at the last address of a row the pad alone leaves the register where it is,
 * and the read of that frame leaves it at the first address of the next row. A pass may cross this many such
 * standstills; 0: none — the walk stops there, as it did before. (The word the table-driven stages use for frames
 * per read; stage 4 has no table.) */
#define P_STANDSTILLS      10u
#define MAX_STANDSTILLS    4u
/* diagnostics (2026-11-14: the walk overflows the receive FIFO, stages 2 and 3 do not). Stage 5 is stage 3 with two
 * options; stage 4 takes the second as well. Both zero: nothing differs from before. */
#define P_DIAG_SEQ         14u           /* stage 5: instead of the table, a generated sequence — at each of this many
                                            addresses from P_FARS[0] on, the pad alone and then the frame */
#define P_DIAG_STACK       15u           /* stages 4 and 5. Low byte: this many more words of stack beneath each target
                                            read. Bits 8 and up: which loop waits for a transfer (below). */
#define MAX_DIAG_SEQ       32u
#define MAX_DIAG_STACK     64u
/* the loop that waits for a transfer (2026-11-15: the overflow follows where the read lies on the stack, and while a
 * transfer runs the only thing the prober does there is this loop: two stores and one load on every poll) */
#define DIAG_POLL_SHIFT    8u
#define POLL_AS_BEFORE     0u            /* status and count stored to the caller's stack on every poll, the limit loaded from it */
#define POLL_NO_STORES     1u            /* nothing stored until the transfer is over; the limit still loaded from the same slot */
#define POLL_NO_STACK      2u            /* nothing stored and nothing loaded: the loop touches no memory at all */
#define MAX_REPEATS        8u
/* stages 6 (S2.0) and 7 (S2.1): the table-driven stage with one thing more — the register read after each operation is
 * chosen by the host, four bits an operation, from the list above. At most eight operations, so the upper half of the
 * table of addresses is free; stage 7 has its second envelope there. Words these stages do not use must be zero. */
#define P_REGS             12u
#define MAX_REG_OPS        8u
#define P_PL_LO            24u           /* stage 7: the envelope of PL addresses, both ends included */
#define P_PL_HI            25u
#define P_PL_ID            26u           /*          what the design's identification register must read */
#define P_SLCR             28u           /*          four words: what the four SLCR registers below must read */

/* ---- stage 7 (S2.1): the first access to user logic (docs/s2_plan.md, section 7) ---- */
#define SLCR_LVL_SHFTR_EN  0xF8000900u   /* read, never written; the SLCR is locked and stays so */
#define SLCR_FPGA_RST_CTRL 0xF8000240u
#define SLCR_FPGA0_CLK     0xF8000170u
#define SLCR_PLL_STATUS    0xF800010Cu
#define N_SLCR             4u
/* the probe design s2a (pl/s2a): eight registers on M_AXI_GP0 */
#define PL_BASE            0x40000000u
#define PL_ID              0x00u         /* read: a fixed word */
#define PL_SCRATCH         0x04u         /* read, write */
#define PL_COUNT           0x08u         /* read: counts FCLK0 */
#define PL_RAM_ADDR        0x0Cu         /* read, write: the address of the LUT RAM, six bits */
#define PL_RAM_DATA        0x10u         /* write: one write of four bits at that address; read: the four outputs there */
#define PL_SRL_ADDR        0x14u         /* read, write: the address of the shift registers' outputs, five bits */
#define PL_SRL_DATA        0x18u         /* read: the four outputs there. A write shifts — and is not on this prober's list */
#define PL_WRITES          0x1Cu         /* read: RAM writes (low half) and shifts (high half) since the design was loaded */
#define PL_SPAN            0x20u
/* the registers this prober may write, one bit for each offset: the scratch register, the two addresses, the RAM's data */
#define PL_WRITABLE        ((1u << PL_SCRATCH) | (1u << PL_RAM_ADDR) | (1u << PL_RAM_DATA) | (1u << PL_SRL_ADDR))   /* 0x00111010 */
#define RAM_DEPTH          64u
#define SRL_DEPTH          32u
#define RAM_STATES         4u            /* all zero, all one, the address's low four bits, their complement */
/* the PL block of a stage-7 result: between the header and the records, counted with the header (H_HDR_WORDS) */
#define PLB_MAGIC_VALUE    0x4C504D53u   /* "SMPL" */
enum { PLB_MAGIC, PLB_N, PLB_CODE, PLB_AT, PLB_SLCR, PLB_LOG = 16 };
#define PL_LOG_MAX         1280u         /* accesses; each two words: the address (bit 0 set: a write), the value */
#define PLB_WORDS          (PLB_LOG + 2u * PL_LOG_MAX)                                    /* 2576 */
enum { PLC_OK, PLC_REFUSED, PLC_ID, PLC_SCRATCH, PLC_COUNT, PLC_RAM, PLC_SRL, PLC_WRITES, PLC_FULL,
       PLC_DISTURBED };                  /* stage 8: after frames were read, the RAM no longer holds the state it was given */

/* ---- stage 8 (S2.2): is the RAM seen in readback (docs/s2_plan.md, section 19) ----
 * For each of the states the host names, the RAM is set through the design, every read of a list is made through
 * PCAP, and the RAM is read through the design again. The list is the host's: one word a read, written to LIST_ADDR
 * before the prober is started — the address in the low 28 bits, the number of frames (1 to 3) above them. The
 * prober does no arithmetic on addresses; it holds each to the envelope, as every stage does. */
#define LIST_ADDR          0x10180000u
#define LIST_MAX           178u          /* with three states: 538 records, which the result area holds */
#define LIST_FAR(w)        ((w) & 0x0FFFFFFFu)
#define LIST_N(w)          ((w) >> 28)
#define P_LIST_N           16u           /* how many reads the list has */
#define P_STATES           17u           /* the states, four bits each, P_REPEATS of them: 0 all zero, 1 all one */
#define MAX_STATES         3u
#define P8_USED            0xF70382BFu   /* the words of the parameter block this stage has a use for; every other is zero */
#define OP8_CTL0           0x100u        /* in R_OP: the read of CTL0, which reads no frame; a read of the list has its index there */
#define PL8_LOG_MAX        1440u         /* 1 + 64 accesses before the states, 451 for each state: 1418 with three */
#define PLB8_WORDS         (PLB_LOG + 2u * PL8_LOG_MAX)                                   /* 2896 */

/* ---- result ---- */
#define RESULT_MAGIC       0x31524D53u   /* "SMR1" */
#define HDR_WORDS          64u
#define REC_HDR_WORDS      16u
#define REC_WORDS          (REC_HDR_WORDS + STREAM_WORDS + CLEANUP_WORDS + READ_WORDS)   /* 266 */
/* stage 2 record: header, the three streams, eight words about the FAR read, the raw data */
#define REC2_FARBLK        (REC_HDR_WORDS + STREAM_WORDS + FARRD_WORDS + CLEANUP_WORDS)   /* 68 */
#define REC2_DATA          (REC2_FARBLK + 8u)                                             /* 76 */
#define REC2_WORDS         (REC2_DATA + DATA2_WORDS)                                      /* 480 */
enum { F_STS_CMD, F_POLLS_CMD, F_STS_READ, F_POLLS_READ, F_VALUE, F_UNREAD,
       F_POLL_VAR,     /* the FAR-read block; this one: where on the stack the status word of the polling loop lay (recorded, not judged) */
       F_STS_AFTER };  /* stage 8, a read of the list: INT_STS as that read left it, before anything is cleared; zero elsewhere */
#define R_NFRAMES          14u           /* stages 2 and 3; zero in stage 1 */
#define R_OP               15u
enum { H_MAGIC, H_VERSION, H_STATUS, H_N_RECORDS, H_N_ANOMALIES, H_TOTAL_WORDS, H_REC_WORDS, H_HDR_WORDS,
       H_CTRL, H_MCTRL, H_INT_STS0, H_STATUS0, H_SCTLR, H_CPSR, H_SP, H_R9,
       H_INT_STS1, H_STATUS1, H_STOP_RECORD, H_WALK, H_PARAMS = 32 };
/* stage 4: from H_WALK, three words per pass: frames walked, how the pass ended, the last address the device named */
enum { END_NONE, END_LEFT, END_LIMIT };  /* not ended; the device named an address outside the envelope; the limit */
enum { OP_SUCC, OP_CONTENT, OP_TRIPLE }; /* stage 4, in R_OP: the pad alone; the pad and the frame; several frames (three, or two) in one read */
enum { R_FAR, R_KIND, R_CODE, R_STS_CMD, R_POLLS_CMD, R_STS_READ, R_POLLS_READ, R_STS_CLEAN, R_POLLS_CLEAN,
       R_SURVIVORS, R_REF_EQUAL, R_STATUS_AFTER, R_REPEAT, R_GUARD, R_STREAM = 16 };
enum { KIND_TARGET = 0, KIND_HEALTH = 1, KIND_BASELINE = 2, KIND_FINAL = 3 };
/* stage 8, a read of the list: INT_STS read again after bit 5 was cleared; 0xffffffff: bit 5 did not show, nothing
 * was cleared. (The word is the health flag of a reference read; a read of the list has none.) */
#define R8_STS_CLEARED     R_REF_EQUAL

/* record codes */
#define C_OK               0x00u
#define C_SURVIVORS        0x10u         /* data class: a short read */
#define C_PAD_NONZERO      0x11u
#define C_REPEAT_DIFFERS   0x12u
#define C_FAR_DIFFERS      0x13u         /* stage 2: the FAR read back differs from the first time */
#define C_FAR_UNREAD       0x14u         /* stage 2: the FAR read delivered nothing */
#define C_STALE            0x20u         /* interface class */
#define C_DEVERR           0x21u
#define C_TIMEOUT          0x22u
#define C_DONE_DROPPED     0x23u
#define C_GUARD            0x30u         /* the generator produced something the guard refuses: a bug */
#define IS_INTERFACE(c)    ((c) >= 0x20u)

/* run status */
#define S_INCOMPLETE       0x000u
#define S_DONE             0x001u
#define S_GATE_CTRL        0x101u
#define S_GATE_LPBK        0x102u
#define S_GATE_NOT_DONE    0x103u
#define S_GATE_DCACHE      0x104u
#define S_GATE_SEU         0x105u        /* stages 6 and 7: SEU_EN is set in devcfg.CTRL */
#define S_GATE_SLCR        0x110u        /* | which of the four words; stage 7: the PS side of the PL is not as recorded */
#define S_STOP_INTERFACE   0x200u        /* | record code */
#define S_STOP_HEALTH      0x300u
#define S_STOP_BUDGET      0x400u
#define S_BAD_PARAMS       0x500u
#define S_STOP_BASELINE    0x600u        /* | record code */
#define S_STOP_WALK        0x700u        /* | record code; stage 4: any anomaly ends the walk, there is nothing to skip to */
#define S_STOP_STUCK       0x800u        /* stage 4: the address the device named is not above the one it was asked about */
#define S_STOP_STANDSTILLS 0x900u        /* stage 4: the register stood still at one address more than a pass may cross */
#define S_STOP_PL          0xA00u        /* | PLC_*; stages 7 and 8: user logic did not answer as the design must */

/* ---- hardware access: the only doors (board: sm_board.c, host twin: twin_hal.c) ---- */
uint32_t hal_rd(uint32_t addr);                 /* device register read */
void     hal_wr(uint32_t addr, uint32_t value); /* device register write */
uint32_t hal_mem_rd(uint32_t addr);             /* DDR word read  */
void     hal_mem_wr(uint32_t addr, uint32_t value);
enum { CPU_SCTLR, CPU_CPSR, CPU_SP, CPU_R9 };
uint32_t hal_cpu(int which);
void     hal_putc(char c);
void     hal_watch(const uint32_t *polls);       /* the count a read's transfers store their polls to: the twin looks at it
                                                    while a transfer is polled; the board does nothing with it */

/* ---- sm_core.c ---- */
void     sm_readback_stream(uint32_t far, uint32_t out[STREAM_WORDS]);
void     sm_cleanup_stream(uint32_t out[CLEANUP_WORDS]);
void     sm_frames_stream(uint32_t far, uint32_t n_frames, uint32_t out[STREAM_WORDS]);
void     sm_far_read_stream(uint32_t out[FARRD_WORDS]);
void     sm_reg_read_stream(uint32_t reg, uint32_t out[FARRD_WORDS]);
uint32_t sm_guard(const uint32_t *w, uint32_t n, uint32_t far_lo, uint32_t far_hi, uint32_t max_read);
uint32_t sm_run(void);

#endif

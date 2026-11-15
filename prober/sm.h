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
#define MCTRL_PCAP_LPBK    0x00000010u
#define STS_PCFG_DONE      0x00000004u
#define STS_D_P_DONE       0x00001000u
#define STS_ERR_MASK       0x00F4C840u
#define STS_CLEAR_MASK     0x00F4F840u   /* errors + D_P_DONE + DMA_DONE; never PCFG_DONE */
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
       F_POLL_VAR };   /* the FAR-read block; the last: where on the stack the status word of the polling loop lay (recorded, not judged) */
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
#define S_STOP_INTERFACE   0x200u        /* | record code */
#define S_STOP_HEALTH      0x300u
#define S_STOP_BUDGET      0x400u
#define S_BAD_PARAMS       0x500u
#define S_STOP_BASELINE    0x600u        /* | record code */
#define S_STOP_WALK        0x700u        /* | record code; stage 4: any anomaly ends the walk, there is nothing to skip to */
#define S_STOP_STUCK       0x800u        /* stage 4: the address the device named is not above the one it was asked about */

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
uint32_t sm_guard(const uint32_t *w, uint32_t n, uint32_t far_lo, uint32_t far_hi, uint32_t max_read);
uint32_t sm_run(void);

#endif

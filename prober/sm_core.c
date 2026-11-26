/* zynq-selfmap prober core: the stream generator, the guard, the DMA transaction and stage S1a.
 * No mutable static data: everything lives on the caller's stack or in the fixed DDR areas. */
#include "sm.h"

/* ------------------------------------------------------------------ generator */
void sm_readback_stream(uint32_t far, uint32_t out[STREAM_WORDS])
{
    uint32_t i = 0, k;
    out[i++] = W_DUMMY;
    out[i++] = W_SYNC;
    out[i++] = W_NOOP;
    out[i++] = W_NOOP;
    out[i++] = W_WR_CMD_1;
    out[i++] = CMD_RCFG;
    out[i++] = W_NOOP;
    out[i++] = W_WR_FAR_1;
    out[i++] = far;
    out[i++] = W_RD_FDRO_0;
    out[i++] = W_T2_READ | READ_WORDS;
    for (k = 0; k < 32u; k++)
        out[i++] = W_NOOP;
}

/* the same stream reading n_frames frames in one FDRO read: only the length differs. A count of 0 reads the
 * pad alone; N_NONE reads nothing — the two words of the read are NOOPs, the rest of the session is the same */
void sm_frames_stream(uint32_t far, uint32_t n_frames, uint32_t out[STREAM_WORDS])
{
    sm_readback_stream(far, out);
    if (n_frames == N_NONE) {
        out[9] = W_NOOP;
        out[10] = W_NOOP;
    } else {
        out[10] = W_T2_READ | (FRAME_WORDS * (n_frames + 1u));
    }
}

/* read the FAR register, inside a session that is already synchronised (UG470 table 6-1, steps 6 to 9) */
void sm_far_read_stream(uint32_t out[FARRD_WORDS])
{
    out[0] = W_NOOP;
    out[1] = W_RD_FAR_1;
    out[2] = W_NOOP;
    out[3] = W_NOOP;
}

/* the same for one of the five registers a stage may read (S2.0; COR0 since S3.0): only the header differs. An unknown
 * choice is the FAR register, the one read there has always been. */
void sm_reg_read_stream(uint32_t reg, uint32_t out[FARRD_WORDS])
{
    sm_far_read_stream(out);
    if (reg == REG_IDCODE)
        out[1] = W_RD_IDCODE_1;
    else if (reg == REG_CTL0)
        out[1] = W_RD_CTL0_1;
    else if (reg == REG_STAT)
        out[1] = W_RD_STAT_1;
    else if (reg == REG_COR0)
        out[1] = W_RD_COR0_1;
}

void sm_cleanup_stream(uint32_t out[CLEANUP_WORDS])
{
    out[0] = W_NOOP;
    out[1] = W_WR_CMD_1;
    out[2] = CMD_DESYNC;
    out[3] = W_NOOP;
    out[4] = W_NOOP;
}

/* ------------------------------------------------------------------ guard
 * Accepts only what a read-only stage may send. Returns 0, or ((index + 1) << 8) | reason. */
#define REFUSE(i, why) ((((i) + 1u) << 8) | (why))
/* how many whole frames a word count is; no division, the image has no runtime library */
static uint32_t whole_frames(uint32_t words)
{
    uint32_t n = 0u;
    while (words >= FRAME_WORDS) {
        words -= FRAME_WORDS;
        n++;
    }
    return words ? 0xFFFFFFFFu : n;
}
uint32_t sm_guard(const uint32_t *w, uint32_t n, uint32_t far_lo, uint32_t far_hi, uint32_t max_read)
{
    uint32_t i = 0, x, v, far_value = 0u;
    int rcfg = 0, far = 0, hdr = 0;

    if (n == 0u)
        return REFUSE(0u, 1u);
    if (w[0] == W_DUMMY || w[0] == W_SYNC) {            /* an optional prefix: dummies, then exactly one sync */
        while (i < n && w[i] == W_DUMMY)
            i++;
        if (i >= n || w[i] != W_SYNC)
            return REFUSE(i, 2u);
        i++;
    }
    while (i < n) {
        x = w[i];
        if (hdr) {                                      /* the word after the zero-count FDRO header */
            v = x & 0x07FFFFFFu;
            if ((x & 0xF8000000u) != W_T2_READ || v == 0u || v > max_read || !rcfg || !far)
                return REFUSE(i, 3u);
            v = whole_frames(v);                                         /* v <= max_read was checked just above */
            if (v == 0xFFFFFFFFu)                                        /* a pad frame and whole frames; the pad alone delivers none */
                return REFUSE(i, 10u);
            if (v >= 2u && v - 2u > far_hi - far_value)                 /* the last frame read is still inside; far_value <= far_hi
                                                                           was checked when it was written, so nothing can wrap */
                return REFUSE(i, 11u);
            far = 0;                                    /* the register has moved on: another read needs a new, checked address */
            hdr = 0; i++;
            continue;
        }
        if (x == W_NOOP) {
            i++;
        } else if (x == W_WR_CMD_1) {
            if (i + 1u >= n)
                return REFUSE(i, 4u);
            v = w[i + 1u];
            if (v == CMD_RCFG)
                rcfg = 1;
            else if (v != CMD_DESYNC)
                return REFUSE(i + 1u, 5u);
            i += 2u;
        } else if (x == W_WR_FAR_1) {
            if (i + 1u >= n)
                return REFUSE(i, 6u);
            v = w[i + 1u];
            if (v < far_lo || v > far_hi)
                return REFUSE(i + 1u, 7u);
            far = 1; far_value = v;
            i += 2u;
        } else if (x == W_RD_FDRO_0) {
            hdr = 1; i++;
        } else if (x == W_RD_FAR_1 || x == W_RD_IDCODE_1 || x == W_RD_CTL0_1 || x == W_RD_STAT_1 || x == W_RD_COR0_1) {
            i++;                                        /* one word of a readable register: these five headers and no other */
        } else {
            return REFUSE(i, 8u);
        }
    }
    if (hdr)
        return REFUSE(n, 9u);
    return 0u;
}

/* ------------------------------------------------------------------ small helpers */
static void put(const char *s) { for (; *s; s++) hal_putc(*s); }
static void puthex(uint32_t v)
{
    int sh;
    for (sh = 28; sh >= 0; sh -= 4)
        hal_putc("0123456789abcdef"[(v >> sh) & 0xFu]);
}
static void res_wr(uint32_t word_index, uint32_t v) { hal_mem_wr(RESULT_ADDR + 4u * word_index, v); }
static uint32_t res_rd(uint32_t word_index)         { return hal_mem_rd(RESULT_ADDR + 4u * word_index); }
static uint32_t par(uint32_t i)                     { return hal_mem_rd(PARAM_ADDR + 4u * i); }

/* ------------------------------------------------------------------ one DMA command
 * Clear and verify the stale status, program the four registers in the normative order, wait for
 * D_P_DONE. PCFG_DONE is a precondition of every command (UG585: no readback without it) and is
 * checked before the command is queued and on every poll: if it is ever seen clear, nothing more
 * is sent. Returns a record code; *sts and *polls are what was seen. */
/* which loop waits for a transfer: stages 4 to 7 choose (word 15), stages 1 to 3 have the one they always had */
static uint32_t poll_mode(void)
{
    uint32_t stage = par(P_STAGE);
    return (stage >= 4u && stage <= 9u) ? par(P_DIAG_STACK) >> DIAG_POLL_SHIFT : POLL_AS_BEFORE;
}

/* What a transfer writes to INT_STS before it begins. Every stage up to 7 clears the error bits with the two done
 * bits, and then holds the register to be clean: an error bit that appeared after the transfer before was seen done
 * is cleared without ever having been read. Stage 8 clears the done bits alone (reviews of 9fa606e and 334df53: a
 * read of the register before the clearing still left the moment between that read and the write). No error bit is
 * cleared by stage 8 at any time, so one that shows after the clearing stood there before it: C_LATE, and the
 * transfer is not queued. The other stages make the accesses they always made, with the values they always wrote. */
static uint32_t begin_mask(void)
{
    return (par(P_STAGE) == 8u || par(P_STAGE) == 9u) ? STS_DONE_MASK : STS_CLEAR_MASK;   /* stage 9 reads as stage 8 does */
}

/* The wait that stores nothing (diagnostics): the write that queues the command, then the same polls and the same
 * four ways out as in dma() below, with the status and the count kept in registers until the transfer is over. With
 * `limit_at` the limit is read through it on every poll — the caller passes the stack slot the original loop loads
 * it from; without, the limit is `limit`, and between queueing the command and its end the prober touches no memory
 * but its own code. The command is queued in here, after this function has saved its registers, so that not even
 * that is written while the transfer runs. Not inlined: its registers are its own, whatever the caller has in use. */
static __attribute__((noinline)) uint32_t queue_and_wait_quiet(uint32_t dlen, const volatile uint32_t *limit_at, uint32_t limit,
                                                               uint32_t *polls)
{
    uint32_t s, n;

    hal_wr(DEVCFG_DMA_DLEN, dlen);                      /* this write queues the command */
    for (n = 1u; ; n++) {
        s = hal_rd(DEVCFG_INT_STS);
        if ((s & STS_ERR_MASK) || !(s & STS_PCFG_DONE) || (s & STS_D_P_DONE))
            break;
        if (n >= (limit_at ? *limit_at : limit))
            break;
    }
    *polls = n;
    return s;
}

/* One DMA command with that wait: what dma() below does, to the same registers in the same order. `limit_at` is
 * where dma()'s own loop reads the limit from. */
static uint32_t dma_quiet(uint32_t mode, uint32_t src, uint32_t dst, uint32_t slen, uint32_t dlen, uint32_t poll_limit,
                          const volatile uint32_t *limit_at, uint32_t *sts, uint32_t *polls)
{
    uint32_t v;

    *polls = 0u;
    hal_wr(DEVCFG_INT_STS, begin_mask());
    v = hal_rd(DEVCFG_INT_STS);
    *sts = v;
    if ((v & STS_ERR_MASK) && begin_mask() == STS_DONE_MASK)
        return C_LATE;
    if (v & STS_CLEAR_MASK)
        return C_STALE;
    if (!(v & STS_PCFG_DONE))
        return C_DONE_DROPPED;
    hal_wr(DEVCFG_DMA_SRC, src);
    hal_wr(DEVCFG_DMA_DST, dst);
    hal_wr(DEVCFG_DMA_SLEN, slen);
    v = queue_and_wait_quiet(dlen, mode == POLL_NO_STORES ? limit_at : 0, poll_limit, polls);
    *sts = v;
    return (v & STS_ERR_MASK) ? C_DEVERR : !(v & STS_PCFG_DONE) ? C_DONE_DROPPED : (v & STS_D_P_DONE) ? C_OK : C_TIMEOUT;
}

static uint32_t dma(uint32_t src, uint32_t dst, uint32_t slen, uint32_t dlen, uint32_t poll_limit,
                    uint32_t *sts, uint32_t *polls)
{
    uint32_t s, n;

    n = poll_mode();                                    /* read before anything is sent */
    if (n != POLL_AS_BEFORE)                            /* diagnostics; from here on this function is as it always was */
        return dma_quiet(n, src, dst, slen, dlen, poll_limit, &poll_limit, sts, polls);
    *polls = 0u;
    hal_wr(DEVCFG_INT_STS, begin_mask());
    s = hal_rd(DEVCFG_INT_STS);
    *sts = s;
    if ((s & STS_ERR_MASK) && begin_mask() == STS_DONE_MASK)
        return C_LATE;
    if (s & STS_CLEAR_MASK)
        return C_STALE;
    if (!(s & STS_PCFG_DONE))
        return C_DONE_DROPPED;
    hal_wr(DEVCFG_DMA_SRC, src);
    hal_wr(DEVCFG_DMA_DST, dst);
    hal_wr(DEVCFG_DMA_SLEN, slen);
    hal_wr(DEVCFG_DMA_DLEN, dlen);                      /* this write queues the command */
    for (n = 1u; ; n++) {
        s = hal_rd(DEVCFG_INT_STS);
        *sts = s; *polls = n;
        if (s & STS_ERR_MASK)
            return C_DEVERR;
        if (!(s & STS_PCFG_DONE))
            return C_DONE_DROPPED;
        if (s & STS_D_P_DONE)
            return C_OK;
        if (n >= poll_limit)
            return C_TIMEOUT;
    }
}

/* ------------------------------------------------------------------ one frame read into record `rec`
 * Returns the record code. The record holds the streams as sent and the raw 202 words. */
static uint32_t read_frame(uint32_t rec, uint32_t far, uint32_t kind, uint32_t repeat,
                           uint32_t far_lo, uint32_t far_hi, uint32_t poll_limit)
{
    uint32_t stream[STREAM_WORDS], clean[CLEANUP_WORDS];
    uint32_t base = HDR_WORDS + rec * REC_WORDS, i, code, g, sts = 0u, polls = 0u, survivors = 0u, w;

    for (i = 0; i < REC_WORDS; i++)
        res_wr(base + i, 0u);
    res_wr(base + R_FAR, far);
    res_wr(base + R_KIND, kind);
    res_wr(base + R_REPEAT, repeat);
    res_wr(base + R_REF_EQUAL, 0xFFFFFFFFu);

    sm_readback_stream(far, stream);
    sm_cleanup_stream(clean);
    g = sm_guard(stream, STREAM_WORDS, far_lo, far_hi, READ_WORDS);
    if (g == 0u)
        g = sm_guard(clean, CLEANUP_WORDS, far_lo, far_hi, READ_WORDS);
    res_wr(base + R_GUARD, g);
    for (i = 0; i < STREAM_WORDS; i++)
        res_wr(base + R_STREAM + i, stream[i]);
    for (i = 0; i < CLEANUP_WORDS; i++)
        res_wr(base + R_STREAM + STREAM_WORDS + i, clean[i]);
    if (g != 0u) {
        res_wr(base + R_CODE, C_GUARD);
        return C_GUARD;
    }

    for (i = 0; i < STREAM_WORDS; i++)
        hal_mem_wr(CMD_BUF + 4u * i, stream[i]);
    for (i = 0; i < READ_WORDS; i++)
        hal_mem_wr(DST_BUF + 4u * i, SENTINEL);

    code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, STREAM_WORDS, 0u, poll_limit, &sts, &polls);
    res_wr(base + R_STS_CMD, sts); res_wr(base + R_POLLS_CMD, polls);
    if (code == C_OK) {
        code = dma(PCAP_ENDPOINT, DST_BUF | DMA_HOLD_TAG, 0u, READ_WORDS, poll_limit, &sts, &polls);
        res_wr(base + R_STS_READ, sts); res_wr(base + R_POLLS_READ, polls);
    }
    if (code == C_OK) {                                 /* leave the engine desynchronised (UG470 step 14) */
        for (i = 0; i < CLEANUP_WORDS; i++)
            hal_mem_wr(CMD_BUF + 4u * i, clean[i]);
        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, CLEANUP_WORDS, 0u, poll_limit, &sts, &polls);
        res_wr(base + R_STS_CLEAN, sts); res_wr(base + R_POLLS_CLEAN, polls);
    }
    res_wr(base + R_STATUS_AFTER, hal_rd(DEVCFG_STATUS));

    for (i = 0; i < READ_WORDS; i++) {                  /* the raw words, whatever happened */
        w = hal_mem_rd(DST_BUF + 4u * i);
        res_wr(base + R_STREAM + STREAM_WORDS + CLEANUP_WORDS + i, w);
        if (w == SENTINEL)
            survivors++;
    }
    res_wr(base + R_SURVIVORS, survivors);

    if (code == C_OK && !(hal_rd(DEVCFG_INT_STS) & STS_PCFG_DONE))
        code = C_DONE_DROPPED;
    if (code == C_OK && survivors != 0u)
        code = C_SURVIVORS;
    if (code == C_OK) {
        for (i = 0; i < FRAME_WORDS; i++)
            if (res_rd(base + R_STREAM + STREAM_WORDS + CLEANUP_WORDS + i) != 0u) {
                code = C_PAD_NONZERO;
                break;
            }
    }
    res_wr(base + R_CODE, code);
    return code;
}

/* are the frame halves of two records equal? */
static int same_frame(uint32_t rec_a, uint32_t rec_b)
{
    uint32_t a = HDR_WORDS + rec_a * REC_WORDS + R_STREAM + STREAM_WORDS + CLEANUP_WORDS + FRAME_WORDS;
    uint32_t b = HDR_WORDS + rec_b * REC_WORDS + R_STREAM + STREAM_WORDS + CLEANUP_WORDS + FRAME_WORDS;
    uint32_t i;
    for (i = 0; i < FRAME_WORDS; i++)
        if (res_rd(a + i) != res_rd(b + i))
            return 0;
    return 1;
}

static uint32_t finish(uint32_t status, uint32_t n_records, uint32_t n_anomalies, uint32_t stop_record)
{
    res_wr(H_STATUS, status);
    if (status == S_BAD_PARAMS) {                       /* refused on form alone: no device register is even read */
        put("SM1 end status="); puthex(status); put("\r\n");
        res_wr(H_TOTAL_WORDS, HDR_WORDS);
        return status;
    }
    res_wr(H_N_RECORDS, n_records);
    res_wr(H_N_ANOMALIES, n_anomalies);
    res_wr(H_TOTAL_WORDS, HDR_WORDS + n_records * REC_WORDS);
    res_wr(H_STOP_RECORD, stop_record);
    res_wr(H_INT_STS1, hal_rd(DEVCFG_INT_STS));
    res_wr(H_STATUS1, hal_rd(DEVCFG_STATUS));
    put("SM1 end status="); puthex(status);
    put(" records="); puthex(n_records);
    put(" anomalies="); puthex(n_anomalies);
    put(" words="); puthex(HDR_WORDS + n_records * REC_WORDS);
    put("\r\n");
    return status == S_DONE ? 0u : status;
}

/* ================================================================== stages 2 (S1b.0) and 3 (S1b.0b)
 * Each operation reads n frames in one FDRO read and then, in the same session, the FAR register.
 * The record layout differs from stage 1 (REC2_WORDS); the header is the same.
 * Stage 3 differs from stage 2 only in which operations its parameters may ask for: also the pad alone
 * (a count of 0) and no FDRO read at all (N_NONE), to see what the FAR register holds after each. */
/* where the records begin: after the header — and in stage 7 after the PL block, which is counted with the header */
static uint32_t log9(void);
static uint32_t rbase(void)
{
    if (par(P_STAGE) == 9u)
        return HDR_WORDS + PLB_LOG + 2u * log9();
    return par(P_STAGE) == 7u ? HDR_WORDS + PLB_WORDS : par(P_STAGE) == 8u ? HDR_WORDS + PLB8_WORDS : HDR_WORDS;
}
static void r2_wr(uint32_t rec, uint32_t field, uint32_t v) { res_wr(rbase() + rec * REC2_WORDS + field, v); }
static uint32_t r2_rd(uint32_t rec, uint32_t field)         { return res_rd(rbase() + rec * REC2_WORDS + field); }

/* which register an operation reads after its frame read: in stages 6 and 7 the one the host's table names for a
 * target operation; in every other stage, and for every reference read, the FAR register */
static uint32_t reg_of(uint32_t op)
{
    uint32_t stage = par(P_STAGE);
    if (stage == 8u || stage == 9u)                     /* its one read of another register, and no table */
        return op == OP8_CTL0 ? REG_CTL0 : REG_FAR;
    if ((stage != 6u && stage != 7u) || op >= MAX_REG_OPS)
        return REG_FAR;
    return (par(P_REGS) >> (4u * op)) & 0xFu;
}

static uint32_t read_op(uint32_t rec, uint32_t far, uint32_t n, uint32_t kind, uint32_t repeat, uint32_t op,
                        uint32_t far_lo, uint32_t far_hi, uint32_t poll_limit)
{
    uint32_t stream[STREAM_WORDS], farrd[FARRD_WORDS], clean[CLEANUP_WORDS];
    uint32_t words = (n == N_NONE) ? 0u : FRAME_WORDS * (n + 1u), i, code, g, sts = 0u, polls = 0u, survivors = 0u, w, value;

    for (i = 0; i < REC2_WORDS; i++)
        r2_wr(rec, i, 0u);
    r2_wr(rec, R_FAR, far);
    r2_wr(rec, R_KIND, kind);
    r2_wr(rec, R_REPEAT, repeat);
    r2_wr(rec, R_REF_EQUAL, 0xFFFFFFFFu);
    r2_wr(rec, R_NFRAMES, n);
    r2_wr(rec, R_OP, op);
    r2_wr(rec, REC2_FARBLK + F_POLL_VAR, (uint32_t)(uintptr_t)&sts);   /* the polling loop stores to it and to its neighbour on every poll */
    hal_watch(&polls);

    sm_frames_stream(far, n, stream);
    sm_reg_read_stream(reg_of(op), farrd);
    sm_cleanup_stream(clean);
    g = sm_guard(stream, STREAM_WORDS, far_lo, far_hi, words);
    if (g == 0u)
        g = sm_guard(farrd, FARRD_WORDS, far_lo, far_hi, words);
    if (g == 0u)
        g = sm_guard(clean, CLEANUP_WORDS, far_lo, far_hi, words);
    r2_wr(rec, R_GUARD, g);
    for (i = 0; i < STREAM_WORDS; i++)
        r2_wr(rec, R_STREAM + i, stream[i]);
    for (i = 0; i < FARRD_WORDS; i++)
        r2_wr(rec, R_STREAM + STREAM_WORDS + i, farrd[i]);
    for (i = 0; i < CLEANUP_WORDS; i++)
        r2_wr(rec, R_STREAM + STREAM_WORDS + FARRD_WORDS + i, clean[i]);
    if (g != 0u) {
        r2_wr(rec, R_CODE, C_GUARD);
        return C_GUARD;
    }

    for (i = 0; i < STREAM_WORDS; i++)
        hal_mem_wr(CMD_BUF + 4u * i, stream[i]);
    for (i = 0; i < words; i++)
        hal_mem_wr(DST_BUF + 4u * i, SENTINEL);

    code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, STREAM_WORDS, 0u, poll_limit, &sts, &polls);
    r2_wr(rec, R_STS_CMD, sts); r2_wr(rec, R_POLLS_CMD, polls);
    if (code == C_OK && words != 0u) {                  /* with nothing to read there is no read command */
        code = dma(PCAP_ENDPOINT, DST_BUF | DMA_HOLD_TAG, 0u, words, poll_limit, &sts, &polls);
        r2_wr(rec, R_STS_READ, sts); r2_wr(rec, R_POLLS_READ, polls);
    }
    for (i = 0; i < words; i++) {                       /* the raw words, whatever happened */
        w = hal_mem_rd(DST_BUF + 4u * i);
        r2_wr(rec, REC2_DATA + i, w);
        if (w == SENTINEL)
            survivors++;
    }
    r2_wr(rec, R_SURVIVORS, survivors);

    if (code == C_OK) {                                 /* the FAR register, as this read left it */
        for (i = 0; i < FARRD_WORDS; i++)
            hal_mem_wr(CMD_BUF + 4u * i, farrd[i]);
        hal_mem_wr(DST_BUF, SENTINEL);
        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, FARRD_WORDS, 0u, poll_limit, &sts, &polls);
        r2_wr(rec, REC2_FARBLK + F_STS_CMD, sts); r2_wr(rec, REC2_FARBLK + F_POLLS_CMD, polls);
        if (code == C_OK) {
            code = dma(PCAP_ENDPOINT, DST_BUF | DMA_HOLD_TAG, 0u, 1u, poll_limit, &sts, &polls);
            r2_wr(rec, REC2_FARBLK + F_STS_READ, sts); r2_wr(rec, REC2_FARBLK + F_POLLS_READ, polls);
            value = hal_mem_rd(DST_BUF);
            r2_wr(rec, REC2_FARBLK + F_VALUE, value);
            r2_wr(rec, REC2_FARBLK + F_UNREAD, value == SENTINEL ? 1u : 0u);
        }
    }
    if (code == C_OK) {                                 /* leave the engine desynchronised */
        for (i = 0; i < CLEANUP_WORDS; i++)
            hal_mem_wr(CMD_BUF + 4u * i, clean[i]);
        code = dma(CMD_BUF | DMA_HOLD_TAG, PCAP_ENDPOINT, CLEANUP_WORDS, 0u, poll_limit, &sts, &polls);
        r2_wr(rec, R_STS_CLEAN, sts); r2_wr(rec, R_POLLS_CLEAN, polls);
    }
    r2_wr(rec, R_STATUS_AFTER, hal_rd(DEVCFG_STATUS));

    if (code == C_OK && !(hal_rd(DEVCFG_INT_STS) & STS_PCFG_DONE))
        code = C_DONE_DROPPED;
    if (code == C_OK && survivors != 0u)
        code = C_SURVIVORS;
    if (code == C_OK && words != 0u) {
        for (i = 0; i < FRAME_WORDS; i++)
            if (r2_rd(rec, REC2_DATA + i) != 0u) {
                code = C_PAD_NONZERO;
                break;
            }
    }
    if (code == C_OK && r2_rd(rec, REC2_FARBLK + F_UNREAD))
        code = C_FAR_UNREAD;
    r2_wr(rec, R_CODE, code);
    return code;
}

/* diagnostics: the same read with `extra` more words of stack beneath it — nothing else differs */
static uint32_t read_deep(uint32_t extra, uint32_t rec, uint32_t far, uint32_t n, uint32_t kind, uint32_t repeat, uint32_t op,
                          uint32_t far_lo, uint32_t far_hi, uint32_t poll_limit)
{
    volatile uint32_t pad[extra];
    uint32_t v;

    pad[0] = extra;
    v = read_op(rec, far, n, kind, repeat, op, far_lo, far_hi, poll_limit);
    pad[extra - 1u] = v;
    return pad[extra - 1u];
}

/* a reference read that did not hold: if it failed on the interface, that is what stopped the run;
 * only otherwise has the reference frame changed */
static uint32_t health_stop(uint32_t rec)
{
    uint32_t code = r2_rd(rec, R_CODE);
    return IS_INTERFACE(code) ? (S_STOP_INTERFACE | code) : S_STOP_HEALTH;
}

/* are the first n frames after the pad equal in two stage-2 records? */
static int same_data(uint32_t rec_a, uint32_t rec_b, uint32_t n)
{
    uint32_t i;
    if (n == N_NONE)
        return 1;                                       /* nothing was read: nothing can differ */
    for (i = FRAME_WORDS; i < FRAME_WORDS * (n + 1u); i++)
        if (r2_rd(rec_a, REC2_DATA + i) != r2_rd(rec_b, REC2_DATA + i))
            return 0;
    return 1;
}

/* a reference read is healthy if it is clean and equals the baseline, frame and FAR value alike */
static uint32_t ref_healthy(uint32_t rec, uint32_t code)
{
    return (code == C_OK && same_data(0u, rec, 1u)
            && r2_rd(rec, REC2_FARBLK + F_VALUE) == r2_rd(0u, REC2_FARBLK + F_VALUE)) ? 1u : 0u;
}

/* "SM2" to "SM8": the stage is read from the parameter block each time, there is no static to keep it in */
static void tag(void)
{
    put("SM");
    hal_putc(par(P_STAGE) == 9u ? '9' : par(P_STAGE) == 8u ? '8' : par(P_STAGE) == 7u ? '7' : par(P_STAGE) == 6u ? '6' : par(P_STAGE) == 5u ? '5' : par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');
}

static uint32_t finish2(uint32_t status, uint32_t n_records, uint32_t n_anomalies, uint32_t stop_record)
{
    res_wr(H_STATUS, status);
    if (status == S_BAD_PARAMS) {
        tag(); put(" end status="); puthex(status); put("\r\n");
        res_wr(H_TOTAL_WORDS, rbase());
        return status;
    }
    res_wr(H_N_RECORDS, n_records);
    res_wr(H_N_ANOMALIES, n_anomalies);
    res_wr(H_TOTAL_WORDS, rbase() + n_records * REC2_WORDS);
    res_wr(H_STOP_RECORD, stop_record);
    res_wr(H_INT_STS1, hal_rd(DEVCFG_INT_STS));
    res_wr(H_STATUS1, hal_rd(DEVCFG_STATUS));
    tag(); put(" end status="); puthex(status);
    put(" records="); puthex(n_records);
    put(" anomalies="); puthex(n_anomalies);
    put(" words="); puthex(rbase() + n_records * REC2_WORDS);
    put("\r\n");
    return status == S_DONE ? 0u : status;
}

/* ================================================================== stage 7 (S2.1): user logic
 * Every access to the PL goes through pl_rd and pl_wr, and through nothing else. They refuse an address that is not
 * a register of the design, lies outside the envelope the host gave, or — for a write — is not one of the four this
 * prober may write; a refused access is not made. Every access made is logged in the PL block of the result, in
 * order: the address (bit 0 set for a write) and the value read or written. After the first thing that is not as
 * the design must answer, nothing more is accessed. */
static void plb_wr(uint32_t i, uint32_t v) { res_wr(HDR_WORDS + i, v); }
static uint32_t plb_rd(uint32_t i)         { return res_rd(HDR_WORDS + i); }

static uint32_t pl_fail(uint32_t code)
{
    if (plb_rd(PLB_CODE) == PLC_OK) {                   /* the first failure is the one that is kept */
        plb_wr(PLB_CODE, code);
        plb_wr(PLB_AT, plb_rd(PLB_N));
    }
    return code;
}

/* The address of the design's register at an offset, if this run may make that access; 0 if it may not. This is the
 * one place where an address of the PL is formed: pl_access takes it from here, and so does the check of a list of
 * stage 9 before anything is touched (it asks only whether the answer is 0). Kept a function of its own for that. */
static __attribute__((noinline)) uint32_t pl_addr(uint32_t off, int write)
{
    uint32_t a = PL_BASE + off;
    if (off >= PL_SPAN || (off & 3u) || a < par(P_PL_LO) || a > par(P_PL_HI))
        return 0u;
    if (write && !(((par(P_STAGE) == 9u ? par(P_PL_WRITE) & PL_WRITABLE9 : PL_WRITABLE) >> off) & 1u))
        return 0u;
    return a;
}

/* stage 9: how many accesses the log has room for — the identification register, and every entry of the host's list
 * that is not a mark. Zero for a block whose counts cannot be: nothing is logged then, and nothing is made. */
static uint32_t log9(void)
{
    uint32_t n = par(P_ACC_N), s = par(P_REPEATS);
    return (s == 0u || s > MAX9_STATES || n > ACC_MAX || n < 2u * s) ? 0u : 1u + n - 2u * s;
}

static uint32_t pl_access(uint32_t off, int write, uint32_t value)
{
    uint32_t n = plb_rd(PLB_N), a = pl_addr(off, write);
    if (plb_rd(PLB_CODE) != PLC_OK)
        return 0u;                                      /* stopped: nothing more is accessed */
    if (!a) {
        pl_fail(PLC_REFUSED);
        return 0u;
    }
    if (n >= (par(P_STAGE) == 9u ? log9() : par(P_STAGE) == 8u ? PL8_LOG_MAX : PL_LOG_MAX)) {
        pl_fail(PLC_FULL);
        return 0u;
    }
    if (write)
        hal_wr(a, value);
    else
        value = hal_rd(a);
    plb_wr(PLB_LOG + 2u * n, a | (write ? 1u : 0u));
    plb_wr(PLB_LOG + 2u * n + 1u, value);
    plb_wr(PLB_N, n + 1u);
    return value;
}
static uint32_t pl_rd(uint32_t off)             { return pl_access(off, 0, 0u); }
static void     pl_wr(uint32_t off, uint32_t v) { (void)pl_access(off, 1, v); }

/* what a state puts at an address of the LUT RAM: four bits, one for each of the four memories */
static uint32_t ram_pattern(uint32_t state, uint32_t a)
{
    return state == 0u ? 0u : state == 1u ? 0xFu : state == 2u ? (a & 0xFu) : (~a & 0xFu);
}

static uint32_t pl_sequence(void)
{
    uint32_t i, s, a, v, first;

    /* 1. the identification register */
    v = pl_rd(PL_ID);
    if (plb_rd(PLB_CODE) == PLC_OK && v != par(P_PL_ID))
        return pl_fail(PLC_ID);
    /* 2. the scratch register: four words written and read back */
    for (i = 0; i < 4u; i++) {
        s = i == 0u ? 0u : i == 1u ? 0xFFFFFFFFu : i == 2u ? SENTINEL : ~SENTINEL;
        pl_wr(PL_SCRATCH, s);
        v = pl_rd(PL_SCRATCH);
        if (plb_rd(PLB_CODE) == PLC_OK && v != s)
            return pl_fail(PLC_SCRATCH);
    }
    /* 3. the counter: two reads differ if the clock runs */
    v = pl_rd(PL_COUNT);
    a = pl_rd(PL_COUNT);
    if (plb_rd(PLB_CODE) == PLC_OK && v == a)
        return pl_fail(PLC_COUNT);
    /* 4. the LUT RAM from the design's side: each state written to all addresses, then all read back */
    for (s = 0; s < RAM_STATES; s++) {
        for (a = 0; a < RAM_DEPTH; a++) {
            pl_wr(PL_RAM_ADDR, a);
            pl_wr(PL_RAM_DATA, ram_pattern(s, a));
        }
        for (a = 0; a < RAM_DEPTH; a++) {
            pl_wr(PL_RAM_ADDR, a);
            v = pl_rd(PL_RAM_DATA);
            if (plb_rd(PLB_CODE) == PLC_OK && v != ram_pattern(s, a))
                return pl_fail(PLC_RAM);
        }
    }
    /* 5. the shift registers, which nothing here shifts: their outputs at every address, twice, alike */
    first = plb_rd(PLB_N);
    for (s = 0; s < 2u; s++)
        for (a = 0; a < SRL_DEPTH; a++) {
            pl_wr(PL_SRL_ADDR, a);
            v = pl_rd(PL_SRL_DATA);
            if (plb_rd(PLB_CODE) == PLC_OK && s == 1u && v != plb_rd(PLB_LOG + 2u * (first + 2u * a + 1u) + 1u))
                return pl_fail(PLC_SRL);
        }
    /* 6. the design's own count: as many RAM writes as were made above, and no shift */
    v = pl_rd(PL_WRITES);
    if (plb_rd(PLB_CODE) == PLC_OK && v != RAM_STATES * RAM_DEPTH)
        return pl_fail(PLC_WRITES);
    return plb_rd(PLB_CODE);
}

static uint32_t slcr_addr(uint32_t k)
{
    return k == 0u ? SLCR_LVL_SHFTR_EN : k == 1u ? SLCR_FPGA_RST_CTRL : k == 2u ? SLCR_FPGA0_CLK : SLCR_PLL_STATUS;
}

static uint32_t op_frames(uint32_t k)
{
    return (par(k < 8u ? P_NFRAMES_LO : P_NFRAMES_HI) >> (4u * (k & 7u))) & 0xFu;
}

/* stage 5 with a generated sequence: operations 2j and 2j+1 are the pad alone and the frame at the j-th address */
static uint32_t op_far(uint32_t k, uint32_t seq) { return seq ? par(P_FARS) + (k >> 1) : par(P_FARS + k); }
static uint32_t op_n(uint32_t k, uint32_t seq)   { return seq ? (k & 1u) : op_frames(k); }

static uint32_t run_s2(void)
{
    uint32_t i, r, k, rec = 0u, anomalies = 0u, code, v, n, far, first;
    uint32_t far_lo, far_hi, ref_far, n_ops, repeats, budget, poll_limit, seq = 0u, extra = 0u;
    int stage5 = par(P_STAGE) == 5u, stage7 = par(P_STAGE) == 7u, regs = stage7 || par(P_STAGE) == 6u;
    int stage3 = stage5 || regs || par(P_STAGE) == 3u; /* stages 6 and 7 may ask for what stage 3 may */

    tag(); put(" start\r\n");
    for (i = 0; i < HDR_WORDS; i++)
        res_wr(i, 0u);
    res_wr(H_MAGIC, RESULT_MAGIC);
    res_wr(H_VERSION, 1u);
    res_wr(H_REC_WORDS, REC2_WORDS);
    res_wr(H_HDR_WORDS, rbase());
    res_wr(H_STOP_RECORD, 0xFFFFFFFFu);
    for (i = 0; i < PARAM_WORDS; i++)
        res_wr(H_PARAMS + i, par(i));
    res_wr(H_SCTLR, hal_cpu(CPU_SCTLR));
    res_wr(H_CPSR, hal_cpu(CPU_CPSR));
    res_wr(H_SP, hal_cpu(CPU_SP));
    res_wr(H_R9, hal_cpu(CPU_R9));
    if (stage7) {                                       /* the PL block: empty, and saying so */
        for (i = 0; i < PLB_WORDS; i++)
            plb_wr(i, 0u);
        plb_wr(PLB_MAGIC, PLB_MAGIC_VALUE);
        plb_wr(PLB_AT, 0xFFFFFFFFu);
    }

    far_lo = par(P_FAR_LO); far_hi = par(P_FAR_HI); ref_far = par(P_REF_FAR);
    n_ops = par(P_N_FARS); repeats = par(P_REPEATS); budget = par(P_ANOMALY_BUDGET); poll_limit = par(P_POLL_LIMIT);
    if (par(P_VERSION) != 1u || far_lo > far_hi || ref_far < far_lo || ref_far > far_hi
        || n_ops == 0u || n_ops > MAX_FARS || repeats == 0u || repeats > MAX_REPEATS
        || budget > 64u || poll_limit == 0u || poll_limit > 0x10000000u)
        return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
    if (regs) {
        /* at most eight operations, each with a register from the list; no word of the table beyond them; no
         * diagnostic option but the choice of the wait; and every word these stages have no use for is zero */
        if (n_ops > MAX_REG_OPS || poll_mode() > POLL_NO_STACK || (par(P_DIAG_STACK) & 0xFFu) || par(P_DIAG_SEQ)
            || par(P_HEALTH_EVERY) || par(P_NFRAMES_HI) || par(P_PL_ID + 1u))
            return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        for (k = 0; k < MAX_REG_OPS; k++) {
            v = (par(P_REGS) >> (4u * k)) & 0xFu;
            if (k < n_ops ? v >= N_REGS : (v != 0u || op_frames(k) != 0u || par(P_FARS + k) != 0u))
                return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        }
        if (stage7) {
            if (par(P_PL_LO) < PL_BASE || par(P_PL_LO) > par(P_PL_HI) || par(P_PL_HI) >= PL_BASE + PL_SPAN)
                return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        } else {
            for (k = P_PL_LO; k < PARAM_WORDS; k++)
                if (par(k))
                    return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        }
    }
    if (stage5) {
        seq = par(P_DIAG_SEQ); extra = par(P_DIAG_STACK) & 0xFFu;
        if (seq > MAX_DIAG_SEQ || extra > MAX_DIAG_STACK || poll_mode() > POLL_NO_STACK || (seq != 0u && (n_ops != 1u || repeats > 2u)))
            return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        if (seq != 0u) {
            /* the sequence must end at or below the top of the envelope, and that is settled by subtraction: the
             * addresses are 32-bit sums, and one past 0xffffffff would come back as 0, inside a wide enough envelope.
             * (A first address above the top makes the difference meaningless; the loop below refuses it at once.) */
            if (seq - 1u > far_hi - par(P_FARS))
                return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
            n_ops = 2u * seq;                           /* each address of the sequence is checked like any other, just below */
        }
    }
    for (k = 0; k < n_ops; k++) {
        far = op_far(k, seq); n = op_n(k, seq);
        if (far < far_lo || far > far_hi)
            return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
        if (stage3 && (n == 0u || n == N_NONE))         /* the pad alone, or no read: no frame is delivered, the address is enough */
            continue;
        if (n == 0u || n > MAX_READ_FRAMES || n - 1u > far_hi - far)
            return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
    }

    v = hal_rd(DEVCFG_CTRL);   res_wr(H_CTRL, v);
    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)
        return finish2(S_GATE_CTRL, 0u, 0u, 0xFFFFFFFFu);
    if (regs && (v & CTRL_SEU_EN))                      /* with it set, a status bit these stages may raise locks the PS */
        return finish2(S_GATE_SEU, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_MCTRL);  res_wr(H_MCTRL, v);
    if (v & MCTRL_PCAP_LPBK)
        return finish2(S_GATE_LPBK, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, v);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!(v & STS_PCFG_DONE))
        return finish2(S_GATE_NOT_DONE, 0u, 0u, 0xFFFFFFFFu);
    if (hal_cpu(CPU_SCTLR) & 0x4u)
        return finish2(S_GATE_DCACHE, 0u, 0u, 0xFFFFFFFFu);
    if (stage7) {
        /* the PS side of the PL: level shifters, resets, the clock and the PLLs, each as the host says this board
         * has them. All four are read and recorded; the first that differs stops the run before the PL is touched. */
        for (k = 0; k < N_SLCR; k++)
            plb_wr(PLB_SLCR + k, hal_rd(slcr_addr(k)));
        for (k = 0; k < N_SLCR; k++)
            if (plb_rd(PLB_SLCR + k) != par(P_SLCR + k))
                return finish2(S_GATE_SLCR | k, 0u, 0u, 0xFFFFFFFFu);
    }

    code = read_op(rec, ref_far, 1u, KIND_BASELINE, 0u, 0xFFFFFFFFu, far_lo, far_hi, poll_limit);
    rec++;
    if (code != C_OK)
        return finish2(S_STOP_BASELINE | code, rec, 0u, 0u);

    if (stage7) {                                       /* user logic, between the reference frame's first reading and the rest */
        v = pl_sequence();
        if (v != PLC_OK)
            return finish2(S_STOP_PL | v, rec, 0u, 0xFFFFFFFFu);
    }

    for (r = 0; r < repeats; r++) {
        for (k = 0; k < n_ops; k++) {
            far = op_far(k, seq); n = op_n(k, seq);
            code = extra ? read_deep(extra, rec, far, n, KIND_TARGET, r, k, far_lo, far_hi, poll_limit)
                         : read_op(rec, far, n, KIND_TARGET, r, k, far_lo, far_hi, poll_limit);
            if (code == C_OK) {                         /* against the first clean run of this same operation */
                first = 0xFFFFFFFFu;
                for (i = 1u; i < rec; i++)
                    if (r2_rd(i, R_KIND) == KIND_TARGET && r2_rd(i, R_OP) == k && r2_rd(i, R_CODE) == C_OK) {
                        first = i;
                        break;
                    }
                if (first != 0xFFFFFFFFu) {
                    if (!same_data(first, rec, n))
                        code = C_REPEAT_DIFFERS;
                    else if (r2_rd(first, REC2_FARBLK + F_VALUE) != r2_rd(rec, REC2_FARBLK + F_VALUE))
                        code = C_FAR_DIFFERS;
                    r2_wr(rec, R_CODE, code);
                }
            }
            rec++;
            if (code == C_OK)
                continue;
            anomalies++;
            if (IS_INTERFACE(code))
                return finish2(S_STOP_INTERFACE | code, rec, anomalies, rec - 1u);
            code = read_op(rec, ref_far, 1u, KIND_HEALTH, r, 0xFFFFFFFFu, far_lo, far_hi, poll_limit);
            v = ref_healthy(rec, code);
            r2_wr(rec, R_REF_EQUAL, v);
            rec++;
            if (!v)
                return finish2(health_stop(rec - 1u), rec, anomalies, rec - 1u);
            if (anomalies > budget)
                return finish2(S_STOP_BUDGET, rec, anomalies, rec - 2u);
        }
    }

    code = read_op(rec, ref_far, 1u, KIND_FINAL, repeats, 0xFFFFFFFFu, far_lo, far_hi, poll_limit);
    v = ref_healthy(rec, code);
    r2_wr(rec, R_REF_EQUAL, v);
    rec++;
    if (!v)
        return finish2(health_stop(rec - 1u), rec, anomalies, rec - 1u);
    return finish2(S_DONE, rec, anomalies, 0xFFFFFFFFu);
}

static uint32_t run_s4(void);
static uint32_t run_s9(void);

/* ================================================================== stage 8 (S2.2): the RAM in readback
 * docs/s2_plan.md, section 19. The gates of stage 7; the reference frame; the design's identification and the
 * outputs of its shift registers, kept for comparison; CTL0. Then, for each state the host names: the RAM written
 * to the state through the design and read back; the counter; every read of the host's list, the status recorded
 * after each and held to what a transfer's status is held to, and bit 5 cleared, alone, where it shows after a read
 * with nothing amiss (what the register reads then is held to the same); the RAM read through the design again —
 * it must still hold the state; the counter, which must have gone on; the shift registers, which must read as before; the design's
 * count of writes. CTL0 and the reference frame again. The first thing that is not so ends the run: nothing is
 * budgeted for, and nothing is read after a RAM that did not hold. */
static uint32_t s8_ram(uint32_t state, uint32_t code)
{
    uint32_t a, x;
    for (a = 0; a < RAM_DEPTH; a++) {
        pl_wr(PL_RAM_ADDR, a);
        x = pl_rd(PL_RAM_DATA);
        if (plb_rd(PLB_CODE) == PLC_OK && x != ram_pattern(state, a))
            return pl_fail(code);
    }
    return plb_rd(PLB_CODE);
}

/* A status word read when no transfer is running — after a read of the list, and after bit 5 was cleared: held to
 * what every transfer's own status is held to. (Review of 0417966: the words were recorded and looked at for bit 5
 * alone; an error bit that appeared once the last transfer was seen done went into the record and the run went on.) */
static uint32_t s8_sts(uint32_t s)
{
    return (s & STS_ERR_MASK) ? C_DEVERR : !(s & STS_PCFG_DONE) ? C_DONE_DROPPED : C_OK;
}

/* One read of stage 8, and the register as the read left it: recorded and held to s8_sts, after every read — of the
 * list, of CTL0 and of the reference frame alike (review of 334df53: after the reads that are not of the list the
 * register was not looked at, and the design was written before the next transfer met the bit). `clear5`: a read of
 * the list, after which bit 5 is cleared, alone, where it shows and nothing is amiss; what the register reads then
 * is recorded and held to the same. The record's code is the read's own, or what the register says. */
static uint32_t s8_read(uint32_t rec, uint32_t far, uint32_t n, uint32_t kind, uint32_t repeat, uint32_t op,
                        uint32_t lo, uint32_t hi, uint32_t limit, uint32_t clear5)
{
    uint32_t code = read_op(rec, far, n, kind, repeat, op, lo, hi, limit), g = hal_rd(DEVCFG_INT_STS);

    r2_wr(rec, REC2_FARBLK + F_STS_AFTER, g);
    if (code == C_OK)
        code = s8_sts(g);
    if (clear5 && code == C_OK && (g & STS_SEU_ERR)) {
        hal_wr(DEVCFG_INT_STS, STS_SEU_ERR);
        g = hal_rd(DEVCFG_INT_STS);
        r2_wr(rec, R8_STS_CLEARED, g);
        code = s8_sts(g);
    }
    r2_wr(rec, R_CODE, code);
    return code;
}

static uint32_t s8_end(uint32_t code, uint32_t rec)     /* a read that was not clean: the status the run ends with */
{
    return finish2(IS_INTERFACE(code) ? (S_STOP_INTERFACE | code) : S_STOP_BUDGET, rec, 1u, rec - 1u);
}

static uint32_t run_s8(void)
{
    uint32_t i, k, s, a, x, w, g, c0, srl0, state, code, rec = 0u;
    uint32_t lo = par(P_FAR_LO), hi = par(P_FAR_HI), ref = par(P_REF_FAR), n_states = par(P_REPEATS);
    uint32_t n_list = par(P_LIST_N), limit = par(P_POLL_LIMIT);

    tag(); put(" start\r\n");
    for (i = 0; i < HDR_WORDS + PLB8_WORDS; i++)
        res_wr(i, 0u);
    res_wr(H_MAGIC, RESULT_MAGIC);
    res_wr(H_VERSION, 1u);
    res_wr(H_REC_WORDS, REC2_WORDS);
    res_wr(H_HDR_WORDS, HDR_WORDS + PLB8_WORDS);
    res_wr(H_STOP_RECORD, 0xFFFFFFFFu);
    for (i = 0; i < PARAM_WORDS; i++)
        res_wr(H_PARAMS + i, par(i));
    for (i = 0; i < 4u; i++)                            /* SCTLR, CPSR, SP, R9: as the header has them */
        res_wr(H_SCTLR + i, hal_cpu((int)i));
    plb_wr(PLB_MAGIC, PLB_MAGIC_VALUE);
    plb_wr(PLB_AT, 0xFFFFFFFFu);

    /* parameters: refused before anything of the device is looked at */
    x = par(P_VERSION) != 1u || lo > hi || ref < lo || ref > hi || n_states == 0u || n_states > MAX_STATES
        || n_list == 0u || n_list > LIST_MAX || limit == 0u || limit > 0x10000000u
        || (par(P_DIAG_STACK) & 0xFFu) || poll_mode() > POLL_NO_STACK || (par(P_STATES) >> (4u * n_states))
        || par(P_PL_LO) < PL_BASE || par(P_PL_LO) > par(P_PL_HI) || par(P_PL_HI) >= PL_BASE + PL_SPAN;
    for (k = 0; k < PARAM_WORDS; k++)
        if (!((P8_USED >> k) & 1u) && par(k))
            x = 1u;
    for (s = 0; s < MAX_STATES; s++)
        if (((par(P_STATES) >> (4u * s)) & 0xFu) > 1u)  /* all zero and all one: this stage has no other state */
            x = 1u;
    for (k = 0; !x && k < n_list; k++) {
        w = hal_mem_rd(LIST_ADDR + 4u * k);
        if (LIST_N(w) == 0u || LIST_N(w) > MAX_READ_FRAMES || LIST_FAR(w) < lo || LIST_FAR(w) > hi || LIST_N(w) - 1u > hi - LIST_FAR(w))
            x = 1u;
    }
    if (x)
        return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);

    /* gates, each read live; the first that fails ends the run with nothing sent and nothing in the PL touched */
    g = hal_rd(DEVCFG_CTRL);    res_wr(H_CTRL, g);
    x = (g & CTRL_PCAP_MASK) != CTRL_PCAP_MASK ? S_GATE_CTRL : (g & CTRL_SEU_EN) ? S_GATE_SEU : 0u;
    g = hal_rd(DEVCFG_MCTRL);   res_wr(H_MCTRL, g);
    if (!x && (g & MCTRL_PCAP_LPBK))
        x = S_GATE_LPBK;
    g = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, g);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!x && !(g & STS_PCFG_DONE))
        x = S_GATE_NOT_DONE;
    if (!x && (hal_cpu(CPU_SCTLR) & 0x4u))
        x = S_GATE_DCACHE;
    for (k = 0; !x && k < N_SLCR; k++)                  /* the PS side of the PL, all four words recorded */
        plb_wr(PLB_SLCR + k, hal_rd(slcr_addr(k)));
    for (k = 0; !x && k < N_SLCR; k++)
        if (plb_rd(PLB_SLCR + k) != par(P_SLCR + k))
            x = S_GATE_SLCR | k;
    if (x)
        return finish2(x, 0u, 0u, 0xFFFFFFFFu);

    code = s8_read(rec, ref, 1u, KIND_BASELINE, 0u, 0xFFFFFFFFu, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return finish2(S_STOP_BASELINE | code, rec, 0u, 0u);

    x = pl_rd(PL_ID);
    if (plb_rd(PLB_CODE) == PLC_OK && x != par(P_PL_ID))
        pl_fail(PLC_ID);
    srl0 = plb_rd(PLB_N);                               /* the shift registers' outputs: this reading is what the later ones are held to */
    for (a = 0; a < SRL_DEPTH; a++) {
        pl_wr(PL_SRL_ADDR, a);
        (void)pl_rd(PL_SRL_DATA);
    }
    if (plb_rd(PLB_CODE) != PLC_OK)
        return finish2(S_STOP_PL | plb_rd(PLB_CODE), rec, 0u, 0xFFFFFFFFu);

    code = s8_read(rec, ref, N_NONE, KIND_TARGET, 0u, OP8_CTL0, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return s8_end(code, rec);

    for (s = 0; s < n_states; s++) {
        state = (par(P_STATES) >> (4u * s)) & 0xFu;
        for (a = 0; a < RAM_DEPTH; a++) {
            pl_wr(PL_RAM_ADDR, a);
            pl_wr(PL_RAM_DATA, ram_pattern(state, a));
        }
        (void)s8_ram(state, PLC_RAM);
        c0 = pl_rd(PL_COUNT);
        if (plb_rd(PLB_CODE) != PLC_OK)
            return finish2(S_STOP_PL | plb_rd(PLB_CODE), rec, 0u, 0xFFFFFFFFu);

        for (k = 0; k < n_list; k++) {
            w = hal_mem_rd(LIST_ADDR + 4u * k);
            code = s8_read(rec, LIST_FAR(w), LIST_N(w), KIND_TARGET, s, k, lo, hi, limit, 1u);
            rec++;
            if (code != C_OK)
                return s8_end(code, rec);
        }

        (void)s8_ram(state, PLC_DISTURBED);             /* question 5: does the RAM still hold what it held before the frames were read */
        x = pl_rd(PL_COUNT);
        if (plb_rd(PLB_CODE) == PLC_OK && x == c0)
            pl_fail(PLC_COUNT);
        for (a = 0; a < SRL_DEPTH; a++) {
            pl_wr(PL_SRL_ADDR, a);
            x = pl_rd(PL_SRL_DATA);
            if (plb_rd(PLB_CODE) == PLC_OK && x != plb_rd(PLB_LOG + 2u * (srl0 + 2u * a + 1u) + 1u))
                pl_fail(PLC_SRL);
        }
        x = pl_rd(PL_WRITES);
        if (plb_rd(PLB_CODE) == PLC_OK && x != (s + 1u) * RAM_DEPTH)
            pl_fail(PLC_WRITES);
        if (plb_rd(PLB_CODE) != PLC_OK)
            return finish2(S_STOP_PL | plb_rd(PLB_CODE), rec, 0u, 0xFFFFFFFFu);
    }

    code = s8_read(rec, ref, N_NONE, KIND_TARGET, n_states, OP8_CTL0, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return s8_end(code, rec);
    code = s8_read(rec, ref, 1u, KIND_FINAL, n_states, 0xFFFFFFFFu, lo, hi, limit, 0u);
    x = ref_healthy(rec, code);
    r2_wr(rec, R_REF_EQUAL, x);
    rec++;
    if (!x)
        return finish2(health_stop(rec - 1u), rec, 0u, rec - 1u);
    return finish2(S_DONE, rec, 0u, 0xFFFFFFFFu);
}

/* ================================================================== stage 9 (S2.3): which bit is which cell
 * docs/s2_plan.md, section 29. Stage 8 with no state of its own: what is written to the design, what is read from
 * it and what a reading must be is the host's list of accesses (sm.h), made here entry by entry. The gates, the
 * reference frame, the design's identification, CTL0; then for each state the entries up to the mark, every read of
 * the list of reads — the status after each as in stage 8, bit 5 cleared alone where it shows — and the entries up to
 * the state's end; CTL0 and the reference frame. A reading that is not what the list says ends the run. */
static uint32_t acc_word(uint32_t entry, uint32_t which) { return hal_mem_rd(ACC_ADDR + 8u * entry + 4u * which); }

static uint32_t run_s9(void)
{
    uint32_t i, k, s, w, v, g, x, at, phase, code, rec = 0u;
    uint32_t lo = par(P_FAR_LO), hi = par(P_FAR_HI), ref = par(P_REF_FAR), n_states = par(P_REPEATS);
    uint32_t n_list = par(P_LIST_N), n_acc = par(P_ACC_N), limit = par(P_POLL_LIMIT);

    tag(); put(" start\r\n");
    /* the header, the PL block and its log. The log's length is the block's word, and a block that is refused is still
     * answered with a result of that length: so it is cleared here, before the block is looked at, and not after — no
     * word of a result is one this run did not write (review of 5936a8e). log9() is bounded whatever the block holds. */
    for (i = 0; i < rbase(); i++)
        res_wr(i, 0u);
    res_wr(H_MAGIC, RESULT_MAGIC);
    res_wr(H_VERSION, 1u);
    res_wr(H_REC_WORDS, REC2_WORDS);
    res_wr(H_HDR_WORDS, rbase());
    res_wr(H_STOP_RECORD, 0xFFFFFFFFu);
    for (i = 0; i < PARAM_WORDS; i++)
        res_wr(H_PARAMS + i, par(i));
    for (i = 0; i < 4u; i++)                            /* SCTLR, CPSR, SP, R9: as the header has them */
        res_wr(H_SCTLR + i, hal_cpu((int)i));
    plb_wr(PLB_MAGIC, PLB_MAGIC_VALUE);
    plb_wr(PLB_AT, 0xFFFFFFFFu);

    /* parameters and both lists: refused before anything of the device is looked at */
    x = par(P_VERSION) != 1u || lo > hi || ref < lo || ref > hi || log9() == 0u
        || n_list == 0u || n_list > LIST_MAX || limit == 0u || limit > 0x10000000u
        || (par(P_DIAG_STACK) & 0xFFu) || poll_mode() > POLL_NO_STACK || (par(P_PL_WRITE) & ~PL_WRITABLE9)
        || par(P_PL_LO) < PL_BASE || par(P_PL_LO) > par(P_PL_HI) || par(P_PL_HI) >= PL_BASE + PL_SPAN;
    if (!x && rbase() + (4u + n_states * n_list) * REC2_WORDS > RESULT_MAX_WORDS)
        x = 1u;                                         /* the result would not lie in its area */
    for (k = 0; k < PARAM_WORDS; k++)
        if (!((P9_USED >> k) & 1u) && par(k))
            x = 1u;
    for (k = 0; !x && k < n_list; k++) {
        w = hal_mem_rd(LIST_ADDR + 4u * k);
        if (LIST_N(w) == 0u || LIST_N(w) > MAX_READ_FRAMES || LIST_FAR(w) < lo || LIST_FAR(w) > hi || LIST_N(w) - 1u > hi - LIST_FAR(w))
            x = 1u;
    }
    s = 0u; phase = 0u;                                 /* the list of accesses: n_states times entries, a mark, entries, a mark */
    for (k = 0; !x && k < n_acc; k++) {
        w = acc_word(k, 0u); v = acc_word(k, 1u);
        if (s >= n_states)
            x = 1u;                                     /* something after the last state's end */
        else if (A_KIND(w) == A_MARK) {
            if (A_OFF(w) || v != phase)                 /* MARK_FRAMES closes the entries before the frames, MARK_END those after */
                x = 1u;
            else if (phase) { phase = 0u; s++; }
            else phase = 1u;
        } else if (!pl_addr(A_OFF(w), A_KIND(w) == A_WRITE) || (A_KIND(w) == A_READ && v))
            x = 1u;
    }
    if (!x && (s != n_states || phase))
        x = 1u;
    if (x)
        return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);

    /* gates, each read live; the first that fails ends the run with nothing sent and nothing in the PL touched */
    g = hal_rd(DEVCFG_CTRL);    res_wr(H_CTRL, g);
    x = (g & CTRL_PCAP_MASK) != CTRL_PCAP_MASK ? S_GATE_CTRL : (g & CTRL_SEU_EN) ? S_GATE_SEU : 0u;
    g = hal_rd(DEVCFG_MCTRL);   res_wr(H_MCTRL, g);
    if (!x && (g & MCTRL_PCAP_LPBK))
        x = S_GATE_LPBK;
    g = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, g);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!x && !(g & STS_PCFG_DONE))
        x = S_GATE_NOT_DONE;
    if (!x && (hal_cpu(CPU_SCTLR) & 0x4u))
        x = S_GATE_DCACHE;
    for (k = 0; !x && k < N_SLCR; k++)                  /* the PS side of the PL, all four words recorded */
        plb_wr(PLB_SLCR + k, hal_rd(slcr_addr(k)));
    for (k = 0; !x && k < N_SLCR; k++)
        if (plb_rd(PLB_SLCR + k) != par(P_SLCR + k))
            x = S_GATE_SLCR | k;
    if (x)
        return finish2(x, 0u, 0u, 0xFFFFFFFFu);

    code = s8_read(rec, ref, 1u, KIND_BASELINE, 0u, 0xFFFFFFFFu, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return finish2(S_STOP_BASELINE | code, rec, 0u, 0u);

    x = pl_rd(PL_ID);                                   /* the one access that is not the list's: is it the design */
    if (plb_rd(PLB_CODE) == PLC_OK && x != par(P_PL_ID))
        pl_fail(PLC_ID);
    if (plb_rd(PLB_CODE) != PLC_OK)
        return finish2(S_STOP_PL | plb_rd(PLB_CODE), rec, 0u, 0xFFFFFFFFu);

    code = s8_read(rec, ref, N_NONE, KIND_TARGET, 0u, OP8_CTL0, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return s8_end(code, rec);

    at = 0u;
    for (s = 0; s < n_states; s++)
        for (phase = 0; phase < 2u; phase++) {
            while (at < n_acc) {                        /* never past the end of the list, whatever the check above let through */
                w = acc_word(at, 0u); v = acc_word(at, 1u);
                at++;
                if (A_KIND(w) == A_MARK)
                    break;
                if (A_KIND(w) == A_WRITE)
                    pl_wr(A_OFF(w), v);
                else {
                    g = pl_rd(A_OFF(w));
                    if (A_KIND(w) == A_EXPECT && plb_rd(PLB_CODE) == PLC_OK && g != v)
                        pl_fail(phase ? PLC_EXPECT_AFTER : PLC_EXPECT);
                }
            }
            if (plb_rd(PLB_CODE) != PLC_OK)
                return finish2(S_STOP_PL | plb_rd(PLB_CODE), rec, 0u, 0xFFFFFFFFu);
            for (k = 0; !phase && k < n_list; k++) {
                w = hal_mem_rd(LIST_ADDR + 4u * k);
                code = s8_read(rec, LIST_FAR(w), LIST_N(w), KIND_TARGET, s, k, lo, hi, limit, 1u);
                rec++;
                if (code != C_OK)
                    return s8_end(code, rec);
            }
        }

    code = s8_read(rec, ref, N_NONE, KIND_TARGET, n_states, OP8_CTL0, lo, hi, limit, 0u);
    rec++;
    if (code != C_OK)
        return s8_end(code, rec);
    code = s8_read(rec, ref, 1u, KIND_FINAL, n_states, 0xFFFFFFFFu, lo, hi, limit, 0u);
    x = ref_healthy(rec, code);
    r2_wr(rec, R_REF_EQUAL, x);
    rec++;
    if (!x)
        return finish2(health_stop(rec - 1u), rec, 0u, rec - 1u);
    return finish2(S_DONE, rec, 0u, 0xFFFFFFFFu);
}

/* ------------------------------------------------------------------ stage S1a */
uint32_t sm_run(void)
{
    uint32_t i, r, k, rec = 0u, anomalies = 0u, code, v;
    uint32_t far_lo, far_hi, ref_far, n_fars, repeats, budget, poll_limit, far, first;

    if (par(P_MAGIC) == PARAM_MAGIC && (par(P_STAGE) == 2u || par(P_STAGE) == 3u || (par(P_STAGE) >= 5u && par(P_STAGE) <= 7u)))
        return run_s2();
    if (par(P_MAGIC) == PARAM_MAGIC && par(P_STAGE) == 4u)
        return run_s4();
    if (par(P_MAGIC) == PARAM_MAGIC && par(P_STAGE) == 8u)
        return run_s8();
    if (par(P_MAGIC) == PARAM_MAGIC && par(P_STAGE) == 9u)
        return run_s9();
    put("SM1 start\r\n");
    for (i = 0; i < HDR_WORDS; i++)
        res_wr(i, 0u);
    res_wr(H_MAGIC, RESULT_MAGIC);
    res_wr(H_VERSION, 1u);
    res_wr(H_REC_WORDS, REC_WORDS);
    res_wr(H_HDR_WORDS, HDR_WORDS);
    res_wr(H_STOP_RECORD, 0xFFFFFFFFu);
    for (i = 0; i < PARAM_WORDS; i++)
        res_wr(H_PARAMS + i, par(i));
    res_wr(H_SCTLR, hal_cpu(CPU_SCTLR));
    res_wr(H_CPSR, hal_cpu(CPU_CPSR));
    res_wr(H_SP, hal_cpu(CPU_SP));
    res_wr(H_R9, hal_cpu(CPU_R9));

    /* parameters: refuse anything out of form before looking at the device */
    far_lo = par(P_FAR_LO); far_hi = par(P_FAR_HI); ref_far = par(P_REF_FAR);
    n_fars = par(P_N_FARS); repeats = par(P_REPEATS); budget = par(P_ANOMALY_BUDGET); poll_limit = par(P_POLL_LIMIT);
    if (par(P_MAGIC) != PARAM_MAGIC || par(P_VERSION) != 1u || par(P_STAGE) != 1u
        || far_lo > far_hi || ref_far < far_lo || ref_far > far_hi
        || n_fars == 0u || n_fars > MAX_FARS || repeats == 0u || repeats > MAX_REPEATS
        || budget > 64u || poll_limit == 0u || poll_limit > 0x10000000u)
        return finish(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
    for (i = 0; i < n_fars; i++) {
        v = par(P_FARS + i);
        if (v < far_lo || v > far_hi)
            return finish(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
    }

    /* gates: each read live; a failure sends nothing */
    v = hal_rd(DEVCFG_CTRL);   res_wr(H_CTRL, v);
    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)
        return finish(S_GATE_CTRL, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_MCTRL);  res_wr(H_MCTRL, v);
    if (v & MCTRL_PCAP_LPBK)
        return finish(S_GATE_LPBK, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, v);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!(v & STS_PCFG_DONE))
        return finish(S_GATE_NOT_DONE, 0u, 0u, 0xFFFFFFFFu);
    if (hal_cpu(CPU_SCTLR) & 0x4u)                      /* SCTLR.C: the DMA writes DDR behind the data cache */
        return finish(S_GATE_DCACHE, 0u, 0u, 0xFFFFFFFFu);

    /* record 0: the reference frame's first reading */
    code = read_frame(rec, ref_far, KIND_BASELINE, 0u, far_lo, far_hi, poll_limit);
    rec++;
    if (code != C_OK)
        return finish(S_STOP_BASELINE | code, rec, 0u, 0u);

    for (r = 0; r < repeats; r++) {
        for (k = 0; k < n_fars; k++) {
            far = par(P_FARS + k);
            code = read_frame(rec, far, KIND_TARGET, r, far_lo, far_hi, poll_limit);
            if (code == C_OK) {                         /* against the first reading of this frame in this run */
                first = 0xFFFFFFFFu;
                for (i = 0; i < rec; i++)
                    if (res_rd(HDR_WORDS + i * REC_WORDS + R_FAR) == far
                        && res_rd(HDR_WORDS + i * REC_WORDS + R_CODE) == C_OK) {
                        first = i;
                        break;
                    }
                if (first != 0xFFFFFFFFu && !same_frame(first, rec)) {
                    code = C_REPEAT_DIFFERS;
                    res_wr(HDR_WORDS + rec * REC_WORDS + R_CODE, code);
                }
            }
            rec++;
            if (code == C_OK)
                continue;
            anomalies++;
            if (IS_INTERFACE(code))
                return finish(S_STOP_INTERFACE | code, rec, anomalies, rec - 1u);
            /* a data anomaly: is the interface still healthy? re-read the reference frame */
            code = read_frame(rec, ref_far, KIND_HEALTH, r, far_lo, far_hi, poll_limit);
            v = (code == C_OK && same_frame(0u, rec)) ? 1u : 0u;
            res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);
            rec++;
            if (!v)
                return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);
            if (anomalies > budget)
                return finish(S_STOP_BUDGET, rec, anomalies, rec - 2u);
        }
    }

    /* the reference frame once more at the end */
    code = read_frame(rec, ref_far, KIND_FINAL, repeats, far_lo, far_hi, poll_limit);
    v = (code == C_OK && same_frame(0u, rec)) ? 1u : 0u;
    res_wr(HDR_WORDS + rec * REC_WORDS + R_REF_EQUAL, v);
    rec++;
    if (!v)
        return finish(S_STOP_HEALTH, rec, anomalies, rec - 1u);
    return finish(S_DONE, rec, anomalies, 0xFFFFFFFFu);
}

/* ================================================================== stage 4 (S1b.1): the walk of one column
 * From the starting address, for each frame: the pad alone and then the register (the device names the next
 * address), and the pad with the frame (its content). The next address read at is the one the device named;
 * none is computed here. A pass ends when the device names an address outside the envelope, or at the limit.
 * Where the register stands still after the pad alone (the last address of a row), the address it holds after the
 * read of that frame is taken as the next one, if it is above — for at most P_STANDSTILLS such places a pass; with
 * that word 0 the walk stops there, as it always did.
 * The walk is made P_REPEATS times; then the frames found are read again several in one read: three from every
 * third address, and where one or two are left over, the last three once more (both, if the walk found only two).
 * Records have the stage-2 layout; R_OP says which of the three reads a record is, R_REPEAT the pass.
 * Any anomaly ends the run after one reference read: a walk cannot skip a frame and go on.
 * Over the whole run — both passes and the reads of several frames — the reference frame is read again before
 * more than P_HEALTH_EVERY frames have been delivered since it was last read. */
struct walk { uint32_t rec, anomalies, stop, far_lo, far_hi, ref_far, poll_limit, since, every, extra; };
#define NO_REC 0xFFFFFFFFu

/* the first clean record of pass 0 for this read at this address */
static uint32_t first_of(uint32_t upto, uint32_t op, uint32_t far)
{
    uint32_t i;
    for (i = 1u; i < upto; i++)
        if (r2_rd(i, R_KIND) == KIND_TARGET && r2_rd(i, R_REPEAT) == 0u && r2_rd(i, R_OP) == op
            && r2_rd(i, R_FAR) == far && r2_rd(i, R_CODE) == C_OK)
            return i;
    return NO_REC;
}

/* the content record of the k-th frame of pass 0 (k from 0) */
static uint32_t nth_content(uint32_t upto, uint32_t k)
{
    uint32_t i;
    for (i = 1u; i < upto; i++)
        if (r2_rd(i, R_KIND) == KIND_TARGET && r2_rd(i, R_REPEAT) == 0u && r2_rd(i, R_OP) == OP_CONTENT
            && r2_rd(i, R_CODE) == C_OK) {
            if (k == 0u)
                return i;
            k--;
        }
    return NO_REC;
}

/* a reference read; returns 1 if it is clean and equal to the baseline */
static uint32_t health4(struct walk *c, uint32_t kind, uint32_t pass)
{
    uint32_t code = read_op(c->rec, c->ref_far, 1u, kind, pass, 0xFFFFFFFFu, c->far_lo, c->far_hi, c->poll_limit);
    uint32_t v = ref_healthy(c->rec, code);
    r2_wr(c->rec, R_REF_EQUAL, v);
    c->rec++;
    c->since = 0u;
    return v;
}

/* before a read that delivers n frames: the reference first, if with these there would be more than `every`
 * frames since it was last read. Returns 0, or the status to stop with if the reference frame has changed. */
static uint32_t due(struct walk *c, uint32_t n, uint32_t pass)
{
    if (c->since + n > c->every && !health4(c, KIND_HEALTH, pass)) {
        c->stop = c->rec - 1u;
        return health_stop(c->stop);
    }
    c->since += n;
    return 0u;
}

/* one record of the walk and what follows from it: 0 to go on, or the status the run stops with.
 * For the three-frame read, `index` is the place of its first frame in the list pass 0 walked. */
static uint32_t walk_op(struct walk *c, uint32_t far, uint32_t n, uint32_t pass, uint32_t op, uint32_t index)
{
    uint32_t me = c->rec, code, first, j, k, a, b;

    code = c->extra ? read_deep(c->extra, me, far, n, KIND_TARGET, pass, op, c->far_lo, c->far_hi, c->poll_limit)
                    : read_op(me, far, n, KIND_TARGET, pass, op, c->far_lo, c->far_hi, c->poll_limit);
    if (code == C_OK && op != OP_TRIPLE && pass != 0u) {            /* a later pass: against pass 0 at this address */
        first = first_of(me, op, far);
        if (first == NO_REC || r2_rd(first, REC2_FARBLK + F_VALUE) != r2_rd(me, REC2_FARBLK + F_VALUE))
            code = C_FAR_DIFFERS;                                   /* pass 0 never stood here, or was told another address */
        else if (!same_data(first, me, n))
            code = C_REPEAT_DIFFERS;
    }
    if (code == C_OK && op == OP_TRIPLE) {                          /* each frame against the single read of that frame */
        for (j = 0u; j < n && code == C_OK; j++) {
            first = nth_content(me, index + j);
            if (first == NO_REC) {
                code = C_REPEAT_DIFFERS;
                break;
            }
            a = HDR_WORDS + me * REC2_WORDS + REC2_DATA + FRAME_WORDS * (j + 1u);
            b = HDR_WORDS + first * REC2_WORDS + REC2_DATA + FRAME_WORDS;
            for (k = 0u; k < FRAME_WORDS; k++)
                if (res_rd(a + k) != res_rd(b + k)) {
                    code = C_REPEAT_DIFFERS;
                    break;
                }
        }
    }
    r2_wr(me, R_CODE, code);
    c->rec++;
    if (code == C_OK)
        return 0u;
    c->anomalies++;
    c->stop = me;
    if (IS_INTERFACE(code))
        return S_STOP_INTERFACE | code;
    if (!health4(c, KIND_HEALTH, pass)) {
        c->stop = c->rec - 1u;
        return health_stop(c->stop);
    }
    return S_STOP_WALK | code;
}

static uint32_t run_s4(void)
{
    struct walk c;
    uint32_t i, v, pass, passes, limit, start, cur, next, count, status, k, n, n0;
    uint32_t allowed, still, still0, piece, from, to, len, cut[MAX_STANDSTILLS];

    tag(); put(" start\r\n");
    for (i = 0; i < HDR_WORDS; i++)
        res_wr(i, 0u);
    res_wr(H_MAGIC, RESULT_MAGIC);
    res_wr(H_VERSION, 1u);
    res_wr(H_REC_WORDS, REC2_WORDS);
    res_wr(H_HDR_WORDS, HDR_WORDS);
    res_wr(H_STOP_RECORD, 0xFFFFFFFFu);
    for (i = 0; i < PARAM_WORDS; i++)
        res_wr(H_PARAMS + i, par(i));
    res_wr(H_SCTLR, hal_cpu(CPU_SCTLR));
    res_wr(H_CPSR, hal_cpu(CPU_CPSR));
    res_wr(H_SP, hal_cpu(CPU_SP));
    res_wr(H_R9, hal_cpu(CPU_R9));

    c.rec = 0u; c.anomalies = 0u; c.stop = 0xFFFFFFFFu; c.since = 0u;
    c.far_lo = par(P_FAR_LO); c.far_hi = par(P_FAR_HI); c.ref_far = par(P_REF_FAR); c.poll_limit = par(P_POLL_LIMIT);
    passes = par(P_REPEATS); limit = par(P_WALK_LIMIT); c.every = par(P_HEALTH_EVERY); start = par(P_FARS);
    c.extra = par(P_DIAG_STACK) & 0xFFu;
    allowed = par(P_STANDSTILLS);
    if (par(P_VERSION) != 1u || c.far_lo > c.far_hi || c.ref_far < c.far_lo || c.ref_far > c.far_hi
        || par(P_N_FARS) != 1u || start < c.far_lo || start > c.far_hi
        || passes == 0u || passes > MAX_PASSES || limit == 0u || limit > MAX_WALK || c.every < MAX_READ_FRAMES
        || par(P_ANOMALY_BUDGET) != 0u || allowed > MAX_STANDSTILLS || c.extra > MAX_DIAG_STACK || poll_mode() > POLL_NO_STACK || c.poll_limit == 0u || c.poll_limit > 0x10000000u)
        return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);

    v = hal_rd(DEVCFG_CTRL);   res_wr(H_CTRL, v);
    if ((v & CTRL_PCAP_MASK) != CTRL_PCAP_MASK)
        return finish2(S_GATE_CTRL, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_MCTRL);  res_wr(H_MCTRL, v);
    if (v & MCTRL_PCAP_LPBK)
        return finish2(S_GATE_LPBK, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, v);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!(v & STS_PCFG_DONE))
        return finish2(S_GATE_NOT_DONE, 0u, 0u, 0xFFFFFFFFu);
    if (hal_cpu(CPU_SCTLR) & 0x4u)
        return finish2(S_GATE_DCACHE, 0u, 0u, 0xFFFFFFFFu);

    v = read_op(c.rec, c.ref_far, 1u, KIND_BASELINE, 0u, 0xFFFFFFFFu, c.far_lo, c.far_hi, c.poll_limit);
    c.rec++;
    if (v != C_OK)
        return finish2(S_STOP_BASELINE | v, c.rec, 0u, 0u);

    n0 = 0u; still0 = 0u;
    for (pass = 0u; pass < passes; pass++) {
        cur = start; count = 0u; still = 0u;
        for (;;) {
            k = c.rec;                                              /* the record in which the device names the next address */
            status = walk_op(&c, cur, 0u, pass, OP_SUCC, 0u);       /* what does the device call the address after cur */
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            next = r2_rd(k, REC2_FARBLK + F_VALUE);
            status = due(&c, 1u, pass);
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            i = c.rec;                                              /* the record of the frame at cur */
            status = walk_op(&c, cur, 1u, pass, OP_CONTENT, 0u);    /* the frame at cur */
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            count++;
            res_wr(H_WALK + 3u * pass, count);
            res_wr(H_WALK + 3u * pass + 2u, next);
            if (next == cur && allowed != 0u) {                     /* after the pad alone the register stood still */
                v = r2_rd(i, REC2_FARBLK + F_VALUE);                /* where the read of the frame itself left it */
                if (v > cur) {                                      /* one step on it names an address above: the end of a row */
                    if (still >= allowed)
                        return finish2(S_STOP_STANDSTILLS, c.rec, c.anomalies, k);
                    if (pass == 0u)
                        cut[still] = count;                         /* the list is cut after this frame */
                    still++;
                    next = v;
                    res_wr(H_WALK + 3u * pass + 2u, next);
                }
            }
            if (next <= cur)                                        /* not above the address asked about — wherever it lies, also
                                                                       below the envelope: following it would not end */
                return finish2(S_STOP_STUCK, c.rec, c.anomalies, k);    /* a reference read may lie between it and the content read */
            if (next > c.far_hi) {                                  /* the device has named something beyond the envelope: not read.
                                                                       (above cur, so it cannot be below the envelope) */
                res_wr(H_WALK + 3u * pass + 1u, END_LEFT);
                break;
            }
            if (count >= limit) {
                res_wr(H_WALK + 3u * pass + 1u, END_LIMIT);
                break;
            }
            cur = next;
        }
        if (pass == 0u) {
            n0 = count; still0 = still;
        }
    }

    /* every frame of pass 0 once more, several in one read — within each piece of the list (the list is cut where the
     * register stood still: a read across such a place would deliver what lies there, which has no address): three
     * from every third address of the piece; where one or two are left over, the last three of the piece again; both,
     * if the piece has only two. A piece of a single frame has no such second path.
     * The addresses of a pass rise strictly and end inside the envelope, so the last frame of any of these reads
     * is inside as well; the guard checks it again for each stream. */
    from = 0u;
    for (piece = 0u; piece <= still0; piece++) {
        to = piece < still0 ? cut[piece] : n0;
        len = to - from;
        for (k = 0u; k < len; k += 3u) {
            n = 3u; i = from + k;
            if (len - k < 3u) {
                if (len >= 3u)
                    i = to - 3u;
                else if (len == 2u)
                    n = 2u;
                else
                    break;
            }
            v = nth_content(c.rec, i);
            if (v == NO_REC)
                break;
            cur = r2_rd(v, R_FAR);
            status = due(&c, n, passes);
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            status = walk_op(&c, cur, n, passes, OP_TRIPLE, i);
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
        }
        from = to;
    }

    if (!health4(&c, KIND_FINAL, passes))
        return finish2(health_stop(c.rec - 1u), c.rec, c.anomalies, c.rec - 1u);
    return finish2(S_DONE, c.rec, c.anomalies, 0xFFFFFFFFu);
}

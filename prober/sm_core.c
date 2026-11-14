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
        } else if (x == W_RD_FAR_1) {                   /* one word of the FAR register: a read, of a readable register */
            i++;
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
static uint32_t dma(uint32_t src, uint32_t dst, uint32_t slen, uint32_t dlen, uint32_t poll_limit,
                    uint32_t *sts, uint32_t *polls)
{
    uint32_t s, n;

    *polls = 0u;
    hal_wr(DEVCFG_INT_STS, STS_CLEAR_MASK);
    s = hal_rd(DEVCFG_INT_STS);
    *sts = s;
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
static void r2_wr(uint32_t rec, uint32_t field, uint32_t v) { res_wr(HDR_WORDS + rec * REC2_WORDS + field, v); }
static uint32_t r2_rd(uint32_t rec, uint32_t field)         { return res_rd(HDR_WORDS + rec * REC2_WORDS + field); }

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

    sm_frames_stream(far, n, stream);
    sm_far_read_stream(farrd);
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

/* "SM2", "SM3" or "SM4": the stage is read from the parameter block each time, there is no static to keep it in */
static void tag(void)
{
    put("SM");
    hal_putc(par(P_STAGE) == 4u ? '4' : par(P_STAGE) == 3u ? '3' : '2');
}

static uint32_t finish2(uint32_t status, uint32_t n_records, uint32_t n_anomalies, uint32_t stop_record)
{
    res_wr(H_STATUS, status);
    if (status == S_BAD_PARAMS) {
        tag(); put(" end status="); puthex(status); put("\r\n");
        res_wr(H_TOTAL_WORDS, HDR_WORDS);
        return status;
    }
    res_wr(H_N_RECORDS, n_records);
    res_wr(H_N_ANOMALIES, n_anomalies);
    res_wr(H_TOTAL_WORDS, HDR_WORDS + n_records * REC2_WORDS);
    res_wr(H_STOP_RECORD, stop_record);
    res_wr(H_INT_STS1, hal_rd(DEVCFG_INT_STS));
    res_wr(H_STATUS1, hal_rd(DEVCFG_STATUS));
    tag(); put(" end status="); puthex(status);
    put(" records="); puthex(n_records);
    put(" anomalies="); puthex(n_anomalies);
    put(" words="); puthex(HDR_WORDS + n_records * REC2_WORDS);
    put("\r\n");
    return status == S_DONE ? 0u : status;
}

static uint32_t op_frames(uint32_t k)
{
    return (par(k < 8u ? P_NFRAMES_LO : P_NFRAMES_HI) >> (4u * (k & 7u))) & 0xFu;
}

static uint32_t run_s2(void)
{
    uint32_t i, r, k, rec = 0u, anomalies = 0u, code, v, n, far, first;
    uint32_t far_lo, far_hi, ref_far, n_ops, repeats, budget, poll_limit;
    int stage3 = par(P_STAGE) == 3u;

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

    far_lo = par(P_FAR_LO); far_hi = par(P_FAR_HI); ref_far = par(P_REF_FAR);
    n_ops = par(P_N_FARS); repeats = par(P_REPEATS); budget = par(P_ANOMALY_BUDGET); poll_limit = par(P_POLL_LIMIT);
    if (par(P_VERSION) != 1u || far_lo > far_hi || ref_far < far_lo || ref_far > far_hi
        || n_ops == 0u || n_ops > MAX_FARS || repeats == 0u || repeats > MAX_REPEATS
        || budget > 64u || poll_limit == 0u || poll_limit > 0x10000000u)
        return finish2(S_BAD_PARAMS, 0u, 0u, 0xFFFFFFFFu);
    for (k = 0; k < n_ops; k++) {
        far = par(P_FARS + k); n = op_frames(k);
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
    v = hal_rd(DEVCFG_MCTRL);  res_wr(H_MCTRL, v);
    if (v & MCTRL_PCAP_LPBK)
        return finish2(S_GATE_LPBK, 0u, 0u, 0xFFFFFFFFu);
    v = hal_rd(DEVCFG_INT_STS); res_wr(H_INT_STS0, v);
    res_wr(H_STATUS0, hal_rd(DEVCFG_STATUS));
    if (!(v & STS_PCFG_DONE))
        return finish2(S_GATE_NOT_DONE, 0u, 0u, 0xFFFFFFFFu);
    if (hal_cpu(CPU_SCTLR) & 0x4u)
        return finish2(S_GATE_DCACHE, 0u, 0u, 0xFFFFFFFFu);

    code = read_op(rec, ref_far, 1u, KIND_BASELINE, 0u, 0xFFFFFFFFu, far_lo, far_hi, poll_limit);
    rec++;
    if (code != C_OK)
        return finish2(S_STOP_BASELINE | code, rec, 0u, 0u);

    for (r = 0; r < repeats; r++) {
        for (k = 0; k < n_ops; k++) {
            far = par(P_FARS + k); n = op_frames(k);
            code = read_op(rec, far, n, KIND_TARGET, r, k, far_lo, far_hi, poll_limit);
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
                return finish2(S_STOP_HEALTH, rec, anomalies, rec - 1u);
            if (anomalies > budget)
                return finish2(S_STOP_BUDGET, rec, anomalies, rec - 2u);
        }
    }

    code = read_op(rec, ref_far, 1u, KIND_FINAL, repeats, 0xFFFFFFFFu, far_lo, far_hi, poll_limit);
    v = ref_healthy(rec, code);
    r2_wr(rec, R_REF_EQUAL, v);
    rec++;
    if (!v)
        return finish2(S_STOP_HEALTH, rec, anomalies, rec - 1u);
    return finish2(S_DONE, rec, anomalies, 0xFFFFFFFFu);
}

static uint32_t run_s4(void);

/* ------------------------------------------------------------------ stage S1a */
uint32_t sm_run(void)
{
    uint32_t i, r, k, rec = 0u, anomalies = 0u, code, v;
    uint32_t far_lo, far_hi, ref_far, n_fars, repeats, budget, poll_limit, far, first;

    if (par(P_MAGIC) == PARAM_MAGIC && (par(P_STAGE) == 2u || par(P_STAGE) == 3u))
        return run_s2();
    if (par(P_MAGIC) == PARAM_MAGIC && par(P_STAGE) == 4u)
        return run_s4();
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
 * The walk is made P_REPEATS times; then the frames found are read again several in one read: three from every
 * third address, and where one or two are left over, the last three once more (both, if the walk found only two).
 * Records have the stage-2 layout; R_OP says which of the three reads a record is, R_REPEAT the pass.
 * Any anomaly ends the run after one reference read: a walk cannot skip a frame and go on.
 * Over the whole run — both passes and the reads of several frames — the reference frame is read again before
 * more than P_HEALTH_EVERY frames have been delivered since it was last read. */
struct walk { uint32_t rec, anomalies, stop, far_lo, far_hi, ref_far, poll_limit, since, every; };
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
        return S_STOP_HEALTH;
    }
    c->since += n;
    return 0u;
}

/* one record of the walk and what follows from it: 0 to go on, or the status the run stops with.
 * For the three-frame read, `index` is the place of its first frame in the list pass 0 walked. */
static uint32_t walk_op(struct walk *c, uint32_t far, uint32_t n, uint32_t pass, uint32_t op, uint32_t index)
{
    uint32_t me = c->rec, code, first, j, k, a, b;

    code = read_op(me, far, n, KIND_TARGET, pass, op, c->far_lo, c->far_hi, c->poll_limit);
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
        return S_STOP_HEALTH;
    }
    return S_STOP_WALK | code;
}

static uint32_t run_s4(void)
{
    struct walk c;
    uint32_t i, v, pass, passes, limit, start, cur, next, count, status, k, n, n0;

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
    if (par(P_VERSION) != 1u || c.far_lo > c.far_hi || c.ref_far < c.far_lo || c.ref_far > c.far_hi
        || par(P_N_FARS) != 1u || start < c.far_lo || start > c.far_hi
        || passes == 0u || passes > MAX_PASSES || limit == 0u || limit > MAX_WALK || c.every < MAX_READ_FRAMES
        || par(P_ANOMALY_BUDGET) != 0u || c.poll_limit == 0u || c.poll_limit > 0x10000000u)
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

    n0 = 0u;
    for (pass = 0u; pass < passes; pass++) {
        cur = start; count = 0u;
        for (;;) {
            k = c.rec;                                              /* the record in which the device names the next address */
            status = walk_op(&c, cur, 0u, pass, OP_SUCC, 0u);       /* what does the device call the address after cur */
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            next = r2_rd(k, REC2_FARBLK + F_VALUE);
            status = due(&c, 1u, pass);
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            status = walk_op(&c, cur, 1u, pass, OP_CONTENT, 0u);    /* the frame at cur */
            if (status != 0u)
                return finish2(status, c.rec, c.anomalies, c.stop);
            count++;
            res_wr(H_WALK + 3u * pass, count);
            res_wr(H_WALK + 3u * pass + 2u, next);
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
        if (pass == 0u)
            n0 = count;
    }

    /* every frame of pass 0 once more, several in one read: three from every third address; where one or two are
     * left over, the last three again; both, if there are only two. A single frame has no such second path.
     * The addresses of a pass rise strictly and end inside the envelope, so the last frame of any of these reads
     * is inside as well; the guard checks it again for each stream. */
    for (k = 0u; k < n0; k += 3u) {
        n = 3u; i = k;
        if (n0 - k < 3u) {
            if (n0 >= 3u)
                i = n0 - 3u;
            else if (n0 == 2u)
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

    if (!health4(&c, KIND_FINAL, passes))
        return finish2(S_STOP_HEALTH, c.rec, c.anomalies, c.rec - 1u);
    return finish2(S_DONE, c.rec, c.anomalies, 0xFFFFFFFFu);
}

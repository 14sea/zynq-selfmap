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

/* the same stream reading n_frames frames in one FDRO read: only the length differs */
void sm_frames_stream(uint32_t far, uint32_t n_frames, uint32_t out[STREAM_WORDS])
{
    sm_readback_stream(far, out);
    out[10] = W_T2_READ | (FRAME_WORDS * (n_frames + 1u));
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
            if (v == 0xFFFFFFFFu || v < 2u)                             /* a pad frame and whole frames */
                return REFUSE(i, 10u);
            if (far_value + (v - 2u) > far_hi)                          /* the last frame read is still inside */
                return REFUSE(i, 11u);
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

/* ------------------------------------------------------------------ stage S1a */
uint32_t sm_run(void)
{
    uint32_t i, r, k, rec = 0u, anomalies = 0u, code, v;
    uint32_t far_lo, far_hi, ref_far, n_fars, repeats, budget, poll_limit, far, first;

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

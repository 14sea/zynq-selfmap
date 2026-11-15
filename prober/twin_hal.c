/* zynq-selfmap prober — the host twin: the hardware doors of sm.h against a small model of DEVCFG and the
 * configuration engine. The model is an assumption about the device, pinned only where zynq-psmap observed
 * it (a 101-word zero pad, then the frame). It exists to exercise the prober's logic, not to stand in for
 * silicon. Every register access is logged; anything the model sees that a read-only stage must never do is
 * logged as VIOLATION.
 *
 *   twin gen <far-hex>                      print the readback stream and the cleanup stream
 *   twin genframes <far-hex> <n>            print the stream reading n frames (0: the pad alone; 15: no read), and the FAR-register read stream
 *   twin guard <lo> <hi> <max> <w0> <w1>..  run the guard on a stream; print its return value
 *   twin run <frames.txt> <params.txt> <result.bin>   run S1a; SM_FAULT selects injected faults
 *
 * Faults (comma separated; N counts DMA commands, R counts read commands, both from 1):
 *   ctrl lpbk nodone dcache stale   a gate or the stale-status check fails
 *   err@N timeout@N                 command N ends with an error bit / never completes
 *   drop@N dropafter@N              PCFG_DONE falls during command N / between command N and the next
 *   short@R padnz@R flip@R flip3@R  frame read R delivers 150 words (half, if it asked for fewer) / a nonzero pad word / one flipped bit in its first / third frame
 *   farshort@K farflip@K            FAR-register read K delivers nothing / a changed value
 * SM_FAR_RULE=skip makes the FAR register end one frame further than the last frame delivered (the pad counted);
 * the default leaves it at the next unread frame. S1b.0 found the board to do the former for reads of one and of
 * three frames. SM_FAR_RULE=skipdata counts the pad only when a frame follows it: after the pad alone the
 * register has not moved. What the device does after the pad alone is what S1b.0b is to find out.
 * SM_SUCC=a:b,c:d (hex) says which address follows which where it is not simply the next number: the end of a
 * column, an address that names itself, a step backwards. What the device does at a column end is what S1b.1
 * is to find out; the tests give the model several answers.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sm.h"

#define DDR_BASE   0x10000000u
#define DDR_WORDS  0x00100000u                         /* 4 MiB */
static uint32_t ddr[DDR_WORDS];
static uint32_t reg_ctrl = 0x4E00E07Fu, reg_mctrl = 0x30800100u, reg_sts = 0x50021004u, reg_status = 0x40000A30u;
static uint32_t dma_src, dma_dst, dma_slen, sctlr = 0x08C51879u;   /* data cache off, as after U-Boot's `dcache off` */
static unsigned n_dma, n_read_dma, n_far_read; static int done_pending, drop_on_next_clear, far_skips, far_skips_data_only;
static char uart[4096]; static unsigned uart_n;

/* frames */
#define MAX_FRAMES 200
static uint32_t f_far[MAX_FRAMES], f_words[MAX_FRAMES][FRAME_WORDS]; static unsigned n_frames;

/* engine */
static int synced, rcfg; static uint32_t far_reg;
static uint32_t succ_from[32], succ_to[32]; static unsigned n_succ;
static uint32_t succ(uint32_t f)
{
    unsigned i;
    for (i = 0; i < n_succ; i++) if (succ_from[i] == f) return succ_to[i];
    return f + 1u;
}
static uint32_t queue[4096]; static unsigned q_n, q_at;

/* faults */
static const char *fault;
static int fault_at(const char *name, unsigned index)
{
    char key[64]; const char *p;
    if (!fault) return 0;
    snprintf(key, sizeof key, "%s@%u", name, index);
    for (p = strstr(fault, key); p; p = strstr(p + 1, key))                  /* a whole entry: "flip@5" is not inside "farflip@5" */
        if ((p == fault || p[-1] == ',') && (p[strlen(key)] == 0 || p[strlen(key)] == ','))
            return 1;
    return 0;
}
static int fault_on(const char *name)
{
    const char *p = fault ? strstr(fault, name) : 0; size_t n = strlen(name);
    return p && (p == fault || p[-1] == ',') && (p[n] == 0 || p[n] == ',');
}

static const uint32_t *frame(uint32_t far)
{
    static const uint32_t zero[FRAME_WORDS];
    unsigned i;
    for (i = 0; i < n_frames; i++) if (f_far[i] == far) return f_words[i];
    return zero;
}

static void engine_feed(const uint32_t *w, uint32_t n)
{
    uint32_t i = 0, x, type, op, reg, count, k, f;
    printf("STREAM");
    for (k = 0; k < n; k++) printf(" %08x", w[k]);
    printf("\n");
    while (i < n) {
        x = w[i++];
        if (!synced) { if (x == W_SYNC) synced = 1; else if (x != W_DUMMY && x != W_NOOP) printf("VIOLATION unsynced word %08x\n", x); continue; }   /* NOOPs after DESYNC are UG470's own trailer */
        if (x == W_NOOP) continue;
        type = x >> 29; op = (x >> 27) & 3u;
        if (type == 1u) {
            reg = (x >> 13) & 0x3FFFu; count = x & 0x7FFu;
            if (op == 2u) {                              /* write */
                for (k = 0; k < count && i < n; k++, i++) {
                    if (reg == 4u) {
                        if (w[i] == CMD_RCFG) rcfg = 1;
                        else if (w[i] == CMD_DESYNC) { synced = 0; rcfg = 0; }
                        else printf("VIOLATION CMD %08x\n", w[i]);
                    } else if (reg == 1u) far_reg = w[i];
                    else printf("VIOLATION write to register %u\n", reg);
                }
            } else if (op == 1u) {                       /* read header */
                if (reg == 1u && count == 1u) { q_n = q_at = 0; queue[q_n++] = far_reg; }             /* the FAR register */
                else if (reg != 3u || count != 0u) printf("VIOLATION read of register %u count %u\n", reg, count);
            } else printf("VIOLATION type-1 op %u\n", op);
        } else if (type == 2u) {
            count = x & 0x07FFFFFFu;
            if (op != 1u) { printf("VIOLATION type-2 op %u\n", op); continue; }
            if (!rcfg) printf("VIOLATION read without RCFG\n");
            q_n = q_at = 0;
            for (k = 0; k < FRAME_WORDS && q_n < count; k++) queue[q_n++] = 0u;          /* the pad frame */
            for (f = far_reg; q_n < count; f = succ(f))
                for (k = 0; k < FRAME_WORDS && q_n < count; k++) queue[q_n++] = frame(f)[k];
            far_reg = (far_skips && !(far_skips_data_only && count <= FRAME_WORDS)) ? succ(f) : f;   /* the register moves on as frames are read; by which rule is the open question */
        } else printf("VIOLATION header %08x\n", x);
    }
}

static int in(uint32_t a, uint32_t base, uint32_t words) { return a >= base && a < base + 4u * words; }

static void dma_execute(uint32_t dlen)
{
    uint32_t i, n;
    n_dma++;
    printf("DMA %u src=%08x dst=%08x slen=%u dlen=%u\n", n_dma, dma_src, dma_dst, dma_slen, dlen);
    if (fault_at("timeout", n_dma)) return;                                   /* never completes */
    if (fault_at("err", n_dma)) { reg_sts |= 0x00040000u; return; }           /* RX_FIFO_OV */
    if (dma_dst == PCAP_ENDPOINT && (dma_src & 3u) == DMA_HOLD_TAG && dlen == 0u) {
        uint32_t a = dma_src & ~3u;
        if (!in(a, CMD_BUF, 64u)) printf("VIOLATION command source %08x\n", a);
        engine_feed(&ddr[(a - DDR_BASE) / 4u], dma_slen);
    } else if (dma_src == PCAP_ENDPOINT && (dma_dst & 3u) == DMA_HOLD_TAG && dma_slen == 0u) {
        uint32_t a = dma_dst & ~3u;
        if (!in(a, DST_BUF, DATA2_WORDS)) printf("VIOLATION read destination %08x\n", a);
        n = dlen;
        if (dlen == 1u) {                                                     /* a register read */
            n_far_read++;
            if (fault_at("farshort", n_far_read)) n = 0u;
            for (i = 0; i < n && q_at < q_n; i++) ddr[(a - DDR_BASE) / 4u + i] = queue[q_at++];
            if (n && fault_at("farflip", n_far_read)) ddr[(a - DDR_BASE) / 4u] ^= 0x00000004u;
        } else {
            n_read_dma++;
            if (fault_at("short", n_read_dma)) n = dlen > 150u ? 150u : dlen / 2u;
            for (i = 0; i < n && q_at < q_n; i++) ddr[(a - DDR_BASE) / 4u + i] = queue[q_at++];
            if (fault_at("padnz", n_read_dma)) ddr[(a - DDR_BASE) / 4u + 7u] = 0x00000100u;
            if (fault_at("flip", n_read_dma)) ddr[(a - DDR_BASE) / 4u + FRAME_WORDS + 3u] ^= 0x00010000u;
            if (fault_at("flip3", n_read_dma) && dlen >= 4u * FRAME_WORDS) ddr[(a - DDR_BASE) / 4u + 3u * FRAME_WORDS + 3u] ^= 0x00010000u;
        }
    } else {
        printf("VIOLATION dma shape\n");
        reg_sts |= 0x00008000u;                                               /* DMA_CMD_ERR */
        return;
    }
    reg_sts |= 0x00002000u;                                                   /* DMA_DONE first: UG585 says it may be set before the PCAP has finished */
    done_pending = 1;                                                         /* D_P_DONE appears on the next status read */
    if (fault_at("drop", n_dma)) reg_sts &= ~STS_PCFG_DONE;             /* during this command */
    if (fault_at("dropafter", n_dma)) drop_on_next_clear = 1;             /* between this command and the next */
}

/* What the prober's own count of polls holds each time a queued transfer is polled: the loop that stores on every
 * poll shows 0, 1, 2, ...; a loop that stores nothing until the transfer is over shows 0 throughout (WATCH), and
 * either shows the whole count once the wait is over (WATCHED).
 *
 * The count is a local variable of the routine that makes the read, so it may be looked at only while that routine
 * is running. A wait begins with the write that queues a command and consists of reads of the status register and
 * nothing else; the first call through any other door ends it — whatever way the wait went, limit included. That
 * call is the routine's own (it records the status and the count as soon as the transfer function returns), so the
 * variable is still there: it is looked at one last time and then left alone until the next command is queued.
 * (Found by review, 2026-11-15: the watch used to go on until a status read showed the transfer done; after a wait
 * that gave up at the limit the next status read came from the end of the run, when the variable was gone.) */
static const uint32_t *watch; static int polling;
static void wait_over(void)
{
    if (polling && watch) printf("WATCHED %u %u\n", n_dma, *watch);
    polling = 0;
}
void hal_watch(const uint32_t *polls) { wait_over(); watch = polls; }

uint32_t hal_rd(uint32_t a)
{
    uint32_t v;
    switch (a) {
    case DEVCFG_CTRL:    v = reg_ctrl; break;
    case DEVCFG_MCTRL:   v = reg_mctrl; break;
    case DEVCFG_INT_STS: v = reg_sts; if (done_pending) { done_pending = 0; reg_sts |= 0x00001000u; }
                         if (polling && watch) printf("WATCH %u %u\n", n_dma, *watch);
                         break;
    case DEVCFG_STATUS:  v = reg_status; break;
    default:             v = 0; printf("VIOLATION read %08x\n", a); break;
    }
    if (a != DEVCFG_INT_STS) wait_over();
    printf("R %08x %08x\n", a, v);
    return v;
}

void hal_wr(uint32_t a, uint32_t v)
{
    wait_over();
    printf("W %08x %08x\n", a, v);
    switch (a) {
    case DEVCFG_INT_STS:  if (!fault_on("stale")) reg_sts &= ~v; else reg_sts |= 0x00000800u;
                          if (drop_on_next_clear) { drop_on_next_clear = 0; reg_sts &= ~STS_PCFG_DONE; }
                          break;
    case DEVCFG_DMA_SRC:  dma_src = v; break;
    case DEVCFG_DMA_DST:  dma_dst = v; break;
    case DEVCFG_DMA_SLEN: dma_slen = v; break;
    case DEVCFG_DMA_DLEN: dma_execute(v); polling = 1; break;
    default: printf("VIOLATION write %08x\n", a); break;
    }
}

uint32_t hal_mem_rd(uint32_t a)
{
    wait_over();
    if (!(in(a, RESULT_ADDR, RESULT_MAX_WORDS) || in(a, PARAM_ADDR, PARAM_WORDS) || in(a, DST_BUF, DATA2_WORDS)))
        { printf("VIOLATION memory read %08x\n", a); return 0; }
    return ddr[(a - DDR_BASE) / 4u];
}

void hal_mem_wr(uint32_t a, uint32_t v)
{
    wait_over();
    if (!(in(a, RESULT_ADDR, RESULT_MAX_WORDS) || in(a, CMD_BUF, STREAM_WORDS) || in(a, DST_BUF, DATA2_WORDS)))
        { printf("VIOLATION memory write %08x\n", a); return; }
    ddr[(a - DDR_BASE) / 4u] = v;
}

uint32_t hal_cpu(int which) { wait_over(); return which == CPU_SCTLR ? sctlr : 0xC0DE0000u | (uint32_t)which; }
void hal_putc(char c) { wait_over(); if (uart_n < sizeof uart - 1) uart[uart_n++] = c; }

static int load_words(const char *path, uint32_t *out, unsigned max)
{
    FILE *f = fopen(path, "r"); unsigned n = 0; unsigned long v;
    if (!f) return -1;
    while (n < max && fscanf(f, "%lx", &v) == 1) out[n++] = (uint32_t)v;
    fclose(f);
    return (int)n;
}

int main(int argc, char **argv)
{
    uint32_t s[STREAM_WORDS], c[CLEANUP_WORDS], w[4096]; unsigned i; int n;
    if (argc >= 3 && !strcmp(argv[1], "gen")) {
        sm_readback_stream((uint32_t)strtoul(argv[2], 0, 16), s); sm_cleanup_stream(c);
        for (i = 0; i < STREAM_WORDS; i++) printf("%08x%c", s[i], i + 1 < STREAM_WORDS ? ' ' : '\n');
        for (i = 0; i < CLEANUP_WORDS; i++) printf("%08x%c", c[i], i + 1 < CLEANUP_WORDS ? ' ' : '\n');
        return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "genframes")) {
        uint32_t f[FARRD_WORDS];
        sm_frames_stream((uint32_t)strtoul(argv[2], 0, 16), (uint32_t)strtoul(argv[3], 0, 10), s); sm_far_read_stream(f);
        for (i = 0; i < STREAM_WORDS; i++) printf("%08x%c", s[i], i + 1 < STREAM_WORDS ? ' ' : '\n');
        for (i = 0; i < FARRD_WORDS; i++) printf("%08x%c", f[i], i + 1 < FARRD_WORDS ? ' ' : '\n');
        return 0;
    }
    if (argc >= 5 && !strcmp(argv[1], "guard")) {
        for (i = 0; i + 5 < (unsigned)argc + 0u && i < 4096; i++) w[i] = (uint32_t)strtoul(argv[5 + i], 0, 16);
        printf("%08x\n", sm_guard(w, i, (uint32_t)strtoul(argv[2], 0, 16), (uint32_t)strtoul(argv[3], 0, 16), (uint32_t)strtoul(argv[4], 0, 16)));
        return 0;
    }
    if (argc >= 5 && !strcmp(argv[1], "run")) {
        static uint32_t all[MAX_FRAMES * (FRAME_WORDS + 1)];
        FILE *f; unsigned long rc; uint32_t total;
        fault = getenv("SM_FAULT");
        far_skips_data_only = getenv("SM_FAR_RULE") && !strcmp(getenv("SM_FAR_RULE"), "skipdata");
        far_skips = far_skips_data_only || (getenv("SM_FAR_RULE") && !strcmp(getenv("SM_FAR_RULE"), "skip"));
        if (getenv("SM_SUCC")) {
            const char *s = getenv("SM_SUCC"); char *e;
            while (*s && n_succ < 32) {
                succ_from[n_succ] = (uint32_t)strtoul(s, &e, 16); if (*e != ':') return 2;
                succ_to[n_succ++] = (uint32_t)strtoul(e + 1, &e, 16);
                s = *e == ',' ? e + 1 : e;
                if (*e && *e != ',') return 2;
            }
        }
        n = load_words(argv[2], all, MAX_FRAMES * (FRAME_WORDS + 1));
        if (n < 0 || n % (int)(FRAME_WORDS + 1)) return 2;
        for (i = 0; i < (unsigned)n / (FRAME_WORDS + 1); i++) {
            f_far[i] = all[i * (FRAME_WORDS + 1)];
            memcpy(f_words[i], &all[i * (FRAME_WORDS + 1) + 1], sizeof f_words[i]);
        }
        n_frames = (unsigned)n / (FRAME_WORDS + 1);
        if (load_words(argv[3], &ddr[(PARAM_ADDR - DDR_BASE) / 4u], PARAM_WORDS) < 0) return 2;
        if (fault_on("ctrl"))   reg_ctrl &= ~0x08000000u;
        if (fault_on("lpbk"))   reg_mctrl |= MCTRL_PCAP_LPBK;
        if (fault_on("nodone")) reg_sts &= ~STS_PCFG_DONE;
        if (fault_on("dcache")) sctlr |= 0x4u;
        rc = sm_run();
        uart[uart_n] = 0;
        printf("UART");
        for (i = 0; i < uart_n; i++) printf(" %02x", (unsigned char)uart[i]);
        printf("\nRC %lx\n", rc);
        total = ddr[H_TOTAL_WORDS];
        if (total < HDR_WORDS || total > RESULT_MAX_WORDS) total = HDR_WORDS;
        f = fopen(argv[4], "wb");
        if (!f || fwrite(ddr, 4, total, f) != total) return 2;
        fclose(f);
        return 0;
    }
    return 64;
}

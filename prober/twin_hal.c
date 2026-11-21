/* zynq-selfmap prober — the host twin: the hardware doors of sm.h against a small model of DEVCFG and the
 * configuration engine. The model is an assumption about the device, pinned only where zynq-psmap observed
 * it (a 101-word zero pad, then the frame). It exists to exercise the prober's logic, not to stand in for
 * silicon. Every register access is logged; anything the model sees that a read-only stage must never do is
 * logged as VIOLATION.
 *
 *   twin gen <far-hex>                      print the readback stream and the cleanup stream
 *   twin genframes <far-hex> <n>            print the stream reading n frames (0: the pad alone; 15: no read), and the FAR-register read stream
 *   twin genreg <n>                         print the stream that reads one word of register n (0 FAR, 1 IDCODE, 2 CTL0, 3 STAT)
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
 * SM_SHOWS=p:v,q:w (hex) says what the address register reads at a position where that is not the position's own
 * number. With SM_SUCC it models places the device passes through that have no address of their own (S1b.2 on the
 * board, run 30: after the last frame of the row the register stood still for a step): give such a place any number
 * no frame has, put it into the chain of successors, and say here what the register shows there. A frame may be
 * given for it like for any other. How many such places there are, and what a read delivers there, is what S1b.2b
 * is to find out; the tests give the model several answers.
 *
 * S2.0 and S2.1 (docs/s2_plan.md). The engine answers a one-word read of IDCODE, CTL0 and STAT as well; what they
 * hold is SM_CREG=idcode:V,ctl0:V,stat:V (hex), each with a default. The four SLCR words stage 7 looks at can be
 * read, and the eight registers of the probe design s2a: a scratch register, a counter, a LUT RAM of 64 x 4 bits
 * written through an address and a data register, four shift registers of 32 bits whose outputs can be read, and
 * the design's count of writes and shifts. This is the design as its source describes it, not the board.
 * More faults:
 *   seu                              SEU_EN is set in devcfg.CTRL
 *   lvl fpgarst fclk pll             one of the four SLCR words is not what the board has
 *   statmoves                        the STAT register reads differently every time
 *   regdisturbs                      after a read of a register other than FAR, every frame delivered has a bit changed
 *   plid scratchstuck countstuck     the identification register reads another word / one bit of the scratch
 *                                    register never sets / the counter stands still
 *   ramstuck ramwild                 one bit of the RAM never sets / a write also changes the address above
 *   srlmoves plcount                 the shift registers' outputs change between reads / the count of writes is one off
 *
 * S2.2 (docs/s2_plan.md, section 19). The list of reads stage 8 makes is SM_LIST=<file> (hex words), put where the
 * host puts it. SM_RAMMAP=<file> says where cells of the design's RAM show in configuration memory: a line for each
 * place — the RAM's address, which of its four memories, the frame address (hex), the word, the bit, and 1 if the
 * place shows the cell inverted. A frame read then delivers, at each such place, what the cell holds at that moment.
 * Where the cells lie on the device nobody here knows; the tests give the model several answers, and none.
 * More faults:
 *   masked                           no place follows its cell: every frame reads as the file of frames has it
 *   ramdisturb@R                     frame read R changes a cell of the RAM
 *   bit5@R bit5stays                 frame read R leaves bit 5 of INT_STS set / a write that clears it does not
 *   lateerr@D latedrop@D             command D completes, and once a status read has shown it done an error bit
 *                                    appears in INT_STS / PCFG_DONE goes one status read after that. Nothing of
 *                                    either shows in any status the transfer itself was judged by
 *   clearerr                         a write that clears bit 5 raises an error bit
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
static unsigned n_dma, n_read_dma, n_far_read; static int done_pending, drop_on_next_clear, late_err, late_drop, far_skips, far_skips_data_only;
static char uart[4096]; static unsigned uart_n;

/* frames */
#define MAX_FRAMES 400
static uint32_t f_far[MAX_FRAMES], f_words[MAX_FRAMES][FRAME_WORDS]; static unsigned n_frames;

/* engine */
static int synced, rcfg; static uint32_t far_reg;
static uint32_t succ_from[96], succ_to[96]; static unsigned n_succ;
static uint32_t succ(uint32_t f)
{
    unsigned i;
    for (i = 0; i < n_succ; i++) if (succ_from[i] == f) return succ_to[i];
    return f + 1u;
}
static uint32_t shows_at[32], shows_what[32]; static unsigned n_shows;
static uint32_t shows(uint32_t position)
{
    unsigned i;
    for (i = 0; i < n_shows; i++) if (shows_at[i] == position) return shows_what[i];
    return position;
}
static uint32_t queue[4096]; static unsigned q_n, q_at;

/* configuration registers a read-only stage may read one word of, beside FAR (S2.0) */
static uint32_t creg_idcode = 0x13722093u, creg_ctl0 = 0x00000501u, creg_stat = 0x401079FCu;
static unsigned n_stat_reads; static int disturbed;

/* the PS side of the PL, and the probe design s2a */
static uint32_t slcr_word[N_SLCR] = { 0x0000000Fu, 0x00000000u, 0x00400800u, 0x0000003Fu };
static uint32_t pl_scratch, pl_count = 0x00010000u, pl_ram_addr, pl_srl_addr, pl_ram[RAM_DEPTH], pl_srl[SRL_DEPTH];
static uint32_t pl_ram_writes, pl_srl_shifts; static unsigned n_srl_reads;
/* where cells of the RAM show in configuration memory (SM_RAMMAP) */
#define MAX_PLACES 1024
static struct { uint32_t addr, mem, far, word, bit, inv; } place[MAX_PLACES]; static unsigned n_places;
#define PL_ID_WORD 0x53324131u                         /* "S2A1": what pl/s2a answers with */

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
    static uint32_t changed[FRAME_WORDS];
    const uint32_t *f = zero;
    unsigned i, shown = 0;
    for (i = 0; i < n_frames; i++) if (f_far[i] == far) f = f_words[i];
    for (i = 0; i < n_places && !fault_on("masked"); i++)                     /* the cells of the RAM that show in this frame */
        if (place[i].far == far) {
            uint32_t cell = ((pl_ram[place[i].addr] >> place[i].mem) & 1u) ^ place[i].inv;
            if (!shown++) memcpy(changed, f, sizeof changed);
            changed[place[i].word] = (changed[place[i].word] & ~(1u << place[i].bit)) | cell << place[i].bit;
        }
    if (!disturbed) return shown ? changed : f;
    if (!shown) memcpy(changed, f, sizeof changed);
    changed[3] ^= 0x00010000u;
    return changed;
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
                if (reg == 1u && count == 1u) { q_n = q_at = 0; queue[q_n++] = shows(far_reg); }      /* the FAR register */
                else if ((reg == 12u || reg == 5u || reg == 7u) && count == 1u) {                      /* IDCODE, CTL0, STAT */
                    q_n = q_at = 0;
                    queue[q_n++] = reg == 12u ? creg_idcode : reg == 5u ? creg_ctl0
                                 : creg_stat ^ (fault_on("statmoves") ? n_stat_reads++ << 4 : 0u);
                    if (fault_on("regdisturbs")) disturbed = 1;
                }
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
            if (fault_at("ramdisturb", n_read_dma)) pl_ram[9] ^= 0x4u;
            if (fault_at("bit5", n_read_dma)) reg_sts |= STS_SEU_ERR;
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
    late_err = fault_at("lateerr", n_dma);                                    /* after the command was seen done */
    late_drop = fault_at("latedrop", n_dma);
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
                         if (late_drop == 2) { late_drop = 0; reg_sts &= ~STS_PCFG_DONE; }
                         if (v & 0x00001000u) {                               /* this read shows the command done */
                             if (late_err) { late_err = 0; reg_sts |= 0x00040000u; }
                             if (late_drop == 1) late_drop = 2;
                         }
                         if (polling && watch) printf("WATCH %u %u\n", n_dma, *watch);
                         break;
    case DEVCFG_STATUS:  v = reg_status; break;
    case SLCR_LVL_SHFTR_EN:  v = slcr_word[0]; break;
    case SLCR_FPGA_RST_CTRL: v = slcr_word[1]; break;
    case SLCR_FPGA0_CLK:     v = slcr_word[2]; break;
    case SLCR_PLL_STATUS:    v = slcr_word[3]; break;
    case PL_BASE + PL_ID:       v = fault_on("plid") ? 0x53324132u : PL_ID_WORD; break;
    case PL_BASE + PL_SCRATCH:  v = pl_scratch; break;
    case PL_BASE + PL_COUNT:    v = pl_count; if (!fault_on("countstuck")) pl_count += 37u; break;
    case PL_BASE + PL_RAM_ADDR: v = pl_ram_addr; break;
    case PL_BASE + PL_RAM_DATA: v = pl_ram[pl_ram_addr]; break;
    case PL_BASE + PL_SRL_ADDR: v = pl_srl_addr; break;
    case PL_BASE + PL_SRL_DATA: v = pl_srl[pl_srl_addr] ^ ((fault_on("srlmoves") && n_srl_reads++ >= SRL_DEPTH + 3u) ? 0x2u : 0u); break;
    case PL_BASE + PL_WRITES:   v = (pl_ram_writes + (fault_on("plcount") ? 1u : 0u)) | pl_srl_shifts << 16; break;
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
                          if (v == STS_SEU_ERR && fault_on("bit5stays")) reg_sts |= STS_SEU_ERR;
                          if (v == STS_SEU_ERR && fault_on("clearerr")) reg_sts |= 0x00040000u;
                          if (v != STS_CLEAR_MASK && v != STS_SEU_ERR) printf("VIOLATION INT_STS write %08x\n", v);
                          if (drop_on_next_clear) { drop_on_next_clear = 0; reg_sts &= ~STS_PCFG_DONE; }
                          break;
    case DEVCFG_DMA_SRC:  dma_src = v; break;
    case DEVCFG_DMA_DST:  dma_dst = v; break;
    case DEVCFG_DMA_SLEN: dma_slen = v; break;
    case DEVCFG_DMA_DLEN: dma_execute(v); polling = 1; break;
    case PL_BASE + PL_SCRATCH:  pl_scratch = fault_on("scratchstuck") ? v & ~0x00000080u : v; break;
    case PL_BASE + PL_RAM_ADDR: pl_ram_addr = v & (RAM_DEPTH - 1u); break;
    case PL_BASE + PL_RAM_DATA: pl_ram[pl_ram_addr] = (fault_on("ramstuck") && pl_ram_addr == 5u) ? v & 0xBu : v & 0xFu;
                                if (fault_on("ramwild")) pl_ram[(pl_ram_addr + 1u) & (RAM_DEPTH - 1u)] = v & 0xFu;
                                pl_ram_writes = (pl_ram_writes + 1u) & 0xFFFFu; break;
    case PL_BASE + PL_SRL_ADDR: pl_srl_addr = v & (SRL_DEPTH - 1u); break;
    case PL_BASE + PL_SRL_DATA: {                       /* a write shifts: the design does it, this prober must never ask for it */
                                    unsigned k;
                                    for (k = SRL_DEPTH - 1u; k > 0u; k--) pl_srl[k] = pl_srl[k - 1u];
                                    pl_srl[0] = v & 0xFu; pl_srl_shifts = (pl_srl_shifts + 1u) & 0xFFFFu;
                                    printf("VIOLATION shift %08x\n", v);
                                } break;
    default: printf("VIOLATION write %08x\n", a); break;
    }
}

uint32_t hal_mem_rd(uint32_t a)
{
    wait_over();
    if (!(in(a, RESULT_ADDR, RESULT_MAX_WORDS) || in(a, PARAM_ADDR, PARAM_WORDS) || in(a, DST_BUF, DATA2_WORDS)
          || in(a, LIST_ADDR, LIST_MAX)))
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
    if (argc >= 3 && !strcmp(argv[1], "genreg")) {      /* the stream that reads one word of register <n> of the prober's list */
        uint32_t f[FARRD_WORDS];
        sm_reg_read_stream((uint32_t)strtoul(argv[2], 0, 10), f);
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
            while (*s && n_succ < 96) {
                succ_from[n_succ] = (uint32_t)strtoul(s, &e, 16); if (*e != ':') return 2;
                succ_to[n_succ++] = (uint32_t)strtoul(e + 1, &e, 16);
                s = *e == ',' ? e + 1 : e;
                if (*e && *e != ',') return 2;
            }
        }
        if (getenv("SM_SHOWS")) {
            const char *s = getenv("SM_SHOWS"); char *e;
            while (*s && n_shows < 32) {
                shows_at[n_shows] = (uint32_t)strtoul(s, &e, 16); if (*e != ':') return 2;
                shows_what[n_shows++] = (uint32_t)strtoul(e + 1, &e, 16);
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
        if (getenv("SM_LIST") && load_words(getenv("SM_LIST"), &ddr[(LIST_ADDR - DDR_BASE) / 4u], LIST_MAX + 8u) < 0) return 2;
        if (getenv("SM_RAMMAP")) {
            FILE *m = fopen(getenv("SM_RAMMAP"), "r"); unsigned long a, b, c, d, e, g;
            if (!m) return 2;
            while (n_places < MAX_PLACES && fscanf(m, "%lu %lu %lx %lu %lu %lu", &a, &b, &c, &d, &e, &g) == 6) {
                if (a >= RAM_DEPTH || b >= 4u || d >= FRAME_WORDS || e >= 32u || g > 1u) return 2;
                place[n_places].addr = (uint32_t)a; place[n_places].mem = (uint32_t)b; place[n_places].far = (uint32_t)c;
                place[n_places].word = (uint32_t)d; place[n_places].bit = (uint32_t)e; place[n_places].inv = (uint32_t)g; n_places++;
            }
            fclose(m);
        }
        if (fault_on("ctrl"))   reg_ctrl &= ~0x08000000u;
        if (fault_on("lpbk"))   reg_mctrl |= MCTRL_PCAP_LPBK;
        if (fault_on("nodone")) reg_sts &= ~STS_PCFG_DONE;
        if (fault_on("dcache")) sctlr |= 0x4u;
        if (fault_on("seu"))    reg_ctrl |= CTRL_SEU_EN;
        if (fault_on("lvl"))     slcr_word[0] = 0x0000000Au;
        if (fault_on("fpgarst")) slcr_word[1] = 0x00000001u;
        if (fault_on("fclk"))    slcr_word[2] = 0x00200A00u;
        if (fault_on("pll"))     slcr_word[3] = 0x0000003Bu;
        for (i = 0; i < SRL_DEPTH; i++)                 /* what the design loads into its four shift registers (pl/s2a) */
            pl_srl[i] = (0xA5C30F69u >> i & 1u) | (0x0F1E2D3Cu >> i & 1u) << 1 | (0x13579BDFu >> i & 1u) << 2 | (0xFEDCBA98u >> i & 1u) << 3;
        if (getenv("SM_CREG")) {
            const char *s = getenv("SM_CREG"); char *e;
            while (*s) {
                uint32_t *which = !strncmp(s, "idcode:", 7) ? &creg_idcode : !strncmp(s, "ctl0:", 5) ? &creg_ctl0 : !strncmp(s, "stat:", 5) ? &creg_stat : 0;
                if (!which) return 2;
                *which = (uint32_t)strtoul(strchr(s, ':') + 1, &e, 16);
                s = *e == ',' ? e + 1 : e;
                if (*e && *e != ',') return 2;
            }
        }
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

/* ret2uboot — can a bare-metal function started by U-Boot's `go` return to U-Boot cleanly?
 *
 * It is the smallest version of the selfmap prober's frame: entered as entry(argc, argv) in
 * U-Boot's own context, it prints two lines on the console UART, takes a read-only snapshot
 * of the PS registers that decide whether the PS-to-PL path is usable, fills a DDR buffer
 * with a deterministic pattern, and returns 0. It never touches the PL, never writes a PS
 * register other than the UART TX FIFO, and issues no configuration command.
 *
 * Every device access goes through the four helpers below, so the same source built with
 * -DHOST_TWIN logs each access and tests/test_ret2uboot.py holds the log to the allow-list
 * before the image is allowed anywhere near a board.
 */
#include <stdint.h>

#define UART1_SR     0xE000102Cu          /* Cadence UART channel status */
#define UART1_FIFO   0xE0001030u
#define SR_TXEMPTY   (1u << 3)
#define SR_TXFULL    (1u << 4)

#define BUF_ADDR     0x10000000u          /* free DDR, far from the image (0x02000000) and from U-Boot (top of RAM) */
#define BUF_WORDS    0x4000u              /* 64 KiB */
#define PATTERN_AT   0x400u               /* word index where the pattern starts (byte 0x1000) */
#define MAGIC        0x30524D53u          /* "SMR0" */

enum { CPU_SCTLR, CPU_CPSR, CPU_SP, CPU_R9, CPU_N };

/* read-only snapshot: the SLCR and DEVCFG words that say whether the PL is configured and reachable */
static const uint32_t SNAPSHOT[] = {
    0xF800000Cu, /* SLCR_LOCKSTA   */
    0xF8000100u, /* ARM_PLL_CTRL   */
    0xF8000104u, /* DDR_PLL_CTRL   */
    0xF8000108u, /* IO_PLL_CTRL    */
    0xF800010Cu, /* PLL_STATUS     */
    0xF8000170u, /* FPGA0_CLK_CTRL */
    0xF8000240u, /* FPGA_RST_CTRL  */
    0xF8000900u, /* LVL_SHFTR_EN   */
    0xF8007000u, /* DEVCFG CTRL    */
    0xF8007004u, /* DEVCFG LOCK    */
    0xF800700Cu, /* DEVCFG INT_STS */
    0xF8007010u, /* DEVCFG INT_MASK*/
    0xF8007014u, /* DEVCFG STATUS  */
    0xF8007080u, /* DEVCFG MCTRL   */
};
#define SNAPSHOT_N (sizeof SNAPSHOT / sizeof SNAPSHOT[0])

#ifdef HOST_TWIN
#include <stdio.h>
static uint32_t twin_buf[BUF_WORDS];
static uint32_t mmio_read(uint32_t a)            { printf("R %08x\n", a); return a == UART1_SR ? SR_TXEMPTY : 0x5A000000u | (a & 0xFFFFu); }
static void     mmio_write(uint32_t a, uint32_t v) { printf("W %08x %08x\n", a, v); }
static void     buf_store(uint32_t i, uint32_t v)  { if (i >= BUF_WORDS) { printf("OOB %08x\n", i); return; } twin_buf[i] = v; }
static uint32_t cpu_read(int which)               { return 0xC0000000u | (uint32_t)which; }
#else
static inline uint32_t mmio_read(uint32_t a)             { return *(volatile uint32_t *)(uintptr_t)a; }
static inline void     mmio_write(uint32_t a, uint32_t v) { *(volatile uint32_t *)(uintptr_t)a = v; }
static inline void     buf_store(uint32_t i, uint32_t v)  { ((volatile uint32_t *)(uintptr_t)BUF_ADDR)[i] = v; }
static inline uint32_t cpu_read(int which)
{
    uint32_t v = 0;
    switch (which) {
    case CPU_SCTLR: __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(v)); break;
    case CPU_CPSR:  __asm__ volatile("mrs %0, cpsr" : "=r"(v)); break;
    case CPU_SP:    __asm__ volatile("mov %0, sp" : "=r"(v)); break;
    case CPU_R9:    __asm__ volatile("mov %0, r9" : "=r"(v)); break;   /* U-Boot's gd pointer: read, never written */
    default: break;
    }
    return v;
}
#endif

static void put(const char *s)
{
    for (; *s; s++) {
        while (mmio_read(UART1_SR) & SR_TXFULL) { }
        mmio_write(UART1_FIFO, (uint32_t)(unsigned char)*s);
    }
}

static void drain(void)
{
    while (!(mmio_read(UART1_SR) & SR_TXEMPTY)) { }
}

unsigned long selfmap_entry(int argc, char *const argv[]) __attribute__((section(".text.entry")));
unsigned long selfmap_entry(int argc, char *const argv[])
{
    uint32_t i, n = 0;
    (void)argc; (void)argv;

    put("SMR0 enter\r\n");

    buf_store(n++, MAGIC);
    buf_store(n++, 1u);                          /* record version */
    buf_store(n++, (uint32_t)SNAPSHOT_N);
    buf_store(n++, (uint32_t)CPU_N);
    for (i = 0; i < SNAPSHOT_N; i++) {
        buf_store(n++, SNAPSHOT[i]);
        buf_store(n++, mmio_read(SNAPSHOT[i]));
    }
    for (i = 0; i < CPU_N; i++)
        buf_store(n++, cpu_read((int)i));
    while (n < PATTERN_AT)
        buf_store(n++, 0u);
    for (i = PATTERN_AT; i < BUF_WORDS; i++)
        buf_store(i, 0x9E3779B9u * (i + 1u));

    put("SMR0 exit rc=0\r\n");
    drain();
    return 0;
}

#ifdef HOST_TWIN
int main(int argc, char **argv)
{
    unsigned long rc = selfmap_entry(0, 0);
    printf("RC %lx\n", rc);
    if (argc > 1) {
        FILE *f = fopen(argv[1], "wb");
        if (!f || fwrite(twin_buf, sizeof twin_buf, 1, f) != 1) return 2;
        fclose(f);
    }
    return 0;
}
#endif

/* zynq-selfmap prober — the board side: the entry U-Boot's `go` calls, and the hardware doors.
 * Runs in U-Boot's context (its stack; r9 is its gd and is never written; no VFP; no mode change). */
#include "sm.h"

#define UART1_SR     0xE000102Cu
#define UART1_FIFO   0xE0001030u
#define SR_TXEMPTY   (1u << 3)
#define SR_TXFULL    (1u << 4)

uint32_t hal_rd(uint32_t addr)                  { return *(volatile uint32_t *)(uintptr_t)addr; }
void     hal_wr(uint32_t addr, uint32_t value)  { *(volatile uint32_t *)(uintptr_t)addr = value; }
uint32_t hal_mem_rd(uint32_t addr)              { return *(volatile uint32_t *)(uintptr_t)addr; }
void     hal_mem_wr(uint32_t addr, uint32_t value) { *(volatile uint32_t *)(uintptr_t)addr = value; }

void     hal_watch(const uint32_t *polls)       { (void)polls; }

uint32_t hal_cpu(int which)
{
    uint32_t v = 0;
    switch (which) {
    case CPU_SCTLR: __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(v)); break;
    case CPU_CPSR:  __asm__ volatile("mrs %0, cpsr" : "=r"(v)); break;
    case CPU_SP:    __asm__ volatile("mov %0, sp" : "=r"(v)); break;
    case CPU_R9:    __asm__ volatile("mov %0, r9" : "=r"(v)); break;
    default: break;
    }
    return v;
}

void hal_putc(char c)
{
    while (hal_rd(UART1_SR) & SR_TXFULL) { }
    hal_wr(UART1_FIFO, (uint32_t)(unsigned char)c);
}

unsigned long selfmap_entry(int argc, char *const argv[]) __attribute__((section(".text.entry")));
unsigned long selfmap_entry(int argc, char *const argv[])
{
    unsigned long rc;
    (void)argc; (void)argv;
    rc = sm_run();
    while (!(hal_rd(UART1_SR) & SR_TXEMPTY)) { }
    return rc;
}

/* the prober: a function called by U-Boot's `go`, linked at its load address. No startup code:
 * it runs on U-Boot's stack, under U-Boot's MMU and caches, and returns to U-Boot. */
ENTRY(selfmap_entry)
SECTIONS
{
    . = 0x02000000;
    .text   : { KEEP(*(.text.entry)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    .bss    : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}

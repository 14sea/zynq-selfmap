# ret2uboot: the host twin (any cc) and the board image (the pinned xPack ARM toolchain).
# Products go to the top-level ignored build/ directory.
BUILD ?= $(abspath $(CURDIR)/../../build/ret2uboot)
XGCC  ?= /home/test/zynq_psoracle/toolchain/xpack-arm-none-eabi-gcc-14.2.1-1.1/bin/arm-none-eabi-gcc
XPFX   = $(XGCC:gcc=)
# soft float and general registers only: U-Boot does not enable the VFP. r9 is U-Boot's gd pointer.
XFLAGS = -mcpu=cortex-a9 -marm -mfloat-abi=soft -mgeneral-regs-only -ffixed-r9 -mno-unaligned-access \
         -std=c99 -Os -ffreestanding -fno-builtin -fno-pic -nostdlib -nostartfiles \
         -Wall -Wextra -Werror

all: twin image
twin: $(BUILD)/ret2uboot_twin
image: $(BUILD)/ret2uboot.bin

$(BUILD)/ret2uboot_twin: ret2uboot.c
	@mkdir -p $(BUILD)
	$(CC) -std=c99 -O1 -Wall -Wextra -Werror -DHOST_TWIN -o $@ $<

$(BUILD)/ret2uboot.elf: ret2uboot.c link.ld
	@mkdir -p $(BUILD)
	$(XGCC) $(XFLAGS) -T link.ld -Wl,--build-id=none -o $@ ret2uboot.c

$(BUILD)/ret2uboot.bin: $(BUILD)/ret2uboot.elf
	$(XPFX)objcopy -O binary $< $@
	$(XPFX)objdump -d $< > $(BUILD)/ret2uboot.dis
	$(XPFX)size -A $< > $(BUILD)/ret2uboot.size

.PHONY: all twin image

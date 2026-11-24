# The prober: the host twin (any cc) and the board image (the pinned xPack ARM toolchain).
BUILD ?= $(abspath $(CURDIR)/../build/prober)
# The toolchain is looked for beside this repository, where the project it was pinned in keeps it; XGCC=... names another place.
XGCC  ?= $(abspath $(CURDIR)/../../zynq_psoracle/toolchain/xpack-arm-none-eabi-gcc-14.2.1-1.1/bin/arm-none-eabi-gcc)
XPFX   = $(XGCC:gcc=)
XFLAGS = -mcpu=cortex-a9 -marm -mfloat-abi=soft -mgeneral-regs-only -ffixed-r9 -mno-unaligned-access \
         -std=c99 -Os -ffreestanding -fno-builtin -fno-pic -nostdlib -nostartfiles \
         -Wall -Wextra -Werror

all: twin image
twin: $(BUILD)/twin
image: $(BUILD)/prober.bin

$(BUILD)/twin: sm_core.c twin_hal.c sm.h
	@mkdir -p $(BUILD)
	$(CC) -std=c99 -O1 -g -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L -o $@ sm_core.c twin_hal.c

$(BUILD)/prober.elf: sm_board.c sm_core.c sm.h link.ld
	@mkdir -p $(BUILD)
	$(XGCC) $(XFLAGS) -T link.ld -Wl,--build-id=none -o $@ sm_board.c sm_core.c

$(BUILD)/prober.bin: $(BUILD)/prober.elf
	$(XPFX)objcopy -O binary $< $@
	$(XPFX)objdump -d $< > $(BUILD)/prober.dis
	$(XPFX)size -A $< > $(BUILD)/prober.size

# the twin with the address and undefined-behaviour sanitizers: the twin looks into the prober's stack (hal_watch)
twin_asan: $(BUILD)/twin_asan
$(BUILD)/twin_asan: sm_core.c twin_hal.c sm.h
	@mkdir -p $(BUILD)
	$(CC) -std=c99 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L -o $@ sm_core.c twin_hal.c

# Where the compiler is looked for from here. A copy of this tree in another place does not find it by itself and is given
# this as XGCC (tests/mutants.py does so for its scratch copies).
xgcc:
	@echo $(XGCC)

.PHONY: all twin twin_asan image xgcc

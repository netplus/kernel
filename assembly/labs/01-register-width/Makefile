AS      := as
LD      := ld
CC      := gcc
OBJDUMP := objdump

ASFLAGS := --64 -g
CFLAGS  := -Wall -Wextra -Werror -g

.PHONY: all run disasm disasm-intel companion clean

all: register_width companion-O0.s companion-Og.s companion-O2.s

register_width: register_width.o
	$(LD) $< -o $@

register_width.o: register_width.s
	$(AS) $(ASFLAGS) $< -o $@

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -fno-omit-frame-pointer -S $< -o $@

companion-Og.s: companion.c
	$(CC) $(CFLAGS) -Og -fno-omit-frame-pointer -S $< -o $@

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S $< -o $@

run: register_width
	./register_width; status=$$?; echo "exit status: $$status (expected 120 / 0x78)"

disasm: register_width
	$(OBJDUMP) -dr $<

disasm-intel: register_width
	$(OBJDUMP) -dr -Mintel $<

companion: companion-O0.s companion-Og.s companion-O2.s
	@printf '%s\n' 'generated: companion-O0.s companion-Og.s companion-O2.s'

clean:
	rm -f register_width register_width.o companion-O0.s companion-Og.s companion-O2.s

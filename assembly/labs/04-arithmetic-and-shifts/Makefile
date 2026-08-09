CC := gcc
AS := as
LD := ld
CFLAGS := -Wall -Wextra -g -fno-omit-frame-pointer -fno-stack-protector -no-pie

.PHONY: all clean run disasm c-asm gdb

all: arithmetic-and-shifts companion-O0.s companion-O2.s

arithmetic_and_shifts.o: arithmetic_and_shifts.s
	$(AS) --64 -g -o $@ $<

arithmetic-and-shifts: arithmetic_and_shifts.o
	$(LD) -o $@ $<

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -S -o $@ $<

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S -o $@ $<

run: arithmetic-and-shifts
	@set +e; ./arithmetic-and-shifts; status=$$?; set -e; \
	echo "exit status=$$status (expected 189)"; \
	test $$status -eq 189

disasm: arithmetic-and-shifts
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS arithmetic-and-shifts
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel arithmetic-and-shifts

c-asm: companion-O0.s companion-O2.s
	@printf '\n===== companion.c -O0 =====\n'
	@cat companion-O0.s
	@printf '\n===== companion.c -O2 =====\n'
	@cat companion-O2.s

gdb: arithmetic-and-shifts
	gdb -q -x gdb.cmd ./arithmetic-and-shifts

clean:
	rm -f arithmetic-and-shifts arithmetic_and_shifts.o companion-O0.s companion-O2.s

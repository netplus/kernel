CC := gcc
AS := as
LD := ld
CFLAGS := -Wall -Wextra -g -fno-omit-frame-pointer -fno-stack-protector -no-pie

.PHONY: all clean disasm run c-asm gdb

all: addressing companion-O0.s companion-O2.s

addressing.o: addressing.s
	$(AS) --64 -g -o $@ $<

addressing: addressing.o
	$(LD) -o $@ $<

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -S -o $@ $<

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S -o $@ $<

disasm: addressing
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS addressing
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel addressing

run: addressing
	@set +e; ./addressing; status=$$?; set -e; \
	echo "exit status=$$status (expected 15)"; \
	test $$status -eq 15

c-asm: companion-O0.s companion-O2.s
	@printf '\n===== companion.c -O0 =====\n'
	@cat companion-O0.s
	@printf '\n===== companion.c -O2 =====\n'
	@cat companion-O2.s

gdb: addressing
	gdb -q -x gdb.cmd ./addressing

clean:
	rm -f addressing addressing.o companion-O0.s companion-O2.s

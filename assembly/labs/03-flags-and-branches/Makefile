CC := gcc
AS := as
LD := ld
CFLAGS := -Wall -Wextra -g -fno-omit-frame-pointer -fno-stack-protector -no-pie

.PHONY: all clean run disasm c-asm gdb

all: flags-and-branches companion-O0.s companion-O2.s

flags_and_branches.o: flags_and_branches.s
	$(AS) --64 -g -o $@ $<

flags-and-branches: flags_and_branches.o
	$(LD) -o $@ $<

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -S -o $@ $<

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S -o $@ $<

run: flags-and-branches
	@set +e; ./flags-and-branches; status=$$?; set -e; \
	echo "exit status=$$status (expected 18)"; \
	test $$status -eq 18

disasm: flags-and-branches
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS flags-and-branches
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel flags-and-branches

c-asm: companion-O0.s companion-O2.s
	@printf '\n===== companion.c -O0 =====\n'
	@cat companion-O0.s
	@printf '\n===== companion.c -O2 =====\n'
	@cat companion-O2.s

gdb: flags-and-branches
	gdb -q -x gdb.cmd ./flags-and-branches

clean:
	rm -f flags-and-branches flags_and_branches.o companion-O0.s companion-O2.s

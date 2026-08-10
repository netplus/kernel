CC := gcc
AS := as
LD := ld
CFLAGS := -Wall -Wextra -g -fno-omit-frame-pointer -fno-stack-protector -no-pie

.PHONY: all clean run disasm symbols c-asm gdb

all: indirect-call companion-O0.s companion-O2.s

indirect_call.o: indirect_call.s
	$(AS) --64 -g -o $@ $<

indirect-call: indirect_call.o
	$(LD) -o $@ $<

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -S -o $@ $<

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S -o $@ $<

run: indirect-call
	@set +e; ./indirect-call; status=$$?; set -e; \
	echo "exit status=$$status (expected 46)"; \
	test $$status -eq 46

disasm: indirect-call
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS indirect-call
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel indirect-call

symbols: indirect-call
	nm -n indirect-call

c-asm: companion-O0.s companion-O2.s
	@printf '\n===== companion.c -O0 =====\n'
	@cat companion-O0.s
	@printf '\n===== companion.c -O2 =====\n'
	@cat companion-O2.s

gdb: indirect-call
	gdb -q -x gdb.cmd ./indirect-call

clean:
	rm -f indirect-call indirect_call.o companion-O0.s companion-O2.s

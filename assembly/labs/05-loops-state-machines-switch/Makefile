CC := gcc
AS := as
LD := ld
CFLAGS := -Wall -Wextra -g -fno-omit-frame-pointer -fno-stack-protector -no-pie

.PHONY: all clean run disasm c-asm gdb symbols

all: control-flow companion-O0.s companion-O2.s

control_flow.o: control_flow.s
	$(AS) --64 -g -o $@ $<

control-flow: control_flow.o
	$(LD) -o $@ $<

companion-O0.s: companion.c
	$(CC) $(CFLAGS) -O0 -S -o $@ $<

companion-O2.s: companion.c
	$(CC) $(CFLAGS) -O2 -S -o $@ $<

run: control-flow
	@set +e; ./control-flow; status=$$?; set -e; \
	echo "exit status=$$status (expected 74)"; \
	test $$status -eq 74

disasm: control-flow
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS control-flow
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel control-flow

c-asm: companion-O0.s companion-O2.s
	@printf '\n===== companion.c -O0 =====\n'
	@cat companion-O0.s
	@printf '\n===== companion.c -O2 =====\n'
	@cat companion-O2.s

symbols: control-flow
	nm -n control-flow | grep -E '(_start|after_)'

gdb: control-flow
	gdb -q -x gdb.cmd ./control-flow

clean:
	rm -f control-flow control_flow.o companion-O0.s companion-O2.s

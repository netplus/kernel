AS := as
LD := ld

.PHONY: all run disasm symbols gdb clean

all: initial-stack

initial_stack.o: initial_stack.s
	$(AS) --64 -g -o $@ $<

initial-stack: initial_stack.o
	$(LD) -o $@ $<

run: initial-stack
	@set +e; env -i DEMO=1 ./initial-stack alpha beta; status=$$?; set -e; \
	echo "exit status=$$status (expected 63)"; \
	test $$status -eq 63

disasm: initial-stack
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS initial-stack
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel initial-stack

symbols: initial-stack
	nm -n initial-stack
	readelf -h initial-stack

gdb: initial-stack
	gdb -q -x gdb.cmd ./initial-stack

clean:
	rm -f initial-stack initial_stack.o

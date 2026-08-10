AS := as
LD := ld

.PHONY: all clean run disasm symbols gdb

all: recursive-call

recursive_call.o: recursive_call.s
	$(AS) --64 -g -o $@ $<

recursive-call: recursive_call.o
	$(LD) -o $@ $<

run: recursive-call
	@set +e; ./recursive-call; status=$$?; set -e; \
	echo "exit status=$$status (expected 6)"; \
	test $$status -eq 6

disasm: recursive-call
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS recursive-call
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel recursive-call

symbols: recursive-call
	nm -n recursive-call

gdb: recursive-call
	gdb -q -x gdb.cmd ./recursive-call

clean:
	rm -f recursive-call recursive_call.o

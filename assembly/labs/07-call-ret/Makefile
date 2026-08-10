AS := as
LD := ld

.PHONY: all clean run disasm symbols gdb

all: call-ret

call_ret.o: call_ret.s
	$(AS) --64 -g -o $@ $<

call-ret: call_ret.o
	$(LD) -o $@ $<

run: call-ret
	@set +e; ./call-ret; status=$$?; set -e; \
	echo "exit status=$$status (expected 37)"; \
	test $$status -eq 37

disasm: call-ret
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS call-ret
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel call-ret

symbols: call-ret
	nm -n call-ret

gdb: call-ret
	gdb -q -x gdb.cmd ./call-ret

clean:
	rm -f call-ret call_ret.o

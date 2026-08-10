AS := as
LD := ld

.PHONY: all clean run disasm symbols gdb

all: stack-push-pop

stack_push_pop.o: stack_push_pop.s
	$(AS) --64 -g -o $@ $<

stack-push-pop: stack_push_pop.o
	$(LD) -o $@ $<

run: stack-push-pop
	@set +e; ./stack-push-pop; status=$$?; set -e; \
	echo "exit status=$$status (expected 42)"; \
	test $$status -eq 42

disasm: stack-push-pop
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS stack-push-pop
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel stack-push-pop

symbols: stack-push-pop
	nm -n stack-push-pop | grep -E '(_start|stack_after|manual_after)'

gdb: stack-push-pop
	gdb -q -x gdb.cmd ./stack-push-pop

clean:
	rm -f stack-push-pop stack_push_pop.o

AS := as
LD := ld

.PHONY: all clean run disasm symbols gdb

all: return-address-corruption

return_address_corruption.o: return_address_corruption.s
	$(AS) --64 -g -o $@ $<

return-address-corruption: return_address_corruption.o
	$(LD) -o $@ $<

run: return-address-corruption
	@set +e; ./return-address-corruption; status=$$?; set -e; \
	echo "exit status=$$status (expected 41)"; \
	test $$status -eq 41

disasm: return-address-corruption
	@printf '\n===== AT&T syntax =====\n'
	objdump -drS return-address-corruption
	@printf '\n===== Intel syntax =====\n'
	objdump -drS -Mintel return-address-corruption

symbols: return-address-corruption
	nm -n return-address-corruption

gdb: return-address-corruption
	gdb -q -x gdb.cmd ./return-address-corruption

clean:
	rm -f return-address-corruption return_address_corruption.o

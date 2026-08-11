CC ?= gcc
LD ?= ld
CFLAGS := -O0 -fno-pie -fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Wextra

.PHONY: all clean check inspect

all: linked.elf

part1.o: part1.c
	$(CC) $(CFLAGS) -c -o $@ $<

part2.o: part2.c
	$(CC) $(CFLAGS) -c -o $@ $<

start.o: start.S
	$(CC) -c -o $@ $<

linked.elf: start.o part1.o part2.o
	$(LD) -o $@ -e _start -Map=linked.map $^

check: linked.elf
	./linked.elf; status=$$?; test $$status -eq 37; echo "exit_status=$$status"

inspect: linked.elf
	@echo '=== input sections ==='
	readelf -SW part1.o part2.o
	@echo '=== input symbols ==='
	readelf -Ws start.o part1.o part2.o
	@echo '=== input relocations ==='
	readelf -Wr start.o part1.o part2.o
	@echo '=== input disassembly + relocations ==='
	objdump -dr start.o part1.o part2.o
	@echo '=== output sections / segments ==='
	readelf -SW linked.elf
	readelf -lW linked.elf
	@echo '=== final symbols ==='
	nm -n linked.elf
	@echo '=== output relocations ==='
	readelf -Wr linked.elf
	@echo '=== final disassembly ==='
	objdump -d linked.elf
	@echo '=== linker map contributions ==='
	grep -E '(^ \.text|^ \.data|start\.o|part1\.o|part2\.o)' linked.map

clean:
	rm -f *.o linked.elf linked.map

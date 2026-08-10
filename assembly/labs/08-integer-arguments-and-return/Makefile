CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -g -fno-pie
LDFLAGS_COMMON := -no-pie

.PHONY: all clean run disasm

all: abi_probe_O0 abi_probe_O2

abi_probe_O0: main.c abi_probe.S
	$(CC) $(CFLAGS_COMMON) -O0 $(LDFLAGS_COMMON) -o $@ $^

abi_probe_O2: main.c abi_probe.S
	$(CC) $(CFLAGS_COMMON) -O2 $(LDFLAGS_COMMON) -o $@ $^

run: all
	./abi_probe_O0
	./abi_probe_O2

disasm: all
	objdump -drwC abi_probe_O0 > abi_probe_O0.att.txt
	objdump -drwC -Mintel abi_probe_O0 > abi_probe_O0.intel.txt
	objdump -drwC abi_probe_O2 > abi_probe_O2.att.txt
	objdump -drwC -Mintel abi_probe_O2 > abi_probe_O2.intel.txt

clean:
	rm -f abi_probe_O0 abi_probe_O2 *.txt

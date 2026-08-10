CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -Werror -fno-pie -no-pie

all: preservation_O0 preservation_O2

preservation_O0: main.c preservation_probe.S
	$(CC) $(CFLAGS_COMMON) -O0 -g -o $@ $^

preservation_O2: main.c preservation_probe.S
	$(CC) $(CFLAGS_COMMON) -O2 -g -o $@ $^

run: all
	./preservation_O0
	./preservation_O2

disasm: all
	objdump -drwC preservation_O0 > preservation_O0.att.txt
	objdump -drwC -Mintel preservation_O0 > preservation_O0.intel.txt
	objdump -drwC preservation_O2 > preservation_O2.att.txt
	objdump -drwC -Mintel preservation_O2 > preservation_O2.intel.txt

symbols: all
	nm -n preservation_O0

clean:
	rm -f preservation_O0 preservation_O2 *.txt

.PHONY: all run disasm symbols clean

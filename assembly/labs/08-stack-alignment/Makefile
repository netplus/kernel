CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -std=c11 -fno-pie
LDFLAGS_COMMON := -no-pie

all: align_O0 align_O2

align_O0: main.c probe.S
	$(CC) $(CFLAGS_COMMON) -O0 $^ $(LDFLAGS_COMMON) -o $@

align_O2: main.c probe.S
	$(CC) $(CFLAGS_COMMON) -O2 $^ $(LDFLAGS_COMMON) -o $@

run: all
	./align_O0
	./align_O2

disasm: all
	objdump -drwC align_O0 > align_O0.att.txt
	objdump -drwC -Mintel align_O0 > align_O0.intel.txt
	objdump -drwC align_O2 > align_O2.att.txt
	objdump -drwC -Mintel align_O2 > align_O2.intel.txt

symbols: all
	nm -n align_O0 | grep -E 'probe_alignment|nested_probe|seen_'
	readelf -Ws align_O0 | grep -E 'probe_alignment|nested_probe|seen_'

clean:
	rm -f align_O0 align_O2 *.txt

.PHONY: all run disasm symbols clean

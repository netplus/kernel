CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -Werror -fno-pie -no-pie

.PHONY: all run verify clean

all: mixed-o0 mixed-o2

mixed-o0: driver.c funcs.S
	$(CC) $(CFLAGS_COMMON) -O0 $^ -o $@

mixed-o2: driver.c funcs.S
	$(CC) $(CFLAGS_COMMON) -O2 $^ -o $@

run: all
	./mixed-o0
	./mixed-o2

verify: run
	objdump -drwC mixed-o0 > mixed-o0.att.txt
	objdump -drwC -Mintel mixed-o0 > mixed-o0.intel.txt
	nm -n mixed-o0 > mixed-o0.nm.txt
	readelf -sW mixed-o0 > mixed-o0.symbols.txt
	grep -A5 '<mixed_bump>:' mixed-o0.att.txt
	grep -A5 '<mixed_bump>:' mixed-o0.intel.txt
	grep ' mixed_bump$$' mixed-o0.nm.txt
	grep 'mixed_bump' mixed-o0.symbols.txt

clean:
	rm -f mixed-o0 mixed-o2 *.txt

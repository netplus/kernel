CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -fno-pie -no-pie

.PHONY: all run verify clean

all: aggregate-o0 aggregate-o2

aggregate-o0: driver.c funcs.S
	$(CC) $(CFLAGS_COMMON) -O0 $^ -o $@

aggregate-o2: driver.c funcs.S
	$(CC) $(CFLAGS_COMMON) -O2 $^ -o $@

run: all
	./aggregate-o0
	./aggregate-o2

verify: run
	objdump -drwC aggregate-o0 > aggregate-o0.att.txt
	objdump -drwC -Mintel aggregate-o0 > aggregate-o0.intel.txt
	nm -n aggregate-o0 > aggregate-o0.nm.txt
	readelf -sW aggregate-o0 > aggregate-o0.symbols.txt
	grep -A4 '<pair_bump>:' aggregate-o0.att.txt
	grep -A14 '<big_bump>:' aggregate-o0.att.txt

clean:
	rm -f aggregate-o0 aggregate-o2 *.txt

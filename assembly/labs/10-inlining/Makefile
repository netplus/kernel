CC ?= gcc
CFLAGS_COMMON := -std=c11 -Wall -Wextra -fno-pie -no-pie

.PHONY: all run inspect clean

all: demo-O0 demo-Og demo-O2

demo-O0: inline_demo.c
	$(CC) $(CFLAGS_COMMON) -O0 $< -o $@

demo-Og: inline_demo.c
	$(CC) $(CFLAGS_COMMON) -Og $< -o $@

demo-O2: inline_demo.c
	$(CC) $(CFLAGS_COMMON) -O2 $< -o $@

run: all
	./demo-O0
	./demo-Og
	./demo-O2

inspect: all
	@echo '=== AT&T: use_inline ==='
	objdump -dr demo-O0 | sed -n '/<use_inline>:/,/^$$/p'
	objdump -dr demo-Og | sed -n '/<use_inline>:/,/^$$/p'
	objdump -dr demo-O2 | sed -n '/<use_inline>:/,/^$$/p'
	@echo '=== Intel: use_inline ==='
	objdump -dr -Mintel demo-O0 | sed -n '/<use_inline>:/,/^$$/p'
	objdump -dr -Mintel demo-Og | sed -n '/<use_inline>:/,/^$$/p'
	objdump -dr -Mintel demo-O2 | sed -n '/<use_inline>:/,/^$$/p'
	@echo '=== O2 noinline control ==='
	objdump -dr demo-O2 | sed -n '/<use_noinline>:/,/^$$/p'
	@echo '=== symbols ==='
	nm -n demo-O0 | grep -E 'inline_helper|noinline_helper|use_inline|use_noinline'
	nm -n demo-O2 | grep -E 'inline_helper|noinline_helper|use_inline|use_noinline'
	readelf -h demo-O2 | grep -E 'Class:|Machine:'

clean:
	rm -f demo-O0 demo-Og demo-O2

CC ?= gcc
CFLAGS_COMMON := -std=c11 -Wall -Wextra -Werror -fno-pie
LDFLAGS_COMMON := -no-pie

.PHONY: all run inspect clean

all: demo-O0 demo-Og demo-O2 demo-O2-nosib

demo-O0: tail_call.c
	$(CC) $(CFLAGS_COMMON) -O0 $< $(LDFLAGS_COMMON) -o $@

demo-Og: tail_call.c
	$(CC) $(CFLAGS_COMMON) -Og $< $(LDFLAGS_COMMON) -o $@

demo-O2: tail_call.c
	$(CC) $(CFLAGS_COMMON) -O2 $< $(LDFLAGS_COMMON) -o $@

demo-O2-nosib: tail_call.c
	$(CC) $(CFLAGS_COMMON) -O2 -fno-optimize-sibling-calls $< $(LDFLAGS_COMMON) -o $@

run: all
	./demo-O0
	./demo-Og
	./demo-O2
	./demo-O2-nosib

inspect: all
	@echo '== AT&T: O0 tail_wrapper =='
	objdump -drwC demo-O0 | sed -n '/<tail_wrapper>:/,/^$$/p'
	@echo '== AT&T: O2 tail_wrapper =='
	objdump -drwC demo-O2 | sed -n '/<tail_wrapper>:/,/^$$/p'
	@echo '== AT&T: O2 non_tail_wrapper =='
	objdump -drwC demo-O2 | sed -n '/<non_tail_wrapper>:/,/^$$/p'
	@echo '== AT&T: O2 with sibling-call optimization disabled =='
	objdump -drwC demo-O2-nosib | sed -n '/<tail_wrapper>:/,/^$$/p'
	@echo '== Intel: O2 wrappers =='
	objdump -drwC -Mintel demo-O2 | sed -n '/<tail_wrapper>:/,/^$$/p;/<non_tail_wrapper>:/,/^$$/p'
	@echo '== symbols =='
	nm -n demo-O2 | grep -E 'tail_target|tail_wrapper|non_tail_wrapper'
	@echo '== ELF header =='
	readelf -h demo-O2 | grep -E 'Class:|Type:|Machine:'

clean:
	rm -f demo-O0 demo-Og demo-O2 demo-O2-nosib

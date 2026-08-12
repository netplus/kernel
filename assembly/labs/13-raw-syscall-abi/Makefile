CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra

all: syscall-demo

syscall-demo: main.o syscall_demo.o
	$(CC) -o $@ $^

main.o: main.c
	$(CC) $(CFLAGS) -c -o $@ $<

syscall_demo.o: syscall_demo.S
	$(CC) -c -o $@ $<

check: syscall-demo
	./syscall-demo
	objdump -dr syscall_demo.o
	objdump -d --no-show-raw-insn syscall-demo | sed -n '/<raw_mmap>:/,/^$$/p'

clean:
	rm -f *.o syscall-demo

.PHONY: all check clean

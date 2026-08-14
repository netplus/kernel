CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra -pthread

all: atomic_rmw

atomic_rmw: atomic_rmw.c
	$(CC) $(CFLAGS) -o $@ $<

check-disasm: atomic_rmw
	objdump -dr -Mintel atomic_rmw | grep -E 'xchg|cmpxchg|xadd'
	objdump -dr atomic_rmw | grep -E 'xchg|cmpxchg|xadd'

run: atomic_rmw
	./atomic_rmw

clean:
	rm -f atomic_rmw

.PHONY: all check-disasm run clean

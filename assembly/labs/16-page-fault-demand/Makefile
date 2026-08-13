CC ?= gcc
CFLAGS ?= -O0 -g3 -Wall -Wextra -Werror -fno-omit-frame-pointer

all: demand_fault

demand_fault: demand_fault.c
	$(CC) $(CFLAGS) -o demand_fault demand_fault.c

check: demand_fault
	./demand_fault
	objdump -drwC -Mintel demand_fault

clean:
	rm -f demand_fault

.PHONY: all check clean

CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra -Werror -std=gnu11

.PHONY: all run disasm-att disasm-intel clean

all: constraints

constraints: constraints.c
	$(CC) $(CFLAGS) -o $@ $<

run: constraints
	./constraints

disasm-att: constraints
	objdump -drwC constraints > constraints.att.txt

disasm-intel: constraints
	objdump -drwC -Mintel constraints > constraints.intel.txt

clean:
	rm -f constraints constraints.att.txt constraints.intel.txt

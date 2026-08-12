CC ?= gcc
CFLAGS ?= -O0 -g3 -Wall -Wextra -Werror -fno-omit-frame-pointer

.PHONY: all run disasm clean

all: trigger

trigger: trigger.c
	$(CC) $(CFLAGS) -o $@ $<

run: trigger
	./trigger

disasm: trigger
	objdump -drwC -Mintel trigger | sed -n '/<trigger_de>:/,/^$/p; /<trigger_gp>:/,/^$/p'

clean:
	rm -f trigger

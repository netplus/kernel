CC ?= gcc
CFLAGS ?= -g -O1 -fno-omit-frame-pointer -fno-optimize-sibling-calls
LDFLAGS ?= -rdynamic

.PHONY: all run inspect clean

all: unwind-demo

unwind-demo: driver.c frames.S
	$(CC) $(CFLAGS) $(LDFLAGS) driver.c frames.S -o $@

run: unwind-demo
	./unwind-demo good
	./unwind-demo missing
	./unwind-demo wrong

inspect: unwind-demo
	objdump -drwC unwind-demo
	objdump -drwC -Mintel unwind-demo
	readelf -S unwind-demo | grep -E '\.(eh_frame|debug_frame)'
	readelf --debug-dump=frames unwind-demo
	nm -n unwind-demo | grep -E 'capture_trace|good_frame|missing_frame|wrong_frame'

clean:
	rm -f unwind-demo

CC ?= gcc
CFLAGS ?= -O0 -fno-pie -Wall -Wextra
LDFLAGS ?= -no-pie

.PHONY: all clean check inspect

all: reloc_demo

caller.o: caller.c
	$(CC) $(CFLAGS) -c $< -o $@

provider.o: provider.c
	$(CC) $(CFLAGS) -c $< -o $@

main.o: main.c
	$(CC) $(CFLAGS) -c $< -o $@

reloc_demo: main.o caller.o provider.o
	$(CC) $(LDFLAGS) $^ -o $@

check: reloc_demo
	./reloc_demo

inspect: caller.o reloc_demo
	readelf -Wr caller.o
	objdump -dr caller.o
	readelf -Ws caller.o | grep -E 'call_target|target|ext_data'
	objdump -d reloc_demo | sed -n '/<call_target>:/,+18p'

clean:
	rm -f *.o reloc_demo

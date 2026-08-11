CC ?= gcc
CFLAGS ?= -O0 -g -fno-pie
LDFLAGS ?= -no-pie

all: symbol_demo

symbol_demo.o: symbol_demo.c
	$(CC) $(CFLAGS) -c $< -o $@

provider.o: provider.c
	$(CC) $(CFLAGS) -c $< -o $@

symbol_demo: symbol_demo.o provider.o
	$(CC) $^ $(LDFLAGS) -o $@

inspect: symbol_demo
	readelf -W -S symbol_demo.o
	readelf -W -s symbol_demo.o
	nm -a symbol_demo.o
	readelf -W -s symbol_demo
	nm -n symbol_demo | grep -E 'local_counter|global_counter|external_counter|local_add|exported_add|external_add|main'

clean:
	rm -f symbol_demo.o provider.o symbol_demo

CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -std=c11 -g -fno-pie -fno-omit-frame-pointer
LDFLAGS_COMMON := -no-pie

.PHONY: all clean run inspect

all: debug-O0 debug-Og debug-O2

debug-O0: main.c
	$(CC) $(CFLAGS_COMMON) -O0 $< $(LDFLAGS_COMMON) -o $@

debug-Og: main.c
	$(CC) $(CFLAGS_COMMON) -Og $< $(LDFLAGS_COMMON) -o $@

debug-O2: main.c
	$(CC) $(CFLAGS_COMMON) -O2 $< $(LDFLAGS_COMMON) -o $@

run: all
	./debug-O0
	./debug-Og
	./debug-O2

inspect: all
	objdump -dr --source --line-numbers debug-O0
	objdump -dr --source --line-numbers debug-Og
	objdump -dr --source --line-numbers debug-O2
	objdump -dr -Mintel debug-O2
	readelf --debug-dump=decodedline debug-O2
	readelf --debug-dump=info debug-O2
	readelf --debug-dump=loc debug-O2
	nm -n debug-O2
	readelf -h debug-O2

clean:
	rm -f debug-O0 debug-Og debug-O2

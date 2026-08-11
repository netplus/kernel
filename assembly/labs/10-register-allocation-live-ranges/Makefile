CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -std=c11 -fno-pie -fno-omit-frame-pointer
LDFLAGS_COMMON := -no-pie

.PHONY: all clean run inspect

all: regalloc-O0 regalloc-Og regalloc-O2

regalloc-O0: main.c opaque.c
	$(CC) $(CFLAGS_COMMON) -O0 main.c opaque.c $(LDFLAGS_COMMON) -o $@

regalloc-Og: main.c opaque.c
	$(CC) $(CFLAGS_COMMON) -Og main.c opaque.c $(LDFLAGS_COMMON) -o $@

regalloc-O2: main.c opaque.c
	$(CC) $(CFLAGS_COMMON) -O2 -c main.c -o main-O2.o
	$(CC) $(CFLAGS_COMMON) -O2 -c opaque.c -o opaque-O2.o
	$(CC) main-O2.o opaque-O2.o $(LDFLAGS_COMMON) -o $@

run: all
	./regalloc-O0
	./regalloc-Og
	./regalloc-O2

inspect: all
	objdump -dr regalloc-O0
	objdump -dr regalloc-Og
	objdump -dr regalloc-O2
	objdump -dr -Mintel regalloc-O2
	nm -n regalloc-O2
	readelf -h regalloc-O2

clean:
	rm -f regalloc-O0 regalloc-Og regalloc-O2 main-O2.o opaque-O2.o

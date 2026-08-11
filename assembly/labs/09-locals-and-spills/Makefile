CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -std=c11 -fno-pie
LDFLAGS_COMMON := -no-pie

all: locals-o0 locals-og locals-o2 spill-o2

locals-o0: locals.c
	$(CC) $(CFLAGS_COMMON) -O0 $< $(LDFLAGS_COMMON) -o $@

locals-og: locals.c
	$(CC) $(CFLAGS_COMMON) -Og $< $(LDFLAGS_COMMON) -o $@

locals-o2: locals.c
	$(CC) $(CFLAGS_COMMON) -O2 $< $(LDFLAGS_COMMON) -o $@

spill.o: spill.c
	$(CC) $(CFLAGS_COMMON) -O2 -fno-omit-frame-pointer -c $< -o $@

helpers.o: helpers.c
	$(CC) $(CFLAGS_COMMON) -O2 -fno-omit-frame-pointer -c $< -o $@

spill-o2: spill.o helpers.o
	$(CC) $^ $(LDFLAGS_COMMON) -o $@

check: all
	./locals-o0
	./locals-og
	./locals-o2
	./spill-o2

objdump: all
	objdump -dr locals-o0
	objdump -dr locals-og
	objdump -dr locals-o2
	objdump -dr spill-o2
	objdump -dr -Mintel spill-o2

clean:
	rm -f locals-o0 locals-og locals-o2 spill-o2 spill.o helpers.o

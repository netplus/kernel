CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -std=c11 -fno-pie
LDFLAGS_COMMON := -no-pie

all: frame-o0 frame-o2

frame-o0: main.c frame.S
	$(CC) $(CFLAGS_COMMON) -O0 $^ $(LDFLAGS_COMMON) -o $@

frame-o2: main.c frame.S
	$(CC) $(CFLAGS_COMMON) -O2 $^ $(LDFLAGS_COMMON) -o $@

check: all
	./frame-o0
	./frame-o2

clean:
	rm -f frame-o0 frame-o2 *.o

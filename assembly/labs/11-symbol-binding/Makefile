CC ?= gcc
CFLAGS ?= -O0 -g -fno-pie
LDFLAGS ?= -no-pie
OBJS = main.o weak.o weak2.o strong.o strong2.o provider.o

.PHONY: all check inspect clean

all: strong-over-weak weak-weak

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

strong-over-weak: main.o weak.o strong.o provider.o
	$(CC) $(LDFLAGS) $^ -o $@

weak-weak: main.o weak.o weak2.o provider.o
	$(CC) $(LDFLAGS) $^ -o $@

check: all
	./strong-over-weak
	./weak-weak
	@rm -f strong-strong.err strong-strong
	@if $(CC) $(LDFLAGS) main.o strong.o strong2.o provider.o -o strong-strong >strong-strong.err 2>&1; then \
		echo "ERROR: duplicate strong definitions unexpectedly linked"; exit 1; \
	else \
		echo "duplicate strong definitions rejected as expected"; \
		cat strong-strong.err; \
	fi

inspect: $(OBJS)
	readelf -W -s main.o | grep -E 'choose|provided' || true
	readelf -W -s weak.o | grep 'choose' || true
	readelf -W -s strong.o | grep 'choose' || true
	nm main.o | grep -E 'choose|provided' || true
	nm weak.o | grep 'choose' || true
	nm strong.o | grep 'choose' || true

clean:
	rm -f *.o strong-over-weak weak-weak strong-strong strong-strong.err

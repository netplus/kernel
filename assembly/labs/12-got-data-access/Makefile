CC ?= gcc
CFLAGS := -O0 -Wall -Wextra

.PHONY: all run inspect clean

all: got_demo

provider.o: provider.c
	$(CC) $(CFLAGS) -fPIC -c $< -o $@

libprovider.so: provider.o
	$(CC) -shared $< -o $@

consumer.o: consumer.c
	$(CC) $(CFLAGS) -fPIC -c $< -o $@

main.o: main.c
	$(CC) $(CFLAGS) -fPIE -c $< -o $@

got_demo: main.o consumer.o libprovider.so
	$(CC) -pie main.o consumer.o -L. -lprovider -Wl,-rpath,'$$ORIGIN' -o $@

run: got_demo
	./got_demo

inspect: got_demo
	readelf -Wr consumer.o
	objdump -dr consumer.o
	readelf -Wr got_demo
	readelf -S got_demo | grep -E '\.got|\.rela'
	readelf -Ws got_demo | grep shared_value || true
	objdump -d got_demo | sed -n '/<read_shared>:/,/^$$/p'

clean:
	rm -f *.o *.so got_demo

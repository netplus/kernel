CC ?= gcc
CFLAGS := -g -Wall -Wextra -fno-inline

.PHONY: all run inspect clean

all: cse-O0 cse-Og cse-O2

cse-O0: cse.c
	$(CC) $(CFLAGS) -O0 $< -o $@

cse-Og: cse.c
	$(CC) $(CFLAGS) -Og $< -o $@

cse-O2: cse.c
	$(CC) $(CFLAGS) -O2 $< -o $@

run: all
	./cse-O0
	./cse-Og
	./cse-O2

inspect: all
	@for f in cse-O0 cse-Og cse-O2; do \
		echo "===== $$f: AT&T ====="; \
		objdump -d --disassemble=repeated_expr $$f; \
		echo "===== $$f: Intel ====="; \
		objdump -d -M intel --disassemble=repeated_expr $$f; \
		echo "===== $$f: symbols ====="; \
		nm -n $$f | grep -E 'repeated_expr| main$$'; \
	done
	readelf -h cse-O2 | grep -E 'Class:|Machine:'

clean:
	rm -f cse-O0 cse-Og cse-O2

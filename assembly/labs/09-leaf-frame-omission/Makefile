CC ?= gcc
CFLAGS_COMMON := -Wall -Wextra -fno-pie -no-pie

.PHONY: all check disasm clean

all: leaf-default leaf-frame-pointer leaf-no-red-zone

leaf-default: leaf_frame.c
	$(CC) $(CFLAGS_COMMON) -O2 -o $@ $<

leaf-frame-pointer: leaf_frame.c
	$(CC) $(CFLAGS_COMMON) -O2 -fno-omit-frame-pointer -o $@ $<

leaf-no-red-zone: leaf_frame.c
	$(CC) $(CFLAGS_COMMON) -O2 -mno-red-zone -o $@ $<

check: all
	./leaf-default
	./leaf-frame-pointer
	./leaf-no-red-zone

disasm: all
	objdump -dr leaf-default
	objdump -dr leaf-frame-pointer
	objdump -dr leaf-no-red-zone
	objdump -dr -Mintel leaf-default
	objdump -dr -Mintel leaf-frame-pointer
	objdump -dr -Mintel leaf-no-red-zone

clean:
	rm -f leaf-default leaf-frame-pointer leaf-no-red-zone

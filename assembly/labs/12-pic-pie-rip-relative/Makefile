CC ?= gcc
CFLAGS_COMMON := -O2 -Wall -Wextra

.PHONY: all run inspect clean

all: nonpie.o pie.o nonpie pie

nonpie.o: pic_pie_demo.c
	$(CC) $(CFLAGS_COMMON) -fno-pie -c $< -o $@

pie.o: pic_pie_demo.c
	$(CC) $(CFLAGS_COMMON) -fPIE -c $< -o $@

nonpie: pic_pie_demo.c
	$(CC) $(CFLAGS_COMMON) -fno-pie -no-pie $< -o $@

pie: pic_pie_demo.c
	$(CC) $(CFLAGS_COMMON) -fPIE -pie $< -o $@

run: all
	@echo '--- non-PIE ---'
	@./nonpie
	@./nonpie
	@./nonpie
	@echo '--- PIE ---'
	@./pie
	@./pie
	@./pie

inspect: all
	@echo '--- ELF type ---'
	@readelf -h nonpie | grep 'Type:'
	@readelf -h pie | grep 'Type:'
	@echo '--- nonpie.o: local_address ---'
	@objdump -dr nonpie.o | sed -n '/<local_address>/,/^$$/p'
	@echo '--- pie.o: local_address ---'
	@objdump -dr pie.o | sed -n '/<local_address>/,/^$$/p'
	@echo '--- nonpie.o relocations ---'
	@readelf -Wr nonpie.o
	@echo '--- pie.o relocations ---'
	@readelf -Wr pie.o

clean:
	rm -f nonpie.o pie.o nonpie pie

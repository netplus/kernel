CC ?= gcc
CFLAGS ?= -O0 -g -fno-pie
LDFLAGS ?= -no-pie

all: elf_sections

elf_sections: elf_sections.c
	$(CC) $(CFLAGS) $< $(LDFLAGS) -o $@

inspect: elf_sections
	readelf -W -S elf_sections
	readelf -W -l elf_sections
	objdump -h elf_sections
	objdump -s -j .rodata -j .data elf_sections
	nm -n elf_sections | grep -E 'course_name|initialized_counter|zero_counter|add_course_value|main'

clean:
	rm -f elf_sections

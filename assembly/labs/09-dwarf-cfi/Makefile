CC ?= gcc
CFLAGS ?= -g -O2 -Wall -Wextra -fno-pie
LDFLAGS ?= -no-pie

TARGET := cfi-demo

.PHONY: all run inspect clean

all: $(TARGET)

$(TARGET): driver.c funcs.S
	$(CC) $(CFLAGS) driver.c funcs.S $(LDFLAGS) -o $@

run: $(TARGET)
	./$(TARGET)

inspect: $(TARGET)
	readelf -S $(TARGET) | grep -E '\.(eh_frame|debug_frame)'
	readelf --debug-dump=frames $(TARGET)
	objdump -drwC $(TARGET)
	objdump -drwC -Mintel $(TARGET)
	nm -n $(TARGET) | grep cfi_

clean:
	rm -f $(TARGET)

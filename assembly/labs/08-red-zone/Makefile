CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -fno-pie
LDFLAGS ?= -no-pie
TARGET := red-zone

.PHONY: all run inspect clean

all: $(TARGET)

$(TARGET): main.c red-zone.S
	$(CC) $(CFLAGS) $(LDFLAGS) $^ -o $@

run: $(TARGET)
	./$(TARGET)

inspect: $(TARGET)
	objdump -dr $(TARGET) > objdump-att.txt
	objdump -dr -Mintel $(TARGET) > objdump-intel.txt
	nm -n $(TARGET) > nm.txt
	readelf -Ws $(TARGET) > readelf-symbols.txt
	@echo '--- compiler_leaf ---'
	@objdump -dr $(TARGET) | sed -n '/<compiler_leaf/,/^$$/p'
	@echo '--- red_zone_leaf ---'
	@objdump -dr $(TARGET) | sed -n '/<red_zone_leaf>/,/^$$/p'
	@echo '--- red_zone_call_boundary ---'
	@objdump -dr $(TARGET) | sed -n '/<red_zone_call_boundary>/,/^$$/p'

clean:
	rm -f $(TARGET) objdump-att.txt objdump-intel.txt nm.txt readelf-symbols.txt

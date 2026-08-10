CC := gcc
CFLAGS := -Wall -Wextra -fno-pie
LDFLAGS := -no-pie

.PHONY: all clean run disasm symbols

all: stack_args_O0 stack_args_O2

probe.o: probe.S
	$(CC) -c $< -o $@

main-O0.o: main.c
	$(CC) $(CFLAGS) -O0 -c $< -o $@

main-O2.o: main.c
	$(CC) $(CFLAGS) -O2 -c $< -o $@

stack_args_O0: main-O0.o probe.o
	$(CC) $(LDFLAGS) $^ -o $@

stack_args_O2: main-O2.o probe.o
	$(CC) $(LDFLAGS) $^ -o $@

run: all
	./stack_args_O0
	./stack_args_O2

disasm: all
	objdump -dr stack_args_O0 > objdump-att-O0.txt
	objdump -dr -Mintel stack_args_O0 > objdump-intel-O0.txt
	objdump -dr stack_args_O2 > objdump-att-O2.txt
	objdump -dr -Mintel stack_args_O2 > objdump-intel-O2.txt

symbols: all
	nm -n stack_args_O0 > nm-O0.txt
	nm -n stack_args_O2 > nm-O2.txt

clean:
	rm -f *.o stack_args_O0 stack_args_O2 objdump-*.txt nm-*.txt

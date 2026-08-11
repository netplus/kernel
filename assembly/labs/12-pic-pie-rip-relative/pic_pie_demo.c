#include <stdint.h>
#include <stdio.h>

static volatile int local_value = 7;

__attribute__((noinline)) uintptr_t local_address(void)
{
    return (uintptr_t)&local_value;
}

__attribute__((noinline)) int local_read(void)
{
    return local_value + 5;
}

int main(void)
{
    int value = local_read();
    uintptr_t address = local_address();

    printf("value=%d address=%p\n", value, (void *)address);
    return (value == 12 && address != 0) ? 0 : 1;
}

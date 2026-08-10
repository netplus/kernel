#include <stdio.h>
#include <stdlib.h>

extern long red_zone_leaf(void);
extern unsigned long red_zone_call_boundary(void);

__attribute__((noinline)) static unsigned long compiler_leaf(unsigned long x)
{
    volatile unsigned long slots[4];

    slots[0] = x + 1;
    slots[1] = x + 2;
    slots[2] = x + 3;
    slots[3] = x + 4;

    return slots[0] + slots[1] + slots[2] + slots[3];
}

int main(void)
{
    long leaf = red_zone_leaf();
    unsigned long survived = red_zone_call_boundary();
    unsigned long c_leaf = compiler_leaf(10);

    printf("asm leaf result=%ld\n", leaf);
    printf("red-zone value survived nested call=%lu\n", survived);
    printf("compiler leaf result=%lu\n", c_leaf);

    if (leaf != 66 || survived != 0 || c_leaf != 50)
        return EXIT_FAILURE;

    return EXIT_SUCCESS;
}

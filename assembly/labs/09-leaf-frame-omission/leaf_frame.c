#include <stdio.h>

__attribute__((noinline)) long leaf_slots(long a, long b)
{
    volatile long slots[2];

    slots[0] = a + 3;
    slots[1] = b + 5;
    return slots[0] + slots[1];
}

int main(void)
{
    long v = leaf_slots(7, 11);

    printf("leaf_slots(7,11)=%ld\n", v);
    return v == 26 ? 0 : 1;
}

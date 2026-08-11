#include <stdio.h>

__attribute__((noinline)) long debug_limits(long a, long b)
{
    long x = a + 3;
    long y = b * 5;
    long z = x + y;
    long w = z * 2;
    return w - x;
}

int main(void)
{
    long r = debug_limits(7, 11);
    printf("debug_limits=%ld\n", r);
    return r == 120 ? 0 : 1;
}

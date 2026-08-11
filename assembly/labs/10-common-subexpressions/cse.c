#include <stdio.h>

__attribute__((noinline)) long repeated_expr(long a, long b, long c)
{
    long x = (a + b) * c;
    long y = (a + b) * c;
    return x + y;
}

int main(void)
{
    long v = repeated_expr(7, 11, 5);

    printf("repeated_expr=%ld\n", v);
    return v == 180 ? 0 : 1;
}

#include <stdio.h>

__attribute__((noinline))
long local_expr(long a, long b)
{
    long x = a + 3;
    long y = b + 5;
    long z = x * y;

    return z + x;
}

int main(void)
{
    long result = local_expr(7, 11);

    printf("local_expr(7,11)=%ld\n", result);
    return result == 170 ? 0 : 1;
}

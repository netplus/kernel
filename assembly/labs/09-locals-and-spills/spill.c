#include <stdio.h>

long opaque(long x);
long consume12(long a, long b, long c, long d, long e, long f,
               long g, long h, long i, long j, long k, long l);

__attribute__((noinline))
long spill_wrapper(long a, long b, long c, long d, long e, long f,
                   long g, long h, long i, long j, long k, long l)
{
    long marker = opaque(a);

    return marker + consume12(a, b, c, d, e, f, g, h, i, j, k, l);
}

int main(void)
{
    long result = spill_wrapper(1, 2, 3, 4, 5, 6,
                                7, 8, 9, 10, 11, 12);

    printf("spill_wrapper=%ld\n", result);
    return result == 178 ? 0 : 1;
}

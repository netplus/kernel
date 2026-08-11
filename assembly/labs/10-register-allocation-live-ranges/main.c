#include <stdio.h>

void opaque(long value);

__attribute__((noinline))
long reuse_chain(long a, long b, long c, long d)
{
    long x = a + b;
    long y = x * c;
    long z = y + d;

    return z * 3;
}

__attribute__((noinline))
long pressure_across_call(long a, long b, long c, long d, long e,
                          long f, long g, long h, long i, long j)
{
    long v0 = a + 1;
    long v1 = b + 2;
    long v2 = c + 3;
    long v3 = d + 4;
    long v4 = e + 5;
    long v5 = f + 6;
    long v6 = g + 7;
    long v7 = h + 8;
    long v8 = i + 9;
    long v9 = j + 10;

    /*
     * opaque() is compiled in another translation unit.  Without LTO the
     * caller must respect the ordinary SysV AMD64 call-clobber rules here.
     */
    opaque(a);

    return v0 + v1 + v2 + v3 + v4 + v5 + v6 + v7 + v8 + v9;
}

int main(void)
{
    long reuse = reuse_chain(1, 2, 3, 4);
    long pressure = pressure_across_call(1, 2, 3, 4, 5,
                                         6, 7, 8, 9, 10);

    printf("reuse_chain=%ld\n", reuse);
    printf("pressure_across_call=%ld\n", pressure);

    return (reuse == 39 && pressure == 110) ? 0 : 1;
}

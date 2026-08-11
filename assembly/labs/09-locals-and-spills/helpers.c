__attribute__((noinline))
long opaque(long x)
{
    return x + 99;
}

__attribute__((noinline))
long consume12(long a, long b, long c, long d, long e, long f,
               long g, long h, long i, long j, long k, long l)
{
    return a + b + c + d + e + f + g + h + i + j + k + l;
}

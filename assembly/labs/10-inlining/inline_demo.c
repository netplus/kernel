#include <stdio.h>

static inline long inline_helper(long x)
{
    return x * 3 + 1;
}

__attribute__((noinline)) long noinline_helper(long x)
{
    return x * 3 + 1;
}

__attribute__((noinline)) long use_inline(long x)
{
    return inline_helper(x) + 5;
}

__attribute__((noinline)) long use_noinline(long x)
{
    return noinline_helper(x) + 5;
}

int main(void)
{
    long a = use_inline(7);
    long b = use_noinline(7);

    printf("use_inline=%ld\nuse_noinline=%ld\n", a, b);
    return (a == 27 && b == 27) ? 0 : 1;
}

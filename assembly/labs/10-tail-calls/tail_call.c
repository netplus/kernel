#include <stdio.h>

__attribute__((noinline, noclone))
long tail_target(long x)
{
    return x * 5 + 3;
}

__attribute__((noinline, noclone))
long tail_wrapper(long x)
{
    return tail_target(x);
}

__attribute__((noinline, noclone))
long non_tail_wrapper(long x)
{
    return tail_target(x) + 1;
}

int main(void)
{
    long a = tail_wrapper(7);
    long b = non_tail_wrapper(7);

    printf("tail_wrapper=%ld\n", a);
    printf("non_tail_wrapper=%ld\n", b);

    return (a == 38 && b == 39) ? 0 : 1;
}

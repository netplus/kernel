#include <stdint.h>

__attribute__((noinline))
int is_zero(long value)
{
    return value == 0;
}

__attribute__((noinline))
int signed_less(long left, long right)
{
    return left < right;
}

__attribute__((noinline))
int unsigned_above(unsigned long left, unsigned long right)
{
    return left > right;
}

__attribute__((noinline))
long max_signed(long left, long right)
{
    if (left > right)
        return left;
    return right;
}

__attribute__((noinline))
int sign_class(long value)
{
    if (value < 0)
        return -1;
    if (value == 0)
        return 0;
    return 1;
}

__attribute__((noinline))
unsigned long add_with_carry(unsigned long left,
                             unsigned long right,
                             unsigned int *carry)
{
    unsigned long sum = left + right;
    *carry = sum < left;
    return sum;
}

#include <stdint.h>

__attribute__((noinline))
uint64_t bit_mix(uint64_t value)
{
    value &= 0xff00ff00ff00ff00ULL;
    value |= 0x11;
    value ^= 0x100;
    return value;
}

__attribute__((noinline))
int64_t signed_shift(int64_t value, unsigned int count)
{
    return value >> count;
}

__attribute__((noinline))
uint64_t unsigned_shift(uint64_t value, unsigned int count)
{
    return value >> count;
}

__attribute__((noinline))
int64_t multiply(int64_t left, int64_t right)
{
    return left * right;
}

__attribute__((noinline))
int64_t divide_signed(int64_t dividend, int64_t divisor)
{
    return dividend / divisor;
}

__attribute__((noinline))
uint64_t divide_unsigned(uint64_t dividend, uint64_t divisor)
{
    return dividend / divisor;
}

__attribute__((noinline))
int64_t divide_by_10(int64_t value)
{
    return value / 10;
}

__attribute__((noinline))
uint64_t scale_by_10(uint64_t value)
{
    return value * 10;
}

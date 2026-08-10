#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

struct mixed {
    double d;
    uint64_t n;
};

extern struct mixed mixed_bump(struct mixed x);

int main(void)
{
    struct mixed x = {1.5, 40};
    struct mixed y = mixed_bump(x);

    printf("mixed=%.1f,%" PRIu64 "\n", y.d, y.n);
    return !(y.d == 2.5 && y.n == 42);
}

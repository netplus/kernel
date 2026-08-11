#include <stdio.h>

long cfi_rbp_sum(long a, long b);
long cfi_rsp_sum(long a, long b);

int main(void)
{
    long a = cfi_rbp_sum(17, 25);
    long b = cfi_rsp_sum(17, 25);

    printf("cfi_rbp_sum=%ld\n", a);
    printf("cfi_rsp_sum=%ld\n", b);

    return (a == 42 && b == 43) ? 0 : 1;
}

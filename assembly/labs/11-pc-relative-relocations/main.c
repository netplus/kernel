#include <stdio.h>

long call_target(long);

int main(void)
{
    printf("result=%ld\n", call_target(7));
    return 0;
}

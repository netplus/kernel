#include <stdio.h>

int read_shared(void);

int main(void)
{
    printf("got_result=%d\n", read_shared());
    return 0;
}

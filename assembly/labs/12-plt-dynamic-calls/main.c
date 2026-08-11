#include <stdio.h>

int call_external(int);

int main(void)
{
    int result = call_external(36);

    printf("plt_result=%d\n", result);
    return result == 42 ? 0 : 1;
}

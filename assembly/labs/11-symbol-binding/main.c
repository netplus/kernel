#include <stdio.h>

extern int choose(void);
extern int provided(void);

int main(void)
{
    printf("choose=%d provided=%d\n", choose(), provided());
    return 0;
}

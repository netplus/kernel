#include <stdio.h>

static int local_counter = 3;
int global_counter = 7;

extern int external_counter;
extern int external_add(int value);

static int local_add(int value)
{
    return value + local_counter;
}

int exported_add(int value)
{
    int base = local_add(value) + global_counter + external_counter;
    return external_add(base);
}

int main(void)
{
    printf("symbol_result=%d\n", exported_add(5));
    return 0;
}

#include <stdio.h>

const char course_name[] = "kernel-5.10";
int initialized_counter = 7;
int zero_counter;

__attribute__((noinline))
int add_course_value(int x)
{
    return x + initialized_counter + zero_counter + course_name[0];
}

int main(void)
{
    printf("value=%d\n", add_course_value(1));
    return 0;
}

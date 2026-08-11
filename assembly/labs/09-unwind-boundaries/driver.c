#define _GNU_SOURCE
#include <execinfo.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void good_frame(void);
void missing_frame(void);
void wrong_frame(void);

__attribute__((noinline))
void capture_trace(const char *label)
{
    void *frames[16];
    int nr = backtrace(frames, 16);
    char **symbols = backtrace_symbols(frames, nr);

    printf("[%s] frames=%d\n", label, nr);
    if (!symbols) {
        perror("backtrace_symbols");
        exit(2);
    }

    for (int i = 0; i < nr; ++i)
        printf("  %s\n", symbols[i]);

    free(symbols);
}

__attribute__((noinline))
static void c_mid(void (*fn)(void))
{
    fn();
}

__attribute__((noinline))
static void c_top(void (*fn)(void))
{
    c_mid(fn);
}

int main(int argc, char **argv)
{
    if (argc != 2)
        return 64;

    if (!strcmp(argv[1], "good"))
        c_top(good_frame);
    else if (!strcmp(argv[1], "missing"))
        c_top(missing_frame);
    else if (!strcmp(argv[1], "wrong"))
        c_top(wrong_frame);
    else
        return 64;

    return 0;
}

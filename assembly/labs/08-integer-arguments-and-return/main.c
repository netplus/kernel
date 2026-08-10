#include <stdio.h>

extern long abi_probe6(long, long, long, long, long, long);
extern long seen_rdi, seen_rsi, seen_rdx, seen_rcx, seen_r8, seen_r9;

__attribute__((noinline))
static long call_probe(void)
{
    return abi_probe6(11, 22, 33, 44, 55, 66);
}

int main(void)
{
    long result = call_probe();
    long expected[] = {11, 22, 33, 44, 55, 66};
    long actual[] = {seen_rdi, seen_rsi, seen_rdx, seen_rcx, seen_r8, seen_r9};

    for (int i = 0; i < 6; ++i) {
        if (actual[i] != expected[i]) {
            fprintf(stderr, "arg%d mismatch: got %ld expected %ld\n",
                    i + 1, actual[i], expected[i]);
            return 10 + i;
        }
    }

    if (result != 231) {
        fprintf(stderr, "return mismatch: got %ld expected 231\n", result);
        return 20;
    }

    printf("args: %ld %ld %ld %ld %ld %ld\n",
           seen_rdi, seen_rsi, seen_rdx, seen_rcx, seen_r8, seen_r9);
    printf("return: %ld\n", result);
    return 0;
}

#include <stddef.h>

__attribute__((noinline))
long sum_while(long n)
{
    long sum = 0;
    long i = 1;
    while (i <= n) {
        sum += i;
        i++;
    }
    return sum;
}

__attribute__((noinline))
long sum_do_while(long n)
{
    long sum = 0;
    if (n <= 0)
        return 0;
    do {
        sum += n;
        n--;
    } while (n != 0);
    return sum;
}

__attribute__((noinline))
long sum_array(const long *values, size_t nr)
{
    long sum = 0;
    for (size_t i = 0; i < nr; i++)
        sum += values[i];
    return sum;
}

__attribute__((noinline)) static long case0(long x) { return x + 11; }
__attribute__((noinline)) static long case1(long x) { return x * 3 + 7; }
__attribute__((noinline)) static long case2(long x) { return x - 5; }
__attribute__((noinline)) static long case3(long x) { return x * x; }
__attribute__((noinline)) static long case4(long x) { return (x << 2) + 3; }
__attribute__((noinline)) static long case5(long x) { return x ^ 0x55; }

__attribute__((noinline))
long dense_switch(unsigned int op, long x)
{
    switch (op) {
    case 0: return case0(x);
    case 1: return case1(x);
    case 2: return case2(x);
    case 3: return case3(x);
    case 4: return case4(x);
    case 5: return case5(x);
    default: return -1;
    }
}

__attribute__((noinline))
long sparse_switch(unsigned int op, long x)
{
    switch (op) {
    case 1: return x + 1;
    case 10: return x + 10;
    case 100: return x + 100;
    case 1000: return x + 1000;
    default: return -1;
    }
}

enum phase {
    PHASE_INIT,
    PHASE_READY,
    PHASE_RUNNING,
    PHASE_DONE,
};

__attribute__((noinline))
long run_state_machine(enum phase phase, long value)
{
    for (;;) {
        switch (phase) {
        case PHASE_INIT:
            value += 1;
            phase = PHASE_READY;
            break;
        case PHASE_READY:
            value += 2;
            phase = PHASE_RUNNING;
            break;
        case PHASE_RUNNING:
            value += 3;
            phase = PHASE_DONE;
            break;
        case PHASE_DONE:
            return value;
        default:
            return -1;
        }
    }
}

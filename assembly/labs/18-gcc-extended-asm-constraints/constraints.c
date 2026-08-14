#include <stdint.h>
#include <stdio.h>

__attribute__((noinline))
uint64_t read_write_operand(uint64_t x)
{
    asm("addq $7, %0" : "+r"(x) : : "cc");
    return x;
}

__attribute__((noinline))
uint64_t matching_operand(uint64_t x, uint64_t y)
{
    uint64_t out;
    asm("addq %2, %0"
        : "=r"(out)
        : "0"(x), "r"(y)
        : "cc");
    return out;
}

__attribute__((noinline))
uint64_t early_clobber_example(uint64_t a, uint64_t b)
{
    uint64_t tmp;
    asm("movq %1, %0\n\t"
        "addq %2, %0"
        : "=&r"(tmp)
        : "r"(a), "r"(b)
        : "cc");
    return tmp;
}

__attribute__((noinline))
int cmpxchg_contract(uint64_t *p, uint64_t *expected, uint64_t desired)
{
    uint64_t old = *expected;
    unsigned char success;

    asm volatile("lock; cmpxchgq %3, %1\n\t"
                 "sete %0"
                 : "=q"(success), "+m"(*p), "+a"(old)
                 : "r"(desired)
                 : "cc", "memory");

    if (!success)
        *expected = old;
    return success;
}

__attribute__((noinline))
uint64_t precise_memory_operand(uint64_t *p)
{
    uint64_t old = 3;
    asm("xchgq %0, %1" : "+r"(old), "+m"(*p));
    return old;
}

int main(void)
{
    uint64_t value = 11;
    uint64_t expected = 11;
    uint64_t old;

    printf("read_write=%llu\n", (unsigned long long)read_write_operand(5));
    printf("matching=%llu\n", (unsigned long long)matching_operand(9, 4));
    printf("early_clobber=%llu\n", (unsigned long long)early_clobber_example(20, 22));

    printf("cmpxchg_success=%d value=%llu expected=%llu\n",
           cmpxchg_contract(&value, &expected, 42),
           (unsigned long long)value, (unsigned long long)expected);

    expected = 7;
    printf("cmpxchg_failure=%d value=%llu expected=%llu\n",
           cmpxchg_contract(&value, &expected, 99),
           (unsigned long long)value, (unsigned long long)expected);

    value = 55;
    old = precise_memory_operand(&value);
    printf("xchg_old=%llu xchg_new=%llu\n",
           (unsigned long long)old, (unsigned long long)value);
    return 0;
}

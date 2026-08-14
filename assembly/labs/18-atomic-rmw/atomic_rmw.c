#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static volatile uint64_t plain_counter;
static volatile uint64_t atomic_counter;

struct cmpxchg_result {
    uint64_t rax;
    unsigned char zf;
};

__attribute__((noinline)) static uint64_t do_xchg(volatile uint64_t *p, uint64_t v)
{
    __asm__ volatile("xchgq %0, %1"
                     : "+r"(v), "+m"(*p)
                     :
                     : "memory");
    return v;
}

__attribute__((noinline)) static struct cmpxchg_result
do_cmpxchg(volatile uint64_t *p, uint64_t expected, uint64_t desired)
{
    struct cmpxchg_result r;
    unsigned char zf;

    __asm__ volatile("lock; cmpxchgq %3, %1\n\t"
                     "setz %0"
                     : "=q"(zf), "+m"(*p), "+a"(expected)
                     : "r"(desired)
                     : "memory", "cc");
    r.rax = expected;
    r.zf = zf;
    return r;
}

__attribute__((noinline)) static uint64_t do_xadd(volatile uint64_t *p, uint64_t inc)
{
    __asm__ volatile("lock; xaddq %0, %1"
                     : "+r"(inc), "+m"(*p)
                     :
                     : "memory", "cc");
    return inc;
}

static void *worker(void *arg)
{
    uint64_t n = *(uint64_t *)arg;
    for (uint64_t i = 0; i < n; ++i) {
        uint64_t tmp = plain_counter;
        tmp++;
        plain_counter = tmp;

        uint64_t one = 1;
        __asm__ volatile("lock; xaddq %0, %1"
                         : "+r"(one), "+m"(atomic_counter)
                         :
                         : "memory", "cc");
    }
    return NULL;
}

int main(int argc, char **argv)
{
    volatile uint64_t x = 10;
    uint64_t old = do_xchg(&x, 20);
    printf("xchg old=%llu new=%llu\n",
           (unsigned long long)old, (unsigned long long)x);

    x = 10;
    struct cmpxchg_result ok = do_cmpxchg(&x, 10, 20);
    printf("cmpxchg_success zf=%u rax=%llu mem=%llu\n", ok.zf,
           (unsigned long long)ok.rax, (unsigned long long)x);

    x = 15;
    struct cmpxchg_result fail = do_cmpxchg(&x, 10, 20);
    printf("cmpxchg_failure zf=%u rax=%llu mem=%llu\n", fail.zf,
           (unsigned long long)fail.rax, (unsigned long long)x);

    x = 10;
    old = do_xadd(&x, 3);
    printf("xadd old=%llu new=%llu\n",
           (unsigned long long)old, (unsigned long long)x);

    const unsigned threads = 4;
    uint64_t iterations = argc > 1 ? strtoull(argv[1], NULL, 0) : 1000000ULL;
    pthread_t tid[threads];
    plain_counter = 0;
    atomic_counter = 0;
    for (unsigned i = 0; i < threads; ++i)
        if (pthread_create(&tid[i], NULL, worker, &iterations) != 0)
            return 2;
    for (unsigned i = 0; i < threads; ++i)
        pthread_join(tid[i], NULL);

    uint64_t expected = threads * iterations;
    printf("threads expected=%llu plain=%llu atomic=%llu\n",
           (unsigned long long)expected,
           (unsigned long long)plain_counter,
           (unsigned long long)atomic_counter);
    return atomic_counter == expected ? 0 : 1;
}

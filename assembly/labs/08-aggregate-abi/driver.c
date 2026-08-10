#include <stdint.h>
#include <stdio.h>

struct pair_u64 {
    uint64_t a;
    uint64_t b;
};

struct big3_u64 {
    uint64_t a;
    uint64_t b;
    uint64_t c;
};

extern struct pair_u64 pair_bump(struct pair_u64 p);
extern struct big3_u64 big_bump(struct big3_u64 p);

int main(void)
{
    struct pair_u64 p = {11, 22};
    struct pair_u64 pr = pair_bump(p);
    struct big3_u64 b = {33, 44, 55};
    struct big3_u64 br = big_bump(b);

    printf("pair=%llu,%llu\n",
           (unsigned long long)pr.a,
           (unsigned long long)pr.b);
    printf("big=%llu,%llu,%llu\n",
           (unsigned long long)br.a,
           (unsigned long long)br.b,
           (unsigned long long)br.c);

    if (pr.a != 12 || pr.b != 24)
        return 1;
    if (br.a != 34 || br.b != 46 || br.c != 58)
        return 2;

    return 0;
}

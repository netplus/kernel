#include <stddef.h>
#include <stdio.h>

struct sample {
    int id;
    int flags;
    long value;
};

struct record {
    int id;
    int flags;
    long value;
    long stamp;
};

struct bucket {
    long count;
    int values[4];
};

struct inner {
    int state;
    int flags;
    long value;
};

struct outer {
    long seq;
    struct inner in;
};

int main(void)
{
    printf("sizeof(struct sample) = %zu\n", sizeof(struct sample));
    printf("  id=%zu flags=%zu value=%zu\n",
           offsetof(struct sample, id),
           offsetof(struct sample, flags),
           offsetof(struct sample, value));

    printf("sizeof(struct record) = %zu\n", sizeof(struct record));
    printf("  id=%zu flags=%zu value=%zu stamp=%zu\n",
           offsetof(struct record, id),
           offsetof(struct record, flags),
           offsetof(struct record, value),
           offsetof(struct record, stamp));

    printf("sizeof(struct bucket) = %zu\n", sizeof(struct bucket));
    printf("  count=%zu values=%zu\n",
           offsetof(struct bucket, count),
           offsetof(struct bucket, values));

    printf("sizeof(struct inner) = %zu\n", sizeof(struct inner));
    printf("sizeof(struct outer) = %zu\n", sizeof(struct outer));
    printf("  seq=%zu in=%zu in.value=%zu\n",
           offsetof(struct outer, seq),
           offsetof(struct outer, in),
           offsetof(struct outer, in) + offsetof(struct inner, value));

    return 0;
}

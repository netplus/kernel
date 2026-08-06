#include <stddef.h>

struct sample {
    int id;
    int flags;
    long value;
};

long array_get(const long *array, size_t index)
{
    return array[index];
}

long member_get(const struct sample *item)
{
    return item->value;
}

long scale_add(long x)
{
    return x * 5 + 5;
}

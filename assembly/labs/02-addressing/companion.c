#include <stddef.h>
#include <stdint.h>

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

long array_get(const long *array, size_t index)
{
    return array[index];
}

const long *array_element_address(const long *array, size_t index)
{
    return &array[index];
}

long member_get(const struct sample *item)
{
    return item->value;
}

long record_value_get(const struct record *records, size_t index)
{
    return records[index].value;
}

int bucket_value_get(const struct bucket *bucket, size_t index)
{
    return bucket->values[index];
}

long nested_value_get(const struct outer *object)
{
    return object->in.value;
}

long matrix_get(const long matrix[][4], size_t row, size_t column)
{
    return matrix[row][column];
}

long pointer_matrix_get(long *const *rows, size_t row, size_t column)
{
    return rows[row][column];
}

long scale_add(long x)
{
    return x * 5 + 5;
}

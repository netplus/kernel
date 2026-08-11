long left_data = 10;

__attribute__((noinline))
long left(long x)
{
    return x + left_data;
}

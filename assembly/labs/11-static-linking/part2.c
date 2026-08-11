extern long left(long x);
long right_data = 20;

__attribute__((noinline))
long combine(long x)
{
    return left(x) + right_data;
}

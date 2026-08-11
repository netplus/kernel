extern int shared_value;

__attribute__((noinline)) int read_shared(void)
{
    return shared_value + 1;
}

extern long target(long);
extern long ext_data;

long call_target(long x)
{
    return target(x + ext_data) + 1;
}

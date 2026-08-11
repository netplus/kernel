extern int external_add(int);

__attribute__((noinline)) int call_external(int x)
{
    return external_add(x) + 1;
}

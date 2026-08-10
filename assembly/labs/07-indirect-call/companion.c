typedef long (*operation_fn)(long);

__attribute__((noinline))
long add_three(long value)
{
    return value + 3;
}

__attribute__((noinline))
long times_five(long value)
{
    return value * 5;
}

__attribute__((noinline))
long call_function_pointer(operation_fn fn, long value)
{
    long result = fn(value);
    return result + 1;
}

__attribute__((noinline))
long choose_and_call(int choose_times_five, long value)
{
    operation_fn fn = choose_times_five ? times_five : add_three;
    long result = fn(value);
    return result + 1;
}

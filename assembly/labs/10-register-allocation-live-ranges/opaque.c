__attribute__((noinline))
void opaque(long value)
{
    __asm__ volatile("" : : "r"(value) : "memory");
}

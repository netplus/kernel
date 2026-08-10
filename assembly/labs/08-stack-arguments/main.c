#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

extern uint64_t seen_regs[6];
extern uint64_t seen_stack[2];
extern uint64_t seen_entry_rsp;

extern long abi_probe8(long, long, long, long,
                       long, long, long, long);

__attribute__((noinline))
static long call_probe(void)
{
    return abi_probe8(11, 22, 33, 44, 55, 66, 77, 88);
}

int main(void)
{
    static const uint64_t expected_regs[6] = {11, 22, 33, 44, 55, 66};
    long ret = call_probe();

    for (int i = 0; i < 6; ++i) {
        if (seen_regs[i] != expected_regs[i]) {
            fprintf(stderr,
                    "reg %d: got=%" PRIu64 " expected=%" PRIu64 "\n",
                    i, seen_regs[i], expected_regs[i]);
            return 1;
        }
    }

    if (seen_stack[0] != 77 || seen_stack[1] != 88) {
        fprintf(stderr,
                "stack: got=%" PRIu64 ",%" PRIu64 " expected=77,88\n",
                seen_stack[0], seen_stack[1]);
        return 2;
    }

    if (((seen_entry_rsp + 8) & 0xf) != 0) {
        fprintf(stderr, "alignment: entry_rsp=%#" PRIx64 "\n",
                seen_entry_rsp);
        return 3;
    }

    if (ret != 396) {
        fprintf(stderr, "return: got=%ld expected=396\n", ret);
        return 4;
    }

    puts("regs: 11 22 33 44 55 66");
    puts("stack: [rsp+8]=77 [rsp+16]=88");
    puts("entry alignment: (rsp+8) mod 16 = 0");
    printf("return: %ld\n", ret);
    return 0;
}

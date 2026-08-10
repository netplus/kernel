#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

extern unsigned long probe_alignment(void);
extern uint64_t seen_outer_entry_rsp;
extern uint64_t seen_pre_nested_call_rsp;
extern uint64_t seen_nested_entry_rsp;

static int aligned16(uint64_t v)
{
    return (v & 0xfu) == 0;
}

static int entry_rule(uint64_t v)
{
    return ((v + 8u) & 0xfu) == 0;
}

int main(void)
{
    unsigned long result = probe_alignment();

    printf("outer entry: rsp%%16=%" PRIu64 " (rsp+8)%%16=%" PRIu64 "\n",
           seen_outer_entry_rsp & 0xfu,
           (seen_outer_entry_rsp + 8u) & 0xfu);
    printf("before nested call: rsp%%16=%" PRIu64 "\n",
           seen_pre_nested_call_rsp & 0xfu);
    printf("nested entry: rsp%%16=%" PRIu64 " (rsp+8)%%16=%" PRIu64 "\n",
           seen_nested_entry_rsp & 0xfu,
           (seen_nested_entry_rsp + 8u) & 0xfu);
    printf("return: %lu\n", result);

    if (!entry_rule(seen_outer_entry_rsp))
        return 1;
    if (!aligned16(seen_pre_nested_call_rsp))
        return 2;
    if (!entry_rule(seen_nested_entry_rsp))
        return 3;
    if (result != 73)
        return 4;

    return 0;
}

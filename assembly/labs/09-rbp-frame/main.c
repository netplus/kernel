#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

extern uint64_t frame_sum(uint64_t a, uint64_t b);

uint64_t entry_rsp;
uint64_t entry_rbp;
uint64_t frame_rbp;
uint64_t frame_rsp;
uint64_t saved_rbp_slot;
uint64_t return_address_slot;

int main(void)
{
    uint64_t result = frame_sum(17, 25);

    printf("result=%" PRIu64 "\n", result);
    printf("entry_rsp=0x%016" PRIx64 "\n", entry_rsp);
    printf("entry_rbp=0x%016" PRIx64 "\n", entry_rbp);
    printf("frame_rbp=0x%016" PRIx64 "\n", frame_rbp);
    printf("frame_rsp=0x%016" PRIx64 "\n", frame_rsp);
    printf("saved_rbp_slot=0x%016" PRIx64 "\n", saved_rbp_slot);
    printf("return_address_slot=0x%016" PRIx64 "\n", return_address_slot);
    printf("entry_rsp-frame_rbp=%" PRIu64 "\n", entry_rsp - frame_rbp);
    printf("frame_rbp-frame_rsp=%" PRIu64 "\n", frame_rbp - frame_rsp);
    printf("saved_rbp_matches_entry=%s\n",
           saved_rbp_slot == entry_rbp ? "yes" : "no");

    return result == 42 &&
           entry_rsp - frame_rbp == 8 &&
           frame_rbp - frame_rsp == 16 &&
           saved_rbp_slot == entry_rbp ? 0 : 1;
}

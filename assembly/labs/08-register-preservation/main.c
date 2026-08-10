#include <stdio.h>

extern void run_preservation_probe(void);

extern unsigned long seen_rbx;
extern unsigned long seen_rbp;
extern unsigned long seen_r12;
extern unsigned long seen_r13;
extern unsigned long seen_r14;
extern unsigned long seen_r15;
extern unsigned long seen_r10;
extern unsigned long seen_r11;

int main(void)
{
    const unsigned long expect_rbx = 0x1111111111111111UL;
    const unsigned long expect_rbp = 0x2222222222222222UL;
    const unsigned long expect_r12 = 0x3333333333333333UL;
    const unsigned long expect_r13 = 0x4444444444444444UL;
    const unsigned long expect_r14 = 0x5555555555555555UL;
    const unsigned long expect_r15 = 0x6666666666666666UL;
    const unsigned long expect_r10 = 0xa0a0a0a0a0a0a0a0UL;
    const unsigned long expect_r11 = 0xb0b0b0b0b0b0b0b0UL;

    run_preservation_probe();

    printf("callee-saved: rbx=%#018lx rbp=%#018lx r12=%#018lx r13=%#018lx r14=%#018lx r15=%#018lx\n",
           seen_rbx, seen_rbp, seen_r12, seen_r13, seen_r14, seen_r15);
    printf("caller-saved: r10=%#018lx r11=%#018lx\n", seen_r10, seen_r11);

    if (seen_rbx != expect_rbx || seen_rbp != expect_rbp ||
        seen_r12 != expect_r12 || seen_r13 != expect_r13 ||
        seen_r14 != expect_r14 || seen_r15 != expect_r15)
        return 1;

    if (seen_r10 == expect_r10 || seen_r11 == expect_r11)
        return 2;

    return 0;
}

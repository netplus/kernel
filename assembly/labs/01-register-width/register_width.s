    .section .text
    .global _start
    .type _start, @function

_start:
    # Establish a recognizable 64-bit pattern.
    movabsq $0x1122334455667788, %rax

    # Partial-register writes.
    movb    $0xff, %al
    movw    $0xabcd, %ax
    movl    $0x12345678, %eax

    # exit(RAX). The shell reports only the low 8 bits of the status.
    movq    %rax, %rdi
    movq    $60, %rax
    syscall

    .size _start, .-_start

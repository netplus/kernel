    .text
    .globl _start
    .type _start, @function
_start:
    # 20 + 7 - 5 = 22
    movq $20, %rbx
    addq $7, %rbx
    subq $5, %rbx

    .globl after_add_sub
after_add_sub:
    # ((0xf0 & 0x3c) | 0x03) ^ 0x11 = 0x22
    movq $0xf0, %rsi
    andq $0x3c, %rsi
    orq  $0x03, %rsi
    xorq $0x11, %rsi

    .globl after_bitops
after_bitops:
    # not does not update RFLAGS. Apply it twice so RSI returns to 0x22.
    notq %rsi

    .globl after_not
after_not:
    notq %rsi

    # The same bit pattern (-16) is shifted with signed and unsigned semantics.
    movq $-16, %r8
    movq %r8, %r9
    sarq $2, %r9

    movq %r8, %r10
    movb $2, %cl
    shrq %cl, %r10

    .globl after_shifts
after_shifts:
    # Two-operand imul keeps the low 64-bit result: 7 * 9 = 63.
    movq $7, %r11
    imulq $9, %r11

    .globl after_imul
after_imul:
    # One-operand mul uses RDX:RAX for the full unsigned product.
    movq $6, %rax
    movq $7, %rcx
    mulq %rcx
    movq %rax, %r12

    .globl after_mul
after_mul:
    # Signed division: -100 / 9 = -11, remainder -1.
    movq $-100, %rax
    cqto
    movq $9, %rcx
    idivq %rcx
    movq %rax, %r13
    movq %rdx, %r14

    .globl after_idiv
after_idiv:
    # Unsigned division: 100 / 9 = 11, remainder 1.
    movq $100, %rax
    xorq %rdx, %rdx
    movq $9, %rcx
    divq %rcx
    movq %rax, %r15

    .globl after_div
after_div:
    # Build a small checksum from the observed results.
    # 22 + 34 - (-4) + 63 + 42 - (-11) - (-1) + 11 + 1 = 189
    movq %rbx, %rdi
    addq %rsi, %rdi
    subq %r9, %rdi
    addq %r11, %rdi
    addq %r12, %rdi
    subq %r13, %rdi
    subq %r14, %rdi
    addq %r15, %rdi
    addq %rdx, %rdi

    movq $60, %rax
    syscall
    .size _start, .-_start

    .section .note.GNU-stack,"",@progbits

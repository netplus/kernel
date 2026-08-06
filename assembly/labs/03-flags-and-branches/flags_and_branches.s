    .section .bss
    .align 8
result_eq:
    .byte 0
result_zero:
    .byte 0
result_signed_less:
    .byte 0
result_unsigned_above:
    .byte 0
result_overflow:
    .byte 0
result_no_carry:
    .byte 0
result_carry:
    .byte 0
result_wrap_zero:
    .byte 0
branch_negative:
    .byte 0
    .align 8
max_value:
    .quad 0

    .section .text
    .global _start
    .type _start, @function

_start:
    # Case 1: cmp updates flags but does not modify RAX.
    movq $7, %rax
    cmpq $7, %rax
.Lafter_cmp_equal:
    sete result_eq(%rip)

    # Case 2: test reg,reg is the conventional zero test.
    xorq %rcx, %rcx
    testq %rcx, %rcx
.Lafter_test_zero:
    setz result_zero(%rip)

    # Case 3: the same CMP flags support signed and unsigned views.
    # Bit pattern -1 is less than 1 as signed, but above 1 as unsigned.
    movq $-1, %r8
    cmpq $1, %r8
.Lafter_cmp_signed_unsigned:
    setl result_signed_less(%rip)
    seta result_unsigned_above(%rip)

    # Case 4: signed overflow without unsigned carry.
    movabsq $0x7fffffffffffffff, %r11
    addq $1, %r11
.Lafter_signed_overflow:
    seto result_overflow(%rip)
    setnc result_no_carry(%rip)

    # Case 5: unsigned carry and zero after wraparound.
    movq $-1, %r14
    addq $1, %r14
.Lafter_unsigned_carry:
    setc result_carry(%rip)
    setz result_wrap_zero(%rip)

    # Case 6: conditional jump creates multiple basic blocks.
    movq $-5, %rax
    testq %rax, %rax
    jns .Lnonnegative

.Lnegative:
    movb $1, branch_negative(%rip)
    jmp .Lafter_sign_branch

.Lnonnegative:
    movb $0, branch_negative(%rip)

.Lafter_sign_branch:
    # Case 7: signed maximum implemented as branch-and-merge.
    movq $9, %rax
    movq $4, %rcx
    cmpq %rcx, %rax
    jle .Lselect_second

.Lselect_first:
    movq %rax, %rdx
    jmp .Lmax_done

.Lselect_second:
    movq %rcx, %rdx

.Lmax_done:
    movq %rdx, max_value(%rip)

    # Build a deterministic checksum:
    # eight true flag predicates + one negative branch + max value 9 = 18.
    xorl %edi, %edi
    movzbl result_eq(%rip), %eax
    addl %eax, %edi
    movzbl result_zero(%rip), %eax
    addl %eax, %edi
    movzbl result_signed_less(%rip), %eax
    addl %eax, %edi
    movzbl result_unsigned_above(%rip), %eax
    addl %eax, %edi
    movzbl result_overflow(%rip), %eax
    addl %eax, %edi
    movzbl result_no_carry(%rip), %eax
    addl %eax, %edi
    movzbl result_carry(%rip), %eax
    addl %eax, %edi
    movzbl result_wrap_zero(%rip), %eax
    addl %eax, %edi
    movzbl branch_negative(%rip), %eax
    addl %eax, %edi
    movq max_value(%rip), %rax
    addl %eax, %edi

    movq $60, %rax
    syscall

    .size _start, .-_start

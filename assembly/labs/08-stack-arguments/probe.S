    .text
    .globl abi_probe8
    .type abi_probe8,@function
abi_probe8:
    movq %rsp, seen_entry_rsp(%rip)

    movq %rdi, seen_regs+0(%rip)
    movq %rsi, seen_regs+8(%rip)
    movq %rdx, seen_regs+16(%rip)
    movq %rcx, seen_regs+24(%rip)
    movq %r8,  seen_regs+32(%rip)
    movq %r9,  seen_regs+40(%rip)

    movq 8(%rsp), %r10
    movq %r10, seen_stack+0(%rip)
    movq 16(%rsp), %r11
    movq %r11, seen_stack+8(%rip)

    movq %rdi, %rax
    addq %rsi, %rax
    addq %rdx, %rax
    addq %rcx, %rax
    addq %r8,  %rax
    addq %r9,  %rax
    addq %r10, %rax
    addq %r11, %rax
    ret
    .size abi_probe8, .-abi_probe8

    .data
    .globl seen_regs
    .align 8
seen_regs:
    .zero 48

    .globl seen_stack
    .align 8
seen_stack:
    .zero 16

    .globl seen_entry_rsp
    .align 8
seen_entry_rsp:
    .quad 0

    .section .note.GNU-stack,"",@progbits

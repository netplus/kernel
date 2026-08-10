    .text
    .globl abi_probe6
    .type abi_probe6, @function
abi_probe6:
    movq %rdi, seen_rdi(%rip)
    movq %rsi, seen_rsi(%rip)
    movq %rdx, seen_rdx(%rip)
    movq %rcx, seen_rcx(%rip)
    movq %r8,  seen_r8(%rip)
    movq %r9,  seen_r9(%rip)

    movq %rdi, %rax
    addq %rsi, %rax
    addq %rdx, %rax
    addq %rcx, %rax
    addq %r8,  %rax
    addq %r9,  %rax
    ret
    .size abi_probe6, .-abi_probe6

    .data
    .globl seen_rdi, seen_rsi, seen_rdx, seen_rcx, seen_r8, seen_r9
    .align 8
seen_rdi: .quad 0
seen_rsi: .quad 0
seen_rdx: .quad 0
seen_rcx: .quad 0
seen_r8:  .quad 0
seen_r9:  .quad 0

    .section .note.GNU-stack,"",@progbits

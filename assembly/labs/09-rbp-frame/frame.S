    .text
    .globl frame_sum
    .type frame_sum, @function
frame_sum:
    movq %rsp, entry_rsp(%rip)
    movq %rbp, entry_rbp(%rip)

    pushq %rbp
    movq %rsp, %rbp
    subq $16, %rsp

    movq %rbp, frame_rbp(%rip)
    movq %rsp, frame_rsp(%rip)
    movq 0(%rbp), %rax
    movq %rax, saved_rbp_slot(%rip)
    movq 8(%rbp), %rax
    movq %rax, return_address_slot(%rip)

    movq %rdi, -8(%rbp)
    movq %rsi, -16(%rbp)
    movq -8(%rbp), %rax
    addq -16(%rbp), %rax

    leave
    ret
    .size frame_sum, .-frame_sum

    .section .note.GNU-stack,"",@progbits

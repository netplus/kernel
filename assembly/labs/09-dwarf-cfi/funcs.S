.text
.globl cfi_rbp_sum
.type cfi_rbp_sum,@function
cfi_rbp_sum:
    .cfi_startproc
    pushq %rbp
    .cfi_def_cfa_offset 16
    .cfi_offset %rbp, -16
    movq %rsp, %rbp
    .cfi_def_cfa_register %rbp
    subq $16, %rsp

    movq %rdi, -8(%rbp)
    movq %rsi, -16(%rbp)
    movq -8(%rbp), %rax
    addq -16(%rbp), %rax

    leave
    .cfi_def_cfa %rsp, 8
    ret
    .cfi_endproc
.size cfi_rbp_sum, .-cfi_rbp_sum

.globl cfi_rsp_sum
.type cfi_rsp_sum,@function
cfi_rsp_sum:
    .cfi_startproc
    pushq %rbx
    .cfi_def_cfa_offset 16
    .cfi_offset %rbx, -16
    subq $16, %rsp
    .cfi_def_cfa_offset 32

    movq %rdi, %rbx
    movq %rsi, 0(%rsp)
    leaq 1(%rbx), %rax
    addq 0(%rsp), %rax

    addq $16, %rsp
    .cfi_def_cfa_offset 16
    popq %rbx
    .cfi_def_cfa_offset 8
    ret
    .cfi_endproc
.size cfi_rsp_sum, .-cfi_rsp_sum

.section .note.GNU-stack,"",@progbits

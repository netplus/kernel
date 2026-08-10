.text

.globl pair_bump
.type pair_bump,@function
pair_bump:
    leaq 1(%rdi), %rax
    leaq 2(%rsi), %rdx
    ret
.size pair_bump, .-pair_bump

.globl big_bump
.type big_bump,@function
big_bump:
    movq 8(%rsp), %rax
    addq $1, %rax
    movq %rax, 0(%rdi)

    movq 16(%rsp), %rax
    addq $2, %rax
    movq %rax, 8(%rdi)

    movq 24(%rsp), %rax
    addq $3, %rax
    movq %rax, 16(%rdi)

    movq %rdi, %rax
    ret
.size big_bump, .-big_bump

.section .note.GNU-stack,"",@progbits

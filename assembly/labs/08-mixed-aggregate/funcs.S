.text
.globl mixed_bump
.type mixed_bump, @function
mixed_bump:
    addsd .LCONE(%rip), %xmm0
    leaq 2(%rdi), %rax
    ret
.size mixed_bump, .-mixed_bump

.section .rodata
.align 8
.LCONE:
    .double 1.0

.section .note.GNU-stack,"",@progbits

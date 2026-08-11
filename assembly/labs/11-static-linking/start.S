    .text
    .globl _start
    .type _start, @function
    .extern combine
_start:
    mov $7, %rdi
    call combine
    mov %rax, %rdi
    mov $60, %rax
    syscall
    .size _start, .-_start

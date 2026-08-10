.section .text
.global _start

_start:
    movq %rsp, %r12
    movq $3, %rdi
    call recursive_sum
    cmpq $6, %rax
    jne fail
    cmpq %r12, %rsp
    jne fail

    movq $60, %rax
    movq $6, %rdi
    syscall

# recursive_sum(n): returns 1+...+n for n >= 0.
# Each non-base invocation saves n before making the recursive call.
recursive_sum:
recursive_entry:
    testq %rdi, %rdi
    je recursive_base

    pushq %rdi
before_recursive_call:
    subq $1, %rdi
    call recursive_sum
after_recursive_call:
    popq %rdi
    addq %rdi, %rax
    ret

recursive_base:
    xorq %rax, %rax
    ret

fail:
    movq $60, %rax
    movq $99, %rdi
    syscall

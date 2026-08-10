    .section .text
    .globl _start

_start:
    movq %rsp, %r15
    xorq %rbx, %rbx

    # 1) register-indirect call: target address lives in R12
    leaq register_target(%rip), %r12
    movq %rsp, %r10
before_register_call:
    call *%r12
after_register_call:
    cmpq %r10, %rsp
    jne fail
    cmpq $17, %rax
    jne fail
    addq %rax, %rbx

    # 2) memory-indirect call: target address is loaded from memory
    movq %rsp, %r11
before_memory_call:
    call *memory_target_ptr(%rip)
after_memory_call:
    cmpq %r11, %rsp
    jne fail
    cmpq $29, %rax
    jne fail
    addq %rax, %rbx

    # Both calls must have restored the original process stack pointer.
    cmpq %r15, %rsp
    jne fail

    # checksum 17 + 29 = 46
    movq %rbx, %rdi
    movq $60, %rax
    syscall

register_target:
register_target_entry:
    movq (%rsp), %r13
    leaq after_register_call(%rip), %r14
    cmpq %r14, %r13
    jne fail_from_callee
    movq $17, %rax
before_register_ret:
    ret

memory_target:
memory_target_entry:
    movq (%rsp), %r13
    leaq after_memory_call(%rip), %r14
    cmpq %r14, %r13
    jne fail_from_callee
    movq $29, %rax
before_memory_ret:
    ret

fail_from_callee:
    # Drop the failed call's return address before leaving through fail.
    addq $8, %rsp
fail:
    movq $99, %rdi
    movq $60, %rax
    syscall

    .section .rodata
    .align 8
memory_target_ptr:
    .quad memory_target

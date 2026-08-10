    .section .text
    .globl _start
    .type _start, @function
_start:
    # 保存调用前 RSP，用于验证 ret 最终是否恢复了栈深度。
    movq %rsp, %r15
    xorq %r12, %r12

    call corrupt_return_address
after_corrupt_call:
    # redirected_target 应当已经执行，并且 RSP 应恢复到调用前值。
    cmpq %r15, %rsp
    jne fail_stack
    cmpq $1, %r12
    jne fail_redirect

    movq $60, %rax
    movq $41, %rdi
    syscall

fail_stack:
    movq $60, %rax
    movq $91, %rdi
    syscall

fail_redirect:
    movq $60, %rax
    movq $92, %rdi
    syscall

    .type corrupt_return_address, @function
corrupt_return_address:
    # 进入函数时，[RSP] 是 call 保存的 after_corrupt_call。
    movq (%rsp), %r13

    # 用当前程序中的合法标签地址替换栈顶返回地址。
    leaq redirected_target(%rip), %rax
    movq %rax, (%rsp)

before_corrupted_ret:
    # ret 会消费被替换后的栈顶值，因此先到 redirected_target。
    ret

redirected_target:
    # 设置观察标志，证明替代路径实际执行。
    movq $1, %r12

    # ret 已经恢复 RSP；这里用 jmp 回到原 continuation，不再消耗栈项。
    jmp *%r13

    .size corrupt_return_address, .-corrupt_return_address
    .size _start, .-_start

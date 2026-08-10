.section .text
.globl _start

_start:
    # 保存进入 _start 时的初始 RSP。
    movq %rsp, %r12

    # 第一次 push：验证 RSP 减少 8 字节，并能从 [RSP] 读回数据。
    movabsq $0x1122334455667788, %rax
    pushq %rax
stack_after_push1:
    movq %rsp, %r13
    movq (%rsp), %rbx

    # 第二次 push：验证 LIFO 布局。
    movabsq $0x99aabbccddeeff00, %rcx
    pushq %rcx
stack_after_push2:
    movq %rsp, %r14
    movq (%rsp), %rdx
    movq 8(%rsp), %r8

    # 两次 pop 应按相反顺序恢复两个值。
    popq %r9
stack_after_pop1:
    popq %r10
stack_after_pop2:

    # 手工保留 16 字节栈空间，使用普通内存寻址读写。
    subq $16, %rsp
manual_after_sub:
    movabsq $0x0102030405060708, %rax
    movq %rax, 8(%rsp)
    movq 8(%rsp), %r11
    addq $16, %rsp
manual_after_add:

    # 自动校验。
    xorq %rdi, %rdi

    cmpq %r12, %rsp
    jne fail

    leaq -8(%r12), %rax
    cmpq %rax, %r13
    jne fail

    leaq -16(%r12), %rax
    cmpq %rax, %r14
    jne fail

    movabsq $0x1122334455667788, %rax
    cmpq %rax, %rbx
    jne fail
    cmpq %rax, %r8
    jne fail

    movabsq $0x99aabbccddeeff00, %rax
    cmpq %rax, %rdx
    jne fail
    cmpq %rax, %r9
    jne fail

    movabsq $0x1122334455667788, %rax
    cmpq %rax, %r10
    jne fail

    movabsq $0x0102030405060708, %rax
    cmpq %rax, %r11
    jne fail

    # 所有检查通过时退出码为 42。
    movq $42, %rdi

fail:
    movq $60, %rax
    syscall

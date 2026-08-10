    .text
    .globl _start
    .type _start,@function

_start:
    # Save the caller-side stack pointer so we can verify that a
    # matching call/ret pair restores it.
    movq %rsp, %r12
    movq $10, %rax

before_direct_call:
    call direct_target
after_direct_call:
    # ret should restore RSP to the value it had before call.
    cmpq %r12, %rsp
    jne fail

    # direct_target adds three to RAX.
    cmpq $13, %rax
    jne fail

    # A distinctive success status; it is only a path check, not a
    # way to expose a full register value.
    movq $37, %rdi
    movq $60, %rax
    syscall

    .type direct_target,@function
direct_target:
direct_target_entry:
    # At function entry, [RSP] must be the return address that CALL
    # pushed.  Compare it with the address immediately after CALL.
    movq (%rsp), %r13
    leaq after_direct_call(%rip), %r14
    cmpq %r14, %r13
    jne corrupt_stack

    addq $3, %rax

before_ret:
    ret

# If the return-address check failed, discard the unexpected stack
# slot before leaving through the common failure path.
corrupt_stack:
    addq $8, %rsp

fail:
    movq $1, %rdi
    movq $60, %rax
    syscall

    .size direct_target, .-direct_target
    .size _start, .-_start

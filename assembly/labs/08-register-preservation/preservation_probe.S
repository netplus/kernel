    .text
    .globl run_preservation_probe
    .type run_preservation_probe, @function
run_preservation_probe:
    # Preserve the C caller's callee-saved registers first. This function is
    # itself a callee and therefore must honor the ABI before using them.
    pushq %rbx
    pushq %rbp
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15

    movabsq $0x1111111111111111, %rbx
    movabsq $0x2222222222222222, %rbp
    movabsq $0x3333333333333333, %r12
    movabsq $0x4444444444444444, %r13
    movabsq $0x5555555555555555, %r14
    movabsq $0x6666666666666666, %r15

    movabsq $0xa0a0a0a0a0a0a0a0, %r10
    movabsq $0xb0b0b0b0b0b0b0b0, %r11

    # On SysV AMD64, RSP is 8 mod 16 on function entry. Six pushes subtract
    # 48 bytes and leave it 8 mod 16, so reserve another 8 bytes before CALL.
    # Then RSP is 0 mod 16 at the call site and clobber_probe enters with
    # RSP 8 mod 16 after CALL pushes the return address.
    subq $8, %rsp
    call clobber_probe
    addq $8, %rsp

    movq %rbx, seen_rbx(%rip)
    movq %rbp, seen_rbp(%rip)
    movq %r12, seen_r12(%rip)
    movq %r13, seen_r13(%rip)
    movq %r14, seen_r14(%rip)
    movq %r15, seen_r15(%rip)
    movq %r10, seen_r10(%rip)
    movq %r11, seen_r11(%rip)

    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbp
    popq %rbx
    ret
    .size run_preservation_probe, .-run_preservation_probe

    .type clobber_probe, @function
clobber_probe:
    # RBX and R12 are callee-saved, so this callee must restore them after use.
    pushq %rbx
    pushq %r12

    movabsq $0xdead000000000001, %rbx
    movabsq $0xdead000000000002, %r12

    # R10/R11 are caller-saved. This callee may overwrite them without
    # restoring their incoming values.
    movabsq $0xaaaaaaaaaaaaaaaa, %r10
    movabsq $0xbbbbbbbbbbbbbbbb, %r11

    popq %r12
    popq %rbx
    ret
    .size clobber_probe, .-clobber_probe

    .bss
    .align 8
    .globl seen_rbx
seen_rbx: .zero 8
    .globl seen_rbp
seen_rbp: .zero 8
    .globl seen_r12
seen_r12: .zero 8
    .globl seen_r13
seen_r13: .zero 8
    .globl seen_r14
seen_r14: .zero 8
    .globl seen_r15
seen_r15: .zero 8
    .globl seen_r10
seen_r10: .zero 8
    .globl seen_r11
seen_r11: .zero 8

    .section .note.GNU-stack,"",@progbits

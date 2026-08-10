.section .data
.globl seen_outer_entry_rsp
seen_outer_entry_rsp:
    .quad 0

.globl seen_pre_nested_call_rsp
seen_pre_nested_call_rsp:
    .quad 0

.globl seen_nested_entry_rsp
seen_nested_entry_rsp:
    .quad 0

.section .text
.globl probe_alignment
.type probe_alignment, @function
probe_alignment:
    movq %rsp, seen_outer_entry_rsp(%rip)

    # At a normal SysV AMD64 function entry, RSP is usually 8 mod 16
    # because call has just pushed an 8-byte return address. Reserve 8
    # bytes so this function's own nested call site is 16-byte aligned.
    subq $8, %rsp
    movq %rsp, seen_pre_nested_call_rsp(%rip)
    call nested_probe
    addq $8, %rsp

    addq $31, %rax
    ret
.size probe_alignment, .-probe_alignment

.type nested_probe, @function
nested_probe:
    movq %rsp, seen_nested_entry_rsp(%rip)
    movq $42, %rax
    ret
.size nested_probe, .-nested_probe

.section .note.GNU-stack,"",@progbits

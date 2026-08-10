.text
.globl red_zone_leaf
.type red_zone_leaf,@function
red_zone_leaf:
    movq %rsp, %r10
    movq $11, -8(%rsp)
    movq $22, -16(%rsp)
    movq $33, -120(%rsp)
    movq -8(%rsp), %rax
    addq -16(%rsp), %rax
    addq -120(%rsp), %rax
    cmpq %r10, %rsp
    jne .Lbad_rsp
    ret
.Lbad_rsp:
    movq $-1, %rax
    ret
.size red_zone_leaf, .-red_zone_leaf

.globl red_zone_call_boundary
.type red_zone_call_boundary,@function
red_zone_call_boundary:
    movabsq $0x1122334455667788, %rax
    movq %rax, -16(%rsp)
    movq -16(%rsp), %r10
    subq $8, %rsp
    call red_zone_nested
    addq $8, %rsp
    movq -16(%rsp), %rax
    cmpq %r10, %rax
    sete %al
    movzbq %al, %rax
    ret
.size red_zone_call_boundary, .-red_zone_call_boundary

.type red_zone_nested,@function
red_zone_nested:
    movq $0x55, -8(%rsp)
    ret
.size red_zone_nested, .-red_zone_nested

.section .note.GNU-stack,"",@progbits

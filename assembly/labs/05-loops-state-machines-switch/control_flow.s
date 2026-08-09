    .section .rodata
values:
    .quad 3, 5, 7, 9

    .section .text
    .globl _start
    .globl after_while
    .globl after_do_while
    .globl after_array_loop
    .globl after_state_machine
    .globl after_switch

_start:
    # while: sum 1..5 = 15
    xorq %rax, %rax
    movq $1, %rcx
.Lwhile_test:
    cmpq $5, %rcx
    jg .Lwhile_done
    addq %rcx, %rax
    incq %rcx
    jmp .Lwhile_test
.Lwhile_done:
after_while:
    movq %rax, %r8

    # do-while: 4 + 3 + 2 + 1 = 10
    xorq %rax, %rax
    movq $4, %rcx
.Ldo_body:
    addq %rcx, %rax
    decq %rcx
    jne .Ldo_body

after_do_while:
    movq %rax, %r9

    # array traversal: 3 + 5 + 7 + 9 = 24
    leaq values(%rip), %rsi
    movq $4, %rcx
    xorq %rax, %rax
.Larray_loop:
    addq (%rsi), %rax
    addq $8, %rsi
    decq %rcx
    jne .Larray_loop

after_array_loop:
    movq %rax, %r10

    # small state machine: 0 -> 1 -> 2 -> done, score = 6
    xorq %rax, %rax
    xorq %rcx, %rcx
.Lstate_dispatch:
    cmpq $0, %rcx
    je .Lstate0
    cmpq $1, %rcx
    je .Lstate1
    cmpq $2, %rcx
    je .Lstate2
    jmp .Lstate_done
.Lstate0:
    addq $1, %rax
    movq $1, %rcx
    jmp .Lstate_dispatch
.Lstate1:
    addq $2, %rax
    movq $2, %rcx
    jmp .Lstate_dispatch
.Lstate2:
    addq $3, %rax
    movq $3, %rcx
    jmp .Lstate_dispatch
.Lstate_done:
after_state_machine:
    movq %rax, %r11

    # dense switch implemented with a relative jump table.
    # selector=4 -> case4 -> 19
    movq $4, %rdi
    leaq .Lswitch_table(%rip), %rdx
    cmpq $5, %rdi
    ja .Lswitch_default
    movslq (%rdx,%rdi,4), %rax
    addq %rdx, %rax
    jmp *%rax

    .p2align 2
.Lswitch_table:
    .long .Lcase0 - .Lswitch_table
    .long .Lcase1 - .Lswitch_table
    .long .Lcase2 - .Lswitch_table
    .long .Lcase3 - .Lswitch_table
    .long .Lcase4 - .Lswitch_table
    .long .Lcase5 - .Lswitch_table

.Lcase0:
    movq $11, %rax
    jmp .Lswitch_done
.Lcase1:
    movq $37, %rax
    jmp .Lswitch_done
.Lcase2:
    movq $4, %rax
    jmp .Lswitch_done
.Lcase3:
    movq $82, %rax
    jmp .Lswitch_done
.Lcase4:
    movq $19, %rax
    jmp .Lswitch_done
.Lcase5:
    movq $55, %rax
    jmp .Lswitch_done
.Lswitch_default:
    xorq %rax, %rax
.Lswitch_done:
after_switch:
    movq %rax, %r12

    # checksum = 15 + 10 + 24 + 6 + 19 = 74
    movq %r8, %rdi
    addq %r9, %rdi
    addq %r10, %rdi
    addq %r11, %rdi
    addq %r12, %rdi
    movq $60, %rax
    syscall

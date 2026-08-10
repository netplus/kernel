.section .text
.global _start
.type _start, @function
_start:
    movq %rsp, %rbx              # save initial RSP

    # Bit 0: initial RSP is 16-byte aligned.
    movq %rsp, %rax
    andq $15, %rax
    sete %r8b
    movzbq %r8b, %r8

    # argc must be 3 for: program alpha beta.
    movq (%rbx), %r12
    cmpq $3, %r12
    sete %r9b
    movzbq %r9b, %r9
    shlq $1, %r9                 # bit 1

    # argv starts at initial_rsp + 8. argv[argc] must be NULL.
    leaq 8(%rbx), %r13
    cmpq $0, (%r13,%r12,8)
    sete %r10b
    movzbq %r10b, %r10
    shlq $2, %r10                # bit 2

    # envp starts after argv[argc] NULL.
    leaq 8(%r13,%r12,8), %r14
    movq %r14, %r15
.Lenv_scan:
    cmpq $0, (%r15)
    je .Lenv_done
    addq $8, %r15
    jmp .Lenv_scan
.Lenv_done:
    # Bit 3: at least one environment pointer existed.
    cmpq %r14, %r15
    setne %r11b
    movzbq %r11b, %r11
    shlq $3, %r11

    # auxv starts after the envp NULL. Each Elf64_auxv_t is (type, value).
    addq $8, %r15
    xorq %rdi, %rdi              # AT_PAGESZ value, 0 until found
.Laux_scan:
    movq 0(%r15), %rax           # a_type
    movq 8(%r15), %rcx           # a_val
    testq %rax, %rax             # AT_NULL == 0
    je .Laux_done
    cmpq $6, %rax                # AT_PAGESZ == 6
    jne .Laux_next
    movq %rcx, %rdi
.Laux_next:
    addq $16, %r15
    jmp .Laux_scan
.Laux_done:
    # Bit 4: reaching this label means AT_NULL terminated the scan.
    movq $16, %rdx

    # Bit 5: AT_PAGESZ existed and had a nonzero value.
    testq %rdi, %rdi
    setne %al
    movzbq %al, %rax
    shlq $5, %rax

    # Success checksum: 1+2+4+8+16+32 = 63.
    orq %r8, %r9
    orq %r10, %r9
    orq %r11, %r9
    orq %rdx, %r9
    orq %rax, %r9

    movq %r9, %rdi
    movq $60, %rax               # SYS_exit
    syscall
.size _start, .-_start

.text

.globl raw_getpid
.type raw_getpid,@function
raw_getpid:
    mov $39, %eax
    syscall
    ret
.size raw_getpid, .-raw_getpid

.globl raw_invalid_syscall
.type raw_invalid_syscall,@function
raw_invalid_syscall:
    mov $0x7fffffff, %eax
    syscall
    ret
.size raw_invalid_syscall, .-raw_invalid_syscall

.globl raw_mmap
.type raw_mmap,@function
raw_mmap:
    mov %rcx, %r10
    mov $9, %eax
    syscall
    ret
.size raw_mmap, .-raw_mmap

.globl raw_getpid_state
.type raw_getpid_state,@function
raw_getpid_state:
    push %r12
    push %r13
    mov %rdi, %r12
    mov %rsi, %r13
    pushfq
    pop %rdx
    mov %rdx, 0(%r12)
    mov $39, %eax
    syscall
    mov %rcx, 8(%r12)
    mov %r11, 16(%r12)
    pushfq
    pop %rdx
    mov %rdx, 24(%r12)
    mov %rax, (%r13)
    pop %r13
    pop %r12
    ret
.size raw_getpid_state, .-raw_getpid_state

.section .note.GNU-stack,"",@progbits
